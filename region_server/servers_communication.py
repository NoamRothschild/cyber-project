# Handles communication between multiple region servers
from __future__ import annotations
import redis
from redis.asyncio.client import Redis, PubSub
import asyncio
import protobuf.region_net_pb2 as region_net
import os
from config import REDIS_PASSWORD
from nodes import get_global_client

REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = 6379


class RedisSingleton:
    _instance: None | RedisSingleton = None
    redis_conn: Redis
    pubsub: PubSub

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisSingleton, cls).__new__(cls)
            cls.redis_conn = Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, decode_responses=False)
            cls.pubsub = cls.redis_conn.pubsub()

        return cls._instance


def get_redis() -> Redis:
    return RedisSingleton().redis_conn

def get_pubsub() -> PubSub:
    return RedisSingleton().pubsub

BROADCAST_PREFIX = b'BRD'
PROXY_CREATE_PREFIX = b'PRX'
PROXY_REMOVE_PREFIX = b'PRM'
NOTIFY_CLIENT_PREFIX = b'NFY'
SERVER_PUBLIC_RECV = f'REGION:{os.getenv("SERVER_ID", "0")}'.encode() # sent here are packets specifically for THIS region server (not node specific)
GLOBAL_CHANNEL = b'global'

async def broadcast_on(node_idx: str, message: bytes):
    await get_redis().publish(node_idx, BROADCAST_PREFIX + message)

async def create_proxy_on(node_idx: str, message: bytes):
    await get_redis().publish(node_idx, PROXY_CREATE_PREFIX + message)

async def remove_proxy_on(node_idx: str, message: bytes):
    await get_redis().publish(node_idx, PROXY_REMOVE_PREFIX + message)

async def notify_server(server_id: int | str, message: bytes):
    await get_redis().publish(f'REGION:{server_id}', message)

async def notify_client_with(node_idx: str, message: region_net.ServerResponse):
    message_bytes = message.SerializeToString()
    await get_redis().publish(node_idx, NOTIFY_CLIENT_PREFIX + message_bytes)

async def publish_proxy_remove_global(sender_id: int, session_id: int) -> None:
    """Publish client proxy remove to GLOBAL_CHANNEL so all servers (including remote) run receive_proxy_remove."""
    event = region_net.ProxyEvent(
        client=region_net.ClientProxy(player_id=sender_id, session_id=session_id)
    )
    await get_redis().publish(GLOBAL_CHANNEL, PROXY_REMOVE_PREFIX + event.SerializeToString())

def start_redis_listener() -> None:
    """Must be called after initializing the node list"""

    async def listener() -> None:
        from region_node import HORIZONAL_NODE_COUNT
        from nodes import nodes, update_global_client_state, remove_global_client
        from region_server_extras import Client, NULL_NODE, load_player_stats_from_redis
        ps = get_pubsub()
        while True:
            msg = await ps.get_message(ignore_subscribe_messages=True, timeout=None)
            if not msg:
                continue
            if msg['type'] != 'message':
                continue

            data: bytes = msg['data']
            channel: bytes = msg['channel']

            if channel == GLOBAL_CHANNEL:
                if data.startswith(PROXY_REMOVE_PREFIX):
                    event = region_net.ProxyEvent()
                    event.ParseFromString(data[len(PROXY_REMOVE_PREFIX):])
                    if event.HasField("client"):
                        for node in nodes.values():
                            await node.receive_proxy_remove(event.client.player_id, "Client")
                    elif event.HasField("enemy"):
                        for node in nodes.values():
                            await node.receive_proxy_remove(event.enemy.player_id, "Enemy")
                continue
            elif channel.startswith(b"REGION:"):
                # TODO: make this allow for more types of server notifications
                cli_session = int(data.removeprefix(b'cli:'))
                cli = await get_global_client(cli_session)
                if not cli:
                    continue
                stats = await load_player_stats_from_redis(cli.user_id)
                cli.state.hp = stats["health"]
                cli.state.weapons = stats["weapons"]
                cli.state.ammo = stats["ammo"]
                cli.state.potions = stats["potions"]
                continue

            node_pos =  (
                int(channel) % HORIZONAL_NODE_COUNT,
                int(channel) // HORIZONAL_NODE_COUNT
            )

            if data.startswith(PROXY_CREATE_PREFIX):
                # print(f"got proxy create event to {node_pos}")
                event = region_net.ProxyEvent()
                event.ParseFromString(data[len(PROXY_CREATE_PREFIX):])
                if node := nodes.get(node_pos):
                    await node.receive_proxy_event(event)
                    if event.HasField("client"):
                        await update_global_client_state(event.client.session_id, event.client)

            elif data.startswith(PROXY_REMOVE_PREFIX):
                event = region_net.ProxyEvent()
                event.ParseFromString(data[len(PROXY_REMOVE_PREFIX):])
                if node := nodes.get(node_pos):
                    if event.HasField("client"):
                        await node.receive_proxy_remove(event.client.player_id)

            elif data.startswith(NOTIFY_CLIENT_PREFIX):
                node = nodes.get(node_pos)
                if not node:
                    continue
                update = region_net.ServerResponse()
                update.ParseFromString(data[len(PROXY_REMOVE_PREFIX):])
                to_client = update.sender_id
                client: Client = None
                for cli_id, cli in node.clients.items():
                    if cli_id != to_client:
                        continue
                    client = cli
                    break
                if client is None:
                    continue
                if update.HasField("enemy_data"):
                    update.sender_id = update.enemy_data.player_id
                await client.write(update.SerializeToString())

            elif data.startswith(BROADCAST_PREFIX):
                update = region_net.RegionUpdate()
                update.ParseFromString(data[len(BROADCAST_PREFIX):])
                if node := nodes.get(node_pos):
                    payload_type = update.WhichOneof('payload')
                    print(f"got update of type {payload_type} to {node.node_pos}")

                    if payload_type == 'bullet_shot':
                        bs = update.bullet_shot
                        dummy = Client(
                            reader=None,
                            writer=None,
                            session_id=None,
                            user_id=update.sender_id,
                            node=NULL_NODE,
                            stats={
                                "health": 400,
                                "spawn_x": bs.x or 0,
                                "spawn_y": bs.y or 0,
                                "weapons": [0] * 10,
                                "ammo": [30] * 10,
                                "potions": [0] * 10,
                            },
                        )
                        dummy.state.x = bs.x
                        dummy.state.y = bs.y
                        update_bytes, new_projs = await node.projectile_handler.add(bs, dummy)
                        if not update_bytes:
                            continue
                        
                        for proj in new_projs:
                            for cli in node.clients.values():
                                proj["seen_by"].add(cli.user_id)
                        # await node.projectile_handler.broadcast_to_adjacent(new_projs)

                        for cli in node.clients.values():
                            if cli.user_id == update.sender_id:
                                continue
                            if cli.user_id in bs.seen_players:
                                continue
                            try:
                                await cli.write(update_bytes)
                            except Exception as e:
                                print(f"Failed to relay bullet to {cli.user_id}: {e}")
                    # TODO: handle location_block from external servers
    
    asyncio.create_task(listener())