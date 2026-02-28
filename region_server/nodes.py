from __future__ import annotations
from typing import Dict, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from region_node import RegionNode

nodes: Dict[Tuple[int, int], RegionNode] = {}
