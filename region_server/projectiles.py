from __future__ import annotations
import asyncio
import itertools
import math
import protobuf.region_net_pb2 as region_net
from constants import BULLET_TYPES, TICK_INTERVAL_SEC, SERVER_COUNT
import os
from enemy_model import EnemyModel
from typing import TYPE_CHECKING, Dict, Union
from nodes import get_global_client
from servers_communication import get_redis, notify_client_with

if TYPE_CHECKING:
    from region_node import RegionNode
    from enemy_handler import EnemyHandler
    from region_server_extras import Client

_proj_start_id = (2**31 // SERVER_COUNT) * int(os.getenv("server_id", "0"))
_next_projectile_id = itertools.count(start=_proj_start_id)

# Match client "Assault rifle bullets" so server hit detection aligns with client display
ENEMY_RANGED_BULLET: Dict[str, Union[int, float]] = {
    "ttl": 80,
    "speed": BULLET_TYPES["Assault rifle bullets"]["speed"],
    "damage": 15,
    "range": BULLET_TYPES["Assault rifle bullets"]["range"],
}

class Projectile(dict):
    """Hashable dict subclass so projectiles can live in the spatial grid sets."""

    def __hash__(self) -> int:
        return self["id"]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Projectile):
            return self["id"] == other["id"]
        return NotImplemented


