"""
턴제 전략 게임 GUI (pygame)
- 설정 화면: 플레이어 수(2~6) 및 인간/AI 지정
- 게임 화면: 보드, 손패, 행동 버튼, 로그, 동적 난이도 표시
"""

import os
import sys
import pygame
import pygame.font

from game import GameEnv, BOARD_SIZE
from agent import DynamicDifficultyAgent
from train import train

# ── 색상 팔레트 ──────────────────────────────────────────────────────────
BG          = (18,  18,  30)
PANEL       = (30,  30,  50)
ACCENT      = (80, 140, 255)
ACCENT2     = (255, 180,  50)
WHITE       = (240, 240, 240)
GRAY        = (120, 120, 140)
DARK_GRAY   = (50,  50,  70)
GREEN       = (80, 210, 120)
RED         = (230,  80,  80)
YELLOW      = (255, 220,  60)
SUPPLY_COL  = (100, 200, 255)
HOME_COL    = (255, 160, 100)
BTN_HOVER   = (60, 110, 200)

# 플레이어별 색상 (최대 6명)
PLAYER_COLORS = [
    (100, 180, 255),
    (255, 130,  80),
    (120, 220, 120),
    (220, 100, 220),
    (255, 220,  60),
    (100, 220, 200),
]

WIN_W, WIN_H = 1100, 700
MODEL_PATH   = "model.pkl"
FPS          = 60


# ── 유틸 ─────────────────────────────────────────────────────────────────
def draw_rounded_rect(surf, color, rect, radius=10, border=0, border_color=None):
    pygame.draw.rect(surf, color, rect, border_radius=radius)
    if border:
        pygame.draw.rect(surf, border_color or WHITE, rect, border, border_radius=radius)


def draw_text(surf, text, font, color, x, y, anchor="topleft"):
    img = font.render(text, True, color)
    r = img.get_rect(**{anchor: (x, y)})
    surf.blit(img, r)
    return r


# ── 버튼 클래스 ───────────────────────────────────────────────────────────
class Button:
    def __init__(self, rect, label, color=ACCENT, font=None, radius=10):
        self.rect   = pygame.Rect(rect)
        self.label  = label
        self.color  = color
        self.font   = font
        self.radius = radius
        self.enabled = True

    def draw(self, surf, hover=False):
        col = BTN_HOVER if hover and self.enabled else self.color
        if not self.enabled:
            col = DARK_GRAY
        draw_rounded_rect(surf, col, self.rect, self.radius)
        pygame.draw.rect(surf, WHITE, self.rect, 1, border_radius=self.radius)
        f = self.font or pygame.font.SysFont("malgungothic", 16)
        draw_text(surf, self.label, f, WHITE if self.enabled else GRAY,
                  self.rect.centerx, self.rect.centery, "center")

    def is_hovered(self, pos):
        return self.rect.collidepoint(pos)

    def clicked(self, pos, event):
        return (self.enabled and event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1 and self.rect.collidepoint(pos))


