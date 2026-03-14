# Provides utility functions for the client for easier communication with server
from __future__ import annotations
import asyncio
from random import randint
from typing import Tuple, Set, Dict, Union
import protobuf.region_net_pb2 as region_net
import math

BUFF_SIZE = 1024

# 60Hz tick rate
TICK_INTERVAL_SEC = 1.0 / 60

# TODO: might parse this from a bullets config json file
BULLET_TYPES: Dict[str, Dict[str, Union[int, float]]] = {
    "Ak 47": {
        "ttl": 20,
        "speed": 25,
        "damage": 40,
        "range": 20,
    },

    "Assault rifle": {
        "ttl": 15,
        "speed": 30,
        "damage": 25,
        "range": 15,
    },

    "Pistol": {
        "ttl": 10,
        "speed": 19,
        "damage": 30,
        "range": 10,
    },

    "sword": {
        "ttl": 3,
        "speed": 7,
        "damage": 60,
        "range": 3,
    },

    "bow": {
        "ttl": 50,  # ttl
        "speed": 20,  # speed
        "damage ": 5,  # damage
        "range": 50,    }
}

user_stt={
    "user1":{
            "ammo_collection":{
                                    "Ak 47":1,
                                    "arrows":1,
                                    "sword hit":1,
                                    "Assault rifle bullets":1,
                                    "Pistol bullets":1,
                                },

            "magazine": {
                        "Ak 47": 2,
                        "bow": 2,
                        "Assault rifle": 2,
                        "Pistol": 2,
                        "sword": 1000
                        },

                "cash":300
            }
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


    def get_player_mag_stat(self, user_id, bullet_type):
        try:
            emmo = user_stt[user_id]["ammo_collection"][bullet_type]
        except:
            print(user_id, " is not registered or no gun type name: ", bullet_type)
            return 0
        return emmo

    def dec_player_mag_stat(self, user_id, bullet_type):
        try:
           user_stt[user_id]["ammo_collection"][bullet_type]-=1
        except:
            print(user_id," is not registered or no gun type name: ",bullet_type)
        return

    async def add(self, bullet_shot: region_net.BulletShot, client: Client) -> bytes:
        template = BULLET_TYPES.get(bullet_shot.gun_type)
        if not template:
            print(f"Warn: unknown bullet type fired: {bullet_shot.gun_type} by user with id {client.user_id}")
            return b''

        mag = self.get_player_mag_stat("user1", bullet_shot.gun_type)
        #ammo = self.getPlayer_AMMO_Stat(client.user_id, bullet_shot.gun_type)

        if mag > 0:
            self.dec_player_mag_stat("user1", bullet_shot.gun_type)
            #self.decPlayer_AMMO_Stat(client.user_id, bullet_shot.gun_type)

            bullet = template.copy()
            bullet["velocity_x"] = math.cos(bullet_shot.angle) * bullet["speed"]
            bullet["velocity_y"] = math.sin(bullet_shot.angle) * bullet["speed"]
            bullet["owner_uuid"] = client.user_id
            bullet["already_hit"] = set[int]() # client ids that have been hit by this bullet
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
        return None


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

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, session_id: int, user_id: int) -> None:
        self.reader = reader
        self.writer = writer
        self.writer_lock = asyncio.Lock()
        self.session_id = session_id
        self.user_id = user_id
        self.hp = 400
        self.pos: Tuple[int, int] = (0, 0) # TODO: fetch this from the DB

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

            #SHOP anticheat
            elif payload_type == "shop_buy":

                resp = region_net.ServerResponse()
                resp.sender_id = self.user_id

                kind = update.shop_buy.item_type
                name = update.shop_buy.item_name
                amount = update.shop_buy.amount
                price= self.priceOfTheSHOPING(kind, name)

                total = price * amount

                player = user_stt["user1"]
                #player = user_stt[client.user_id]
                if player["cash"] >= total:
                    player["cash"] -= total
                    resp.other_data.shop_ans = True
                else:
                    resp.other_data.shop_ans = False

                print(resp.other_data.shop_ans)
                await self.write(resp.SerializeToString())

    def priceOfTheSHOPING(self,kind,name):
        price = 0

        if kind == "weapon":
            prices = {
                "Ak 47": 300,
                "Assault rifle": 350,
                "Pistol": 200,
                "bow": 80,
                "sword": 60
            }
            price = prices.get(name, 0)

        elif kind == "ammo":
            prices = {
                "Pistol bullets": 40,
                "AK 47 bullets": 50,
                "Assault rifle bullets": 60,
                "arrows": 60
            }
            price = prices.get(name, 0)

        elif kind == "potion":
            prices = {
                "healing": 140,
                "speed": 70,
                "super_speed": 140
            }
            price = prices.get(name, 0)

        return price

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

