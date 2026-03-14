# Fixler the pro ᓚᘏᗢ
import pygame

from client import potion
from client.arsenal import Arsenal
from client.bullets import Bullets
from zone_connection import ZoneConnectionSingleton
from potion import Potion

class ShopUI:

    def __init__(self):
        self.open = False
        # price
        self.weapon_prices = {
            "Ak 47": 300,
            "Assault rifle": 350,
            "Pistol": 200,
            "bow": 80,
            "sword": 60,
        }

        #  bullet_name -- (price, amount)
        self.ammo_packs = {
            "Pistol bullets": (40, 15),
            "AK 47 bullets": (50, 5),
            "Assault rifle bullets": (60, 10),
            "arrows": (60, 5)
        }

        #  bullet_name -- (price)
        self.potion={
            "healing": 140,
            "speed": 70,
            "super_speed": 140
        }

        self.category = "weapon"  # current category you on: weapon or potion or ammo

        self.font_title = pygame.font.SysFont(None, 36)
        self.font = pygame.font.SysFont(None, 26)

        self.selected = None
        self.item_rects = []
        self.buy_button_rect = None
        self.bg_alpha = 180


    def all_items(self):
        items = []

        if self.category == "weapon":
            for w in self.weapon_prices:
                items.append(("weapon", w))

        elif self.category == "potion":
            for p in self.potion:
                items.append(("potion", p))

        elif self.category == "ammo":
            for b in self.ammo_packs:
                items.append(("ammo", b))

        return items

    def item_price(self, item):
        kind, name = item
        if kind == "weapon":
            return self.weapon_prices[name]
        if kind == "ammo":
            return self.ammo_packs[name][0]
        if kind == "potion":
            return self.potion[name]
        return None

    def item_title(self, item):
        kind, name = item
        if kind == "weapon":
            return name
        if kind == "ammo":
            return f"{name} x{self.ammo_packs[name][1]}"
        if kind == "potion":
            return name
        return None

    def item_icon(self, item):  # ᓚᘏᗢ
        kind, name = item

        if kind == "weapon":
            w = Arsenal(name)
            weapon_frames = w._cut_weapon_frames(w.weapon_img, w.img_num)
            img=weapon_frames[0]

        elif kind == "ammo":
            img = Bullets.bullet_types[name][0].copy()
        else:
            img = Potion.get_potion_img(name).copy()

        key = img.get_at((0, 0))[:3]
        img.set_colorkey(key)
        return img

    def toggle(self):
        self.open = not self.open
        self.item_rects = []
        self.buy_button_rect = None

        if self.open and self.selected is None:
            items = self.all_items()
            if items:
                self.selected = items[0]

    def handle_event(self, event, player):
        if not self.open:
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos

            # category tabs
            for cat, rect in getattr(self, "category_rects", []):
                if rect.collidepoint(mx, my):
                    self.category = cat
                    self.item_rects = []
                    return

            # items
            for item, rect, icon, icon_rect in self.item_rects:
                if rect.collidepoint(mx, my):
                    self.selected = item
                    return

            # buy button
            if self.buy_button_rect and self.buy_button_rect.collidepoint(mx, my):
                self.buy(player)


    def buy(self, player):
        if not self.selected:
            return

        kind, name = self.selected

        try:
            zone = ZoneConnectionSingleton().zone
        except RuntimeError:
            print("server not ok")
            return

        game = zone.game
        game.last_shop_result = None

        # can I buy pleas :c (Me asking the server)
        zone.try_to_buy(kind, name, 1)
        # The server replay on game var named: game.last_shop_result

        # waiting to server replay
        import time
        start = time.time()

        while game.last_shop_result is None:
            if time.time() - start > 1:
                print("server timeout")
                return
            time.sleep(0.01)


        print("Server say ",game.last_shop_result," to the buy!!!")
        if game.last_shop_result:
            print("buy success")

            price = self.item_price(self.selected)
            player.money -= price

            if kind == "weapon":
                player.inventory.add_item_toThe_Inventory(Arsenal(name), "weapon")

            elif kind == "ammo":
                if name not in player.ammo_collection:
                    player.ammo_collection[name] = 0

                amount = 10
                if name in self.ammo_packs:
                    amount = self.ammo_packs[name][1]

                player.ammo_collection[name] += amount

            elif kind == "potion":
                player.inventory.add_item_toThe_Inventory(Potion(name), "potion")

        else:
            print("buy failed")
        game.last_shop_result = None
    # ᓚᘏᗢ

    def draw_categories(self, screen, left):

        tabs = ["weapon", "potion", "ammo"]

        tab_w = 110
        tab_h = 36
        gap = 8

        total_w = len(tabs) * tab_w + (len(tabs) - 1) * gap
        start_x = left.centerx - total_w // 2
        y = left.y + 60

        self.category_rects = []

        mx, my = pygame.mouse.get_pos()

        for i, tab in enumerate(tabs):

            x = start_x + i * (tab_w + gap)
            rect = pygame.Rect(x, y, tab_w, tab_h)

            hovered = rect.collidepoint(mx, my)
            selected = self.category == tab

            if selected:
                color = (90, 120, 200)
            elif hovered:
                color = (70, 70, 70)
            else:
                color = (50, 50, 50)

            pygame.draw.rect(screen, color, rect, border_radius=8)
            pygame.draw.rect(screen, (200, 200, 200), rect, 2, border_radius=8)

            text = self.font.render(tab.upper(), True, (255, 255, 255))
            screen.blit(text, text.get_rect(center=rect.center))

            self.category_rects.append((tab, rect))


    def build_grid(self, left):
        if self.item_rects:
            return

        padding = 14
        card_w = 104
        card_h = 104
        icon_size = 80
        cols = 3
        # ᓚᘏᗢ
        x0 = left.x + padding
        y0 = left.y + 130  # lower then titel

        items = self.all_items()
        for i, item in enumerate(items):
            col = i % cols
            row = i // cols

            x = x0 + col * (card_w + padding)
            y = y0 + row * (card_h + padding)

            card_rect = pygame.Rect(x, y, card_w, card_h)

            icon = self.item_icon(item)

            min_icon = 56

            iw, ih = icon.get_size()
            max_w = card_rect.w - 16
            max_h = card_rect.h - 28

            scale_up = min_icon / max(iw, ih)
            scale_fit = min(max_w / iw, max_h / ih)
            scale = min(max(scale_up, 1.0), scale_fit)

            new_w = max(1, int(iw * scale))
            new_h = max(1, int(ih * scale))

            icon = pygame.transform.scale(icon, (new_w, new_h))

            # center
            icon_rect = icon.get_rect(
                centerx=card_rect.centerx,
                centery=card_rect.y + max_h // 2 + 8
            )

            self.item_rects.append((item, card_rect, icon, icon_rect))

    def get_item_stats(self, item):
        kind, name = item

        if kind == "weapon":
            data = Arsenal.Arsenal_gunType[name]
            bullet = data[1]
            mag = data[5]
            cooldown = data[6]
            damage = data[7] if len(data) >= 8 else 0

            return [
                f"Type: Weapon",
                f"Damage: {damage}",
                f"Magazine: {mag}",
                f"Cooldown: {cooldown} ms",
                f"Bullet: {bullet}",
            ]

        # ammo
        if kind == "ammo":
            price, amount = self.ammo_packs[name]
            bullet_damage = Bullets.bullet_types[name][4]

            return [  # ᓚᘏᗢ
                "Type: Ammo",  # ᓚᘏᗢ
                f"Bullet: {name}",  # ᓚᘏᗢ
                f"Adds: {amount}",  # ᓚᘏᗢ
                f"Bullet damage: {bullet_damage}",  # ᓚᘏᗢ
            ]

        if kind == "potion":
            price= self.potion[name]

            return [  # ᓚᘏᗢ
                "Type: Potion",  # ᓚᘏᗢ
                f"Effect: {name} potion",  # ᓚᘏᗢ
                f"Adds: {1}",  # ᓚᘏᗢ
                f"Time last: {Potion.effect_time(name)}",  # ᓚᘏᗢ
            ]

    # -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-#
    # -=-=-=-=-=-=-=-=-draw=-=-=-=-=-=-=-=-=-=-#
    # -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-#
    def draw(self, screen, player):
        if not self.open:
            return
        # ᓚᘏᗢ
        w, h = screen.get_size()

        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, self.bg_alpha))
        screen.blit(overlay, (0, 0))
        # ᓚᘏᗢ
        panel = pygame.Rect(80, 60, w - 160, h - 120)
        pygame.draw.rect(screen, (25, 25, 25), panel, border_radius=16)
        pygame.draw.rect(screen, (80, 80, 80), panel, 2, border_radius=16)

        left = pygame.Rect(panel.x + 16, panel.y + 16, int(panel.w * 0.42), panel.h - 32)
        right = pygame.Rect(left.right + 16, panel.y + 16,
                            panel.right - (left.right + 32), panel.h - 32)

        pygame.draw.rect(screen, (32, 32, 32), left, border_radius=14)
        pygame.draw.rect(screen, (32, 32, 32), right, border_radius=14)

        self.draw_categories(screen, left)
        # -=-=-=-=-=-=-titale-=-=-=-=-=-#
        title = self.font_title.render("SHOP", True, (255, 255, 255))
        screen.blit(title, (left.x + 12, left.y + 12))

        money = self.font.render(f"Money: {player.money}$", True, (220, 220, 220))
        screen.blit(money, (left.x + 12, left.y + 38))

        # -=-=-=-=-=-=-GREED-=-=-=-=-=-#
        self.build_grid(left)  # ᓚᘏᗢ
        mx, my = pygame.mouse.get_pos()

        for item, rect, icon, icon_rect in self.item_rects:
            hovered = rect.collidepoint(mx, my)
            selected = (item == self.selected)

            # -=-=-=-=-=-=-card bg-=-=-=-=-=-#
            bg = (44, 44, 44) if (hovered or selected) else (36, 36, 36)
            border = (255, 255, 255) if selected else ((170, 170, 170) if hovered else (90, 90, 90))

            pygame.draw.rect(screen, bg, rect, border_radius=12)
            pygame.draw.rect(screen, border, rect, 2, border_radius=12)

            screen.blit(icon, icon_rect.topleft)

            # -=-=-=-=-=-=-price-=-=-=-=-=-#
            price = self.item_price(item)
            badge_txt = self.font.render(f"{price}$", True, (245, 245, 245))
            badge_pad_x = 8
            badge_pad_y = 4
            badge_rect = badge_txt.get_rect()
            badge_rect.topright = (rect.right - 6, rect.top + 6)
            badge_rect.inflate_ip(badge_pad_x * 2, badge_pad_y * 2)

            pygame.draw.rect(screen, (20, 20, 20), badge_rect, border_radius=10)
            pygame.draw.rect(screen, (120, 120, 120), badge_rect, 1, border_radius=10)
            screen.blit(badge_txt, badge_txt.get_rect(center=badge_rect.center))

            # -----name-----#
            kind, name = item
            if kind == "weapon":
                label=  "weapon"

            elif kind == "ammo":
                label=  "AMMO"

            elif kind == "potion":
                label = "POTION"
            else:
                label = "UNKNOWN"

            label_txt = self.font.render(label, True, (210, 210, 210))
            label_rect = label_txt.get_rect(midbottom=(rect.centerx, rect.bottom - 6))
            screen.blit(label_txt, label_rect)

        # -------right panel----------#
        if not self.selected:
            return

        name_txt = self.font_title.render(self.item_title(self.selected), True, (255, 255, 255))
        screen.blit(name_txt, (right.x + 16, right.y + 14))

        img = self.item_icon(self.selected)
        ow, oh = img.get_size()

        scale = min(260 / ow, 220 / oh)
        scale = min(scale, 3)

        img = pygame.transform.smoothscale(img, (int(ow * scale), int(oh * scale)))

        img_rect = img.get_rect(topleft=(right.x + 16, right.y + 60))
        bg = img_rect.inflate(20, 20)

        pygame.draw.rect(screen, (45, 45, 45), bg, border_radius=14)
        pygame.draw.rect(screen, (90, 90, 90), bg, 2, border_radius=14)
        screen.blit(img, img_rect.topleft)

        # ------------stats--------------#
        stats = self.get_item_stats(self.selected)

        gap = 26
        sy = img_rect.bottom + 20
        sx = img_rect.left

        for i, line in enumerate(stats):
            txt = self.font.render(line, True, (230, 230, 230))
            screen.blit(txt, (sx, sy + i * gap))

        # ---------buy-----------#
        price = self.item_price(self.selected)
        y = right.bottom - 90
        price_txt = self.font_title.render(f"{price}$", True, (255, 255, 255))
        screen.blit(price_txt, (right.x + 16, y))

        can_buy = player.money >= price
        self.buy_button_rect = pygame.Rect(right.right - 236, y, 220, 52)

        color = (60, 160, 60) if can_buy else (120, 60, 60)
        pygame.draw.rect(screen, color, self.buy_button_rect, border_radius=12)
        pygame.draw.rect(screen, (220, 220, 220), self.buy_button_rect, 2, border_radius=12)

        label = "BUY" if can_buy else "NOT ENOUGH $"
        txt = self.font_title.render(label, True, (255, 255, 255))
        screen.blit(txt, txt.get_rect(center=self.buy_button_rect.center))
