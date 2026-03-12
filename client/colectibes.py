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

            if getattr(self.obj, "weapon_frames", None):
                self.image = self.obj.weapon_frames[0]
                DROP_SIZE = 67+20
            else:
                self.image = self.obj.get_image()
                DROP_SIZE = 26

        elif kind == "potion":
            self.obj = Potion(name,id)
            self.image = self.obj.get_image()
            DROP_SIZE = 35
        elif kind == "money":
            self.obj = Mony(id)
            DROP_SIZE = 20
            self.image = self.obj.get_image()

        w, h = self.image.get_size()

        self.image = pygame.transform.scale(
            self.image,
            (DROP_SIZE, int(h * (DROP_SIZE / w)))
        )

        self.rect = self.image.get_rect(topleft=position)
        self.id=id
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