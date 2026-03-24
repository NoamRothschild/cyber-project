import pygame
import sys

# --- Constants & Colors ---
BG_COLOR = (15, 23, 42)  # Dark Navy
INPUT_BG = (30, 41, 59)  # Slate lighter
INPUT_BORDER = (56, 189, 248)  # Neon Sky Blue
TEXT_COLOR = (241, 245, 249)  # Off-white
GLOW_COLOR = (0, 255, 255)  # Cyan Glow
BACK_BTN_COLOR = (200, 50, 50)  # Reddish for "Cancel"
BACK_BTN_HOVER = (255, 100, 100)

WIDTH, HEIGHT = 800, 600


class LogIn:
    def __init__(self):
        # We grab the screen created in EnterScreen
        self.screen = pygame.display.get_surface()

        # Modern Fonts
        self.font_header = pygame.font.SysFont("verdana", 40, bold=True)
        self.font_label = pygame.font.SysFont("arial", 14, bold=True)
        self.font_input = pygame.font.SysFont("consolas", 24)

        # Input Boxes (Centered)
        cx, cy = WIDTH // 2, HEIGHT // 2
        self.user_rect = pygame.Rect(cx - 150, cy - 60, 300, 50)
        self.pass_rect = pygame.Rect(cx - 150, cy + 40, 300, 50)

        # --- BUTTONS ---
        self.btn_rect = pygame.Rect(cx - 100, cy + 130, 200, 50)  # Access Button
        self.back_rect = pygame.Rect(cx - 100, cy + 195, 200, 40)  # Back Button

        self.user_text = ""
        self.pass_text = ""
        self.active_field = "user"  # 'user' or 'pass'

    def draw_glow(self, rect, color):
        """Creates a neon glow effect around a rectangle."""
        for i in range(10):
            alpha = 100 - (i * 10)
            glow_surf = pygame.Surface((rect.width + i * 4, rect.height + i * 4), pygame.SRCALPHA)
            pygame.draw.rect(glow_surf, (*color, alpha), glow_surf.get_rect(), border_radius=15)
            self.screen.blit(glow_surf, (rect.x - i * 2, rect.y - i * 2))

    def run(self):
        running = True
        clock = pygame.time.Clock()

        # Cursor blinking
        cursor_visible = True
        cursor_timer = 0

        while running:
            mouse_pos = pygame.mouse.get_pos()

            # --- Event Handling ---
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

                if event.type == pygame.MOUSEBUTTONDOWN:
                    if self.user_rect.collidepoint(event.pos):
                        self.active_field = "user"
                    elif self.pass_rect.collidepoint(event.pos):
                        self.active_field = "pass"
                    elif self.btn_rect.collidepoint(event.pos):
                        # SUBMIT BUTTON CLICKED
                        return self.user_text, self.pass_text

                    # --- NEW: BACK BUTTON CLICKED ---
                    elif self.back_rect.collidepoint(event.pos):
                        return None, None

                if event.type == pygame.KEYDOWN:
                    # --- NEW: ESCAPE KEY TO GO BACK ---
                    if event.key == pygame.K_ESCAPE:
                        return None, None

                    if event.key == pygame.K_TAB:
                        self.active_field = "pass" if self.active_field == "user" else "user"
                    elif event.key == pygame.K_RETURN:
                        # ENTER KEY PRESSED
                        return self.user_text, self.pass_text
                    elif event.key == pygame.K_BACKSPACE:
                        if self.active_field == "user":
                            self.user_text = self.user_text[:-1]
                        else:
                            self.pass_text = self.pass_text[:-1]
                    else:
                        # Typing limit (15 chars)
                        if self.active_field == "user" and len(self.user_text) < 15:
                            self.user_text += event.unicode
                        elif self.active_field == "pass" and len(self.pass_text) < 15:
                            self.pass_text += event.unicode

            # --- Drawing ---

            # 1. Background with Grid pattern
            self.screen.fill(BG_COLOR)
            self.draw_grid()

            # 2. Header Title
            title = self.font_header.render("AUTHENTICATION", True, TEXT_COLOR)
            shadow = self.font_header.render("AUTHENTICATION", True, (0, 0, 0))
            self.screen.blit(shadow, (WIDTH // 2 - title.get_width() // 2 + 4, 104))
            self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 100))

            # 3. Input Fields
            self.draw_input(self.user_rect, "USERNAME", self.user_text, self.active_field == "user", False,
                            cursor_visible)
            self.draw_input(self.pass_rect, "PASSWORD", self.pass_text, self.active_field == "pass", True,
                            cursor_visible)

            # 4. Submit Button (Access Terminal)
            is_hover = self.btn_rect.collidepoint(mouse_pos)
            btn_color = (0, 255, 150) if is_hover else (0, 200, 100)

            if is_hover:
                self.draw_glow(self.btn_rect, btn_color)

            pygame.draw.rect(self.screen, btn_color, self.btn_rect, border_radius=10)
            btn_text = self.font_label.render("ACCESS TERMINAL", True, (10, 20, 30))
            self.screen.blit(btn_text, (self.btn_rect.centerx - btn_text.get_width() // 2,
                                        self.btn_rect.centery - btn_text.get_height() // 2))

            # --- 5. NEW: Back Button (Return to Menu) ---
            is_back_hover = self.back_rect.collidepoint(mouse_pos)
            current_back_color = BACK_BTN_HOVER if is_back_hover else BACK_BTN_COLOR

            if is_back_hover:
                self.draw_glow(self.back_rect, current_back_color)

            pygame.draw.rect(self.screen, current_back_color, self.back_rect, border_radius=10)
            back_text = self.font_label.render("RETURN TO MENU", True, (30, 10, 10))
            self.screen.blit(back_text, (self.back_rect.centerx - back_text.get_width() // 2,
                                         self.back_rect.centery - back_text.get_height() // 2))

            # Cursor Blinking Logic
            cursor_timer += 1
            if cursor_timer >= 30:
                cursor_visible = not cursor_visible
                cursor_timer = 0

            pygame.display.flip()
            clock.tick(60)

    def draw_grid(self):
        """Draws a faint tech-grid background."""
        for x in range(0, WIDTH, 40):
            pygame.draw.line(self.screen, (30, 40, 60), (x, 0), (x, HEIGHT))
        for y in range(0, HEIGHT, 40):
            pygame.draw.line(self.screen, (30, 40, 60), (0, y), (WIDTH, y))

    def draw_input(self, rect, label, text, is_active, is_password, show_cursor):
        # Label above box
        lbl_surf = self.font_label.render(label, True, INPUT_BORDER)
        self.screen.blit(lbl_surf, (rect.x, rect.y - 20))

        # Box Glow
        if is_active:
            self.draw_glow(rect, INPUT_BORDER)
            border_col = INPUT_BORDER
        else:
            border_col = (100, 100, 120)

        # Draw Box
        pygame.draw.rect(self.screen, INPUT_BG, rect, border_radius=8)
        pygame.draw.rect(self.screen, border_col, rect, 2, border_radius=8)

        # Draw Text
        display_text = "*" * len(text) if is_password else text
        if is_active and show_cursor:
            display_text += "|"

        txt_surf = self.font_input.render(display_text, True, TEXT_COLOR)
        # Center text vertically in the box
        self.screen.blit(txt_surf, (rect.x + 10, rect.y + 12))