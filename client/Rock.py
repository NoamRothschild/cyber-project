import pygame
from mapset import *
class Rock(pygame.sprite.Sprite):#rock obstacle sprites
    def __init__(self,pos,groups,image):
        super().__init__(groups)
        self.image = image
        self.image.set_colorkey(PINK)
        self.rect = self.image.get_rect(topleft=pos)
