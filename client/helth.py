import pygame
from mapset import *
import time

class HealthBar(pygame.sprite.Sprite):
     def __init__(self):
         self.height = 40
         self.width = 400
         pygame.sprite.Sprite.__init__(self)
         self.screen = pygame.display.get_surface()
         self.plus_rect = pygame.Rect(WIDTH-self.width-10, 10,  self.width,self.height)
         x,y=self.plus_rect.topright
         self.minus_rect = pygame.Rect(x,y, self.width-400,self.height)
         self.shield_time=1
         self.last_sub_life=time.time()
     def draw(self):
        pygame.draw.rect(self.screen, (0, 255, 0), self.plus_rect)
        pygame.draw.rect(self.screen, (255, 0, 0), self.minus_rect)
     def sub_life(self, num):
         current_time = time.time()

         if current_time - self.last_sub_life >= self.shield_time:
            if num>self.plus_rect.width:
                 num = abs(0 - self.plus_rect.width)
            self.plus_rect.width -= num
            self.minus_rect.width += num
            self.minus_rect.x=self.plus_rect.x+self.plus_rect.width
            self.last_sub_life = current_time


     def add_life(self, num):
         if num>self.minus_rect.width:
             num=abs(0-self.minus_rect.width)
         self.plus_rect.width +=num
         self.minus_rect.width -=num
         self.minus_rect.x = self.plus_rect.x + self.plus_rect.width

     def is_alive(self):
         return self.plus_rect.width>0