from __future__ import annotations
from queue import Empty, Queue
import select
import socket
import threading
from typing import Tuple, List, Dict, TYPE_CHECKING
import protobuf.region_net_pb2 as region_net
from potion import Potion
from arsenal import Arsenal

if TYPE_CHECKING:
    # Imported only for type checking to avoid circular imports at runtime
    from game import Game
BUFF_SIZE = 1024

_TCP = 0
_UDP = 1


class ZoneConnection:
    def __init__(
        self, game: Game, host: str, reliable_port: int, fast_port: int
    ) -> None:
        # the position the server thinks we are at
        self.server_known_pos: Tuple[int, int] = (0, 0)

        # reliable -> TCP, fast -> UDP
        self.reliable_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.fast_conn = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self.host = host
        self.reliable_port = reliable_port
        self.fast_port = fast_port

        self.message_queue: Queue[region_net.ServerResponse] = Queue()
        self.last_recevied_seq = 0
        self.last_sent_seq = 0
        self._stop_event = threading.Event()
        self._listener_thread: threading.Thread | None = None
        self._event_handler_thread: threading.Thread | None = None

        self.game = game

    def open_connections(self, session_id: int) -> int:
        """opens the TCP and UDP conn's and returns the user id. can throw"""
        self.reliable_conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        if hasattr(socket, "TCP_KEEPIDLE"):
            self.reliable_conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 15)
        if hasattr(socket, "TCP_KEEPINTVL"):
            self.reliable_conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 5)
        if hasattr(socket, "TCP_KEEPCNT"):
            self.reliable_conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
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
        self.open_fast_conn(session_id)

        player = self.game.level.player

        player.hitbox.x = login_resp.pos_x
        player.hitbox.y = login_resp.pos_y

        player.rect.center = player.hitbox.center

        self.server_known_pos = (login_resp.pos_x, login_resp.pos_y)

        player.health.set_life(login_resp.health)

        # Clear the new lists and create Arsenal objects
        player.inventory.wep_inventory.clear()
        player.inventory.potion_inventory.clear()

        from arsenal import Arsenal

        from inventory import WEAPON_MAP, POTION_MAP

        # Sync ammo slots from Handshake into Arsenal objects
        for i, weapon_id in enumerate(login_resp.weapons):
            if weapon_id != 0:
                if weapon_id in WEAPON_MAP:
                    weapon_name = WEAPON_MAP[weapon_id]

                    # Grab the matching ammo from the login response
                    saved_ammo = login_resp.ammo[i]

                    # Pass the ammo to the Arsenal object
                    weapon_obj = Arsenal(weapon_name, saved_ammo=saved_ammo)
                    player.inventory.add_item_toThe_Inventory(weapon_obj, "weapon")
                else:
                    print(f"[WARNING] Server sent unknown weapon ID: {weapon_id}")

        for potion_id in login_resp.potions:
            if potion_id != 0:
                if potion_id in POTION_MAP:
                    potion_name = POTION_MAP[potion_id]
                    potion_obj = Potion(potion_name)
                    player.inventory.add_item_toThe_Inventory(potion_obj, "potion")
                else:
                    print(f"[WARNING] Server sent unknown potion ID: {potion_id}")

        print(
            f"Sync Complete: Player loaded at X:{player.hitbox.x} Y:{player.hitbox.y}"
        )

        self._listener_thread = threading.Thread(
            target=server_listener, args=(self,), daemon=True
        )
        self._listener_thread.start()
        return login_resp.user_id

    def open_fast_conn(self, session_id: int) -> None:
        handshake = region_net.HandshakeStart()
        handshake.session_id = session_id
        handshake.kind = handshake.LOGIN
        handshake_bytes = handshake.SerializeToString()

        udp_timeout_sec = 3.0
        max_retries = 5
        old_timeout = self.fast_conn.gettimeout()
        self.fast_conn.settimeout(udp_timeout_sec)
        try:
            for attempt in range(max_retries):
                self.fast_conn.sendto(handshake_bytes, (self.host, self.fast_port))
                try:
                    login_resp_raw = self.fast_conn.recv(BUFF_SIZE)
                except socket.timeout:
                    if attempt == max_retries - 1:
                        raise RuntimeError(
                            "failed connecting to udp zone: no response after retries (packet loss?)"
                        )
                    continue
                if not login_resp_raw:
                    continue
                login_resp = region_net.HandshakeStart()
                login_resp.ParseFromString(login_resp_raw)
                if login_resp.kind != login_resp.SERVER_OK:
                    raise RuntimeError(
                        "failed connecting to udp zone: invalid session id"
                    )
                return
        finally:
            self.fast_conn.settimeout(old_timeout)

    def start_event_handler(self):
        self._event_handler_thread = threading.Thread(
            target=event_handler,
            args=(self.game, self.message_queue, self._stop_event),
            daemon=True,
        )
        self._event_handler_thread.start()

    def stop(self) -> None:
        """Signal listener and event_handler threads to exit, then join them."""
        self._stop_event.set()
        self.message_queue.put(None)
        if self._listener_thread is not None:
            self._listener_thread.join(timeout=2.0)
        if self._event_handler_thread is not None:
            self._event_handler_thread.join(timeout=2.0)

    def send_udp(self, update: region_net.RegionUpdate) -> None:
        update.seq_num = self.last_sent_seq
        ZoneConnectionSingleton.enqueue_send(_UDP, update.SerializeToString())
        self.last_sent_seq += 1

    def send_tcp(self, data: bytes) -> None:
        ZoneConnectionSingleton.enqueue_send(_TCP, data)

    def try_send_update_pos(self, pos: Tuple[int, int]) -> None:
        if not should_update_location(self.server_known_pos, pos):
            return

        update = region_net.RegionUpdate()
        update.location_block.CopyFrom(region_net.LocationBlock(x=pos[0], y=pos[1]))
        self.server_known_pos = pos
        self.send_udp(update)

    def try_send_bullet(self, gun_type: str, angle: float, count: int) -> None:
        """NOTE: currently uses TCP. TODO: move to udp"""
        update = region_net.RegionUpdate()
        update.bullet_shot.CopyFrom(
            region_net.BulletShot(gun_type=gun_type, angle=angle, count=count)
        )
        self.send_tcp(update.SerializeToString())

        self.reliable_conn.sendall(update.SerializeToString())

    def try_send_potion_use(self, potion_kind: str, how_much: int) -> None:
        print("Sending HP event to server...")
        update = region_net.RegionUpdate()
        update.potion_use.CopyFrom(
            region_net.PotionUse(potion_type=potion_kind, HowMuch=how_much)
        )
        self.send_tcp(update.SerializeToString())

    def try_send_item(self, item_kind: str, item_name: str, id) -> None:
        update = region_net.RegionUpdate()
        update.item_pickup.CopyFrom(
            region_net.Item(Kind=item_kind, Name=item_name, id=id)
        )
        self.send_tcp(update.SerializeToString())

    def try_send_item_drop(self, inventory_index: int, item_kind: str) -> None:
        print(f"Sending drop request for {item_kind} at slot {inventory_index}")
        update = region_net.RegionUpdate()
        update.item_drop.CopyFrom(
            region_net.ItemDrop(inventory_index=inventory_index, item_kind=item_kind)
        )
        self.reliable_conn.sendall(update.SerializeToString())

    def try_send_item_pickup(
        self, item_name: str, item_kind: str, ammo: int = 0
    ) -> None:
        """Tells the server we picked up an item and how much ammo it has."""
        update = region_net.RegionUpdate()

        update.item_drop.CopyFrom(
            region_net.ItemDrop(inventory_index=-1, item_kind=item_name, ammo=ammo)
        )
        self.reliable_conn.sendall(update.SerializeToString())


