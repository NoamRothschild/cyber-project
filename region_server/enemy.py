from typing import Optional, Iterable

import pygame

from client.helth import HealthBar
from client.mapset import WIDTH

RGB_BACKGROUND = (110, 129, 198)
HIT_BOX = -20, -10
SPEED = 4

HEALTH_BAR_SCALE = 400
HEALTH_BAR_POS = [WIDTH - HEALTH_BAR_SCALE - 10, 10]

PATROL_STEP_MS = 600  # how long each patrol direction lasts
CHASE_RADIUS = 260  # start chasing if player is closer than this
ATTACK_RADIUS = 45  # attack range (melee)
ATTACK_COOLDOWN_MS = 700  # time between attacks
DAMAGE = 10


class Enemy(pygame.sprite.Sprite):
    def __init__(self, pos, groups, other_groups):
        super().__init__(groups)

        self.image = pygame.image.load("enemy.png").convert_alpha()
        self.image.set_colorkey(RGB_BACKGROUND)

        self.rect = self.image.get_rect(topleft=pos)
        self.hitbox = self.rect.inflate(HIT_BOX)

        self.speed = SPEED
        self.direction = pygame.math.Vector2(1, 0)

        # other_groups: (obstacle_sprites, harmful_sprites)
        self.obstacle_sprites, self.harmful_sprites = other_groups

        self.health = HealthBar(HEALTH_BAR_POS, HEALTH_BAR_SCALE)

        # AI state
        self.state = "PATROL"  # PATROL | CHASE | ATTACK
        self.patrol_index = 0
        self.next_patrol_switch = pygame.time.get_ticks() + PATROL_STEP_MS

        self.next_attack_time = 0

    def closest_player(self, players: Iterable[pygame.sprite.Sprite]) -> Optional[pygame.sprite.Sprite]:
        closest_player = None
        closest_distance = float("inf")
        enemy_x, enemy_y = self.hitbox.center
        for p in players:
            player_x, player_y = p.hitbox.center if hasattr(p, "hitbox") else p.rect.center
            d2 = (player_x - enemy_x) ** 2 + (player_y - enemy_y) ** 2
            if d2 < closest_distance:
                closest_distance = d2
                closest_player = p
        return closest_player

    def set_patrol_direction(self):
        # 4-step square patrol: right, down, left, up
        dirs = [pygame.math.Vector2(1, 0), pygame.math.Vector2(0, 1),
                pygame.math.Vector2(-1, 0), pygame.math.Vector2(0, -1)]
        self.direction = dirs[self.patrol_index].copy()

    def move_axis(self, axis: str):
        if axis == "x":
            self.hitbox.x += int(self.direction.x * self.speed)
            for sprite in self.obstacle_sprites:
                if sprite.hitbox.colliderect(self.hitbox):
                    if self.direction.x > 0:  # moving right
                        self.hitbox.right = sprite.hitbox.left
                    elif self.direction.x < 0:  # moving left
                        self.hitbox.left = sprite.hitbox.right
        else:
            self.hitbox.y += int(self.direction.y * self.speed)
            for sprite in self.obstacle_sprites:
                if sprite.hitbox.colliderect(self.hitbox):
                    if self.direction.y > 0:  # moving down
                        self.hitbox.bottom = sprite.hitbox.top
                    elif self.direction.y < 0:  # moving up
                        self.hitbox.top = sprite.hitbox.bottom

        self.rect.topleft = self.hitbox.topleft

    def move(self):
        if self.direction.length_squared() > 0:
            self.direction = self.direction.normalize()
        self.move_axis("x")
        self.move_axis("y")

    def attack(self, player):
        now = pygame.time.get_ticks()
        if now < self.next_attack_time:
            return

        if hasattr(player, "health") and hasattr(player.health, "sub_life"):
            player.health.sub_life(DAMAGE)

        self.next_attack_time = now + ATTACK_COOLDOWN_MS

    def update(self, players):
        """
        Call every frame: enemy_group.update(players)
        where `players` is an iterable/group of player sprites.
        """
        now = pygame.time.get_ticks()
        target = self.closest_player(players)

        # If no players exist, just patrol
        if target is None:
            self.state = "PATROL"
            return

        if target is not None:
            target_x, target_y = target.hitbox.center if hasattr(target, "hitbox") else target.rect.center
            distance_x = target_x - self.hitbox.centerx
            distance_y = target_y - self.hitbox.centery
            distance_2 = distance_x * distance_x + distance_y * distance_y

            if distance_2 <= ATTACK_RADIUS * ATTACK_RADIUS:
                self.state = "ATTACK"
            elif distance_2 <= CHASE_RADIUS * CHASE_RADIUS:
                self.state = "CHASE"
            else:
                self.state = "PATROL"

        if self.state == "PATROL":
            if now >= self.next_patrol_switch:
                self.patrol_index = (self.patrol_index + 1) % 4
                self.next_patrol_switch = now + PATROL_STEP_MS
            self.set_patrol_direction()
            self.move()

        elif self.state == "CHASE" and target is not None:
            target_x, target_y = target.hitbox.center if hasattr(target, "hitbox") else target.rect.center
            self.direction.x = target_x - self.hitbox.centerx
            self.direction.y = target_y - self.hitbox.centery
            self.move()

        elif self.state == "ATTACK" and target is not None:
            self.direction.update(0, 0)
            self.attack(target)
