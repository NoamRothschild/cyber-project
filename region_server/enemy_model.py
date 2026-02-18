from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple
import math

Vec2 = Tuple[float, float]

@dataclass
class AABB:
    x: float
    y: float
    w: float
    h: float

    def intersects(self, other: "AABB") -> bool:
        return not (
            self.x + self.w <= other.x or
            self.x >= other.x + other.w or
            self.y + self.h <= other.y or
            self.y >= other.y + other.h
        )

@dataclass
class PlayerSnapshot:
    player_id: int
    x: float
    y: float
    w: float = 30
    h: float = 40

    @property
    def aabb(self) -> AABB:
        return AABB(self.x, self.y, self.w, self.h)

@dataclass
class EnemyModel:
    enemy_id: int
    x: float
    y: float
    w: float = 30
    h: float = 40

    speed: float = 4.0  # pixels per tick
    state: str = "PATROL"  # PATROL|CHASE|ATTACK

    patrol_index: int = 0
    patrol_switch_ms: int = 600
    next_patrol_switch_ms: int = 0

    chase_radius: float = 260.0
    attack_radius: float = 45.0

    attack_cooldown_ms: int = 700
    next_attack_time_ms: int = 0

    # direction as normalized vector
    direction_x: float = 1.0
    direction_y: float = 0.0

    @property
    def aabb(self) -> AABB:
        return AABB(self.x, self.y, self.w, self.h)

    def _closest_player(self, players: Sequence[PlayerSnapshot]) -> Optional[PlayerSnapshot]:
        if not players:
            return None
        enemy_x = self.x + self.w / 2
        enemy_y = self.y + self.h / 2
        best = None
        best_distance_2 = float("inf")
        for player in players:
            player_x = player.x + player.w / 2
            player_y = player.y + player.h / 2
            distance_2 = (player_x - enemy_x) ** 2 + (player_y - enemy_y) ** 2
            if distance_2 < best_distance_2:
                best_distance_2 = distance_2
                best = player
        return best

    def _set_patrol_dir(self) -> None:
        dirs = [(1,0), (0,1), (-1,0), (0,-1)]
        self.direction_x, self.direction_y = dirs[self.patrol_index]

    def _normalize_dir(self) -> None:
        enemy_threshold = 1e-9
        magnitude_2 = self.direction_x * self.direction_x + self.direction_y * self.direction_y
        if magnitude_2 <= enemy_threshold:
            self.direction_x, self.direction_y = 0.0, 0.0
            return
        magnitude = math.sqrt(magnitude_2)
        self.direction_x /= magnitude
        self.direction_y /= magnitude

    def update_ai(self, now_ms: int, players: Sequence[PlayerSnapshot]) -> Optional[int]:
        """
        Returns attacked_player_id if an attack happened, else None.
        """
        target = self._closest_player(players)
        if target is None:
            self.state = "PATROL"
            return None

        enemy_center_x = self.x + self.w / 2
        enemy_center_y = self.y + self.h / 2
        target_center_x = target.x + target.w / 2
        target_center_y = target.y + target.h / 2
        distance_2 = (target_center_x - enemy_center_x) ** 2 + (target_center_y - enemy_center_y) ** 2

        if distance_2 <= self.attack_radius ** 2:
            self.state = "ATTACK"
        elif distance_2 <= self.chase_radius ** 2:
            self.state = "CHASE"
        else:
            self.state = "PATROL"

        #PATROL
        if self.state == "PATROL":
            if now_ms >= self.next_patrol_switch_ms:
                self.patrol_index = (self.patrol_index + 1) % 4
                self.next_patrol_switch_ms = now_ms + self.patrol_switch_ms
            self._set_patrol_dir()
            return None

        #CHASE
        if self.state == "CHASE":
            self.direction_x = target_center_x - enemy_center_x
            self.direction_y = target_center_y - enemy_center_y
            return None

        # ATTACK
        self.direction_x, self.direction_y = 0.0, 0.0
        if now_ms >= self.next_attack_time_ms:
            self.next_attack_time_ms = now_ms + self.attack_cooldown_ms
            return target.player_id

        return None

    def move_and_collide(self, obstacles: Sequence[AABB]) -> None:
        self._normalize_dir()

        # X axis
        self.x += self.direction_x * self.speed
        me = self.aabb
        for o in obstacles:
            if me.intersects(o):
                if self.direction_x > 0:
                    self.x = o.x - self.w
                elif self.direction_x < 0:
                    self.x = o.x + o.w
                me = self.aabb

        # Y axis
        self.y += self.direction_y * self.speed
        me = self.aabb
        for o in obstacles:
            if me.intersects(o):
                if self.direction_y > 0:
                    self.y = o.y - self.h
                elif self.direction_y < 0:
                    self.y = o.y + o.h
                me = self.aabb
