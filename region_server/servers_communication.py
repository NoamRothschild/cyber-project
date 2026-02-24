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
async def broadcast_on(node_idx: str, message: bytes):
    await get_redis().publish(node_idx, BROADCAST_PREFIX + message)

    
def start_redis_listener() -> None:
    """Must be called after initializing the node list"""

    async def listener() -> None:
        from region_node import HORIZONAL_NODE_COUNT, nodes
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

            if data.startswith(BROADCAST_PREFIX):
                update = region_net.RegionUpdate()
                update.ParseFromString(data[len(BROADCAST_PREFIX):])
                if node := nodes.get(node_pos):
                    print(f"got update of type {update.WhichOneof('payload')} to {node.node_pos}")
                    pass # TODO: a system for handling events from outside the node
    
    asyncio.create_task(listener())