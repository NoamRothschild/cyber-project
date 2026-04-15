# the main game loop
# basic register and login loop
import pygame, sys
from mapset import *
from config import ZONE_HOSTS, ZONE_TCP_PORT, ZONE_UDP_PORT
from level import *
from protobuf import auth_net_pb2
from zone_connection import *
import traceback
from typing import List, cast
from enter_screen import EnterScreen

import sys
from sys import argv

from paths import resource_path

GREEN = (55, 126, 71)
fps_screen_pos = (10, 10)
SCREEN = pygame.display.set_mode((WIDTH, HEIGHT))


class Game:
    SCREEN = pygame.display.set_mode((WIDTH, HEIGHT))

    def __init__(self, hosts: List[str], tcp_port: int, udp_port: int, session_id: int):
        ZoneConnectionSingleton.set_creds(self, hosts, tcp_port, udp_port)
        pygame.init()
        self.last_shop_ans = None
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))

        self.image = pygame.image.load(
            resource_path("grass.png")
        )  # Placeholder background
        self.image = pygame.transform.scale(self.image, (WIDTH, HEIGHT))

        pygame.display.set_caption("Game")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont(FONT, 30, bold=True)
        self.zone = lambda: cast(ZoneConnection, ZoneConnectionSingleton().zone)
        self.session_id = session_id
        self.server_fps: int | None = None  # updated by zone event handler from server
        self.level = Level(self.session_id)
        self.is_running = False
        self.user_id: int | None = None

    def run(self):
        for zone in cast(
            Dict[str, ZoneConnection], ZoneConnectionSingleton().zone_connections
        ).values():
            print(f"trying {zone.host}")
            zone.open_connections(self.session_id)

        ZoneConnectionSingleton.start_sender()
        self.zone().start_event_handler()
        self.is_running = True

        try:
            while self.is_running:
                # 1. Event Handling
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.is_running = False
                        break
                    self.level.handle_event(event)

                if not self.is_running:
                    break

                # 2. Drawing
                self.screen.fill(GREEN)

                # FPS Counter (client + server)
                client_fps = str(int(self.clock.get_fps()))
                server_fps_str = (
                    str(self.server_fps) if self.server_fps is not None else "-"
                )
                fps_text = f"FPS: {client_fps} | Server: {server_fps_str}"
                fps_surface = self.font.render(fps_text, True, "White")
                self.screen.blit(fps_surface, fps_screen_pos)

                y_next = fps_screen_pos[1] + fps_surface.get_height() + 4
                srv_surface = self.font.render(self.zone().host, True, "White")
                self.screen.blit(srv_surface, (fps_screen_pos[0], y_next))

                self.level.run()
                self.screen.blit(fps_surface, fps_screen_pos)
                self.screen.blit(srv_surface, (fps_screen_pos[0], y_next))
                hb = self.level.player.hitbox
                self.zone().try_send_update_pos((hb.x, hb.y))

                y_hud = y_next + srv_surface.get_height() + 5
                pos_text = f"Pos: ({int(hb.x // 200)}, {int(hb.y // 200)})"
                pos_surface = self.font.render(pos_text, True, "White")
                self.screen.blit(pos_surface, (fps_screen_pos[0], y_hud))

                pygame.display.update()
                self.clock.tick(FPS)
        except Exception as e:
            print(f"Game Loop Error: {e}")
        finally:
            print("Closing Game...")
            ZoneConnectionSingleton.stop_all()
            pygame.quit()
            import os, time

            time.sleep(1)
            os._exit(0)


def reg_or_log_unwrap(username: str, type: str) -> int | None:
    """depending on the value of type {"REG", "LOG"} ..."""
    import client_auth

    type = type.upper()[:3]

    resp: auth_net_pb2.SendAnswer | str = client_auth.connect(
        str(username), "123", "REG"
    )
    if isinstance(resp, str):
        print(
            f"[ERR] creating/loging in to client with id {username} failed with: {resp}"
        )
        sys.exit()
    if resp.status != auth_net_pb2.Status.SUCCESS:
        print(
            f"[ERR] server gave a not wanted resp: {auth_net_pb2.Status.Name(resp.status)}"
        )
        sys.exit()
    return resp.session_id


if __name__ == "__main__":
    argv = argv[1:]
    session_id: int | None = None
    if len(argv) == 0:
        login_screen = EnterScreen()
        session_id = login_screen.run()
    else:
        username = argv[0]
        reg_or_log_unwrap(username, "REG")
        session_id = reg_or_log_unwrap(username, "LOG")

    if session_id is None:
        print("User cancelled login. Exiting.")
        sys.exit()

    YELLOW = "\033[33m"
    RESET = "\033[0m"
    print(f"Login successful! Starting Game with Session ID: {session_id}")
    print(
        YELLOW
        + f"connecting to server at {ZONE_HOSTS[0]}:{ZONE_TCP_PORT}. If this is incorrect, please re-run setup_dev.py"
        + RESET
    )

    try:
        game = Game(ZONE_HOSTS, ZONE_TCP_PORT, ZONE_UDP_PORT, session_id)
        game.run()
    except Exception as e:
        print(f"[FATAL]: {e}")
        if "game" in locals():
            try:
                game.zone().stop()
            except:
                pass
        pygame.quit()
        print(f"[TRACEBACK]: {traceback.format_exc()}")
        sys.exit(1)

    print("finished-end")
