import pygame

from mapset import *
from Player import *
from Rock import Rock
class level:
    def __init__(self):
        self.display_surface = pygame.display.get_surface()

        self.visible_sprites = Camera()
        self.obstacle_sprites = pygame.sprite.Group()

        self.draw_map()

    def draw_map(self):#crating a very basic map with small borders(need to be changed
        for i in range(WIDTH*40//size-size):
            Rock((i*size, 0), [self.visible_sprites, self.obstacle_sprites])
            Rock((i * size, 100*size), [self.visible_sprites, self.obstacle_sprites])
        for i in range(HEIGHT*40//size-size):
            Rock((0, i * size), [self.visible_sprites, self.obstacle_sprites])
            Rock((100*size,i * size ), [self.visible_sprites, self.obstacle_sprites])
        for rindex,row in enumerate(world_map):
            for cindex,col in enumerate(row):
                x=cindex*size+2*size
                y=rindex*size+2*size
                if col=='x':
                    Rock((x,y),[self.visible_sprites,self.obstacle_sprites])

                if col=='p':
                    self.player=Player((x,y),[self.visible_sprites],self.obstacle_sprites)


    def run(self):
        self.visible_sprites.custom_draw(self.player)

        self.visible_sprites.update()

class Camera(pygame.sprite.Group):# a group that has every visible sprite that should be moved when the player does
    def __init__(self):
        super().__init__()
        self.display = pygame.display.get_surface()
        self.half_width = self.display.get_width()/2
        self.half_height = self.display.get_height()/2
        self.point=pygame.math.Vector2()

    def custom_draw(self,player):
        self.point.x=player.rect.centerx-self.half_width
        self.point.y=player.rect.centery-self.half_height
        for sprite in self.sprites():
            point_pos= sprite.rect.topleft-self.point
            self.display.blit(sprite.image,point_pos)