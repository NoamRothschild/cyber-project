import pygame,sys

BLACK = (0,0,0)


FPS=60
WHITE = (255,255,255)
GRAY = (150,150,150)
side_txt="push Enter for ok \n push tub for moving from a to b"



class LogIn(pygame.sprite.Sprite):

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.get_surface()
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 30, bold=True)

        # הגדרת המיקומים של התיבות והכפתורים
        self.user_rect = pygame.Rect(50, 150, 300, 45)
        self.pass_rect = pygame.Rect(50, 250, 300, 45)


    def run(self):

        user_text = ""
        pass_text = ""
        active_field = "user"  # שדה ברירת מחדל
        is_running = True
        self.screen.blit(self.font.render(side_txt, True, WHITE), (70, 110))
        while is_running:
            self.screen.fill(BLACK)  # ניקוי המסך בכל פריים

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

                if event.type == pygame.MOUSEBUTTONDOWN:
                    # בחירת שדה להקלדה
                    if self.user_rect.collidepoint(event.pos):
                        active_field = "user"
                    elif self.pass_rect.collidepoint(event.pos):
                        active_field = "pass"

                    # לחיצה על כפתורים


                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        is_running = False
                    elif event.key == pygame.K_BACKSPACE:
                        if active_field == "user":
                            user_text = user_text[:-1]
                        else:
                            pass_text = pass_text[:-1]
                    elif event.key == pygame.K_TAB:  # מעבר נוח בין שדות
                        active_field = "pass" if active_field == "user" else "user"
                    else:
                        if active_field == "user":
                            user_text += event.unicode
                        else:
                            pass_text += event.unicode

            # --- פקודות הציור (Text & Boxes) ---

            # ציור תוויות (Labels)
            self.screen.blit(self.font.render(side_txt, True, WHITE), (400, 20))
            self.screen.blit(self.font.render("Username:", True, WHITE), (50, 110))
            self.screen.blit(self.font.render("Password:", True, WHITE), (50, 210))

            # ציור מסגרות לתיבות (צבע משתנה אם השדה פעיל)
            u_color = WHITE if active_field == "user" else GRAY
            p_color = WHITE if active_field == "pass" else GRAY
            pygame.draw.rect(self.screen, u_color, self.user_rect, 2)
            pygame.draw.rect(self.screen, p_color, self.pass_rect, 2)

            # רינדור והצגת הטקסט בתוך התיבות (סיסמה מוצגת ככוכביות)
            user_surface = self.font.render(user_text, True, WHITE)
            pass_surface = self.font.render(pass_text , True, WHITE)

            self.screen.blit(user_surface, (self.user_rect.x + 5, self.user_rect.y + 5))
            self.screen.blit(pass_surface, (self.pass_rect.x + 5, self.pass_rect.y + 5))

            # ציור כפתורי Login ו-Register


            pygame.display.flip()
            self.clock.tick(FPS)

        return user_text, pass_text





