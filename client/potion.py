import pygame
import time
from helth import HealthBar
from mapset import *
from functools import cache
from random import randint


class Potion(pygame.sprite.Sprite):
    # Start with None. We will load the images safely AFTER the window is created.
    potions = None

    @classmethod
    def load_assets(cls):
        if cls.potions is None:
            # We only load these the first time a potion is requested
            cls.potions = {
                "healing": (pygame.image.load("Potion/super_health.png").convert_alpha(),
                            "health_bar", 15, 15),
                "speed": (pygame.image.load("Potion/speed.png").convert_alpha(),
                          "speed", 10, 1),
                "super_speed": (pygame.image.load("Potion/super_speed.png").convert_alpha(),
                                "speed", 40, 10)
            }

    def __init__(self, potion_type):
        super().__init__()
        # Ensure the assets are loaded before we try to use them!
        Potion.load_assets()

        self.potion_type = potion_type
        # Safely grab the surface here, inside the init!
        self.display_surface = pygame.display.get_surface()

        self.image, self.what, self.how_much, self.ttl = Potion.potions[potion_type]
        self.image = pygame.image.load(self.image).convert_alpha()
        self.smaller_v = pygame.transform.scale(self.image, (30, 30))
        self.is_potion_is = False
        self.delete_last_action_time = time.time()
        self.health = HealthBar((0, 0), 30)
        if id==0:
            self.id=randint(0, 2**31 - 1)
        else:
            self.id=id

    @staticmethod
    def get_potion_img(potion: str) -> pygame.Surface:
        Potion.load_assets()
        image, what, how_much, ttl  = Potion.potions[potion]
        return image

    @staticmethod
    def effect_time(potion: str) -> int:
        Potion.load_assets()
        image, what, how_much, ttl = Potion.potions[potion]
        return how_much

    def draw_for_inventory(self, i, low_x, low_y):
        if (i < 10):
            self.display_surface.blit(self.smaller_v, (low_x + i * 31 + 369, low_y + 20))

    def get_image(self):
        return self.image

    def get_name(self):
        return self.potion_type

    def purpose(self, player):
        """doing the potion purpose"""
        if self.what == "health_bar":
            player.health.add_life(self.how_much)

            Green_hit.start()
            if self.is_potion_is == False:
                self.is_potion_is = True
                self.last_heal = time.time()
                self.delete_last_action_time = self.last_heal
        elif self.what == "gold":
            if self.is_potion_is == False:
                self.is_potion_is = True
                self.last_heal = time.time()
                self.delete_last_action_time = self.last_heal
                self.lg=player.inventory.money
            else:
                player.inventory.money += (player.inventory.money-self.lg)*self.how_much-(player.inventory.money-self.lg)
                self.lg = player.inventory.money

            print("aaa bbb kdkds")
            print(player.inventory.money-self.lg*self.how_much)
        elif self.what == "speed":
            player.speed += self.how_much
            self.old_speed = player.speed
            self.is_potion_is = True
            self.delete_last_action_time = time.time()
    def creat_bar(self,i,pos):
        low_x,low_y = pos
        self.health.move((low_x + i * 31 + 370, low_y-self.health.height))
        self.health.draw()
        self.delete_last_bar_sub=time.time()

    def should_it_stop(self, player):
        """checking if the potion should stop its purpose"""
        if self.is_potion_is == True and self.ttl != None:
            current_time = time.time()
            if (self.what != "speed" and current_time - self.last_heal >= 1):
                self.last_heal = current_time
                self.purpose(player)
            elif current_time - self.delete_last_action_time > self.ttl:
                if self.what == "speed":
                    player.speed -= self.how_much
                self.delete_last_action_time = current_time
                return True
            elif current_time - self.delete_last_bar_sub > 1:
                self.health.sub_life(30/self.ttl)

                self.delete_last_bar_sub = current_time
            self.health.draw()
        return False
