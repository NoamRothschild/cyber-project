from client.Arsenal import *
from client.Arsenal import Arsenal
from client.Inventory import *
from client.bullets import *
from client.domain_Expansion import *
from shop import ShopUI

PINK = (234, 54, 128)



class Player(pygame.sprite.Sprite):
    def __init__(self, pos, groups, obstacle_sprites):
        super().__init__(groups)
        self.display_surface = pygame.display.get_surface()
        self.screen_scroll = [0, 0]

        self.image = pygame.image.load('player.png').convert_alpha()
        self.image.set_colorkey(PINK)
        self.rect = self.image.get_rect(topleft=pos)
        self.hitbox = self.rect.inflate(-20, -10)
        self.speed = 4
        self.direction = pygame.math.Vector2()
        self.obstacle_sprites = obstacle_sprites

        self.last_r_press = 0
        self.last_shoot = 0

        self.shop_open = False
        self.last_b_press = 0

        self.money = 200
        self.shop_ui = ShopUI()

        self.ammo_collection = {
            "AK-7_bullet": 1,
            "arrow": 1
        }

        self.inventory = Inventory()
        self.inventory.add_item_toThe_Inventory(Arsenal("Ak-7"), "weapon")
        self.inventory.add_item_toThe_Inventory(Arsenal("rock"), "weapon")
        self.inventory.add_item_toThe_Inventory(Arsenal("bow"), "weapon")
        self.inventory.add_item_toThe_Inventory(Arsenal("sword"), "weapon")
        self.inventory.add_item_toThe_Inventory(Potion("super_speed"), "potion")
        self.inventory.add_item_toThe_Inventory(Arsenal("domain_expansion"), "weapon")

    def current_Weapon(self):
        return self.inventory.wep_inventory[self.inventory.current_weapon]

    def input(self):
        keys = pygame.key.get_pressed()

        if self.shop_ui.open:
            self.direction.x = 0
            self.direction.y = 0

            if keys[pygame.K_b]:
                now = pygame.time.get_ticks()
                if now - self.last_b_press > 300:
                    self.last_b_press = now
                    self.shop_ui.toggle()
            return

        if keys[pygame.K_UP] or keys[pygame.K_w]:
            self.direction.y = -1
            self.screen_scroll[1] -= self.speed

        elif keys[pygame.K_DOWN] or keys[pygame.K_s]:
            self.direction.y = 1
            self.screen_scroll[1] += self.speed
        else:
            self.direction.y = 0

        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.direction.x = -1
            self.screen_scroll[0] -= self.speed

        elif keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.direction.x = 1
            self.screen_scroll[0] += self.speed
        else:
            self.direction.x = 0

        if keys[pygame.K_b]:
            now = pygame.time.get_ticks()
            if now - self.last_b_press > 300:
                self.last_b_press = now
                self.shop_ui.toggle()

        if keys[pygame.K_r]:
            w = self.current_Weapon()
            now = pygame.time.get_ticks()
            if now - self.last_r_press >= w.fire_cooldown:
                self.last_r_press = now

                if w.bullet == "null":
                    w.refill_mag()
                else:
                    capability = Arsenal.Arsenal_gunType[w.gun_type][5]
                    need = max(0, capability - w.mag)
                    have = self.ammo_collection.get(w.bullet, 0)
                    take = min(need, have)

                    w.mag += take
                    self.ammo_collection[w.bullet] = have - take

        mouse_buttons = pygame.mouse.get_pressed()

        if mouse_buttons[0] and not self.inventory.is_wep_empty():
            try:
                if self.current_Weapon().mag > 0:

                    now = pygame.time.get_ticks()
                    if now - self.last_shoot >= self.current_Weapon().fire_cooldown:
                        self.last_shoot = now

                        mouse_x, mouse_y = pygame.mouse.get_pos()
                        Bullets.BulletLS.append(
                            Bullets(
                                self.current_Weapon(),
                                self.display_surface.get_width() / 2,
                                self.display_surface.get_height() / 2,
                                mouse_x,
                                mouse_y,
                                self.screen_scroll
                            )
                        )
                        self.current_Weapon().mag -= 1
            except:
                print("error")

            if self.current_Weapon().gun_type == "domain_expansion":
                Domain_Expansion.run(self)
                # Level.Domain_Expansion_ls.append("h")
                # self.inventory.delete() delet from inventory when it used

    def move(self):
        if self.direction.magnitude() != 0:
            self.direction = self.direction.normalize()
        self.hitbox.x += int(self.direction.x * self.speed)
        self.check_coalition("horizontal")
        self.hitbox.y += int(self.direction.y * self.speed)
        self.check_coalition("vertical")
        self.rect.center = self.hitbox.center

    def check_coalition(self, direction):
        if direction == 'horizontal':
            for sprite in self.obstacle_sprites:
                if sprite.rect.colliderect(self.hitbox):
                    if self.direction.x > 0:
                        self.hitbox.right = sprite.rect.left
                    elif self.direction.x < 0:
                        self.hitbox.left = sprite.rect.right
        if direction == 'vertical':
            for sprite in self.obstacle_sprites:
                if sprite.rect.colliderect(self.hitbox):
                    if self.direction.y > 0:
                        self.hitbox.bottom = sprite.rect.top
                    elif self.direction.y < 0:
                        self.hitbox.top = sprite.rect.bottom

    def check_if_collect(self, collecters):
        for sprite in collecters:
            if sprite.rect.colliderect(self.hitbox):
                if sprite.kind == "weapon":
                    self.inventory.add_item_toThe_Inventory(sprite.obj, "weapon")
                elif sprite.kind == "potion":
                    self.inventory.add_item_toThe_Inventory(sprite.obj, "potion")
                sprite.kill()
                break

    def update(self, collecters):
        self.input()
        draw_AND_update_Bullets(self)
        self.current_Weapon().draw_mag_stat()
        self.shop_ui.draw(self.display_surface, self)

        self.move()
        self.check_if_collect(collecters)
        self.inventory.open([self.groups()[0], collecters], self.rect, self)
