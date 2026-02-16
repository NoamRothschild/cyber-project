from __future__ import annotations
import asyncio
from typing import Any, List, Optional
from constants import TICK_INTERVAL_SEC, WHOLE_MAP_X_RANGE, WHOLE_MAP_Y_RANGE
from region_node import RegionNode

nodes: List[RegionNode] = []


def get_client(session_id: int) -> Optional[Any]:
    """Return the Client for session_id if connected to any node."""
    for node in nodes:
        if session_id in node.clients:
            return node.clients[session_id]
    return None


def _create_initial_nodes() -> None:
    """Create the single whole-map node. Call once at startup."""
    nodes.append(RegionNode(x_range=WHOLE_MAP_X_RANGE, y_range=WHOLE_MAP_Y_RANGE))


def start_global_tick_loop() -> None:
    """One global tick loop: each tick, call tick() on every node's projectile handler."""

    async def _ticker() -> None:
        loop = asyncio.get_running_loop()
        while True:
            start_time = loop.time()
            for node in nodes:
                await node.projectile_handler.tick()
            sleep_time = TICK_INTERVAL_SEC - (loop.time() - start_time)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    asyncio.create_task(_ticker())


# Create the one region node (whole map) when this module loads
_create_initial_nodes()
