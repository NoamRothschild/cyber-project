from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Tuple, Set, Dict, Union
import protobuf.region_net_pb2 as region_net
import redis
import socket
import json
from dataclasses import dataclass, field
from random import randint, choice
import aioudp
import auth_crypto
from constants import (
    BUFF_SIZE,
    CLIENT_RECEIVE_WIDTH,
    CLIENT_RECEIVE_HEIGHT,
    PLAYER_WIDTH,
    PLAYER_HEIGHT,
    MAX_DIST_FOR_ITEM_DROP,
    THIS_SERVER_ID,
    SERVER_WEAPON_MAP,
    SERVER_MAX_AMMO,
)

from nodes import nodes, register_global_client, remove_global_client, get_global_client
from servers_communication import get_redis, notify_server
from region_node import RegionNode
from proxy import broadcast_proxy_remove
from grid_utils import AABB

REDIS_PORT = 6379
_REGION_SERVER_DIR = Path(__file__).resolve().parent
HEALING=15
HEALING_TIMES=10
IN_HOW_MUCH_TIME_HEAL=10

def _get_server_private_key():
    server_id = THIS_SERVER_ID
    if not hasattr(_get_server_private_key, "_cache"):
        _get_server_private_key._cache = {}
    if server_id not in _get_server_private_key._cache:
        _get_server_private_key._cache[server_id] = auth_crypto.load_private_key(
            _REGION_SERVER_DIR / f"region_keys_{server_id}.pem"
        )
    return _get_server_private_key._cache[server_id]


import os
from config import REDIS_PASSWORD
_redis_host = os.environ.get("REDIS_HOST", "127.0.0.1")
redis_client = redis.Redis(host=_redis_host, port=REDIS_PORT, password=REDIS_PASSWORD, decode_responses=True)

NULL_NODE = RegionNode((-1, -1))
item_count = 0

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

