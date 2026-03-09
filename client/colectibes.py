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
                # Use .copy() so we don't accidentally mess up the original Arsenal image
                self.image = self.obj.weapon_frames[0].copy()
                DROP_SIZE = 87
            else:
                self.image = self.obj.get_image().copy()
                DROP_SIZE = 26
        elif kind == "potion":
            self.obj = Potion(name)
            self.image = self.obj.get_image().copy()
            DROP_SIZE = 35

        # 1. Scale first (this creates the "dirty" blue edges)
        w, h = self.image.get_size()
        self.image = pygame.transform.scale(
            self.image,
            (DROP_SIZE, int(h * (DROP_SIZE / w)))
        )

        # 2. NOW set the colorkey so it wipes the blue away
        self.image.set_colorkey(blue)

        # 3. Use convert_alpha() to ensure the transparency is baked in
        self.image = self.image.convert_alpha()

        self.rect = self.image.get_rect(topleft=position)