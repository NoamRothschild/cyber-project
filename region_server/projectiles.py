from __future__ import annotations
import asyncio
import itertools
import math
import protobuf.region_net_pb2 as region_net
from constants import BULLET_TYPES, TICK_INTERVAL_SEC, SERVER_COUNT
import os
from enemy_model import EnemyModel
from typing import TYPE_CHECKING, Dict, Union

if TYPE_CHECKING:
    from region_node import RegionNode
    from enemy_handler import EnemyHandler
    from region_server_extras import Client

_proj_start_id = (2**31 // SERVER_COUNT) * int(os.getenv("server_id", "0"))
_next_projectile_id = itertools.count(start=_proj_start_id)

ENEMY_RANGED_BULLET: Dict[str, Union[int, float]] = {
    "ttl": 80,
    "speed": 15,
    "damage": 15,
    "range": 30,
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
        hit_radius = (enemy.w + enemy.h) / 4  # ~17.5px to fit the sprite
        ex = enemy.x + enemy.w / 2
        ey = enemy.y + enemy.h / 2
        dx = ex - proj["x"]
        dy = ey - proj["y"]
        return (dx * dx + dy * dy) < (hit_radius ** 2)

    async def tick(self, cycle: int) -> None:
        from nodes import nodes
        from region_node import RegionNode
        from servers_communication import broadcast_on
        from region_server_extras import Client

        to_remove: list[Projectile] = []
        to_transfer: list[tuple[Projectile, tuple[int, int]]] = []
        node = self._node
        dead_enemy_ids: list[int] = []
        # list of (enemy_id, hp) — snapshot hp at hit time, not after lock release
        enemies_to_broadcast_hp: list[EnemyModel] = []

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
                search_radius = math.ceil(proj["range"] / RegionNode.CELL_SIZE)
                for grid_field in node.nearby(
                    proj["cell_x"], proj["cell_y"], search_radius
                ):
                    # TODO: expand to also catch Enemy objects when pulled
                    if isinstance(grid_field.obj, Client):
                        client = grid_field.obj
                        if proj["owner_uuid"] == client.user_id:
                            continue
                        if client.user_id in proj["already_hit"]:
                            continue
                        if self.bullet_hit(proj, client):
                            await client.hit(proj["damage"], proj["owner_uuid"])
                            proj["already_hit"].add(client.user_id)

                    elif isinstance(grid_field.obj, EnemyModel):
                        enemy = grid_field.obj
                        # skip enemies already dead or already hit by this bullet
                        if enemy.enemy_id in proj["already_hit"]:
                            continue
                        # TODO: go over the bellow again
                        if enemy.enemy_id in self.enemy_handler._dead_ids:
                            continue

                        if self.bullet_hit_enemy(proj, enemy):
                            died = enemy.take_damage(int(proj["damage"]))
                            proj["already_hit"].add(enemy.enemy_id)
                            # snapshot hp now while lock is held
                            enemies_to_broadcast_hp.append(enemy)

                            if died:
                                dead_enemy_ids.append(enemy.enemy_id)
                                self.enemy_handler._dead_ids.add(enemy.enemy_id)
                                # override the hp broadcast to max_hp so the client resets the enemy
                                enemy.hp = enemy.max_hp
        
        for enemy in enemies_to_broadcast_hp:
            await self._node.propagate_entity(enemy)
            for cli in self._node.clients_in_view((enemy.x, enemy.y)):
                await cli.saw_enemy_hp(enemy.enemy_id, enemy.hp)
        
        for enemy_id in dead_enemy_ids:
            asyncio.create_task(self.enemy_handler.respawn_enemy(enemy_id))

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

        bullet = template.copy()
        bullet["owner_uuid"] = client.user_id
        bullet["gun_type"] = bullet_shot.gun_type
        bullet["angle"] = bullet_shot.angle
        bullet["x"] = client.state.x
        bullet["y"] = client.state.y

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
