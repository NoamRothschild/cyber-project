# the main game loop
# basic rejister and login loop
from entity import Entities
import protobuf.region_net_pb2 as region_net
import pygame, sys
import math
from mapset import *
from level import *
from config import ZONE_HOSTS, ZONE_TCP_PORT, ZONE_UDP_PORT
from random import randint
from zone_connection import *
import traceback
from typing import List, cast

GREEN = (55, 126, 71)
fps_screen_pos = (10, 10)


class Game:
    SCREEN=pygame.display.set_mode((WIDTH,HEIGHT))
    def __init__(self, hosts: List[str], tcp_port: int, udp_port: int):
        ZoneConnectionSingleton.set_creds(self, hosts, tcp_port, udp_port)
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.image = pygame.image.load("grass.png")  # the background should be changed and moved to level
        self.image = pygame.transform.scale(self.image, (WIDTH, HEIGHT))
        pygame.display.set_caption('Game')
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont(FONT, 30, bold=True)
        self.zone = lambda: cast(ZoneConnection, ZoneConnectionSingleton().zone)
        # randomized for now, will get generated from the auth server.
        self.session_id = randint(0, 2 ** 31 - 1)
        self.level = Level()
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

        while self.is_running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.is_running = False
                    break
            if not self.is_running: break

            self.screen.fill(GREEN)  # for now but we should add the background to visable sprite in level
            fps = str(int(self.clock.get_fps()))
            fps_surface = self.font.render(fps, True, "White")

            self.level.run()
            self.screen.blit(fps_surface,fps_screen_pos )
            hb = self.level.player.hitbox
            # Report precise world position to the server
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

        ZoneConnectionSingleton.stop_sender()
        self.zone().stop()
        pygame.quit()
        #sys.exit()



if __name__ == '__main__':

    YELLOW = '\033[33m'
    RESET = '\033[0m'
    print(YELLOW + f"connecting to server at {ZONE_HOSTS[0]}:{ZONE_TCP_PORT}. If this is incorrect, please re-run setup_dev.py" + RESET)

    try:
        game = Game(ZONE_HOSTS, ZONE_TCP_PORT, ZONE_UDP_PORT)
        game.run()
    except Exception as e:
        print(f"[FATAL]: {e}")
        game.zone().stop()
        pygame.quit()
        print(f"[TRACEBACK]: {traceback.format_exc()}")
        sys.exit(1)

    print("finished-end")
