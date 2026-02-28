# Handles communication between multiple region servers
from __future__ import annotations
import redis
from redis.asyncio.client import Redis, PubSub
import asyncio
import protobuf.region_net_pb2 as region_net
from config import REDIS_HOST
REDIS_PORT = 6379


class RedisSingleton:
    _instance: None | RedisSingleton = None
    redis_conn: Redis
    pubsub: PubSub

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisSingleton, cls).__new__(cls)
            cls.redis_conn = Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=False)
            cls.pubsub = cls.redis_conn.pubsub()

        return cls._instance


def get_redis() -> Redis:
    return RedisSingleton().redis_conn

def get_pubsub() -> PubSub:
    return RedisSingleton().pubsub

BROADCAST_PREFIX = b'BRD'
PROXY_CREATE_PREFIX = b'PRX'
async def broadcast_on(node_idx: str, message: bytes):
    await get_redis().publish(node_idx, BROADCAST_PREFIX + message)

async def create_proxy_on(node_idx: str, message: bytes):
    await get_redis().publish(node_idx, PROXY_CREATE_PREFIX + message)

def start_redis_listener() -> None:
    """Must be called after initializing the node list"""

    async def listener() -> None:
        from region_node import HORIZONAL_NODE_COUNT
        from nodes import nodes
        ps = get_pubsub()
        while True:
            msg = await ps.get_message(ignore_subscribe_messages=True, timeout=None)
            if not msg:
                continue
            if msg['type'] != 'message':
                continue

            data: bytes = msg['data']
            channel: bytes = msg['channel']
            node_pos =  (
                int(channel) % HORIZONAL_NODE_COUNT,
                int(channel) // HORIZONAL_NODE_COUNT
            )

            if data.startswith(PROXY_CREATE_PREFIX):
                update = region_net.RegionUpdate()
                update.ParseFromString(data[len(PROXY_CREATE_PREFIX):])
                if node := nodes.get(node_pos):
                    await node.receive_proxy_event(update)

            if data.startswith(BROADCAST_PREFIX):
                update = region_net.RegionUpdate()
                update.ParseFromString(data[len(BROADCAST_PREFIX):])
                if node := nodes.get(node_pos):
                    payload_type = update.WhichOneof('payload')
                    print(f"got update of type {payload_type} to {node.node_pos}")

                    if payload_type == 'bullet_shot':
                        bs = update.bullet_shot
                        resp = region_net.ServerResponse(sender_id=update.sender_id)
                        resp.bullet_shot.add(
                            gun_type=bs.gun_type,
                            angle=bs.angle,
                            count=bs.count,
                            x=bs.x,
                            y=bs.y,
                            ttl=bs.ttl,
                            speed=bs.speed,
                        )
                        relay_data = resp.SerializeToString()
                        for cli in node.clients.values():
                            try:
                                await cli.write(relay_data)
                            except Exception as e:
                                print(f"Failed to relay bullet to {cli.user_id}: {e}")
                    # TODO: handle location_block from external servers
    
    asyncio.create_task(listener())