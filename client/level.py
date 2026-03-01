from entity import Entities
import pygame
from player import *
from tile import Rock
from colectibes import Colectible_sprite
from PIL import Image
from mapset import (
    WIDTH,
    HEIGHT,
    VIEW_WIDTH,
    VIEW_HEIGHT,
    VIEW_SCALE_X,
    VIEW_SCALE_Y,
    SCREEN_SCALE_X,
    SCREEN_SCALE_Y,
    NODE_WIDTH,
    NODE_HEIGHT,
    VERTICAL_NODE_COUNT,
    HORIZONAL_NODE_COUNT,
)
import random
import os
from chat import *
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
    Domain_Expansion_ls = []

    def __init__(self,session_id):
        self.display_surface = pygame.display.get_surface()

        self.visible_sprites = Camera()
        self.obstacle_sprites = pygame.sprite.Group()
        self.colectible_sprite = pygame.sprite.Group()
        self.harmfull_sprites = pygame.sprite.Group()

        self.image = [pygame.image.load('rock.png').convert(), pygame.image.load('tree.png').convert(),
                      pygame.image.load('water.png').convert()]
        self.chat=Chat(session_id)
        self.entities = Entities()
        preload_all_bushes()
        preload_all_trees()
        self.draw_map()

    def handle_event(self, event):
        self.player.shop_ui.handle_event(event, self.player)
        self.chat.handle_event(event)
        if event.type == pygame.K_z:
            self.chat.add_external_message("ai alon")
    def draw_map(self):  # crating a very basic map with small borders(need to be changed
        # Ensure the map is in RGB so each pixel is an (r, g, b) tuple.
        self.map_image = Image.open("map.png").convert("RGB")

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
                        Rock((x * SIZE, y * SIZE), [self.visible_sprites, self.obstacle_sprites,self.harmfull_sprites],
                             get_trees(), "tree")

                    else:
                        Rock((x * SIZE, y * SIZE), [self.visible_sprites, self.obstacle_sprites,self.harmfull_sprites],
                             self.image[1], "tree")
                    tree_count += 1
                    ground_count = 0
                else:
                    ground_count += 1
                    if random.randint(0,BUSH_FRIQWENTY) == 1 :
                        Rock((x * SIZE+SIZE/2, y * SIZE+SIZE/2), [self.visible_sprites],get_bushes(), " "," ")


        self.player = Player( [self.visible_sprites],
                             [self.obstacle_sprites, self.harmfull_sprites,self.colectible_sprite])

    def run(self):
        self.visible_sprites.custom_draw(self.player)

        self.player.inventory.items_hendeling(self.player)

        self.visible_sprites.update(self.chat.is_open)
        self.chat.draw()
        Green_hit.draw_fill()
        Red_hit.draw_fill()

class Camera(pygame.sprite.Group):  # a group that has every visible sprite that should be moved when the player does
    def __init__(self):
        super().__init__()
        self.display = pygame.display.get_surface()
        self.view_width = VIEW_WIDTH
        self.view_height = VIEW_HEIGHT
        self.half_width = self.view_width / 2
        self.half_height = self.view_height / 2
        self.point = pygame.math.Vector2()
        self.scale_x = SCREEN_SCALE_X
        self.scale_y = SCREEN_SCALE_Y
        # Light green, bold node bounding boxes
        self.node_box_color = (144, 238, 144)
        self.node_box_thickness = 4

    def custom_draw(self, player):
        self.point.x = player.rect.centerx - self.half_width
        self.point.y = player.rect.centery - self.half_height
        screen_rect = pygame.Rect(self.point.x, self.point.y, self.view_width, self.view_height)
        visible_now = [s for s in self.sprites() if hasattr(s, 'rect') and s.rect.colliderect(screen_rect)]

        for sprite in sorted(visible_now, key=lambda s: s.rect.bottom):
            if hasattr(sprite, 'image') and sprite.image is not None:
                view_offset = sprite.rect.topleft - self.point
                screen_x = view_offset[0] * self.scale_x
                screen_y = view_offset[1] * self.scale_y
                scaled_w = max(1, int(sprite.rect.width * self.scale_x))
                scaled_h = max(1, int(sprite.rect.height * self.scale_y))
                scaled_image = pygame.transform.scale(sprite.image, (scaled_w, scaled_h))
                self.display.blit(scaled_image, (screen_x, screen_y))
            elif hasattr(sprite, 'plus_rect') and sprite.plus_rect is not None:
                sprite.draw(self.point.x, self.point.y)

        # Draw bold light-green bounding boxes around all visible region nodes
        self._draw_region_node_grid()

        # Draw a centered red border box that mimics the original (unscaled)
        # WIDTH x HEIGHT viewport within the currently zoomed-out view.
        box_w = WIDTH / VIEW_SCALE_X
        box_h = HEIGHT / VIEW_SCALE_Y
        box_x = (WIDTH - box_w) / 2
        box_y = (HEIGHT - box_h) / 2

        # Inner "must see" viewport
        pygame.draw.rect(
            self.display,
            (255, 0, 0),
            pygame.Rect(box_x, box_y, box_w, box_h),
            3,
        )

        # Outer, slightly larger viewport (1.5x the size) with a thinner stroke
        outer_w = box_w * 1.5
        outer_h = box_h * 1.5
        outer_x = (WIDTH - outer_w) / 2
        outer_y = (HEIGHT - outer_h) / 2

        pygame.draw.rect(
            self.display,
            (255, 128, 128),
            pygame.Rect(outer_x, outer_y, outer_w, outer_h),
            2,
        )

    def _draw_region_node_grid(self):
        # Current camera view in world coordinates
        view_rect = pygame.Rect(self.point.x, self.point.y, self.view_width, self.view_height)

        for node_x in range(HORIZONAL_NODE_COUNT):
            for node_y in range(VERTICAL_NODE_COUNT):
                world_rect = pygame.Rect(
                    node_x * NODE_WIDTH,
                    node_y * NODE_HEIGHT,
                    NODE_WIDTH,
                    NODE_HEIGHT,
                )

                if not world_rect.colliderect(view_rect):
                    continue

                # Convert world rect to screen space using the same scaling as sprites
                view_offset_x = world_rect.x - self.point.x
                view_offset_y = world_rect.y - self.point.y
                screen_x = view_offset_x * self.scale_x
                screen_y = view_offset_y * self.scale_y
                screen_w = world_rect.width * self.scale_x
                screen_h = world_rect.height * self.scale_y

                pygame.draw.rect(
                    self.display,
                    self.node_box_color,
                    pygame.Rect(screen_x, screen_y, screen_w, screen_h),
                    self.node_box_thickness,
                )
