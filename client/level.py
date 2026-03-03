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

map_for_d = {}
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

                world_pos = (x * SIZE, y * SIZE)
                grid_pos = (x, y)
                s = None

                if r == 0 and g == 162 and b == 232:
                    ground_count = 0
                    s=Rock(world_pos, self.image[2], 'water', [ self.obstacle_sprites])
                elif r == 120 and g == 67 and b == 21:
                    ground_count = 0
                    s=Rock(world_pos, self.image[0], "rock", [ self.obstacle_sprites])
                    map_for_d[(x, y)] = self.image[0]
                elif r == 24 and g == 62 and b == 12:
                    if tree_count % 7 == 0:
                        t=get_trees()
                        s=Rock(world_pos,
                             t, "tree", [self.obstacle_sprites,self.harmfull_sprites])

                    else:
                        s=Rock(world_pos,
                             self.image[1], "tree", [self.obstacle_sprites,self.harmfull_sprites])
                    tree_count += 1
                    ground_count = 0
                else:
                    ground_count += 1
                    if random.randint(0,BUSH_FRIQWENTY) == 1 :
                        b=get_bushes()
                        s=Rock(world_pos,b, " ")
                if s is not None:
                    map_for_d[grid_pos] = s
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
        # 1. עדכון המצלמה
        self.point.x = player.rect.centerx - self.half_width
        self.point.y = player.rect.centery - self.half_height

        # חישוב גבולות הגריד פעם אחת
        start_x = int(self.point.x // SIZE)
        end_x = int((self.point.x + self.view_width) // SIZE) + 1
        start_y = int(self.point.y // SIZE)
        end_y = int((self.point.y + self.view_height) // SIZE) + 1

        # 2. איסוף אובייקטים (ללא colliderect מיותר על המפה הסטטית)
        visible_now = []

        # אובייקטים מהמפה
        for x in range(start_x, end_x):
            for y in range(start_y, end_y):
                item = map_for_d.get((x, y))
                if item and item.rect and item.rect.bottom : visible_now.append(item)

        # אובייקטים דינמיים (הקבוצה הזו קטנה ממילא)
        for item in self.sprites():
            if item and item.rect and item.rect.bottom: visible_now.append(item)

        # 3. לולאת ציור ללא חישובים כבדים
        # אנחנו ממיינים פעם אחת ומציירים
        for sprite in sorted(visible_now, key=lambda s: s.rect.bottom):
            view_offset_x = (sprite.rect.x - self.point.x) * self.scale_x
            view_offset_y = (sprite.rect.y - self.point.y) * self.scale_y

            if hasattr(sprite, 'image') and sprite.image:
                # --- אופטימיזציה קריטית: שימוש ב-scaled_image מוכן מראש ---
                # אם אין לספרייט תמונה מוקטנת, או שהקנה מידה השתנה - רק אז נחשב
                if not hasattr(sprite, 'cached_scale') or sprite.cached_scale != (self.scale_x, self.scale_y):
                    sw = max(1, int(sprite.rect.width * self.scale_x))
                    sh = max(1, int(sprite.rect.height * self.scale_y))
                    sprite.scaled_image = pygame.transform.scale(sprite.image, (sw, sh))
                    sprite.cached_scale = (self.scale_x, self.scale_y)

                self.display.blit(sprite.scaled_image, (view_offset_x, view_offset_y))

            elif hasattr(sprite, 'plus_rect'):
                sprite.draw(self.point.x, self.point.y)

        # 4. ייעול ה-Grid (שימוש בטווחים שכבר חישבנו)
        self._draw_optimized_grid(start_x, end_x, start_y, end_y)
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

    def _draw_optimized_grid(self, start_x, end_x, start_y, end_y):
        # המרת הקואורדינטות של המפה לקואורדינטות של ה-Nodes
        # (בהנחה ש-NODE_WIDTH הוא כפולה של SIZE)
        for nx in range(int(self.point.x // NODE_WIDTH), int((self.point.x + self.view_width) // NODE_WIDTH) + 1):
            for ny in range(int(self.point.y // NODE_HEIGHT),
                            int((self.point.y + self.view_height) // NODE_HEIGHT) + 1):
                screen_x = (nx * NODE_WIDTH - self.point.x) * self.scale_x
                screen_y = (ny * NODE_HEIGHT - self.point.y) * self.scale_y
                screen_w = NODE_WIDTH * self.scale_x
                screen_h = NODE_HEIGHT * self.scale_y

                pygame.draw.rect(self.display, self.node_box_color,
                                 (screen_x, screen_y, screen_w, screen_h), self.node_box_thickness)
