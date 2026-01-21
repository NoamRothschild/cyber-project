import pygame
from mapset import *

class Inventory(pygame.sprite.Sprite):

    def __init__(self):
        super().__init__()
        self.image = pygame.image.load('inventory.png').convert()
        #self.image=pygame.transform.scale(self.image,(WIDTH,self.image.get_height()))
        self.image.set_colorkey(PINK)
        self.rect = self.image.get_rect()
        self.rect.y=HEIGHT-(self.rect.height)
        self.rect.x=WIDTH/2-(self.rect.width/2)
        self.display = pygame.display.get_surface()
        #self.unused_weapons=pygame.sprite.Group()
        #self.potions=pygame.sprite.Group()
    def open(self):
        self.display.blit(self.image, self.rect)
        self.use()

    def use(self):
        keys = pygame.key.get_pressed()
        if keys[pygame.K_p] and keys[pygame.K_1]:
            print("P and 1 are being pressed together!")

