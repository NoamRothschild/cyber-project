from entity import Entities
import pygame
from player import *
from tile import Rock
from PIL import Image
import random
import os
colors = ["GREEN", "YELLOWISH GREEN", "RED"]
ALL_BUSH_IMAGES = []
ALL_TREE_IMAGES=[]
BUSH_FRIQWENTY=30
def preload_all_trees():
    folder_path = "Pixel Trees"
    if not os.path.exists(folder_path):
        return

    for filename in os.listdir(folder_path):
        if filename.lower().endswith(".png"):
            path = os.path.join(folder_path, filename)
            try:
                img = pygame.image.load(path).convert_alpha()
                img = pygame.transform.scale(img, (SIZE, SIZE))
                # --- התיקון כאן: לשמור ברשימת העצים ---
                ALL_TREE_IMAGES.append(img)
            except Exception as e:
                print(f"Error: {e}")

def get_trees():
    # --- התיקון כאן: לשלוף מרשימת העצים ---
    if ALL_TREE_IMAGES:
        return random.choice(ALL_TREE_IMAGES)
    return None
def preload_all_bushes():
    for n in range(1, 15):
        for color in colors:
            path = f"Pixel Art Bush Pack/Bush {n}/Bush {n}_{color}.png"
            img = pygame.image.load(path).convert_alpha()
            # אם אתה עושה scale של 0.2, עדיף לעשות אותו כאן פעם אחת
            img = pygame.transform.scale(img, (90,90))
            ALL_BUSH_IMAGES.append(img)

def get_bushes():

    return random.choice(ALL_BUSH_IMAGES)
class Level:
    def __init__(self):
        self.display_surface = pygame.display.get_surface()

        self.visible_sprites = Camera()
        self.obstacle_sprites = pygame.sprite.Group()
        self.harmfull_sprites = pygame.sprite.Group()

        self.image = [pygame.image.load('rock.png').convert(), pygame.image.load('tree.png').convert(),
                      pygame.image.load('water.png').convert()]

        self.entities = Entities()
        preload_all_bushes()
        preload_all_trees()
        self.draw_map()

    def draw_map(self):  # crating a very basic map with small borders(need to be changed
        self.map_image = Image.open("map.png")

        pixels = self.map_image.load()
        width, height = self.map_image.size
        tree_count = 0
        ground_count = 0
        for x in range(width):
            for y in range(height):

                pixel = pixels[x, y]
                r, g, b = pixel[:3]

                if r == 0 and g == 162 and b == 232:
                    ground_count = 0
                    Rock((x * SIZE, y * SIZE), [self.visible_sprites, self.obstacle_sprites], self.image[2], 'water')
                elif r == 120 and g == 67 and b == 21:
                    ground_count = 0
                    Rock((x * SIZE, y * SIZE), [self.visible_sprites, self.obstacle_sprites], self.image[0], "rock")
                elif r == 24 and g == 62 and b == 12:
                    if tree_count % 7 == 0:
                        Rock((x * SIZE, y * SIZE), [self.visible_sprites, self.obstacle_sprites],
                             get_trees(), "tree")

                    else:
                        Rock((x * SIZE, y * SIZE), [self.visible_sprites, self.obstacle_sprites],
                             self.image[1], "tree")
                    tree_count += 1
                    ground_count = 0
                else:
                    ground_count += 1
                    if random.randint(0,BUSH_FRIQWENTY) == 1 :
                        Rock((x * SIZE+SIZE/2, y * SIZE+SIZE/2), [self.visible_sprites],get_bushes(), " "," ")


        self.player = Player((370 * SIZE, 163 * SIZE), [self.visible_sprites],
                             [self.obstacle_sprites, self.harmfull_sprites])

    def run(self):
        self.visible_sprites.custom_draw(self.player)

        self.player.inventory.items_hendeling(self.player)

        self.visible_sprites.update()

class Camera(pygame.sprite.Group):  # a group that has every visible sprite that should be moved when the player does
    def __init__(self):
        super().__init__()
        self.display = pygame.display.get_surface()
        self.half_width = self.display.get_width() / 2
        self.half_height = self.display.get_height() / 2
        self.point = pygame.math.Vector2()

    def custom_draw(self, player):
        self.point.x = player.rect.centerx - self.half_width
        self.point.y = player.rect.centery - self.half_height
        screen_rect = pygame.Rect(self.point.x, self.point.y, WIDTH, HEIGHT)
        visible_now = [s for s in self.sprites() if hasattr(s.rect, 'colliderect') and s.rect.colliderect(screen_rect)]

        for sprite in sorted(visible_now, key=lambda s: s.rect.bottom):
            if hasattr(sprite, 'image') and sprite.image is not None:
                self.display.blit(sprite.image, sprite.rect.topleft - self.point)
            elif hasattr(sprite, 'plus_rect') and sprite.plus_rect is not None:
                sprite.draw(self.point.x, self.point.y)
