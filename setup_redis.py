import os
import redis
from region_server.config import REDIS_PASSWORD
REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))

# region server -> handled nodes
REGION_SERVERS = {
    # "0": [i for i in range(340) if i % 5 == 0],
    # "1": [i for i in range(340) if i % 5 == 1],
    # "2": [i for i in range(340) if i % 5 == 2],
    # "3": [i for i in range(340) if i % 5 == 3],
    # "4": [i for i in range(340) if i % 5 == 4],

    # "0": [i for i in range(340) if i % 2 == 0],
    # "1": [i for i in range(340) if i % 2 == 1],

    "0": [i for i in range(340)],
}

if __name__ == "__main__":
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, decode_responses=True)

    r.delete('server_ids')
    r.sadd('server_ids', *(REGION_SERVERS.keys()))
    for region_server, nodes in REGION_SERVERS.items():
        region_key = f'region:{region_server}'
        r.delete(region_key)
        r.sadd(region_key, *nodes)

    print("Done setting up redis!")