class ZoneConnectionSingleton:
    _instance: None | ZoneConnectionSingleton = None
    _lock = threading.Lock()
    _config_game: Game | None = None
    _config_hosts: List[str] | None = None
    _config_reliable_port: int | None = None
    _config_fast_port: int | None = None
    zone: ZoneConnection | None = None
    zone_connections: Dict[str, ZoneConnection] | None = None

    _send_queue: Queue[Tuple[int, bytes] | None] = Queue()
    _send_stop = threading.Event()
    _sender_thread: threading.Thread | None = None

    @staticmethod
    def set_creds(game: Game, hosts: List[str], reliable_port: int, fast_port: int):
        ZoneConnectionSingleton._config_game = game
        ZoneConnectionSingleton._config_hosts = hosts
        ZoneConnectionSingleton._config_reliable_port = reliable_port
        ZoneConnectionSingleton._config_fast_port = fast_port

    @staticmethod
    def enqueue_send(protocol: int, data: bytes):
        ZoneConnectionSingleton._send_queue.put((protocol, data))

    @staticmethod
    def start_sender():
        if ZoneConnectionSingleton._sender_thread is not None:
            return
        ZoneConnectionSingleton._send_stop.clear()
        ZoneConnectionSingleton._sender_thread = threading.Thread(
            target=_sender_worker,
            args=(
                ZoneConnectionSingleton._send_queue,
                ZoneConnectionSingleton._send_stop,
            ),
            daemon=True,
        )
        ZoneConnectionSingleton._sender_thread.start()

    @staticmethod
    def stop_sender():
        ZoneConnectionSingleton._send_stop.set()
        ZoneConnectionSingleton._send_queue.put(None)
        if ZoneConnectionSingleton._sender_thread is not None:
            ZoneConnectionSingleton._sender_thread.join(timeout=2.0)
            ZoneConnectionSingleton._sender_thread = None

    @staticmethod
    def move_zone(new_host: str):
        if new_host not in ZoneConnectionSingleton._config_hosts:
            raise RuntimeError(f"Invalid host: {new_host}")
        ZoneConnectionSingleton._instance.zone = (
            ZoneConnectionSingleton._instance.zone_connections[new_host]
        )

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                if (
                    cls._config_game is None
                    or cls._config_hosts is None
                    or cls._config_reliable_port is None
                    or cls._config_fast_port is None
                ):
                    raise RuntimeError(
                        "A field value was missing while trying to construct ZoneConnection"
                    )

                cls._instance = super(ZoneConnectionSingleton, cls).__new__(cls)
                zone_connections = {}
                for host in cls._config_hosts:
                    zone_connections[host] = ZoneConnection(
                        cls._config_game,
                        host,
                        cls._config_reliable_port,
                        cls._config_fast_port,
                    )

                cls._instance.zone_connections = zone_connections
                cls._instance.zone = zone_connections[cls._config_hosts[0]]
        return cls._instance


