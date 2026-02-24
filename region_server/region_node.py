from __future__ import annotations
from typing import Any, Dict, Tuple, Set
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from region_server_extras import Client

import math
from projectiles import ProjectileHandler
import protobuf.region_net_pb2 as region_net

nodes: Dict[Tuple[int, int], RegionNode] = {}

VERTICAL_NODE_COUNT = 20
HORIZONAL_NODE_COUNT = 17


class RegionNode:
    NODE_WIDTH = 4600  # [px]
    NODE_HEIGHT = 2200  # [px]
    CELL_SIZE = 200  # [px]

    def __init__(self, topleft: Tuple[int, int]) -> None:
        self.topleft = topleft
        self.view = f'{topleft[0] // RegionNode.NODE_WIDTH, topleft[1] // RegionNode.NODE_HEIGHT}'
        self.x_range = (topleft[0], topleft[0] + RegionNode.NODE_WIDTH)
        self.y_range = (topleft[1], topleft[1] + RegionNode.NODE_HEIGHT)
        self.grid: Dict[Tuple[int, int], Set[Client]] = {}

        self.clients: Dict[int, Any] = {}  # session_id -> Client
        self.projectile_handler = ProjectileHandler(self)

    def to_cell_pos(self, pos: Tuple[int, int]) -> Tuple[int, int]:
        """Assumes RegionNode.contains(pos) == true"""
        x = (pos[0] - self.x_range[0]) // RegionNode.CELL_SIZE
        y = (pos[1] - self.y_range[0]) // RegionNode.CELL_SIZE
        return (x, y)

    def contains(self, x: int, y: int) -> bool:
        """True if (x, y) is inside this node's bounds."""
        return (
            self.x_range[0] <= x <= self.x_range[1]
            and self.y_range[0] <= y <= self.y_range[1]
        )
    
    @staticmethod
    def which_node(x: int, y: int) -> Tuple[int, int]:
        """Takes a position and returns the node pos it correlates to"""
        return math.ceil(x / RegionNode.NODE_WIDTH) - 1, math.ceil(y / RegionNode.NODE_HEIGHT) - 1

    async def register_client(self, client: Client, initial_pos: Tuple[int, int]):
        self.clients[client.session_id] = client
        cell_x, cell_y = self.to_cell_pos(initial_pos)
        client.state.cell_x, client.state.cell_y = cell_x, cell_y

        if cell := self.grid.get((cell_x, cell_y)):
            cell.add(client)
        else:
            cell = set()
            cell.add(client)
            self.grid[(cell_x, cell_y)] = cell
    
    async def unregister_client(self, client: Client):
        old_cell_x, old_cell_y = client.state.cell_x, client.state.cell_y
        self.grid.get((old_cell_x, old_cell_y), set()).discard(client)
        self.clients.pop(client.session_id, None)

    async def handle_movement(self, client: Client, pos_update: region_net.LocationBlock):
        raw_x, raw_y = pos_update.x, pos_update.y

        # moved to another node
        if not self.contains(raw_x, raw_y):
            await self.unregister_client(client)
            node_pos = RegionNode.which_node(raw_x, raw_y)
            if new_node := nodes.get(node_pos):
                await new_node.register_client(client, (raw_x, raw_y))
                client.node = new_node
            else:
                ... # TODO: Node is on another physical server

        old_cell_x, old_cell_y = client.state.cell_x, client.state.cell_y
        client.state.x = raw_x
        client.state.y = raw_y
        cell_x, cell_y = self.to_cell_pos((raw_x, raw_y))
        client.state.cell_x, client.state.cell_y = cell_x, cell_y

        if (old_cell_x, old_cell_y) != (cell_x, cell_y):
            self.grid.get((old_cell_x, old_cell_y), set()).discard(client)
            if cell := self.grid.get((cell_x, cell_y)):
                cell.add(client)
            else:
                cell = set()
                cell.add(client)
                self.grid[(cell_x, cell_y)] = cell

        resp = region_net.ServerResponse()
        resp.sender_id = client.user_id
        resp.other_data.new_location.CopyFrom(
            region_net.LocationBlock(x=client.state.x, y=client.state.y)
        )
        await client.broadcast_udp(resp)

WHOLE_MAP_X_RANGE = HORIZONAL_NODE_COUNT * RegionNode.NODE_WIDTH
WHOLE_MAP_Y_RANGE = VERTICAL_NODE_COUNT * RegionNode.NODE_HEIGHT