import pygame, math
from Game import *

def draw_AND_update_Bullets(player):
    for bullet in Bullets.BulletLS:
        if bullet.ttl <= 0:
            Bullets.BulletLS.remove(bullet)
        bullet.update()
        bullet.draw(player.screen_scroll)

class Bullets:
    BulletLS=[]
    def __init__(self, weapon, player_x, player_y, mouse_x, mouse_y,scroll):
        self.display_surface = pygame.display.get_surface()

        self.bullet_types = {
            "AK-7_bullet": (
                pygame.image.load("arsenal-images/bullets/bullet-AK7.png").convert_alpha(),
                (-15,5),  # relative offset from the player
                20,  # ttl
                20,    # speed
                2,     # damage
                0.15 #scale
            ),
            "arrow":(
                pygame.image.load("arsenal-images/bullets/arrow.png").convert_alpha(),
                (-15, 5),  # relative offset from the player
                50,  # ttl
                10,  # speed
                5,  # damage
                1  # scale
            )
        }

        self.image_bullet,coordinates, self.ttl, self.speed,self.damage,self.scale = self.bullet_types[weapon.bullet]
        self.offset_x, self.offset_y = coordinates


        w, h = self.image_bullet.get_size()
        self.image_bullet=pygame.transform.flip(self.image_bullet, True, False)
        self.image_bullet = pygame.transform.scale(self.image_bullet, (int(w * self.scale), int(h * self.scale)))
        self.image_bullet.set_colorkey((23, 130, 184))

        if mouse_x > player_x:
            self.offset_x+=60

        self.x = float(player_x + scroll[0])
        self.y = float(player_y + scroll[1])
        world_mx = mouse_x + scroll[0]
        world_my = mouse_y + scroll[1]

        self.angle = math.atan2(world_my - self.y, world_mx - self.x)
        self.x_v = math.cos(self.angle) * self.speed
        self.y_v = math.sin(self.angle) * self.speed

    def update(self):
        self.x += self.x_v
        self.y += self.y_v
        self.ttl -= 1

    def draw(self,scroll):
        rotated = pygame.transform.rotate(self.image_bullet, -math.degrees(self.angle))
        rect = rotated.get_rect(center=(self.x - scroll[0]+self.offset_x, self.y - scroll[1]+ self.offset_y))
        self.display_surface.blit(rotated, rect.topleft)
