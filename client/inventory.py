import pygame
from mapset import WIDTH, HEIGHT
from mapset import *
from arsenal import *
import time
from zone_connection import *
from colectibes import Colectible_sprite, Mony
import os
import sys

# ==========================================
# --- THE TRANSLATOR---
# This dictionary will map the database numbers to Pygame strings.
# ==========================================
# Our SQLite database only stores integers (1, 2, 3) to save space.
# But Pygame needs the exact string name ("Ak 47") to load the image and stats.
# When the server sends the Handshake packet with our saved loadout,
# the client uses these maps to translate the DB numbers back into actual items.

# maps database magic numbers to weapon names
WEAPON_MAP = {
    1: "Ak 47",
    2: "bow",
    3: "sword",
    4: "Assault rifle",
    5: "Pistol"
}

# maps database magic numbers to potion names
POTION_MAP = {
    1: "healing",
    2: "speed",
    3: "super_speed"
}

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class Inventory(pygame.sprite.Sprite):

    def __init__(self):
        super().__init__()
        self.image = pygame.image.load(resource_path('inventory.png')).convert()
        self.image.set_colorkey(PINK)  # image background
        self.rect = self.image.get_rect()
        self.rect.y = HEIGHT - (self.rect.height)
        self.rect.x = WIDTH / 2 - (self.rect.width / 2)
        self.display = pygame.display.get_surface()

        # Lists
        self.wep_inventory = []
        self.potion_inventory = []
        self.current_weapon = 0
        self.delete_last_action_time = time.time()
        self.delete_interval = 0.5
        self.money = 200

    def add_item_toThe_Inventory(self, item, kind):
        if kind == "potion":
            self.potion_inventory.append(item)
        elif kind == "weapon":
            self.wep_inventory.append(item)
        elif kind == "money":
            self.money += 50
    def items_hendeling(self, player):
        if not self.is_wep_empty():
            self.wep_inventory[self.current_weapon].draw(WIDTH / 2, HEIGHT / 2)

    # (Note: items_hendeling was removed because player.py handles drawing now!)

    def open(self, group, player):
        self.display.blit(self.image, self.rect)
        prect = player.rect

        for i, wep in enumerate(self.wep_inventory):
            wep.draw_for_inventory(i, self.rect.x, self.rect.y)

        for i, potion in enumerate(self.potion_inventory):
            potion.draw_for_inventory(i, self.rect.x, self.rect.y)

        self.use(group, prect)
        self.use_potion(player)

    def is_wep_empty(self):
        return len(self.wep_inventory) == 0
    def is_wep_in_1(self):
        return len(self.wep_inventory) == 1

    def is_potion_empty(self):
        return len(self.potion_inventory) == 0

    def use(self, group, prect):
        keys = pygame.key.get_pressed()

        # --- HOTBAR WEAPON SWAPPING ---
        # Loops through the number keys (1-9, 0).
        # If the player presses '2', it sets the current_weapon index to 1.
        # This index matches exactly with the server's parallel lists!
        for i in range(10):
            key_constant = getattr(pygame, f"K_{i}")
            if keys[key_constant] and i - 1 != self.current_weapon and i - 1 < len(self.wep_inventory) and not keys[pygame.K_p]:
                self.current_weapon = i - 1
        if keys[pygame.K_DELETE] and not keys[pygame.K_p] and not keys[pygame.K_m]  and self.is_wep_in_1() == False:
            self.delete_w(group, prect)
        self.delete_p()
        self.delete_mony()

    def drop_all_items(self, group, prect):
        """Drop all carried items into the world (local-only helper; currently unused)."""
        import random

        # Weapons
        for weapon in self.wep_inventory:
            x = prect.centerx + random.randint(-120, 120)
            y = prect.centery + random.randint(-120, 120)
            Colectible_sprite(
                (x, y),
                group,
                weapon.get_name(),
                "weapon",
                weapon.id,
                getattr(weapon, "mag", None),
            )

        # Potions
        for potion in self.potion_inventory:
            x = prect.centerx + random.randint(-120, 120)
            y = prect.centery + random.randint(-120, 120)
            Colectible_sprite(
                (x, y),
                group,
                potion.get_name(),
                "potion",
                potion.id,
            )

        self.wep_inventory.clear()
        self.potion_inventory.clear()

    def delete_w(self, group, prect):
        """Drop the currently selected weapon: tell the server and remove from inventory."""
        current_time = time.time()
        if (
            current_time - self.delete_last_action_time >= self.delete_interval
            and not self.is_wep_empty()
        ):
            dropped_wep = self.wep_inventory[self.current_weapon]
            # Inform the region server so it can spawn the dropped weapon as an item
            ZoneConnectionSingleton().zone.try_send_item(
                "weapon", dropped_wep.get_name(), dropped_wep.id
            )

            del self.wep_inventory[self.current_weapon]
            if self.current_weapon != 0:
                self.current_weapon -= 1
            self.delete_last_action_time = current_time
    def delete_mony(self):
        keys = pygame.key.get_pressed()
        current_time = time.time()
        if keys[pygame.K_m] and keys[pygame.K_DELETE] and self.money >= 50 and current_time - self.delete_last_action_time >= self.delete_interval :
            self.money -= 50
            ZoneConnectionSingleton().zone.try_send_item("money", "money",Mony().id )
            self.delete_last_action_time = current_time
    def delete_p(self):
        keys = pygame.key.get_pressed()
        if keys[pygame.K_p] and keys[pygame.K_DELETE]:
            for i in range(10):
                key_constant = getattr(pygame, f"K_{i}")
                if keys[key_constant] and i - 1 < len(self.potion_inventory) and self.potion_inventory[
                    i - 1].is_potion_is == False:
                    current_time = time.time()
                    if current_time - self.delete_last_action_time >= self.delete_interval and self.is_potion_empty() == False:
                        ZoneConnectionSingleton().zone.try_send_item("potion", self.potion_inventory[i-1].get_name(),self.potion_inventory[i-1].id)
                        del self.potion_inventory[i-1]
                        self.delete_last_action_time = current_time
    def use_potion(self, player):
        keys = pygame.key.get_pressed()
        if keys[pygame.K_p] and not keys[pygame.K_DELETE]:
            for i in range(10):
                key_constant = getattr(pygame, f"K_{i}")
                if keys[key_constant] and i - 1 < len(self.potion_inventory) and self.potion_inventory[
                    i - 1].is_potion_is == False:
                    print("hii")
                    self.potion_inventory[i - 1].purpose(player)
                    self.potion_inventory[i - 1].creat_bar((i - 1),self.rect.bottomleft)

        for i in range(10):
            if i < len(self.potion_inventory) and not self.is_potion_empty():
                if self.potion_inventory[i].should_it_stop(player):
                    del self.potion_inventory[i]