from __future__ import annotations
import asyncio
from typing import Any, Dict, List, Optional, Tuple, cast, Set
from constants import TICK_INTERVAL_SEC, THIS_SERVER_IP
from region_node import RegionNode, HORIZONAL_NODE_COUNT
from nodes import nodes
from servers_communication import get_redis, get_pubsub, GLOBAL_CHANNEL


async def create_initial_nodes() -> None:
    """Create the single whole-map node. Call once at startup."""
    r = get_redis()
    my_nodes = await r.smembers(f'region:{THIS_SERVER_IP}')
    ps = get_pubsub()

    for node_idx_raw in cast(Set[bytes], my_nodes):
        node_idx = int(node_idx_raw)
        x = node_idx % HORIZONAL_NODE_COUNT
        y = node_idx // HORIZONAL_NODE_COUNT
        nodes[(x, y)] = RegionNode(
            (x * RegionNode.NODE_WIDTH, y * RegionNode.NODE_HEIGHT)
        )
        await ps.subscribe(node_idx_raw)
        print(f"initiliazed node at pos {x, y}")

    await ps.subscribe(GLOBAL_CHANNEL)


def start_global_tick_loop() -> None:
    """One global tick loop: each tick, call tick() on every node's projectile handler."""

    async def _ticker() -> None:
        loop = asyncio.get_running_loop()
        cycle = 0
        while True:
            cycle += 1
            start_time = loop.time()
            try:
                for node in nodes.values():
                    await node.projectile_handler.tick(cycle)
                    await node.tick2(cycle)
            except Exception as e:
                print(f"[ERROR] tick {cycle} failed: {e}")
            sleep_time = TICK_INTERVAL_SEC - (loop.time() - start_time)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    asyncio.create_task(_ticker())