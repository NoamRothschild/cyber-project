from __future__ import annotations
from typing import Any, Dict, Generator, Tuple, Set, List
from typing import TYPE_CHECKING, cast
from enum import Enum

if TYPE_CHECKING:
    from region_server_extras import Client

import math
from projectiles import ProjectileHandler
import protobuf.region_net_pb2 as region_net
from servers_communication import broadcast_on
from constants import (
    CLIENT_ASPECT_RATIO,
    CLIENT_RECEIVE_WIDTH,
    CLIENT_RECEIVE_HEIGHT,
    ITEM_HEIGHT,
    ITEM_WIDTH,
)
from proxy import (
    create_proxy,
    remove_proxy,
    broadcast_disconnect,
    ProxyObject,
    ProxyClient,
    ProxyItem,
    ProxyEnemy,
)
from grid_utils import AABB, GridField, ProxyField, Direction, ItemState
from nodes import nodes
from enemy_handler import EnemyHandler, EnemyModel

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
        self.proxies: List[Set[ProxyField]] = [
            set() for _ in range(8)
        ]  # a set of proxies from each direction

        self.clients: Dict[int, Client] = {}  # session_id -> Client
        node_index = RegionNode.node_pos_to_idx(*self.node_pos)
        self.enemy_handler = EnemyHandler(self, node_index, self.x_range, self.y_range)
        self.projectile_handler = ProjectileHandler(self, self.enemy_handler)
        self.items: Dict[int, GridField] = {}  # id -> GridField(obj -> ItemState, seen)

    def to_cell_pos(self, pos: Tuple[int, int]) -> Tuple[int, int]:
        """Assumes RegionNode.contains(pos) == true"""
        x = (pos[0] - self.x_range[0]) // RegionNode.CELL_SIZE
        y = (pos[1] - self.y_range[0]) // RegionNode.CELL_SIZE
        return (x, y)

    def contains(self, x: int, y: int) -> bool:
        """True if (x, y) is inside this node's bounds."""
        if self.topleft == (-1, -1):
            return False

        return (
            self.x_range[0] <= x <= self.x_range[1]
            and self.y_range[0] <= y <= self.y_range[1]
        )

    async def receive_proxy_event(self, event: region_net.ProxyEvent) -> None:
        from region_server_extras import Client

        payload_type = event.WhichOneof("payload")
        if payload_type == "client":
            cp = event.client
            proxy = ProxyClient(cp.pos.x, cp.pos.y, cp.player_id, cp.HP)
        elif payload_type == "enemy":
            ep = event.enemy
            proxy = ProxyEnemy(ep.pos.x, ep.pos.y, ep.player_id, ep.HP)
        elif payload_type == "item":
            cp = event.item
            if cp.action == region_net.ItemProxy.REMOVE:
                for prx in self.proxies:
                    to_remove = None
                    for existing in prx:
                        if (
                            isinstance(existing.proxy, ProxyItem)
                            and existing.proxy.id == cp.id
                        ):
                            to_remove = existing
                            break
                    if to_remove:
                        for cli in self.clients.values():
                            if cli.user_id in to_remove.seen:
                                await cli.item_removed(
                                    to_remove.proxy.name,
                                    to_remove.proxy.kind,
                                    *to_remove.proxy.pos,
                                    to_remove.proxy.id,
                                )
                        prx.discard(to_remove)
                        break
                return
            proxy = ProxyItem(cp.pos.x, cp.pos.y, cp.id, cp.name, cp.kind)
        else:
            return

        try:
            direction = Direction.from_diff(
                self.node_pos, RegionNode.which_node(*proxy.pos)
            )
        except ValueError:
            return

        # remove the old proxy entry, capturing its seen set for despawn checks
        old_seen: set[int] = set()
        lookup = ProxyField(proxy, set())
        moved = True
        old_hp: int = 0

        if isinstance(proxy, ProxyClient):
            for prx in self.proxies:
                for existing in prx:
                    if existing != lookup:
                        continue
                    old_seen = existing.seen
                    if existing.proxy.pos == proxy.pos:
                        moved = False
                    old_hp = cast(ProxyClient, existing.proxy).hp
                    break
                prx.discard(lookup)
        elif isinstance(proxy, ProxyEnemy):
            for prx in self.proxies:
                for existing in prx:
                    if existing != lookup:
                        continue
                    old_seen = existing.seen
                    if existing.proxy.pos == proxy.pos:
                        moved = False
                    old_hp = cast(ProxyEnemy, existing.proxy).hp
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

            if isinstance(proxy, ProxyClient):
                if moved:
                    await cli.saw_client(proxy.pos, proxy.id)
                if old_hp != proxy.hp:
                    await cli.update_other_hp(proxy.id, proxy.hp)
            elif isinstance(proxy, ProxyEnemy):
                await cli.saw_enemy(proxy.pos, proxy.id)
                if old_hp != proxy.hp:
                    await cli.saw_enemy_hp(proxy.id, proxy.hp)
            elif isinstance(proxy, ProxyItem):
                await cli.item_hendeling(proxy.name, proxy.kind, *proxy.pos, proxy.id)

        # despawn only for clients who could see the old proxy but truly can't see the new position
        # (re-check with can_see_static to avoid false despawns when proxy is on adjacent node)
        for uid in old_seen - field.seen:
            for cli in self.clients.values():
                if cli.user_id != uid:
                    continue
                if Client.can_see_static((cli.state.x, cli.state.y), proxy.pos):
                    continue  # client can still see proxy, do not despawn
                print(f"despawning enemy {proxy.id}, since dX={abs(cli.state.x - proxy.pos[0])} dY={abs(cli.state.y - proxy.pos[1])}")
                await cli.entity_despawned(proxy.id)
                break

    async def receive_proxy_remove(self, sender_id: int, type: str = "Client") -> None:
        """Remove all proxies matching sender_id and type; despawn for clients who had seen them."""
        for prx in self.proxies:
            to_remove = None
            for existing in prx:
                if existing.proxy.id != sender_id:
                    continue
                if type == "Client" and isinstance(existing.proxy, ProxyClient):
                    to_remove = existing
                    break
                if type == "Enemy" and isinstance(existing.proxy, ProxyEnemy):
                    to_remove = existing
                    break
            if to_remove:
                for cli in self.clients.values():
                    if cli.user_id in to_remove.seen:
                        await cli.entity_despawned(sender_id)
                prx.discard(to_remove)

    # ---- grid helpers ----

    def grid_add(
        self, obj: Any, cell_x: int, cell_y: int, seen: set[int] = set()
    ) -> GridField:
        key = (cell_x, cell_y)
        field = GridField(obj, seen)
        if cell := self.grid.get(key):
            cell.add(field)
        else:
            self.grid[key] = {field}
        return field

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
    ) -> Generator[GridField, None, None]:
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

    def clients_in_view(self, pos: Tuple[int, int]) -> Generator[Client, None, None]:
        from region_server_extras import Client
        for grid_field in self.objects_in_view(pos):
            obj = grid_field.obj
            if isinstance(obj, Client):
                yield obj

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
        local_x = (
            raw_x - self.node_pos[0] * RegionNode.NODE_WIDTH
        ) / RegionNode.NODE_WIDTH
        local_y = (
            raw_y - self.node_pos[1] * RegionNode.NODE_HEIGHT
        ) / RegionNode.NODE_HEIGHT

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
        client.state.x, client.state.y = initial_pos
        cell_x, cell_y = self.to_cell_pos(initial_pos)
        client.state.cell_x, client.state.cell_y = cell_x, cell_y
        self.clients[client.session_id] = client
        self.grid_add(client, cell_x, cell_y)
        await self.propagate_entity(client)

    async def register_item(
        self, Name: str, Kind: str, player_x: int, player_y: int, id: int
    ):
        # creating the items position while making sure it will stay in this node
        x = min(player_x + 70, self.x_range[1] - ITEM_WIDTH)
        y = min(player_y + 70, self.y_range[1] - ITEM_HEIGHT)

        cell_x, cell_y = self.to_cell_pos((x, y))
        item = ItemState(
            Name, Kind, x, y, cell_x, cell_y, id, AABB(x, y, ITEM_WIDTH, ITEM_HEIGHT)
        )
        field = self.grid_add(item, cell_x, cell_y)
        self.items[id] = field

        item_update = region_net.ServerResponse(
            other_data=region_net.OtherPlayerData(
                New_Item=region_net.Item(Kind=Kind, Name=Name, x=x, y=y, id=id)
            )
        ).SerializeToString()

        for cli in self.clients.values():
            await cli.write(item_update)
            field.seen.add(cli.user_id)

        await self.propagate_item(item)

    def detach_client(self, client: Client):
        """Remove client from this node's grid and client list without global cleanup."""
        try:
            self.grid_remove(client, client.state.cell_x, client.state.cell_y)
            self.clients.pop(client.session_id, None)
        except:
            pass

    async def unregister_client(self, client: Client):
        """Full disconnect: remove from node and purge proxies on all servers."""
        client._proxied_directions = set()
        self.detach_client(client)
        await broadcast_disconnect(client.user_id, client.session_id)

    async def propagate_entity(self, entity) -> None:
        """Sync this entity's proxy state to all relevant neighboring nodes.
        Removes stale proxies from directions we moved away from and
        creates/updates proxies on directions we're currently near."""
        from region_server_extras import Client
        x, y = 0, 0
        session_id = 0
        user_id = 0
        if isinstance(entity, EnemyModel):
            x, y = entity.x, entity.y
            user_id = entity.enemy_id
        elif isinstance(entity, Client):
            x, y = entity.state.x, entity.state.y
            session_id = entity.session_id
            user_id = entity.user_id
        
        bounds = self.possible_bounding_nodes(x, y)
        new_proxied = set(bounds)
        old_proxied: set = getattr(entity, "_proxied_directions", set())

        entity_kind = "Enemy" if isinstance(entity, EnemyModel) else "Client"
        for direction in old_proxied - new_proxied:
            node_pos = (
                self.node_pos[0] + direction.value[0],
                self.node_pos[1] + direction.value[1],
            )
            await remove_proxy(
                self.node_pos, node_pos, user_id, session_id, type=entity_kind
            )
        entity._proxied_directions = new_proxied

        for direction in bounds:
            node_pos = (
                self.node_pos[0] + direction.value[0],
                self.node_pos[1] + direction.value[1],
            )
            await create_proxy(self.node_pos, node_pos, entity.to_proxy_event())

    async def propagate_item(
        self, item: ItemState, remove_instead: bool = False
    ) -> None:
        """Sync this items's proxy state to all relevant neighboring nodes. if remove_instead == True, deletes the item from its proxies"""
        bounds = self.possible_bounding_nodes(item.x, item.y)

        for direction in bounds:
            node_pos = (
                self.node_pos[0] + direction.value[0],
                self.node_pos[1] + direction.value[1],
            )
            await create_proxy(
                self.node_pos, node_pos, item.to_proxy_event(remove_instead)
            )

    async def check_neighbor_spawns(self, client: Client) -> None:
        """Show the moving client any proxied entities from neighboring nodes
        that they haven't seen yet."""
        from region_server_extras import Client

        bounds = self.possible_bounding_nodes(client.state.x, client.state.y)
        for direction in bounds:
            node_pos = (
                self.node_pos[0] + direction.value[0],
                self.node_pos[1] + direction.value[1],
            )
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
                    print(
                        f"showed {client.user_id}({client.node.view}) to {obj.id}({node_pos})"
                    )
                elif isinstance(obj, ProxyEnemy):
                    await client.saw_enemy(obj.pos, obj.id)
                elif isinstance(obj, ProxyItem):
                    await client.item_hendeling(obj.name, obj.kind, *obj.pos, obj.id)

    async def might_hit_item(self, client: Client):
        new_pos = client.state.x, client.state.y
        to_remove: set[Tuple[Any, int, int]] = set()

        for obj_field in self.nearby(client.state.cell_x, client.state.cell_y, 1):
            obj = obj_field.obj
            print(f"nearby obj: {obj}")
            if not isinstance(obj, ItemState):
                continue
            if self.items.get(obj.id) is None:
                continue
            item = obj

            print(new_pos)
            print(obj.x, obj.y)

            if obj.collision.intersects(client.collision):
                print("l3")
                print(obj.id)

                # item picked up -> remove it
                self.items.pop(obj.id, None)
                to_remove.add((obj, obj.cell_x, obj.cell_y))
                await self.propagate_item(
                    item, remove_instead=True
                )  # remove proxies of item

                update = region_net.ServerResponse()
                update.other_data.CopyFrom(
                    region_net.OtherPlayerData(
                        New_Item=region_net.Item(
                            Kind=item.kind,
                            Name=item.name,
                            x=item.x,
                            y=item.y,
                            id=item.id,
                            Picked_up=bool(True),
                        )
                    )
                )

                await client.write(update.SerializeToString())
                update.other_data.New_Item.Picked_up = False
                update.other_data.New_Item.Not_exist = True
                await client.broadcast(update.SerializeToString())

        for obj, cell_x, cell_y in to_remove:
            self.grid_remove(obj, cell_x, cell_y)

    async def update_local_visibility(
        self, client: Client, old_pos: Tuple[int, int]
    ) -> None:
        """Handle spawn/despawn for same-node entities around a moving client."""
        from region_server_extras import Client

        new_pos = (client.state.x, client.state.y)

        for grid_field in self.objects_in_view(new_pos):
            obj = grid_field.obj
            if client.user_id in grid_field.seen:
                continue
            if isinstance(obj, Client):
                if obj.user_id == client.user_id:
                    continue
                if not Client.can_see_static(new_pos, (obj.state.x, obj.state.y)):
                    continue
                grid_field.seen.add(client.user_id)
                await client.saw_client((obj.state.x, obj.state.y), obj.user_id)
            elif isinstance(obj, EnemyModel):
                if obj.enemy_id == client.user_id:
                    continue
                if not Client.can_see_static(new_pos, (obj.x, obj.y)):
                    continue
                grid_field.seen.add(client.user_id)
                await client.saw_enemy((obj.x, obj.y), obj.enemy_id)
            elif isinstance(obj, ItemState):
                grid_field.seen.add(client.user_id)
                await client.item_hendeling(obj.name, obj.kind, obj.x, obj.y, obj.id)

        for grid_field in self.objects_in_view(old_pos):
            obj = grid_field.obj
            if not isinstance(obj, Client):
                continue
            if obj.user_id == client.user_id:
                continue
            if client.user_id not in grid_field.seen:
                continue
            if Client.can_see_static(new_pos, (obj.state.x, obj.state.y)):
                continue
            grid_field.seen.discard(client.user_id)
            await client.entity_despawned(obj.user_id)

        for cli in self.clients.values():
            if cli.user_id == client.user_id:
                continue
            could_see = Client.can_see_static((cli.state.x, cli.state.y), old_pos)
            can_see = Client.can_see_static((cli.state.x, cli.state.y), new_pos)
            if could_see and not can_see:
                await cli.entity_despawned(client.user_id)

    async def handle_movement(
        self, client: Client, pos_update: region_net.LocationBlock
    ):
        from region_server_extras import Client

        old_pos = (client.state.x, client.state.y)
        old_cell = (client.state.cell_x, client.state.cell_y)

        client.state.x = pos_update.x
        client.state.y = pos_update.y
        cell_x, cell_y = self.to_cell_pos((pos_update.x, pos_update.y))
        client.state.cell_x, client.state.cell_y = cell_x, cell_y

        client.collision.x = client.state.x
        client.collision.y = client.state.y

        await self.propagate_entity(client)
        await self.check_neighbor_spawns(client)
        await self.update_local_visibility(client, old_pos)
        await self.might_hit_item(client)

        self.grid_move(client, *old_cell, cell_x, cell_y)

        resp = region_net.ServerResponse()
        resp.sender_id = client.user_id
        resp.other_data.new_location.CopyFrom(
            region_net.LocationBlock(x=client.state.x, y=client.state.y)
        )
        resp.other_data.player_id = client.user_id
        await client.broadcast_udp(resp)


WHOLE_MAP_X_RANGE = HORIZONAL_NODE_COUNT * RegionNode.NODE_WIDTH
WHOLE_MAP_Y_RANGE = VERTICAL_NODE_COUNT * RegionNode.NODE_HEIGHT
