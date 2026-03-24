import pygame
from mapset import *
class Rock(pygame.sprite.Sprite):#rock obstacle sprites
    def __init__(self,pos,image,name,groups=None):
        if groups is not None:
            super().__init__(groups)
        self.image = image
        if True:
            self.image = pygame.transform.scale(self.image,(SIZE,SIZE))
        self.image.set_colorkey(PINK)
        self.rect = self.image.get_rect(topleft=pos)
        if(name=="rock"):
            self.hitbox = self.rect.inflate(-SIZE/8,-SIZE/8)
        if (name == "tree"):
            self.hitbox = self.rect.inflate(-SIZE / 1.2, -SIZE / 1.5)
            self.hitbox.y+=self.rect.height/3
        else:
            self.hitbox = self.rect.inflate(0,0)
