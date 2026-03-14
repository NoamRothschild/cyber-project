import threading
from typing import Any, Dict, Tuple

import pygame
from health import HealthBar
from animation import Animation

SCALE_FROM_LIFE = 5
MIN_SMOOTH_DST = 5  # pixels; below this we interpolate, above we snap
BASE_HP = 400

# Match the player's default skin: "fiona"
FIONA_SKIN = {
    "sheet_path": "Player_Skins/fiona.png",
    "frame_w": 32,
    "frame_h": 32,
    "rows": {"idle": 0, "run": 3, "injured": 5, "dead": 6},
    "frames_per_row": {"idle": 4, "run": 4, "injured": 4, "dead": 4},
    "scale": 3,
    "speed_ms": 180,
}


class Entity(pygame.sprite.Sprite):
    def __init__(self, groups: Any, pos: Tuple[int, int]) -> None:
        super().__init__(groups)

        # Always use the same skin as the local player ("fiona")
        self.animation = Animation(**FIONA_SKIN)
        self.facing_right = True
        self.image = self.animation.image()
        self.rect = self.image.get_rect()

        self.hitbox = pygame.Rect(pos[0], pos[1], 30, 30)
        self.rect.center = self.hitbox.center

        self.hp = BASE_HP
        self.hp_b = HealthBar(
            (self.hitbox.x, self.hitbox.y - 10), self.hp // SCALE_FROM_LIFE, groups[0]
        )

        self.last_pos = pos
        self._moved = False
        self._last_move_time = pygame.time.get_ticks()
        self.injured_until = 0

        # Smooth interpolation towards latest server position
        self._lerp_active = False
        self._lerp_start_time = 0
        self._lerp_duration = 150  # ms
        self._lerp_start_pos = pygame.math.Vector2(self.hitbox.x, self.hitbox.y)
        self._lerp_target_pos = pygame.math.Vector2(self.hitbox.x, self.hitbox.y)

    def move(self, new_pos: None | Tuple[int, int]):
        if new_pos is None:
            return
        if new_pos == self.last_pos:
            return

        old = (self.hitbox.x, self.hitbox.y)
        dx = new_pos[0] - old[0]
        dy = new_pos[1] - old[1]
        traveled_dst_squared = dx * dx + dy * dy
        min_dst_squared = MIN_SMOOTH_DST * MIN_SMOOTH_DST

        # If the update is a small correction, interpolate; otherwise snap.
        if traveled_dst_squared <= min_dst_squared:
            self._lerp_active = True
            self._lerp_start_time = pygame.time.get_ticks()
            self._lerp_start_pos.update(old)
            self._lerp_target_pos.update(new_pos)
        else:
            self._lerp_active = False
            self.hitbox.x, self.hitbox.y = new_pos
            self.rect.center = self.hitbox.center
            self.hp_b.move([new_pos[0], new_pos[1] - 10])

        self._moved = True
        self._last_move_time = pygame.time.get_ticks()

        if new_pos[0] > old[0]:
            self.facing_right = True
        elif new_pos[0] < old[0]:
            self.facing_right = False

        self.last_pos = new_pos

    def set_hp(self, hp: int | None = None):
        if hp is None:
            return
        if hp > self.hp:
            self.hp_b.add_life(hp // SCALE_FROM_LIFE - self.hp_b.get_life())
        elif hp < self.hp:
            self.hp_b.sub_life(self.hp_b.get_life() - hp // SCALE_FROM_LIFE)
            self.injured_until = pygame.time.get_ticks() + 600
        self.hp = hp

    def update(self, *args):
        now = pygame.time.get_ticks()

        if self._lerp_active:
            t = (now - self._lerp_start_time) / self._lerp_duration
            if t >= 1.0:
                t = 1.0
                self._lerp_active = False
            x = self._lerp_start_pos.x + (self._lerp_target_pos.x - self._lerp_start_pos.x) * t
            y = self._lerp_start_pos.y + (self._lerp_target_pos.y - self._lerp_start_pos.y) * t
            self.hitbox.x = int(x)
            self.hitbox.y = int(y)
            self.rect.center = self.hitbox.center
            self.hp_b.move([self.hitbox.x, self.hitbox.y - 10])
            self._moved = True

        if self.hp <= 0:
            self.animation.set_state("dead")
        elif now < self.injured_until:
            self.animation.set_state("injured")
        elif self._moved or (now - self._last_move_time) <= 400:
            self.animation.set_state("run")
        else:
            self.animation.set_state("idle")

        self._moved = False

        self.animation.update()
        old_center = self.rect.center
        # Match Player: flip_x argument is inverted inside Animation.image
        self.image = self.animation.image(flip_x=(not self.facing_right))
        self.rect = self.image.get_rect(center=old_center)

class Entities:
    def __init__(self) -> None:
        self.entities: Dict[int, Entity] = dict()
        self.lock = threading.Lock()

    def add_or_update(self, groups: Any, id: int, pos: None | Tuple[int, int] = None, hp: None | int = None):
        with self.lock:
            if e := self.entities.get(id):
                e.move(pos)
                e.set_hp(hp)
            else:
                self.entities[id] = Entity(groups, pos if pos is not None else (0, 0))
                self.entities[id].set_hp(hp)

    def remove(self, entity_id: int) -> None:
        with self.lock:
            if e := self.entities.pop(entity_id, None):
                e.kill()
                e.hp_b.kill()
