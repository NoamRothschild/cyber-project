import time
from collections import defaultdict, deque
from typing import Dict
DOS_THRESHOLD = 20 # connection attempts
DELETE_AFTER = 20 # seconds

IP_TYPE = str
QUEUE_ENTRY = float # time of connection

attempts: Dict[IP_TYPE, deque] = defaultdict(deque)


def received_conn(ip: str) -> bool:
    """
    Records a connection attempt and returns False if the rate limit is exceeded
    Example usage:

    print("Received connection")
    if not received_conn(ip):
        return # ignore connection, likely a DOS attack
    """
    global attempts

    now = time.time()
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


def should_continue(user_addr) -> bool:
    return received_conn(user_addr[0])