def _sender_worker(send_queue: Queue, stop_event: threading.Event):
    """Single background thread that drains the shared send queue for all zones."""
    while not stop_event.is_set():
        try:
            item = send_queue.get(timeout=0.5)
        except Empty:
            continue
        if item is None:
            break
        protocol, data = item
        zone = ZoneConnectionSingleton().zone
        try:
            if protocol == _UDP:
                zone.fast_conn.sendto(data, (zone.host, zone.fast_port))
            else:
                zone.reliable_conn.sendall(data)
        except Exception as e:
            if protocol == _UDP:
                try:
                    zone.reliable_conn.sendall(data)
                except Exception:
                    print(f"[WARN]: failed sending (both UDP and TCP fallback): {e}")
            else:
                print(f"[WARN]: failed sending TCP: {e}")


def should_update_location(
    old_pos: Tuple[int, int], new_pos: Tuple[int, int], min_dst=5
) -> bool:
    """returns true when the distance between the two pos are above min_dst"""
    if old_pos == new_pos:
        return False
    traveled_dst_squared = (old_pos[0] - new_pos[0]) ** 2 + (
        old_pos[1] - new_pos[1]
    ) ** 2
    min_dst_squared = min_dst**2

    return traveled_dst_squared > min_dst_squared


def server_listener(zone: ZoneConnection):
    """
    Start this one in another thread
    Continiously polls server updates and pushes them into the queue
    """
    sock_list = [zone.reliable_conn, zone.fast_conn]
    tcp_recv = lambda: zone.reliable_conn.recv(BUFF_SIZE)
    udp_recv = lambda: zone.fast_conn.recvfrom(BUFF_SIZE)[0]
    select_timeout = 0.5

    while not zone._stop_event.is_set():
        readable, _, _ = select.select(sock_list, [], [], select_timeout)
        if not readable:
            continue
        for s in readable:
            receiver = tcp_recv
            is_udp = False
            if s == zone.fast_conn:
                receiver = udp_recv
                is_udp = True

            server_raw = receiver()
            if not server_raw:
                continue

            parsed = region_net.ServerResponse()
            parsed.ParseFromString(server_raw)

            if is_udp and parsed.seq_num and parsed.seq_num < zone.last_recevied_seq:
                print(
                    f"[INFO]: ignoring packet with {parsed.seq_num=} since max seq={zone.last_recevied_seq}"
                )
                continue
            if is_udp:
                zone.last_recevied_seq = max(zone.last_recevied_seq, parsed.seq_num)

            zone.message_queue.put(parsed)


