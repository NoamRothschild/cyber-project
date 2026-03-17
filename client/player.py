from health import HealthBar
from inventory import *
from arsenal import Arsenal
from bullets import Bullets
from zone_connection import ZoneConnectionSingleton
from zone_connection import *
from game import *
from zone_connection import ZoneConnectionSingleton
from mapset import *
from inventory import Inventory
from bullets import *
from shop import ShopUI
from potion import Potion
from animation import Animation
import os
import sys
from AutoPlay import AutoMove as AutoMoveController
import random

PINK = (234, 54, 128)
HEALTH_BAR_SCALE = 400
HEALTH_BAR_POS = [WIDTH - HEALTH_BAR_SCALE - 10, 10]
Starting_POS = (370 * SIZE, 163 * SIZE)



def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class Player(pygame.sprite.Sprite):
    player_skins_and_animatiom = \
        {
            "blue golden knight": Animation(
                "Player_Skins/blue golden knight.png",
                frame_w=32, frame_h=32,
                rows={"idle": 0, "run": 4, "injured": 8, "dead": 9},
                frames_per_row={"idle": 4, "run": 4, "injured": 4, "dead": 4},
                scale=3,
                speed_ms=180
            ),
            "fiona": Animation(
                "Player_Skins/fiona.png",
                frame_w=32, frame_h=32,
                rows={"idle": 0, "run": 3, "injured": 5, "dead": 6},
                frames_per_row={"idle": 4, "run": 4, "injured": 4, "dead": 4},
                scale=3,
                speed_ms=180
            ),
            "golden knight": Animation(
                "Player_Skins/golden knight.png",
                frame_w=32, frame_h=32,
                rows={"idle": 0, "run": 4, "injured": 8, "dead": 9},
                frames_per_row={"idle": 4, "run": 4, "injured": 4, "dead": 4},
                scale=3,
                speed_ms=180
            ),
            "red knight": Animation(
                "Player_Skins/red knight.png",
                frame_w=32, frame_h=32,
                rows={"idle": 0, "run": 3, "injured": 9, "dead": 10},
                frames_per_row={"idle": 4, "run": 4, "injured": 4, "dead": 4},
                scale=3,
                speed_ms=180
            ),
            "king": Animation(
                "Player_Skins/king.png",
                frame_w=32, frame_h=32,
                rows={"idle": 0, "run": 3, "injured": 5, "dead": 6},
                frames_per_row={"idle": 4, "run": 4, "injured": 4, "dead": 4},
                scale=3,
                speed_ms=180
            )
        }


    player_skins_and_animatiom = {
        "blue golden knight": Animation(
            resource_path("Player_Skins/blue golden knight.png"),
            frame_w=32, frame_h=32,
            rows={"idle": 0, "run": 4, "injured": 8, "dead": 9},
            frames_per_row={"idle": 4, "run": 4, "injured": 4, "dead": 4},
            scale=3,
            speed_ms=180
        ),
        "fiona": Animation(
            resource_path("Player_Skins/fiona.png"),
            frame_w=32, frame_h=32,
            rows={"idle": 0, "run": 3, "injured": 5, "dead": 6},
            frames_per_row={"idle": 4, "run": 4, "injured": 4, "dead": 4},
            scale=3,
            speed_ms=180
        ),
        "golden knight": Animation(
            resource_path("Player_Skins/golden knight.png"),
            frame_w=32, frame_h=32,
            rows={"idle": 0, "run": 4, "injured": 8, "dead": 9},
            frames_per_row={"idle": 4, "run": 4, "injured": 4, "dead": 4},
            scale=3,
            speed_ms=180
        ),
        "red knight": Animation(
            resource_path("Player_Skins/red knight.png"),
            frame_w=32, frame_h=32,
            rows={"idle": 0, "run": 3, "injured": 9, "dead": 10},
            frames_per_row={"idle": 4, "run": 4, "injured": 4, "dead": 4},
            scale=3,
            speed_ms=180
        ),
        "king": Animation(
            resource_path("Player_Skins/king.png"),
            frame_w=32, frame_h=32,
            rows={"idle": 0, "run": 3, "injured": 5, "dead": 6},
            frames_per_row={"idle": 4, "run": 4, "injured": 4, "dead": 4},
            scale=3,
            speed_ms=180
        )
    }

    def __init__(self, groups, other_groups):
        super().__init__(groups)  # the groups for now is only visable sprite

        self.display_surface = pygame.display.get_surface()

        skins=["blue golden knight", "fiona", "golden knight","red knight","king"]
        self.skin = random.choice(skins)

        self.animation = Player.player_skins_and_animatiom[self.skin]

        self.image = self.animation.image()
        self.facing = "RIGHT"

        self.rect = self.image.get_rect(topleft=Starting_POS)

        self.hitbox = self.rect.inflate(0, 0)
        self.hitbox.width = 30
        self.hitbox.height = 30

        self.speed = 4
        self.direction = pygame.math.Vector2()
        self.groups = groups
        self.obstacle_sprites, self.harmful_sprites, self.colect_sprite = other_groups  # rocks and such

        self.inventory = Inventory()

        self.last_r_press = 0
        self.last_shoot = 0

        self.shop_open = False
        self.last_b_press = 0

        self.money = 200000
        self.shop_ui = ShopUI()

        self.ammo_collection = {
            "AK 47 bullets": 104,
            "arrows": 103,
            "Assault rifle bullets": 102,
            "Pistol bullets": 101
        }

        self.magazine = {
            "Ak 47": 5,
            "bow": 5,
            "Assault rifle": 5,
            "Pistol": 5,
            "sword": 1000
        }

        self.health = HealthBar(HEALTH_BAR_POS, HEALTH_BAR_SCALE)
        self.injured_until = 0

        self.is_dead = False
        self.death_time = 0

        self.death_animation_time = 750
        self.respawn_delay = 2000

        self.auto_move = AutoMoveController(self)

    def current_Weapon(self):
        return self.inventory.wep_inventory[self.inventory.current_weapon]

    def input(self, is_c_o):  # check if you want to move with your player
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

        elif keys[pygame.K_DOWN] or keys[pygame.K_s]:
            self.direction.y = 1
        else:
            self.direction.y = 0

        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.direction.x = -1
            self.facing = "LEFT"

        elif keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.direction.x = 1
            self.facing = "RIGHT"

        else:
            self.direction.x = 0
        if not is_c_o:
            if keys[pygame.K_b]:
                now = pygame.time.get_ticks()
                if now - self.last_b_press > 300:
                    self.last_b_press = now
                    self.shop_ui.toggle()

            if len(self.inventory.wep_inventory) != 0:
                if keys[pygame.K_r]:
                    w = self.current_Weapon()
                    now = pygame.time.get_ticks()
                    if now - self.last_r_press >= w.fire_cooldown:
                        self.last_r_press = now

                        ZoneConnectionSingleton().zone.try_to_reload(w.gun_type,Arsenal.Arsenal_gunType[w.gun_type][6])

                        if w.bullet != "null":
                            if w.bullet != "sword hit":
                                capability = Arsenal.Arsenal_gunType[w.gun_type][6]
                                need = max(0, capability - self.magazine[w.gun_type])
                                have = self.ammo_collection[w.bullet]

                                take = min(need, have)

                                self.magazine[w.gun_type] += take
                                self.ammo_collection[w.bullet] = have - take

            mouse_buttons = pygame.mouse.get_pressed()

            if mouse_buttons[0] and not self.inventory.is_wep_empty():
                try:
                    if self.magazine[self.current_Weapon().gun_type] > 0:

                        now = pygame.time.get_ticks()
                        if now - self.last_shoot >= self.current_Weapon().fire_cooldown:
                            self.last_shoot = now

                            mouse_x, mouse_y = pygame.mouse.get_pos()
                            scroll = [
                                self.rect.centerx - WIDTH / 2,
                                self.rect.centery - HEIGHT / 2,
                            ]

                            # Sync local UI and prepare authoritative shot for server
                            self.current_Weapon().on_fire()
                            weapon = self.current_Weapon()

                            # to alain the gun with the bullet
                            if mouse_x > self.display_surface.get_width() / 2:
                                const_x = -35
                            else:
                                const_x = 0

                            if mouse_y > self.display_surface.get_height() / 2:
                                const_y = +15
                            else:
                                const_y = 0

                            # Fire local bullets from each spawn point, but send
                            # a single aggregated shot to the server using 'count'.
                            angle_for_server = None
                            for x, y in weapon.spawn_points:
                                bullet = Bullets(
                                    weapon.GetBulletType(),
                                    self.display_surface.get_width() / 2 + x + const_x,
                                    self.display_surface.get_height() / 2 + y + const_y,
                                    mouse_x,
                                    mouse_y,
                                    scroll=scroll,
                                    from_network=False,
                                )
                                Bullets.BulletLS.append(bullet)
                                angle_for_server = bullet.angle
                                self.current_Weapon().mag -= 1

                            if angle_for_server is not None:
                                ZoneConnectionSingleton().zone.try_send_bullet(
                                    weapon.GetBulletType(),
                                    angle_for_server,
                                    len(weapon.spawn_points),
                                )

                                self.magazine[weapon.gun_type] -= 1
                except:
                    print("error")

    def move(self):  # change x and y pos according to direction, speed
        if self.direction.magnitude() != 0:
            self.direction = self.direction.normalize()
        self.hitbox.x += int(self.direction.x * self.speed)
        self.check_coalition("horizontal")
        self.hitbox.y += int(self.direction.y * self.speed)
        self.check_coalition("vertical")
        self.rect.center = self.hitbox.center

    def check_coalition(self, direction):

        collision_sprites = pygame.sprite.spritecollide(self, self.obstacle_sprites, False)

        for sprite in collision_sprites:

            if sprite.hitbox.colliderect(self.hitbox):
                self.check_harm_done(sprite)
                if direction == 'horizontal':

                    if self.direction.x > 0:
                        self.hitbox.right = sprite.hitbox.left
                    elif self.direction.x < 0:
                        self.hitbox.left = sprite.hitbox.right


                elif direction == 'vertical':
                    if self.direction.y > 0:  # נע למטה
                        self.hitbox.bottom = sprite.hitbox.top
                    elif self.direction.y < 0:  # נע למעלה
                        self.hitbox.top = sprite.hitbox.bottom

    def check_harm_done(self, sprite):
        if sprite in self.harmful_sprites:
            self.health.sub_life(30)
            Red_hit.start()
            self.injured_until = pygame.time.get_ticks() + 600 #0.6s of red skin :c

    def check_if_collect(self):
        for sprite in self.colect_sprite:
            if sprite.rect.colliderect(self.hitbox):

                from zone_connection import ZoneConnectionSingleton

                if sprite.kind == "weapon":
                    # --- NEW: Grab the current ammo and send it! ---
                    current_ammo = sprite.obj.mag
                    ZoneConnectionSingleton().zone.try_send_item_pickup(sprite.obj.get_name(), "weapon", current_ammo)
                    self.inventory.add_item_toThe_Inventory(sprite.obj, "weapon")

                elif sprite.kind == "potion":
                    # Potions don't need ammo, so we can just leave it at the default 0
                    ZoneConnectionSingleton().zone.try_send_item_pickup(sprite.obj.get_name(), "potion")
                    self.inventory.add_item_toThe_Inventory(sprite.obj, "potion")

                sprite.kill()
                break

    def dead(self):
        now = pygame.time.get_ticks()

        if not self.health.is_alive() and not self.is_dead:
            self.is_dead = True
            self.death_time = now
            self.animation.set_state("dead")

        if self.is_dead:

            if now - self.death_time > self.death_animation_time:
                self.direction.x = 0
                self.direction.y = 0

            if now - self.death_time > self.death_animation_time + self.respawn_delay:
                self.is_dead = False

                #self.inventory.drop_all_items([self.colect_sprite, self.groups[0]], self.rect)
                self.health.add_life(HEALTH_BAR_SCALE)

                self.rect.topleft = Starting_POS
                self.hitbox.center = self.rect.center

    def playerState(self):
        now = pygame.time.get_ticks()

        if self.is_dead:
            self.animation.set_state("dead")

        elif now < self.injured_until:
            self.animation.set_state("injured")

        elif self.direction.x != 0 or self.direction.y != 0:
            self.animation.set_state("run")

        else:
            self.animation.set_state("idle")

        self.animation.update()

        old_center = self.rect.center
        self.image = self.animation.image(flip_x=(not self.facing == "RIGHT"))
        self.rect = self.image.get_rect(center=old_center)

    def update(self, is_c_o):
        self.dead()
        self.playerState()

        draw_AND_update_Bullets(self)

        if not self.is_dead:
            self.auto_move.step()

            if not self.auto_move.enabled:
                self.input(is_c_o)

            if len(self.inventory.wep_inventory) != 0:
                if not self.is_dead:
                    self.current_Weapon().draw(WIDTH / 2, HEIGHT / 2)
                    self.current_Weapon().draw_mag_stat(self)

        self.move()
        self.inventory.open([self.colect_sprite,self.groups[0]],self)
        self.health.draw()

        self.shop_ui.draw(self.display_surface, self)
        self.auto_move.draw_label()  # AutoMove label
