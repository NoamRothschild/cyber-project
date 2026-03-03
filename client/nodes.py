import redis
from config import REDIS_HOST
from mapset import NODE_WIDTH, NODE_HEIGHT, HORIZONAL_NODE_COUNT
from typing import Dict, Tuple

# NOTE: our client WILL NOT CONNECT TO REDIS IN THE FUTURE. instead, these values will get hard coded.

REDIS_PORT = 6379


def fetch_zone_map() -> Dict[int, str]:
    """Fetch from Redis and return a dict mapping zone index -> host string."""
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    server_ips = r.smembers('server_ips')
    zone_map: Dict[int, str] = {}
    for ip in server_ips:
        node_indices = r.smembers(f'region:{ip}')
        for idx in node_indices:
            zone_map[int(idx)] = ip
    return zone_map


def pos_to_node(x: int, y: int) -> Tuple[int, int]:
    """Convert raw world position to (node_x, node_y)."""
    return (x // NODE_WIDTH, y // NODE_HEIGHT)


def pos_to_zone_index(x: int, y: int) -> int:
    """Convert raw world position to a flat zone index."""
    node_x, node_y = pos_to_node(x, y)
    return node_y * HORIZONAL_NODE_COUNT + node_x
