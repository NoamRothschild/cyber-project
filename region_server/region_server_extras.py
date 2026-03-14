from __future__ import annotations
import asyncio
from typing import Tuple, Set, Dict, Union
import protobuf.region_net_pb2 as region_net
import redis
import socket
import json
from dataclasses import dataclass, field
from random import randint, choice
import aioudp
import protobuf.region_net_pb2 as region_net
from constants import (
    BUFF_SIZE,
    CLIENT_RECEIVE_WIDTH,
    CLIENT_RECEIVE_HEIGHT,
    PLAYER_WIDTH,
    PLAYER_HEIGHT,
    MAX_DIST_FOR_ITEM_DROP,
)

from nodes import nodes, register_global_client, remove_global_client, get_global_client
from servers_communication import get_redis
from region_node import RegionNode
from grid_utils import AABB

REDIS_PORT = 6379
IP = "127.0.0.1"
redis_client = redis.Redis(host=IP, port=REDIS_PORT, decode_responses=True)

NULL_NODE = RegionNode((-1, -1))
item_count = 0

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

@dataclass
class PlayerState:
    x: int
    y: int
    cell_x: int
    cell_y: int
    hp: int = 400
    money: int = 0
    weapons: list[int] = field(default_factory=lambda: [0] * 10)
    ammo: list[int] = field(default_factory=lambda: [30] * 10)
    potions: list[int] = field(default_factory=lambda: [0] * 10)


@dataclass
class ConnectionState:
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    writer_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    udp_conn: aioudp.Connection | None = None
    stop_udp_conn: asyncio.Event = field(default_factory=asyncio.Event)
    last_recevied_seq: int = 0
    last_sent_seq: int = 0


async def load_player_stats_from_redis(user_id: int) -> dict:
    r = get_redis()
    prefix = f"client:{user_id}:"

    health = await r.get(prefix + "health")
    money = await r.get(prefix + "money")
    spawn_x = await r.get(prefix + "spawn_x")
    spawn_y = await r.get(prefix + "spawn_y")
    weapons_raw = await r.get(prefix + "weapons")
    ammo_raw = await r.get(prefix + "ammo")
    potions_raw = await r.get(prefix + "potions")

    if health is None or money is None or spawn_x is None or spawn_y is None:
        return {
            "health": 400,
            "money": 0,
            "weapons": [0] * 10,
            "ammo": [30] * 10,
            "potions": [0] * 10,
            "spawn_x": 74010,
            "spawn_y": 32605
        }

    def parse_list(raw: bytes) -> list[int]:
        if not raw:
            return []
        return [int(x) for x in raw.decode().split(",")]

    return {
        "health": int(health),
        "money": int(money),
        "weapons": parse_list(weapons_raw),
        "ammo": parse_list(ammo_raw),
        "potions": parse_list(potions_raw),
        "spawn_x": int(spawn_x),
        "spawn_y": int(spawn_y),
    }


