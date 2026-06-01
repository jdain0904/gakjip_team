"""
턴제 전략 게임 GUI
- 아이소메트릭 과녁 게임판 (45도 기울인 동심원)
- 플레이어 수 설정, 사람/AI 개별 지정
- 카드 뽑기 시스템 (덱에서 랜덤 드로우)
"""

import os, sys, math, random
import pygame

from game import GameEnv, BOARD_SIZE, MAX_HAND
from agent import DynamicDifficultyAgent
from train import train

# ─── 색상 ────────────────────────────────────────────────────────────────
BG          = (14,  16,  26)
PANEL_BG    = (22,  26,  42)
PANEL_DARK  = (16,  19,  32)
WHITE       = (230, 235, 245)
GRAY        = (110, 115, 135)
DIM         = ( 55,  58,  78)
ACCENT      = ( 80, 145, 255)
GREEN       = ( 70, 205, 110)
RED         = (215,  75,  75)
YELLOW      = (255, 215,  50)
GOLD        = (255, 185,  30)
SUPPLY_C    = ( 90, 195, 255)
HOME_C      = (255, 150,  80)
DRAW_C      = (160, 110, 255)
MOVE_C      = ( 80, 180, 120)

PLAYER_COLORS = [
    (100, 175, 255),
    (255, 120,  70),
    (100, 220, 120),
    (210,  90, 210),
    (255, 215,  55),
    ( 80, 215, 195),
]

# 링 색상: 바깥(차갑고 어두움) → 안(밝고 따뜻함)
RING_COLORS = [
    ( 30,  38,  65),
    ( 35,  48,  80),
    ( 40,  58,  85),
    ( 45,  70,  90),
    ( 55,  82,  85),
    ( 65,  95,  75),
    ( 80, 110,  60),
    (105, 120,  45),
    (145, 130,  35),
    (185, 150,  25),
]

WIN_W, WIN_H = 1180, 720
MODEL_PATH   = "model.pkl"
FPS          = 60

# ─── 아이소메트릭 과녁판 설정 ─────────────────────────────────────────────
BOARD_CX = 390          # 판 중심 x
BOARD_CY = 370          # 판 중심 y (아래로 내려 원근감)
BOARD_RX = 300          # 최대 가로 반지름
BOARD_RY = 150          # 최대 세로 반지름 (rx * 0.5 → 45도 기울임)
N_RINGS  = 10           # 링 개수 (BOARD_SIZE / 5)
SPOKE_N  = 12           # 방사선 수


