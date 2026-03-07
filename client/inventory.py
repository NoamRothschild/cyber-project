import pygame
from mapset import WIDTH,HEIGHT
from mapset import *
from arsenal import *
import time
from colectibes import Colectible_sprite
class Inventory(pygame.sprite.Sprite):


    def __init__(self):
        super().__init__()
        self.image = pygame.image.load('inventory.png').convert()
        self.image.set_colorkey(PINK)#image background
        self.rect = self.image.get_rect()
        self.rect.y=HEIGHT-self.rect.height
        self.rect.x=WIDTH/2-(self.rect.width/2)#putting the inventory in a specific place
        self.display = pygame.display.get_surface()
        # self.unused_weapons=pygame.sprite.Group()
        # self.potions=pygame.sprite.Group()

        self.potion_inventory = []
        self.wep_inventory = []
        self.current_weapon = 0
        self.delete_interval = 2
        self.delete_last_action_time = 0

    def add_item_toThe_Inventory(self, item, kind):
        if kind == "potion":
            self.potion_inventory.append(item)
        elif kind == "weapon":
            self.wep_inventory.append(item)

    def items_hendeling(self, player):
        if not self.is_wep_empty():
            self.wep_inventory[self.current_weapon].draw(WIDTH / 2, HEIGHT / 2)

    def open(self, group, player):
        self.display.blit(self.image, self.rect)
        prect=player.rect
        for i, wep in enumerate(self.wep_inventory):
            wep.draw_for_inventory(i, self.rect.x, self.rect.y)
        for i, potion in enumerate(self.potion_inventory):
            potion.draw_for_inventory(i, self.rect.x, self.rect.y, )

        self.use(group, prect)
        self.use_potion(player)

    def is_wep_empty(self):
        return len(self.wep_inventory) == 0

    def is_potion_empty(self):
        return len(self.potion_inventory) == 0

    def use(self, group, prect):
        keys = pygame.key.get_pressed()
        for i in range(10):
            key_constant = getattr(pygame, f"K_{i}")
            if keys[key_constant] and i - 1 != self.current_weapon and i - 1 < len(self.wep_inventory):
                self.current_weapon = i - 1
        if keys[pygame.K_DELETE]:
            self.delete_w(group, prect)

    def drop_all_items(self, group, prect):

        import random

        for weapon in self.wep_inventory:
            x = prect.centerx + random.randint(-120, 120)
            y = prect.centery + random.randint(-120, 120)

            Colectible_sprite((x, y), group, weapon.get_name(), "weapon")

        for potion in self.potion_inventory:
            x = prect.centerx + random.randint(-120, 120)
            y = prect.centery + random.randint(-120, 120)

            Colectible_sprite((x, y), group, potion.get_name(), "potion")

        self.wep_inventory.clear()
        self.potion_inventory.clear()


    def delete_w(self, group, prect):
        current_time = time.time()
        if current_time - self.delete_last_action_time >= self.delete_interval and self.is_wep_empty() == False:
            Colectible_sprite((prect.x + 70, prect.y + 70), group, self.wep_inventory[self.current_weapon].get_name(),
                              "weapon")
            del self.wep_inventory[self.current_weapon]
            if self.current_weapon != 0:
                self.current_weapon = self.current_weapon - 1
            self.delete_last_action_time = current_time

    def use_potion(self, player):
        keys = pygame.key.get_pressed()
        if keys[pygame.K_p]:
            for i in range(10):
                key_constant = getattr(pygame, f"K_{i}")
                if keys[key_constant] and i - 1 < len(self.potion_inventory) and self.potion_inventory[
                    i - 1].is_potion_is == False:
                    print("hii")
                    self.potion_inventory[i - 1].purpose(player)
        for i in range(10):
            if i < len(self.potion_inventory) and not self.is_potion_empty():
                if self.potion_inventory[i].should_it_stop(player):
                    del self.potion_inventory[i]
