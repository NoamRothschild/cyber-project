import pygame, math
from game import *
import os
import sys

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def draw_AND_update_Bullets(player):
    # Derive camera scroll exactly like Camera.custom_draw does:
    display = pygame.display.get_surface()
    scroll = [
        player.rect.centerx - display.get_width() / 2,
        player.rect.centery - display.get_height() / 2,
    ]

    # Iterate over a copy so we can safely remove expired bullets
    for bullet in list(Bullets.BulletLS):
        if bullet.ttl <= 0:
            Bullets.BulletLS.remove(bullet)
            continue

        bullet.update()
        bullet.draw(scroll)


blue=(23, 130, 184)
class Bullets:
    BulletLS = []

    bullet_types = {
        "AK 47 bullets": (
            pygame.image.load(resource_path("arsenal-images/bullets/AK 47 bullets.png")).convert_alpha(),
            (-15, 15), 20, 25, 40, 0.1
        ),
        "Assault rifle bullets": (
            pygame.image.load(resource_path("arsenal-images/bullets/AK 47 bullets.png")).convert_alpha(),
            (-15, 15), 15, 30, 25, 0.1
        ),
        "Pistol bullets": (
            pygame.image.load(resource_path("arsenal-images/bullets/AK 47 bullets.png")).convert_alpha(),
            (-15, 15), 10, 19, 30, 0.1
        ),
        "arrows": (
            pygame.image.load(resource_path("arsenal-images/bullets/arrows.png")).convert_alpha(),
            (-15, 5), 50, 30, 40, 1
        ),
        "sword hit": (
            pygame.image.load(resource_path("arsenal-images/bullets/sword hit.png")).convert_alpha(),
            (-15, 5), 1, 20, 60, 0.3
        )
    }

    def __init__(
        self,
        bullet_type: str,
        player_x: float,
        player_y: float,
        mouse_x: float | None = None,
        mouse_y: float | None = None,
        angle: float | None = None,
        scroll=None,
        from_network: bool = False,
    ):
        self.display_surface = pygame.display.get_surface()

        self.image_bullet, coordinates, self.ttl, self.speed, self.damage, self.scale = self.bullet_types[bullet_type]
        self.offset_x, self.offset_y = coordinates

        # Scale and set transparency
        w, h = self.image_bullet.get_size()
        self.image_bullet = pygame.transform.scale(
        self.image_bullet, (int(w * self.scale), int(h * self.scale)))

        self.image_bullet = pygame.transform.flip(self.image_bullet, True, False)
        self.rect = self.image_bullet.get_rect()
        if from_network:
            # Network bullet: we must have an angle; x/y are already world-space.
            if angle is None:
                raise ValueError("Network bullets require 'angle'")


            # From the network we already receive world coordinates and an angle.
            # Treat player_x / player_y as world-space bullet coordinates.
            self.offset_x = 0
            self.offset_y = 0
            self.x = float(player_x)
            self.y = float(player_y)
            self.angle = float(angle)
        else:
            # Local bullet: scroll + mouse are required to compute direction.
            if scroll is None or len(scroll) < 2:
                raise ValueError("Local bullets require a valid 'scroll'")
            if mouse_x is None or mouse_y is None:
                raise ValueError("Local bullets require mouse_x and mouse_y")

            # Local bullet: start at player center in world space and aim at mouse.
            # Player position is provided in screen-space (center of the screen).
            player_screen_x = float(player_x)
            player_screen_y = float(player_y)

            # Convert player position to world-space by applying the current scroll.
            player_world_x = player_screen_x + scroll[0]
            player_world_y = player_screen_y + scroll[1]
            self.x = player_world_x
            self.y = player_world_y

            # If the mouse is to the right of the player, we shift the bullet sprite so it
            # appears to come out of the right side of the weapon.
            if mouse_x > player_x:
                self.offset_x += 60

            # Mouse position is also in screen-space; convert it to world-space.
            mouse_world_x = float(mouse_x + scroll[0])
            mouse_world_y = float(mouse_y + scroll[1])

            # Direction vector from bullet start to the mouse position in world-space.
            dx = mouse_world_x - self.x
            dy = mouse_world_y - self.y

            # Angle and velocity components.
            self.angle = math.atan2(dy, dx)

        self.velocity_x = math.cos(self.angle) * self.speed
        self.velocity_y = math.sin(self.angle) * self.speed

    def update(self):
        # Move bullet in world-space according to its velocity.
        self.x += self.velocity_x
        self.y += self.velocity_y
        self.ttl -= 1

    def draw(self, scroll):
        # Convert world-space bullet position to screen-space.
        screen_x = self.x - scroll[0]
        screen_y = self.y - scroll[1]

        # Apply the sprite offset so the bullet appears relative to the weapon.
        bullet_center_x = screen_x + self.offset_x
        bullet_center_y = screen_y + self.offset_y

        rotated = pygame.transform.rotate(
            self.image_bullet, -math.degrees(self.angle)
        )
        rect = rotated.get_rect(center=(bullet_center_x, bullet_center_y))
        self.display_surface.blit(rotated, rect.topleft)
