import pygame
import math
from functools import cache

# need to add bullet class (new TTL - time to live of the bullet - need to despond after some time every gun will be having different ttl )


class Arsenal:
    #     USE example
    #     weapon = Arsenal("Ak-7")
    #     weapon.draw(SCREEN, player.x, player.y)
    Arsenal_gunType = {  # image directory & ttl of the bullet & relative offset from the player
        "Ak-7": ("arsenal-images/guns/Ak1.png",
                 "AK-7_bullet",
                 "not fixed",
                 (0, 27),  # relative offset from the player
                 70,  # scale
                 15,  # magzin
                 250  # fire_cooldown in ms (0.25s)
                 ),

        "rock": ("rock.png",
                 "null",
                 "fixed",
                 (4, 32),  # relative offset from the player
                 20,  # scale
                 0,  # magzin
                 -1  # fire_cooldown
                 ),

        "bow": ("arsenal-images/guns/bow.png",
                "arrow",
                "not fixed",
                (-10, 20),  # relative offset from the player
                22,  # scale
                5,  # magzin
                500  # fire_cooldown
                ),
        "sword": ("arsenal-images/guns/sword.png",
                  "arrow",
                  "fixed",
                  (-5, 12),  # relative offset from the player
                  100,  # scale
                  10,  # magzin
                  10  # fire_cooldown
                  )
    }

    @staticmethod
    def bullet_from_gun(gun_type: str, default_fmt='{}_bullet') -> str:
        if gun := Arsenal.Arsenal_gunType.get(gun_type):
            return gun[1]  # index 1 -> bullet type
        return default_fmt.format(gun_type)

    @staticmethod
    @cache
    def get_weapon_img(gun_type: str) -> pygame.Surface:
        path = Arsenal.Arsenal_gunType[gun_type][0]
        return pygame.image.load(path).convert_alpha()

    def GetBulletType(self):

        return self.bullet

    def __init__(self, gun_type):
        # gun type - type of the gun c:
        self.display = pygame.display.get_surface()
        self.gun_type = gun_type
        self.weapon_path, self.bullet, self.movement, coordinates, self.scale, self.mag, self.fire_cooldown = \
            Arsenal.Arsenal_gunType[gun_type]
        
        self.weapon_img = Arsenal.get_weapon_img(gun_type)
        self.weapon_img.set_colorkey((23, 130, 184))
        self.smaller_v = pygame.transform.scale(self.weapon_img, (30, 30))
        self.offset_x, self.offset_y = coordinates

        self.rect = self.weapon_img.get_rect()

    def refill_mag(self):
        weapon_path, bullet, movement, coordinates, scale, mag, fire_cooldown = Arsenal.Arsenal_gunType[
            self.gun_type]
        self.mag = mag

    def draw_for_inventory(self, i, low_x, low_y):
        if (i < 10):
            self.display.blit(
                self.smaller_v, (low_x + i * 31 + 10, low_y + 20))

    def draw(self, player_x, player_y):
        # drowing the gun with angle
        if self.movement == "not fixed":
            mouse_x, mouse_y = pygame.mouse.get_pos()
            weapon_img = self.weapon_img

            w, h = weapon_img.get_size()
            weapon_img = pygame.transform.scale(
                weapon_img, (self.scale, int(h * (self.scale / w))))

            weapon_img = pygame.transform.flip(weapon_img, True, False)

            if mouse_x < player_x:
                weapon_img = pygame.transform.flip(weapon_img, False, True)

            x_r, y_r = mouse_x - player_x, mouse_y - player_y
            angle = -math.degrees(math.atan2(y_r, x_r))

        else:
            w, h = self.weapon_img.get_size()
            weapon_img = pygame.transform.scale(
                self.weapon_img, (self.scale, int(h * (self.scale / w))))

            if self.gun_type == "sword":
                angle = 360 - 45
            else:
                angle = 0

        rotated = pygame.transform.rotate(weapon_img, angle)

        # draw
        rect = rotated.get_rect(
            center=(player_x + self.offset_x, player_y + self.offset_y))
        self.display.blit(rotated, rect.topleft)

    def get_image(self):
        return self.weapon_img

    def get_name(self):
        return self.gun_type

    def draw_mag_stat(self):
        x = 300
        y = 705

        if not self.bullet == "null":
            bullet_left = self.mag
            numLs = []
            while bullet_left > 0:
                numLs.append(bullet_left % 10)
                bullet_left //= 10

            if len(numLs) == 0:
                numLs = [0]

            offset_x = 0

            for num in numLs:
                img_num = pygame.image.load(
                    "numbers-image/" + f"{num}.png").convert_alpha()
                img_num.set_colorkey((23, 130, 184))
                img_num = pygame.transform.scale(img_num, (17, 18))

                self.display.blit(img_num, (x + offset_x, y))
                offset_x -= img_num.get_width()

            offset_x -= 10

            img_bullet = pygame.image.load(
                "arsenal-images/bullets/" + f"{self.bullet}.png").convert_alpha()
            img_bullet.set_colorkey((23, 130, 184))

            img_bullet = pygame.transform.rotate(img_bullet, 90 * 3)

            w, h = img_bullet.get_size()
            scale = 15
            img_bullet = pygame.transform.scale(
                img_bullet, (scale, int(h * (scale / w))))

            self.display.blit(img_bullet, (x + offset_x, y - 15))
            return
        else:
            weapon_img = self.weapon_img
            w, h = weapon_img.get_size()
            scale = 35
            weapon_img = pygame.transform.scale(
                weapon_img, (scale, int(h * (scale / w))))

            self.display.blit(weapon_img, (x - w / 2, y))
