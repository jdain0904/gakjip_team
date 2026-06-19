"""Main menu: title + mode selection."""
import pygame
from constants import (BG, PANEL_BG, WHITE, GRAY, GOLD, GREEN, RED, BLUE,
                       PURPLE, ACCENT, WIN_W, WIN_H)
from ui_utils import draw_text, rounded_rect, Button


class MenuScreen:
    """타이틀 화면 — 플레이어가 로컬 플레이(한 화면 돌려쓰기) 또는 AI 대전
    중 하나를 선택하면 SetupScreen으로 넘어간다."""
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        cx = WIN_W // 2

        self.btn_local = Button((cx - 140, 340, 280, 60), "로컬 플레이",
                                GREEN, radius=12, fkey="sub")
        self.btn_ai    = Button((cx - 140, 420, 280, 60), "AI 대전",
                                ACCENT, radius=12, fkey="sub")

        self._stars = _make_stars(120)

    def handle(self, event) -> str | None:
        pos = pygame.mouse.get_pos()
        if self.btn_local.clicked(event, pos):
            return "local"
        if self.btn_ai.clicked(event, pos):
            return "ai"
        return None

    def draw(self):
        s = self.screen
        s.fill(BG)

        # Starfield
        for (x, y, r, bright) in self._stars:
            pygame.draw.circle(s, (bright, bright, bright), (x, y), r)

        # Title panel
        cx = WIN_W // 2
        panel_r = pygame.Rect(cx - 260, 140, 520, 130)
        rounded_rect(s, PANEL_BG, panel_r, 18)
        pygame.draw.rect(s, GOLD, panel_r, 2, border_radius=18)

        draw_text(s, "BANG!", "title", GOLD, cx, 166, "center")
        draw_text(s, "웨스턴 카드 게임", "sub", (195, 170, 100), cx, 222, "center")

        draw_text(s, "모드를 선택하세요", "small", GRAY, cx, 310, "center")

        pos = pygame.mouse.get_pos()
        self.btn_local.draw(s, self.btn_local.is_hovered(pos))
        self.btn_ai.draw(s, self.btn_ai.is_hovered(pos))

        # Mode descriptions
        draw_text(s, "같은 화면에서 여러 명이 함께 플레이", "tiny", GRAY,
                  cx, 412, "center")
        draw_text(s, "혼자 또는 인간과 AI가 함께 플레이", "tiny", GRAY,
                  cx, 492, "center")

        # Legend
        legend_y = WIN_H - 80
        roles = [("보안관", GOLD), ("부관", BLUE), ("무법자", RED), ("배신자", PURPLE)]
        total_w = len(roles) * 130
        sx = cx - total_w // 2
        for name, col in roles:
            rounded_rect(s, PANEL_BG, pygame.Rect(sx, legend_y, 120, 32), 8)
            pygame.draw.rect(s, col, pygame.Rect(sx, legend_y, 120, 32), 2, border_radius=8)
            draw_text(s, name, "small", col, sx + 60, legend_y + 16, "center")
            sx += 130

        pygame.display.flip()


def _make_stars(n: int):
    import random
    from constants import WIN_W, WIN_H
    stars = []
    for _ in range(n):
        x = random.randint(0, WIN_W)
        y = random.randint(0, WIN_H // 2)
        r = random.choice([1, 1, 1, 2])
        bright = random.randint(80, 200)
        stars.append((x, y, r, bright))
    return stars
