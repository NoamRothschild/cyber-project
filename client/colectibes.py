import pygame
from mapset import *
from client.arsenal import Arsenal
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
        self.image = self.obj.get_image()
        self.image.set_colorkey(blue)
        self.id=id

        self.image = pygame.transform.scale(self.image,
                                            (SIZE / 2, self.image.get_height() * ((SIZE / 2)) / self.image.get_width()))
        self.rect = self.image.get_rect()
        self.rect = self.image.get_rect(topleft=position)
