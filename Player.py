import pygame
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
        self.hitbox.x += self.direction.x*self.speed
        self.check_coalition("horizontal")# if th player collides with obstical
        self.hitbox.y += self.direction.y*self.speed
        self.check_coalition("vertical")
        self.rect.center=self.hitbox.center

    def check_coalition(self,direction):#if it collides it move the player to only tach the rock
        if direction=='horizontal':
            for sprite in self.obstacle_sprites:
                if sprite.rect.colliderect(self.hitbox):
                    if self.direction.x>0:
                        self.hitbox.right=sprite.rect.left
                    elif self.direction.x<0:
                        self.hitbox.left=sprite.rect.right
        if direction=='vertical':
            for sprite in self.obstacle_sprites:
                if sprite.rect.colliderect(self.hitbox):
                    if self.direction.y>0:
                        self.hitbox.bottom=sprite.rect.top
                    elif self.direction.y<0:
                        self.hitbox.top=sprite.rect.bottom

    def update(self):#call to all the player action
        self.input()

        self.move()
        self.inventory.open()


