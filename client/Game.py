#the main game loop
#basic rejister and login loop
from Entity import Entities
import protobuf.region_net_pb2 as region_net
import pygame,sys
from mapset import *
from level import *
from config import ZONE_HOST, ZONE_TCP_PORT, ZONE_UDP_PORT
from random import randint
from region_connection import *

GREEN=(55,126,71)
class Game:
    def __init__(self, host: str, tcp_port: int, udp_port: int):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH,HEIGHT))
        self.image=pygame.image.load("grass.png")#the background should be changed and moved to level
        self.image=pygame.transform.scale(self.image,(WIDTH,HEIGHT))
        pygame.display.set_caption('Game')
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont(Font, 30, bold=True)
        self.zone = ZoneConnection(self, host, tcp_port, udp_port)
        # randomized for now, will get generated from the auth server.
        self.session_id = randint(0, 2 ** 31 - 1)
        self.level =Level()
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

            self.screen.fill(GREEN)#for now but we should add the background to visable sprite in level
            fps = str(int(self.clock.get_fps()))
            fps_surface = self.font.render(fps, True, (255, 255, 255))

            self.level.run()
            self.screen.blit(fps_surface, (10, 10))
            hb = self.level.player.hitbox

            self.zone.try_send_update_pos((hb.x, hb.y))
            pygame.display.update()
            self.clock.tick(FPS)

        pygame.quit()
        sys.exit()


if __name__ == '__main__':
    game = Game(ZONE_HOST, ZONE_TCP_PORT, ZONE_UDP_PORT)
    game.run()

