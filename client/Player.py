import pygame
from Inventory import *
from Bullets import *
from Bullets import Bullets
from game import *
from zone_connection import ZoneConnectionSingleton

PINK=(234,54,128)



class Player(pygame.sprite.Sprite):
    def __init__(self, pos, groups,obstacle_sprites):
        super().__init__(groups)
        self.display_surface = pygame.display.get_surface()

        self.image = pygame.image.load('player.png').convert_alpha()
        self.image.set_colorkey(PINK)
        self.rect = self.image.get_rect(topleft=pos)
        self.hitbox = self.rect.inflate(-20,-10)
        self.speed = 4
        self.direction = pygame.math.Vector2()
        self.obstacle_sprites = obstacle_sprites
        self.inventory = Inventory()



    def input(self):
        keys = pygame.key.get_pressed()

        if keys[pygame.K_UP] or keys[pygame.K_w]:
            self.direction.y = -1

        elif keys[pygame.K_DOWN]or keys[pygame.K_s]:
            self.direction.y = 1
        else:
            self.direction.y=0

        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.direction.x=-1

        elif keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.direction.x=1
        else:
            self.direction.x=0

        mouse_buttons = pygame.mouse.get_pressed()
        if mouse_buttons[0]:  # 0 = קליק שמאלי
            mouse_x, mouse_y = pygame.mouse.get_pos()

            gun_type = "Ak-7" # NOTE: REPLACE ME
            count = 1 # NOTE: REPLACE ME

            # Camera scroll is derived the same way as in Camera.custom_draw:
            # center the camera on this player's rect.
            scroll = [
                self.rect.centerx - self.display_surface.get_width() / 2,
                self.rect.centery - self.display_surface.get_height() / 2,
            ]

            bullet = Bullets(
                "Ak-7_bullet",
                self.display_surface.get_width() / 2,
                self.display_surface.get_height() / 2,
                mouse_x=mouse_x,
                mouse_y=mouse_y,
                scroll=scroll,
                from_network=False,
            )

            ZoneConnectionSingleton().zone.try_send_bullet(gun_type, bullet.angle, count)
            Bullets.BulletLS.append(bullet)

    def move(self):
        if self.direction.magnitude()!=0:
            self.direction=self.direction.normalize()
        self.hitbox.x += int(self.direction.x*self.speed)
        self.check_coalition("horizontal")
        self.hitbox.y += int(self.direction.y*self.speed)
        self.check_coalition("vertical")
        self.rect.center=self.hitbox.center

    def check_coalition(self,direction):
        if direction=='horizontal':
            for sprite in self.obstacle_sprites:
                if sprite.rect.colliderect(self.hitbox):
                    if self.direction.x>0:
                        self.hitbox.right=sprite.rect.left
                    elif self.direction.x<0:
                        self.hitbox.left=sprite.rect.right
        if direction=='vertical':
            for sprite in self.obstacle_sprites:
                if sprite.rect.colliderect(self.hitbox):
                    if self.direction.y>0:
                        self.hitbox.bottom=sprite.rect.top
                    elif self.direction.y<0:
                        self.hitbox.top=sprite.rect.bottom

    def update(self):
        self.input()
        draw_AND_update_Bullets(self)

        self.move()
        self.inventory.open()
