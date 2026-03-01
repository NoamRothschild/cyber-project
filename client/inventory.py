import pygame
from mapset import WIDTH,HEIGHT
from mapset import *
from arsenal import *

# ==========================================
# --- THE TRANSLATOR (ROSETTA STONE) ---
# This dictionary will map the database numbers to Pygame strings.
# ==========================================
WEAPON_MAP = {
    1: "Ak-7",
}

class Inventory(pygame.sprite.Sprite):

    def __init__(self):
        super().__init__()
        self.image = pygame.image.load('inventory.png').convert()
        self.image.set_colorkey(PINK)#image background
        self.rect = self.image.get_rect()
        self.rect.y=HEIGHT-(self.rect.height)
        self.rect.x=WIDTH/2-(self.rect.width/2)#putting the inventory in a specific place
        self.display = pygame.display.get_surface()
        #self.unused_weapons=pygame.sprite.Group()
        #self.potions=pygame.sprite.Group()

        # --- FIX 1: Start with an empty inventory ---
        # The database will fill this up later.
        self.inventory = []
        self.inventory_pointer = 0

    def add_item_toThe_Inventory(self, item):
        self.inventory.append(item)

    def items_hendeling(self, player):
        # --- FIX 2: Safe Drawing Logic ---
        # Only try to draw an Arsenal object if the player actually has a weapon.
        # This prevents the game from crashing if the list is empty [].
        if len(self.inventory) > 0:
            current_weapon = self.inventory[self.inventory_pointer]
            Arsenal(current_weapon).draw(WIDTH/2,HEIGHT/2)

    def open(self):
        self.display.blit(self.image, self.rect)
        self.use()#prints inventory

    def use(self):#jast a simple check of wht weapon are you choosing
        keys = pygame.key.get_pressed()
        if keys[pygame.K_p] and keys[pygame.K_1]:
            print("P and 1 are being pressed together!")