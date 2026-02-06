import pygame
import math
from game import *


#need to add bullet class (new TTL - time to live of the bullet - need to despond after some time every gun will be having different ttl )

class Arsenal:
    #     USE example
    #     weapon = Arsenal("Ak-7")
    #     weapon.draw(SCREEN, player.x, player.y)
    Arsenal_gunType = {  # image directory & ttl of the bullet & relative offset from the player
        "Ak-7": (pygame.image.load("arsenal-images/guns/Ak1.png").convert_alpha(),
                 "Ak-7_bullet",
                 (15, 30))  # relative offset from the player
    }

    def GetBulletType(self):
        self.weapon, self.Bullet, coordinates = Arsenal.Arsenal_gunType[self]
        return self.Bullet

    def __init__(self, gun_type):
        #gun type - type of the gun c:

        self.weapon,self.Bullet,coordinates =Arsenal.Arsenal_gunType[gun_type]
        self.weapon.set_colorkey((23, 130, 184))

        self.offset_x, self.offset_y = coordinates

    def draw(self, player_x, player_y):
        #drowing the gun with angle
        mouse_x, mouse_y = pygame.mouse.get_pos()
        weapon = self.weapon

        scale = 0.1
        w,h = weapon.get_size()
        weapon = pygame.transform.scale(weapon, (int(w * scale), int(h * scale)))

        weapon = pygame.transform.flip(weapon, True, False)
        if mouse_x < player_x:
            weapon = pygame.transform.flip(weapon, False, True)

        x_r,y_r = mouse_x - player_x, mouse_y - player_y
        angle = -math.degrees(math.atan2(y_r, x_r))
        rotated = pygame.transform.rotate(weapon, angle)

        #draw
        rect = rotated.get_rect(center=(player_x + self.offset_x, player_y + self.offset_y))
        Game.SCREEN.blit(rotated, rect.topleft)