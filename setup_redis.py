import os
import redis
from region_server.config import REDIS_PASSWORD

REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))

# region server -> handled nodes
REGION_SERVERS_TESTING = {
    # "0": [i for i in range(340) if i % 5 == 0],
    # "1": [i for i in range(340) if i % 5 == 1],
    # "2": [i for i in range(340) if i % 5 == 2],
    # "3": [i for i in range(340) if i % 5 == 3],
    # "4": [i for i in range(340) if i % 5 == 4],

    # "0": [i for i in range(340) if i % 2 == 0],
    # "1": [i for i in range(340) if i % 2 == 1],

    "0": [i for i in range(340)],
}
REGION_SERVERS_LOCAL = REGION_SERVERS_TESTING

REGION_SERVERS_PROD_OPTIMIZED_LAYOUT = {
    # core / center
    "0": [8, 25, 42, 59, 76, 93, 109, 110, 111, 125, 126, 127, 128, 129, 142, 143, 144, 145, 146, 153, 154, 155, 156,
          157, 158, 159, 160, 161, 162, 163, 164, 165, 166, 167, 168, 169, 176, 177, 178, 179, 180, 193, 194, 195, 196,
          197, 210, 211, 212, 213, 214, 228, 229, 230, 246, 263, 280, 297, 314, 331],

    # top left
    "1": [0, 1, 2, 3, 4, 5, 6, 7, 17, 18, 19, 20, 21, 22, 23, 24, 34, 35, 36, 37, 38, 39, 40, 41, 51, 52, 53, 54, 55,
          56, 57, 58, 68, 69, 70, 71, 72, 73, 74, 75, 85, 86, 87, 88, 89, 90, 91, 92, 102, 103, 104, 105, 106, 107, 108,
          119, 120, 121, 122, 123, 124, 136, 137, 138, 139, 140, 141],

    # top right
    "2": [9, 10, 11, 12, 13, 14, 15, 16, 26, 27, 28, 29, 30, 31, 32, 33, 43, 44, 45, 46, 47, 48, 49, 50, 60, 61, 62, 63,
          64, 65, 66, 67, 77, 78, 79, 80, 81, 82, 83, 84, 94, 95, 96, 97, 98, 99, 100, 101, 112, 113, 114, 115, 116,
          117, 118, 130, 131, 132, 133, 134, 135, 147, 148, 149, 150, 151, 152],

    # bottom left
    "3": [170, 171, 172, 173, 174, 175, 187, 188, 189, 190, 191, 192, 204, 205, 206, 207, 208, 209, 221, 222, 223, 224,
          225, 226, 227, 238, 239, 240, 241, 242, 243, 244, 245, 255, 256, 257, 258, 259, 260, 261, 262, 272, 273, 274,
          275, 276, 277, 278, 279, 289, 290, 291, 292, 293, 294, 295, 296, 306, 307, 308, 309, 310, 311, 312, 313, 323,
          324, 325, 326, 327, 328, 329, 330],

    # bottom right
    "4": [181, 182, 183, 184, 185, 186, 198, 199, 200, 201, 202, 203, 215, 216, 217, 218, 219, 220, 231, 232, 233, 234,
          235, 236, 237, 247, 248, 249, 250, 251, 252, 253, 254, 264, 265, 266, 267, 268, 269, 270, 271, 281, 282, 283,
          284, 285, 286, 287, 288, 298, 299, 300, 301, 302, 303, 304, 305, 315, 316, 317, 318, 319, 320, 321, 322, 332,
          333, 334, 335, 336, 337, 338, 339],
}

REGION_SERVERS = REGION_SERVERS_LOCAL  # TODO: change this to PROD when in school
if __name__ == "__main__":
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, decode_responses=True)

    r.delete('server_ids')
    r.sadd('server_ids', *(REGION_SERVERS.keys()))
    for region_server, nodes in REGION_SERVERS.items():
        region_key = f'region:{region_server}'
        r.delete(region_key)
        r.sadd(region_key, *nodes)

    print("Done setting up redis!")
