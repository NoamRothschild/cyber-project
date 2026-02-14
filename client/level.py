from client.inventory import *
from mapset import *
from player import *
from tile import Rock
from client.colectibes import Colectible_sprite

pygame.init()


class level:
    Domain_Expansion_ls = []

    def __init__(self):
        self.display_surface = pygame.display.get_surface()

        self.visible_sprites = Camera()
        self.obstacle_sprites = pygame.sprite.Group()
        self.colectible_sprite = pygame.sprite.Group()

        self.draw_map()

    def handle_event(self, event):
        self.player.shop_ui.handle_event(event, self.player)

    def draw_map(self):
        for rindex, row in enumerate(world_map):
            for cindex, col in enumerate(row):
                x = cindex * size
                y = rindex * size
                if col == 'x':
                    Rock((x, y), [self.visible_sprites, self.obstacle_sprites])
                if col == 't':
                    Colectible_sprite((x, y), [self.visible_sprites, self.colectible_sprite], "Ak-7", "weapon")
                if col == 'c':
                    Colectible_sprite((x, y), [self.visible_sprites, self.colectible_sprite], "speed", "potion")
                if col == 'p':
                    self.player = Player((x, y), [self.visible_sprites], self.obstacle_sprites)

    def run(self):
        self.visible_sprites.custom_draw(self.player)

        self.player.inventory.items_hendeling(self.player)

        self.visible_sprites.update(self.colectible_sprite)


class Camera(pygame.sprite.Group):
    def __init__(self):
        super().__init__()
        self.display = pygame.display.get_surface()
        self.half_width = self.display.get_width() / 2
        self.half_height = self.display.get_height() / 2
        self.point = pygame.math.Vector2()

    def custom_draw(self, player):
        self.point.x = player.rect.centerx - self.half_width
        self.point.y = player.rect.centery - self.half_height
        for sprite in self.sprites():
            point_pos = sprite.rect.center - self.point
            self.display.blit(sprite.image, point_pos)
