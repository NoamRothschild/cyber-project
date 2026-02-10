# Shop.py
import pygame
from Arsenal import Arsenal


class ShopUI:
    def __init__(self):
        self.open = False

        # weapon_name <---> price
        self.shop = {
            "Ak-7": 120,
            "bow": 80,
            "sword": 60,
            "rock": 10,
            "domain_expansion": 500
        }

        self.font_title = pygame.font.SysFont(None, 36)
        self.font = pygame.font.SysFont(None, 26)

        self.selected = None
        self.item_rects = []  # (weapon_name, rect, icon_surface)
        self.bg_alpha = 180

        self.buy_button_rect = None

        # no bullet weapons - dameg
        self.melee_damage = {
            "sword": 10,
            "rock": 2,
            "domain_expansion": 999
        }

        # (image, offset, ttl, speed, damage, scale) -> אנחנו משתמשים רק ב-damage
        self.bullet_types = {
            "AK-7_bullet": (None, None, 20, 25, 2, 0.2),
            "arrow": (None, None, 50, 20, 5, 1)
        }

    def toggle(self):
        self.open = not self.open

        # כשפותחים פעם ראשונה - לבחור אייטם ראשון אם אין
        if self.open and self.selected is None and len(self.shop) > 0:
            self.selected = next(iter(self.shop.keys()))

        # לאפס גריד אם צריך לבנות מחדש
        if not self.open:
            self.buy_button_rect = None

    def _get_weapon_damage(self, weapon_name: str) -> int:
        bullet_name = Arsenal.Arsenal_gunType[weapon_name][1]
        if bullet_name == "null":
            return self.melee_damage.get(weapon_name, 0)
        if bullet_name in self.bullet_types:
            return self.bullet_types[bullet_name][4]
        return 0

    def _get_stats(self, weapon_name: str) -> dict:
        weapon_img, bullet, movement, coords, scale, mag, cooldown = Arsenal.Arsenal_gunType[weapon_name]
        dmg = self._get_weapon_damage(weapon_name)
        return {
            "damage": dmg,
            "mag": mag,
            "cooldown_ms": cooldown,
            "bullet": bullet,
            "movement": movement
        }

    def _build_item_grid(self, left_rect):
        if self.item_rects:
            return

        padding = 12
        icon_size = 56
        cols = 3

        price_h = 22  # מקום לטקסט מחיר
        cell_h = icon_size + price_h + padding  # גובה תא מלא

        x0 = left_rect.x + padding
        y0 = left_rect.y + 60

        i = 0
        for weapon_name in self.shop.keys():
            base = Arsenal.Arsenal_gunType[weapon_name][0].copy()

            # colorkey לכל האייקונים (כדי שלא יהיה רקע כחול)
            key = base.get_at((0, 0))[:3]  # צבע פינה-שמאל-עליון (עובד גם אם לא אחיד אצל כולם)
            base.set_colorkey(key)

            icon = pygame.transform.smoothscale(base, (icon_size, icon_size))

            col = i % cols
            row = i // cols

            x = x0 + col * (icon_size + padding)
            y = y0 + row * cell_h
            rect = pygame.Rect(x, y, icon_size, icon_size)

            self.item_rects.append((weapon_name, rect, icon))
            i += 1

        if self.selected is None and len(self.shop) > 0:
            self.selected = next(iter(self.shop.keys()))

    def handle_event(self, event, player):
        if not self.open:
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos

            # בחירת נשק מהגריד
            for weapon_name, rect, _icon in self.item_rects:
                if rect.collidepoint(mx, my):
                    self.selected = weapon_name
                    return

            # לחיצה על BUY
            if self.selected is not None and self.buy_button_rect is not None:
                if self.buy_button_rect.collidepoint(mx, my):
                    self.try_buy(player, self.selected)

    def try_buy(self, player, weapon_name: str):
        price = self.shop.get(weapon_name)
        if price is None:
            return
        if player.money < price:
            return

        player.money -= price
        player.inventory.add_item_toThe_Inventory(Arsenal(weapon_name))

    def draw(self, screen, player):
        if not self.open:
            return

        w, h = screen.get_size()

        # overlay
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, self.bg_alpha))
        screen.blit(overlay, (0, 0))

        # panel
        panel = pygame.Rect(80, 60, w - 160, h - 120)
        pygame.draw.rect(screen, (25, 25, 25), panel, border_radius=16)
        pygame.draw.rect(screen, (80, 80, 80), panel, 2, border_radius=16)

        left = pygame.Rect(panel.x + 16, panel.y + 16, int(panel.w * 0.42), panel.h - 32)
        right = pygame.Rect(left.right + 16, panel.y + 16, panel.right - (left.right + 32), panel.h - 32)

        pygame.draw.rect(screen, (32, 32, 32), left, border_radius=14)
        pygame.draw.rect(screen, (32, 32, 32), right, border_radius=14)

        # headers
        title = self.font_title.render("SHOP", True, (255, 255, 255))
        screen.blit(title, (left.x + 12, left.y + 12))

        money_txt = self.font.render(f"Money: {player.money}$", True, (220, 220, 220))
        screen.blit(money_txt, (left.x + 12, left.y + 38))

        # grid (build once)
        self._build_item_grid(left)

        # draw grid items
        for weapon_name, rect, icon in self.item_rects:
            screen.blit(icon, rect.topleft)

            if weapon_name == self.selected:
                pygame.draw.rect(screen, (255, 255, 255), rect, 3, border_radius=8)
            else:
                pygame.draw.rect(screen, (120, 120, 120), rect, 2, border_radius=8)

            price = self.shop[weapon_name]
            ptxt = self.font.render(f"{price}$", True, (200, 200, 200))

            ptxt = self.font.render(f"{price}$", True, (200, 200, 200))
            ptxt_rect = ptxt.get_rect(midtop=(rect.centerx, rect.bottom + 4))
            screen.blit(ptxt, ptxt_rect)

        # right side details
        if self.selected is None:
            return

        weapon_name = self.selected
        price = self.shop[weapon_name]
        stats = self._get_stats(weapon_name)

        name_txt = self.font_title.render(weapon_name, True, (255, 255, 255))
        screen.blit(name_txt, (right.x + 16, right.y + 14))

        # ==== BIG IMAGE (KEEP RATIO + COLORKEY) ====
        # ==== BIG IMAGE (KEEP RATIO + COLORKEY) ====
        img = Arsenal.Arsenal_gunType[weapon_name][0].copy()

        key = img.get_at((0, 0))[:3]
        img.set_colorkey(key)

        orig_w, orig_h = img.get_size()

        MAX_W = 260
        MAX_H = 220
        scale = min(MAX_W / orig_w, MAX_H / orig_h, 1)
        new_w = int(orig_w * scale)
        new_h = int(orig_h * scale)

        big = pygame.transform.smoothscale(img, (new_w, new_h))
        big_rect = big.get_rect(topleft=(right.x + 16, right.y + 60))

        # ✅ מלבן “קצת החוצה” סביב הרובה
        pad = 10  # כמה שיבלוט החוצה
        bg_rect = big_rect.inflate(pad * 2, pad * 2)

        pygame.draw.rect(screen, (45, 45, 45), bg_rect, border_radius=14)  # מילוי
        pygame.draw.rect(screen, (90, 90, 90), bg_rect, 2, border_radius=14)  # מסגרת דקה

        screen.blit(big, big_rect.topleft)

        # ==== STATS (MORE SPACING, EACH ON ITS OWN LINE) ====
        sx = big_rect.right + 32
        sy = big_rect.y + 10
        LINE_GAP = 36

        def stat_line(label, value, i):
            t = self.font.render(f"{label}: {value}", True, (235, 235, 235))
            screen.blit(t, (sx, sy + i * LINE_GAP))

        stat_line("Damage", stats["damage"], 0)
        stat_line("Magazine", stats["mag"], 1)
        stat_line("Cooldown", f"{stats['cooldown_ms']} ms", 2)
        stat_line("Bullet type", stats["bullet"], 3)
        stat_line("Movement", stats["movement"], 4)

        # price + buy button
        bottom_y = right.bottom - 90

        price_txt = self.font_title.render(f"{price}$", True, (255, 255, 255))
        screen.blit(price_txt, (right.x + 16, bottom_y))

        can_afford = player.money >= price

        btn_w, btn_h = 220, 52
        self.buy_button_rect = pygame.Rect(right.right - btn_w - 16, bottom_y, btn_w, btn_h)

        btn_color = (60, 160, 60) if can_afford else (120, 60, 60)
        pygame.draw.rect(screen, btn_color, self.buy_button_rect, border_radius=12)
        pygame.draw.rect(screen, (220, 220, 220), self.buy_button_rect, 2, border_radius=12)

        btn_label = "BUY" if can_afford else "NOT ENOUGH $"
        txt = self.font_title.render(btn_label, True, (255, 255, 255))
        txt_rect = txt.get_rect(center=self.buy_button_rect.center)
        screen.blit(txt, txt_rect)
