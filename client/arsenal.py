from typing import Any

import pygame
import math
from functools import cache

from weapon_anim import WeaponAnim


class Arsenal:
    Arsenal_gunType = {  # image directory & ttl of the bullet & relative offset from the player
        "Ak 47": ("arsenal-images/guns/Ak 47.png",
                 12,
                 "AK 47 bullets",
                 "not fixed",
                 (15, 47),  # relative offset from the player
                 120,  # scale
                 15,  # magzin
                 250,  # fire_cooldown in ms (0.25s)
                 (40, 26),  #rotating point

                  [(0, 0)]  # spawn points (multy shot)
                 ),

        "bow": ("arsenal-images/guns/bow.png",
                1,
                "arrows",
                "not fixed",
                (30, 30),  # relative offset from the player
                30,  # scale
                3,  # magzin
                500,  # fire_cooldown
                (25, 40),  #rotating point

                [(0, 0), (0, -60), (0, 60)]  # spawn points (multy shot)
                ),
        "sword": ("arsenal-images/guns/sword.png",
                  1,
                  "sword hit",
                  "fixed",
                  (60, -35),  # relative offset from the player
                  30,  # scale
                  1000,  # magzin
                  1000,  # fire_cooldown
                  (0, 0),  #rotating point

                  [(0, 0)]  # spawn points (multy shot)
                  ),
        "Assault rifle":
                ("arsenal-images/guns/Assault rifle.png",
                 24,
                  "Assault rifle bullets",
                  "not fixed",
                  (10, 35),  # relative offset from the player
                  130,  # scale
                  30,  # magzin
                  100,  # fire_cooldown
                 (35, 26), #rotating point

                 [(0, 0)]  # spawn points (multy shot)
                  ),
        "Pistol":
            ("arsenal-images/guns/Pistol.png",
             12,
             "Pistol bullets",
             "not fixed",
             (26, 28),  # relative offset from the player
             100,  # scale
             10,  # magzin
             100,  # fire_cooldown
             (25, 25), #rotating point

             [(0, 0)]  # spawn points (multy shot)
             )
    }

    @staticmethod
    def bullet_from_gun(gun_type: str, default_fmt='{}_bullet') -> str:
        if gun := Arsenal.Arsenal_gunType.get(gun_type):
            return gun[2]  # index 1 -> bullet type
        return default_fmt.format(gun_type)

    @staticmethod
    @cache
    def get_weapon_img(gun_type: str) -> pygame.Surface:
        path = Arsenal.Arsenal_gunType[gun_type][0]
        return pygame.image.load(path).convert_alpha()

    @staticmethod
    def _cut_weapon_frames(sheet: pygame.Surface, frames: int) -> list[Any]:
        # spritesheet
        sheet_w, sheet_h = sheet.get_size()
        frame_w = sheet_w // frames
        out = []

        for i in range(frames):
            x = i * frame_w
            frame = pygame.Surface((frame_w, sheet_h), pygame.SRCALPHA).convert_alpha()
            frame.blit(sheet, (0, 0), (x, 0, frame_w, sheet_h))
            out.append(frame)

        return out

    def GetBulletType(self):
        return self.bullet

    def __init__(self, gun_type):
        # gun type - type of the gun c:
        self.display = pygame.display.get_surface()
        self.gun_type = gun_type
        self.weapon_path,self.img_num, self.bullet, self.movement, coordinates, self.scale, self.mag, self.fire_cooldown,self.pivot,self.spawn_points = \
            Arsenal.Arsenal_gunType[gun_type]
        
        self.weapon_img = Arsenal.get_weapon_img(gun_type)
        self.smaller_v = pygame.transform.scale(self.weapon_img, (30, 30))
        self.offset_x, self.offset_y = coordinates

        self.rect = self.weapon_img.get_rect()

        #weapon animation
        self.weapon_frames = None
        self.weapon_anim_playing = False
        self.weapon_frame_i = 0
        self.weapon_last_time = pygame.time.get_ticks()
        self.weapon_speed_ms = 30

        if self.img_num and self.img_num > 1:
            self.weapon_frames = self._cut_weapon_frames(self.weapon_img, self.img_num)


    def refill_mag(self):
        weapon_path,img_num, bullet, movement, coordinates, scale, mag, fire_cooldown,pivot = Arsenal.Arsenal_gunType[self.gun_type]
        self.mag = mag

    def draw(self, player_x, player_y):
        weapon_img_src = self.weapon_img

        if self.weapon_frames:
            if self.weapon_anim_playing:
                now = pygame.time.get_ticks()
                if now - self.weapon_last_time >= self.weapon_speed_ms:
                    self.weapon_last_time = now
                    self.weapon_frame_i += 1
                    if self.weapon_frame_i >= len(self.weapon_frames):
                        self.weapon_frame_i = 0
                        self.weapon_anim_playing = False

            weapon_img_src = self.weapon_frames[self.weapon_frame_i]

        offset_x = self.offset_x
        offset_y=self.offset_y
        # drowing the gun with angle
        if self.movement == "not fixed":
            mouse_x, mouse_y = pygame.mouse.get_pos()

            w, h = weapon_img_src.get_size()
            weapon_img_src = pygame.transform.scale(
                weapon_img_src, (self.scale, int(h * (self.scale / w))))

            if mouse_x < player_x:
                weapon_img_src = pygame.transform.flip(weapon_img_src, False, True)

                offset_x = self.offset_x*-1


            if mouse_y < player_y and mouse_x>player_x:
                offset_x,offset_y =offset_x+4,offset_y-11

            if mouse_y < player_y and mouse_x<player_x :
                offset_x,offset_y =offset_x-7,offset_y-11


            x_r, y_r = mouse_x - player_x, mouse_y - player_y
            angle = -math.degrees(math.atan2(y_r, x_r))

        else:
            w, h = weapon_img_src.get_size()
            weapon_img = pygame.transform.scale(
                weapon_img_src, (self.scale, int(h * (self.scale / w))))

            if self.gun_type == "sword":
                angle = 360 - 45
            else:
                angle = 0

        # DEBUG

        #debug_img = weapon_img_src.copy()
        #pygame.draw.circle(debug_img, (255, 0, 0), self.pivot, 5)
        #self.display.blit(debug_img, (50, 50))


        w, h = weapon_img_src.get_size()
        scale_ratio = self.scale / w

        weapon_img = pygame.transform.scale(
            weapon_img_src,
            (self.scale, int(h * scale_ratio))
        )

        #center of rotation
        pivot = pygame.math.Vector2(
            self.pivot[0] * scale_ratio,
            self.pivot[1] * scale_ratio
        )

        hand_pos = pygame.math.Vector2(
            player_x + offset_x,
            player_y + offset_y
        )

        image_rect = weapon_img.get_rect()
        center = pygame.math.Vector2(image_rect.center)
        pivot_offset = pivot - center

        rotated_offset = pivot_offset.rotate(-angle)

        rotated_image = pygame.transform.rotate(weapon_img, angle)

        new_center = hand_pos - rotated_offset
        rotated_rect = rotated_image.get_rect(center=new_center)

        self.display.blit(rotated_image, rotated_rect)

    def draw_for_inventory(self, i, low_x, low_y):
        if i >= 10:
            return

        # imag
        img = None
        if getattr(self, "weapon_frames", None):
            if 0 <= self.weapon_frame_i < len(self.weapon_frames):
                img = self.weapon_frames[self.weapon_frame_i]
        if img is None:
            img = self.weapon_img
        if img is None:
            return

        # ---------------slot settings---------------
        slot_w = 30
        slot_h = 30
        gap = 3
        x0 = low_x + 10
        y0 = low_y + 20
        padding = 2
        # -------------------------------------------

        slot_rect = pygame.Rect(
            x0 + i * (slot_w + gap),
            y0,
            slot_w,
            slot_h
        )

        target_w = slot_rect.w - padding * 2
        target_h = slot_rect.h - padding * 2

        iw, ih = img.get_size()
        if iw <= 0 or ih <= 0:
            return

        scale = min(target_w / iw, target_h / ih)
        new_size = (max(1, int(iw * scale)), max(1, int(ih * scale)))

        scaled = pygame.transform.smoothscale(img, new_size)
        draw_rect = scaled.get_rect(center=slot_rect.center)
        self.display.blit(scaled, draw_rect)


    def get_image(self):
        return self.weapon_img

    def get_name(self):
        return self.gun_type

    def on_fire(self):
        if self.weapon_frames:
            self.weapon_anim_playing = True
            self.weapon_frame_i = 0
            self.weapon_last_time = pygame.time.get_ticks()

    def draw_mag_stat(self):
        x = 300
        y = 705

        if not self.bullet == "null":
            bullet_left = self.mag

            offset_x = 0

            font = pygame.font.SysFont(None, 36)
            bullet_left_txt = font.render(str(bullet_left), True, 'black')
            x -= bullet_left_txt.get_width()

            from client import game
            game.SCREEN.blit(bullet_left_txt, (x + offset_x, y))
            x-=10
            img_bullet = pygame.image.load(
                "arsenal-images/bullets/" + f"{self.bullet}.png").convert_alpha()

            img_bullet = pygame.transform.rotate(img_bullet, 90 * 3)

            w, h = img_bullet.get_size()
            if self.bullet=="arrows": scale = 8
            else: scale = 15

            img_bullet = pygame.transform.scale(
                img_bullet, (scale, int(h * (scale / w))))

            self.display.blit(img_bullet, (x-img_bullet.get_width()+5 + offset_x, y - 15))
            return
        else:
            weapon_img = self.weapon_img
            w, h = weapon_img.get_size()
            scale = 35
            weapon_img = pygame.transform.scale(
                weapon_img, (scale, int(h * (scale / w))))

            self.display.blit(weapon_img, (x - w / 2, y))