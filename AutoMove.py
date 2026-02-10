import random
import heapq
from mapset import world_map, size

WALKABLE = {" ", "t", "p"}  # איפה מותר ללכת (תוסיף עוד סמלים אם יש)

def in_bounds(r, c):
    return 0 <= r < len(world_map) and 0 <= c < len(world_map[0])

def is_walkable(r, c):
    return in_bounds(r, c) and world_map[r][c] in WALKABLE

def pixel_to_tile(x, y):
    return int(y // size), int(x // size)

def tile_to_pixel_center(r, c):
    return (c * size + size // 2, r * size + size // 2)

def random_walkable_tile():
    tiles = []
    for r in range(len(world_map)):
        for c in range(len(world_map[0])):
            if is_walkable(r, c):
                tiles.append((r, c))
    return random.choice(tiles) if tiles else None

def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

def astar(start, goal):
    if start == goal:
        return [start]

    open_heap = []
    heapq.heappush(open_heap, (0, start))

    came_from = {}
    g = {start: 0}

    while open_heap:
        _, cur = heapq.heappop(open_heap)

        if cur == goal:
            # reconstruct path
            path = [cur]
            while cur in came_from:
                cur = came_from[cur]
                path.append(cur)
            path.reverse()
            return path

        r, c = cur
        for dr, dc in ((1,0), (-1,0), (0,1), (0,-1)):
            nr, nc = r + dr, c + dc
            nxt = (nr, nc)
            if not is_walkable(nr, nc):
                continue

            cand_g = g[cur] + 1
            if nxt not in g or cand_g < g[nxt]:
                g[nxt] = cand_g
                f = cand_g + manhattan(nxt, goal)
                came_from[nxt] = cur
                heapq.heappush(open_heap, (f, nxt))

    return None  # no path
