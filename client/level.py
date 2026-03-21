from entity import Entities
import pygame
import mapset
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
from nodes import fetch_zone_map, pos_to_zone_index
import random
import os
from chat import *

colors = ["GREEN", "YELLOWISH GREEN", "RED"]
ALL_BUSH_IMAGES = []
ALL_TREE_IMAGES=[]
BUSH_FRIQWENTY=7

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

    def __init__(self,session_id):
        self.display_surface = pygame.display.get_surface()

        self.visible_sprites = Camera()
        self.obstacle_sprites = pygame.sprite.Group()
        self.colectible_sprite = pygame.sprite.Group()
        self.harmfull_sprites = pygame.sprite.Group()

        self.image = [pygame.image.load('rock.png').convert(),
                      pygame.image.load('tree.png').convert(),
                      pygame.image.load('water.png').convert()]
        self.chat=Chat(session_id)
        self.entities = Entities()
        self.zone_map = fetch_zone_map()
        self.current_zone_index: int | None = None
        self.current_host: str | None = None

        preload_all_bushes()
        preload_all_trees()
        self.draw_map()
    def add_c(self,pos,n,k,id):
        c=Colectible_sprite(pos,[self.visible_sprites,self.colectible_sprite],n,k,id)
    def handle_event(self, event):
        self.player.shop_ui.handle_event(event, self.player)
        self.chat.handle_event(event)
        self.player.auto_move.handle_event(event)   # ← AutoMove key handler
        if event.type == pygame.K_z:
            self.chat.add_external_message("ai alon")
    def draw_map(self):  # crating a very basic map with small borders(need to be changed
        # Ensure the map is in RGB so each pixel is an (r, g, b) tuple.
        self.map_image = Image.open("map.png").convert("RGB")

        pixels = self.map_image.load()
        width, height = self.map_image.size

        # ── Build world_map for AutoMove (all walkable for now, obstacles added after) ──
        grid = []
        for y in range(height):
            row = []
            for x in range(width):
                r, g, b = pixels[x, y][:3]
                if r == 0 and g == 162 and b == 232:
                    row.append(None)  # water — not walkable
                elif r == 120 and g == 67 and b == 21:
                    row.append(None)  # rock  — not walkable
                else:
                    row.append(None)  # ground + trees — walkable (hitbox based below)
            grid.append(row)
        mapset.world_map[:] = grid
        # ─────────────────────────────────────────────────────────────
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
                             t, "tree", [self.obstacle_sprites])

                    else:
                        s=Rock(world_pos,
                             self.image[1], "tree", [self.obstacle_sprites])
                    tree_count += 1
                    ground_count = 0
                else:
                    ground_count += 1
                    if x%BUSH_FRIQWENTY==0 and y%BUSH_FRIQWENTY==0:
                        b=get_bushes()
                        s=Rock(world_pos,b, " ")
                if s is not None:
                    map_for_d[grid_pos] = s
        # ── Mark obstacle tiles based on ACTUAL hitboxes ──────────────
        self._mark_obstacle_tiles()
        # ─────────────────────────────────────────────────────────────

        self.player = Player( [self.visible_sprites],
                             [self.obstacle_sprites, self.harmfull_sprites,self.colectible_sprite])

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
                        mapset.world_map[r][c] = hb

    def run(self):
        self.visible_sprites.custom_draw(self.player)

        self.player.inventory.items_hendeling(self.player)

        self.entities.cleanup_dead()
        self.visible_sprites.update(self.chat.is_open)
        self.chat.draw()
        Green_hit.draw_fill()
        Red_hit.draw_fill()

        self._check_zone_change()

    def _check_zone_change(self):
        hb = self.player.hitbox
        zone_index = pos_to_zone_index(hb.x, hb.y)
        if zone_index == self.current_zone_index:
            return
        self.current_zone_index = zone_index
        host = self.zone_map.get(zone_index)
        if host is None or host == self.current_host:
            self.current_host = host
            return
        self.current_host = host
        from zone_connection import ZoneConnectionSingleton
        ZoneConnectionSingleton.move_zone(host)
        print(f"[ZONE] Switched to host {host} (zone index {zone_index})")



class Camera(pygame.sprite.Group):
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
                if item and hasattr(item, 'rect') and item.rect and item.rect.bottom : visible_now.append(item)

        # אובייקטים דינמיים (הקבוצה הזו קטנה ממילא)
        for item in self.sprites():
            if item and hasattr(item, 'rect') and item.rect and item.rect.bottom: visible_now.append(item)

        # 3. לולאת ציור ללא חישובים כבדים
        # אנחנו ממיינים פעם אחת ומציירים
        for sprite in sorted(visible_now, key=lambda s: s.rect.bottom):
            view_offset_x = (sprite.rect.x - self.point.x) * self.scale_x
            view_offset_y = (sprite.rect.y - self.point.y) * self.scale_y

            if hasattr(sprite, 'image') and sprite.image:
                self.display.blit(sprite.image, (view_offset_x, view_offset_y))

            elif hasattr(sprite, 'plus_rect'):
                if getattr(sprite, '_hidden', False):
                    continue
                sprite.draw(self.point.x, self.point.y)

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
