import pygame
from mapset import *
import time


class HealthBar(pygame.sprite.Sprite):
    def __init__(self,pos,scale,groups=None) -> None:
        if groups is not None:
            super().__init__(groups)
        self.height = scale//10
        self.width = scale
        self.rect = pygame.Rect(pos[0],pos[1],self.width,self.height)

        self.screen = pygame.display.get_surface()
        self.plus_rect = pygame.Rect(pos[0],pos[1], self.width, self.height)
        x, y = self.plus_rect.topright
        self.minus_rect = pygame.Rect(x, y, 0, self.height)
        self.shield_time = 0.5
        self.last_sub_life = time.time()

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
        # TODO: add a red flash effect when getting hit
        current_time = time.time()

        if current_time - self.last_sub_life >= self.shield_time:
            if num > self.plus_rect.width:
                num = abs(0 - self.plus_rect.width)
            self.plus_rect.width -= num
            self.minus_rect.width += num
            self.minus_rect.x = self.plus_rect.x + self.plus_rect.width
            self.last_sub_life = current_time

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
