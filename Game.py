#the main game loop
#basic register and login loop
import pygame,sys
from mapset import *

class Game:

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH,HEIGHT))
        self.image=pygame.image.load("grass.png")
        self.image=pygame.transform.scale(self.image,(WIDTH,HEIGHT))
        pygame.display.set_caption('Game')
        self.clock = pygame.time.Clock()

    def enter_screen(self):
        pass#here will call the enter screen
    def run(self):
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

            self.screen.blit(self.image,(0,0))

            pygame.display.update()
            self.clock.tick(FPS)
if __name__ == '__main__':
    game = Game()
    game.run()

