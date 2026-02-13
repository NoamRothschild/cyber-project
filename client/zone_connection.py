from __future__ import annotations
from queue import Queue
import select
import socket
import threading
from typing import Tuple, TYPE_CHECKING
import protobuf.region_net_pb2 as region_net

if TYPE_CHECKING:
    # Imported only for type checking to avoid circular imports at runtime
    from game import Game
BUFF_SIZE = 1024

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

        self.message_queue: Queue[region_net.ServerResponse] = Queue()
        self.last_recevied_seq = 0
        self.last_sent_seq = 0

        self.game = game

    def open_connections(self, session_id: int) -> int:
        """opens the TCP and UDP conn's and returns the user id. can throw"""
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

        listener = threading.Thread(target=server_listener, args=(self,))
        listener.start()
        return login_resp.user_id

    def open_fast_conn(self, session_id: int) -> None:
        # TODO: IMPORTANT! retry after set timeout if no resp in case packet got lost
        handshake = region_net.HandshakeStart()
        handshake.session_id = session_id
        handshake.kind = handshake.LOGIN

        self.fast_conn.sendto(handshake.SerializeToString(), (self.host, self.fast_port))
        login_resp_raw = self.fast_conn.recv(BUFF_SIZE)
        login_resp = region_net.HandshakeStart()
        login_resp.ParseFromString(login_resp_raw)
        if login_resp.kind != login_resp.SERVER_OK:
            raise RuntimeError("failed connecting to udp zone: invalid session id")

    def start_event_handler(self):
        listener = threading.Thread(target=event_handler, args=(self.game, self.message_queue,))
        listener.start()

    def send_udp(self, update: region_net.RegionUpdate) -> None:
        update.seq_num = self.last_sent_seq
        try:
            self.fast_conn.sendto(update.SerializeToString(), (self.host, self.fast_port))
        except Exception as e:
            print(f"[WARN]: failed sending UDP update: {e}, falling back to TCP")
            self.reliable_conn.sendall(update.SerializeToString())
        self.last_sent_seq += 1

    def try_send_update_pos(self, pos: Tuple[int, int]) -> None:
        if not should_update_location(self.server_known_pos, pos):
            return

        update = region_net.RegionUpdate()
        update.location_block.CopyFrom(
            region_net.LocationBlock(
                x=pos[0], y=pos[1]
            )
        )
        self.server_known_pos = pos
        self.send_udp(update)

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


def server_listener(zone: ZoneConnection):
    """
    Start this one in another thread
    Continiously polls server updates and pushes them into the queue
    """
    sock_list = [zone.reliable_conn, zone.fast_conn]
    tcp_recv = lambda: zone.reliable_conn.recv(BUFF_SIZE)
    udp_recv = lambda: zone.fast_conn.recvfrom(BUFF_SIZE)[0]

    while True:
        readable, _, _ = select.select(sock_list, [], [])
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
                print(f"[INFO]: ignoring packet with {parsed.seq_num=} since max seq={zone.last_recevied_seq}")
                continue
            if is_udp:
                zone.last_recevied_seq = max(zone.last_recevied_seq, parsed.seq_num)

            zone.message_queue.put(parsed)

def event_handler(game: Game, zone_queue: Queue[region_net.ServerResponse]):
    """
    Start this one in another thread
    Continiously polls queue events and updates acordingly
    """
    from bullets import Bullets

    while True:
        update = zone_queue.get()
        if not update:
            break
        print(f"received: {update}")

        payload_type = update.WhichOneof("payload")
        print(f'{payload_type=}')
        if payload_type == "move_self":
            print("force moving self...")
            # TODO: have a lock sorrounding player hitbox
            hb = game.level.player.hitbox
            hb.x = update.move_self.x
            hb.y = update.move_self.y
        elif payload_type == "other_data":
            payload_type = update.other_data.WhichOneof("payload")
            print(f"{payload_type=}")
            if payload_type == "new_location":
                pos = update.other_data.new_location
                game.level.entities.add_or_update([game.level.visible_sprites], update.sender_id, pos=(pos.x, pos.y))
            elif payload_type == "HP":
                health_elem = game.level.player.health
                new_hp = update.other_data.HP
                print(f"{update.other_data.player_id=}")
                if update.other_data.player_id != game.user_id:
                    game.level.entities.add_or_update([game.level.visible_sprites], update.other_data.player_id, hp=new_hp)
                else:
                    old_hp = health_elem.get_life()
                    diff = new_hp - old_hp
                    print(f"player hp changed")
                    if diff > 0:
                        health_elem.add_life(diff)
                    elif diff < 0:
                        health_elem.sub_life(abs(diff))
            # elif payload_type == "state":
            #     ...
        elif len(update.bullet_shot) > 0:
            inc_bullets = update.bullet_shot
            for bullet in inc_bullets:
                Bullets.BulletLS.append(Bullets(
                    bullet.gun_type + '_bullet',
                    bullet.x, bullet.y,
                    angle=bullet.angle,
                    from_network=True)
                )

