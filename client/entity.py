import threading
from typing import Any, Dict, Tuple
from mapset import PINK
import pygame
from helth import HealthBar
# TODO: display entitys hp bar above them
SCALE_FROM_LIFE=5
class Entity(pygame.sprite.Sprite):
    _cached_image: pygame.Surface | None = None

    @classmethod
    def _get_image(cls) -> pygame.Surface:
        if cls._cached_image is None:
            cls._cached_image = pygame.image.load('rock.png').convert_alpha()
            cls._cached_image.set_colorkey(PINK)
        return cls._cached_image

    def __init__(self, groups: Any, pos: Tuple[int, int]) -> None:
        super().__init__(groups)
        self.image = Entity._get_image()
        self.rect = self.image.get_rect()
        # pos is the hitbox position (matching what Player sends)
        self.hitbox = pygame.Rect(pos[0], pos[1], self.rect.width - 20, self.rect.height - 10)
        self.rect.center = self.hitbox.center
        self.hp = 400 # TODO: fetch from config
        self.hp_b = HealthBar((self.hitbox.x,self.hitbox.y-10),self.hp//SCALE_FROM_LIFE,groups[0])

    def move(self, new_pos: None | Tuple[int, int]):
        if new_pos is None:
            return
        self.hitbox.x = new_pos[0]
        self.hitbox.y = new_pos[1]
        self.rect.center = self.hitbox.center
        self.hp_b.move([new_pos[0],new_pos[1]-10])
    
    def set_hp(self, hp: int | None = None):
        if hp is None:
            return
        if hp>self.hp:
            self.hp_b.add_life(hp//SCALE_FROM_LIFE-self.hp_b.get_life())
        elif hp<self.hp:
            self.hp_b.sub_life(self.hp_b.get_life()-hp//SCALE_FROM_LIFE)
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
                e.hp_b.kill()
