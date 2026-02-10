from entity import Entities

from player import *
from tile import Rock
from PIL import Image


class Level:
    def __init__(self):
        self.display_surface = pygame.display.get_surface()

        self.visible_sprites = Camera()
        self.obstacle_sprites = pygame.sprite.Group()
        self.harmfull_sprites = pygame.sprite.Group()

        self.image = [pygame.image.load('rock.png').convert(), pygame.image.load('tree.png').convert(),
                      pygame.image.load('water.png').convert()]

        self.entities = Entities()

        self.draw_map()

    def draw_map(self):  # crating a very basic map with small borders(need to be changed
        self.map_image = Image.open("map.png")

        pixels = self.map_image.load()
        width, height = self.map_image.size
        tree_count = 0

        for x in range(width):
            for y in range(height):

                pixel = pixels[x, y]
                r, g, b = pixel[:3]

                if r == 0 and g == 162 and b == 232:
                    Rock((x * SIZE, y * SIZE), [self.visible_sprites, self.obstacle_sprites], self.image[2], 'water')
                elif r == 120 and g == 67 and b == 21:
                    Rock((x * SIZE, y * SIZE), [self.visible_sprites, self.obstacle_sprites], self.image[0], "rock")
                elif r == 24 and g == 62 and b == 12:
                    if tree_count % 1 == 0:
                        Rock((x * SIZE, y * SIZE), [self.visible_sprites, self.obstacle_sprites, self.harmfull_sprites],
                             self.image[1], "tree")
                    tree_count += 1

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
        screen_rect = pygame.Rect(self.point.x, self.point.y, self.display.get_width(), self.display.get_height())
        visible_now = [s for s in self.sprites() if s.rect.colliderect(screen_rect)]

        for sprite in sorted(visible_now, key=lambda s: s.rect.bottom):
            if sprite.image is not None:
                self.display.blit(sprite.image, sprite.rect.topleft - self.point)
            elif sprite.plus_rect is not None:
                sprite.draw(self.point.x, self.point.y)
