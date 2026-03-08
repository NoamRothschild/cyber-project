# the main game loop
# basic register and login loop
from entity import Entities
import protobuf.region_net_pb2 as region_net
import pygame, sys
from mapset import *
from level import *
from config import ZONE_HOST, ZONE_TCP_PORT, ZONE_UDP_PORT
from random import randint
from zone_connection import *
from enter_screen import EnterScreen
from enter_screen import EnterScreen
from config import ZONE_HOST, ZONE_TCP_PORT, ZONE_UDP_PORT
import traceback

GREEN = (55, 126, 71)
fps_screen_pos = (10, 10)

class Game:
    SCREEN=pygame.display.set_mode((WIDTH,HEIGHT))
    def __init__(self, host: str, tcp_port: int, udp_port: int):
        ZoneConnectionSingleton.set_creds(self, host, tcp_port, udp_port)

        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))

        self.image = pygame.image.load("grass.png")  # Placeholder background
        self.image = pygame.transform.scale(self.image, (WIDTH, HEIGHT))

        pygame.display.set_caption('Game')
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont(FONT, 30, bold=True)

        self.zone = ZoneConnectionSingleton().zone
        self.session_id = session_id

        self.level = Level()
        self.is_running = False

    def run(self):
        # Open connection
        self.user_id = self.zone.open_reliable_conn(self.session_id)
        self.is_running = True

        try:
            while self.is_running:
                # 1. Event Handling
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.is_running = False
                        break

                if not self.is_running:
                    break
            if not self.is_running: break

                # 2. Drawing
                self.screen.fill(GREEN)

                # FPS Counter
                fps = str(int(self.clock.get_fps()))
                fps_surface = self.font.render(fps, True, "White")
                self.screen.blit(fps_surface, fps_screen_pos)

                # 3. Game Logic
                self.level.run()

                # 4. Network Update
                hb = self.level.player.hitbox
                self.zone.try_send_update_pos((hb.x, hb.y))

                # 5. Display Update
                pygame.display.update()
                self.clock.tick(FPS)

        pygame.quit()
        #sys.exit()


if __name__ == "__main__":
    login_screen = EnterScreen()
    session_id = login_screen.run()

    if session_id is None:
        print("User cancelled login. Exiting.")
        sys.exit()

    print(f"Login successful! Starting Game with Session ID: {session_id}")

    try:
        game = Game(ZONE_HOST, ZONE_TCP_PORT, ZONE_UDP_PORT, session_id)
        game.run()
    except Exception as e:
        print(f"Game Error: {e}")
        traceback.print_exc()
