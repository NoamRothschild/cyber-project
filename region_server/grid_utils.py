from __future__ import annotations
from typing import Any, Tuple
from enum import Enum


class ProxyObject:
    """Base for proxy entities (e.g. ProxyClient, ProxyBullet); lives here to avoid circular import with proxy."""
    def __init__(self, pos_x: int, pos_y: int, id: int) -> None:
        self.pos = (pos_x, pos_y)
        self.id = id

    def __hash__(self) -> int:
        return hash((self.id, type(self)))

    def __eq__(self, other: Any) -> bool:
        return self.id == other.id and isinstance(self, type(other))


class GridField:
    def __init__(self, obj: Any, seen: set[int] = set()) -> None:
        self.obj = obj
        self.seen = seen
    
    def add_seen(self, user_id: int) -> None:
        self.seen.add(user_id)
    
    def __hash__(self) -> int:
        return hash(self.obj)
    
    def __eq__(self, other: Any) -> bool:
        return self.obj == other.obj


class ProxyField:
    def __init__(self, proxy: ProxyObject, seen: set[int]) -> None:
        self.proxy = proxy
        self.seen = seen

    def add_seen(self, user_id: int) -> None:
        self.seen.add(user_id)

    def __hash__(self) -> int:
        return hash(self.proxy)

    def __eq__(self, other: Any) -> bool:
        return self.proxy == other.proxy

    def __iter__(self):
        # Iterates as (seen, proxy_obj) to allow: for seen, proxy_obj in proxy
        yield self.seen
        yield self.proxy


class Direction(Enum):
    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)
    UP_LEFT = (-1, -1)
    UP_RIGHT = (1, -1)
    DOWN_LEFT = (-1, 1)
    DOWN_RIGHT = (1, 1)

    @staticmethod
    def to_proxy_pos(value: Direction) -> int:
        """converts a direction to a position within the proxies set"""
        m = {
            Direction.UP_LEFT: 0,
            Direction.UP: 1,
            Direction.UP_RIGHT: 2,
            Direction.LEFT: 3,
            Direction.RIGHT: 4,
            Direction.DOWN_LEFT: 5,
            Direction.DOWN: 6,
            Direction.DOWN_RIGHT: 7,
        }
        return m[value]
    
    @staticmethod
    def from_diff(initial_pos: Tuple[int, int], new_pos: Tuple[int, int]) -> Direction:
        """Direction from initial_pos to new_pos. Normalizes to a unit step (one of the 8 directions)"""
        dx = new_pos[0] - initial_pos[0]
        dy = new_pos[1] - initial_pos[1]
        
        # normalize to a unit step
        if dx != 0:
            dx = 1 if dx > 0 else -1
        if dy != 0:
            dy = 1 if dy > 0 else -1
        if dx == 0 and dy == 0:
            raise ValueError("Initial and new positions are the same")
        
        return Direction((dx, dy))

