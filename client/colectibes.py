import pygame
from pygame.examples.cursors import image
from random import randint
from mapset import *
from arsenal import Arsenal
from potion import Potion

blue=(23, 130, 184)
class Colectible_sprite(pygame.sprite.Sprite):
    def __init__(self, position, groups, name, kind,id: int):
        super().__init__(groups)
        self.kind = kind
        if kind == "weapon":
            self.obj = Arsenal(name,id)
        elif kind == "potion":
            self.obj = Potion(name,id)
        elif kind == "money":
            self.obj = Mony(id)
        self.image = self.obj.get_image()

        self.id=id
        if kind != "money":
            self.image.set_colorkey(blue)
            self.image = pygame.transform.scale(self.image,
                                            (SIZE / 2, self.image.get_height() * ((SIZE / 2)) / self.image.get_width()))
        self.rect = self.image.get_rect()
        self.rect = self.image.get_rect(topleft=position)

class Mony(pygame.sprite.Sprite):

    def __init__(self,id: int=0):
        pygame.display.get_surface()
        image=pygame.image.load("gold.png").convert_alpha()
        if id==0:
            self.id=randint(0, 2**31 - 1)
        else:
            self.id=id
        self.image = pygame.transform.scale(image, (20, 20))
    def get_image(self):
        return self.image