# ═══════════════════════════════════════════════════════════════════════════
# 유틸
# ═══════════════════════════════════════════════════════════════════════════
def lerp_color(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def draw_text(surf, text, font, color, x, y, anchor="topleft"):
    img = font.render(text, True, color)
    r = img.get_rect(**{anchor: (x, y)})
    surf.blit(img, r)
    return r


def rounded_rect(surf, color, rect, r=10, border=0, bc=None):
    pygame.draw.rect(surf, color, rect, border_radius=r)
    if border:
        pygame.draw.rect(surf, bc or WHITE, rect, border, border_radius=r)


# ─── 아이소메트릭 좌표 변환 ───────────────────────────────────────────────
def iso_point(frac: float, angle_rad: float):
    """frac=0 → 중심, frac=1 → 가장자리"""
    x = BOARD_CX + math.cos(angle_rad) * frac * BOARD_RX
    y = BOARD_CY + math.sin(angle_rad) * frac * BOARD_RY
    return int(x), int(y)


# ═══════════════════════════════════════════════════════════════════════════
# 버튼
# ═══════════════════════════════════════════════════════════════════════════
class Button:
    def __init__(self, rect, label, color=ACCENT, radius=9, font=None):
        self.rect    = pygame.Rect(rect)
        self.label   = label
        self.color   = color
        self.radius  = radius
        self._font   = font
        self.enabled = True

    def draw(self, surf, hovered=False):
        c = tuple(min(255, v + 25) for v in self.color) if hovered and self.enabled else self.color
        if not self.enabled:
            c = DIM
        rounded_rect(surf, c, self.rect, self.radius)
        pygame.draw.rect(surf, (*WHITE[:3], 80), self.rect, 1, border_radius=self.radius)
        f = self._font or _fonts.get("small")
        if f:
            draw_text(surf, self.label, f, WHITE if self.enabled else GRAY,
                      self.rect.centerx, self.rect.centery, "center")

    def hit(self, pos, event=None):
        if event:
            return self.enabled and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(pos)
        return self.rect.collidepoint(pos)


_fonts: dict = {}   # 전역 폰트 캐시


# ═══════════════════════════════════════════════════════════════════════════
# 카드 드로우 애니메이션
# ═══════════════════════════════════════════════════════════════════════════
class DrawAnim:
    DURATION = 40   # 프레임

    def __init__(self, card, start_pos, end_pos):
        self.card      = card
        self.start     = start_pos
        self.end       = end_pos
        self.frame     = 0
        self.done      = False

    def update(self):
        self.frame += 1
        if self.frame >= self.DURATION:
            self.done = True

    def draw(self, surf):
        t = self.frame / self.DURATION
        t = t * t * (3 - 2 * t)   # smoothstep
        x = int(self.start[0] + (self.end[0] - self.start[0]) * t)
        y = int(self.start[1] + (self.end[1] - self.start[1]) * t)
        alpha = int(255 * (1 - abs(t - 0.5) * 2))
        col = SUPPLY_C if self.card.card_type == "supply" else HOME_C
        r = pygame.Rect(x - 35, y - 24, 70, 48)
        rounded_rect(surf, (*col, alpha), r, 7)   # 단순 드로우 (alpha 무시됨, pygame surface 없이)
        rounded_rect(surf, col, r, 7)
        if _fonts.get("tiny"):
            draw_text(surf, self.card.label(), _fonts["tiny"], BG, r.centerx, r.centery, "center")


# ═══════════════════════════════════════════════════════════════════════════
# 아이소메트릭 게임판 렌더러
# ═══════════════════════════════════════════════════════════════════════════
class IsoBoard:
    """과녁형 아이소메트릭 보드"""

    # 미리 렌더링한 배경 Surface
    _cached_bg: pygame.Surface | None = None

    @classmethod
    def build_bg(cls):
        """정적 배경(링+방사선) 한 번만 그리기"""
        surf = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 0))

        # ── 링 (바깥 → 안 순서로 채우기) ────────────────────────────────
        for i in range(N_RINGS, 0, -1):
            frac  = i / N_RINGS
            rx    = int(BOARD_RX * frac)
            ry    = int(BOARD_RY * frac)
            col   = RING_COLORS[i - 1]
            rect  = pygame.Rect(BOARD_CX - rx, BOARD_CY - ry, rx * 2, ry * 2)
            pygame.draw.ellipse(surf, col, rect)

        # ── 링 테두리 ────────────────────────────────────────────────────
        for i in range(1, N_RINGS + 1):
            frac = i / N_RINGS
            rx   = int(BOARD_RX * frac)
            ry   = int(BOARD_RY * frac)
            rect = pygame.Rect(BOARD_CX - rx, BOARD_CY - ry, rx * 2, ry * 2)
            alpha_col = lerp_color((80, 90, 120), (200, 170, 50), (i - 1) / (N_RINGS - 1))
            pygame.draw.ellipse(surf, alpha_col, rect, 1)

        # ── 방사선 ───────────────────────────────────────────────────────
        for k in range(SPOKE_N):
            angle = math.pi * 2 * k / SPOKE_N
            ex, ey = iso_point(1.0, angle)
            pygame.draw.line(surf, (50, 55, 80), (BOARD_CX, BOARD_CY), (ex, ey), 1)

        # ── 거리 눈금 라벨 (5단위) ──────────────────────────────────────
        font = _fonts.get("tiny")
        label_angle = math.radians(-60)   # 오른쪽 위 방향
        for i in range(1, N_RINGS + 1):
            dist  = i * (BOARD_SIZE // N_RINGS)
            frac  = i / N_RINGS
            lx, ly = iso_point(frac + 0.04, label_angle)
            if font:
                draw_text(surf, str(dist), font, GRAY, lx, ly, "center")

        # ── 중심 별표 ────────────────────────────────────────────────────
        pygame.draw.circle(surf, GOLD, (BOARD_CX, BOARD_CY), 12)
        pygame.draw.circle(surf, WHITE, (BOARD_CX, BOARD_CY), 12, 2)
        if _fonts.get("tiny"):
            draw_text(surf, "GOAL", _fonts["tiny"], BG, BOARD_CX, BOARD_CY, "center")

        cls._cached_bg = surf

    @classmethod
    def draw(cls, surf, players, current_pid, done):
        if cls._cached_bg is None:
            cls.build_bg()
        surf.blit(cls._cached_bg, (0, 0))

        n = len(players)
        # 각 플레이어의 각도: 균등 배치 + 고정 오프셋
        angles = [math.radians(90 + 360 * i / n) for i in range(n)]

        # 플레이어 토큰 (뒤→앞 순서로 그려서 앞에 있는 플레이어가 위로)
        order = sorted(range(n), key=lambda i: players[i].position, reverse=True)

        for pid in order:
            p     = players[pid]
            frac  = p.position / BOARD_SIZE
            frac  = max(0.0, min(1.0, frac))
            tx, ty = iso_point(frac, angles[pid])
            col    = PLAYER_COLORS[pid % len(PLAYER_COLORS)]

            # 그림자
            pygame.draw.ellipse(surf, (0, 0, 0, 100),
                                 (tx - 14, ty + 10, 28, 10))

            # 현재 차례 → 더 크고 빛나게
            is_current = (pid == current_pid and not done)
            R = 18 if is_current else 13

            if is_current:
                # 글로우 효과 (여러 겹 반투명 원)
                for glow_r in [R + 10, R + 6, R + 3]:
                    glow_c = lerp_color(col, BG, 0.6)
                    pygame.draw.circle(surf, glow_c, (tx, ty), glow_r)

            pygame.draw.circle(surf, col, (tx, ty), R)
            pygame.draw.circle(surf, WHITE, (tx, ty), R, 2)

            # 플레이어 번호
            f = _fonts.get("small" if is_current else "tiny")
            if f:
                draw_text(surf, f"P{pid+1}", f, BG, tx, ty, "center")

            # 이름 툴팁 (현재 차례만)
            if is_current and _fonts.get("tiny"):
                draw_text(surf, p.name, _fonts["tiny"], col, tx, ty - R - 14, "center")


# ═══════════════════════════════════════════════════════════════════════════
# 카드 UI
# ═══════════════════════════════════════════════════════════════════════════
CARD_W, CARD_H = 88, 62
DECK_X, DECK_Y = 820, 30    # 덱 패일 위치 (오른쪽 패널 위)


def draw_card_widget(surf, card, x, y, highlight=False, small=False):
    cw = CARD_W - 10 if small else CARD_W
    ch = CARD_H - 8  if small else CARD_H
    col = SUPPLY_C if card.card_type == "supply" else HOME_C
    r   = pygame.Rect(x, y, cw, ch)

    # 배경
    rounded_rect(surf, DIM, r, 8)
    if highlight:
        rounded_rect(surf, col, r, 8, border=2, bc=WHITE)
    else:
        rounded_rect(surf, col, pygame.Rect(x, y + ch - 20, cw, 20), 0)
        rounded_rect(surf, DIM, r, 8, border=1, bc=col)

    # 타입 아이콘 텍스트
    f_label = _fonts.get("tiny")
    f_val   = _fonts.get("normal" if not small else "small")
    t = "보급" if card.card_type == "supply" else "집"
    icon = "⛽" if card.card_type == "supply" else "🏠"
    if f_label:
        draw_text(surf, t, f_label, BG if highlight else col, x + 5, y + 5)
    if f_val:
        draw_text(surf, f"+{card.value}", f_val, WHITE, x + cw // 2, y + ch // 2 - 2, "center")


def draw_deck_pile(surf, x, y):
    """덱 더미 시각화 (겹쳐진 카드 3장)"""
    for i in range(3, 0, -1):
        r = pygame.Rect(x + i * 2, y + i * 2, CARD_W, CARD_H)
        rounded_rect(surf, DIM, r, 8)
        pygame.draw.rect(surf, GRAY, r, 1, border_radius=8)
    # 앞 카드 (뒷면)
    fr = pygame.Rect(x, y, CARD_W, CARD_H)
    rounded_rect(surf, (45, 50, 75), fr, 8)
    pygame.draw.rect(surf, ACCENT, fr, 2, border_radius=8)
    if _fonts.get("small"):
        draw_text(surf, "덱", _fonts["small"], ACCENT, fr.centerx, fr.centery, "center")


# ═══════════════════════════════════════════════════════════════════════════
# 설정 화면
# ═══════════════════════════════════════════════════════════════════════════
class SetupScreen:
    def __init__(self, screen):
        self.screen    = screen
        self.n         = 2
        self.human_ids = [0]
        self._build()

    def _build(self):
        cx = WIN_W // 2
        self.minus = Button((cx - 90, 205, 42, 42), "−", DIM)
        self.plus  = Button((cx + 48, 205, 42, 42), "+", DIM)
        self.start = Button((cx - 110, 570, 220, 52), "게임 시작", GREEN, radius=13)
        self._rebuild_toggles()

    def _rebuild_toggles(self):
        self.toggles = []
        span = self.n * 115
        sx   = WIN_W // 2 - span // 2
        for i in range(self.n):
            is_h = i in self.human_ids
            col  = ACCENT if is_h else DIM
            self.toggles.append((i, Button((sx + i * 115, 325, 105, 50),
                                           f"P{i+1}  {'사람' if is_h else 'AI'}", col, radius=8)))

    def handle(self, event):
        pos = pygame.mouse.get_pos()
        if self.minus.hit(pos, event):
            if self.n > 2:
                self.n -= 1
                self.human_ids = [h for h in self.human_ids if h < self.n]
                self._rebuild_toggles()
        if self.plus.hit(pos, event):
            if self.n < 6:
                self.n += 1
                self._rebuild_toggles()
        for idx, btn in self.toggles:
            if btn.hit(pos, event):
                if idx in self.human_ids: self.human_ids.remove(idx)
                else: self.human_ids.append(idx)
                self._rebuild_toggles()
        if self.start.hit(pos, event):
            return "start"
        return None

    def draw(self):
        s   = self.screen
        pos = pygame.mouse.get_pos()
        s.fill(BG)

        # 배경 장식: 희미한 과녁
        IsoBoard.build_bg()
        ghost = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        ghost.blit(IsoBoard._cached_bg, (0, 0))
        ghost.set_alpha(35)
        s.blit(ghost, (0, 0))

        cx = WIN_W // 2
        draw_text(s, "턴제 전략 게임", _fonts["title"], WHITE, cx, 75, "center")
        draw_text(s, "AI 강화학습 × 동적 난이도 × 아이소메트릭 보드", _fonts["sub"], GRAY, cx, 128, "center")

        # 플레이어 수 선택
        rounded_rect(s, PANEL_BG, pygame.Rect(cx - 175, 178, 350, 90), 12)
        draw_text(s, "플레이어 수", _fonts["small"], GRAY, cx, 185, "center")
        draw_text(s, str(self.n), _fonts["large"], GOLD, cx, 210, "center")
        self.minus.draw(s, self.minus.hit(pos))
        self.plus.draw(s, self.plus.hit(pos))

        # 사람/AI 토글
        draw_text(s, "플레이어 유형 설정  (클릭으로 사람↔AI 전환)", _fonts["small"], GRAY, cx, 295, "center")
        for _, btn in self.toggles:
            btn.draw(s, btn.hit(pos))

        # 규칙 카드
        ry = 400
        rounded_rect(s, PANEL_BG, pygame.Rect(cx - 310, ry, 620, 145), 12)
        rules = [
            ("목표", f"중심까지 {BOARD_SIZE}칸을 먼저 줄이면 승리"),
            ("행동", "이동(1칸) / 집카드 사용 / 보급카드(1회) / 카드 뽑기"),
            ("카드", f"집·보급 카드: 0~60 랜덤 이동  |  손패 최대 {MAX_HAND}장"),
            ("AI",   "강화학습으로 훈련된 AI, 동적 난이도 자동 조절"),
        ]
        for i, (k, v) in enumerate(rules):
            draw_text(s, k, _fonts["small"], GOLD, cx - 300, ry + 14 + i * 30)
            draw_text(s, v, _fonts["small"], WHITE, cx - 260, ry + 14 + i * 30)

        self.start.draw(s, self.start.hit(pos))
        pygame.display.flip()


# ═══════════════════════════════════════════════════════════════════════════
# 게임 화면
# ═══════════════════════════════════════════════════════════════════════════
class GameScreen:
    LOG_MAX = 18
    RIGHT_X = 790    # 오른쪽 패널 시작 x

    def __init__(self, screen, num_players, human_ids):
        self.screen   = screen
        self.n        = num_players
        self.human_ids = human_ids

        # AI 에이전트
        self.agents = []
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

        self.log: list[str]  = []
        self.result_msg      = ""
        self.dda_msg         = ""
        self.anim: list      = []    # DrawAnim 목록
        self.waiting_human   = False
        self.action_btns: list[tuple] = []

        self.menu_btn  = Button((WIN_W - 125, 8, 115, 36), "← 설정", DIM, radius=8)
        self.again_btn = Button((WIN_W // 2 - 95, WIN_H // 2 + 70, 190, 50), "다시 시작", GREEN, radius=11)

        IsoBoard.build_bg()
        self._refresh_buttons()
        self._maybe_ai()

    # ── 행동 버튼 ─────────────────────────────────────────────────────────
    def _refresh_buttons(self):
        if self.env.done:
            self.action_btns = []
            return
        pid   = self.env.current_pid
        valid = self.env.get_valid_actions(pid)
        me    = self.env.players[pid]
        bh    = me.get_best_home_card()
        bs    = me.get_supply_card()
        info  = {
            0: ("이동 +1칸",        MOVE_C),
            1: (f"집카드 +{bh.value if bh else 0}", HOME_C),
            2: (f"보급카드 +{bs.value if bs else 0}", SUPPLY_C),
            3: ("카드 뽑기",         DRAW_C),
        }
        self.action_btns = []
        bx = self.RIGHT_X + 5
        for a in valid:
            label, col = info[a]
            btn = Button((bx, WIN_H - 68, 170, 48), label, col, radius=8)
            self.action_btns.append((a, btn))
            bx += 178

    # ── AI 자동 진행 ───────────────────────────────────────────────────────
    def _maybe_ai(self):
        while not self.env.done:
            pid = self.env.current_pid
            if pid in self.human_ids:
                self.waiting_human = True
                self._refresh_buttons()
                return
            state  = self.env.get_state(pid)
            valid  = self.env.get_valid_actions(pid)
            action = self.agents[pid].choose_action(state, valid)
            r, done, drew = self.env.step(pid, action)
            wp   = self.agents[pid].predict_win_prob(state, valid)
            name = self.env.players[pid].name
            acts = {0:"이동", 1:"집카드", 2:"보급카드", 3:"카드뽑기"}
            self._log(f"{name}: {acts[action]}  (승리예측{wp:.0%})")
            if drew:
                self._log(f"  └ 뽑은 카드: {drew.label()}")
            if done:
                self._on_end()
                return
        self.waiting_human = False

    def _log(self, msg):
        self.log.append(msg)
        if len(self.log) > self.LOG_MAX:
            self.log.pop(0)

    def _on_end(self):
        w = self.env.players[self.env.winner]
        self.result_msg = f"🏆  {w.name}  승리!"
        for pid, ag in enumerate(self.agents):
            if pid not in self.human_ids:
                ag.record_result(ai_won=(self.env.winner != pid))
                msg = ag.adjust_difficulty()
                if msg:
                    self.dda_msg = msg

    # ── 이벤트 ────────────────────────────────────────────────────────────
    def handle(self, event):
        pos = pygame.mouse.get_pos()
        if self.menu_btn.hit(pos, event):
            return "menu"

        if self.env.done:
            if self.again_btn.hit(pos, event):
                self.env.reset()
                self.log = []
                self.result_msg = ""
                self.dda_msg = ""
                self.anim = []
                self.waiting_human = False
                self._maybe_ai()
            return None

        if self.waiting_human and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for action, btn in self.action_btns:
                if btn.hit(pos):
                    pid   = self.env.current_pid
                    state = self.env.get_state(pid)
                    r, done, drew = self.env.step(pid, action)
                    name = self.env.players[pid].name
                    acts = {0:"이동", 1:"집카드", 2:"보급카드", 3:"카드뽑기"}
                    self._log(f"{name}: {acts[action]}")
                    if drew:
                        self._log(f"  └ 뽑은 카드: {drew.label()}")
                        # 카드 드로우 애니메이션
                        end_x = self.RIGHT_X + 10 + (len(self.env.players[pid].hand) - 1) * (CARD_W + 6)
                        end_y = WIN_H - 160
                        self.anim.append(DrawAnim(drew, (DECK_X + CARD_W//2, DECK_Y + CARD_H//2), (end_x, end_y)))
                    self.waiting_human = False
                    if done:
                        self._on_end()
                    else:
                        self._maybe_ai()
                    break
        return None

    # ── 오른쪽 패널 ───────────────────────────────────────────────────────
    def _draw_right_panel(self):
        s  = self.screen
        rx = self.RIGHT_X
        rounded_rect(s, PANEL_BG, pygame.Rect(rx - 8, 0, WIN_W - rx + 8, WIN_H), 0)

        # 현재 차례 헤더
        if not self.env.done:
            pid = self.env.current_pid
            col = PLAYER_COLORS[pid % len(PLAYER_COLORS)]
            rounded_rect(s, col, pygame.Rect(rx, 8, WIN_W - rx - 12, 38), 8)
            name = self.env.players[pid].name
            draw_text(s, f"턴 {self.env.turn + 1}  —  {name}의 차례", _fonts["normal"],
                      BG, rx + (WIN_W - rx - 12) // 2, 27, "center")

        # 덱 아이콘
        draw_deck_pile(s, DECK_X, DECK_Y)
        draw_text(s, "카드 덱 (무제한)", _fonts["tiny"], GRAY, DECK_X, DECK_Y + CARD_H + 5)

        # 플레이어 현황
        py = 58
        draw_text(s, "현황", _fonts["small"], GRAY, rx, py)
        py += 18
        for i, p in enumerate(self.env.players):
            col  = PLAYER_COLORS[i % len(PLAYER_COLORS)]
            h    = 52
            rounded_rect(s, PANEL_DARK, pygame.Rect(rx, py, WIN_W - rx - 10, h), 7)
            if i == self.env.current_pid and not self.env.done:
                pygame.draw.rect(s, col, pygame.Rect(rx, py, WIN_W - rx - 10, h), 2, border_radius=7)

            # 색 원
            pygame.draw.circle(s, col, (rx + 15, py + h // 2), 9)
            draw_text(s, f"P{i+1}", _fonts["tiny"], BG, rx + 15, py + h // 2, "center")

            # 이름 + 손패 수
            draw_text(s, p.name, _fonts["small"], WHITE, rx + 30, py + 6)
            draw_text(s, f"손패 {len(p.hand)}/{MAX_HAND}장", _fonts["tiny"], GRAY, rx + 30, py + 24)

            # 진행바
            bar_total = WIN_W - rx - 55
            bar_filled = int(bar_total * (1 - p.position / BOARD_SIZE))
            pygame.draw.rect(s, DIM, (rx + 30, py + 38, bar_total, 8), border_radius=4)
            pygame.draw.rect(s, col,  (rx + 30, py + 38, bar_filled, 8), border_radius=4)
            pct = (1 - p.position / BOARD_SIZE) * 100
            draw_text(s, f"{pct:.0f}%", _fonts["tiny"], col, rx + 32 + bar_total, py + 35)

            # 보급 카드 사용 여부
            sup_txt = "보급 사용" if p.supply_used else "보급 가능"
            draw_text(s, sup_txt, _fonts["tiny"], GRAY if p.supply_used else SUPPLY_C,
                      WIN_W - 78, py + 6)
            py += h + 4

        # DDA 메시지
        if self.dda_msg:
            ry2 = py + 4
            rounded_rect(s, (30, 55, 35), pygame.Rect(rx, ry2, WIN_W - rx - 10, 24), 5)
            draw_text(s, self.dda_msg, _fonts["tiny"], GREEN, rx + 6, ry2 + 4)
            py = ry2 + 28

        # 게임 로그
        draw_text(s, "로그", _fonts["small"], GRAY, rx, py + 4)
        py += 22
        for line in self.log[-(self.LOG_MAX - self.n * 3):]:
            col_txt = SUPPLY_C if "보급" in line else HOME_C if "집카드" in line else \
                      DRAW_C if "뽑" in line else WHITE
            draw_text(s, line, _fonts["tiny"], col_txt, rx, py)
            py += 17

    # ── 현재 플레이어 손패 ────────────────────────────────────────────────
    def _draw_hand(self):
        if self.env.done or not self.waiting_human:
            return
        pid = self.env.current_pid
        if pid not in self.human_ids:
            return
        me = self.env.players[pid]
        s  = self.screen
        hx = self.RIGHT_X + 5
        hy = WIN_H - 165

        draw_text(s, f"손패  ({len(me.hand)}/{MAX_HAND})", _fonts["small"], GRAY, hx, hy - 20)

        # 보급 카드 1회 사용 안내
        if me.supply_used:
            draw_text(s, "보급카드 이미 사용", _fonts["tiny"], GRAY, hx + 200, hy - 18)

        for i, card in enumerate(me.hand):
            cx2 = hx + i * (CARD_W + 6)
            draw_card_widget(s, card, cx2, hy)

        # 행동 버튼
        draw_text(s, "행동 선택:", _fonts["small"], GRAY, hx, WIN_H - 86)
        pos = pygame.mouse.get_pos()
        for _, btn in self.action_btns:
            btn.draw(s, btn.hit(pos))

    # ── 결과 오버레이 ─────────────────────────────────────────────────────
    def _draw_result(self):
        if not self.result_msg:
            return
        s  = self.screen
        ov = pygame.Surface((WIN_W, WIN_H))
        ov.fill(BG)
        ov.set_alpha(175)
        s.blit(ov, (0, 0))
        rounded_rect(s, PANEL_BG, pygame.Rect(WIN_W // 2 - 230, WIN_H // 2 - 90, 460, 210), 16)
        draw_text(s, self.result_msg, _fonts["large"], GOLD, WIN_W // 2, WIN_H // 2 - 45, "center")
        if self.dda_msg:
            draw_text(s, self.dda_msg, _fonts["small"], GREEN, WIN_W // 2, WIN_H // 2 + 5, "center")
        pos = pygame.mouse.get_pos()
        self.again_btn.draw(s, self.again_btn.hit(pos))

    # ── 전체 드로우 ───────────────────────────────────────────────────────
    def draw(self):
        s = self.screen
        s.fill(BG)

        # 과녁 보드
        IsoBoard.draw(s, self.env.players, self.env.current_pid, self.env.done)

        # 오른쪽 패널
        self._draw_right_panel()
        self._draw_hand()

        # 카드 애니메이션
        for anim in self.anim[:]:
            anim.update()
            anim.draw(s)
            if anim.done:
                self.anim.remove(anim)

        # 결과
        self._draw_result()

        # 메뉴 버튼
        pos = pygame.mouse.get_pos()
        self.menu_btn.draw(s, self.menu_btn.hit(pos))

        pygame.display.flip()


# ═══════════════════════════════════════════════════════════════════════════
# 로딩 화면
# ═══════════════════════════════════════════════════════════════════════════
def loading_screen(screen):
    screen.fill(BG)
    draw_text(screen, "AI 학습 중...", _fonts["title"], WHITE, WIN_W // 2, WIN_H // 2 - 50, "center")
    draw_text(screen, "처음 실행 시 약 1~2분 소요됩니다.", _fonts["sub"], GRAY, WIN_W // 2, WIN_H // 2 + 10, "center")
    pygame.display.flip()
    train(episodes=8000, save_path=MODEL_PATH, verbose_every=9999)


# ═══════════════════════════════════════════════════════════════════════════
# 메인
# ═══════════════════════════════════════════════════════════════════════════
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("턴제 전략 게임")

    def load_font(size):
        for name in ["malgungothic", "nanumgothic", "gulim", "malgun gothic",
                     "notosanskr", "freesansbold", "arial"]:
            try:
                f = pygame.font.SysFont(name, size)
                if f: return f
            except Exception:
                pass
        return pygame.font.Font(None, size)

    _fonts.update({
        "title":  load_font(40),
        "large":  load_font(30),
        "sub":    load_font(21),
        "normal": load_font(18),
        "small":  load_font(15),
        "tiny":   load_font(12),
    })

    clock = pygame.time.Clock()

    if not os.path.exists(MODEL_PATH):
        loading_screen(screen)

    setup  = SetupScreen(screen)
    state  = "setup"
    game: GameScreen | None = None

    while True:
        pos = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            if state == "setup":
                if setup.handle(event) == "start":
                    game  = GameScreen(screen, setup.n, list(setup.human_ids))
                    state = "game"
            elif state == "game" and game:
                if game.handle(event) == "menu":
                    IsoBoard._cached_bg = None
                    setup  = SetupScreen(screen)
                    state  = "setup"

        if state == "setup":
            setup.draw()
        elif state == "game" and game:
            game.draw()

        clock.tick(FPS)


if __name__ == "__main__":
    main()
