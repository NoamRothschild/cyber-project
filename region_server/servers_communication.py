# Handles communication between multiple region servers
from __future__ import annotations
from typing import cast
import redis
from redis.asyncio.client import Redis, PubSub
from config import ZONE_HOSTS, REDIS_HOST
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