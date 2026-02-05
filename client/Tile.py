import pygame
from mapset import *
class Rock(pygame.sprite.Sprite):#rock obstacle sprites
    def __init__(self,pos,groups,image,name):
        super().__init__(groups)
        self.image = image
        self.image = pygame.transform.scale(self.image,(size,size))
        self.image.set_colorkey(PINK)
        self.rect = self.image.get_rect(topleft=pos)
        if(name=="rock"):
            self.hitbox = self.rect.inflate(-size/8,-size/8)
        if (name == "tree"):
            self.hitbox = self.rect.inflate(-size / 1.2, -size / 1.5)
            self.hitbox.y+=self.rect.height/3
        else:
            self.hitbox = self.rect.inflate(0,0)
