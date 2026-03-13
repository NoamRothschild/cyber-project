# Provides utility functions for the client for easier communication with server
from __future__ import annotations
import asyncio
from random import randint, random
from typing import Tuple, Set, Dict, Union
import protobuf.region_net_pb2 as region_net
import math
import time

from enemy_model import PlayerSnapshot
from enemy_model import EnemyModel

BUFF_SIZE = 1024
SECONDS_TO_MS = 1000
ENEMY_DAMAGE = 5

# 60Hz tick rate
TICK_INTERVAL_SEC = 1.0 / 60

# TODO: might parse this from a bullets config json file
BULLET_TYPES: Dict[str, Dict[str, Union[int, float]]] = {
    "Ak-7": {
        "ttl": 50,
        "speed": 20,
        "damage": 1,
        "range": 50,
    }
}


def loop_time_ms():
    return int(time.time() * SECONDS_TO_MS)


class ProjectileHandler:
    def __init__(self, tick_intervals: float = TICK_INTERVAL_SEC) -> None:
        self.lock = asyncio.Lock()
        self.projectiles = []
        self.tick_intervals = tick_intervals

    async def ticker(self):
        loop = asyncio.get_running_loop()
        global clients
        while True:
            start_time = loop.time()
            await self.tick()
            sleep_time = self.tick_intervals - (loop.time() - start_time)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    def create_background_task(self) -> None:
        """Start the ticker so bullets move every tick. Call once at server startup."""
        asyncio.create_task(self.ticker())

    def bullet_hit(self, proj: dict, client: Client) -> bool:
        dst_squared = (client.pos[0] - proj["x"]) ** 2 + (client.pos[1] - proj["y"]) ** 2
        return dst_squared < proj["range"] ** 2

    def bullet_hit_enemy(self, proj: dict, enemy: EnemyModel) -> bool:
        # Hit test against enemy center
        ex = enemy.x + enemy.w / 2
        ey = enemy.y + enemy.h / 2
        dx = ex - proj["x"]
        dy = ey - proj["y"]
        return (dx * dx + dy * dy) < (proj["range"] ** 2)

    async def tick(self) -> None:
        to_remove: list[dict] = []
        global clients
        global enemy_handler

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

            for client in clients:
                for proj in self.projectiles:
                    if proj['owner_uuid'] == client.user_id:
                        continue
                    if client.user_id in proj["already_hit"]:
                        continue

                    if self.bullet_hit(proj, client):
                        await client.hit(proj["damage"], proj["owner_uuid"])
                        proj["already_hit"].add(client.user_id)

        async with enemy_handler.lock:
            for proj in self.projectiles:
                for enemy in enemy_handler.enemies.values():
                    # prevent multi-hits from same bullet
                    if enemy.enemy_id in proj["already_hit"]:
                        continue

                    if self.bullet_hit_enemy(proj, enemy):
                        died = enemy.take_damage(int(proj["damage"]))
                        proj["already_hit"].add(enemy.enemy_id)

                        await enemy_handler.broadcast_enemy_hp(enemy)

                        if died:
                            await enemy_handler.respawn_enemy(enemy.enemy_id)

    async def add(self, bullet_shot: region_net.BulletShot, client: Client) -> bytes:
        template = BULLET_TYPES.get(bullet_shot.gun_type)
        if not template:
            print(f"Warn: unknown bullet type fired: {bullet_shot.gun_type} by user with id {client.user_id}")
            return b''

        bullet = template.copy()
        bullet["velocity_x"] = math.cos(bullet_shot.angle) * bullet["speed"]
        bullet["velocity_y"] = math.sin(bullet_shot.angle) * bullet["speed"]
        bullet["owner_uuid"] = client.user_id
        bullet["already_hit"] = set[int]()  # client ids that have been hit by this bullet
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


def should_update_location(old_pos: Tuple[float, float], new_pos: Tuple[float, float], min_dst=5) -> bool:
    """returns true when the distance between the two pos are above min_dst"""
    if old_pos == new_pos:
        return False
    traveled_dst_squared = (old_pos[0] - new_pos[0]) ** 2 + (old_pos[1] - new_pos[1]) ** 2
    min_dst_squared = min_dst ** 2

    return traveled_dst_squared > min_dst_squared


