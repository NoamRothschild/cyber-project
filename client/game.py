#the main game loop
#basic rejister and login loop
from Entity import Entities
import protobuf.region_net_pb2 as region_net
import pygame
from mapset import *
from level import *
from config import ZONE_HOST, ZONE_TCP_PORT, ZONE_UDP_PORT
from zone_connection import *
from random import randint
from mapset import WIDTH,HEIGHT

class Game:
    SCREEN=pygame.display.set_mode((WIDTH,HEIGHT))
    def __init__(self, host: str, tcp_port: int, udp_port: int):
        ZoneConnectionSingleton.set_creds(self, host, tcp_port, udp_port)
        pygame.init()

        self.screen = Game.SCREEN
        self.image=pygame.image.load("grass.png")
        self.image=pygame.transform.scale(self.image,(WIDTH,HEIGHT))

        pygame.display.set_caption('Game')
        self.clock = pygame.time.Clock()
        self.zone = ZoneConnectionSingleton().zone

        # randomized for now, will get generated from the auth server.
        self.session_id = randint(0, 2 ** 31 - 1)
        self.level = level()
        self.is_running = False

    def run(self):
        self.zone.open_reliable_conn(self.session_id)
        self.is_running = True

        while self.is_running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.is_running = False
                    break
            if not self.is_running: break

            self.screen.blit(self.image,(0,0))

            self.level.run(self.zone)

            hb = self.level.player.hitbox
            self.zone.try_send_update_pos((hb.x, hb.y))
            pygame.display.update()
            self.clock.tick(FPS)

        pygame.quit()
        #sys.exit()



if __name__ == '__main__':

    YELLOW = '\033[33m'
    RESET = '\033[0m'
    print(YELLOW + f"connecting to server at {ZONE_HOST}:{ZONE_TCP_PORT}. If this is incorrect, please re-run setup_dev.py" + RESET)

    game = Game(ZONE_HOST, ZONE_TCP_PORT, ZONE_UDP_PORT)
    game.run()

    print("finished-end")
