import pygame

from paths import resource_path


class Animation:
    def __init__(
        self,
        sheet_path: str,
        frame_w: int,
        frame_h: int,
        rows: dict,
        frames_per_row: dict,
        *,
        scale: int = 1,
        colorkey="AUTO",
        margin: int = 0,
        spacing: int = 0,
        speed_ms: int = 120
    ):
        # --- THE FIX IS HERE: Wrapped sheet_path with resource_path ---
        self.sheet = pygame.image.load(resource_path(sheet_path)).convert()
        self.no_loop = {"dead"}

        if colorkey == "AUTO":
            self.colorkey = self.sheet.get_at((0, 0))
        else:
            self.colorkey = colorkey

        self.frame_w = frame_w
        self.frame_h = frame_h
        self.scale = scale
        self.margin = margin
        self.spacing = spacing

        self.animations = {}
        for name, row_idx in rows.items():
            self.animations[name] = self._cut_row(row_idx, frames_per_row[name])

        self.state = next(iter(self.animations.keys()))
        self.index = 0
        self.speed_ms = speed_ms
        self.last_time = pygame.time.get_ticks()

    def _cut_row(self, row_idx: int, count: int):
        frames = []
        sheet_w = self.sheet.get_width()
        y = self.margin + row_idx * (self.frame_h + self.spacing)

        for i in range(count):
            x = self.margin + i * (self.frame_w + self.spacing)

            if x + self.frame_w > sheet_w:
                break

            frame = pygame.Surface((self.frame_w, self.frame_h)).convert()
            frame.blit(self.sheet, (0, 0), (x, y, self.frame_w, self.frame_h))
            frame.set_colorkey(self.colorkey)

            if self.scale != 1:
                frame = pygame.transform.scale(
                    frame, (self.frame_w * self.scale, self.frame_h * self.scale)
                )

            frames.append(frame)

        return frames

    def set_state(self, state: str):
        if state != self.state:
            self.state = state
            self.index = 0

    def update(self):
        now = pygame.time.get_ticks()

        if now - self.last_time >= self.speed_ms:
            self.last_time = now
            frames = len(self.animations[self.state])
            if self.state in self.no_loop:
                if self.index < frames - 1:
                    self.index += 1
            else:
                self.index = (self.index + 1) % frames

    def image(self, flip_x: bool = False):
        img = self.animations[self.state][self.index]
        if not flip_x:
            img = pygame.transform.flip(img, True, False)
        return img