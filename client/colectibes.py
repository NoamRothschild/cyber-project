import pygame
from mapset import *
from client.arsenal import Arsenal
from potion import Potion

blue=(23, 130, 184)
class Colectible_sprite(pygame.sprite.Sprite):
    def __init__(self, position, groups, name, kind):
        super().__init__(groups)

        self.kind = kind

        if kind == "weapon":
            self.obj = Arsenal(name)

            if getattr(self.obj, "weapon_frames", None):
                self.image = self.obj.weapon_frames[0]
                DROP_SIZE = 67+20
            else:
                self.image = self.obj.get_image()
                DROP_SIZE = 26

        elif kind == "potion":
            self.obj = Potion(name)
            self.image = self.obj.get_image()
            DROP_SIZE = 35

        self.image.set_colorkey(blue)

        w, h = self.image.get_size()

        self.image = pygame.transform.scale(
            self.image,
            (DROP_SIZE, int(h * (DROP_SIZE / w)))
        )

        self.rect = self.image.get_rect(topleft=position)