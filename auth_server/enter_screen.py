import pygame, sys
from auth_server import client_auth
from login import LogIn

# --- Modern Color Palette ---
BLACK = (10, 10, 20)  # Deep dark blue-black
WHITE = (240, 240, 255)
ACCENT = (0, 200, 255)  # Neon Cyan
HOVER = (50, 220, 255)  # Lighter Cyan
GRAY = (60, 70, 90)
ERROR_RED = (255, 80, 80)
SUCCESS_GREEN = (80, 255, 100)

WIDTH = 800
HEIGHT = 600
FPS = 60


class EnterScreen:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption('Cyber Login')
        self.clock = pygame.time.Clock()

        # Better Fonts
        self.title_font = pygame.font.SysFont("verdana", 50, bold=True)
        self.btn_font = pygame.font.SysFont("arial", 22, bold=True)
        self.msg_font = pygame.font.SysFont("consolas", 16)

        # Center buttons
        center_x = WIDTH // 2
        self.login_rect = pygame.Rect(center_x - 140, 350, 120, 45)
        self.register_rect = pygame.Rect(center_x + 20, 350, 120, 45)

        self.is_running = False
        self.log_in = LogIn()

        # State for feedback messages
        self.status_message = "Ready to connect..."
        self.status_color = GRAY

    def draw_gradient_bg(self):
        """Draws a cool vertical gradient background."""
        top_color = (20, 30, 50)
        bottom_color = (5, 5, 10)
        for y in range(HEIGHT):
            r = top_color[0] + (bottom_color[0] - top_color[0]) * y // HEIGHT
            g = top_color[1] + (bottom_color[1] - top_color[1]) * y // HEIGHT
            b = top_color[2] + (bottom_color[2] - top_color[2]) * y // HEIGHT
            pygame.draw.line(self.screen, (r, g, b), (0, y), (WIDTH, y))

    def draw_button(self, rect, text, is_hovered):
        """Helper to draw stylish buttons with shadows."""
        color = HOVER if is_hovered else ACCENT
        shadow_rect = rect.move(0, 4)

        # Draw Shadow
        pygame.draw.rect(self.screen, (0, 0, 0, 100), shadow_rect, border_radius=8)
        # Draw Button
        pygame.draw.rect(self.screen, color, rect, border_radius=8)

        # Text
        text_surf = self.btn_font.render(text, True, (20, 20, 20))
        text_rect = text_surf.get_rect(center=rect.center)
        self.screen.blit(text_surf, text_rect)

    def run(self):
        self.is_running = True

        while self.is_running:
            command = ""
            user_name, password = "", ""
            mouse_pos = pygame.mouse.get_pos()

            # --- Event Handling ---
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.is_running = False

                if event.type == pygame.MOUSEBUTTONDOWN:
                    if self.login_rect.collidepoint(event.pos):
                        command = "LOG"
                        user_name, password = self.log_in.run()
                    elif self.register_rect.collidepoint(event.pos):
                        command = "REG"
                        user_name, password = self.log_in.run()

            # --- Logic Handling (Connecting) ---
            if user_name and password:
                # Update UI to show we are working
                self.status_message = "Connecting to server..."
                self.status_color = ACCENT
                self.draw_screen(mouse_pos)  # Force a redraw so user sees "Connecting"

                # Call the modified client_auth which now returns a string!
                response = client_auth.connect(user_name, password, command)

                # Handle Response
                if response.startswith("LOGIN_SUCCESS"):
                    print("Game Starting...")
                    self.is_running = False  # Break loop to start game
                elif response == "AUTH_SUCCESS":
                    print("Registration complete. Logging in...")
                    self.is_running = False
                elif response == "LOGIN_FAILED":
                    self.status_message = "Login Failed: Incorrect credentials."
                    self.status_color = ERROR_RED
                elif response == "AUTH_TAKEN":
                    self.status_message = "Registration Failed: Username taken."
                    self.status_color = ERROR_RED
                elif response == "SERVER_OFFLINE":
                    self.status_message = "Error: Server is unreachable."
                    self.status_color = ERROR_RED
                else:
                    self.status_message = f"Unknown Error: {response}"
                    self.status_color = ERROR_RED

            # --- Drawing ---
            self.draw_screen(mouse_pos)
            self.clock.tick(FPS)

        pygame.quit()
        sys.exit()

    def draw_screen(self, mouse_pos):
        self.draw_gradient_bg()

        # Title with Shadow
        title_text = "OverDrive"
        shadow = self.title_font.render(title_text, True, (0, 0, 0))
        main = self.title_font.render(title_text, True, WHITE)
        self.screen.blit(shadow, (WIDTH // 2 - shadow.get_width() // 2 + 3, 153))
        self.screen.blit(main, (WIDTH // 2 - main.get_width() // 2, 150))

        # Status Message (The logic fix visualization)
        msg_surf = self.msg_font.render(self.status_message, True, self.status_color)
        self.screen.blit(msg_surf, (WIDTH // 2 - msg_surf.get_width() // 2, 500))

        # Buttons
        self.draw_button(self.login_rect, "LOGIN", self.login_rect.collidepoint(mouse_pos))
        self.draw_button(self.register_rect, "REGISTER", self.register_rect.collidepoint(mouse_pos))

        pygame.display.flip()


if __name__ == '__main__':
    game = EnterScreen()
    game.run()
