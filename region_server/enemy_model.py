from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple
from random import random
import math
import protobuf.region_net_pb2 as region_net

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
    x: int
    y: int
    w: float = 30
    h: float = 40

    @property
    def aabb(self) -> AABB:
        return AABB(self.x, self.y, self.w, self.h)


@dataclass
class MeleeEnemy:
    enemy_id: int
    x: int
    y: int

    last_sent_x: int = 0
    last_sent_y: int = 0
    
    cell_x: int = 0
    cell_y: int = 0

    w: float = 30
    h: float = 40
    speed: float = 6.0

    state: str = "PATROL"  # PATROL | CHASE | ATTACK
    direction_x: float = 1.0
    direction_y: float = 0.0

    max_hp: int = 50
    hp: int = 50

    zone_min_x: int = 0
    zone_min_y: int = 0
    zone_max_x: int = 10000
    zone_max_y: int = 10000

    patrol_target_x: float = 0.0
    patrol_target_y: float = 0.0
    patrol_switch_ms: int = 4000
    next_patrol_switch_ms: int = 0
    patrol_target_reached_dist: float = 20.0

    chase_radius: float = 260.0
    attack_radius: float = 40.0
    attack_cooldown_ms: int = 700
    next_attack_time_ms: int = 0

    @property
    def aabb(self) -> AABB:
        return AABB(self.x, self.y, self.w, self.h)

    def to_proxy_event(self) -> region_net.ProxyEvent:
        return region_net.ProxyEvent(
            enemy=region_net.EnemyProxy(
                pos=region_net.LocationBlock(x=self.x, y=self.y),
                player_id=self.enemy_id,
                session_id=0,
                HP=self.hp,
            )
        )

    def __hash__(self) -> int:
        return hash(self.enemy_id)

    def reset_combat(self) -> None:
        self.hp = self.max_hp

    def take_damage(self, amount: int) -> bool:
        if amount <= 0 or self.hp <= 0:
            return False
        self.hp = max(0, self.hp - amount)
        return self.hp == 0

    def closest_player(self, players: Sequence[PlayerSnapshot]) -> Optional[PlayerSnapshot]:
        if not players:
            return None
        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        best, best_d2 = None, float("inf")
        for p in players:
            d2 = (p.x + p.w/2 - cx)**2 + (p.y + p.h/2 - cy)**2
            if d2 < best_d2:
                best_d2, best = d2, p
        return best

    def pick_patrol_target(self) -> None:
        self.patrol_target_x = self.zone_min_x + random() * (self.zone_max_x - self.zone_min_x - self.w)
        self.patrol_target_y = self.zone_min_y + random() * (self.zone_max_y - self.zone_min_y - self.h)

    def update_state_machine(
        self, now_ms: int, players: Sequence[PlayerSnapshot]
    ) -> Optional[int]:
        """Returns attacked player_id on melee hit, else None."""
        target = self.closest_player(players)
        if target is None:
            self.state = "PATROL"
            return None

        current_x = self.x + self.w / 2
        current_y = self.y + self.h / 2
        tx = target.x + target.w / 2
        ty = target.y + target.h / 2
        dx, dy = tx - current_x, ty - current_y
        d2 = dx*dx + dy*dy

        if d2 <= self.attack_radius ** 2:
            self.state = "ATTACK"
        elif d2 <= self.chase_radius ** 2:
            self.state = "CHASE"
        else:
            self.state = "PATROL"

        if self.state == "PATROL":
            current_x = self.x + self.w / 2
            current_y = self.y + self.h / 2
            patrol_delta_x = self.patrol_target_x - current_x
            patrol_delta_y = self.patrol_target_y - current_y
            reached = ((patrol_delta_x * patrol_delta_x + patrol_delta_y * patrol_delta_y)
                       <= self.patrol_target_reached_dist ** 2)
            if reached or now_ms >= self.next_patrol_switch_ms:
                self.pick_patrol_target()
                self.next_patrol_switch_ms = now_ms + self.patrol_switch_ms
                patrol_delta_x = self.patrol_target_x - current_x
                patrol_delta_y = self.patrol_target_y - current_y
            self.direction_x = patrol_delta_x
            self.direction_y = patrol_delta_y
            return None

        if self.state == "CHASE":
            self.direction_x, self.direction_y = dx, dy
            return None

        # ATTACK
        self.direction_x, self.direction_y = 0.0, 0.0
        if now_ms >= self.next_attack_time_ms:
            self.next_attack_time_ms = now_ms + self.attack_cooldown_ms
            return target.player_id
        return None

    def normalize_dir(self) -> None:
        m2 = self.direction_x**2 + self.direction_y**2
        if m2 <= 1e-9:
            self.direction_x, self.direction_y = 0.0, 0.0
            return
        m = math.sqrt(m2)
        self.direction_x /= m
        self.direction_y /= m

    def move_and_collide(self, obstacles: Sequence[AABB]) -> None:
        self.normalize_dir()

        self.x += self.direction_x * self.speed
        me = self.aabb
        for o in obstacles:
            if me.intersects(o):
                if self.direction_x > 0:
                    self.x = o.x - self.w
                elif self.direction_x < 0:
                    self.x = o.x + o.w
                me = self.aabb

        self.y += self.direction_y * self.speed
        me = self.aabb
        for o in obstacles:
            if me.intersects(o):
                if self.direction_y > 0:
                    self.y = o.y - self.h
                elif self.direction_y < 0:
                    self.y = o.y + o.h
                me = self.aabb
        
        self.x = int(round(self.x))
        self.y = int(round(self.y))


