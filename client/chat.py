import pygame

# הגדרות בסיסיות
width, height = 300, 400


class Chat(pygame.sprite.Sprite):
    def __init__(self):
        super().__init__()
        self.rect = pygame.Rect(0, 80, width, height)
        self.screen = pygame.display.get_surface()
        self.is_open = False  # שיניתי ל-is_open כדי לא להתנגש עם פונקציות
        self.font = pygame.font.SysFont('Arial', 18)

        self.messages = []
        self.current_typing = ""  # מה שהמשתמש כותב כרגע

    def add_external_message(self, text):

        self.messages.append(text)

        if len(self.messages) > 18:
            self.messages.pop(0)

    def handle_event(self, event):

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_c and not self.is_open:
                self.is_open = True
                return

            if self.is_open:
                if event.key == pygame.K_ESCAPE:
                    self.is_open = False
                elif event.key == pygame.K_RETURN:
                    if self.current_typing:
                        self.add_external_message(f"You: {self.current_typing}")
                        self.current_typing = ""
                elif event.key == pygame.K_BACKSPACE:
                    self.current_typing = self.current_typing[:-1]
                else:

                    if event.unicode.isprintable():
                        self.current_typing += event.unicode

    def draw(self):
        if not self.is_open:
            return


        overlay = pygame.Surface((width, height))
        overlay.set_alpha(180)
        overlay.fill((20, 20, 20))
        self.screen.blit(overlay, (0, 80))

        # ציור ההודעות
        for i, msg in enumerate(self.messages):
            msg_surf = self.font.render(msg, True, (255, 255, 255))
            self.screen.blit(msg_surf, (10, 10 + i * 20+80))

        # ציור מה שהמשתמש מקליד כרגע (בתחתית)
        input_text = self.font.render(f"> {self.current_typing}", True, (0, 255, 0))
        self.screen.blit(input_text, (10, height+80 - 30))