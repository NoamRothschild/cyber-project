from __future__ import annotations
import socket
import threading
from typing import Tuple, TYPE_CHECKING
import protobuf.region_net_pb2 as region_net

if TYPE_CHECKING:
    from Game import Game

BUFF_SIZE = 1024

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
            if payload_type == "new_location":
                pos = parsed.other_data.new_location
                game.level.entities.add_or_update(parsed.sender_id, (pos.x, pos.y), [game.level.visible_sprites])
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


def should_update_location(old_pos: Tuple[int, int], new_pos: Tuple[int, int], min_dst=5) -> bool:
    """returns true when the distance between the two pos are above min_dst"""
    if old_pos == new_pos:
        return False
    traveled_dst_squared = (old_pos[0] - new_pos[0]) ** 2 + (old_pos[1] - new_pos[1]) ** 2
    min_dst_squared = min_dst ** 2

    return traveled_dst_squared > min_dst_squared
