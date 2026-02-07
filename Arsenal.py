import pygame
import math
from Game import *
from Game import Game


#need to add bullet class (new TTL - time to live of the bullet - need to despond after some time every gun will be having different ttl )

class Arsenal:
    #     USE example
    #     weapon = Arsenal("Ak-7")
    #     weapon.draw(SCREEN, player.x, player.y)
    Arsenal_gunType = {  # image directory & ttl of the bullet & relative offset from the player
        "Ak-7": (pygame.image.load("arsenal-images/guns/Ak1.png").convert_alpha(),
                 "AK-7_bullet",
                 "not fixed",
                 (15, 30), # relative offset from the player
                 70, #scale
                 15, #magzin
                 250 #fire_cooldown in ms (0.25s)
                 ),

        "rock": (pygame.image.load("rock.png").convert_alpha(),
                 "null",
                 "not fixed",
                 (4, 32), # relative offset from the player
                 20, #scale
                 0,#magzin
                 -1 #fire_cooldown
                 ),

        "bow": (pygame.image.load("arsenal-images/guns/bow.png").convert_alpha(),
                "arrow",
                "not fixed",
                (15, 30),  # relative offset from the player
                15, #scale
                5, #magzin
                1000 #fire_cooldown
                ),
        "domain_expansion": (pygame.image.load("arsenal-images/guns/domainExp.png").convert_alpha(),
                "DE_power",
                "fixed",
                (25, 30),  # relative offset from the player
                35, #scale
                5, #magzin
                1000 #fire_cooldown
            )
        }

    def __init__(self, gun_type):
        #gun type - type of the gun c:
        self.gun_type=gun_type
        self.weapon,self.bullet,self.movement,coordinates,self.scale,self.mag,self.fire_cooldown =Arsenal.Arsenal_gunType[gun_type]
        self.weapon.set_colorkey((23, 130, 184))
        self.smaller_v = pygame.transform.scale(self.weapon, (30, 30))
        self.offset_x, self.offset_y = coordinates

    def refill_mag(self):
        weapon,bullet,fixed,coordinates,scale,mag,fire_cooldown =Arsenal.Arsenal_gunType[self.gun_type]
        self.mag=mag

    def draw_for_inventory(self, i, low_x, low_y):
        if (i < 10):
            Game.SCREEN.blit(self.smaller_v, (low_x + i * 31 + 10, low_y + 20))

    def draw(self, player_x, player_y):
        #drowing the gun with angle
        if self.movement=="not fixed":
            mouse_x, mouse_y = pygame.mouse.get_pos()
            weapon = self.weapon

            w,h = weapon.get_size()
            weapon = pygame.transform.scale(weapon, (self.scale, int(h *(self.scale/w) )))

            weapon = pygame.transform.flip(weapon, True, False)
            if mouse_x < player_x:
                weapon = pygame.transform.flip(weapon, False, True)

            x_r,y_r = mouse_x - player_x, mouse_y - player_y
            angle = -math.degrees(math.atan2(y_r, x_r))

        else:
            w, h = self.weapon.get_size()
            weapon = pygame.transform.scale(self.weapon, (self.scale, int(h * (self.scale / w))))
            angle=0

        rotated = pygame.transform.rotate(weapon, angle)

        #draw
        rect = rotated.get_rect(center=(player_x + self.offset_x, player_y + self.offset_y))
        Game.SCREEN.blit(rotated, rect.topleft)

    def get_image(self):
        return self.weapon
    def get_name(self):
        return self.gun_type