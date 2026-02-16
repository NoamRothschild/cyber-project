from __future__ import annotations
from typing import Dict, Tuple, Union

BUFF_SIZE = 1024

# 60Hz tick rate
TICK_INTERVAL_SEC = 1.0 / 60

# Bounds for the single "whole map" region node (for now one node covers everything)
WHOLE_MAP_X_RANGE: Tuple[int, int] = (-(10**6), 10**6)
WHOLE_MAP_Y_RANGE: Tuple[int, int] = (-(10**6), 10**6)

# TODO: might parse this from a bullets config json file
BULLET_TYPES: Dict[str, Dict[str, Union[int, float]]] = {
    "Ak-7": {
        "ttl": 50,
        "speed": 20,
        "damage": 1,
        "range": 50,
    }
}
