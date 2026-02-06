# Provides utility functions for the client for easier communication with server
from __future__ import annotations
import asyncio
from random import randint
import socket
import threading
from typing import Tuple, Set, TYPE_CHECKING
import protobuf.region_net_pb2 as region_net
import math

if TYPE_CHECKING:
    from game import Game

BUFF_SIZE = 1024

# TODO: might parse this from a bullets config json file
BULLET_TYPES = {
    "Ak-7": {
        "ttl": 50,
        "speed": 20,
        "damage": 10.0,
    }
}

class ProjectileHandler:
    def __init__(self, tick_intervals: float = 0.1) -> None:
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
            await asyncio.sleep(sleep_time)

    async def create_background_task(self):
        # asyncio.create_task()
        pass

    async def tick(self) -> None:
        to_remove = set()
        async with self.lock:
            for proj in self.projectiles:
                proj["ttl"] -= 1
                if proj["ttl"] <= 0:
                    to_remove.add(proj)
                    continue
                proj["x"] += proj["velocity_x"]
                proj["y"] += proj["velocity_y"]
            for e in to_remove:
                self.projectiles.remove(e)

    async def add(self, bullet_shot: region_net.BulletShot, client: Client) -> bytes:
        bullet = BULLET_TYPES.get(bullet_shot.gun_type)
        if not bullet:
            print(f"Warn: unknown bullet type fired: {bullet_shot.gun_type} by user with id {client.user_id}")
            return b''

        bullet["velocity_x"] = math.cos(bullet_shot.angle) * bullet["speed"]
        bullet["velocity_y"] = math.sin(bullet_shot.angle) * bullet["speed"]
        bullet["owner_uuid"] = client.user_id
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
        # TODO: verify the session id with the auth server && cache it
        session_id = handshake.session_id
        handshake.Clear()
        handshake.CopyFrom(region_net.HandshakeStart(
            kind=region_net.HandshakeStart.SERVER_OK,
        ))
        writer.write(handshake.SerializeToString())
        await writer.drain()
        # TODO: get this one from the auth server
        user_id = randint(0, 2 ** 31 - 1)

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
        self.pos: Tuple[int, int] = (0, 0) # TODO: fetch this from the DB

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


def server_listener(game: Game, zone: ZoneConnection):
    """
    Start this one in another thread
    Assumes a connection has already been established in `game.region_conn`
    """
    # Imported lazily so the standalone region server
    # does not pull in pygame / client-only code.
    from Bullets import Bullets

    while True:
        server_raw = zone.reliable_conn.recv(BUFF_SIZE)
        if not server_raw:
            continue
        parsed = region_net.ServerResponse()
        parsed.ParseFromString(server_raw)
        print(f"received: {parsed}")

        payload_type = parsed.WhichOneof("payload")
        print(f'{payload_type=}')
        if payload_type == "move_self":
            print("force moving self...")
            # TODO: have a lock sorrounding player hitbox
            hb = game.level.player.hitbox
            hb.x = parsed.move_self.x
            hb.y = parsed.move_self.y
        elif payload_type == "other_data":
            payload_type = parsed.other_data.WhichOneof("payload")
            print(f"{payload_type=}")
            if payload_type == "new_location":
                pos = parsed.other_data.new_location
                game.level.entities.add_or_update(parsed.sender_id, (pos.x, pos.y), [game.level.visible_sprites])
            # elif payload_type == "HP":
            #     ...
            # elif payload_type == "state":
            #     ...
        elif len(parsed.bullet_shot) > 0:
            inc_bullets = parsed.bullet_shot
            for bullet in inc_bullets:
                Bullets.BulletLS.append(Bullets(
                    bullet.gun_type + '_bullet',
                    bullet.x, bullet.y,
                    angle=bullet.angle,
                    from_network=True)
                )


class ZoneConnection:
    def __init__(self, game: Game, host: str, reliable_port: int, fast_port: int) -> None:
        # the position the server thinks we are at
        self.server_known_pos: Tuple[int, int] = (0, 0)

        # reliable -> TCP, fast -> UDP
        self.reliable_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.fast_conn = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self.host = host
        self.reliable_port = reliable_port
        self.fast_port = fast_port

        self.game = game

    def open_reliable_conn(self, session_id: int) -> None:
        """opens the TCP conn. can throw"""
        self.reliable_conn.connect((self.host, self.reliable_port))
        handshake = region_net.HandshakeStart()
        handshake.session_id = session_id
        handshake.kind = handshake.LOGIN

        self.reliable_conn.sendall(handshake.SerializeToString())
        login_resp_raw = self.reliable_conn.recv(BUFF_SIZE)
        login_resp = region_net.HandshakeStart()
        login_resp.ParseFromString(login_resp_raw)
        if login_resp.kind != login_resp.SERVER_OK:
            raise RuntimeError("failed connecting to zone: invalid session id")

        listener = threading.Thread(target=server_listener, args=(self.game, self,))
        listener.start()

    def try_send_update_pos(self, pos: Tuple[int, int]) -> None:
        """NOTE: currently uses TCP. TODO: move to udp"""
        if not should_update_location(self.server_known_pos, pos):
            return

        update = region_net.RegionUpdate()
        update.location_block.CopyFrom(
            region_net.LocationBlock(
                x=pos[0], y=pos[1]
            )
        )

        self.server_known_pos = pos
        self.reliable_conn.sendall(update.SerializeToString())

    def try_send_bullet(self, gun_type: str, angle: float, count: int) -> None:
        """NOTE: currently uses TCP. TODO: move to udp"""
        update = region_net.RegionUpdate()
        update.bullet_shot.CopyFrom(
            region_net.BulletShot(
                gun_type=gun_type, angle=angle, count=count
            )
        )

        self.reliable_conn.sendall(update.SerializeToString())


class ZoneConnectionSingleton:
    _instance: None | ZoneConnectionSingleton = None
    _lock = threading.Lock()
    _config_game: Game | None = None
    _config_host: str | None = None
    _config_reliable_port: int | None = None
    _config_fast_port: int | None = None

    @staticmethod
    def set_creds(game: Game, host: str, reliable_port: int, fast_port: int):
        ZoneConnectionSingleton._config_game = game
        ZoneConnectionSingleton._config_host = host
        ZoneConnectionSingleton._config_reliable_port = reliable_port
        ZoneConnectionSingleton._config_fast_port = fast_port

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                if cls._config_game is None or cls._config_host is None or cls._config_reliable_port is None or cls._config_fast_port is None:
                    raise RuntimeError("A field value was missing while trying to construct ZoneConnection")

                cls._instance = super(ZoneConnectionSingleton, cls).__new__(cls)
                cls.zone = ZoneConnection(cls._config_game, cls._config_host, cls._config_reliable_port, cls._config_fast_port)
        return cls._instance

def should_update_location(old_pos: Tuple[int, int], new_pos: Tuple[int, int], min_dst=5) -> bool:
    """returns true when the distance between the two pos are above min_dst"""
    if old_pos == new_pos:
        return False
    traveled_dst_squared = (old_pos[0] - new_pos[0]) ** 2 + (old_pos[1] - new_pos[1]) ** 2
    min_dst_squared = min_dst ** 2

    return traveled_dst_squared > min_dst_squared
