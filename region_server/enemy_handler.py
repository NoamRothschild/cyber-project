import asyncio
from typing import List, Set, Tuple
from random import random
import time
from constants import TICK_INTERVAL_SEC
from enemy_model import EnemyModel, MeleeEnemy, RangedEnemy, PlayerSnapshot
import protobuf.region_net_pb2 as region_net
from typing import Dict, Union
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from region_node import RegionNode

SECONDS_TO_MS = 1000
ENEMY_DAMAGE = 5

# Per-node enemy ID scheme: no conflicts across nodes (NODE_COUNT = 340)
NODE_COUNT = 340
MAX_ID = (2 ** 31) - 1

def _melee_base_id(node_index: int) -> int:
    return int(MAX_ID / NODE_COUNT * node_index)

def _ranged_base_id(node_index: int) -> int:
    return int(MAX_ID / NODE_COUNT * (node_index + 0.5))

def loop_time_ms():
    return int(time.time() * SECONDS_TO_MS)

class EnemyHandler:
    def __init__(self, node: "RegionNode", node_index: int, x_range: Tuple[int, int], y_range: Tuple[int, int], tick_intervals: float = TICK_INTERVAL_SEC) -> None:
        self.node = node
        self.node_index = node_index
        self.tick_intervals = tick_intervals
        self.enemies = {}  # key: enemy_id -> value: EnemyModel
        self.lock = asyncio.Lock()

        # # Dynamic enemy population based on distance from (14, 14)
        # # Max at (14,14) is 20, approached 0 in an area of roughly 5x5 from there
        # target_center_x, target_center_y = 14, 14
        # max_count = 20
        # fade_dist_x, fade_dist_y = 5, 5
        # # Get our node position (RegionNode keeps this as .node_pos)
        # # node_index -> (x, y) conversion (import constants or local mapping)
        # from region_node import HORIZONAL_NODE_COUNT
        # node_x = node_index % HORIZONAL_NODE_COUNT
        # node_y = node_index // HORIZONAL_NODE_COUNT

        # dx = abs(node_x - target_center_x) / fade_dist_x
        # dy = abs(node_y - target_center_y) / fade_dist_y

        # distance_score = max(dx, dy)
        # if distance_score >= 1.0:
        #     self.target_enemy_count = 0
        # else:
        #     self.target_enemy_count = int(round(max_count * (1.0 - distance_score)))
        self.target_enemy_count = 3

        self.world_min_x = x_range[0]
        self.world_min_y = y_range[0]
        self.world_max_x = x_range[1]
        self.world_max_y = y_range[1]

        # Per-node ID bases so IDs don't conflict across nodes
        self._melee_base = _melee_base_id(node_index)
        self._ranged_base = _ranged_base_id(node_index)
        self._next_melee_slot = 0
        self._next_ranged_slot = 0

        # enemy_ids currently dead and awaiting respawn — skipped by bullets and movement
        self._dead_ids: Set[int] = set()

    def random_spawn(self) -> Tuple[int, int]:
        x = self.world_min_x + (self.world_max_x - self.world_min_x) * random()
        y = self.world_min_y + (self.world_max_y - self.world_min_y) * random()
        return int(x), int(y)

    def _is_ranged_id(self, enemy_id: int) -> bool:
        """True if this ID was assigned to a ranged enemy on this node."""
        return enemy_id >= self._ranged_base

    def spawn_enemy(self, enemy_id: int | None = None) -> EnemyModel:
        if enemy_id is None:
            is_ranged = random() < 0.4
            if is_ranged:
                enemy_id = self._ranged_base + self._next_ranged_slot
                self._next_ranged_slot += 1
            else:
                enemy_id = self._melee_base + self._next_melee_slot
                self._next_melee_slot += 1

        x, y = self.random_spawn()
        if self._is_ranged_id(enemy_id):
            e: EnemyModel = RangedEnemy(enemy_id=enemy_id, x=x, y=y)
        else:
            e = MeleeEnemy(enemy_id=enemy_id, x=x, y=y)
        e.reset_combat()
        e.last_sent_x = e.x
        e.last_sent_y = e.y
        self.enemies[enemy_id] = e
        return e

    async def ensure_population(self) -> None:
        """Create enemies until we have target_enemy_count."""
        async with self.lock:
            missing = self.target_enemy_count - len(self.enemies)
            if missing <= 0:
                return
            spawned = [self.spawn_enemy() for _ in range(missing)]

        # broadcast outside lock
        for e in spawned:
            await self.broadcast_enemy_spawn(e)

    async def respawn_enemy(self, enemy_id: int) -> None:
        """Respawn an enemy at a random location with full HP."""
        # Wait before respawning — gives the client time to hide the dead enemy
        # and ensures no in-flight bullets can hit the resetting enemy
        await asyncio.sleep(2.0)

        async with self.lock:
            enemy = self.enemies.get(enemy_id)
            if enemy is None:
                enemy = self.spawn_enemy(enemy_id)
            else:
                enemy.x, enemy.y = self.random_spawn()
                enemy.reset_combat()
                enemy.last_sent_x = enemy.x
                enemy.last_sent_y = enemy.y
            snapshot_x = int(enemy.x)
            snapshot_y = int(enemy.y)
            snapshot_hp = int(enemy.hp)
            # clear dead flag now that the enemy is fully reset
            self._dead_ids.discard(enemy_id)

        for cli in self.node.clients_in_view((enemy.x, enemy.y)):
            await cli.saw_enemy((enemy.x, enemy.y), enemy.enemy_id)

    async def broadcast_enemy_spawn(self, enemy: EnemyModel) -> None:
        """Broadcast enemy location (spawn/respawn)."""
        update = region_net.ServerResponse()
        update.sender_id = enemy.enemy_id
        update.enemy_data.new_location.CopyFrom(
            region_net.LocationBlock(
                x=int(enemy.x),
                y=int(enemy.y))
        )

        for cli in self.node.clients_in_view((enemy.x, enemy.y)):
            await cli.write(update.SerializeToString())

        await self.broadcast_enemy_hp(enemy)

    async def broadcast_enemy_hp(self, enemy: EnemyModel) -> None:
        """Broadcast HP (reuses OtherPlayerData payload)."""
        update = region_net.ServerResponse()
        update.sender_id = enemy.enemy_id
        update.enemy_data.CopyFrom(
            region_net.OtherPlayerData(
                HP=int(enemy.hp),
                player_id=enemy.enemy_id)
        )
        for cli in self.node.clients_in_view((enemy.x, enemy.y)):
            await cli.write(update.SerializeToString())

    async def tick(self, cycle: int) -> None:
        has_viewers = self.node.has_nearby_viewers()
        if not has_viewers and cycle % 3 == 0:
            return # lower tick rate on nodes with no viewers

        pending_hits = []
        pending_moves: List[EnemyModel] = []
        pending_shots = []  # (spawn_x, spawn_y, enemy_id, angle)

        async with self.lock:
            now_ms = loop_time_ms()

            for enemy in list(self.enemies.values()):
                if enemy.enemy_id in self._dead_ids:
                    continue

                if isinstance(enemy, MeleeEnemy):
                    attacked_player_id = enemy.update_state_machine(
                        now_ms,
                        [PlayerSnapshot(c.user_id, c.state.x, c.state.y) for c in self.node.clients_in_view((enemy.x, enemy.y))]
                    )
                    if attacked_player_id is not None:
                        pending_hits.append((attacked_player_id, enemy.enemy_id))
                else:  # RangedEnemy
                    shoot_angle = enemy.update_state_machine(
                        now_ms,
                        [PlayerSnapshot(c.user_id, c.state.x, c.state.y) for c in self.node.clients_in_view((enemy.x, enemy.y))]
                    )
                    if shoot_angle is not None:
                        pending_shots.append((
                            enemy.x + enemy.w / 2,
                            enemy.y + enemy.h / 2,
                            enemy.enemy_id,
                            shoot_angle,
                        ))

                old_cell_x, old_cell_y = enemy.cell_x, enemy.cell_y
                enemy.move_and_collide([])
                # Keep enemy inside this node's zone
                enemy.x = int(max(
                    self.world_min_x,
                    min(self.world_max_x - enemy.w, enemy.x),
                ))
                enemy.y = int(max(
                    self.world_min_y,
                    min(self.world_max_y - enemy.h, enemy.y),
                ))
                enemy.cell_x, enemy.cell_y = self.node.to_cell_pos((enemy.x, enemy.y))
                self.node.grid_move(enemy, old_cell_x, old_cell_y, enemy.cell_x, enemy.cell_y)

                if should_update_location((enemy.last_sent_x, enemy.last_sent_y),
                                          (enemy.x, enemy.y)):
                    pending_moves.append(enemy)
                    enemy.last_sent_x = enemy.x
                    enemy.last_sent_y = enemy.y

        for attacked_player_id, enemy_id in pending_hits:
            # Attacked player is on this node; find them by id and apply damage
            for c in self.node.clients.values():
                if c.user_id == attacked_player_id:
                    await c.hit(ENEMY_DAMAGE, enemy_id)
                    break

        for spawn_x, spawn_y, enemy_id, angle in pending_shots:
            update_bytes, new_projs = await self.node.projectile_handler.add_enemy_bullet(
                spawn_x, spawn_y, angle, enemy_id
            )
            if not update_bytes:
                continue
            spawn_pos = (int(spawn_x), int(spawn_y))
            for cli in self.node.clients_in_view(spawn_pos):
                await cli.write(update_bytes)
                for proj in new_projs:
                    proj["seen_by"].add(cli.user_id)
            await self.node.projectile_handler.broadcast_to_adjacent(new_projs)

        if self.node._had_viewers and not has_viewers:
            await self._cleanup_enemy_proxies()
        self.node._had_viewers = has_viewers

        if has_viewers:
            for enemy in pending_moves:
                await self.node.propagate_entity(enemy)
                for cli in self.node.clients_in_view((enemy.x, enemy.y)):
                    await cli.saw_enemy((enemy.x, enemy.y), enemy.enemy_id)

    async def _cleanup_enemy_proxies(self) -> None:
        """Remove all outgoing enemy proxies when no viewers remain,
        so adjacent nodes don't keep stale proxy entries."""
        from proxy import remove_proxy
        for enemy in self.enemies.values():
            old_dirs = getattr(enemy, "_proxied_directions", set())
            for direction in old_dirs:
                adj_pos = (
                    self.node.node_pos[0] + direction.value[0],
                    self.node.node_pos[1] + direction.value[1],
                )
                await remove_proxy(
                    self.node.node_pos, adj_pos, enemy.enemy_id, 0, type="Enemy"
                )
            enemy._proxied_directions = set()


def should_update_location(old_pos: Tuple[float, float], new_pos: Tuple[float, float], min_dst=5) -> bool:
    """returns true when the distance between the two pos are above min_dst"""
    if old_pos == new_pos:
        return False
    traveled_dst_squared = (old_pos[0] - new_pos[0]) ** 2 + (old_pos[1] - new_pos[1]) ** 2
    min_dst_squared = min_dst ** 2

    return traveled_dst_squared > min_dst_squared