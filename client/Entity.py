import threading
from typing import Any, Dict, Set, Tuple
from mapset import PINK
import pygame

class Entity(pygame.sprite.Sprite):
    def __init__(self, groups: Any, pos: Tuple[int, int]) -> None:
        super().__init__(groups)
        self.image = pygame.image.load('player.png').convert_alpha()
        self.image.set_colorkey(PINK)
        self.rect = self.image.get_rect()
        # pos is the hitbox position (matching what Player sends)
        self.hitbox = pygame.Rect(pos[0], pos[1], self.rect.width - 20, self.rect.height - 10)
        self.rect.center = self.hitbox.center

    def move(self, new_pos: Tuple[int, int]):
        self.hitbox.x = new_pos[0]
        self.hitbox.y = new_pos[1]
        self.rect.center = self.hitbox.center


class Entities:
    def __init__(self) -> None:
        self.entities: Dict[int, Entity] = dict()
        self.lock = threading.Lock()

    def add_or_update(self, id: int, pos: Tuple[int, int], groups: Any):
        with self.lock:
            if e := self.entities.get(id):
                e.move(pos)
            else:
                self.entities[id] = Entity(groups, pos)
