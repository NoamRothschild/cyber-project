import threading
from typing import Any, Dict, Tuple

import pygame
from health import HealthBar
from mapset import PINK
import os
import sys
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# TODO: display entitys hp bar above them
SCALE_FROM_LIFE = 5


from health import HealthBar
from animation import Animation

SCALE_FROM_LIFE = 5
MIN_SMOOTH_DST = 25  # pixels; below this we interpolate, above we snap
HIDE_AFTER_NO_MOVE_MS = 1000  # hide entity from view if no position update for this long (we probably screwd up on the server, lets hide it)
DEATH_ANIMATION_MS = 1200  # time to show death animation before removing entity (DIED)
BASE_HP_PLAYER = 400
BASE_HP_ENEMY = 50
# Bar is always this many units wide so player and enemy bars look the same length
BAR_SCALE = BASE_HP_PLAYER // SCALE_FROM_LIFE

# Match the player's default skin: "fiona"
FIONA_SKIN = {
    "sheet_path": "Player_Skins/fiona.png",
    "frame_w": 32,
    "frame_h": 32,
    "rows": {"idle": 0, "run": 3, "injured": 5, "dead": 6},
    "frames_per_row": {"idle": 4, "run": 4, "injured": 4, "dead": 4},
    "scale": 3,
    "speed_ms": 180,  # match client/player skin animation speed
}

BLUE_GOLDEN_KNIGHT = {
    "sheet_path": "Player_Skins/blue golden knight.png",
    "frame_w": 32,
    "frame_h": 32,
    "rows": {"idle": 0, "run": 4, "injured": 8, "dead": 9},
    "frames_per_row": {"idle": 4, "run": 4, "injured": 4, "dead": 4},
    "scale": 3,
    "speed_ms": 180,  # match client/player skin animation speed
}


