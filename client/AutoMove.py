# AutoMove.py
import random
import heapq
import mapset
import math
import pygame
WALKABLE = {" ", "p"}

def in_bounds(r, c):
    return 0 <= r < len(mapset.world_map) and 0 <= c < len(mapset.world_map[0])

def is_walkable(r, c):
    return in_bounds(r, c) and (mapset.world_map[r][c]==None or (not mapset.world_map[r][c].colliderect(pygame.Rect(c * mapset.SIZE, r * mapset.SIZE, 32, 32))))

def pixel_to_tile(x, y):
    r = math.floor(y / mapset.SIZE)
    c = math.floor(x / mapset.SIZE)
    return r, c
def tile_to_pixel_center(r, c):
    return (c * mapset.SIZE + mapset.SIZE//2, r * mapset.SIZE + mapset.SIZE//2)

def random_walkable_tile(margin=1):
    rows = len(mapset.world_map)
    cols = len(mapset.world_map[0])
    cells = []
    for r in range(margin, rows - margin):
        for c in range(margin, cols - margin):
            if is_walkable(r, c):
                cells.append((r, c))
    return random.choice(cells) if cells else None

def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

def astar(start, goal):
    if start == goal:
        return [start]

    open_heap = []
    heapq.heappush(open_heap, (0, start))
    count=0
    came = {}
    g = {start: 0}

    while open_heap:
        _, cur = heapq.heappop(open_heap)
        if cur == goal:
            path = [cur]
            while cur in came:
                cur = came[cur]
                path.append(cur)
            path.reverse()
            return path

        r, c = cur
        for dr, dc in ((1,0),(-1,0),(0,1),(0,-1)):
            nr, nc = r + dr, c + dc
            nxt = (nr, nc)
            if not is_walkable(nr, nc):
                continue

            cand = g[cur] + 1
            if nxt not in g or cand < g[nxt]:
                g[nxt] = cand
                f = cand + manhattan(nxt, goal)
                came[nxt] = cur
                heapq.heappush(open_heap, (f, nxt))

    return None

def map_pixel_bounds():
    map_w = len(mapset.world_map[0]) * mapset.SIZE
    map_h = len(mapset.world_map) * mapset.SIZE
    return 0, 0, map_w, map_h