from __future__ import annotations
from typing import Dict, Tuple, Union
import os

BUFF_SIZE = 1024
THIS_SERVER_IP = os.getenv("region_server_ip", "127.0.0.1")
print(f"{THIS_SERVER_IP=}")
SERVER_COUNT = 5

# for collision checking
ITEM_WIDTH = 50
ITEM_HEIGHT = 50
PLAYER_WIDTH = 50
PLAYER_HEIGHT = 80

# 60Hz tick rate
TICK_INTERVAL_SEC = 1.0 / 60

CLIENT_WIDTH = 1500
CLIENT_HEIGHT = 750
CLIENT_RECEIVE_WIDTH = CLIENT_WIDTH * 1.5
CLIENT_RECEIVE_HEIGHT = CLIENT_HEIGHT * 1.5
CLIENT_ASPECT_RATIO = CLIENT_WIDTH / CLIENT_HEIGHT

MIN_DIST_SQR_FOR_ITEM_DROP = 100 ** 2
MAX_DIST_FOR_ITEM_DROP = 100

# TODO: might parse this from a bullets config json file
BULLET_TYPES: Dict[str, Dict[str, Union[int, float]]] = {
    "AK 47 bullets": {
        "ttl": 50,
        "speed": 20,
        "damage": 40,
        "range": 50,
    },
    "arrows": {
        "ttl": 50,
        "speed": 20,
        "damage": 50,
        "range": 50,
    },
    "sword hit":{
        "ttl": 5,
        "speed": 4,
        "damage": 60,
        "range": 80,
    },
    "Pistol bullets":{
        "ttl": 10,
        "speed": 19,
        "damage": 30,
        "range": 50,
    },
    "Assault rifle bullets":{
        "ttl": 15,
        "speed": 30,
        "damage": 25,
        "range": 50,
    }
}
