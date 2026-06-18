"""Handoff screen shown between turns in local mode — shows role + character card."""
import pygame
from constants import BG, PANEL_BG, WHITE, GOLD, GRAY, GREEN, DIM, WIN_W, WIN_H
from ui_utils import draw_text, rounded_rect, Button
from card_renderer import draw_role_card, draw_character_card
from roles import Role
from characters import CharacterType, CHARACTERS


class HandoffScreen:
    """Pass-and-play privacy screen: shown right before a local player's
    turn so only they see their own role/character cards before clicking
    through to the shared GameScreen."""
    CARD_W = 210
    CARD_H = 296   # ~√2 ratio

    def __init__(self, screen: pygame.Surface, player_info: dict):
        """
        player_info keys:
          name        – str
          role        – Role
          character   – CharacterType
          max_hp      – int
          is_sheriff  – bool (role already publicly known)
        """
        self.screen = screen
        self.info   = player_info
        cx = WIN_W // 2
        self.btn = Button(
            (cx - 120, WIN_H - 110, 240, 52),
            "준비 완료 →", GREEN, radius=12, fkey="sub"
        )
        self._role_surf = None
        self._char_surf = None
        self._build_card_surfaces()

    def _build_card_surfaces(self):
        w, h = self.CARD_W, self.CARD_H
        rs = pygame.Surface((w, h), pygame.SRCALPHA)
        rs.fill((0, 0, 0, 0))
        draw_role_card(rs, self.info["role"], pygame.Rect(0, 0, w, h))
        self._role_surf = rs

        cs = pygame.Surface((w, h), pygame.SRCALPHA)
        cs.fill((0, 0, 0, 0))
        draw_character_card(cs, self.info["character"],
                            self.info["max_hp"], pygame.Rect(0, 0, w, h))
        self._char_surf = cs

    def handle(self, event) -> bool:
        pos = pygame.mouse.get_pos()
        return self.btn.clicked(event, pos)

    def draw(self):
        s = self.screen
        s.fill((8, 5, 2))

        cx, cy = WIN_W // 2, WIN_H // 2
        w, h   = self.CARD_W, self.CARD_H

        # Header
        draw_text(s, "화면을 가립니다", "sub", GRAY, cx, 30, "center")
        draw_text(s, self.info["name"], "title", GOLD, cx, 60, "center")
        draw_text(s, "의 턴입니다", "sub", WHITE, cx, 108, "center")

        # Cards side by side
        gap   = 32
        total = w * 2 + gap
        lx    = cx - total // 2
        card_y = 140

        # Role card
        s.blit(self._role_surf, (lx, card_y))
        draw_text(s, "역할 카드", "tiny", GRAY,
                  lx + w // 2, card_y - 18, "center")

        # Character card
        rx = lx + w + gap
        s.blit(self._char_surf, (rx, card_y))
        draw_text(s, "캐릭터 카드", "tiny", GRAY,
                  rx + w // 2, card_y - 18, "center")

        pos = pygame.mouse.get_pos()
        self.btn.draw(s, self.btn.is_hovered(pos))
        pygame.display.flip()
