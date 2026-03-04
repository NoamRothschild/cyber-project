from helth import HealthBar
from inventory import *
from client.arsenal import Arsenal
from bullets import Bullets
from zone_connection import ZoneConnectionSingleton
from zone_connection import *
from game import *
from mapset import *
from inventory import *
from bullets import *
from shop import ShopUI
from potion import Potion

PINK = (234, 54, 128)
HEALTH_BAR_SCALE=400
HEALTH_BAR_POS =[WIDTH-HEALTH_BAR_SCALE-10,10]
Starting_POS = (370 * SIZE, 163 * SIZE)
class Player(pygame.sprite.Sprite):

    def __init__(self, groups, other_groups):
        super().__init__(groups)  # the groups for now is only visable sprite

        self.display_surface=pygame.display.get_surface()
        self.color="golden knight"
        #self.color="king"

        self.animation = Animation(
            f"Player_Skins/{self.color}.png",
            frame_w=32, frame_h=32,
            rows={"idle": 0, "run": 3},
            frames_per_row={"idle": 4, "run": 4},
            scale=3,
            speed_ms=180
        )
        self.image = self.animation.image()
        self.facing = "RIGHT"

        self.rect = self.image.get_rect(topleft=Starting_POS)

        self.hitbox = self.rect.inflate(0,0)
        self.hitbox.width = 30
        self.hitbox.height = 30

        self.speed = 4
        self.direction = pygame.math.Vector2()
        self.groups = groups
        self.obstacle_sprites, self.harmfull_sprites,self.colect_sprite = other_groups # rocks and such

        self.inventory = Inventory()

        self.last_r_press = 0
        self.last_shoot = 0

        self.shop_open = False
        self.last_b_press = 0

        self.money = 200000
        self.shop_ui = ShopUI()

        self.ammo_collection = {
            "AK-7_bullet": 1,
            "arrow": 1
        }

        self.health = HealthBar(HEALTH_BAR_POS,HEALTH_BAR_SCALE)
        self.inventory.add_item_toThe_Inventory(Arsenal("Ak 47"), "weapon")
        self.inventory.add_item_toThe_Inventory(Arsenal("bow"), "weapon")
        self.inventory.add_item_toThe_Inventory(Arsenal("sword"), "weapon")
        self.inventory.add_item_toThe_Inventory(Arsenal("Assault rifle"), "weapon")
        self.inventory.add_item_toThe_Inventory(Arsenal("Pistol"), "weapon")
        self.inventory.add_item_toThe_Inventory(Potion("healing"), "potion")

    def current_Weapon(self):
        return self.inventory.wep_inventory[self.inventory.current_weapon]

    def input(self,is_c_o):  # check if you want to move with your player
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
                        scroll = [
                            self.rect.centerx - WIDTH / 2,
                            self.rect.centery - HEIGHT / 2,
                        ]
                        self.current_Weapon().on_fire()
                        bullet=Bullets(
                                self.current_Weapon().GetBulletType(),
                                self.display_surface.get_width() / 2,
                                self.display_surface.get_height() / 2,
                                mouse_x=mouse_x,
                                mouse_y=mouse_y,
                                scroll=scroll,
                                from_network=False,
                            )

                        self.current_Weapon().mag -= 1
                        ZoneConnectionSingleton().zone.try_send_bullet(self.current_Weapon().get_name(), bullet.angle, 1)
                        Bullets.BulletLS.append(bullet)
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
        if sprite in self.harmfull_sprites:
            self.health.sub_life(30)


    def check_if_collect(self):
        for sprite in self.colect_sprite:
            if sprite.rect.colliderect(self.hitbox):
                if sprite.kind == "weapon":
                    self.inventory.add_item_toThe_Inventory(sprite.obj, "weapon")
                elif sprite.kind == "potion":
                    self.inventory.add_item_toThe_Inventory(sprite.obj, "potion")
                sprite.kill()
                break
    def dead(self):
        if not self.health.is_alive():
            self.inventory.delete_w([self.colect_sprite,self.groups[0]],self.rect)
            self.health.add_life(HEALTH_BAR_SCALE,True)
            self.rect.topleft = Starting_POS
            self.hitbox.center=self.rect.center

    def playerState(self):
        if self.direction.x != 0 or self.direction.y != 0:
            self.animation.set_state("run")
        else:
            self.animation.set_state("idle")

        self.animation.update()

        old_center = self.rect.center

        self.image = self.animation.image(flip_x=(not self.facing=="RIGHT"))

        self.rect = self.image.get_rect(center=old_center)


    def update(self,is_c_o):
        self.dead()
        self.input(is_c_o)

        self.playerState()

        draw_AND_update_Bullets(self)
        self.current_Weapon().draw_mag_stat()
        self.shop_ui.draw(self.display_surface, self)

        self.move()
        self.inventory.open([self.colect_sprite,self.groups[0]],self)
        self.health.draw()
        self.check_if_collect()
