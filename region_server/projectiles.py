from __future__ import annotations
import asyncio
import itertools
import math
import protobuf.region_net_pb2 as region_net
from constants import BULLET_TYPES, TICK_INTERVAL_SEC

_next_projectile_id = itertools.count()


class ProjectileHandler:
    """Handles projectiles for one region node; uses node.clients when ticking."""

    def __init__(
        self,
        node: "RegionNode",
        tick_intervals: float = TICK_INTERVAL_SEC,
    ) -> None:
        self._node = node
        self.lock = asyncio.Lock()
        self.projectiles: list[dict] = []
        self._incoming: list[dict] = []
        self.tick_intervals = tick_intervals

    def bullet_hit(self, proj: dict, client: "Client") -> bool:
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

    async def tick(self, cycle: int) -> None:
        from region_node import nodes, RegionNode
        from servers_communication import broadcast_on

        to_remove: list[dict] = []
        to_transfer: list[tuple[dict, tuple[int, int]]] = []
        clients = self._node.clients

        async with self.lock:
            if self._incoming:
                self.projectiles.extend(self._incoming)
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

                if not self._node.contains(int(proj["x"]), int(proj["y"])):
                    new_node_pos = RegionNode.which_node(
                        int(proj["x"]), int(proj["y"])
                    )
                    if new_node_pos != self._node.node_pos:
                        to_transfer.append((proj, new_node_pos))

            for e in to_remove:
                self.projectiles.remove(e)
            for proj, _ in to_transfer:
                self.projectiles.remove(proj)

            for client in clients.values():
                for proj in self.projectiles:
                    if proj["owner_uuid"] == client.user_id:
                        continue
                    if client.user_id in proj["already_hit"]:
                        continue
                    if self.bullet_hit(proj, client):
                        await client.hit(proj["damage"], proj["owner_uuid"])
                        proj["already_hit"].add(client.user_id)

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
                await broadcast_on(node_idx, update.SerializeToString())
                print(
                    f"projectile left to off-server node {new_node_pos}, forwarding via Redis"
                )

    async def add(
        self, bullet_shot: region_net.BulletShot, client: "Client"
    ) -> tuple[bytes, list[dict]]:
        template = BULLET_TYPES.get(bullet_shot.gun_type)
        if not template:
            print(
                f"Warn: unknown bullet type fired: {bullet_shot.gun_type} "
                f"by user with id {client.user_id}"
            )
            return b"", []

        bullet = template.copy()
        bullet["velocity_x"] = math.cos(bullet_shot.angle) * bullet["speed"]
        bullet["velocity_y"] = math.sin(bullet_shot.angle) * bullet["speed"]
        bullet["owner_uuid"] = client.user_id
        bullet["gun_type"] = bullet_shot.gun_type
        bullet["angle"] = bullet_shot.angle
        bullet["x"] = client.state.x
        bullet["y"] = client.state.y

        update = region_net.ServerResponse(sender_id=client.user_id)
        new_projectiles: list[dict] = []

        async with self.lock:
            for i in range(bullet_shot.count):
                blt = bullet.copy()
                blt["already_hit"] = set()
                blt["seen_by"] = {client.user_id}
                blt["id"] = next(_next_projectile_id)
                blt["x"] += i * blt["velocity_x"]
                blt["y"] += i * blt["velocity_y"]
                self.projectiles.append(blt)
                new_projectiles.append(blt)
                update.bullet_shot.add(
                    gun_type=bullet_shot.gun_type,
                    angle=bullet_shot.angle,
                    count=1,
                    x=int(blt["x"]),
                    y=int(blt["y"]),
                    ttl=int(blt["ttl"]),
                    speed=int(blt["speed"]),
                )

        return update.SerializeToString(), new_projectiles

    async def receive_transferred(self, proj: dict) -> None:
        """Receive a projectile transferred from an adjacent node on this server."""
        print(f"Transferred projectile received: id={proj['id']} at node={self._node.node_pos}")
        async with self.lock:
            self._incoming.append(proj)
        await self._broadcast_to_unseen_clients(proj)
        await self.broadcast_to_adjacent([proj])

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
        from region_node import nodes, RegionNode
        from servers_communication import broadcast_on

        for proj in projectiles:
            data = self._build_bullet_response(proj)

            for bound_x, bound_y in self._node.possible_bounding_nodes(
                int(proj["x"]), int(proj["y"])
            ):
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
                    await broadcast_on(node_idx, update.SerializeToString())
                    print(
                        f"projectile left to off-server node {node_pos}, forwarding via Redis"
                    )
