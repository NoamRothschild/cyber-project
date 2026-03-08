# Provides utility functions for the client for easier communication with server
from __future__ import annotations
import asyncio
from typing import Tuple, Set, Dict, Union
import protobuf.region_net_pb2 as region_net
import math
import redis
from auth_server import data_db_handler as db

REDIS_PORT = 6379
IP = "127.0.0.1"
redis_client = redis.Redis(host=IP, port=REDIS_PORT, decode_responses=True)

BUFF_SIZE = 1024

# 60Hz tick rate
TICK_INTERVAL_SEC = 1.0 / 60

# TODO: might parse this from a bullets config json file
BULLET_TYPES: Dict[str, Dict[str, Union[int, float]]] = {
    "Ak-7": {
        "ttl": 50,
        "speed": 20,
        "damage": 30,
        "range": 50,
    },
    "bow": {
        "ttl": 50,  # ttl
        "speed": 20,  # speed
        "damage": 5,  # damage
        "range": 50,    }
}


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

    async def tick(self) -> None:
        to_remove: list[dict] = []
        global clients
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


# TODO: sorround with a lock as well
clients: Set[Client] = set()

projectile_handler = ProjectileHandler()


class Client:
    @staticmethod
    async def client_handler_setup(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        print("new connection established")

        handshake_raw = await reader.read(1024)
        handshake = region_net.HandshakeStart()
        handshake.ParseFromString(handshake_raw)
        session_id = handshake.session_id
        user_id_str = redis_client.get(f"session:{session_id}")

        if user_id_str is None:
            print(f"Authentication failed for session: {session_id}")
            # Send failure status if your proto supports it, or just close
            response = region_net.HandshakeStart(
                kind=region_net.HandshakeStart.AUTH_FAIL,
                session_id=-1,
            )
            writer.write(response.SerializeToString())
            await writer.drain()

            writer.close()
            await writer.wait_closed()
            return

        user_id = int(user_id_str)
        print(f"User {user_id} authenticated via Redis.")

        player_stats = db.load_player(user_id)

        if not player_stats:
            print("Error: Player data not found! Fallback to defaults.")
            player_stats = {
                "health": 400,
                "money": 0,
                "weapons": [0] * 10,
                "potions": [0] * 10,
                "spawn_x": 74010,
                "spawn_y": 32605
            }

        handshake.Clear()
        response = region_net.HandshakeStart(
            kind=region_net.HandshakeStart.SERVER_OK,
            user_id=user_id,
            health=player_stats["health"],
            money=player_stats["money"],
            pos_x=player_stats["spawn_x"],
            pos_y=player_stats["spawn_y"]
        )

        response.weapons.extend(player_stats["weapons"])
        response.potions.extend(player_stats["potions"])

        writer.write(response.SerializeToString())
        await writer.drain()

        global clients
        self = Client(reader, writer, session_id, user_id, player_stats)
        clients.add(self)

        try:
            await self.handle()
        finally:
            clients.remove(self)

            print(f"User {user_id} disconnected. Saving state to database...")

            # Package the live memory back into a dictionary
            db.save_player(
                player_id=self.user_id,
                health=self.hp,
                money=self.money,
                weapons_list=list(self.weapons),
                potions_list=list(self.potions),
                spawn_x=int(self.pos[0]),
                spawn_y=int(self.pos[1])
            )
            print(f" User {user_id} saved successfully.")

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, session_id: str,
                 user_id: int, stats:dict) -> None:
        self.reader = reader
        self.writer = writer
        self.writer_lock = asyncio.Lock()
        self.session_id = session_id
        self.user_id = user_id

        self.hp = stats["health"]
        self.pos: Tuple[int, int] = (stats["spawn_x"], stats["spawn_y"])

        self.money = stats["money"]
        self.weapons = stats["weapons"]
        self.potions = stats["potions"]

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
            elif payload_type == "potion_use":
                print("should + h")
                if update.potion_use.potion_type == region_net.PotionUse.PotionType.health:

                    await self.hit(-update.potion_use.HowMuch,self.user_id)

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
