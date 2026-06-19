"""로컬 모드에서 턴 사이에 표시되는 핸드오프 화면 — 역할 + 캐릭터 카드를 보여준다."""
import pygame
from constants import BG, PANEL_BG, WHITE, GOLD, GRAY, GREEN, DIM, WIN_W, WIN_H
from ui_utils import draw_text, rounded_rect, Button
from card_renderer import draw_role_card, draw_character_card
from roles import Role
from characters import CharacterType, CHARACTERS


class HandoffScreen:
    """돌려가며 플레이할 때의 정보 보호 화면: 로컬 플레이어의 턴이 시작되기
    직전에 띄워서, 본인만 자신의 역할/캐릭터 카드를 확인한 뒤 클릭해서
    공용 GameScreen으로 넘어가게 한다."""
    CARD_W = 210
    CARD_H = 296   # 비율 약 √2

    def __init__(self, screen: pygame.Surface, player_info: dict):
        """
        player_info의 키:
          name        – str
          role        – Role
          character   – CharacterType
          max_hp      – int
          is_sheriff  – bool (역할이 이미 공개된 상태인지)
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

        # 헤더
        draw_text(s, "화면을 가립니다", "sub", GRAY, cx, 30, "center")
        draw_text(s, self.info["name"], "title", GOLD, cx, 60, "center")
        draw_text(s, "의 턴입니다", "sub", WHITE, cx, 108, "center")

        # 카드를 나란히 배치
        gap   = 32
        total = w * 2 + gap
        lx    = cx - total // 2
        card_y = 140

        # 역할 카드
        s.blit(self._role_surf, (lx, card_y))
        draw_text(s, "역할 카드", "tiny", GRAY,
                  lx + w // 2, card_y - 18, "center")

        # 캐릭터 카드
        rx = lx + w + gap
        s.blit(self._char_surf, (rx, card_y))
        draw_text(s, "캐릭터 카드", "tiny", GRAY,
                  rx + w // 2, card_y - 18, "center")

        pos = pygame.mouse.get_pos()
        self.btn.draw(s, self.btn.is_hovered(pos))
        pygame.display.flip()
