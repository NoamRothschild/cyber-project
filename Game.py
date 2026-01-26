#the main game loop
#basic rejister and login loop
from typing import Tuple
import pygame,sys
from mapset import *
from level import *
from connection_handler import SERVER_ADDR, region_net
import socket
import threading

class Game:
    def __init__(self, region_server_addr: Tuple[str, int]):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH,HEIGHT))
        self.image=pygame.image.load("grass.png")
        self.image=pygame.transform.scale(self.image,(WIDTH,HEIGHT))
        pygame.display.set_caption('Game')
        self.clock = pygame.time.Clock()

        self.old_pos: Tuple[int, int] = (0,0)
        self.region_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.region_server_addr = region_server_addr

        self.listener_thread = threading.Thread(target=Game.handle_server_packet, args=(self,))

        self.level =level()
        self.is_running = False

    def run(self):
        self.region_conn.connect(self.region_server_addr)
        self.listener_thread.start()
        self.is_running = True

        while self.is_running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.is_running = False
                    break
            if not self.is_running: break

            self.screen.blit(self.image,(0,0))
            self.level.run()
            pygame.display.update()
            hb = self.level.player.hitbox

            new_pos = (hb.x, hb.y)
            moved = self.old_pos != new_pos
            if moved:
                update = region_net.RegionUpdate()
                update.location_block.CopyFrom(
                    region_net.LocationBlock(
                        x=hb.x, y=hb.y
                    )
                )
                self.old_pos = new_pos
                self.region_conn.sendall(update.SerializeToString())

            self.clock.tick(FPS)

        pygame.quit()
        sys.exit()


    def handle_server_packet(self):
        buff_size = 1024
        while True:
            server_raw = self.region_conn.recv(buff_size)
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
                hb = self.level.player.hitbox
                hb.x = parsed.move_self.x
                hb.y = parsed.move_self.y
            elif payload_type == "other_data":
                payload_type = parsed.other_data.WhichOneof("payload")
                print(f"{payload_type=}")
                # if payload_type == "new_location":
                #     ...
                # elif payload_type == "HP":
                #     ...
                # elif payload_type == "state":
                #     ...

if __name__ == '__main__':
    game = Game(SERVER_ADDR)
    game.run()

