import pygame, math
from Game import *



def draw_AND_update_Bullets():
    for bullet in Bullets.BulletLS:
        if bullet.ttl <= 0:
            Bullets.BulletLS.remove(bullet)
        bullet.update()
        bullet.draw()

class Bullets:
    BulletLS=[]
    def __init__(self, bullet_type, player_x, player_y, mouse_x, mouse_y):
        self.display_surface = pygame.display.get_surface()
        self.bullet_types = {
            "AK-7_bullet": (
                pygame.image.load("arsenal-images/bullets/bullet-AK7.png").convert_alpha(),
                (-15, -15),  # relative offset from the player
                50,  # ttl
                40,    # speed
                4,     # damage
                0.2 #scale
            )
        }

        self.image_bullet,coordinates, self.ttl, self.speed,self.damage,self.scale = self.bullet_types[bullet_type]
        self.offset_x, self.offset_y = coordinates


        w, h = self.image_bullet.get_size()
        self.image_bullet = pygame.transform.scale(self.image_bullet, (int(w * self.scale), int(h * self.scale)))
        self.image_bullet.set_colorkey((23, 130, 184))

        if mouse_x > player_x:
            self.offset_x+=60

        self.x = float(player_x)
        self.y = float(player_y)
        print("bullet",self.x, " ", self.y)
        world_mx = mouse_x
        world_my = mouse_y

        self.angle = math.atan2(world_my - self.y, world_mx - self.x)
        self.x_v = math.cos(self.angle) * self.speed
        self.y_v = math.sin(self.angle) * self.speed

    def update(self):
        self.x += self.x_v
        self.y += self.y_v
        self.ttl -= 1

    def draw(self):
        rotated = pygame.transform.rotate(self.image_bullet, -math.degrees(self.angle))
        rect = rotated.get_rect(center=(self.x+self.offset_x, self.y + self.offset_y))
        self.display_surface.blit(rotated, rect.topleft)
