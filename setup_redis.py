import redis
from region_server.config import REDIS_HOST
REDIS_PORT = 6379

# region server -> handled nodes
REGION_SERVERS = {
    "127.0.0.1": [i for i in range(340)],

    # "192.168.1.1",
    # ...
}

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

r.delete('server_ips')
r.sadd('server_ips', *(REGION_SERVERS.keys()))
for region_server, nodes in REGION_SERVERS.items():
    region_key = f'region:{region_server}'
    r.delete(region_key)
    r.sadd(region_key, *nodes)

print("Done setting up redis!")