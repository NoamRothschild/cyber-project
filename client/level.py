import pygame

from Entity import Entities
from mapset import *
from Player import *
from Rock import Rock
from PIL import Image
class level:
    def __init__(self):
        self.display_surface = pygame.display.get_surface()

        self.visible_sprites = Camera()
        self.obstacle_sprites = pygame.sprite.Group()

        self.image = [pygame.image.load('rock.png').convert_alpha(), pygame.image.load('tree.png').convert_alpha(),
                      pygame.image.load('water.png').convert_alpha()]

        self.entities = Entities()

        self.draw_map()

    def draw_map(self):#crating a very basic map with small borders(need to be changed
        self.map_image = Image.open("map.png")
        pixels = self.map_image.load()
        width, height = self.map_image.size
        tree_count = 0

        for x in range(width):
            for y in range(height):
                # בדיקה אם יש ערוץ אלפא (RGBA) או רק RGB
                pixel = pixels[x, y]
                r, g, b = pixel[:3]

                if r == 0 and g == 162 and b == 232:
                    Rock((x * size, y * size), [self.visible_sprites, self.obstacle_sprites], self.image[2])
                elif r == 120 and g == 67 and b == 21:
                    Rock((x * size, y * size), [self.visible_sprites, self.obstacle_sprites], self.image[0])
                elif r == 24 and g == 62 and b == 12:
                    if tree_count % 7 == 0:
                        Rock((x * size, y * size), [self.visible_sprites, self.obstacle_sprites], self.image[1])
                    tree_count += 1

        # השחקן נוצר פעם אחת בלבד - מחוץ ללולאה
        self.player = Player((640 * size, 260 * size), [self.visible_sprites], self.obstacle_sprites)


    def run(self):
        self.visible_sprites.custom_draw(self.player)

        self.visible_sprites.update()

class Camera(pygame.sprite.Group):# a group that has every visible sprite that should be moved when the player does
    def __init__(self):
        super().__init__()
        self.display = pygame.display.get_surface()
        self.half_width = self.display.get_width()/2
        self.half_height = self.display.get_height()/2
        self.point=pygame.math.Vector2()

    def custom_draw(self,player):
        self.point.x=player.rect.centerx-self.half_width
        self.point.y=player.rect.centery-self.half_height
        screen_rect = pygame.Rect(self.point.x, self.point.y, self.display.get_width(), self.display.get_height())

        for sprite in self.sprites():
            if sprite.rect.colliderect(screen_rect):
                point_pos= sprite.rect.topleft-self.point
                self.display.blit(sprite.image,point_pos)
