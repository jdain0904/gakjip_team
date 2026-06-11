"""Handoff screen shown between turns in local mode (hides cards)."""
import pygame
from constants import BG, PANEL_BG, WHITE, GOLD, GRAY, GREEN, WIN_W, WIN_H
from ui_utils import draw_text, rounded_rect, Button


class HandoffScreen:
    def __init__(self, screen: pygame.Surface, player_name: str, reason: str = ""):
        self.screen = screen
        self.player_name = player_name
        self.reason = reason
        cx = WIN_W // 2
        self.btn_ready = Button((cx - 110, WIN_H // 2 + 80, 220, 54),
                                "준비 완료 →", GREEN, radius=12, fkey="sub")

    def handle(self, event) -> bool:
        pos = pygame.mouse.get_pos()
        return self.btn_ready.clicked(event, pos)

    def draw(self):
        s = self.screen
        s.fill((10, 8, 4))
        cx, cy = WIN_W // 2, WIN_H // 2

        rounded_rect(s, PANEL_BG, pygame.Rect(cx - 300, cy - 130, 600, 260), 18)
        pygame.draw.rect(s, GOLD, pygame.Rect(cx - 300, cy - 130, 600, 260), 2,
                         border_radius=18)

        draw_text(s, "화면을 가립니다", "sub", GRAY, cx, cy - 110, "center")
        draw_text(s, self.player_name, "large", GOLD, cx, cy - 60, "center")
        draw_text(s, "의 턴입니다", "sub", WHITE, cx, cy - 10, "center")

        if self.reason:
            draw_text(s, self.reason, "small", GRAY, cx, cy + 32, "center")

        pos = pygame.mouse.get_pos()
        self.btn_ready.draw(s, self.btn_ready.is_hovered(pos))
        pygame.display.flip()
