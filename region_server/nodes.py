from __future__ import annotations
from typing import Dict, Tuple, TYPE_CHECKING
import asyncio

if TYPE_CHECKING:
    from region_node import RegionNode
    from region_server_extras import Client
    import protobuf.region_net_pb2 as region_net

nodes: Dict[Tuple[int, int], RegionNode] = {}

connected_clients: Dict[int, Client] = {}
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
