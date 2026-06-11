"""Setup screen: player count + name/type configuration."""
import pygame
from constants import (BG, PANEL_BG, WHITE, GRAY, GOLD, GREEN, ACCENT, DIM,
                       BLUE, RED, WIN_W, WIN_H, ROLE_COLORS)
from ui_utils import draw_text, rounded_rect, Button


_DEFAULT_NAMES_LOCAL = ["플레이어1", "플레이어2", "플레이어3",
                        "플레이어4", "플레이어5", "플레이어6", "플레이어7"]
_DEFAULT_NAMES_AI    = ["플레이어", "AI-1", "AI-2", "AI-3",
                        "AI-4", "AI-5", "AI-6"]

ROLE_COUNTS = {
    4: "보안관 1 + 부관 0 + 무법자 2 + 배신자 1",
    5: "보안관 1 + 부관 1 + 무법자 2 + 배신자 1",
    6: "보안관 1 + 부관 1 + 무법자 3 + 배신자 1",
    7: "보안관 1 + 부관 2 + 무법자 3 + 배신자 1",
}


class SetupScreen:
    def __init__(self, screen: pygame.Surface, mode: str):
        self.screen = screen
        self.mode   = mode      # 'local' | 'ai'
        self.n      = 4
        # For AI mode: only player 0 is human by default
        self.human_ids: list[int] = list(range(self.n)) if mode == "local" else [0]
        self._build_buttons()

    def _build_buttons(self):
        cx = WIN_W // 2
        self.btn_minus = Button((cx - 100, 188, 42, 42), "−", DIM, radius=8)
        self.btn_plus  = Button((cx +  58, 188, 42, 42), "+", DIM, radius=8)
        self.btn_start = Button((cx - 120, WIN_H - 90, 240, 54), "게임 시작!", GREEN,
                                radius=12, fkey="sub")
        self.btn_back  = Button((30, WIN_H - 90, 100, 40), "← 뒤로", DIM, radius=8)
        self._rebuild_toggles()

    def _rebuild_toggles(self):
        self.toggles: list[tuple[int, Button]] = []
        span = self.n * 125
        sx   = WIN_W // 2 - span // 2
        for i in range(self.n):
            if self.mode == "local":
                label = f"P{i+1}  사람"
                col   = ACCENT
            else:
                is_h  = i in self.human_ids
                label = f"P{i+1} {'사람' if is_h else 'AI'}"
                col   = BLUE if is_h else (80, 80, 90)
            btn = Button((sx + i * 125, 330, 115, 48), label, col, radius=8)
            self.toggles.append((i, btn))

    def handle(self, event) -> dict | None:
        pos = pygame.mouse.get_pos()

        if self.btn_back.clicked(event, pos):
            return {"action": "back"}

        if self.btn_minus.clicked(event, pos) and self.n > 4:
            self.n -= 1
            self.human_ids = [h for h in self.human_ids if h < self.n]
            if self.mode == "local":
                self.human_ids = list(range(self.n))
            self._build_buttons()

        if self.btn_plus.clicked(event, pos) and self.n < 7:
            self.n += 1
            if self.mode == "local":
                self.human_ids = list(range(self.n))
            self._build_buttons()

        if self.mode == "ai":
            for idx, btn in self.toggles:
                if btn.clicked(event, pos) and idx != 0:  # P1 always human in AI mode
                    if idx in self.human_ids:
                        self.human_ids.remove(idx)
                    else:
                        self.human_ids.append(idx)
                    self._rebuild_toggles()

        if self.btn_start.clicked(event, pos):
            if self.mode == "local":
                names = _DEFAULT_NAMES_LOCAL[:self.n]
                human_ids = list(range(self.n))
            else:
                names = _DEFAULT_NAMES_AI[:self.n]
                human_ids = self.human_ids
            return {
                "action": "start",
                "n": self.n,
                "human_ids": human_ids,
                "names": names,
                "mode": self.mode,
            }
        return None

    def draw(self):
        s   = self.screen
        pos = pygame.mouse.get_pos()
        s.fill(BG)
        cx = WIN_W // 2

        draw_text(s, "게임 설정", "large", GOLD, cx, 52, "center")
        mode_label = "로컬 플레이" if self.mode == "local" else "AI 대전"
        draw_text(s, f"모드: {mode_label}", "small", GRAY, cx, 96, "center")

        # Player count
        rounded_rect(s, PANEL_BG, pygame.Rect(cx - 200, 162, 400, 82), 12)
        draw_text(s, "플레이어 수", "small", GRAY, cx, 170, "center")
        draw_text(s, str(self.n), "large", GOLD, cx, 194, "center")
        self.btn_minus.draw(s, self.btn_minus.is_hovered(pos))
        self.btn_plus.draw(s, self.btn_plus.is_hovered(pos))

        # Role composition
        draw_text(s, ROLE_COUNTS[self.n], "tiny", (160, 140, 80), cx, 258, "center")

        # Player type toggles
        if self.mode == "ai":
            draw_text(s, "클릭으로 사람 / AI 전환  (P1은 항상 사람)", "small",
                      GRAY, cx, 304, "center")
        else:
            draw_text(s, "로컬 플레이: 모든 플레이어 같은 화면 사용", "small",
                      GRAY, cx, 304, "center")

        for _, btn in self.toggles:
            btn.draw(s, btn.is_hovered(pos))

        # Rules summary
        ry = 408
        rounded_rect(s, PANEL_BG, pygame.Rect(cx - 340, ry, 680, 200), 12)
        rules = [
            ("목표",   "역할에 따라 다른 승리 조건 달성"),
            ("보안관", "무법자·배신자 전원 제거 → 보안관+부관 승리"),
            ("무법자", "보안관을 처치하면 무법자 승리"),
            ("배신자", "마지막 1명으로 살아남으면 배신자 승리"),
            ("턴 순서","드로우 2장 → 카드 플레이 → HP만큼 버리기"),
        ]
        for i, (k, v) in enumerate(rules):
            draw_text(s, k, "small", GOLD,  cx - 330, ry + 14 + i * 34)
            draw_text(s, v, "small", WHITE, cx - 260, ry + 14 + i * 34)

        self.btn_start.draw(s, self.btn_start.is_hovered(pos))
        self.btn_back.draw(s, self.btn_back.is_hovered(pos))
        pygame.display.flip()
