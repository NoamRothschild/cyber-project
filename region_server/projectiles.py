from __future__ import annotations
import asyncio
import math
import protobuf.region_net_pb2 as region_net
from constants import BULLET_TYPES, TICK_INTERVAL_SEC


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
        self.tick_intervals = tick_intervals

    def bullet_hit(self, proj: dict, client: "Client") -> bool:
        dst_squared = (client.pos[0] - proj["x"]) ** 2 + (
            client.pos[1] - proj["y"]
        ) ** 2
        return dst_squared < proj["range"] ** 2

    async def tick(self) -> None:
        to_remove: list[dict] = []
        clients = self._node.clients
        async with self.lock:
            for proj in self.projectiles:
                proj["ttl"] -= 1
                if proj["ttl"] <= 0:
                    to_remove.append(proj)
                    continue
                proj["x"] += proj["velocity_x"]
                proj["y"] += proj["velocity_y"]
            for e in to_remove:
                self.projectiles.remove(e)

            for client in clients.values():
                for proj in self.projectiles:
                    if proj["owner_uuid"] == client.user_id:
                        continue
                    if client.user_id in proj["already_hit"]:
                        continue
                    if self.bullet_hit(proj, client):
                        await client.hit(proj["damage"], proj["owner_uuid"])
                        proj["already_hit"].add(client.user_id)

    async def add(self, bullet_shot: region_net.BulletShot, client: "Client") -> bytes:
        template = BULLET_TYPES.get(bullet_shot.gun_type)
        if not template:
            print(
                f"Warn: unknown bullet type fired: {bullet_shot.gun_type} by user with id {client.user_id}"
            )
            return b""

        bullet = template.copy()
        bullet["velocity_x"] = math.cos(bullet_shot.angle) * bullet["speed"]
        bullet["velocity_y"] = math.sin(bullet_shot.angle) * bullet["speed"]
        bullet["owner_uuid"] = client.user_id
        bullet["already_hit"] = set()
        bullet["x"] = client.pos[0]
        bullet["y"] = client.pos[1]

        update = region_net.ServerResponse(sender_id=client.user_id)

        async with self.lock:
            for i in range(bullet_shot.count):
                blt = bullet.copy()
                blt["x"] += i * blt["velocity_x"]
                blt["y"] += i * blt["velocity_y"]
                self.projectiles.append(blt)
                update.bullet_shot.add(
                    gun_type=bullet_shot.gun_type,
                    angle=bullet_shot.angle,
                    count=1,
                    x=int(blt["x"]),
                    y=int(blt["y"]),
                    ttl=int(blt["ttl"]),
                    speed=int(blt["speed"]),
                )

        return update.SerializeToString()