TEMPLATE_USER_STATE = {
    "ammo_collection": {
        "AK 47 bullets": 100,
        "arrows": 100,
        "sword hit": 100,
        "Assault rifle bullets": 100,
        "Pistol bullets": 100,
    },
    "magazine": {
        "Ak 47": 5,
        "bow": 5,
        "Assault rifle": 5,
        "Pistol": 5,
        "sword": 1000
    },
    "cash": 300
}


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
            "money": 200,
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

        server_private_key = _get_server_private_key()
        try:
            handshake_plain = await auth_crypto.async_receive_and_decrypt(reader, server_private_key)
        except ValueError:
            writer.close()
            await writer.wait_closed()
            return
        handshake = region_net.HandshakeStart()
        handshake.ParseFromString(handshake_plain)
        session_id = handshake.session_id
        if not handshake.client_public_key:
            writer.close()
            await writer.wait_closed()
            return
        client_public_key = auth_crypto.public_key_from_bytes(handshake.client_public_key)

        r = get_redis()

        uid_key = f"session:{session_id}"
        if not (stored_uid := await r.get(uid_key)):
            print(f"Authentication failed for session: {session_id}")
            response = region_net.HandshakeStart(
                kind=region_net.HandshakeStart.AUTH_FAIL,
                session_id=-1,
            )
            encrypted = auth_crypto.encrypt_and_prefix(response.SerializeToString(), client_public_key)
            writer.write(encrypted)
            await writer.drain()
            await writer.wait_closed()
            return

        user_id = int(stored_uid)
        client_created = False

        try:
            player_stats = await load_player_stats_from_redis(user_id)
            initial_pos = (player_stats["spawn_x"], player_stats["spawn_y"])

            node_pos = RegionNode.which_node(*initial_pos)
            node = nodes.get(node_pos)
            if node is None:
                node = NULL_NODE

            self = Client(reader, writer, session_id, user_id, node, player_stats, node != NULL_NODE, client_public_key)
            client_created = True
            await register_global_client(session_id, self)
            if node != NULL_NODE:
                node_key = f"client:{self.user_id}:node"
                await r.set(node_key, str(node.index))
                await node.register_client(self, initial_pos)
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
            response.ammo.extend(player_stats["ammo"])

            encrypted = auth_crypto.encrypt_and_prefix(response.SerializeToString(), client_public_key)
            writer.write(encrypted)
            await writer.drain()

            await self.handle_tcp()
        except Exception as e:
            print(f"Client disconnect/error (session {session_id}, user_id {user_id}): {e}")
        finally:
            # Always disconnect and close all client resources; never let one client bring down the server.
            if client_created:
                self.conn_state.stop_udp_conn.set()
                try:
                    self.conn_state.writer.close()
                    await self.conn_state.writer.wait_closed()
                except Exception:
                    pass
                try:
                    await remove_global_client(self.session_id)
                except Exception as e:
                    print(f"Error removing global client {user_id}: {e}")
                try:
                    await node.unregister_client(self)
                except Exception as e:
                    print(f"Error unregistering client {user_id} from node: {e}")
                try:
                    if not self.on_this_server:
                        return
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
                    print(f"User {user_id} disconnected; state published to auth-update.")
                except Exception as pub_err:
                    print(f"User {user_id} disconnected; failed to publish state: {pub_err}")
            else:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass


    @staticmethod
    async def udp_handler(conn: aioudp.Connection) -> None:
        server_private_key = _get_server_private_key()
        try:
            handshake_raw = await conn.recv()
            handshake_plain = auth_crypto.decrypt_length_prefixed(handshake_raw, server_private_key)
        except ValueError:
            return
        handshake = region_net.HandshakeStart()
        handshake.ParseFromString(handshake_plain)
        session_id = handshake.session_id
        cli = await get_global_client(session_id)
        if cli is not None:
            resp = region_net.HandshakeStart(kind=region_net.HandshakeStart.SERVER_OK)
            encrypted = auth_crypto.encrypt_and_prefix(resp.SerializeToString(), cli.client_public_key)
            await conn.send(encrypted)
            cli.conn_state.udp_conn = conn
            try:
                await cli.handle_udp(conn)
            finally:
                cli.conn_state.udp_conn = None
        else:
            if handshake.client_public_key:
                client_pub = auth_crypto.public_key_from_bytes(handshake.client_public_key)
                resp = region_net.HandshakeStart(kind=region_net.HandshakeStart.AUTH_FAIL)
                encrypted = auth_crypto.encrypt_and_prefix(resp.SerializeToString(), client_pub)
                await conn.send(encrypted)


    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, session_id: int,
                 user_id: int, node: "RegionNode", stats: dict, on_this_server: bool, client_public_key) -> None:
        self.session_id = session_id
        self.user_id = user_id
        self.node = node
        self.client_public_key = client_public_key
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
        self.user_state = TEMPLATE_USER_STATE.copy() # TODO: copy from redis
        self.old_view = [] # List[GridField]
        self.on_this_server = on_this_server
        self.hp_potion_activ=False
        self.health_count=0

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

        if self.state.hp <= 0:
            await self._handle_death()
            return

        await self.node.propagate_entity(self)

    WORLD_SPAWN = (74000, 32600)
    SPAWN_NODE_POS = RegionNode.which_node(*WORLD_SPAWN)

    async def _handle_death(self) -> None:
        """Broadcast DESPAWN to viewers, force TP to spawn, reset HP, move to spawn node."""
        from nodes import nodes

        dead_pos = (self.state.x, self.state.y)
        node = self.node

        for cli in node.clients.values():
            if cli is self:
                continue
            if Client.can_see_static((cli.state.x, cli.state.y), dead_pos):
                await cli.client_despawned(self.user_id)

        await broadcast_proxy_remove(self.user_id, "Client", self.session_id)

        self.state.hp = 400
        spawn_node = nodes.get(Client.SPAWN_NODE_POS)

        if spawn_node is None:
            # Spawn is on another server: detach here so we don't leave a ghost client.
            node.detach_client(self)
            self.node = NULL_NODE
            return
        if spawn_node != node:
            node.detach_client(self)
            self.node = spawn_node
            await spawn_node.register_client(self, self.WORLD_SPAWN)
        else:
            self.state.x, self.state.y = self.WORLD_SPAWN[0], self.WORLD_SPAWN[1]
            cell_x, cell_y = node.to_cell_pos(self.WORLD_SPAWN)
            old_cx, old_cy = self.state.cell_x, self.state.cell_y
            self.state.cell_x, self.state.cell_y = cell_x, cell_y
            node.grid_move(self, old_cx, old_cy, cell_x, cell_y)
            await node.propagate_entity(self)

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
    async def tick(self, cycle: int) -> None:
        if self.hp_potion_activ==True:
            if cycle % IN_HOW_MUCH_TIME_HEAL == 0:
                self.health_count+=1
                await self.hit(-HEALING, self.user_id)
                if self.health_count>=HEALING_TIMES:
                    self.hp_potion_activ=False
                    self.health_count=0

    async def entity_despawned(self, entity_user_id: int) -> None:
        """Notify this player that an entity (enemy) left their viewport."""
        resp = region_net.ServerResponse()
        resp.sender_id = entity_user_id
        resp.enemy_data.state = region_net.OtherPlayerData.DESPAWNED
        resp.enemy_data.player_id = entity_user_id
        await self.write_udp(resp)

    async def entity_died(self, entity_user_id: int) -> None:
        """Notify this player that an entity (enemy) was killed; client plays death animation then removes."""
        resp = region_net.ServerResponse()
        resp.sender_id = entity_user_id
        resp.enemy_data.state = region_net.OtherPlayerData.DIED
        resp.enemy_data.player_id = entity_user_id
        await self.write_udp(resp)

    async def client_despawned(self, other_user_id: int) -> None:
        """Notify this player that another client (player) left their viewport."""
        resp = region_net.ServerResponse()
        resp.sender_id = other_user_id
        resp.other_data.state = region_net.OtherPlayerData.DESPAWNED
        resp.other_data.player_id = other_user_id
        await self.write_udp(resp)

    async def send_fps(self, fps: int) -> None:
        resp = region_net.ServerResponse()
        resp.fps = int(fps)
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
    
    @staticmethod
    def priceOfTheSHOPING(kind: str, name: str) -> int:
        prices = {
            "weapon": {
                "Ak 47": 300,
                "Assault rifle": 350,
                "Pistol": 200,
                "bow": 80,
                "sword": 60
            },
            "ammo": {
                "Pistol bullets": 40,
                "AK 47 bullets": 50,
                "Assault rifle bullets": 60,
                "arrows": 60
            },
            "potion": {
                "healing": 140,
                "speed": 70,
                "super_speed": 140
            }
        }
        return prices.get(kind, {}).get(name, 0)

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
                self.on_this_server = False
                return

            if self.node != node:
                if self.node != NULL_NODE:
                    await self.node.unregister_client(self)
                self.on_this_server = True

                self.node = node
                await self.node.register_client(
                    self, (update.location_block.x, update.location_block.y)
                )
                r = get_redis()
                node_key = f"client:{self.user_id}:node"
                await r.set(node_key, str(self.node.index))

            await self.node.handle_movement(self, update.location_block)
        elif payload_type == "moved_server":
            new_server_id = update.moved_server.new_server_id
            self.on_this_server = THIS_SERVER_ID == new_server_id
            if self.on_this_server:
                return

            try:
                r = get_redis()
                prefix = f"client:{self.user_id}:"
                await r.set(prefix + "health", self.state.hp)
                await r.set(prefix + "money", self.state.money)
                # await r.set(prefix + "spawn_x", self.state.x)
                # await r.set(prefix + "spawn_y", self.state.y)
                await r.set(prefix + "weapons", ",".join(str(w) for w in self.state.weapons))
                await r.set(prefix + "ammo", ",".join(str(a) for a in self.state.ammo))
                await r.set(prefix + "potions", ",".join(str(p) for p in self.state.potions))
                print(f"[redis-sync] Saved live stats for user {self.user_id} before server move to {new_server_id}")
            except Exception as e:
                print(f"[redis-sync] Failed to save stats for user {self.user_id} before server move: {e}")

            await notify_server(new_server_id, f'cli:{self.session_id}'.encode())
        elif payload_type == "potion_use":
            if update.potion_use.potion_type == region_net.PotionUse.PotionType.health:
                self.hp_potion_activ=True
        elif payload_type == "item_pickup":
            # Client requests to DROP an item from their inventory into the world.
            # (delete_w / delete_p / delete_mony call ZoneConnection.try_send_item -> item_pickup)
            # We reflect this in PlayerState (weapons/potions/money) and then spawn the dropped item.
            kind = update.item_pickup.Kind
            name = update.item_pickup.Name

            dropped = False

            if kind == "money":
                # Client already subtracted 50 locally; mirror on server, clamped at 0.
                if self.state.money >= 50:
                    self.state.money -= 50
                    dropped = True
                    print(f"[MONEY] player {self.user_id} dropped 50; now has {self.state.money}")
            elif kind == "potion":
                # Mirror client.inventory.POTION_MAP: 1: healing, 2: speed, 3: super_speed
                potion_id_map = {
                    "healing": 1,
                    "speed": 2,
                    "super_speed": 3,
                    "gold": 4,
                }
                potion_id = potion_id_map.get(name)
                if potion_id is None:
                    print(f"[WARN] item_drop: unknown potion '{name}' from player {self.user_id}")
                else:
                    for i, slot in enumerate(self.state.potions):
                        if slot == potion_id:
                            self.state.potions[i] = 0
                            dropped = True
                            break
            elif kind == "weapon":
                weapon_id = SERVER_WEAPON_MAP.get(name)
                if weapon_id is None:
                    print(f"[WARN] item_drop: unknown weapon '{name}' from player {self.user_id}")
                else:
                    for i, slot in enumerate(self.state.weapons):
                        if slot == weapon_id:
                            self.state.weapons[i] = 0
                            # Clear ammo for that slot as well
                            if 0 <= i < len(self.state.ammo):
                                self.state.ammo[i] = 0
                            dropped = True
                            break

            if not dropped:
                # Inventory/server state didn't change; don't spawn a ghost drop.
                return

            # Spawn the dropped item near the player, same as before.
            x_offset = randint(-120, 120)
            y_offset = MAX_DIST_FOR_ITEM_DROP - abs(x_offset)
            y_offset = choice([-1, 1]) * randint(y_offset, 120)

            await self.node.register_item(
                name,
                kind,
                self.state.x + x_offset,
                self.state.y + y_offset,
                update.item_pickup.id,
            )
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
        elif payload_type == "shop_buy": #SHOP anticheat
            resp = region_net.ServerResponse()
            resp.sender_id = self.user_id

            kind, name = update.shop_buy.item_type, update.shop_buy.item_name
            amount = update.shop_buy.amount
            price = Client.priceOfTheSHOPING(kind, name)

            total = price * amount

            if self.user_state["cash"] >= total:
                self.user_state["cash"] -= total
                resp.other_data.shop_ans = True
                print(f"[SHOP] player {self.user_id} bought {amount}x {kind}:{name} for {total}. Cash now: {self.user_state['cash']}")
            else:
                resp.other_data.shop_ans = False
                print(f"[SHOP] player {self.user_id} cannot afford {amount}x {kind}:{name} (total {total}). Cash: {self.user_state['cash']}")
            await self.write(resp.SerializeToString())
        elif payload_type == "reload_act":
            try:
                gun_type = update.reload_act.gun_type
                full_mag = update.reload_act.full_mag

                ammo_type = {
                    "Ak 47": "Ak 47",
                    "bow": "arrows",
                    "Assault rifle": "Assault rifle bullets",
                    "Pistol": "Pistol bullets",
                    "sword": "sword hit"
                }

                ammo_name = ammo_type.get(gun_type)
                if ammo_name is None:
                    return

                current_mag = self.user_state["magazine"].get(gun_type, 0)
                ammo_have = self.user_state["ammo_collection"].get(ammo_name, 0)
                need = full_mag - current_mag

                if need <= 0:
                    return
                
                reload_amount = min(need, ammo_have)
                self.user_state["magazine"][gun_type] += reload_amount
                self.user_state["ammo_collection"][ammo_name] -= reload_amount

                print("was needed: ",reload_amount)
                print("ammo_collection left: ", self.user_state["ammo_collection"][ammo_name])

            except Exception as e:
                print("reload error:", e)

    async def handle_tcp(self) -> None:
        server_private_key = _get_server_private_key()
        try:
            while True:
                try:
                    data = await auth_crypto.async_receive_and_decrypt(
                        self.conn_state.reader, server_private_key
                    )
                except ValueError:
                    break
                await self.handle_region_update(data, Client.FROM_TCP)
        except (ConnectionResetError, ConnectionAbortedError, OSError):
            pass

    async def handle_udp(self, conn: aioudp.Connection) -> None:
        server_private_key = _get_server_private_key()
        try:
            while not self.conn_state.stop_udp_conn.is_set():
                message = await conn.recv()
                if not message:
                    self.conn_state.udp_conn = None
                    break
                try:
                    data = auth_crypto.decrypt_length_prefixed(message, server_private_key)
                except ValueError:
                    continue
                await self.handle_region_update(data, Client.FROM_UDP)
        except (ConnectionResetError, ConnectionAbortedError, OSError):
            self.conn_state.udp_conn = None

    async def write_udp(self, data: region_net.ServerResponse) -> None:
        if data.HasField("other_data") and (
            data.other_data.player_id == self.user_id or data.other_data.player_id == 0
        ):
            return

        data.seq_num = self.conn_state.last_sent_seq
        raw = data.SerializeToString()
        encrypted = auth_crypto.encrypt_and_prefix(raw, self.client_public_key)
        if conn := self.conn_state.udp_conn:
            try:
                await conn.send(encrypted)
                self.conn_state.last_sent_seq += 1
            except Exception as e:
                print(f"Failed to send UDP to client {self.user_id}: {e}")
        else:
            await self.write(encrypted, encrypt=False)

    async def write(self, data: bytes, encrypt: bool = True) -> bool:
        """Write data to the TCP stream. Returns False if the connection is dead."""
        if encrypt:
            data = auth_crypto.encrypt_and_prefix(data, self.client_public_key)
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
            encrypted = auth_crypto.encrypt_and_prefix(raw, client.client_public_key)
            try:
                if conn := client.conn_state.udp_conn:
                    await conn.send(encrypted)
                    client.conn_state.last_sent_seq += 1
                else:
                    await client.write(encrypted)
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
