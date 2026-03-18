import pygame

from zone_connection import ZoneConnectionSingleton
from mapset import *

class HealthBar(pygame.sprite.Sprite):
    def __init__(self,pos,scale,groups=None) -> None:
        if groups is not None:
            super().__init__(groups)
        self.height = scale//10
        if self.height < 5:
            self.height = 5
        self.width = scale
        self.rect = pygame.Rect(pos[0],pos[1],self.width,self.height)

        self.screen = pygame.display.get_surface()
        self.plus_rect = pygame.Rect(pos[0],pos[1], self.width, self.height)
        x, y = self.plus_rect.topright
        self.minus_rect = pygame.Rect(x, y, 0, self.height)

    def draw(self,x=None,y=None):

        if x is not None and y is not None:
            plus_draw_rect = self.plus_rect.move(-x, -y)
            minus_draw_rect = self.minus_rect.move(-x, -y)

            pygame.draw.rect(self.screen, (0, 255, 0), plus_draw_rect)
            pygame.draw.rect(self.screen, (255, 0, 0), minus_draw_rect)
        else:
            pygame.draw.rect(self.screen, (0, 255, 0), self.plus_rect)
            pygame.draw.rect(self.screen, (255, 0, 0), self.minus_rect)

    def get_life(self):
        return self.plus_rect.width

    def sub_life(self, num):
        if num > self.plus_rect.width:
            num = self.plus_rect.width
        self.plus_rect.width -= num
        self.minus_rect.width += num
        self.minus_rect.x = self.plus_rect.x + self.plus_rect.width

    def add_life(self, num):
        if num > self.minus_rect.width:
            num = abs(0 - self.minus_rect.width)
        self.plus_rect.width += num
        self.minus_rect.width -= num
        self.minus_rect.x = self.plus_rect.x + self.plus_rect.width

    def move(self,pos):
        self.plus_rect.x = pos[0]
        self.plus_rect.y = pos[1]
        self.minus_rect.x = self.plus_rect.x + self.plus_rect.width
        self.minus_rect.y = pos[1]

    def is_alive(self):
        return self.plus_rect.width > 0

    def set_life(self, num):
        # A direct override for loading from the database.
        # It bypasses the shield and hit effects.

        # Clamp the database numbers just in case of glitches
        if num > 400:
            num = 400
        if num < 0:
            num = 0

        self.plus_rect.width = num
        self.minus_rect.width = 400 - num
        self.minus_rect.x = self.plus_rect.x + self.plus_rect.width

    def set_absolute(self, current_width: int):
        """Set the bar fill to current_width (0 to self.width). Used for fixed-width bars driven by hp/max_hp."""
        current_width = max(0, min(current_width, self.width))
        self.plus_rect.width = current_width
        self.minus_rect.width = self.width - current_width
        self.minus_rect.x = self.plus_rect.x + self.plus_rect.width
