# Handles communication between multiple region servers
from __future__ import annotations
from typing import cast
import redis
from config import ZONE_HOSTS, REDIS_HOST
REDIS_PORT = 6379


class RedisSingleton:
    _instance: None | RedisSingleton = None
    redis_conn: redis.Redis | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisSingleton, cls).__new__(cls)
            cls.redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        return cls._instance


def get_redis() -> redis.Redis:
    return cast(redis.Redis, RedisSingleton().redis_conn)

