from __future__ import annotations
from typing import Any, Dict, Generator, Tuple, Set, List
from typing import TYPE_CHECKING, cast
from enum import Enum

if TYPE_CHECKING:
    from region_server_extras import Client

import math
from projectiles import ProjectileHandler
import protobuf.region_net_pb2 as region_net
from servers_communication import get_redis, notify_client_with
from constants import (
    CLIENT_ASPECT_RATIO,
    CLIENT_RECEIVE_WIDTH,
    CLIENT_RECEIVE_HEIGHT,
    ITEM_HEIGHT,
    ITEM_WIDTH,
    SERVER_WEAPON_MAP,
    SERVER_MAX_AMMO,
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
    _grid_w = NODE_WIDTH // CELL_SIZE
    _grid_h = NODE_HEIGHT // CELL_SIZE

    def __init__(self, topleft: Tuple[int, int]) -> None:
        self.topleft = topleft
        self.node_pos = RegionNode.which_node(*topleft)
        self.index = RegionNode.node_pos_to_idx(*self.node_pos)
        self.view = str(self.node_pos)
        self.x_range = (topleft[0], topleft[0] + RegionNode.NODE_WIDTH)
        self.y_range = (topleft[1], topleft[1] + RegionNode.NODE_HEIGHT)
        self.grid: List[Set[GridField]] = [set() for _ in range(RegionNode._grid_w * RegionNode._grid_h)]
        self.proxies: List[Set[ProxyField]] = [
            set() for _ in range(8)
        ]  # a set of proxies from each direction

        self.clients: Dict[int, Client] = {}  # user_id -> Client
        self._had_viewers = False
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

    def has_nearby_viewers(self) -> bool:
        """True if this node, any local adjacent node has clients,
        or any adjacent position is a remote node (conservatively assume viewers)."""
        if self.clients:
            return True
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                adj_x = self.node_pos[0] + dx
                adj_y = self.node_pos[1] + dy
                if not (0 <= adj_x < HORIZONAL_NODE_COUNT and 0 <= adj_y < VERTICAL_NODE_COUNT):
                    continue
                adj_node = nodes.get((adj_x, adj_y))
                if adj_node is None:
                    return True
                if adj_node.clients:
                    return True
        return False

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
                prx.discard(to_remove)
                seen = to_remove.seen
                r = get_redis()
                for cli_id in seen:
                    if cli := self.clients.get(cli_id):
                        await cli.entity_despawned(sender_id)
                    else:
                        node_idx = int(await r.get(f"client:{cli_id}:node"))
                        node_pos = RegionNode.node_idx_to_pos(node_idx)
                        if clients_node := nodes.get(node_pos):
                            cli = clients_node.clients.get(cli_id, None)
                            if cli is None:
                                continue
                            await cli.entity_despawned(sender_id)
                        else:
                            enemy_data = region_net.OtherPlayerData()
                            enemy_data.state = region_net.OtherPlayerData.DESPAWNED
                            enemy_data.player_id = sender_id
                            await notify_client_with(str(node_idx), region_net.ServerResponse(
                                sender_id=cli_id,
                                enemy_data=enemy_data,
                            ))

    # ---- grid helpers ----

    def grid_add(
        self, obj: Any, cell_x: int, cell_y: int, seen: set[int] = set()
    ) -> GridField:
        field = GridField(obj, seen)
        self.grid[cell_y * RegionNode._grid_w + cell_x].add(field)
        return field

    def grid_remove(self, obj: Any, cell_x: int, cell_y: int) -> None:
        self.grid[cell_y * RegionNode._grid_w + cell_x].discard(GridField(obj))

    def grid_move(
        self, obj: Any, old_cx: int, old_cy: int, new_cx: int, new_cy: int
    ) -> None:
        if (old_cx, old_cy) != (new_cx, new_cy):
            old_seen = set()
            cell = self.grid[old_cy * RegionNode._grid_w + old_cx]
            if cell:
                target = GridField(obj)
                for field in tuple(cell):  # snapshot in case set is modified during iteration
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
        grid = self.grid
        w = RegionNode._grid_w
        h = RegionNode._grid_h
        for r in range(radius + 1):
            if r == 0:
                if 0 <= cell_x < w and 0 <= cell_y < h:
                    cell = grid[cell_y * w + cell_x]
                    if cell:
                        yield from tuple(cell)
                continue
            for dx in range(-r, r + 1):
                nx = cell_x + dx
                if 0 <= nx < w:
                    ny = cell_y - r
                    if 0 <= ny < h:
                        cell = grid[ny * w + nx]
                        if cell:
                            yield from tuple(cell)
                    ny = cell_y + r
                    if 0 <= ny < h:
                        cell = grid[ny * w + nx]
                        if cell:
                            yield from tuple(cell)
            for dy in range(-r + 1, r):
                ny = cell_y + dy
                if 0 <= ny < h:
                    nx = cell_x - r
                    if 0 <= nx < w:
                        cell = grid[ny * w + nx]
                        if cell:
                            yield from tuple(cell)
                    nx = cell_x + r
                    if 0 <= nx < w:
                        cell = grid[ny * w + nx]
                        if cell:
                            yield from tuple(cell)

    def clients_in_view(self, pos: Tuple[int, int]) -> Generator[Client, None, None]:
        from region_server_extras import Client
        for grid_field in self.objects_in_view(pos):
            obj = grid_field.obj
            if isinstance(obj, Client):
                yield obj

    _VIEW_HALF_W = int(CLIENT_RECEIVE_WIDTH) // 2
    _VIEW_HALF_H = int(CLIENT_RECEIVE_HEIGHT) // 2

    def objects_in_view(self, pos: Tuple[int, int]) -> List[GridField]:
        """Return grid objects in cells overlapping the view rect."""
        x0 = self.x_range[0]
        y0 = self.y_range[0]
        cs = RegionNode.CELL_SIZE
        w = RegionNode._grid_w

        cell_x_min = max(0, (pos[0] - self._VIEW_HALF_W - x0) // cs)
        cell_x_max = min(w - 1, (pos[0] + self._VIEW_HALF_W - 1 - x0) // cs)
        cell_y_min = max(0, (pos[1] - self._VIEW_HALF_H - y0) // cs)
        cell_y_max = min(RegionNode._grid_h - 1, (pos[1] + self._VIEW_HALF_H - 1 - y0) // cs)

        result: List[GridField] = []
        grid = self.grid
        for cell_y in range(cell_y_min, cell_y_max + 1):
            row = cell_y * w
            for cell_x in range(cell_x_min, cell_x_max + 1):
                cell = grid[row + cell_x]
                if cell:
                    result.extend(cell)
        return result

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

    @staticmethod
    def node_idx_to_pos(idx: int) -> Tuple[int, int]:
        return  (
            idx % HORIZONAL_NODE_COUNT,
            idx // HORIZONAL_NODE_COUNT
        )

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
        self.clients[client.user_id] = client
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
            self.clients.pop(client.user_id, None)
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

            if obj.collision.intersects(client.collision):
                picked_up = False

                if item.kind == "money":
                    if client.gold_active:
                        client.state.money += 100
                    else:
                        client.state.money += 50
                    picked_up = True
                    print(f"[MONEY] player {client.user_id} picked up 50; now has {client.state.money}")
                elif item.kind == "potion":
                    # Map potion name to ID (must stay in sync with client.inventory.POTION_MAP)
                    potion_id_map = {
                        "healing": 1,
                        "speed": 2,
                        "super_speed": 3,
                        "gold":3,
                    }
                    potion_id = potion_id_map.get(item.name)
                    if potion_id is None:
                        print(f"[WARN] Unknown potion name '{item.name}', ignoring pickup")
                    else:
                        for i, slot in enumerate(client.state.potions):
                            if slot == 0:
                                client.state.potions[i] = potion_id
                                picked_up = True
                                break
                elif item.kind == "weapon":
                    weapon_id = SERVER_WEAPON_MAP.get(item.name)
                    if weapon_id is None:
                        print(f"[WARN] Unknown weapon name '{item.name}', ignoring pickup")
                    else:
                        for i, slot in enumerate(client.state.weapons):
                            if slot == 0:
                                client.state.weapons[i] = weapon_id
                                client.state.ammo[i] = 0
                                picked_up = True
                                break

                # If the inventory was full (or item kind unknown), leave the item on the ground
                if not picked_up:
                    continue

                # Item successfully picked up -> remove it from this node and all proxies
                self.items.pop(obj.id, None)
                to_remove.add((obj, obj.cell_x, obj.cell_y))
                await self.propagate_item(
                    item, remove_instead=True
                )

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

        for grid_field in client.old_view:
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
        client.old_view.clear()

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
            client.old_view.append(grid_field)

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
