import pygame
from mapset import WIDTH,HEIGHT
from Game import Game
from mapset import *
from  Arsenal import *
from Game import *
import time
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


        self.inventory=[]
        self.current_weapon = 0
        self.delete_interval = 4
        self.delete_last_action_time = 0
    def add_item_toThe_Inventory(self, item):
        self.inventory.append(item)

    def items_hendeling(self, player):
        #for item in self.inventory:
            #for keyGunType in Arsenal.Arsenal_gunType.keys():
                #if item == keyGunType:
        if not self.is_empty():
            self.inventory[self.current_weapon].draw(WIDTH / 2, HEIGHT / 2)

    def open(self):
        self.display.blit(self.image, self.rect)
        for i, wep in enumerate(self.inventory):
            wep.draw_for_inventory(i, self.rect.x, self.rect.y)

        self.use()
    def is_empty(self):
        return len(self.inventory)==0
    def use(self):
        keys = pygame.key.get_pressed()
        for i in range(10):
            key_constant = getattr(pygame, f"K_{i}")
            if keys[key_constant] and i-1!=self.current_weapon and i-1<len(self.inventory):
                self.current_weapon=i-1
        if keys[pygame.K_DELETE]:
            self.delete()

    def delete(self):
        current_time = time.time()
        if current_time - self.delete_last_action_time >= self.delete_interval and self.is_empty()==False:
            del self.inventory[self.current_weapon]
            if self.current_weapon!=0:
                self.current_weapon=self.current_weapon-1
            self.delete_last_action_time = current_time
