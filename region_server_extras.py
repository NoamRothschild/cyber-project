# Provides utility functions for the client for easier communication with server
from __future__ import annotations
import asyncio
import socket
import threading
from typing import Tuple, Set, TYPE_CHECKING
import protobuf.region_net_pb2 as region_net

if TYPE_CHECKING:
    from Game import Game

BUFF_SIZE = 1024

# TODO: sorround with a lock as well
clients: Set[Client] = set()

class Client:
    @staticmethod
    async def client_handler_setup(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        print("new connection established")
        global clients
        self = Client(reader, writer)
        clients.add(self)

        try:
            await self.handle()
        finally:
            clients.remove(self)

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader = reader
        self.writer = writer
        self.writer_lock = asyncio.Lock()

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

                resp = region_net.ServerResponse()
                resp.other_data.new_location.CopyFrom(region_net.LocationBlock(x=pos[0], y=pos[1]))
                await self.broadcast(resp.SerializeToString())

    async def write(self, data: bytes):
        async with self.writer_lock:
            self.writer.write(data)
            await self.writer.drain()

    async def broadcast(self, data: bytes):
        global clients
        for client in clients:
            if client == self:
                continue
            async with client.writer_lock:
                self.writer.write(data)
                await self.writer.drain()
        print(f"data broadcasted to {len(clients) - 1} clients")


def server_listener(game: Game, zone: ZoneConnection):
    """
    Start this one in another thread
    Assumes a connection has already been established in `game.region_conn`
    """
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
            # if payload_type == "new_location":
            #     ...
            # elif payload_type == "HP":
            #     ...
            # elif payload_type == "state":
            #     ...


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

    def open_reliable_conn(self) -> None:
        """opens the TCP conn. can throw"""
        self.reliable_conn.connect((self.host, self.reliable_port))
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

def should_update_location(old_pos: Tuple[int, int], new_pos: Tuple[int, int], min_dst=5) -> bool:
    """returns true when the distance between the two pos are above min_dst"""
    if old_pos == new_pos:
        return False
    traveled_dst_squared = (old_pos[0] - new_pos[0]) ** 2 + (old_pos[1] - new_pos[1]) ** 2
    min_dst_squared = min_dst ** 2

    return traveled_dst_squared > min_dst_squared
