import pygame
from random import randint
from mapset import *
from arsenal import Arsenal
from potion import Potion

blue = (23, 130, 184)


class Colectible_sprite(pygame.sprite.Sprite):
    def __init__(self, position, groups, name, kind, id: int, ammo=None):
        super().__init__(groups)
        self.kind = kind
        self.id = id

        if kind == "weapon":
            # Pass saved ammo into the Arsenal (if provided) and preserve id
            self.obj = Arsenal(name, saved_ammo=ammo, id=id)

            if getattr(self.obj, "weapon_frames", None):
                self.image = self.obj.weapon_frames[0].copy()
                DROP_SIZE = 87
            else:
                self.image = self.obj.get_image().copy()
                DROP_SIZE = 26
        elif kind == "potion":
            self.obj = Potion(name, id)
            self.image = self.obj.get_image().copy()
            DROP_SIZE = 35
        elif kind == "money":
            self.obj = Mony(id)
            self.image = self.obj.get_image()
            DROP_SIZE = 20
        else:
            # Fallback: no associated object
            self.obj = None
            self.image = pygame.Surface((0, 0))
            DROP_SIZE = 0

        if DROP_SIZE > 0:
            w, h = self.image.get_size()
            if w > 0 and h > 0:
                self.image = pygame.transform.scale(
                    self.image,
                    (DROP_SIZE, int(h * (DROP_SIZE / w))),
                )

        self.image.set_colorkey(blue)
        self.image = self.image.convert_alpha()
        self.rect = self.image.get_rect(topleft=position)


class Mony(pygame.sprite.Sprite):
    def __init__(self, id: int = 0):
        pygame.display.get_surface()
        image = pygame.image.load("gold.png").convert_alpha()
        if id == 0:
            self.id = randint(0, 2**31 - 1)
        else:
            self.id = id
        self.image = pygame.transform.scale(image, (20, 20))

    def get_image(self):
        return self.image
