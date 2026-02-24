import pygame
import math
from mapset import SCREEN_SCALE_X, SCREEN_SCALE_Y


#need to add bullet class (new TTL - time to live of the bullet - need to despond after some time every gun will be having different ttl )

class Arsenal:
    #     USE example
    #     weapon = Arsenal("Ak-7")
    #     weapon.draw(SCREEN, player.x, player.y)
    
    # image path & bullet type & relative offset from the player
    Arsenal_gunType = {
        "Ak-7": ("arsenal-images/guns/Ak1.png",
                 "Ak-7_bullet",
                 (15, 30))  # relative offset from the player
    }

    def GetBulletType(self):
        return self.Bullet

    def __init__(self, gun_type):
        # gun type - type of the gun
        image_path, self.Bullet, coordinates = Arsenal.Arsenal_gunType[gun_type]
        # load and convert only after display is initialized
        self.weapon = pygame.image.load(image_path).convert_alpha()
        self.weapon.set_colorkey((23, 130, 184))

        self.offset_x, self.offset_y = coordinates

    def draw(self, player_x, player_y):
        #drowing the gun with angle (scaled to match zoomed view)
        mouse_x, mouse_y = pygame.mouse.get_pos()
        weapon = self.weapon

        scale = 0.1
        w, h = weapon.get_size()
        scaled_w = max(1, int(w * scale * SCREEN_SCALE_X))
        scaled_h = max(1, int(h * scale * SCREEN_SCALE_Y))
        weapon = pygame.transform.scale(weapon, (scaled_w, scaled_h))

        weapon = pygame.transform.flip(weapon, True, False)
        if mouse_x < player_x:
            weapon = pygame.transform.flip(weapon, False, True)

        x_r, y_r = mouse_x - player_x, mouse_y - player_y
        angle = -math.degrees(math.atan2(y_r, x_r))
        rotated = pygame.transform.rotate(weapon, angle)

        # draw (offset scaled to match view)
        offset_x = self.offset_x * SCREEN_SCALE_X
        offset_y = self.offset_y * SCREEN_SCALE_Y
        rect = rotated.get_rect(center=(player_x + offset_x, player_y + offset_y))
        screen = pygame.display.get_surface()
        screen.blit(rotated, rect.topleft)