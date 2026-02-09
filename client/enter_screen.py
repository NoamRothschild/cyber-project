import pygame,sys

import client_auth
from login import LogIn
from client_auth import *

BLACK = (0,0,0)
WHITE = (255, 255, 255)
GRAY = (200, 200, 200)
BLUE = (50, 150, 255)
WIDTH = 800
HEIGHT = 600
FPS = 60
class EnterScreen:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))


        pygame.display.set_caption('Game')
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 30, bold=True)

        self.login_rect = pygame.Rect(250, 350, 120, 50)
        self.register_rect = pygame.Rect(430, 350, 120, 50)

        self.screen.fill(BLACK)
        self.is_running = False
        self.log_in = LogIn()


    def run(self):

        self.is_running = True

        while self.is_running:
            user_name,password,command = "","",""
            mouse_pos = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.is_running = False
                    break
                if event.type == pygame.MOUSEBUTTONDOWN:
                    # בדיקה אם לחצו על Login
                    if self.login_rect.collidepoint(event.pos):
                        command="LOG"
                        user_name,password=self.log_in.run()
                        password="LOG"+password
                    # בדיקה אם לחצו על Register
                    if self.register_rect.collidepoint(event.pos):
                        command="REG"
                        user_name,password = self.log_in.run()
                        user_name= user_name

            if not self.is_running: break
            self.screen.fill(BLACK)

            # כאן נכנסות הפקודות החדשות:


            login_color = BLUE if self.login_rect.collidepoint(mouse_pos) else GRAY
            pygame.draw.rect(self.screen, login_color, self.login_rect, border_radius=10)
            login_text = self.font.render("Login", True, (0, 0, 0))
            self.screen.blit(login_text, (self.login_rect.x + 25, self.login_rect.y + 10))

            # --- ציור כפתור Register ---
            reg_color = BLUE if self.register_rect.collidepoint(mouse_pos) else GRAY
            pygame.draw.rect(self.screen, reg_color, self.register_rect, border_radius=10)
            reg_text = self.font.render("Register", True, (0, 0, 0))
            self.screen.blit(reg_text, (self.register_rect.x + 15, self.register_rect.y + 10))
            # בסוף הלולאה חייב להופיע:
            pygame.display.flip()
            if user_name != "" and password != "":
                print(command +" "+user_name+" "+password)
                client_auth.connect(user_name, password,command)







            self.clock.tick(FPS)

        pygame.quit()
        sys.exit()


if __name__ == '__main__':
    game = EnterScreen()
    game.run()
