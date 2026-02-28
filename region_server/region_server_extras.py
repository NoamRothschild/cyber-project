from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from random import randint
from typing import TYPE_CHECKING, Tuple
import aioudp
import protobuf.region_net_pb2 as region_net
from constants import BUFF_SIZE, CLIENT_RECEIVE_WIDTH, CLIENT_RECEIVE_HEIGHT

from state import get_client
from nodes import nodes

if TYPE_CHECKING:
    from region_node import RegionNode


@dataclass
class PlayerState:
    x: int
    y: int
    cell_x: int
    cell_y: int
    hp: int = 400


@dataclass
class ConnectionState:
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    writer_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    udp_conn: aioudp.Connection | None = None
    stop_udp_conn: asyncio.Event = field(default_factory=asyncio.Event)
    last_recevied_seq: int = 0
    last_sent_seq: int = 0


class Client:
    FROM_TCP = 0
    FROM_UDP = 1

    @staticmethod
    async def client_handler_setup(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        print("new connection established")

        handshake_raw = await reader.read(BUFF_SIZE)
        handshake = region_net.HandshakeStart()
        handshake.ParseFromString(handshake_raw)
        # TODO: verify the session id with the auth server && cache it
        session_id = handshake.session_id

        # TODO: get this one from the auth server
        user_id = randint(0, 2**31 - 1)

        handshake.Clear()
        handshake.CopyFrom(
            region_net.HandshakeStart(
                kind=region_net.HandshakeStart.SERVER_OK,
                user_id=user_id,
            )
        )

        writer.write(handshake.SerializeToString())
        await writer.drain()

        # For now: assign to the single whole-map node
        node = nodes[(16, 14)]  # NOTE: this is the node the player was constructed at (see Player class construction on client code)
        self = Client(reader, writer, session_id, user_id, node)
        await node.register_client(self, (74000, 32600))

        # TODO: move to register_client
        # when a new player joins:
        # 1. provide the new client everyone's location (ServerResponse so client can render entities)
        # 2. provide everyone the new client's location
        for client in node.clients.values():
            if client == self:
                continue
            resp_to_new = region_net.ServerResponse()
            resp_to_new.sender_id = client.user_id
            resp_to_new.other_data.new_location.CopyFrom(
                region_net.LocationBlock(x=client.state.x, y=client.state.y)
            )
            resp_to_new.other_data.player_id = client.user_id
            await self.write(resp_to_new.SerializeToString())

            resp_to_other = region_net.ServerResponse()
            resp_to_other.sender_id = self.user_id
            resp_to_other.other_data.new_location.CopyFrom(
                region_net.LocationBlock(x=self.state.x, y=self.state.y)
            )
            resp_to_other.other_data.player_id = self.user_id
            await client.write(resp_to_other.SerializeToString())

        try:
            await self.handle_tcp()
        finally:
            self.conn_state.stop_udp_conn.set()
            await node.unregister_client(self)

    @staticmethod
    async def udp_handler(conn: aioudp.Connection) -> None:
        handshake_raw = await conn.recv()
        handshake = region_net.HandshakeStart()
        handshake.ParseFromString(handshake_raw)

        session_id = handshake.session_id
        cli = get_client(session_id)
        if cli is not None:
            handshake.Clear()
            handshake.CopyFrom(
                region_net.HandshakeStart(
                    kind=region_net.HandshakeStart.SERVER_OK,
                )
            )
            await conn.send(handshake.SerializeToString())

            cli.conn_state.udp_conn = conn
            try:
                await cli.handle_udp(conn)
            finally:
                cli.conn_state.udp_conn = None
        else:
            handshake.Clear()
            handshake.CopyFrom(
                region_net.HandshakeStart(
                    kind=region_net.HandshakeStart.SERVER_FAIL_INVALID_SESSION_ID,
                )
            )
            await conn.send(handshake.SerializeToString())

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        session_id: int,
        user_id: int,
        node: "RegionNode",
    ) -> None:
        self.session_id = session_id
        self.user_id = user_id
        self.node = node
        self.state = PlayerState(*node.topleft, *node.to_cell_pos(node.topleft))
        self.conn_state = ConnectionState(
            reader,
            writer,
        )
    
    async def saw_client(self, client_pos: Tuple[int, int], client_user_id: int) -> None:
        """Notify this player about a new client's location"""
        resp = region_net.ServerResponse()
        resp.sender_id = client_user_id
        resp.other_data.new_location.CopyFrom(
            region_net.LocationBlock(x=client_pos[0], y=client_pos[1])
        )
        resp.other_data.player_id = client_user_id
        await self.write_udp(resp)
    
    def can_see(self, pos: Tuple[int, int]) -> bool:
        return abs(self.state.x - pos[0]) < (CLIENT_RECEIVE_WIDTH / 2) and abs(self.state.y - pos[1]) < (CLIENT_RECEIVE_HEIGHT / 2)
    
    @staticmethod
    def can_see_static(player_pos: Tuple[int, int], object_pos: Tuple[int, int]) -> bool:
        return abs(player_pos[0] - object_pos[0]) < (CLIENT_RECEIVE_WIDTH / 2) and abs(player_pos[1] - object_pos[1]) < (CLIENT_RECEIVE_HEIGHT / 2)

    async def hit(self, count: int, hitter_id: int) -> None:
        self.state.hp -= count
        update = region_net.ServerResponse()
        update.sender_id = hitter_id
        update.other_data.CopyFrom(
            region_net.OtherPlayerData(HP=self.state.hp, player_id=self.user_id)
        )
        await self.broadcast(update.SerializeToString())
        await self.write(update.SerializeToString())

    async def handle_region_update(self, data: bytes, source: int) -> None:
        update = region_net.RegionUpdate()
        update.ParseFromString(data)
        print(f"received: {update}")
        if source == Client.FROM_UDP:
            seq = update.seq_num
            if seq and seq < self.conn_state.last_recevied_seq:
                print(
                    f"[INFO]: ignoring packet with {seq=} since max seq={self.conn_state.last_recevied_seq}"
                )
                return
            self.conn_state.last_recevied_seq = seq

        payload_type = update.WhichOneof("payload")
        if payload_type == "location_block":
            await self.node.handle_movement(self, update.location_block)
        elif payload_type == "bullet_shot":
            update_bytes, new_projs = await self.node.projectile_handler.add(
                update.bullet_shot, self
            )
            if update_bytes:
                await self.broadcast(update_bytes)
                for proj in new_projs:
                    for cli in self.node.clients.values():
                        proj["seen_by"].add(cli.user_id)
                await self.node.projectile_handler.broadcast_to_adjacent(new_projs)

    async def handle_tcp(self) -> None:
        while True:
            data = await self.conn_state.reader.read(BUFF_SIZE)
            if not data:
                break
            await self.handle_region_update(data, Client.FROM_TCP)

    async def handle_udp(self, conn: aioudp.Connection) -> None:
        while not self.conn_state.stop_udp_conn.is_set():
            message = await conn.recv()
            if not message:
                self.conn_state.udp_conn = None
                break
            await self.handle_region_update(message, Client.FROM_UDP)

    async def write_udp(self, data: region_net.ServerResponse) -> None:
        data.seq_num = self.conn_state.last_sent_seq
        raw = data.SerializeToString()
        if conn := self.conn_state.udp_conn:
            await conn.send(raw)
            self.conn_state.last_sent_seq += 1
        else:
            await self.write(raw)  # fallback to tcp when udp sock is not available

    async def write(self, data: bytes) -> None:
        async with self.conn_state.writer_lock:
            self.conn_state.writer.write(data)
            await self.conn_state.writer.drain()

    async def broadcast_udp(self, data: region_net.ServerResponse) -> None:
        for client in self.node.clients.values():
            if client == self:
                continue
            if client.user_id == data.sender_id:
                continue
            if not client.can_see((data.other_data.new_location.x, data.other_data.new_location.y)):
                continue
            data.seq_num = client.conn_state.last_sent_seq
            raw = data.SerializeToString()

            try:
                if conn := client.conn_state.udp_conn:
                    await conn.send(raw)
                    client.conn_state.last_sent_seq += 1
                else:
                    await client.write(
                        raw
                    )  # fallback to tcp when udp sock is not available
            except Exception as e:
                print(
                    f"Client {client.user_id} was unable to receive data: {e}, ignoring..."
                )
        print(f"data broadcasted to {len(self.node.clients) - 1} clients on node {self.node.view}")

    async def broadcast(self, data: bytes) -> None:
        for client in self.node.clients.values():
            if client == self:
                continue
            await client.write(data)
        print(f"data broadcasted to {len(self.node.clients) - 1} clients on node {self.node.view}")
