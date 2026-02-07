import pygame
from mapset import *
from Arsenal import Arsenal
from potion import Potion
class Colectible_sprite(pygame.sprite.Sprite):
    def __init__(self,position,groups,name,kind):
        super().__init__(groups)
        self.kind = kind
        if kind=="weapon":
            self.obj=Arsenal(name)
        elif kind=="potion":
            self.obj = Potion(name)
        self.image = self.obj.get_image()
        self.image.set_colorkey((23, 130, 184))

        self.image=pygame.transform.scale(self.image,(size/2,self.image.get_height()*((size/2))/self.image.get_width()))
        self.rect = self.image.get_rect()
        self.rect = self.image.get_rect(topleft=position)