def event_handler(
    game: Game,
    zone_queue: Queue[region_net.ServerResponse],
    stop_event: threading.Event,
):
    """
    Start this one in another thread
    Continiously polls queue events and updates acordingly
    """
    from bullets import Bullets

    not_enemy_packet = lambda p: not (p.HasField("enemy_data") and p.enemy_data.HasField("new_location"))

    while not stop_event.is_set():
        try:
            update = zone_queue.get(timeout=0.5)
        except Empty:
            continue
        if update is None:
            break
        nep = not_enemy_packet(update)
        if nep: print(f"received: {update}")

        payload_type = update.WhichOneof("payload")
        if nep: print(f"{payload_type=}")
        if payload_type == "move_self":
            print("force moving self...")
            # TODO: have a lock sorrounding player hitbox
            hb = game.level.player.hitbox
            hb.x = update.move_self.x
            hb.y = update.move_self.y
        elif payload_type == "other_data" or payload_type == "enemy_data":
            sender_id = update.sender_id
            if payload_type == "other_data":
                update = update.other_data
                is_enemy = False
            else:
                update = update.enemy_data
                is_enemy = True

            payload_type = update.WhichOneof("payload")
            if nep: print(f"{payload_type=}, {update.player_id=}")
            if payload_type == "new_location":
                pos = update.new_location
                game.level.entities.add_or_update(
                    [game.level.visible_sprites],
                    sender_id,
                    pos=(pos.x, pos.y),
                    type="ENEMY" if is_enemy else "PLAYER",
                )
            elif payload_type == "New_Item":
                item = update.New_Item
                print(f"{item.id}")

                if item.Picked_up:
                    sprite = find(item, game)
                    if sprite:
                        if (
                            sprite.kind == "money"
                            and game.level.player.inventory.money < 1950
                        ):
                            game.level.player.inventory.money += 50
                            sprite.kill()
                        else:
                            game.level.player.inventory.add_item_toThe_Inventory(
                                sprite.obj, sprite.kind
                            )
                        sprite.kill()
                elif item.Not_exist:
                    remve(item, game)
                else:
                    game.level.add_c(
                        (item.x, item.y), str(item.Name), str(item.Kind), item.id
                    )
            elif payload_type == "HP":
                health_elem = game.level.player.health
                new_hp = update.HP
                print(f"{update.player_id=}")
                if update.player_id != game.user_id:
                    game.level.entities.add_or_update(
                        [game.level.visible_sprites],
                        update.player_id,
                        hp=new_hp,
                        type="ENEMY" if is_enemy else "PLAYER",
                    )
                else:
                    old_hp = health_elem.get_life()
                    diff = new_hp - old_hp
                    print(f"player hp changed")
                    if diff > 0:
                        health_elem.add_life(diff)
                    elif diff < 0:
                        health_elem.sub_life(abs(diff))
            elif payload_type == "state":
                if update.state == region_net.OtherPlayerData.DESPAWNED:
                    game.level.entities.remove(update.player_id)
        elif len(update.bullet_shot) > 0:
            inc_bullets = update.bullet_shot
            for bullet in inc_bullets:
                Bullets.BulletLS.append(
                    Bullets(
                        bullet.gun_type,
                        bullet.x,
                        bullet.y,
                        angle=bullet.angle,
                        from_network=True,
                    )
                )


def find(item, game):
    for sprite in game.level.colectible_sprite:
        print(sprite.id, item.id)
        if int(sprite.id) == int(item.id):
            print(sprite)
            return sprite


def remve(item, game):
    for sprite in game.level.colectible_sprite:
        print(sprite.id, item.id)
        if int(sprite.id) == int(item.id):
            print(sprite)
            sprite.kill()