class EnemyHandler:
    def __init__(self, tick_intervals: float = TICK_INTERVAL_SEC) -> None:
        self.tick_intervals = tick_intervals
        self.enemies = {}  # key: enemy_id -> value: EnemyModel
        self.lock = asyncio.Lock()

        # Maintain a constant population
        self.target_enemy_count = 100

        self.world_min_x = 73000
        self.world_min_y = 31600
        # self.world_max_x = 77400
        # self.world_max_y = 43600
        self.world_max_x = 75000
        self.world_max_y = 33600
        self.next_enemy_id = 1

    def random_spawn(self) -> Tuple[float, float]:
        x = self.world_min_x + (self.world_max_x - self.world_min_x) * random()
        y = self.world_min_y + (self.world_max_y - self.world_min_y) * random()
        return x, y

    def spawn_enemy(self, enemy_id: int | None = None) -> EnemyModel:
        if enemy_id is None:
            enemy_id = self.next_enemy_id
            self.next_enemy_id += 1

        x, y = self.random_spawn()
        e = EnemyModel(enemy_id=enemy_id, x=x, y=y)
        e.reset_combat()
        e.last_sent_x = e.x
        e.last_sent_y = e.y
        self.enemies[enemy_id] = e
        return e

    async def ensure_population(self) -> None:
        """Create enemies until we have target_enemy_count."""
        async with self.lock:
            missing = self.target_enemy_count - len(self.enemies)
            if missing <= 0:
                return
            spawned = [self.spawn_enemy() for _ in range(missing)]

        # broadcast outside lock
        for e in spawned:
            await self.broadcast_enemy_spawn(e)

    async def respawn_enemy(self, enemy_id: int) -> None:
        """Respawn an enemy at a random location with full HP."""
        async with self.lock:
            enemy = self.enemies.get(enemy_id)
            if enemy is None:
                enemy = self.spawn_enemy(enemy_id)
            else:
                enemy.x, enemy.y = self.random_spawn()
                enemy.reset_combat()
                enemy.last_sent_x = enemy.x
                enemy.last_sent_y = enemy.y

        await self.broadcast_enemy_spawn(enemy)

    async def broadcast_enemy_spawn(self, enemy: EnemyModel) -> None:
        """Broadcast enemy location (spawn/respawn)."""
        global clients
        update = region_net.ServerResponse()
        update.sender_id = enemy.enemy_id
        update.other_data.new_location.CopyFrom(
            region_net.LocationBlock(
                x=int(enemy.x),
                y=int(enemy.y))
        )
        for c in clients:
            await c.write(update.SerializeToString())

        await self.broadcast_enemy_hp(enemy)

    async def broadcast_enemy_hp(self, enemy: EnemyModel) -> None:
        """Broadcast HP (reuses OtherPlayerData payload)."""
        global clients
        update = region_net.ServerResponse()
        update.sender_id = enemy.enemy_id
        update.other_data.CopyFrom(
            region_net.OtherPlayerData(
                HP=int(enemy.hp),
                player_id=enemy.enemy_id)
        )
        for c in clients:
            await c.write(update.SerializeToString())

    def create_background_task(self) -> None:
        asyncio.create_task(self.ticker())

    async def ticker(self):
        loop = asyncio.get_running_loop()
        while True:
            start_time = loop.time()
            await self.ensure_population()
            await self.tick()
            sleep_time = self.tick_intervals - (loop.time() - start_time)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    async def tick(self) -> None:
        global clients

        async with self.lock:
            now_ms = loop_time_ms()

            for enemy in self.enemies.values():
                attacked_player_id = enemy.update_state_machine(
                    now_ms,
                    [PlayerSnapshot(c.user_id, c.pos[0], c.pos[1]) for c in clients]
                )

                enemy.move_and_collide([])  # TODO: add obstacles later

                # Handle attack
                if attacked_player_id is not None:
                    for c in clients:
                        if c.user_id == attacked_player_id:
                            await c.hit(ENEMY_DAMAGE, enemy.enemy_id)

                if not should_update_location((enemy.last_sent_x, enemy.last_sent_y),
                                              (enemy.x, enemy.y)):
                    continue

                # Broadcast new location
                update = region_net.ServerResponse()
                update.sender_id = enemy.enemy_id
                update.other_data.new_location.CopyFrom(
                    region_net.LocationBlock(
                        x=int(enemy.x),
                        y=int(enemy.y)
                    )
                )
                enemy.last_sent_x = enemy.x
                enemy.last_sent_y = enemy.y

                for c in clients:
                    await c.write(update.SerializeToString())


# TODO: surround with a lock as well
clients: Set[Client] = set()

projectile_handler = ProjectileHandler()
enemy_handler = EnemyHandler()


class Client:
    @staticmethod
    async def client_handler_setup(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        print("new connection established")

        handshake_raw = await reader.read(1024)
        handshake = region_net.HandshakeStart()
        handshake.ParseFromString(handshake_raw)
        # TODO: verify the session id with the auth server && cache it
        session_id = handshake.session_id

        # TODO: get this one from the auth server
        user_id = randint(0, 2 ** 31 - 1)

        handshake.Clear()
        handshake.CopyFrom(region_net.HandshakeStart(
            kind=region_net.HandshakeStart.SERVER_OK,
            user_id=user_id,
        ))

        writer.write(handshake.SerializeToString())
        await writer.drain()

        global clients
        self = Client(reader, writer, session_id, user_id)
        clients.add(self)

        try:
            await self.handle()
        finally:
            clients.remove(self)

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, session_id: int,
                 user_id: int) -> None:
        self.reader = reader
        self.writer = writer
        self.writer_lock = asyncio.Lock()
        self.session_id = session_id
        self.user_id = user_id
        self.hp = 400
        self.pos: Tuple[int, int] = (0, 0)  # TODO: fetch this from the DB

    async def hit(self, count, hitter_id: int):
        self.hp -= count
        update = region_net.ServerResponse()
        update.sender_id = hitter_id
        update.other_data.CopyFrom(region_net.OtherPlayerData(HP=self.hp, player_id=self.user_id))
        await self.broadcast(update.SerializeToString())
        await self.write(update.SerializeToString())

    async def handle(self):
        while True:
            data = await self.reader.read(1024)
            if not data:
                break

            update = region_net.RegionUpdate()
            update.ParseFromString(data)
            print(f"received: {update}")

            payload_type = update.WhichOneof("payload")
            if payload_type == "location_block":
                pos = (update.location_block.x, update.location_block.y)
                self.pos = pos

                resp = region_net.ServerResponse()
                resp.sender_id = self.user_id
                resp.other_data.new_location.CopyFrom(region_net.LocationBlock(x=pos[0], y=pos[1]))
                await self.broadcast(resp.SerializeToString())
            elif payload_type == "bullet_shot":
                global projectile_handler
                update_bytes = await projectile_handler.add(update.bullet_shot, self)
                if update_bytes:
                    await self.broadcast(update_bytes)

    async def write(self, data: bytes):
        async with self.writer_lock:
            self.writer.write(data)
            await self.writer.drain()

    async def broadcast(self, data: bytes):
        global clients
        for client in clients:
            if client == self:
                continue
            await client.write(data)
        print(f"data broadcasted to {len(clients) - 1} clients")
