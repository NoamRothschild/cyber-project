import pygame
from AutoMove import astar, random_walkable_tile, pixel_to_tile, tile_to_pixel_center, map_pixel_bounds


class AutoMove:
    def __init__(self, player):
        self.player = player
        self.enabled = False

        self.target_tile = None
        self.path = []
        self.path_i = 0

        self.stuck_frames = 0
        self.last_pos = None  # set on first step() call, after hitbox is ready

        self._font = pygame.font.SysFont("Arial", 20, bold=True)

    def toggle(self):
        self.enabled = not self.enabled
        if self.enabled:
            self.reset()

    def reset(self):
        p = self.player
        p.direction.x = 0
        p.direction.y = 0

        self.target_tile = None
        self.path = []
        self.path_i = 0
        self.stuck_frames = 0
        self.last_pos = None

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_BACKSLASH:
            print("AUTO MOVE TOGGLED: ", not self.enabled)
            self.toggle()

    def pick_new_target(self):
        import mapset
        print("world_map rows: ", len(mapset.world_map))
        target = random_walkable_tile()
        print("target: ", target)
        if target is None:
            self.target_tile = None
            self.path = []
            self.path_i = 0
            return

        p = self.player
        start = pixel_to_tile(p.hitbox.centerx, p.hitbox.centery)
        print("start tile: ", start, "map size:", len(mapset.world_map), "x",
              len(mapset.world_map[0]) if mapset.world_map else 0)
        path = astar(start, target)
        print (path is not None)
        print("path found: ", path is not None and len(path) > 1)

        if not path or len(path) < 2:
            self.target_tile = None
            self.path = []
            self.path_i = 0
            return

        self.target_tile = target
        self.path = path
        self.path_i = 1

    def step(self):
        if not self.enabled:
            return

        p = self.player

        if self.target_tile is None or not self.path or self.path_i >= len(self.path):
            self.pick_new_target()
            return

        tr, tc = self.path[self.path_i]
        tx, ty = tile_to_pixel_center(tr, tc)

        x, y = p.hitbox.centerx, p.hitbox.centery
        dx, dy = tx - x, ty - y

        if abs(dx) < 20 and abs(dy) < 20:
            self.path_i += 1
            return

        # Set direction — Camera in level.py handles scrolling automatically
        p.direction.x = 0
        p.direction.y = 0

        if abs(dx) > abs(dy):
            p.direction.x = 1 if dx > 0 else -1
        else:
            p.direction.y = 1 if dy > 0 else -1

        # Stuck detection
        cur = (p.hitbox.centerx, p.hitbox.centery)
        if self.last_pos is None:
            self.last_pos = cur
        if cur == self.last_pos:
            self.stuck_frames += 1
            if self.stuck_frames > 20:
                self.stuck_frames = 0
                self.pick_new_target()
        else:
            self.stuck_frames = 0
            self.last_pos = cur

    def draw_label(self):
        if not self.enabled:
            return

        screen = self.player.display_surface

        text = self._font.render("AUTO MOVE", True, (230, 230, 230))
        x = 12
        y = screen.get_height() - text.get_height() - 10

        pad = 6
        bg = pygame.Rect(x - pad, y - pad, text.get_width() + pad * 2, text.get_height() + pad * 2)
        pygame.draw.rect(screen, (30, 30, 30), bg, border_radius=8)
        pygame.draw.rect(screen, (90, 90, 90), bg, 2, border_radius=8)
        screen.blit(text, (x, y))
