import pygame
from mapset import WIDTH,HEIGHT
from mapset import *
from Arsenal import *

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

        self.inventory=["Ak-7"]
        self.inventory_pointer = 0

    def add_item_toThe_Inventory(self, item):
        self.inventory.append(item)

    def items_hendeling(self, player):
        #for item in self.inventory:
            #for keyGunType in Arsenal.Arsenal_gunType.keys():
                #if item == keyGunType:
        Arsenal("Ak-7").draw(WIDTH/2,HEIGHT/2)

    def open(self):
        self.display.blit(self.image, self.rect)
        self.use()

    def use(self):
        keys = pygame.key.get_pressed()
        if keys[pygame.K_p] and keys[pygame.K_1]:
            print("P and 1 are being pressed together!")

