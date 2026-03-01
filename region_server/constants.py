from __future__ import annotations
from typing import Dict, Tuple, Union

BUFF_SIZE = 1024
THIS_SERVER_IP = '127.0.0.1' # TODO: move to somewhere else

# 60Hz tick rate
TICK_INTERVAL_SEC = 1.0 / 60

CLIENT_WIDTH = 1500
CLIENT_HEIGHT = 750
CLIENT_RECEIVE_WIDTH = CLIENT_WIDTH * 1.5
CLIENT_RECEIVE_HEIGHT = CLIENT_HEIGHT * 1.5
CLIENT_ASPECT_RATIO = CLIENT_WIDTH / CLIENT_HEIGHT

# TODO: might parse this from a bullets config json file
BULLET_TYPES: Dict[str, Dict[str, Union[int, float]]] = {
    "AK-7_bullet": {
        "ttl": 50,
        "speed": 20,
        "damage": 25,
        "range": 50,
    },
    "arrow": {
        "ttl": 50,
        "speed": 20,
        "damage": 50,
        "range": 50,
    }

}
