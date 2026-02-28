from __future__ import annotations
from typing import Any, Dict, Generator, Tuple, Set, List
from typing import TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from region_server_extras import Client

import math
from projectiles import ProjectileHandler
import protobuf.region_net_pb2 as region_net
from servers_communication import broadcast_on
from constants import CLIENT_ASPECT_RATIO, CLIENT_RECEIVE_WIDTH, CLIENT_RECEIVE_HEIGHT
from proxy import create_proxy, remove_proxy, ProxyObject, ProxyClient
from grid_utils import GridField, ProxyField, Direction
from nodes import nodes

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
        self.grid: Dict[Tuple[int, int], Set[GridField]] = {}
        self.proxies: List[Set[ProxyField]] = [set() for _ in range(8)] # a set of proxies from each direction

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
    
    async def receive_proxy_event(self, proxy_update: region_net.RegionUpdate) -> None:
        from region_server_extras import Client
        payload_type = proxy_update.WhichOneof("payload")
        if payload_type == "location_block":
            proxy = ProxyClient(proxy_update.location_block.x, proxy_update.location_block.y, proxy_update.sender_id)
        elif payload_type == "bullet_shot":
            raise NotImplementedError("Bullet shots are not supported yet")
        else:
            raise ValueError(f"Unknown proxy update type: {payload_type}")

        try:
            direction = Direction.from_diff(self.node_pos, RegionNode.which_node(*proxy.pos))
        except ValueError:
            return

        # remove the old proxy entry, capturing its seen set for despawn checks
        old_seen: set[int] = set()
        lookup = ProxyField(proxy, set())
        for prx in self.proxies:
            for existing in prx:
                if existing == lookup:
                    old_seen = existing.seen
                    break
            prx.discard(lookup)

        field = ProxyField(proxy, set())
        self.proxies[Direction.to_proxy_pos(direction)].add(field)

        # notify all clients in this node who can see the proxy (using objects_in_view)
        for grid_field in self.objects_in_view(proxy.pos):
            cli = grid_field.obj
            if not isinstance(cli, Client):
                continue
            if cli.user_id == proxy.id:
                continue
            if not Client.can_see_static((cli.state.x, cli.state.y), proxy.pos):
                continue
            field.seen.add(cli.user_id)
            await cli.saw_client(proxy.pos, proxy.id)

        # despawn for clients who could see the old proxy but can't see the new position
        for uid in old_seen - field.seen:
            for cli in self.clients.values():
                if cli.user_id == uid:
                    await cli.entity_despawned(proxy.id)
                    break

    async def receive_proxy_remove(self, sender_id: int) -> None:
        """Remove a proxy by sender_id and despawn it for all clients who had seen it."""
        from region_server_extras import Client
        for prx in self.proxies:
            to_remove = None
            for existing in prx:
                if existing.proxy.id == sender_id:
                    to_remove = existing
                    break
            if to_remove:
                for cli in self.clients.values():
                    if cli.user_id in to_remove.seen:
                        await cli.entity_despawned(sender_id)
                prx.discard(to_remove)
                return

    # ---- grid helpers ----

    def grid_add(self, obj: Any, cell_x: int, cell_y: int, seen: set[int] = set()) -> None:
        key = (cell_x, cell_y)
        if cell := self.grid.get(key):
            cell.add(GridField(obj, seen))
        else:
            self.grid[key] = {GridField(obj, seen)}

    def grid_remove(self, obj: Any, cell_x: int, cell_y: int) -> None:
        if cell := self.grid.get((cell_x, cell_y)):
            cell.discard(GridField(obj))

    def grid_move(
        self, obj: Any, old_cx: int, old_cy: int, new_cx: int, new_cy: int
    ) -> None:
        if (old_cx, old_cy) != (new_cx, new_cy):
            old_seen = set()
            if cell := self.grid.get((old_cx, old_cy)):
                target = GridField(obj)
                for field in cell:
                    if field == target:
                        old_seen = field.seen
                        break
            self.grid_remove(obj, old_cx, old_cy)
            self.grid_add(obj, new_cx, new_cy, old_seen)

    def nearby(
        self, cell_x: int, cell_y: int, radius: int
    ) -> Generator[Any, None, None]:
        """Yield grid objects expanding outward ring-by-ring up to
        Chebyshev distance *radius*.  Typical usage::

            radius = ceil(detection_range_px / CELL_SIZE)
        """
        for r in range(radius + 1):
            if r == 0:
                if cell := self.grid.get((cell_x, cell_y)):
                    yield from cell
                continue
            # top and bottom edges of the ring
            for dx in range(-r, r + 1):
                if cell := self.grid.get((cell_x + dx, cell_y - r)):
                    yield from cell
                if cell := self.grid.get((cell_x + dx, cell_y + r)):
                    yield from cell
            # left and right edges (corners already covered above)
            for dy in range(-r + 1, r):
                if cell := self.grid.get((cell_x - r, cell_y + dy)):
                    yield from cell
                if cell := self.grid.get((cell_x + r, cell_y + dy)):
                    yield from cell

    def objects_in_view(self, pos: Tuple[int, int]) -> Generator[Any, None, None]:
        """Yield grid objects in cells overlapping the view rect (no per-pixel iteration)."""
        left = pos[0] - int(CLIENT_RECEIVE_WIDTH) // 2
        top = pos[1] - int(CLIENT_RECEIVE_HEIGHT) // 2
        right = pos[0] + int(CLIENT_RECEIVE_WIDTH) // 2
        bottom = pos[1] + int(CLIENT_RECEIVE_HEIGHT) // 2

        cell_x_min = (left - self.x_range[0]) // RegionNode.CELL_SIZE
        cell_x_max = (right - 1 - self.x_range[0]) // RegionNode.CELL_SIZE
        cell_y_min = (top - self.y_range[0]) // RegionNode.CELL_SIZE
        cell_y_max = (bottom - 1 - self.y_range[0]) // RegionNode.CELL_SIZE

        max_cx = RegionNode.NODE_WIDTH // RegionNode.CELL_SIZE - 1
        max_cy = RegionNode.NODE_HEIGHT // RegionNode.CELL_SIZE - 1
        cell_x_min = max(0, cell_x_min)
        cell_x_max = min(max_cx, cell_x_max)
        cell_y_min = max(0, cell_y_min)
        cell_y_max = min(max_cy, cell_y_max)

        for cell_y in range(cell_y_min, cell_y_max + 1):
            for cell_x in range(cell_x_min, cell_x_max + 1):
                if cell := self.grid.get((cell_x, cell_y)):
                    yield from cell

    # ---- static helpers ----

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

    def possible_bounding_nodes(self, raw_x: int, raw_y: int) -> List[Direction]:
        """
        Returns relative node offsets (dx, dy) for neighboring nodes that can see an object at (raw_x, raw_y), 
        based on how close the position is to this node's borders.
        """
        local_x = (raw_x - self.node_pos[0] * RegionNode.NODE_WIDTH) / RegionNode.NODE_WIDTH
        local_y = (raw_y - self.node_pos[1] * RegionNode.NODE_HEIGHT) / RegionNode.NODE_HEIGHT

        edge_thresh_sides = (CLIENT_RECEIVE_WIDTH / 2) / RegionNode.NODE_WIDTH
        edge_thresh_up_down = (CLIENT_RECEIVE_HEIGHT / 2) / RegionNode.NODE_HEIGHT
        is_left = local_x < edge_thresh_sides
        is_right = local_x > (1.0 - edge_thresh_sides)
        is_up = local_y < edge_thresh_up_down
        is_down = local_y > (1.0 - edge_thresh_up_down)

        if is_left and is_up:
            return [Direction.UP_LEFT, Direction.UP, Direction.LEFT]
        elif is_left and is_down:
            return [Direction.DOWN_LEFT, Direction.DOWN, Direction.LEFT]
        elif is_right and is_up:
            return [Direction.UP_RIGHT, Direction.UP, Direction.RIGHT]
        elif is_right and is_down:
            return [Direction.DOWN_RIGHT, Direction.DOWN, Direction.RIGHT]
        elif is_left:
            return [Direction.LEFT]
        elif is_right:
            return [Direction.RIGHT]
        elif is_up:
            return [Direction.UP]
        elif is_down:
            return [Direction.DOWN]
        return []

    async def register_client(self, client: Client, initial_pos: Tuple[int, int]):
        self.clients[client.session_id] = client
        cell_x, cell_y = self.to_cell_pos(initial_pos)
        client.state.cell_x, client.state.cell_y = cell_x, cell_y
        self.grid_add(client, cell_x, cell_y)
    
    async def unregister_client(self, client: Client):
        self.grid_remove(client, client.state.cell_x, client.state.cell_y)
        self.clients.pop(client.session_id, None)

    async def handle_movement(self, client: Client, pos_update: region_net.LocationBlock):
        from region_server_extras import Client  # lazy to avoid circular import
        raw_x, raw_y = pos_update.x, pos_update.y

        # moved to another node
        if not self.contains(raw_x, raw_y):
            for cli in self.clients.values():
                if cli.user_id == client.user_id:
                    continue
                if Client.can_see_static((cli.state.x, cli.state.y), (client.state.x, client.state.y)):
                    await cli.entity_despawned(client.user_id)
            # remove all proxies this client had on neighboring nodes
            for direction in getattr(client, '_proxied_directions', set()):
                node_pos = (self.node_pos[0] + direction.value[0], self.node_pos[1] + direction.value[1])
                await remove_proxy(self.node_pos, node_pos, client.user_id)
            client._proxied_directions = set()
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
        old_x, old_y = client.state.x, client.state.y
        client.state.x = raw_x
        client.state.y = raw_y
        cell_x, cell_y = self.to_cell_pos((raw_x, raw_y))
        client.state.cell_x, client.state.cell_y = cell_x, cell_y

        bounds = self.possible_bounding_nodes(raw_x, raw_y)
        new_proxied = set(bounds)
        old_proxied: set = getattr(client, '_proxied_directions', set())
        print(f"possible bounding nodes: {bounds}")

        # remove proxies for directions we're no longer near
        for direction in old_proxied - new_proxied:
            node_pos = (self.node_pos[0] + direction.value[0], self.node_pos[1] + direction.value[1])
            await remove_proxy(self.node_pos, node_pos, client.user_id)
        client._proxied_directions = new_proxied

        # checking who can we see and who can see us
        for direction in bounds:
            node_pos = (self.node_pos[0] + direction.value[0], self.node_pos[1] + direction.value[1])

            # show proxy events in the found node to the client sent the packet
            for seen, obj in self.proxies[Direction.to_proxy_pos(direction)]:
                if client.user_id in seen:
                    continue
                if obj.id == client.user_id:
                    continue
                if not Client.can_see_static(obj.pos, (client.state.x, client.state.y)):
                    continue
                seen.add(client.user_id)
                if isinstance(obj, ProxyClient):
                    await client.saw_client(obj.pos, obj.id)
                    print(f'showed {client.user_id}({client.node.view}) to {obj.id}({node_pos})')
                else:
                    ... # TODO: handle other proxy objects

            # proxy this movement to the other node
            proxy_update = region_net.RegionUpdate(location_block=pos_update, sender_id=client.user_id)
            await create_proxy(self.node_pos, node_pos, proxy_update)

        # notify player about same-node objects they haven't seen yet
        for grid_field in self.objects_in_view((raw_x, raw_y)):
            obj = grid_field.obj
            if not isinstance(obj, Client):
                continue
            if obj.user_id == client.user_id:
                continue
            if client.user_id in grid_field.seen:
                continue
            if not Client.can_see_static((client.state.x, client.state.y), (obj.state.x, obj.state.y)):
                continue
            grid_field.seen.add(client.user_id)
            await client.saw_client((obj.state.x, obj.state.y), obj.user_id)

        # despawn: entities that left the moving player's viewport
        for grid_field in self.objects_in_view((old_x, old_y)):
            obj = grid_field.obj
            if not isinstance(obj, Client):
                continue
            if obj.user_id == client.user_id:
                continue
            if client.user_id not in grid_field.seen:
                continue
            if Client.can_see_static((raw_x, raw_y), (obj.state.x, obj.state.y)):
                continue
            grid_field.seen.discard(client.user_id)
            await client.entity_despawned(obj.user_id)

        self.grid_move(client, old_cell_x, old_cell_y, cell_x, cell_y)

        # despawn: other clients who lost sight of the moving player
        for cli in self.clients.values():
            if cli.user_id == client.user_id:
                continue
            could_see = Client.can_see_static((cli.state.x, cli.state.y), (old_x, old_y))
            can_see = Client.can_see_static((cli.state.x, cli.state.y), (raw_x, raw_y))
            if could_see and not can_see:
                await cli.entity_despawned(client.user_id)

        resp = region_net.ServerResponse()
        resp.sender_id = client.user_id
        resp.other_data.new_location.CopyFrom(
            region_net.LocationBlock(x=client.state.x, y=client.state.y)
        )
        resp.other_data.player_id = client.user_id
        await client.broadcast_udp(resp)

WHOLE_MAP_X_RANGE = HORIZONAL_NODE_COUNT * RegionNode.NODE_WIDTH
WHOLE_MAP_Y_RANGE = VERTICAL_NODE_COUNT * RegionNode.NODE_HEIGHT