from helth import HealthBar
from inventory import *
PINK=(234,54,128)



class Player(pygame.sprite.Sprite):
    def __init__(self, pos, groups,obstacle_sprites):
        super().__init__(groups)#the groups for now is only visable sprite
        self.image = pygame.image.load('player.png').convert_alpha()
        self.image.set_colorkey(PINK)#background
        self.rect = self.image.get_rect(topleft=pos)
        self.hitbox = self.rect.inflate(-20,-10)#where it gets hit by rocks
        self.speed = 4#for every move to x or right he moves 4 pixels
        self.direction = pygame.math.Vector2()#a vector that contains if you should move 1 to the right (1,0),left(-1,0), up(0,-1), down(0,1);
        self.obstacle_sprites = obstacle_sprites#rocks and such
        self.inventory = Inventory()
        self.health=HealthBar()



    def input(self):#check if you want to move with your player
        keys = pygame.key.get_pressed()
        if keys[pygame.K_UP] or keys[pygame.K_w]:

            self.direction.y = -1

        elif keys[pygame.K_DOWN]or keys[pygame.K_s]:
            self.direction.y = 1
        else:
            self.direction.y=0

            if keys[pygame.K_LEFT] or keys[pygame.K_a]:
                self.direction.x=-1
            elif keys[pygame.K_RIGHT] or keys[pygame.K_d]:
                self.direction.x=1
            else:
                self.direction.x=0






    def move(self):#change x and y pos according to direction, speed
        if self.direction.magnitude()!=0:
            self.direction=self.direction.normalize()
        self.hitbox.x += int(self.direction.x*self.speed)
        self.check_coalition("horizontal")
        self.hitbox.y += int(self.direction.y*self.speed)
        self.check_coalition("vertical")
        self.rect.center=self.hitbox.center

    def check_coalition(self, direction):

        collision_sprites = pygame.sprite.spritecollide(self, self.obstacle_sprites, False)

        for sprite in collision_sprites:

            if sprite.hitbox.colliderect(self.hitbox):
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

    def update(self):#call to all the player action

        self.input()

        self.move()
        self.inventory.open()
        self.health.draw()
        if self.health.is_alive():
            self.kill()


