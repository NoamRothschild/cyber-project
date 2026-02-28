import threading
from typing import Any, Dict, Tuple
from mapset import PINK
import pygame

# TODO: display entitys hp bar above them

class Entity(pygame.sprite.Sprite):
    def __init__(self, groups: Any, pos: Tuple[int, int]) -> None:
        super().__init__(groups)
        self.image = pygame.image.load('player.png').convert_alpha()
        self.image.set_colorkey(PINK)
        self.rect = self.image.get_rect()
        # pos is the hitbox position (matching what Player sends)
        self.hitbox = pygame.Rect(pos[0], pos[1], self.rect.width - 20, self.rect.height - 10)
        self.rect.center = self.hitbox.center
        self.hp = 400 # TODO: fetch from config

    def move(self, new_pos: None | Tuple[int, int]):
        if new_pos is None:
            return
        self.hitbox.x = new_pos[0]
        self.hitbox.y = new_pos[1]
        self.rect.center = self.hitbox.center
    
    def set_hp(self, hp: int | None = None):
        if hp is None:
            return
        self.hp = hp

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
