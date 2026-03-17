# the main game loop
# basic register and login loop
from entity import Entities
import protobuf.region_net_pb2 as region_net
import pygame, sys
import math
from mapset import *
from animation import Animation
from config import ZONE_HOSTS, ZONE_TCP_PORT, ZONE_UDP_PORT
from level import *
from random import randint
from zone_connection import *
import traceback
from typing import List, cast
from enter_screen import EnterScreen

import os
import sys

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)



GREEN = (55, 126, 71)
fps_screen_pos = (10, 10)
SCREEN=pygame.display.set_mode((WIDTH,HEIGHT))
class Game:
    SCREEN=pygame.display.set_mode((WIDTH,HEIGHT))
    def __init__(self, hosts: List[str], tcp_port: int, udp_port: int, session_id: int):
        ZoneConnectionSingleton.set_creds(self, hosts, tcp_port, udp_port)
        pygame.init()
        self.last_shop_ans = None
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))

        self.image = pygame.image.load(resource_path("grass.png"))  # Placeholder background
        self.image = pygame.transform.scale(self.image, (WIDTH, HEIGHT))

        pygame.display.set_caption('Game')
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont(FONT, 30, bold=True)
        self.zone = lambda: cast(ZoneConnection, ZoneConnectionSingleton().zone)
        self.session_id = session_id
        self.level = Level(self.session_id)
        self.is_running = False

    def run(self):
        self.user_id = self.zone().open_connections(self.session_id)
        print(f'trying {self.zone().host}')

        for zone in cast(Dict[str, ZoneConnection], ZoneConnectionSingleton().zone_connections).values():
            if self.zone() == zone:
                continue # we already connected there a second ago
            print(f'trying {zone.host}')
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

                # FPS Counter
                fps = str(int(self.clock.get_fps()))
                fps_surface = self.font.render(fps, True, "White")
                self.screen.blit(fps_surface, fps_screen_pos)

                self.level.run()
                self.screen.blit(fps_surface, fps_screen_pos)
                hb = self.level.player.hitbox
                self.zone().try_send_update_pos((hb.x, hb.y))

                # Show current region node near the FPS bar (0-based indices)
                node_x = int(hb.x // NODE_WIDTH)
                node_y = int(hb.y // NODE_HEIGHT)
                node_text = f"({node_x}, {node_y})"
                node_surface = self.font.render(node_text, True, "White")
                node_pos = (fps_screen_pos[0], fps_screen_pos[1] + fps_surface.get_height() + 5)
                self.screen.blit(node_surface, node_pos)

                pygame.display.update()
                self.clock.tick(FPS)
        except Exception as e:
            print(f"Game Loop Error: {e}")
        finally:
            print("Closing Game...")
            ZoneConnectionSingleton.stop_sender()
            self.zone().stop()
            pygame.quit()
            sys.exit()

if __name__ == "__main__":
    login_screen = EnterScreen()
    session_id = login_screen.run()

    if session_id is None:
        print("User cancelled login. Exiting.")
        sys.exit()

    YELLOW = '\033[33m'
    RESET = '\033[0m'
    print(f"Login successful! Starting Game with Session ID: {session_id}")
    print(YELLOW + f"connecting to server at {ZONE_HOSTS[0]}:{ZONE_TCP_PORT}. If this is incorrect, please re-run setup_dev.py" + RESET)

    try:
        game = Game(ZONE_HOSTS, ZONE_TCP_PORT, ZONE_UDP_PORT, session_id)
        game.run()
    except Exception as e:
        print(f"[FATAL]: {e}")
        if 'game' in locals():
            try:
                game.zone().stop()
            except:
                pass
        pygame.quit()
        print(f"[TRACEBACK]: {traceback.format_exc()}")
        sys.exit(1)

    print("finished-end")
