from __future__ import annotations
from typing import Dict, Tuple, Union
import os

BUFF_SIZE = 1024
THIS_SERVER_IP = os.getenv('region_server_ip', '127.0.0.2')
print(f'{THIS_SERVER_IP=}')

# 60Hz tick rate
TICK_INTERVAL_SEC = 1.0 / 60

CLIENT_WIDTH = 1500
CLIENT_HEIGHT = 750
CLIENT_RECEIVE_WIDTH = CLIENT_WIDTH * 1.5
CLIENT_RECEIVE_HEIGHT = CLIENT_HEIGHT * 1.5
CLIENT_ASPECT_RATIO = CLIENT_WIDTH / CLIENT_HEIGHT

# TODO: might parse this from a bullets config json file
BULLET_TYPES: Dict[str, Dict[str, Union[int, float]]] = {
    "Ak-7": {
        "ttl": 50,
        "speed": 20,
        "damage": 1,
        "range": 50,
    }
}
