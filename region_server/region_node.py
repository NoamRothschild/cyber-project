from __future__ import annotations
from typing import Any, Dict, Tuple
from projectiles import ProjectileHandler


class RegionNode:
    """A region with a bounding box, its players and projectiles. Packable-friendly."""

    def __init__(
        self,
        x_range: Tuple[int, int],
        y_range: Tuple[int, int],
    ) -> None:
        self.x_range = x_range
        self.y_range = y_range
        self.clients: Dict[int, Any] = {}  # session_id -> Client
        self.projectile_handler = ProjectileHandler(self)

    def contains(self, x: int, y: int) -> bool:
        """True if (x, y) is inside this node's bounds."""
        return (
            self.x_range[0] <= x <= self.x_range[1]
            and self.y_range[0] <= y <= self.y_range[1]
        )
