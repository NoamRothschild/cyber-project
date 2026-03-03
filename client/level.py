from entity import Entities

from player import *
from tile import Rock
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


class Level:
    def __init__(self):
        self.display_surface = pygame.display.get_surface()

        self.visible_sprites = Camera()
        self.obstacle_sprites = pygame.sprite.Group()
        self.harmfull_sprites = pygame.sprite.Group()

        self.image = [pygame.image.load('rock.png').convert(), pygame.image.load('tree.png').convert(),
                      pygame.image.load('water.png').convert()]

        self.entities = Entities()
        self.zone_map = fetch_zone_map()
        self.current_zone_index: int | None = None
        self.current_host: str | None = None

        self.draw_map()

    def draw_map(self):  # crating a very basic map with small borders(need to be changed
        # Ensure the map is in RGB so each pixel is an (r, g, b) tuple.
        self.map_image = Image.open("map.png").convert("RGB")

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
            view_offset = sprite.rect.topleft - self.point
            screen_x = view_offset[0] * self.scale_x
            screen_y = view_offset[1] * self.scale_y
            scaled_w = max(1, int(sprite.rect.width * self.scale_x))
            scaled_h = max(1, int(sprite.rect.height * self.scale_y))
            scaled_image = pygame.transform.scale(sprite.image, (scaled_w, scaled_h))
            self.display.blit(scaled_image, (screen_x, screen_y))

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
