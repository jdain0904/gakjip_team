"""설정 화면: 플레이어 수 + 이름/타입 구성."""
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


DIFFICULTY_LABELS = ["쉬움", "보통", "어려움"]
DIFFICULTY_COLORS = [
    (50, 140, 70),    # 녹색 – 쉬움
    (60, 100, 180),   # 청색 – 보통
    (160, 50, 50),    # 적색 – 어려움
]


class SetupScreen:
    """게임 시작 전 설정 화면: 플레이어 수, 사람/AI 배정, AI 난이도를
    정한 뒤 GameState.new_game()에 필요한 dict를 만들어 반환한다."""
    def __init__(self, screen: pygame.Surface, mode: str):
        self.screen = screen
        self.mode   = mode      # 'local' | 'ai'
        self.n      = 4
        self.ai_difficulty = 1   # 0=쉬움 1=보통 2=어려움
        # AI 모드에서는 기본적으로 플레이어 0만 사람으로 설정
        self.human_ids: list[int] = list(range(self.n)) if mode == "local" else [0]
        self._build_buttons()

    def _build_buttons(self):
        cx = WIN_W // 2
        self.btn_minus = Button((cx - 100, 188, 42, 42), "-", DIM, radius=8)
        self.btn_plus  = Button((cx +  58, 188, 42, 42), "+", DIM, radius=8)
        self.btn_start = Button((cx - 120, WIN_H - 90, 240, 54), "게임 시작!", GREEN,
                                radius=12, fkey="sub")
        self.btn_back  = Button((30, WIN_H - 90, 100, 40), "< 뒤로", DIM, radius=8)
        # 난이도 버튼 (AI 모드에서만 사용)
        self.diff_btns: list[Button] = []
        if self.mode == "ai":
            bw, bh, gap = 100, 38, 10
            total = len(DIFFICULTY_LABELS) * bw + (len(DIFFICULTY_LABELS) - 1) * gap
            sx = cx - total // 2
            for di, lbl in enumerate(DIFFICULTY_LABELS):
                col = DIFFICULTY_COLORS[di]
                self.diff_btns.append(
                    Button((sx + di * (bw + gap), 292, bw, bh), lbl, col, radius=8)
                )
        self._rebuild_toggles()

    def _rebuild_toggles(self):
        self.toggles: list[tuple[int, Button]] = []
        span = self.n * 125
        sx   = WIN_W // 2 - span // 2
        ty   = 386 if self.mode == "ai" else 330
        for i in range(self.n):
            if self.mode == "local":
                label = f"P{i+1}  사람"
                col   = ACCENT
            else:
                is_h  = i in self.human_ids
                label = f"P{i+1} {'사람' if is_h else 'AI'}"
                col   = BLUE if is_h else (80, 80, 90)
            btn = Button((sx + i * 125, ty, 115, 48), label, col, radius=8)
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
            for di, dbtn in enumerate(self.diff_btns):
                if dbtn.clicked(event, pos):
                    self.ai_difficulty = di
                    break
            for idx, btn in self.toggles:
                if btn.clicked(event, pos) and idx != 0:  # AI 모드에서 P1은 항상 사람
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
                "action":        "start",
                "n":             self.n,
                "human_ids":     human_ids,
                "names":         names,
                "mode":          self.mode,
                "ai_difficulty": self.ai_difficulty,
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

        # 플레이어 수
        rounded_rect(s, PANEL_BG, pygame.Rect(cx - 200, 162, 400, 82), 12)
        draw_text(s, "플레이어 수", "small", GRAY, cx, 170, "center")
        draw_text(s, str(self.n), "large", GOLD, cx, 194, "center")
        self.btn_minus.draw(s, self.btn_minus.is_hovered(pos))
        self.btn_plus.draw(s, self.btn_plus.is_hovered(pos))

        # 역할 구성
        draw_text(s, ROLE_COUNTS[self.n], "tiny", (160, 140, 80), cx, 258, "center")

        # 난이도 선택 + 플레이어 타입 토글 (AI 모드)
        if self.mode == "ai":
            draw_text(s, "AI 난이도", "small", GRAY, cx, 272, "center")
            for di, dbtn in enumerate(self.diff_btns):
                dbtn.draw(s, dbtn.is_hovered(pos))
                if di == self.ai_difficulty:
                    r = pygame.Rect(dbtn.rect)
                    pygame.draw.rect(s, (255, 220, 80), r, 3, border_radius=8)
            diff_descs = ["AI가 무작위로 행동합니다",
                          "승률 예측 모델로 실시간 난이도를 조절합니다",
                          "강화학습으로 학습한 가중치로 항상 최적의 수를 둡니다"]
            draw_text(s, diff_descs[self.ai_difficulty], "tiny", GOLD, cx, 344, "center")
            draw_text(s, "클릭으로 사람 / AI 전환  (P1은 항상 사람)", "small",
                      GRAY, cx, 368, "center")
        else:
            draw_text(s, "로컬 플레이: 모든 플레이어 같은 화면 사용", "small",
                      GRAY, cx, 304, "center")

        for _, btn in self.toggles:
            btn.draw(s, btn.is_hovered(pos))

        # 규칙 요약
        ry = 442
        rounded_rect(s, PANEL_BG, pygame.Rect(cx - 340, ry, 680, 200), 12)
        rules = [
            ("목표",   "역할에 따라 다른 승리 조건 달성"),
            ("보안관", "무법자·배신자 전원 제거 > 보안관+부관 승리"),
            ("무법자", "보안관을 처치하면 무법자 승리"),
            ("배신자", "마지막 1명으로 살아남으면 배신자 승리"),
            ("턴 순서","드로우 2장 > 카드 플레이 > HP만큼 버리기"),
        ]
        for i, (k, v) in enumerate(rules):
            draw_text(s, k, "small", GOLD,  cx - 330, ry + 14 + i * 34)
            draw_text(s, v, "small", WHITE, cx - 260, ry + 14 + i * 34)

        self.btn_start.draw(s, self.btn_start.is_hovered(pos))
        self.btn_back.draw(s, self.btn_back.is_hovered(pos))
        pygame.display.flip()
