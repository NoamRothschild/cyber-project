from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from random import randint
from typing import TYPE_CHECKING, Tuple
import aioudp
import protobuf.region_net_pb2 as region_net
from constants import BUFF_SIZE, CLIENT_RECEIVE_WIDTH, CLIENT_RECEIVE_HEIGHT

from nodes import nodes, register_global_client, remove_global_client, get_global_client
from servers_communication import get_redis
from region_node import RegionNode
from proxy import create_proxy

NULL_NODE = RegionNode((-1, -1))

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

        r = get_redis()

        # TODO: get this one from the auth server
        uid_key = f"client:{session_id}:user_id"
        if stored_uid := await r.get(uid_key):
            user_id = int(stored_uid)
        else:
            user_id = randint(0, 2**31 - 1)
            await r.set(uid_key, str(user_id).encode())

        initial_pos = (74000, 32600)
        if pos := await r.get(f"client:{session_id}:pos"):
            p = pos.decode().split(",")
            initial_pos = (int(p[0]), int(p[1]))
        else:
            await r.set(f"client:{session_id}:pos", f"{initial_pos[0]},{initial_pos[1]}".encode())
        
        node_pos = RegionNode.which_node(*initial_pos)
        node = nodes.get(node_pos)
        if node is None:
            node = NULL_NODE

        self = Client(reader, writer, session_id, user_id, node)
        await register_global_client(session_id, self)
        if node != NULL_NODE:
            await node.register_client(self, initial_pos)
        
        handshake.Clear()
        handshake.CopyFrom(
            region_net.HandshakeStart(
                kind=region_net.HandshakeStart.SERVER_OK,
                user_id=user_id,
            )
        )

        writer.write(handshake.SerializeToString())
        await writer.drain()

        try:
            await self.handle_tcp()
        finally:
            self.conn_state.stop_udp_conn.set()
            await remove_global_client(self.session_id)
            await node.unregister_client(self)

    @staticmethod
    async def udp_handler(conn: aioudp.Connection) -> None:
        handshake_raw = await conn.recv()
        handshake = region_net.HandshakeStart()
        handshake.ParseFromString(handshake_raw)

        session_id = handshake.session_id
        cli = await get_global_client(session_id)
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
    
    async def update_other_hp(self, other_user_id: int, new_hp: int):
        """Notify this player about a client's hp change"""
        resp = region_net.ServerResponse()
        resp.sender_id = other_user_id
        resp.other_data.HP = new_hp
        resp.other_data.player_id = other_user_id
        await self.write_udp(resp)

    async def entity_despawned(self, entity_user_id: int) -> None:
        """Notify this player that an entity left their viewport"""
        resp = region_net.ServerResponse()
        resp.sender_id = entity_user_id
        resp.other_data.state = region_net.OtherPlayerData.DESPAWNED
        resp.other_data.player_id = entity_user_id
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

        for direction in self.node.possible_bounding_nodes(self.state.x, self.state.y):
            node_pos = (self.node.node_pos[0] + direction.value[0], self.node.node_pos[1] + direction.value[1])

            # proxy this update to the other nodes
            proxy_event = region_net.ProxyEvent(client=region_net.ClientProxy(
                pos=region_net.LocationBlock(x=self.state.x, y=self.state.y),
                player_id=self.user_id,
                session_id=self.session_id,
                HP=self.state.hp,
            ))
            await create_proxy(self.node.node_pos, node_pos, proxy_event)

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
            node_pos = RegionNode.which_node(update.location_block.x, update.location_block.y)
            node = nodes.get(node_pos)
            if node is None:
                # moved to a node on another server
                await self.node.unregister_client(self)
                self.node = NULL_NODE
                return
            
            if self.node != node:
                if self.node != NULL_NODE:
                    await self.node.unregister_client(self)

                self.node = node
                await self.node.register_client(self, (update.location_block.x, update.location_block.y))

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
        try:
            while True:
                data = await self.conn_state.reader.read(BUFF_SIZE)
                if not data:
                    break
                await self.handle_region_update(data, Client.FROM_TCP)
        except (ConnectionResetError, ConnectionAbortedError, OSError):
            pass

    async def handle_udp(self, conn: aioudp.Connection) -> None:
        try:
            while not self.conn_state.stop_udp_conn.is_set():
                message = await conn.recv()
                if not message:
                    self.conn_state.udp_conn = None
                    break
                await self.handle_region_update(message, Client.FROM_UDP)
        except (ConnectionResetError, ConnectionAbortedError, OSError):
            self.conn_state.udp_conn = None

    async def write_udp(self, data: region_net.ServerResponse) -> None:
        if data.HasField("other_data") and (data.other_data.player_id == self.user_id or data.other_data.player_id == 0):
            return

        data.seq_num = self.conn_state.last_sent_seq
        raw = data.SerializeToString()
        if conn := self.conn_state.udp_conn:
            try:
                await conn.send(raw)
                self.conn_state.last_sent_seq += 1
            except Exception as e:
                print(f"Failed to send UDP to client {self.user_id}: {e}")
        else:
            await self.write(raw)

    async def write(self, data: bytes) -> bool:
        """Write data to the TCP stream. Returns False if the connection is dead."""
        try:
            async with self.conn_state.writer_lock:
                self.conn_state.writer.write(data)
                await self.conn_state.writer.drain()
            return True
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError) as e:
            print(f"Failed to write to client {self.user_id}: {e}")
            return False

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
            try:
                await client.write(data)
            except Exception as e:
                print(f"Client {client.user_id} was unable to receive data: {e}, ignoring...")
        print(f"data broadcasted to {len(self.node.clients) - 1} clients on node {self.node.view}")
