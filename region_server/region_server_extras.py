# Provides utility functions for the client for easier communication with server
from __future__ import annotations
import asyncio
from random import randint
from typing import Tuple, Set, Dict, Union

import aioudp
import protobuf.region_net_pb2 as region_net
import math

BUFF_SIZE = 1024

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

class ProjectileHandler:
    def __init__(self, tick_intervals: float = TICK_INTERVAL_SEC) -> None:
        self.lock = asyncio.Lock()
        self.projectiles = []
        self.tick_intervals = tick_intervals

    async def ticker(self):
        loop = asyncio.get_running_loop()
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

            for client in clients.values():
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


# TODO: sorround with a lock as well
clients: Dict[int, Client] = {}

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

        # when a new player joins:
        # 1. provide the new client everyone's location (ServerResponse so client can render entities)
        # 2. provide everyone the new client's location
        for client in clients.values():
            resp_to_new = region_net.ServerResponse()
            resp_to_new.sender_id = client.user_id
            resp_to_new.other_data.new_location.CopyFrom(
                region_net.LocationBlock(x=client.pos[0], y=client.pos[1])
            )
            await self.write(resp_to_new.SerializeToString())

            resp_to_other = region_net.ServerResponse()
            resp_to_other.sender_id = self.user_id
            resp_to_other.other_data.new_location.CopyFrom(
                region_net.LocationBlock(x=self.pos[0], y=self.pos[1])
            )
            await client.write(resp_to_other.SerializeToString())

        clients[session_id] = self

        try:
            await self.handle_tcp()
        finally:
            self.stop_udp_conn.set()
            del clients[session_id]

    @staticmethod
    async def udp_handler(conn: aioudp.Connection):
        global clients
        handshake_raw = await conn.recv()
        handshake = region_net.HandshakeStart()
        handshake.ParseFromString(handshake_raw)

        session_id = handshake.session_id
        if cli := clients.get(session_id):
            handshake.Clear()
            handshake.CopyFrom(region_net.HandshakeStart(
                kind=region_net.HandshakeStart.SERVER_OK,
            ))
            await conn.send(handshake.SerializeToString())

            cli.udp_conn = conn
            try:
                await cli.handle_udp(conn)
            finally:
                cli.udp_conn = None
        else:
            handshake.Clear()
            handshake.CopyFrom(region_net.HandshakeStart(
                kind=region_net.HandshakeStart.SERVER_FAIL_INVALID_SESSION_ID,
            ))
            await conn.send(handshake.SerializeToString())

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, session_id: int, user_id: int) -> None:
        self.reader = reader
        self.writer = writer
        self.writer_lock = asyncio.Lock()
        self.udp_conn: aioudp.Connection | None = None
        self.stop_udp_conn = asyncio.Event()
        self.last_recevied_seq = 0
        self.last_sent_seq = 0
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

    FROM_TCP = 0
    FROM_UDP = 1
    async def handle_region_update(self, data: bytes, source: int):
        update = region_net.RegionUpdate()
        update.ParseFromString(data)
        print(f"received: {update}")
        if source == Client.FROM_UDP:
            seq = update.seq_num
            if seq and seq < self.last_recevied_seq:
                print(f"[INFO]: ignoring packet with {seq=} since max seq={self.last_recevied_seq}")
                return
            self.last_recevied_seq = seq

        payload_type = update.WhichOneof("payload")
        if payload_type == "location_block":
            pos = (update.location_block.x, update.location_block.y)
            self.pos = pos

            resp = region_net.ServerResponse()
            resp.sender_id = self.user_id
            resp.other_data.new_location.CopyFrom(region_net.LocationBlock(x=pos[0], y=pos[1]))
            await self.broadcast_udp(resp)
        elif payload_type == "bullet_shot":
            global projectile_handler
            update_bytes = await projectile_handler.add(update.bullet_shot, self)
            if update_bytes:
                await self.broadcast(update_bytes)

    async def handle_tcp(self):
        while True:
            data = await self.reader.read(1024)
            if not data:
                break
            await self.handle_region_update(data, Client.FROM_TCP)

    async def handle_udp(self, conn: aioudp.Connection):
        while not self.stop_udp_conn.is_set():
            message = await conn.recv()
            if not message:
                self.udp_conn = None
                break
            await self.handle_region_update(message, Client.FROM_UDP)

    async def write_udp(self, data: region_net.ServerResponse):
        data.seq_num = self.last_sent_seq
        raw = data.SerializeToString()
        if conn := self.udp_conn:
            await conn.send(raw)
            self.last_sent_seq += 1
        else:
            await self.write(raw) # fallback to tcp when udp sock is not available

    async def write(self, data: bytes):
        async with self.writer_lock:
            self.writer.write(data)
            await self.writer.drain()

    async def broadcast_udp(self, data: region_net.ServerResponse):
        global clients
        for client in clients.values():
            if client == self:
                continue
            data.seq_num = client.last_sent_seq
            raw = data.SerializeToString()

            try:
                if conn := client.udp_conn:
                    await conn.send(raw)
                    client.last_sent_seq += 1
                else:
                    await client.write(raw) # fallback to tcp when udp sock is not available
            except Exception as e:
                print(f"Client {client.user_id} was unable to receive data: {e}, ignoring...")
        print(f"data broadcasted to {len(clients) - 1} clients")

    async def broadcast(self, data: bytes):
        global clients
        for client in clients.values():
            if client == self:
                continue
            await client.write(data)
        print(f"data broadcasted to {len(clients) - 1} clients")
