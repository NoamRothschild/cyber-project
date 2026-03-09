from entity import Entities
import pygame
import mapset
from player import *
from tile import Rock
from colectibes import Colectible_sprite
from PIL import Image
import random
import os
from chat import *

colors = ["GREEN", "YELLOWISH GREEN", "RED"]
ALL_BUSH_IMAGES = []
ALL_TREE_IMAGES = []
BUSH_FRIQWENTY = 30

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
                ALL_TREE_IMAGES.append(img)
            except Exception as e:
                print(f"Error: {e}")

def get_trees():
    if ALL_TREE_IMAGES:
        return random.choice(ALL_TREE_IMAGES)
    return None

def preload_all_bushes():
    for n in range(1, 15):
        for color in colors:
            path = f"Pixel Art Bush Pack/Bush {n}/Bush {n}_{color}.png"
            img = pygame.image.load(path).convert_alpha()
            img = pygame.transform.scale(img, (90, 90))
            ALL_BUSH_IMAGES.append(img)

def get_bushes():
    return random.choice(ALL_BUSH_IMAGES)


class Level:

    def __init__(self):
        self.display_surface = pygame.display.get_surface()

        self.visible_sprites = Camera()
        self.obstacle_sprites = pygame.sprite.Group()
        self.colectible_sprite = pygame.sprite.Group()
        self.harmfull_sprites = pygame.sprite.Group()

        self.image = [pygame.image.load('rock.png').convert(),
                      pygame.image.load('tree.png').convert(),
                      pygame.image.load('water.png').convert()]
        self.chat = Chat()
        self.entities = Entities()
        preload_all_bushes()
        preload_all_trees()
        self.draw_map()

    def handle_event(self, event):
        self.player.shop_ui.handle_event(event, self.player)
        self.chat.handle_event(event)
        self.player.auto_move.handle_event(event)   # ← AutoMove key handler
        if event.type == pygame.K_z:
            self.chat.add_external_message("ai alon")

    def draw_map(self):
        self.map_image = Image.open("map.png")
        pixels = self.map_image.load()
        width, height = self.map_image.size

        # ── Build world_map for AutoMove (all walkable for now, obstacles added after) ──
        grid = []
        for y in range(height):
            row = []
            for x in range(width):
                r, g, b = pixels[x, y][:3]
                if r == 0 and g == 162 and b == 232:
                    row.append("w")   # water — not walkable
                elif r == 120 and g == 67 and b == 21:
                    row.append("r")   # rock  — not walkable
                else:
                    row.append(" ")   # ground + trees — walkable (hitbox based below)
            grid.append(row)
        mapset.world_map[:] = grid
        # ─────────────────────────────────────────────────────────────

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
                        Rock((x * SIZE, y * SIZE),
                             [self.visible_sprites, self.obstacle_sprites, self.harmfull_sprites],
                             get_trees(), "tree")
                    else:
                        Rock((x * SIZE, y * SIZE),
                             [self.visible_sprites, self.obstacle_sprites, self.harmfull_sprites],
                             self.image[1], "tree")
                    tree_count += 1
                    ground_count = 0
                else:
                    ground_count += 1
                    if random.randint(0, BUSH_FRIQWENTY) == 1:
                        Rock((x * SIZE + SIZE / 2, y * SIZE + SIZE / 2),
                             [self.visible_sprites], get_bushes(), " ", " ")

        # ── Mark obstacle tiles based on ACTUAL hitboxes ──────────────
        self._mark_obstacle_tiles()
        # ─────────────────────────────────────────────────────────────

        self.player = Player([self.visible_sprites],
                             [self.obstacle_sprites, self.harmfull_sprites, self.colectible_sprite])

    def _mark_obstacle_tiles(self):
        """Walk every obstacle sprite and mark its hitbox tiles as blocked."""
        for sprite in self.obstacle_sprites:
            hb = sprite.hitbox
            # convert hitbox pixel rect to tile range
            c0 = hb.left   // mapset.SIZE
            c1 = hb.right  // mapset.SIZE
            r0 = hb.top    // mapset.SIZE
            r1 = hb.bottom // mapset.SIZE
            for r in range(r0, r1 + 1):
                for c in range(c0, c1 + 1):
                    if 0 <= r < len(mapset.world_map) and 0 <= c < len(mapset.world_map[0]):
                        mapset.world_map[r][c] = "x"  # blocked

    def run(self):
        self.visible_sprites.custom_draw(self.player)
        self.visible_sprites.update(self.chat.is_open)
        self.chat.draw()


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
        screen_rect = pygame.Rect(self.point.x, self.point.y, WIDTH, HEIGHT)
        visible_now = [s for s in self.sprites()
                       if hasattr(s.rect, 'colliderect') and s.rect.colliderect(screen_rect)]

        for sprite in sorted(visible_now, key=lambda s: s.rect.bottom):
            if hasattr(sprite, 'image') and sprite.image is not None:
                self.display.blit(sprite.image, sprite.rect.topleft - self.point)
            elif hasattr(sprite, 'plus_rect') and sprite.plus_rect is not None:
                sprite.draw(self.point.x, self.point.y)