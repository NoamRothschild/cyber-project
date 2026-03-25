from __future__ import annotations
import asyncio
from typing import Any, Dict, List, Optional, Tuple, cast, Set
from constants import TICK_INTERVAL_SEC, THIS_SERVER_ID
from region_node import RegionNode, HORIZONAL_NODE_COUNT
from nodes import NODE_SLOT_COUNT, iter_local_nodes, local_region_nodes, nodes
from servers_communication import get_redis, get_pubsub, GLOBAL_CHANNEL, SERVER_PUBLIC_RECV


async def create_initial_nodes() -> None:
    """Create the single whole-map node. Call once at startup."""
    r = get_redis()
    my_nodes = await r.smembers(f"region:{THIS_SERVER_ID}")
    ps = get_pubsub()

    local_region_nodes.clear()
    for node_idx_raw in cast(Set[bytes], my_nodes):
        node_idx = int(node_idx_raw)
        x = node_idx % HORIZONAL_NODE_COUNT
        y = node_idx // HORIZONAL_NODE_COUNT
        rn = RegionNode(
            (x * RegionNode.NODE_WIDTH, y * RegionNode.NODE_HEIGHT)
        )
        nodes[node_idx] = rn
        local_region_nodes.append(rn)
        await ps.subscribe(node_idx_raw)
        print(f"initiliazed node at pos {x, y}")
    await ps.subscribe(SERVER_PUBLIC_RECV)
    await ps.subscribe(GLOBAL_CHANNEL)


def start_global_tick_loop() -> None:
    """One global tick loop: each tick, call tick() on every node's projectile handler."""

    async def _ticker() -> None:
        loop = asyncio.get_running_loop()
        cycle = 0

        FPS_SEND_INTERVAL_SEC = 2.0
        ticked_since_last_sent = 0
        last_sent_wall = loop.time()
        while True:
            cycle += 1
            start_time = loop.time()
            try:
                for node in iter_local_nodes():
                    for client in list(node.potion_clients.values()):
                        await client.tick(cycle)
                    await node.enemy_handler.tick(cycle)
                    await node.projectile_handler.tick(cycle)
                    await node.enemy_handler.ensure_population()
            except Exception as e:
                print(f"[ERROR] tick {cycle} failed: {e}")
                import traceback
                traceback.print_exc()

            elapsed = loop.time() - start_time
            sleep_time = TICK_INTERVAL_SEC - elapsed
            ticked_since_last_sent += 1

            wall_now = loop.time()
            if wall_now - last_sent_wall >= FPS_SEND_INTERVAL_SEC:
                elapsed_sec = wall_now - last_sent_wall
                fps = int(ticked_since_last_sent / elapsed_sec) if elapsed_sec > 0 else 0
                last_sent_wall = wall_now
                ticked_since_last_sent = 0
                for node in iter_local_nodes():
                    for cli in node.clients.values():
                        await cli.send_fps(fps)

            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
                #print(f"[INFO] tick {cycle} took {elapsed*1000:.3f}ms")
            else:
                #print(f"[WARN] tick {cycle} OVERRAN by {-sleep_time*1000:.1f}ms (elapsed={elapsed:.3f}s)")
                await asyncio.sleep(0)  # yield to event loop to prevent I/O starvation

    asyncio.create_task(_ticker())