class Client:
    FROM_TCP = 0
    FROM_UDP = 1

    @staticmethod
    async def client_handler_setup(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        print("new connection established")

        sock = writer.get_extra_info("socket")
        if sock is not None:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            if hasattr(socket, "TCP_KEEPIDLE"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 15)
            if hasattr(socket, "TCP_KEEPINTVL"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 5)
            if hasattr(socket, "TCP_KEEPCNT"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)

        handshake_raw = await reader.read(BUFF_SIZE)
        handshake = region_net.HandshakeStart()
        handshake.ParseFromString(handshake_raw)
        session_id = handshake.session_id

        r = get_redis()

        uid_key = f"session:{session_id}"
        if not (stored_uid := await r.get(uid_key)):
            print(f"Authentication failed for session: {session_id}")
            response = region_net.HandshakeStart(
                kind=region_net.HandshakeStart.AUTH_FAIL,
                session_id=-1,
            )
            writer.write(response.SerializeToString())
            await writer.drain()
            await writer.wait_closed()
            return

        user_id = int(stored_uid)

        player_stats = await load_player_stats_from_redis(user_id)
        initial_pos = (player_stats["spawn_x"], player_stats["spawn_y"])

        node_pos = RegionNode.which_node(*initial_pos)
        node = nodes.get(node_pos)
        if node is None:
            node = NULL_NODE

        self = Client(reader, writer, session_id, user_id, node, player_stats)
        await register_global_client(session_id, self)
        if node != NULL_NODE:
            await node.register_client(self, initial_pos)

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

        try:
            await self.handle_tcp()
        finally:
            self.conn_state.stop_udp_conn.set()
            await remove_global_client(self.session_id)
            await node.unregister_client(self)

            print(f"User {user_id} disconnected. Saving state to database...")

            payload = json.dumps({
                "user_id": self.user_id,
                "health": self.state.hp,
                "money": self.state.money,
                "weapons": list(self.state.weapons),
                "ammo": list(self.state.ammo),
                "potions": list(self.state.potions),
                "spawn_x": self.state.x,
                "spawn_y": self.state.y,
            })
            await r.publish("auth-update", payload)
            print(f"User {user_id} state published to auth-update.")


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
                    kind=region_net.HandshakeStart.AUTH_FAIL,
                )
            )
            await conn.send(handshake.SerializeToString())


    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, session_id: str,
                 user_id: int, node: "RegionNode", stats:dict) -> None:

        self.session_id = session_id
        self.user_id = user_id
        self.node = node
        self.state = PlayerState(*node.topleft, *node.to_cell_pos(node.topleft))
        self.conn_state = ConnectionState(
            reader,
            writer,
        )
        self.collision = AABB(0, 0, PLAYER_WIDTH, PLAYER_HEIGHT)

        self.state.hp = stats["health"]
        self.state.x = stats["spawn_x"]
        self.state.y = stats["spawn_y"]
        cell = node.to_cell_pos((stats["spawn_x"], stats["spawn_y"]))
        self.state.cell_x = cell[0]
        self.state.cell_y = cell[1]
        self.state.weapons = stats["weapons"]
        self.state.ammo = stats["ammo"]
        self.state.potions = stats["potions"]

    async def hit(self, count, hitter_id: int):
        self.state.hp -= count

        if self.state.hp > 400:
            self.state.hp = 400
        elif self.state.hp < 0:
            self.state.hp = 0

        update = region_net.ServerResponse()
        update.sender_id = hitter_id
        update.other_data.CopyFrom(region_net.OtherPlayerData(HP=self.state.hp, player_id=self.user_id))
        await self.broadcast(update.SerializeToString())
        await self.write(update.SerializeToString())
        await self.node.propagate_entity(self)

    async def saw_enemy(self, enemy_pos: Tuple[int, int], enemy_user_id: int) -> None:
        """Notify this player about a new enemy's location"""
        resp = region_net.ServerResponse()
        resp.sender_id = enemy_user_id
        resp.enemy_data.new_location.CopyFrom(
            region_net.LocationBlock(x=enemy_pos[0], y=enemy_pos[1])
        )
        resp.enemy_data.player_id = enemy_user_id
        await self.write_udp(resp)

    async def saw_enemy_hp(self, enemy_user_id: int, new_hp: int) -> None:
        """Notify this player about a enemy's hp change"""
        resp = region_net.ServerResponse()
        resp.sender_id = enemy_user_id
        resp.enemy_data.HP = new_hp
        resp.enemy_data.player_id = enemy_user_id
        await self.write_udp(resp)

    async def saw_client(
        self, client_pos: Tuple[int, int], client_user_id: int
    ) -> None:
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
        resp.enemy_data.state = region_net.OtherPlayerData.DESPAWNED
        resp.enemy_data.player_id = entity_user_id
        await self.write_udp(resp)

    def can_see(self, pos: Tuple[int, int]) -> bool:
        return abs(self.state.x - pos[0]) < (CLIENT_RECEIVE_WIDTH / 2) and abs(
            self.state.y - pos[1]
        ) < (CLIENT_RECEIVE_HEIGHT / 2)

    @staticmethod
    def can_see_static(
        player_pos: Tuple[int, int], object_pos: Tuple[int, int]
    ) -> bool:
        return abs(player_pos[0] - object_pos[0]) < (CLIENT_RECEIVE_WIDTH / 2) and abs(
            player_pos[1] - object_pos[1]
        ) < (CLIENT_RECEIVE_HEIGHT / 2)

    def to_proxy_event(self) -> region_net.ProxyEvent:
        return region_net.ProxyEvent(
            client=region_net.ClientProxy(
                pos=region_net.LocationBlock(x=self.state.x, y=self.state.y),
                player_id=self.user_id,
                session_id=self.session_id,
                HP=self.state.hp,
            )
        )

    async def item_hendeling(
        self, name: str, kind: str, x: int, y: int, id: int
    ) -> None:
        update = region_net.ServerResponse()
        update.other_data.CopyFrom(
            region_net.OtherPlayerData(
                New_Item=region_net.Item(Kind=kind, Name=name, x=x, y=y, id=id)
            )
        )

        await self.write(update.SerializeToString())

    async def item_removed(
        self, name: str, kind: str, x: int, y: int, id: int
    ) -> None:
        update = region_net.ServerResponse()
        update.other_data.CopyFrom(
            region_net.OtherPlayerData(
                New_Item=region_net.Item(
                    Kind=kind, Name=name, x=x, y=y, id=id, Not_exist=True
                )
            )
        )
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
            node_pos = RegionNode.which_node(
                update.location_block.x, update.location_block.y
            )
            node = nodes.get(node_pos)
            if node is None:
                if self.node != NULL_NODE:
                    await self.node.unregister_client(self)
                    self.node = NULL_NODE
                return

            if self.node != node:
                if self.node != NULL_NODE:
                    await self.node.unregister_client(self)

                self.node = node
                await self.node.register_client(
                    self, (update.location_block.x, update.location_block.y)
                )

            await self.node.handle_movement(self, update.location_block)
        elif payload_type == "potion_use":
            if update.potion_use.potion_type == region_net.PotionUse.PotionType.health:
                await self.hit(-update.potion_use.HowMuch, self.user_id)
        elif payload_type == "item_pickup":
            # TODO: verify the dropped item exists on the client

            x_offset = randint(-120, 120)
            y_offset = MAX_DIST_FOR_ITEM_DROP - abs(x_offset)
            y_offset = choice([-1, 1]) * randint(y_offset, 120)

            await self.node.register_item(
                update.item_pickup.Name,
                update.item_pickup.Kind,
                self.state.x + x_offset,
                self.state.y + y_offset,
                update.item_pickup.id,
            )
            # await self.item_hendeling(update.item_pickup.Name, update.item_pickup.Kind, update.item_pickup.x, update.item_pickup.y)
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
        if data.HasField("other_data") and (
            data.other_data.player_id == self.user_id or data.other_data.player_id == 0
        ):
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
        except (
            ConnectionAbortedError,
            ConnectionResetError,
            BrokenPipeError,
            OSError,
        ) as e:
            print(f"Failed to write to client {self.user_id}: {e}")
            return False

    async def broadcast_udp(self, data: region_net.ServerResponse) -> None:
        for client in self.node.clients.values():
            if client == self:
                continue
            if client.user_id == data.sender_id:
                continue
            if not client.can_see(
                (data.other_data.new_location.x, data.other_data.new_location.y)
            ):
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
        print(
            f"data broadcasted to {len(self.node.clients) - 1} clients on node {self.node.view}"
        )

    async def broadcast(self, data: bytes) -> None:
        for client in self.node.clients.values():
            if client == self:
                continue
            try:
                await client.write(data)
            except Exception as e:
                print(
                    f"Client {client.user_id} was unable to receive data: {e}, ignoring..."
                )
        print(
            f"data broadcasted to {len(self.node.clients) - 1} clients on node {self.node.view}"
        )

# TODO: ask idan wtf should I do with this
#            elif payload_type == "item_drop":
#                idx = update.item_drop.inventory_index
#                kind = update.item_drop.item_kind
#
#                # --- HANDLING DROPS ---
#                if idx == -1:
#                    return
#                if kind == "weapon":
#                    current_idx = 0
#                    weapon_id = SERVER_WEAPON_MAP.get(kind)
#
#                    for i in range(len(self.state.weapons)):
#                        if self.state.weapons[i] != 0:
#                            if current_idx == idx:
#                                self.state.weapons[i] = 0
#                                break
#                            current_idx += 1
#                            continue
#
#                        # Find the first empty slot (0) and fill it
#                        for i in range(len(self.state.weapons)):
#                            if self.state.weapons[i] != 0:
#                                continue
#                            self.state.weapons[i] = weapon_id
#
#                            # --- NEW: Save the ammo to the matching slot! ---
#                            self.state.ammo[i] = update.item_drop.ammo
#
#                            print(
#                                f"Server: Player {self.user_id} picked up {kind} with {self.ammo[i]} ammo into slot {i}")
#                            break
