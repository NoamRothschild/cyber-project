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

SERVER_WEAPON_MAP = {
    "Ak 47": 1,
    "bow": 2,
    "sword": 3,
    "Assault rifle": 4,
    "Pistol": 5
}

# The absolute maximum ammo allowed for each weapon ID
SERVER_MAX_AMMO = {
    1: 15,    # Ak 47
    2: 3,     # bow
    3: 1000,  # sword
    4: 30,    # Assault rifle
    5: 10     # Pistol
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
                "ammo": [30] * 10,  # <-- NEW: Fallback ammo
                "potions": [0] * 10,
                "spawn_x": 74010,
                "spawn_y": 32605
            }
        else:
            # --- THE DATABASE CLEANER ---
            # Scrub the DB data BEFORE we send it to the client!
            # Clamps illegal ammo values during login
            for i in range(len(player_stats["weapons"])):
                weapon_id = player_stats["weapons"][i]
                if weapon_id != 0:
                    max_ammo = SERVER_MAX_AMMO.get(weapon_id, 30)

                    if player_stats["ammo"][i] > max_ammo:
                        player_stats["ammo"][i] = max_ammo
                        print(f"[SECURITY] Clamped over-cap ammo for User {user_id} down to {max_ammo}")
                    elif player_stats["ammo"][i] < 0:
                        player_stats["ammo"][i] = 0
                        print(f"[SECURITY] Clamped negative ammo for User {user_id} up to 0")
                else:
                    player_stats["ammo"][i] = 0

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
        response.ammo.extend(player_stats["ammo"])  # <-- NEW: Send ammo to client!

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

            # <-- NEW: Add self.ammo to the save function!
            db.save_player(
                player_id=self.user_id,
                health=self.hp,
                money=self.money,
                weapons_list=list(self.weapons),
                ammo_list=list(self.ammo),
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
        self.ammo = stats["ammo"] # <-- NEW: Server tracks ammo in RAM



    async def hit(self, count, hitter_id: int):
        self.hp -= count

        if self.hp > 400:
            self.hp = 400
        elif self.hp < 0:
            self.hp = 0

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
                # HowMuch is positive for healing (+15) and negative for damage (-30).
                # Since hit() subtracts the number, we flip the sign here so the math works perfectly.
                await self.hit(-update.potion_use.HowMuch, self.user_id)
                print(f"Server: Player {self.user_id} HP changed! HP is now {self.hp}")


            elif payload_type == "item_drop":
                idx = update.item_drop.inventory_index
                kind = update.item_drop.item_kind

                # --- HANDLING DROPS ---
                if idx != -1:
                    if kind == "weapon":
                        current_idx = 0

                        for i in range(len(self.weapons)):
                            if self.weapons[i] != 0:
                                if current_idx == idx:
                                    self.weapons[i] = 0
                                    break
                                current_idx += 1

                # --- NEW: HANDLING PICKUPS ---
                else:
                    # Convert the name back to an ID (e.g., "Ak 47" -> 1)
                    weapon_id = SERVER_WEAPON_MAP.get(kind)
                    if weapon_id:
                        # Find the first empty slot (0) and fill it
                        for i in range(len(self.weapons)):
                            if self.weapons[i] == 0:
                                self.weapons[i] = weapon_id
                                print(f"Server: Player {self.user_id} picked up {kind} into slot {i}")
                                break



            elif payload_type == "bullet_shot":
                gun_type = update.bullet_shot.gun_type
                weapon_id = SERVER_WEAPON_MAP.get(gun_type)

                # We start by assuming the shot is illegal
                can_shoot = False

                # NEW: Server Authority - Validate ammo in RAM before spawning bullet
                if weapon_id and weapon_id in self.weapons:
                    slot_index = self.weapons.index(weapon_id)

                    # --- SERVER SECURITY: Do they actually have enough bullets? ---
                    if self.ammo[slot_index] >= update.bullet_shot.count:
                        self.ammo[slot_index] -= update.bullet_shot.count
                        can_shoot = True  # The math checks out, approve the shot!

                    else:
                        print(f"[SECURITY] Player {self.user_id} tried to shoot {gun_type} without ammo!")

                # Only spawn the bullet if the server approved it
                if can_shoot:
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
