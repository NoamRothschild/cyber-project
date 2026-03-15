import pygame
from mapset import *
from arsenal import Arsenal
from potion import Potion

blue=(23, 130, 184)


class Colectible_sprite(pygame.sprite.Sprite):
    # --- NEW: Added 'ammo=None' to the parameters ---
    def __init__(self, position, groups, name, kind, ammo=None):
        super().__init__(groups)
        self.kind = kind

        if kind == "weapon":
            # --- NEW: Pass the saved ammo into the Arsenal! ---
            self.obj = Arsenal(name, saved_ammo=ammo)

            if getattr(self.obj, "weapon_frames", None):
                self.image = self.obj.weapon_frames[0].copy()
                DROP_SIZE = 87
            else:
                self.image = self.obj.get_image().copy()
                DROP_SIZE = 26
        elif kind == "potion":
            self.obj = Potion(name)
            self.image = self.obj.get_image().copy()
            DROP_SIZE = 35

        w, h = self.image.get_size()
        self.image = pygame.transform.scale(
            self.image,
            (DROP_SIZE, int(h * (DROP_SIZE / w)))
        )

        self.image.set_colorkey(blue)
        self.image = self.image.convert_alpha()
        self.rect = self.image.get_rect(topleft=position)