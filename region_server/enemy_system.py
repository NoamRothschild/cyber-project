# region_server/enemy_system.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Sequence, Callable
from enemy_model import EnemyModel, PlayerSnapshot, AABB

@dataclass
class EnemyUpdate:
    enemy_id: int
    x: float
    y: float
    state: str
    # @TODO extend in later versions to include HP, animation state, velocity etc


class EnemySystem:
    def __init__(self) -> None:
        self.enemies: Dict[int, EnemyModel] = {}
        self.obstacles: List[AABB] = []

    def spawn_enemy(self, enemy: EnemyModel) -> None:
        self.enemies[enemy.enemy_id] = enemy

    def set_obstacles(self, obstacles: Sequence[AABB]) -> None:
        self.obstacles = list(obstacles)

    def tick(
        self,
        now_ms: int,
        players: Sequence[PlayerSnapshot],
        on_attack: Callable[[int, int], None],  # (enemy_id, player_id)
    ) -> List[EnemyUpdate]:
        updates: List[EnemyUpdate] = []
        for enemy in self.enemies.values():
            attacked_player_id = enemy.update_state_machine(now_ms, players)
            enemy.move_and_collide(self.obstacles)

            if attacked_player_id is not None:
                on_attack(enemy.enemy_id, attacked_player_id)

            updates.append(EnemyUpdate(enemy.enemy_id, enemy.x, enemy.y, enemy.state))
        return updates
