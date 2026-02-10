#the main game loop
#basic rejister and login loop
import protobuf.region_net_pb2 as region_net
import pygame,sys

from mapset import *
from Level import *
from config import ZONE_HOST, ZONE_TCP_PORT, ZONE_UDP_PORT
from region_server_extras import ZoneConnection
from mapset import WIDTH,HEIGHT

class Game:
    SCREEN=pygame.display.set_mode((WIDTH,HEIGHT))
    def __init__(self, host: str, tcp_port: int, udp_port: int):
        pygame.init()
        self.screen = Game.SCREEN
        self.image=pygame.image.load("grass.png")
        self.image=pygame.transform.scale(self.image,(WIDTH,HEIGHT))
        pygame.display.set_caption('Game')
        self.clock = pygame.time.Clock()
        self.zone = ZoneConnection(self, host, tcp_port, udp_port)

        self.level =Level()
        self.is_running = False

    def run(self):
        self.zone.open_reliable_conn()
        self.is_running = True

        while self.is_running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.is_running = False
                    break
                self.level.handle_event(event)

            if not self.is_running: break

            self.screen.blit(self.image,(0,0))

            self.level.run()

            hb = self.level.player.hitbox
            self.zone.try_send_update_pos((hb.x, hb.y))
            pygame.display.update()
            self.clock.tick(FPS)

        pygame.quit()
        #sys.exit()



if __name__ == '__main__':
    game = Game(ZONE_HOST, ZONE_TCP_PORT, ZONE_UDP_PORT)
    game.run()

    print("finished-end")