import pygame

from paths import resource_path


class WeaponAnim:
    def __init__(self, sheet_path: str, frames: int, *, scale: float = 1.0, speed_ms: int = 35, colorkey="AUTO"):
        self.sheet = pygame.image.load(resource_path(sheet_path)).convert_alpha()

        if colorkey == "AUTO":
            self.colorkey = self.sheet.get_at((0, 0))
        else:
            self.colorkey = colorkey

        self.sheet.set_colorkey(self.colorkey)

        self.frames = self._cut_single_row(frames, scale)

        self.state = "idle"
        self.i = 0
        self.speed_ms = speed_ms
        self.last = pygame.time.get_ticks()

        # shoot parameters
        self.shoot_start = 0
        self.shoot_end = len(self.frames)
        self.shoot_loop = False

    def _cut_single_row(self, frames: int, scale: float):
        w = self.sheet.get_width()
        h = self.sheet.get_height()
        frame_w = w // frames
        frame_h = h

        out = []
        for idx in range(frames):
            x = idx * frame_w
            frame = pygame.Surface((frame_w, frame_h), pygame.SRCALPHA).convert_alpha()
            frame.blit(self.sheet, (0, 0), (x, 0, frame_w, frame_h))
            frame.set_colorkey(self.colorkey)

            if scale != 1.0:
                frame = pygame.transform.scale(frame, (int(frame_w * scale), int(frame_h * scale)))

            out.append(frame)
        return out

    def play_shoot(self):
        self.state = "shoot"
        self.i = self.shoot_start

    def update(self):
        now = pygame.time.get_ticks()
        if now - self.last < self.speed_ms:
            return
        self.last = now

        if self.state == "idle":
            self.i = 0
            return

        # shoot
        self.i += 1
        if self.i >= self.shoot_end:
            self.state = "idle"
            self.i = 0

    def image(self):
        return self.frames[self.i]