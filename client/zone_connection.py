from __future__ import annotations
import socket
import threading
from typing import Tuple, TYPE_CHECKING
import protobuf.region_net_pb2 as region_net
from inventory import WEAPON_MAP, POTION_MAP
from potion import Potion
from arsenal import Arsenal

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

        self.game = game

    def open_reliable_conn(self, session_id: str) -> int:
        """opens the TCP conn and returns the user id. can throw"""
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

        player = self.game.level.player

        player.hitbox.x = login_resp.pos_x
        player.hitbox.y = login_resp.pos_y

        player.rect.center = player.hitbox.center

        self.server_known_pos = (login_resp.pos_x, login_resp.pos_y)

        player.health.set_life(login_resp.health)

        # --- THE FIX: Clear the new lists and create Arsenal objects ---
        player.inventory.wep_inventory.clear()
        player.inventory.potion_inventory.clear()

        from arsenal import Arsenal

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

        print(f"Sync Complete: Player loaded at X:{player.hitbox.x} Y:{player.hitbox.y}")

        listener = threading.Thread(target=server_listener, args=(self.game, self,))
        listener.start()
        return login_resp.user_id

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
    def try_send_potion_use(self, potion_kind: str, how_much: int ) -> None:
        print("Sending HP event to server...")
        update = region_net.RegionUpdate()
        # --- THE FIX: Pass 0 instead of the string so Protobuf doesn't choke ---
        update.potion_use.CopyFrom(
            region_net.PotionUse(
                potion_type=0, HowMuch=how_much
            )
        )
        self.reliable_conn.sendall(update.SerializeToString())

    def try_send_item_drop(self, inventory_index: int, item_kind: str) -> None:
        print(f"Sending drop request for {item_kind} at slot {inventory_index}")
        update = region_net.RegionUpdate()
        update.item_drop.CopyFrom(
            region_net.ItemDrop(
                inventory_index=inventory_index,
                item_kind=item_kind
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


def server_listener(game: Game, zone: ZoneConnection):
    """
    Start this one in another thread
    Assumes a connection has already been established in `game.region_conn`
    """
    from bullets import Bullets

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
                game.level.entities.add_or_update([game.level.visible_sprites], parsed.sender_id, pos=(pos.x, pos.y))
            elif payload_type == "HP":
                health_elem = game.level.player.health
                new_hp = parsed.other_data.HP
                print(f"{parsed.other_data.player_id=}")
                if parsed.other_data.player_id != game.user_id:
                    game.level.entities.add_or_update([game.level.visible_sprites], parsed.other_data.player_id,
                                                      hp=new_hp)
                else:
                    # Forces the screen to show the "true" health from the server so the game doesn't desync.
                    # --- THE FIX: Hard-Sync with the Server ---
                    # Don't use diffs. Don't trigger I-frames. Just snap the UI to the Server's absolute truth.
                    print(f"Syncing local HP to Server's absolute HP: {new_hp}")
                    health_elem.set_life(new_hp)
            # elif payload_type == "state":
            #     ...
        elif len(parsed.bullet_shot) > 0:
            inc_bullets = parsed.bullet_shot
            for bullet in inc_bullets:
                Bullets.BulletLS.append(Bullets(
                    Arsenal.bullet_from_gun(bullet.gun_type),
                    bullet.x, bullet.y,
                    angle=bullet.angle,
                    from_network=True)
                )