class Entity(pygame.sprite.Sprite):
    def __init__(self, groups: Any, pos: Tuple[int, int], type: str = "PLAYER") -> None:
        super().__init__(groups)

        self.image = pygame.image.load(resource_path('player.png')).convert_alpha()

        self.image.set_colorkey(PINK)

        # Set all attributes used by update()/draw first so we're safe if __init__ fails later
        self._lerp_active = False
        self._lerp_start_time = 0
        self._lerp_duration = 240  # slower on-screen movement
        self._lerp_start_pos = pygame.math.Vector2(pos[0], pos[1])
        self._lerp_target_pos = pygame.math.Vector2(pos[0], pos[1])
        self._pending_pos: None | Tuple[int, int] = None  # next target when current lerp finishes
        self.max_hp = BASE_HP_PLAYER if type == "PLAYER" else BASE_HP_ENEMY
        self.hp = self.max_hp
        self.hp_b = None
        self.injured_until = 0
        self._moved = False
        self._last_move_time = pygame.time.get_ticks()
        self.entity_type = type  # "PLAYER" or "ENEMY" for refresh_activity
        self.last_pos = pos
        self._hidden = False  # hide from view after HIDE_AFTER_NO_MOVE_MS without updates
        self.facing_right = True
        # Placeholders in case Animation() fails below
        self.animation = None
        self.image = pygame.Surface((32, 32))
        self.rect = self.image.get_rect()

        # Always use the same skin as the local player ("fiona") or enemy
        anim_config = FIONA_SKIN if type == "PLAYER" else BLUE_GOLDEN_KNIGHT
        self.animation = Animation(**anim_config)
        self.image = self.animation.image()
        self.rect = self.image.get_rect()

        self.hitbox = pygame.Rect(pos[0], pos[1], 30, 30)
        self.rect.center = self.hitbox.center
        self.hp = 400  # TODO: fetch from config
        self.hp_b = HealthBar((self.hitbox.x, self.hitbox.y - 10), self.hp // SCALE_FROM_LIFE, groups[0])

        self.hp_b = HealthBar(
            (self.hitbox.x, self.hitbox.y - 10), BAR_SCALE, groups[0]
        )
        self.hp_b.set_absolute(BAR_SCALE)  # full bar initially

        # Update lerp vectors to match hitbox
        self._lerp_start_pos.update(self.hitbox.x, self.hitbox.y)
        self._lerp_target_pos.update(self.hitbox.x, self.hitbox.y)

    def move(self, new_pos: None | Tuple[int, int]):
        if new_pos is None:
            return
        self.hitbox.x = new_pos[0]
        self.hitbox.y = new_pos[1]
        self.rect.center = self.hitbox.center
        self.hp_b.move([new_pos[0], new_pos[1] - 10])

        if new_pos == self.last_pos:
            return

        # If we're still lerping, only store the latest target; apply it when lerp finishes.
        if getattr(self, "_lerp_active", False):
            self._pending_pos = new_pos
            self._last_move_time = pygame.time.get_ticks()
            old = (self.hitbox.x, self.hitbox.y)
            if new_pos[0] > old[0]:
                self.facing_right = True
            elif new_pos[0] < old[0]:
                self.facing_right = False
            self.last_pos = new_pos
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
            if self.hp_b is not None:
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
        hp = max(0, min(hp, self.max_hp))
        self.hp = hp
        if self.hp_b is not None:
            target_width = round(hp / self.max_hp * BAR_SCALE)
            self.hp_b.set_absolute(target_width)
            if hp < self.max_hp:
                self.injured_until = pygame.time.get_ticks() + 600

    def update(self, *args):
        if getattr(self, "animation", None) is None:
            return
        now = pygame.time.get_ticks()

        min_dst_squared = MIN_SMOOTH_DST * MIN_SMOOTH_DST
        if getattr(self, "_lerp_active", False):
            t = (now - self._lerp_start_time) / self._lerp_duration
            if t >= 1.0:
                t = 1.0
                self._lerp_active = False
                self.hitbox.x = int(self._lerp_target_pos.x)
                self.hitbox.y = int(self._lerp_target_pos.y)
                self.rect.center = self.hitbox.center
                if self.hp_b is not None:
                    self.hp_b.move([self.hitbox.x, self.hitbox.y - 10])
                # Apply pending position (last received while we were lerping); skip intermediates.
                p = getattr(self, "_pending_pos", None)
                self._pending_pos = None
                if p is not None:
                    old = (self.hitbox.x, self.hitbox.y)
                    dx = p[0] - old[0]
                    dy = p[1] - old[1]
                    if dx * dx + dy * dy <= min_dst_squared:
                        self._lerp_active = True
                        self._lerp_start_time = now
                        self._lerp_start_pos.update(self.hitbox.x, self.hitbox.y)
                        self._lerp_target_pos.update(p)
                    else:
                        self.hitbox.x, self.hitbox.y = p
                        self.rect.center = self.hitbox.center
                        if self.hp_b is not None:
                            self.hp_b.move([p[0], p[1] - 10])
                    self.last_pos = p
                    if p[0] > old[0]:
                        self.facing_right = True
                    elif p[0] < old[0]:
                        self.facing_right = False
            else:
                x = (
                    self._lerp_start_pos.x
                    + (self._lerp_target_pos.x - self._lerp_start_pos.x) * t
                )
                y = (
                    self._lerp_start_pos.y
                    + (self._lerp_target_pos.y - self._lerp_start_pos.y) * t
                )
                self.hitbox.x = int(x)
                self.hitbox.y = int(y)
                self.rect.center = self.hitbox.center
                if self.hp_b is not None:
                    self.hp_b.move([self.hitbox.x, self.hitbox.y - 10])
            self._moved = True

        # Hide entity from view if no position update for a while; show again on next update.
        # Keep visible while playing death animation (_remove_after set).
        if getattr(self, "_remove_after", None) is not None:
            self._hidden = False
        else:
            self._hidden = (now - self._last_move_time) > HIDE_AFTER_NO_MOVE_MS
        if self.hp_b is not None:
            self.hp_b._hidden = self._hidden or getattr(self, "_remove_after", None) is not None

        if self.hp <= 0 or getattr(self, "_remove_after", None) is not None:
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
        self.image.set_alpha(0 if self._hidden else 255)



class Entities:
    def __init__(self) -> None:
        self.entities: Dict[int, Entity] = dict()
        self.lock = threading.Lock()

    def add_or_update(
        self,
        groups: Any,
        id: int,
        pos: None | Tuple[int, int] = None,
        hp: None | int = None,
        type: str = "PLAYER",
    ):
        with self.lock:
            if e := self.entities.get(id):
                e.move(pos)
                e.set_hp(hp)
                e.entity_type = type
            else:
                self.entities[id] = Entity(
                    groups, pos if pos is not None else (0, 0), type=type
                )
                self.entities[id].set_hp(hp)

    def refresh_activity(self, entity_id: int, only_if_enemy: bool = False) -> None:
        """Set the entity's _last_move_time to now (e.g. so it stays visible after shooting/hitting)."""
        with self.lock:
            e = self.entities.get(entity_id)
            if e is None:
                return
            if only_if_enemy and getattr(e, "entity_type", None) != "ENEMY":
                return
            e._last_move_time = pygame.time.get_ticks()

    def entity_died(self, entity_id: int) -> None:
        """Play death animation then remove after DEATH_ANIMATION_MS. Call cleanup_dead() each frame to actually remove."""
        with self.lock:
            e = self.entities.get(entity_id)
            if e is None:
                return
            e.set_hp(0)
            e._remove_after = pygame.time.get_ticks() + DEATH_ANIMATION_MS
            e._last_move_time = pygame.time.get_ticks()  # keep visible (don't hide) during death

    def cleanup_dead(self) -> None:
        """Remove entities that finished their death animation (_remove_after in the past)."""
        now = pygame.time.get_ticks()
        with self.lock:
            to_remove = [
                eid for eid, e in self.entities.items()
                if getattr(e, "_remove_after", None) is not None and now >= e._remove_after
            ]
            for eid in to_remove:
                e = self.entities.pop(eid, None)
                if e is not None:
                    e.kill()
                    if e.hp_b is not None:
                        e.hp_b.kill()

    def remove(self, entity_id: int) -> None:
        with self.lock:
            if e := self.entities.pop(entity_id, None):
                e.kill()
                if e.hp_b is not None:
                    e.hp_b.kill()
