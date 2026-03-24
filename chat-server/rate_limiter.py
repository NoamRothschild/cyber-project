import asyncio
import time
from collections import defaultdict, deque
from typing import Dict
DOS_THRESHOLD = 20 # connection attempts
DELETE_AFTER = 20 # seconds

IP_TYPE = str
QUEUE_ENTRY = float # time of connection

lock = asyncio.Lock()
attempts: Dict[IP_TYPE, deque] = defaultdict(deque)


async def received_conn(ip: str) -> bool:
    """
    Records a connection attempt and returns False if the rate limit is exceeded
    Example usage:

    print("Received connection")
    if not received_conn(ip):
        return # ignore connection, likely a DOS attack
    """
    global lock, attempts

    now = time.time()
    async with lock:
        # remove old connection attempt entries if expired
        while len(attempts[ip]) > 0:
            head: QUEUE_ENTRY = attempts[ip][0]
            if now - head <= DELETE_AFTER:
                break
            attempts[ip].popleft()

        attempts[ip].append(now)
        if len(attempts[ip]) >= DOS_THRESHOLD:
            return False
    return True


def user_ip(user_writer: asyncio.StreamWriter) -> IP_TYPE:
    return user_writer.get_extra_info("peername")[0]


async def should_continue(user_writer: asyncio.StreamWriter) -> bool:
    return await received_conn(user_ip(user_writer))