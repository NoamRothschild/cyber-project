from __future__ import annotations
from typing import Any, Dict, Tuple, Set, List
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from region_server_extras import Client

import math
from projectiles import ProjectileHandler
import protobuf.region_net_pb2 as region_net
from servers_communication import broadcast_on

nodes: Dict[Tuple[int, int], RegionNode] = {}

VERTICAL_NODE_COUNT = 20
HORIZONAL_NODE_COUNT = 17


class RegionNode:
    NODE_WIDTH = 4600  # [px]
    NODE_HEIGHT = 2200  # [px]
    CELL_SIZE = 200  # [px]

    def __init__(self, topleft: Tuple[int, int]) -> None:
        self.topleft = topleft
        self.node_pos = RegionNode.which_node(*topleft)
        self.view = str(self.node_pos)
        self.x_range = (topleft[0], topleft[0] + RegionNode.NODE_WIDTH)
        self.y_range = (topleft[1], topleft[1] + RegionNode.NODE_HEIGHT)
        self.grid: Dict[Tuple[int, int], Set[Client]] = {}

        self.clients: Dict[int, Client] = {}  # session_id -> Client
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
        """Takes a position and returns the node pos it correlates to."""
        node_x = x // RegionNode.NODE_WIDTH
        node_y = y // RegionNode.NODE_HEIGHT

        # Clamp to valid grid range
        if node_x < 0:
            node_x = 0
        elif node_x >= HORIZONAL_NODE_COUNT:
            node_x = HORIZONAL_NODE_COUNT - 1

        if node_y < 0:
            node_y = 0
        elif node_y >= VERTICAL_NODE_COUNT:
            node_y = VERTICAL_NODE_COUNT - 1

        return node_x, node_y
    
    @staticmethod
    def node_pos_to_idx(pos_x: int, pos_y: int) -> int:
        return pos_y * HORIZONAL_NODE_COUNT + pos_x
    
    def possible_bounding_nodes(self, raw_x: int, raw_y: int) -> List[Tuple[int, int]]:
        is_left = (raw_x - self.node_pos[0] * RegionNode.NODE_WIDTH) / RegionNode.NODE_WIDTH < .5
        is_up = (raw_y - self.node_pos[1] * RegionNode.NODE_HEIGHT) / RegionNode.NODE_HEIGHT < .5

        if is_left and is_up:
            return [(-1,-1),(0,-1),(-1,0)]
        elif is_left and not is_up:
            return [(-1,0),(-1,1),(0,1)]
        elif is_up: # and not is_left
            return [(0,-1),(1,-1),(1,0)]
        else: # not is_up and not is_left
            return [(1,0),(0,1),(1,1)]

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
            # node is on this device
            if new_node := nodes.get(node_pos):
                await new_node.register_client(client, (raw_x, raw_y))
                client.node = new_node
            else:
                print(f"Client on node {node_pos} that is not on this server.")
                # node is on another physical server
                # TODO: connect client to the new server
                # TODO: set client.node to some other thing
                # r = get_redis()
                # channel = str(RegionNode.node_pos_to_idx(*node_pos))
                # message = region_net.RegionUpdate(location_block=pos_update).SerializeToString()
                # await r.publish(channel, message)
                pass
            return

        old_cell_x, old_cell_y = client.state.cell_x, client.state.cell_y
        client.state.x = raw_x
        client.state.y = raw_y
        cell_x, cell_y = self.to_cell_pos((raw_x, raw_y))
        client.state.cell_x, client.state.cell_y = cell_x, cell_y

        # checking if other nodes can see this movement event
        for bound_x, bound_y in self.possible_bounding_nodes(raw_x, raw_y):
            node_pos = (self.node_pos[0] + bound_x, self.node_pos[1] + bound_y)

            if extra_node := nodes.get(node_pos):
                # notify players in other nodes that can see this movement
                for cli in extra_node.clients.values():
                    if cli.user_id == client.user_id:
                        continue
                    resp = region_net.ServerResponse()
                    resp.sender_id = client.user_id
                    resp.other_data.new_location.CopyFrom(
                        region_net.LocationBlock(x=client.state.x, y=client.state.y)
                    )
                    await cli.write_udp(resp)
                    print(f'showed {client.user_id}({client.node.view}) to {cli.user_id}({cli.node.view})')
            else:
                print(f"key {node_pos}: {node_pos in nodes.keys()=}")
                node_idx = str(RegionNode.node_pos_to_idx(*node_pos))
                message = region_net.RegionUpdate(location_block=pos_update).SerializeToString()
                await broadcast_on(node_idx, message)
                print(f"({self.view}) -> ({node_pos}), played can be seen outside of this server, forwarding...")

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