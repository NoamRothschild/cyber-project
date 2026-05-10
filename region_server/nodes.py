from __future__ import annotations

import asyncio
from typing import Iterator, Optional, Tuple, TYPE_CHECKING

import protobuf.region_net_pb2 as region_net

if TYPE_CHECKING:
    from region_node import RegionNode
    from region_server_extras import Client

# Must match region_node.HORIZONAL_NODE_COUNT and VERTICAL_NODE_COUNT
HORIZONAL_NODE_COUNT = 17
VERTICAL_NODE_COUNT = 20
NODE_SLOT_COUNT = HORIZONAL_NODE_COUNT * VERTICAL_NODE_COUNT


def node_index(pos_x: int, pos_y: int) -> int:
    return pos_y * HORIZONAL_NODE_COUNT + pos_x


nodes: list[Optional["RegionNode"]] = [None] * NODE_SLOT_COUNT
local_region_nodes: list["RegionNode"] = []


def get_node_at(node_pos: Tuple[int, int]) -> Optional["RegionNode"]:
    x, y = node_pos
    if not (0 <= x < HORIZONAL_NODE_COUNT and 0 <= y < VERTICAL_NODE_COUNT):
        return None
    return nodes[node_index(x, y)]


def iter_local_nodes() -> Iterator["RegionNode"]:
    """Iterate nodes owned by this server process (same order as registration)."""
    return iter(local_region_nodes)


connected_clients: dict[int, "Client"] = {}
connected_clients_lock = asyncio.Lock()


async def get_global_client(session_id: int) -> Client | None:
    async with connected_clients_lock:
        return connected_clients.get(session_id)


async def register_global_client(session_id: int, client: Client):
    async with connected_clients_lock:
        connected_clients[session_id] = client


async def remove_global_client(session_id: int):
    async with connected_clients_lock:
        if session_id not in connected_clients.keys():
            return
        del connected_clients[session_id]


async def update_global_client_state(session_id: int, new_state: region_net.ClientProxy):
    """To be used by a proxy"""
    from region_node import RegionNode

    async with connected_clients_lock:
        cli = connected_clients.get(session_id)
        if cli is None:
            return
        cli.state.hp = new_state.HP # TODO: make sure HP is always set
        cli.state.x = new_state.pos.x
        cli.state.y = new_state.pos.y

        node_pos = RegionNode.which_node(new_state.pos.x, new_state.pos.y)
        origin_x = node_pos[0] * RegionNode.NODE_WIDTH
        origin_y = node_pos[1] * RegionNode.NODE_HEIGHT
        cli.state.cell_x = (new_state.pos.x - origin_x) // RegionNode.CELL_SIZE
        cli.state.cell_y = (new_state.pos.y - origin_y) // RegionNode.CELL_SIZE
        print(f"updated global client state for {session_id} to {cli.state}")