# ══════════════════════════════════════════════════════════════════════════
# 설정 화면
# ══════════════════════════════════════════════════════════════════════════
class SetupScreen:
    def __init__(self, screen, fonts):
        self.screen  = screen
        self.fonts   = fonts
        self.n_players = 2           # 선택된 플레이어 수
        self.human_ids: list[int] = [0]   # 사람으로 설정된 인덱스
        self._build()

    def _build(self):
        self.minus_btn = Button((WIN_W//2 - 80, 210, 40, 40), "−", DARK_GRAY)
        self.plus_btn  = Button((WIN_W//2 + 40, 210, 40, 40), "+", DARK_GRAY)
        self.start_btn = Button((WIN_W//2 - 100, 560, 200, 50), "게임 시작", GREEN, radius=12)
        self.toggle_btns: list[Button] = []
        self._rebuild_toggle_btns()

    def _rebuild_toggle_btns(self):
        self.toggle_btns = []
        for i in range(self.n_players):
            x = WIN_W//2 - (self.n_players * 110)//2 + i * 110
            y = 340
            col = ACCENT if i in self.human_ids else GRAY
            self.toggle_btns.append(Button((x, y, 100, 44),
                                           f"P{i+1}\n{'사람' if i in self.human_ids else 'AI'}",
                                           col, radius=8))

    def handle(self, event):
        pos = pygame.mouse.get_pos()
        if self.minus_btn.clicked(pos, event):
            if self.n_players > 2:
                self.n_players -= 1
                self.human_ids = [h for h in self.human_ids if h < self.n_players]
                self._rebuild_toggle_btns()
        if self.plus_btn.clicked(pos, event):
            if self.n_players < 6:
                self.n_players += 1
                self._rebuild_toggle_btns()
        for i, btn in enumerate(self.toggle_btns):
            if btn.clicked(pos, event):
                if i in self.human_ids:
                    self.human_ids.remove(i)
                else:
                    self.human_ids.append(i)
                self._rebuild_toggle_btns()
        if self.start_btn.clicked(pos, event):
            return "start"
        return None

    def draw(self):
        s = self.screen
        s.fill(BG)
        draw_text(s, "턴제 전략 게임", self.fonts["title"], WHITE,
                  WIN_W//2, 80, "center")
        draw_text(s, "AI 강화학습 × 동적 난이도 조정", self.fonts["sub"], GRAY,
                  WIN_W//2, 130, "center")

        # 플레이어 수 선택
        draw_rounded_rect(s, PANEL, pygame.Rect(WIN_W//2-160, 185, 320, 90), 12)
        draw_text(s, "플레이어 수", self.fonts["normal"], GRAY, WIN_W//2, 192, "center")
        draw_text(s, str(self.n_players), self.fonts["large"], ACCENT2,
                  WIN_W//2, 218, "center")
        pos = pygame.mouse.get_pos()
        self.minus_btn.draw(s, self.minus_btn.is_hovered(pos))
        self.plus_btn.draw(s, self.plus_btn.is_hovered(pos))

        # 사람/AI 토글
        draw_text(s, "각 플레이어 유형 설정 (클릭하여 변경)", self.fonts["small"], GRAY,
                  WIN_W//2, 305, "center")
        for btn in self.toggle_btns:
            lines = btn.label.split("\n")
            col = ACCENT if btn.color == ACCENT else GRAY
            draw_rounded_rect(s, col, btn.rect, 8)
            pygame.draw.rect(s, WHITE, btn.rect, 1, border_radius=8)
            draw_text(s, lines[0], self.fonts["normal"], WHITE,
                      btn.rect.centerx, btn.rect.top + 8, "midtop")
            draw_text(s, lines[1], self.fonts["small"], WHITE,
                      btn.rect.centerx, btn.rect.bottom - 8, "midbottom")

        # 규칙 요약
        rules = [
            f"목표: {BOARD_SIZE}칸을 먼저 줄이면 승리",
            "매 턴: 이동(1칸) 또는 카드 사용",
            "집 카드: 0~60 랜덤 이동  |  보급 카드: 게임당 1회 사용",
        ]
        ry = 430
        draw_rounded_rect(s, PANEL, pygame.Rect(WIN_W//2-280, ry-10, 560, 95), 10)
        for r in rules:
            draw_text(s, r, self.fonts["small"], GRAY, WIN_W//2, ry, "center")
            ry += 26

        self.start_btn.draw(s, self.start_btn.is_hovered(pos))
        pygame.display.flip()


# ══════════════════════════════════════════════════════════════════════════
# 게임 화면
# ══════════════════════════════════════════════════════════════════════════
class GameScreen:
    LOG_MAX = 14

    def __init__(self, screen, fonts, num_players: int, human_ids: list):
        self.screen    = screen
        self.fonts     = fonts
        self.num_players = num_players
        self.human_ids = human_ids

        # AI 에이전트 초기화
        self.agents: list[DynamicDifficultyAgent] = []
        for _ in range(num_players):
            ag = DynamicDifficultyAgent(epsilon=0.1, epsilon_min=0.05)
            if os.path.exists(MODEL_PATH):
                ag.load(MODEL_PATH)
                ag.epsilon = 0.1
            else:
                ag.epsilon = 0.4
            self.agents.append(ag)

        self.env = GameEnv(num_players=num_players, human_ids=human_ids)
        self.env.reset()

        self.log: list[str]   = []
        self.result_msg: str  = ""
        self.dda_msg: str     = ""
        self.waiting_human    = False
        self.action_btns: list[Button] = []
        self.menu_btn  = Button((WIN_W - 130, 10, 120, 38), "설정으로", DARK_GRAY, radius=8)
        self.again_btn = Button((WIN_W//2 - 90, WIN_H//2 + 60, 180, 48), "다시 시작", GREEN, radius=10)
        self._refresh_action_buttons()
        self._maybe_ai_step()

    # ── 행동 버튼 생성 ──────────────────────────────────────────────────
    def _refresh_action_buttons(self):
        if self.env.done:
            self.action_btns = []
            return
        pid = self.env.current_pid
        valid = self.env.get_valid_actions(pid)
        me = self.env.players[pid]
        labels = {
            0: "이동  (+1칸)",
            1: f"집 카드  (+{me.get_best_home_card().value if me.get_best_home_card() else 0}칸)",
            2: f"보급 카드  (+{me.get_supply_card().value if me.get_supply_card() else 0}칸)",
        }
        colors = {0: ACCENT, 1: HOME_COL, 2: SUPPLY_COL}
        self.action_btns = []
        bx = 30
        for a in valid:
            btn = Button((bx, WIN_H - 68, 170, 48), labels[a], colors[a], radius=8)
            self.action_btns.append((a, btn))
            bx += 185

    # ── AI 자동 행동 ────────────────────────────────────────────────────
    def _maybe_ai_step(self):
        while not self.env.done:
            pid = self.env.current_pid
            if pid in self.human_ids:
                self.waiting_human = True
                self._refresh_action_buttons()
                return
            # AI 차례
            state   = self.env.get_state(pid)
            valid   = self.env.get_valid_actions(pid)
            action  = self.agents[pid].choose_action(state, valid)
            reward, done = self.env.step(pid, action)
            win_p = self.agents[pid].predict_win_prob(state, valid)
            name  = self.env.players[pid].name
            act_str = ["이동", "집카드", "보급카드"][action]
            self._log(f"{name}: {act_str}  (승리예측 {win_p:.0%})")
            if done:
                self._on_game_end()
                return
        self.waiting_human = False

    def _log(self, msg: str):
        self.log.append(msg)
        if len(self.log) > self.LOG_MAX:
            self.log.pop(0)

    def _on_game_end(self):
        winner = self.env.players[self.env.winner]
        self.result_msg = f"🏆  {winner.name}  승리!"
        # DDA 기록 및 조정
        for pid, ag in enumerate(self.agents):
            if pid not in self.human_ids:
                ai_won = (self.env.winner != pid)
                ag.record_result(ai_won=ai_won)
                msg = ag.adjust_difficulty()
                if msg:
                    self.dda_msg = msg

    # ── 이벤트 처리 ─────────────────────────────────────────────────────
    def handle(self, event):
        pos = pygame.mouse.get_pos()
        if self.menu_btn.clicked(pos, event):
            return "menu"
        if self.env.done:
            if self.again_btn.clicked(pos, event):
                self.env.reset()
                self.log = []
                self.result_msg = ""
                self.dda_msg = ""
                self.waiting_human = False
                self._maybe_ai_step()
            return None

        if self.waiting_human and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for action, btn in self.action_btns:
                if btn.is_hovered(pos):
                    pid  = self.env.current_pid
                    state = self.env.get_state(pid)
                    valid = self.env.get_valid_actions(pid)
                    reward, done = self.env.step(pid, action)
                    name = self.env.players[pid].name
                    act_str = ["이동", "집카드", "보급카드"][action]
                    self._log(f"{name}: {act_str}")
                    self.waiting_human = False
                    if done:
                        self._on_game_end()
                    else:
                        self._maybe_ai_step()
                    break
        return None

    # ── 보드 그리기 ─────────────────────────────────────────────────────
    def _draw_board(self):
        s = self.screen
        bx, by = 30, 30
        bw, bh = WIN_W - 370, 130
        cell_w = bw / BOARD_SIZE

        draw_rounded_rect(s, PANEL, pygame.Rect(bx-5, by-5, bw+10, bh+10), 10)

        # 칸 구분선
        for i in range(BOARD_SIZE + 1):
            x = int(bx + i * cell_w)
            pygame.draw.line(s, DARK_GRAY, (x, by + 10), (x, by + bh - 10))

        # 목표 지점 (왼쪽 끝 = 0)
        goal_x = bx
        pygame.draw.rect(s, YELLOW, (goal_x, by + 15, max(3, int(cell_w)), bh - 30), border_radius=4)
        draw_text(s, "GOAL", self.fonts["tiny"], YELLOW, goal_x + 2, by + bh//2, "midleft")

        # 플레이어 토큰 (여러 명 겹칠 때 오프셋)
        offset_per = 20
        for i, p in enumerate(self.env.players):
            px = int(bx + (p.position / BOARD_SIZE) * bw)
            py = by + bh // 2 + (i - self.num_players // 2) * offset_per
            col = PLAYER_COLORS[i % len(PLAYER_COLORS)]
            if i == self.env.current_pid and not self.env.done:
                pygame.draw.circle(s, col, (px, py), 14)
                pygame.draw.circle(s, WHITE, (px, py), 14, 2)
            else:
                pygame.draw.circle(s, col, (px, py), 10)
            draw_text(s, f"P{i+1}", self.fonts["tiny"], BG, px, py, "center")

        # 범례
        lx = bx
        for i, p in enumerate(self.env.players):
            col = PLAYER_COLORS[i % len(PLAYER_COLORS)]
            pygame.draw.circle(s, col, (lx + 8, by + bh + 18), 7)
            draw_text(s, f"{p.name}  {p.position}칸", self.fonts["tiny"], WHITE,
                      lx + 20, by + bh + 10)
            lx += max(120, len(p.name) * 10 + 80)

    # ── 손패 그리기 ─────────────────────────────────────────────────────
    def _draw_hand(self):
        if self.env.done:
            return
        pid = self.env.current_pid
        if pid not in self.human_ids:
            return
        me = self.env.players[pid]
        s  = self.screen
        hx, hy = 30, WIN_H - 180
        draw_text(s, "손패", self.fonts["small"], GRAY, hx, hy - 20)
        for i, card in enumerate(me.hand):
            col = SUPPLY_COL if card.card_type == "supply" else HOME_COL
            cr = pygame.Rect(hx + i * 90, hy, 82, 58)
            draw_rounded_rect(s, col, cr, 8)
            pygame.draw.rect(s, WHITE, cr, 1, border_radius=8)
            t = "보급" if card.card_type == "supply" else "집"
            draw_text(s, t, self.fonts["tiny"], BG, cr.centerx, cr.top + 10, "midtop")
            draw_text(s, f"+{card.value}", self.fonts["normal"], BG,
                      cr.centerx, cr.centery + 5, "center")

    # ── 오른쪽 패널 ─────────────────────────────────────────────────────
    def _draw_panel(self):
        s  = self.screen
        px = WIN_W - 330
        draw_rounded_rect(s, PANEL, pygame.Rect(px - 10, 20, 330, WIN_H - 40), 12)

        # 현재 차례 표시
        if not self.env.done:
            pid = self.env.current_pid
            col = PLAYER_COLORS[pid % len(PLAYER_COLORS)]
            draw_rounded_rect(s, col, pygame.Rect(px, 28, 310, 38), 8)
            name = self.env.players[pid].name
            turn_str = f"턴 {self.env.turn + 1}  —  {name}의 차례"
            draw_text(s, turn_str, self.fonts["normal"], BG, px + 155, 47, "center")

        # 플레이어 상태 목록
        draw_text(s, "플레이어 현황", self.fonts["small"], GRAY, px, 80)
        for i, p in enumerate(self.env.players):
            col = PLAYER_COLORS[i % len(PLAYER_COLORS)]
            ry = 100 + i * 72
            draw_rounded_rect(s, DARK_GRAY, pygame.Rect(px, ry, 310, 65), 8)
            if i == self.env.current_pid and not self.env.done:
                pygame.draw.rect(s, col, pygame.Rect(px, ry, 310, 65), 2, border_radius=8)
            pygame.draw.circle(s, col, (px + 18, ry + 18), 12)
            draw_text(s, f"P{i+1}", self.fonts["tiny"], BG, px + 18, ry + 18, "center")
            draw_text(s, p.name, self.fonts["small"], WHITE, px + 36, ry + 8)
            bar_w = int(300 * (1 - p.position / BOARD_SIZE))
            pygame.draw.rect(s, DARK_GRAY, (px + 5, ry + 38, 300, 14), border_radius=6)
            pygame.draw.rect(s, col, (px + 5, ry + 38, bar_w, 14), border_radius=6)
            pct = (1 - p.position / BOARD_SIZE) * 100
            draw_text(s, f"{pct:.0f}%  남은거리:{p.position}", self.fonts["tiny"], WHITE,
                      px + 10, ry + 40)
            supply_txt = "보급:사용" if p.supply_used else "보급:가능"
            draw_text(s, supply_txt, self.fonts["tiny"], SUPPLY_COL if not p.supply_used else GRAY,
                      px + 230, ry + 8)

        # DDA 메시지
        log_y = 110 + self.num_players * 72
        if self.dda_msg:
            draw_rounded_rect(s, (40, 60, 40), pygame.Rect(px, log_y, 310, 26), 6)
            draw_text(s, f"난이도: {self.dda_msg}", self.fonts["tiny"], GREEN, px + 6, log_y + 4)
            log_y += 32

        # 게임 로그
        draw_text(s, "게임 로그", self.fonts["small"], GRAY, px, log_y)
        log_y += 20
        for line in self.log[-(self.LOG_MAX - self.num_players * 3):]:
            draw_text(s, line, self.fonts["tiny"], WHITE, px, log_y)
            log_y += 18

    # ── 행동 버튼 ────────────────────────────────────────────────────────
    def _draw_action_buttons(self):
        if self.env.done or not self.waiting_human:
            return
        pos = pygame.mouse.get_pos()
        draw_text(self.screen, "행동 선택:", self.fonts["small"], GRAY, 30, WIN_H - 90)
        for _, btn in self.action_btns:
            btn.draw(self.screen, btn.is_hovered(pos))

    # ── 결과 오버레이 ────────────────────────────────────────────────────
    def _draw_result(self):
        if not self.result_msg:
            return
        s   = self.screen
        ov  = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 160))
        s.blit(ov, (0, 0))
        draw_rounded_rect(s, PANEL, pygame.Rect(WIN_W//2 - 220, WIN_H//2 - 80, 440, 200), 16)
        draw_text(s, self.result_msg, self.fonts["large"], YELLOW,
                  WIN_W//2, WIN_H//2 - 40, "center")
        pos = pygame.mouse.get_pos()
        self.again_btn.draw(s, self.again_btn.is_hovered(pos))

    # ── 전체 드로우 ──────────────────────────────────────────────────────
    def draw(self):
        self.screen.fill(BG)
        self._draw_board()
        self._draw_panel()
        self._draw_hand()
        self._draw_action_buttons()
        self._draw_result()

        pos = pygame.mouse.get_pos()
        self.menu_btn.draw(self.screen, self.menu_btn.is_hovered(pos))
        pygame.display.flip()


# ══════════════════════════════════════════════════════════════════════════
# 로딩 화면 (학습)
# ══════════════════════════════════════════════════════════════════════════
def run_loading_screen(screen, fonts):
    screen.fill(BG)
    draw_text(screen, "AI 학습 중...", fonts["title"], WHITE, WIN_W//2, WIN_H//2 - 40, "center")
    draw_text(screen, "처음 실행 시 약 1~2분 소요됩니다", fonts["sub"], GRAY,
              WIN_W//2, WIN_H//2 + 10, "center")
    pygame.display.flip()
    train(episodes=8000, save_path=MODEL_PATH, verbose_every=9999)


# ══════════════════════════════════════════════════════════════════════════
# 메인 루프
# ══════════════════════════════════════════════════════════════════════════
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("턴제 전략 게임 — AI 강화학습")

    # 한글 폰트 (시스템에 따라 fallback)
    def load_font(size):
        for name in ["malgungothic", "nanumgothic", "gulim", "notosanskr", "freesansbold"]:
            try:
                return pygame.font.SysFont(name, size)
            except Exception:
                pass
        return pygame.font.Font(None, size)

    fonts = {
        "title":  load_font(38),
        "large":  load_font(30),
        "sub":    load_font(22),
        "normal": load_font(18),
        "small":  load_font(15),
        "tiny":   load_font(13),
    }

    clock = pygame.time.Clock()

    # 첫 실행 시 학습
    if not os.path.exists(MODEL_PATH):
        run_loading_screen(screen, fonts)

    setup  = SetupScreen(screen, fonts)
    state  = "setup"
    game: GameScreen | None = None

    while True:
        pos = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            if state == "setup":
                result = setup.handle(event)
                if result == "start":
                    game = GameScreen(screen, fonts,
                                      setup.n_players,
                                      list(setup.human_ids))
                    state = "game"

            elif state == "game" and game:
                result = game.handle(event)
                if result == "menu":
                    setup  = SetupScreen(screen, fonts)
                    state  = "setup"

        if state == "setup":
            setup.draw()
        elif state == "game" and game:
            game.draw()

        clock.tick(FPS)


if __name__ == "__main__":
    main()