@dataclass
class RangedEnemy:
    enemy_id: int
    x: int
    y: int

    last_sent_x: float = 0
    last_sent_y: float = 0

    cell_x: int = 0
    cell_y: int = 0

    w: float = 30
    h: float = 40
    speed: float = 4  # slower than melee

    state: str = "PATROL"  # PATROL | CHASE | SHOOT
    direction_x: float = 1.0
    direction_y: float = 0.0

    max_hp: int = 30  # squishier than melee
    hp: int = 30

    zone_min_x: int = 0
    zone_min_y: int = 0
    zone_max_x: int = 10000
    zone_max_y: int = 10000

    patrol_target_x: float = 0.0
    patrol_target_y: float = 0.0
    patrol_switch_ms: int = 4000
    next_patrol_switch_ms: int = 0
    patrol_target_reached_dist: float = 20.0

    chase_radius: float = 400.0
    shoot_range: float = 200.0   # stops here and shoots
    shoot_cooldown_ms: int = 1500
    next_shoot_time_ms: int = 0

    @property
    def aabb(self) -> AABB:
        return AABB(self.x, self.y, self.w, self.h)
    
    def to_proxy_event(self) -> region_net.ProxyEvent:
        return region_net.ProxyEvent(
            enemy=region_net.EnemyProxy(
                pos=region_net.LocationBlock(x=self.x, y=self.y),
                player_id=self.enemy_id,
                session_id=0,
                HP=self.hp,
            )
        )
    
    def __hash__(self) -> int:
        return hash(self.enemy_id)

    def reset_combat(self) -> None:
        self.hp = self.max_hp

    def take_damage(self, amount: int) -> bool:
        if amount <= 0 or self.hp <= 0:
            return False
        self.hp = max(0, self.hp - amount)
        return self.hp == 0

    def closest_player(self, players: Sequence[PlayerSnapshot]) -> Optional[PlayerSnapshot]:
        if not players:
            return None
        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        best, best_d2 = None, float("inf")
        for p in players:
            d2 = (p.x + p.w/2 - cx)**2 + (p.y + p.h/2 - cy)**2
            if d2 < best_d2:
                best_d2, best = d2, p
        return best

    def pick_patrol_target(self) -> None:
        self.patrol_target_x = self.zone_min_x + random() * (self.zone_max_x - self.zone_min_x - self.w)
        self.patrol_target_y = self.zone_min_y + random() * (self.zone_max_y - self.zone_min_y - self.h)

    def update_state_machine(
        self, now_ms: int, players: Sequence[PlayerSnapshot]
    ) -> Optional[float]:
        """Returns shoot angle (radians) when firing, else None."""
        target = self.closest_player(players)
        if target is None:
            self.state = "PATROL"
            return None

        cx = self.x + self.w / 2
        cy = self.y + self.h / 2
        tx = target.x + target.w / 2
        ty = target.y + target.h / 2
        dx, dy = tx - cx, ty - cy
        d2 = dx*dx + dy*dy

        if d2 <= self.shoot_range ** 2:
            self.state = "SHOOT"
        elif d2 <= self.chase_radius ** 2:
            self.state = "CHASE"
        else:
            self.state = "PATROL"

        if self.state == "PATROL":
            if now_ms >= self.next_patrol_switch_ms:
                self.patrol_index = (self.patrol_index + 1) % 4
                self.next_patrol_switch_ms = now_ms + self.patrol_switch_ms
            self.set_patrol_dir()
            return None

        if self.state == "CHASE":
            self.direction_x, self.direction_y = dx, dy
            return None

        # SHOOT — stop and fire
        self.direction_x, self.direction_y = 0.0, 0.0
        if now_ms >= self.next_shoot_time_ms:
            self.next_shoot_time_ms = now_ms + self.shoot_cooldown_ms
            return math.atan2(dy, dx)
        return None

    def normalize_dir(self) -> None:
        m2 = self.direction_x**2 + self.direction_y**2
        if m2 <= 1e-9:
            self.direction_x, self.direction_y = 0.0, 0.0
            return
        m = math.sqrt(m2)
        self.direction_x /= m
        self.direction_y /= m

    def move_and_collide(self, obstacles: Sequence[AABB]) -> None:
        self.normalize_dir()

        self.x += self.direction_x * self.speed
        me = self.aabb
        for o in obstacles:
            if me.intersects(o):
                if self.direction_x > 0:
                    self.x = o.x - self.w
                elif self.direction_x < 0:
                    self.x = o.x + o.w
                me = self.aabb

        self.y += self.direction_y * self.speed
        me = self.aabb
        for o in obstacles:
            if me.intersects(o):
                if self.direction_y > 0:
                    self.y = o.y - self.h
                elif self.direction_y < 0:
                    self.y = o.y + o.h
                me = self.aabb

        self.x = int(round(self.x))
        self.y = int(round(self.y))


# Union type used throughout the server
EnemyModel = MeleeEnemy | RangedEnemy