class ProjectileHandler:
    """Handles projectiles for one region node; uses node.clients when ticking."""

    def __init__(
        self,
        node: "RegionNode",
        enemy_handler: "EnemyHandler",
        tick_intervals: float = TICK_INTERVAL_SEC,
    ) -> None:
        self._node: RegionNode = node
        self.lock = asyncio.Lock()
        self.projectiles: list[Projectile] = []
        self._incoming: list[Projectile] = []
        self.tick_intervals = tick_intervals
        self.enemy_handler = enemy_handler

    def bullet_hit(self, proj: Projectile, client: "Client") -> bool:
        dst_squared = (client.state.x - proj["x"]) ** 2 + (
            client.state.y - proj["y"]
        ) ** 2
        return dst_squared < proj["range"] ** 2

    def bullet_hit_at(self, proj: Projectile, client: "Client", bx: float, by: float) -> bool:
        """Check if bullet at (bx, by) is within range of client (avoids tunneling)."""
        dst_squared = (client.state.x - bx) ** 2 + (client.state.y - by) ** 2
        return dst_squared < proj["range"] ** 2

    @staticmethod
    def _build_bullet_response(proj: dict) -> bytes:
        """Serialize a single projectile into a ServerResponse for client delivery."""
        resp = region_net.ServerResponse(sender_id=proj["owner_uuid"])
        resp.bullet_shot.add(
            gun_type=proj["gun_type"],
            angle=proj["angle"],
            count=1,
            x=int(proj["x"]),
            y=int(proj["y"]),
            ttl=int(proj["ttl"]),
            speed=int(proj["speed"]),
        )
        return resp.SerializeToString()

    def bullet_hit_enemy(self, proj: dict, enemy: EnemyModel) -> bool:
        return self._bullet_hit_enemy_at(proj, enemy, proj["x"], proj["y"])

    def _bullet_hit_enemy_at(self, proj: dict, enemy: EnemyModel, bx: float, by: float) -> bool:
        """True if (bx, by) is inside the enemy AABB (or within a small margin for fast bullets)."""
        # Point-in-AABB: bullet inside enemy rect
        margin = max(abs(proj["velocity_x"]), abs(proj["velocity_y"]), 1.0)
        return (
            enemy.x - margin <= bx <= enemy.x + enemy.w + margin
            and enemy.y - margin <= by <= enemy.y + enemy.h + margin
        )

    @staticmethod
    async def get_player_mag_stat(session_id: int, bullet_type: str) -> int:
        """
        Look up the player's remaining ammo for the given bullet type
        using the global connected-clients registry.
        """
        client = await get_global_client(session_id)
        if client is None:
            print(f"Warning: {session_id} is not registered (no global client found)")
            return 0

        return client.user_state["ammo_collection"].get(bullet_type, 0)

    @staticmethod
    async def dec_player_mag_stat(session_id: int, bullet_type: str, shot_count: int) -> None:
        """
        Decrease the player's ammo for the given bullet type by 1
        using the global connected-clients registry.
        """
        client = await get_global_client(session_id)
        if client is None:
            print(session_id, "is not registered (no global client found)")
            return

        client.user_state["ammo_collection"][bullet_type] -= shot_count

    async def tick(self, cycle: int) -> None:
        from nodes import nodes
        from region_node import RegionNode
        from servers_communication import broadcast_on
        from region_server_extras import Client
        from proxy import remove_proxy

        to_remove: list[Projectile] = []
        to_transfer: list[tuple[Projectile, tuple[int, int]]] = []
        node = self._node
        dead_enemies: list[tuple[int, int, int, set, set]] = []  # (enemy_id, x, y, proxied_directions, seen)
        enemies_to_broadcast_hp: list[EnemyModel] = []
        pending_client_hits: dict[int, tuple[Client, int, int]] = {}  # user_id -> (client, total_dmg, last_hitter)

        async with self.lock:
            # Merge incoming transfers and place on the grid
            for proj in self._incoming:
                self.projectiles.append(proj)
                cx, cy = node.to_cell_pos((int(proj["x"]), int(proj["y"])))
                proj["cell_x"], proj["cell_y"] = cx, cy
                node.grid_add(proj, cx, cy)
            self._incoming.clear()

            for proj in self.projectiles:
                if proj.get("_last_ticked") == cycle:
                    continue
                proj["_last_ticked"] = cycle

                proj["ttl"] -= 1
                if proj["ttl"] <= 0:
                    to_remove.append(proj)
                    continue

                proj["x"] += proj["velocity_x"]
                proj["y"] += proj["velocity_y"]

                px, py = int(proj["x"]), int(proj["y"])
                if not node.contains(px, py):
                    new_node_pos = RegionNode.which_node(px, py)
                    if new_node_pos != node.node_pos:
                        to_transfer.append((proj, new_node_pos))
                        continue
                    # world boundary — keep last valid grid cell
                    continue

                new_cx, new_cy = node.to_cell_pos((px, py))
                old_cx, old_cy = proj["cell_x"], proj["cell_y"]
                if (old_cx, old_cy) != (new_cx, new_cy):
                    node.grid_move(proj, old_cx, old_cy, new_cx, new_cy)
                    proj["cell_x"], proj["cell_y"] = new_cx, new_cy

            for e in to_remove:
                if "cell_x" in e:
                    node.grid_remove(e, e["cell_x"], e["cell_y"])
                self.projectiles.remove(e)
            for proj, _ in to_transfer:
                if "cell_x" in proj:
                    node.grid_remove(proj, proj["cell_x"], proj["cell_y"])
                self.projectiles.remove(proj)

            # Spatial collision detection
            for proj in self.projectiles:
                search_radius = math.ceil(proj["range"] / RegionNode.CELL_SIZE) + 1
                for grid_field in node.nearby(
                    proj["cell_x"], proj["cell_y"], search_radius
                ):
                    # can_print = proj.get("src") == "CLIENT"
                    # prnt = print if can_print else lambda *args, **kwargs: None
                    # TODO: expand to also catch Enemy objects when pulled
                    if isinstance(grid_field.obj, Client):
                        # prnt(f'bullet found a close client')
                        client = grid_field.obj
                        if proj["owner_uuid"] == client.user_id:
                            continue
                        if client.user_id in proj["already_hit"]:
                            continue
                        # Check current and previous position to avoid tunneling through fast bullets
                        prev_x = proj["x"] - proj["velocity_x"]
                        prev_y = proj["y"] - proj["velocity_y"]
                        if self.bullet_hit(proj, client) or self.bullet_hit_at(proj, client, prev_x, prev_y):
                            uid = client.user_id
                            prev = pending_client_hits.get(uid)
                            if prev is not None:
                                pending_client_hits[uid] = (client, prev[1] + proj["damage"], proj["owner_uuid"])
                            else:
                                pending_client_hits[uid] = (client, proj["damage"], proj["owner_uuid"])
                            proj["already_hit"].add(uid)

                    elif isinstance(grid_field.obj, EnemyModel):
                        # prnt(f'bullet found a close enemy')
                        enemy = grid_field.obj
                        # skip enemies already dead or already hit by this bullet
                        if enemy.enemy_id in proj["already_hit"]:
                            continue
                        # TODO: go over the bellow again
                        if enemy.enemy_id in self.enemy_handler.dead_ids:
                            continue

                        prev_x = proj["x"] - proj["velocity_x"]
                        prev_y = proj["y"] - proj["velocity_y"]
                        hit_now = self.bullet_hit_enemy(proj, enemy)
                        hit_prev = self._bullet_hit_enemy_at(proj, enemy, prev_x, prev_y)
                        if hit_now or hit_prev:
                            # prnt(f'BULLET HIT ENEMY')
                            died = enemy.take_damage(int(proj["damage"]))
                            proj["already_hit"].add(enemy.enemy_id)
                            # snapshot hp now while lock is held
                            enemies_to_broadcast_hp.append(enemy)

                            if died:
                                proxied = getattr(enemy, "_proxied_directions", set())
                                dead_enemies.append((enemy.enemy_id, enemy.x, enemy.y, proxied, grid_field.seen))
                                enemy._proxied_directions = set()
                                self.enemy_handler.dead_ids.add(enemy.enemy_id)
                                # override the hp broadcast to max_hp so the client resets the enemy
                                enemy.hp = enemy.max_hp
        
        for client, total_damage, hitter_id in pending_client_hits.values():
            await client.hit(total_damage, hitter_id)

        r = get_redis()
        for enemy_id, ex, ey, proxied_directions, seen in dead_enemies:
            for cli in node.clients_in_view((ex, ey)):
                await cli.entity_died(enemy_id)
                seen.discard(cli.user_id)
            for cli_id in seen: # each client that should get the despawn we don't own
                node_idx = int(await r.get(f"client:{cli_id}:node"))
                node_pos = RegionNode.node_idx_to_pos(node_idx)
                if clients_node := nodes.get(node_pos):
                    cli = clients_node.clients.get(cli_id, None)
                    if cli is None:
                        continue
                    await cli.entity_died(enemy_id)
                else:
                    enemy_data = region_net.OtherPlayerData()
                    enemy_data.state = region_net.OtherPlayerData.DIED
                    enemy_data.player_id = enemy_id
                    await notify_client_with(str(node_idx), region_net.ServerResponse(
                        sender_id=cli_id,
                        enemy_data=enemy_data,
                    ))
            for direction in proxied_directions:
                adj_node_pos = (
                    node.node_pos[0] + direction.value[0],
                    node.node_pos[1] + direction.value[1],
                )
                await remove_proxy(
                    node.node_pos, adj_node_pos, enemy_id, 0, type="Enemy"
                )
            asyncio.create_task(self.enemy_handler.respawn_enemy(enemy_id))

        dead_ids = {e[0] for e in dead_enemies}
        for enemy in enemies_to_broadcast_hp:
            if enemy.enemy_id in dead_ids:
                continue
            await self._node.propagate_entity(enemy)
            for cli in self._node.clients_in_view((enemy.x, enemy.y)):
                await cli.saw_enemy_hp(enemy.enemy_id, enemy.hp)

        for proj, new_node_pos in to_transfer:
            if new_node := nodes.get(new_node_pos):
                await new_node.projectile_handler.receive_transferred(proj)
            else:
                node_idx = str(RegionNode.node_pos_to_idx(*new_node_pos))
                update = region_net.RegionUpdate(sender_id=proj["owner_uuid"])
                bs = update.bullet_shot
                bs.gun_type = proj["gun_type"]
                bs.angle = proj["angle"]
                bs.count = 1
                bs.x = int(proj["x"])
                bs.y = int(proj["y"])
                bs.ttl = int(proj["ttl"])
                bs.speed = int(proj["speed"])
                bs.seen_players.extend(proj["seen_by"])
                await broadcast_on(node_idx, update.SerializeToString())
                print(
                    f"projectile left to off-server node {new_node_pos}, forwarding via Redis"
                )

    async def add(
        self, bullet_shot: region_net.BulletShot, client: "Client"
    ) -> tuple[bytes, list[Projectile]]:
        template = BULLET_TYPES.get(bullet_shot.gun_type)
        if not template:
            print(
                f"Warn: unknown bullet type fired: {bullet_shot.gun_type} "
                f"by user with id {client.user_id}"
            )
            return b"", []

        shot_count = bullet_shot.count
        mag = await ProjectileHandler.get_player_mag_stat(client.session_id, bullet_shot.gun_type)
        if mag - shot_count >= 0:
            await ProjectileHandler.dec_player_mag_stat(client.session_id, bullet_shot.gun_type, shot_count)
        else:
            return b"", []

        bullet = template.copy()
        bullet["owner_uuid"] = client.user_id
        bullet["gun_type"] = bullet_shot.gun_type
        bullet["angle"] = bullet_shot.angle
        bullet["x"] = client.state.x
        bullet["y"] = client.state.y
        bullet["src"] = "CLIENT"

        update = region_net.ServerResponse(sender_id=client.user_id)
        new_projectiles: list[Projectile] = []
        node = self._node

        async with self.lock:
            for i in range(bullet_shot.count):
                blt = Projectile(bullet)
                blt["already_hit"] = set()
                blt["seen_by"] = {client.user_id} | set(bullet_shot.seen_players)
                blt["id"] = next(_next_projectile_id)

                # For multi-arrow shots, fan out angles slightly to mimic client-side pattern.
                if bullet_shot.gun_type == "arrows" and bullet_shot.count > 1:
                    center_index = (bullet_shot.count - 1) / 2
                    angle_offset = (i - center_index) * 0.12  # ~7 degrees spread per step
                    angle = bullet_shot.angle + angle_offset
                else:
                    angle = bullet_shot.angle

                blt["angle"] = angle
                blt["velocity_x"] = math.cos(angle) * blt["speed"]
                blt["velocity_y"] = math.sin(angle) * blt["speed"]

                blt["x"] = bullet["x"]
                blt["y"] = bullet["y"]

                blt["x"] += i * blt["velocity_x"]
                blt["y"] += i * blt["velocity_y"]

                px, py = int(blt["x"]), int(blt["y"])
                cx, cy = node.to_cell_pos((px, py))
                blt["cell_x"], blt["cell_y"] = cx, cy
                node.grid_add(blt, cx, cy)

                self.projectiles.append(blt)
                new_projectiles.append(blt)
                update.bullet_shot.add(
                    gun_type=bullet_shot.gun_type,
                    angle=angle,
                    count=1,
                    x=px,
                    y=py,
                    ttl=int(blt["ttl"]),
                    speed=int(blt["speed"]),
                )

        return update.SerializeToString(), new_projectiles

    async def add_enemy_bullet(self, spawn_x: float, spawn_y: float, angle: float, enemy_id: int) -> None:
        """Fire a projectile from a ranged enemy."""
        bullet = ENEMY_RANGED_BULLET.copy()
        bullet["velocity_x"] = math.cos(angle) * bullet["speed"]
        bullet["velocity_y"] = math.sin(angle) * bullet["speed"]
        bullet["owner_uuid"] = enemy_id
        bullet["already_hit"] = {enemy_id}
        bullet["x"] = spawn_x
        bullet["y"] = spawn_y
        bullet["gun_type"] = "Assault rifle bullets"
        bullet["src"] = "ENEMY"

        update = region_net.ServerResponse(sender_id=enemy_id)
        update.bullet_shot.add(
            gun_type="Assault rifle bullets",
            angle=angle,
            count=1,
            x=int(spawn_x),
            y=int(spawn_y),
            ttl=int(bullet["ttl"]),
            speed=int(bullet["speed"]),
        )

        new_projectiles: list[Projectile] = []
        node = self._node

        blt = Projectile(bullet)
        blt["already_hit"] = {enemy_id}
        blt["seen_by"] = set()
        blt["id"] = next(_next_projectile_id)

        blt["angle"] = angle
        blt["velocity_x"] = math.cos(angle) * blt["speed"]
        blt["velocity_y"] = math.sin(angle) * blt["speed"]

        blt["x"] = bullet["x"]
        blt["y"] = bullet["y"]

        px, py = int(blt["x"]), int(blt["y"])
        cx, cy = node.to_cell_pos((px, py))
        blt["cell_x"], blt["cell_y"] = cx, cy
        node.grid_add(blt, cx, cy)
        
        async with self.lock:
            self.projectiles.append(blt)
        
        new_projectiles.append(blt)
        update.bullet_shot.add(
            gun_type="Assault rifle bullets",
            angle=angle,
            count=1,
            x=px,
            y=py,
            ttl=int(blt["ttl"]),
            speed=int(blt["speed"]),
        )

        return update.SerializeToString(), new_projectiles


    async def receive_transferred(self, proj: Projectile) -> None:
        """Receive a projectile transferred from an adjacent node on this server."""
        print(
            f"Transferred projectile received: id={proj['id']} at node={self._node.node_pos}"
        )
        async with self.lock:
            self._incoming.append(proj)
        await self._broadcast_to_unseen_clients(proj)
        # Do not call broadcast_to_adjacent here: the projectile is only in this node.
        # If it leaves again, the tick loop will transfer/forward it once to the correct node.

    async def _broadcast_to_unseen_clients(self, proj: dict) -> None:
        """Send this projectile's creation data to local clients that haven't seen it."""
        data = self._build_bullet_response(proj)
        for client in self._node.clients.values():
            if client.user_id in proj["seen_by"]:
                continue
            await client.write(data)
            proj["seen_by"].add(client.user_id)

    async def broadcast_to_adjacent(self, projectiles: list[dict]) -> None:
        """Broadcast projectile creation data to players in adjacent nodes."""
        from nodes import nodes
        from region_node import RegionNode
        from servers_communication import broadcast_on

        for proj in projectiles:
            data = self._build_bullet_response(proj)

            for direction in self._node.possible_bounding_nodes(
                int(proj["x"]), int(proj["y"])
            ):
                bound_x, bound_y = direction.value
                node_pos = (
                    self._node.node_pos[0] + bound_x,
                    self._node.node_pos[1] + bound_y,
                )

                if extra_node := nodes.get(node_pos):
                    for cli in extra_node.clients.values():
                        if cli.user_id in proj["seen_by"]:
                            continue
                        await cli.write(data)
                        proj["seen_by"].add(cli.user_id)
                else:
                    node_idx = str(RegionNode.node_pos_to_idx(*node_pos))
                    update = region_net.RegionUpdate(sender_id=proj["owner_uuid"])
                    bs = update.bullet_shot
                    bs.gun_type = proj["gun_type"]
                    bs.angle = proj["angle"]
                    bs.count = 1
                    bs.x = int(proj["x"])
                    bs.y = int(proj["y"])
                    bs.ttl = int(proj["ttl"])
                    bs.speed = int(proj["speed"])
                    bs.seen_players.extend(proj["seen_by"])
                    await broadcast_on(node_idx, update.SerializeToString())
                    print(
                        f"projectile left to off-server node {node_pos}, forwarding via Redis"
                    )
