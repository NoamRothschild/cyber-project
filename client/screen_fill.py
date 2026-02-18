import pygame

import pygame
import time

class ScreenFill:
    def __init__(self, color_name, WIDTH, HEIGHT):
        # 1. קביעת הצבע עם ערך Alpha (למשל 180 לרמת אטימות גבוהה)
        if color_name == "green":
            color = (0, 255, 0, 40)  # ירוק עם שקיפות
        elif color_name == "red":
            color = (255, 0, 0, 40)  # אדום עם שקיפות
        else:
            color = (255, 255, 255, 40)  # ברירת מחדל לבן

        # 2. יצירת המשטח עם תמיכה בשקיפות
        self.square_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)

        # 3. מילוי הריבוע בצבע שבחרנו
        self.square_surface.fill(color)

        # 4. יצירת ה"חור" השקוף במרכז
        # אנחנו מציירים עיגול ש"מוחק" את הצבע (Alpha = 0)
        center_pos = (WIDTH//2, HEIGHT//2)  # מרכז הריבוע (חצי מ-200)
        radius = 60
        pygame.draw.circle(self.square_surface, (0, 0, 0, 0), center_pos, radius)

        # הגדרת המיקום על המסך
        self.rect = self.square_surface.get_rect(center=(WIDTH // 2, HEIGHT // 2))
        self.is_fill = False

    def draw_fill(self):
        if self.is_fill == True:
            screen = pygame.display.get_surface()
            screen.blit(self.square_surface, self.rect)
            s_time = time.time()
            if s_time - self.current_time >= 0.5:
                self.is_fill = False
    def start(self):
        self.is_fill = True
        self.current_time = time.time()
