from __future__ import annotations
from typing import Dict, Tuple, Union

BUFF_SIZE = 1024
THIS_SERVER_IP = '127.0.0.1' # TODO: move to somewhere else

# 60Hz tick rate
TICK_INTERVAL_SEC = 1.0 / 60

# TODO: might parse this from a bullets config json file
BULLET_TYPES: Dict[str, Dict[str, Union[int, float]]] = {
    "Ak-7": {
        "ttl": 50,
        "speed": 20,
        "damage": 1,
        "range": 50,
    }
}
