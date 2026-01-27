#the main game loop
#basic register and login loop
import pygame,sys
from mapset import *
from level import *
class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH,HEIGHT))
        self.image=pygame.image.load("grass.png")#the background should be changed and moved to level
        self.image=pygame.transform.scale(self.image,(WIDTH,HEIGHT))
        pygame.display.set_caption('Game')
        self.clock = pygame.time.Clock()

        self.level =level()#build the game level class that handhelds the game

    def run(self):#running the game loop
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

            self.screen.blit(self.image,(0,0))#for now but we should add the background to visable sprite in level
            self.level.run()
            pygame.display.update()
            self.clock.tick(FPS)
if __name__ == '__main__':
    game = Game()
    game.run()

