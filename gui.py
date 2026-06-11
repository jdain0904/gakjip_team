"""
턴제 전략 게임 GUI - Enhanced Edition
- 서서히 회전하는 아이소메트릭 보드 (모바일 모노폴리 스타일)
- 부드러운 플레이어 이동 / 글로우 / 드롭섀도우
- 손패·행동 버튼을 보드 하단으로 분리해 가독성 향상
- 이모지 없는 게임 스타일 텍스트
"""

import os, sys, math
import pygame

from game import GameEnv, BOARD_SIZE, MAX_HAND
from agent import DynamicDifficultyAgent
from train import train

# ── 색상 ──────────────────────────────────────────────────────────────────
BG           = ( 9,  11,  19)
PANEL_BG     = (17,  21,  35)
PANEL_DARK   = (12,  15,  27)
PANEL_BORDER = (38,  48,  78)
WHITE        = (218, 226, 244)
GRAY         = ( 98, 106, 130)
DIM          = ( 42,  48,  68)
ACCENT       = ( 70, 135, 255)
GREEN        = ( 55, 195,  95)
GOLD         = (252, 176,  18)
SUPPLY_C     = ( 78, 188, 255)
HOME_C       = (252, 142,  68)
DRAW_C       = (148,  98, 252)
MOVE_C       = ( 68, 172, 108)

PLAYER_COLORS = [
    ( 88, 165, 255),
    (255, 108,  58),
    ( 88, 212, 108),
    (198,  78, 198),
    (255, 208,  42),
    ( 68, 208, 188),
]

RING_COLORS = [
    ( 24,  31,  56),
    ( 29,  41,  70),
    ( 34,  51,  74),
    ( 39,  61,  78),
    ( 49,  74,  76),
    ( 59,  87,  66),
    ( 74, 103,  52),
    ( 98, 113,  38),
    (138, 123,  28),
    (178, 143,  18),
]

WIN_W, WIN_H  = 1200, 720
MODEL_PATH    = "model.pkl"
FPS           = 60

BOARD_CX      = 400
BOARD_CY      = 360
BOARD_RX      = 308
BOARD_RY      = 154
N_RINGS       = 10
SPOKE_N       = 12
ROT_SPEED     = 0.005   # rad/frame  약 20초 1회전

CARD_W, CARD_H = 88, 62
DECK_X, DECK_Y = 828, 26

_fonts: dict = {}

# ── 배경 그라디언트 캐시 ──────────────────────────────────────────────────
_bg_surf: pygame.Surface | None = None


def _build_bg():
    global _bg_surf
    if _bg_surf is not None:
        return
    s = pygame.Surface((WIN_W, WIN_H))
    for y in range(WIN_H):
        t = y / WIN_H
        pygame.draw.line(s, (int(7 + 5 * t), int(9 + 5 * t), int(17 + 9 * t)),
                         (0, y), (WIN_W, y))
    _bg_surf = s


# ── 유틸 ─────────────────────────────────────────────────────────────────
def lerp_color(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def draw_text(surf, text, font, color, x, y, anchor="topleft", shadow=False):
    if shadow:
        s_img = font.render(text, True, (0, 0, 0))
        surf.blit(s_img, s_img.get_rect(**{anchor: (x + 1, y + 2)}))
    img = font.render(text, True, color)
    r = img.get_rect(**{anchor: (x, y)})
    surf.blit(img, r)
    return r


def rounded_rect(surf, color, rect, r=10, border=0, bc=None):
    pygame.draw.rect(surf, color, rect, border_radius=r)
    if border:
        pygame.draw.rect(surf, bc or WHITE, rect, border, border_radius=r)


def iso_point(frac: float, angle_rad: float):
    x = BOARD_CX + math.cos(angle_rad) * frac * BOARD_RX
    y = BOARD_CY + math.sin(angle_rad) * frac * BOARD_RY
    return int(x), int(y)


# ── 아이소메트릭 보드 ─────────────────────────────────────────────────────
class IsoBoard:
    _cached_rings: pygame.Surface | None = None

    @classmethod
    def build_rings(cls):
        if cls._cached_rings is not None:
            return
        surf = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 0))
        for i in range(N_RINGS, 0, -1):
            frac = i / N_RINGS
            rx   = int(BOARD_RX * frac)
            ry   = int(BOARD_RY * frac)
            pygame.draw.ellipse(surf, RING_COLORS[i - 1],
                                (BOARD_CX - rx, BOARD_CY - ry, rx * 2, ry * 2))
        for i in range(1, N_RINGS + 1):
            frac = i / N_RINGS
            rx   = int(BOARD_RX * frac)
            ry   = int(BOARD_RY * frac)
            bc   = lerp_color((58, 70, 98), (188, 158, 42), (i - 1) / (N_RINGS - 1))
            pygame.draw.ellipse(surf, bc,
                                (BOARD_CX - rx, BOARD_CY - ry, rx * 2, ry * 2), 1)
        cls._cached_rings = surf

    @classmethod
    def draw(cls, surf, players, current_pid, done, rotation: float = 0.0):
        if cls._cached_rings is None:
            cls.build_rings()
        surf.blit(cls._cached_rings, (0, 0))

        # 회전하는 스포크
        for k in range(SPOKE_N):
            angle = math.pi * 2 * k / SPOKE_N + rotation
            ex, ey = iso_point(1.0, angle)
            pygame.draw.line(surf, (38, 44, 70), (BOARD_CX, BOARD_CY), (ex, ey), 1)

        # 거리 눈금 (고정 각도)
        font  = _fonts.get("tiny")
        l_ang = math.radians(-55)
        for i in range(1, N_RINGS + 1):
            dist   = i * (BOARD_SIZE // N_RINGS)
            frac   = i / N_RINGS
            lx, ly = iso_point(frac + 0.046, l_ang)
            if font:
                draw_text(surf, str(dist), font, GRAY, lx, ly, "center")

        # 중심 골 마커
        pygame.draw.circle(surf, GOLD, (BOARD_CX, BOARD_CY), 15)
        pygame.draw.circle(surf, (255, 228, 90), (BOARD_CX, BOARD_CY), 15, 2)
        pygame.draw.circle(surf, (20, 14, 4),    (BOARD_CX, BOARD_CY),  6)
        if _fonts.get("tiny"):
            draw_text(surf, "G", _fonts["tiny"], (20, 14, 4),
                      BOARD_CX, BOARD_CY, "center")

        # 플레이어 토큰 (뒤→앞 순서)
        n      = len(players)
        base_a = [math.radians(90 + 360 * i / n) for i in range(n)]
        angles = [a + rotation for a in base_a]
        order  = sorted(range(n), key=lambda i: players[i].position, reverse=True)

        for pid in order:
            p      = players[pid]
            frac   = max(0.0, min(1.0, p.position / BOARD_SIZE))
            tx, ty = iso_point(frac, angles[pid])
            col    = PLAYER_COLORS[pid % len(PLAYER_COLORS)]
            is_cur = (pid == current_pid and not done)
            R      = 21 if is_cur else 14

            sh = pygame.Surface((R * 4, R * 2), pygame.SRCALPHA)
            pygame.draw.ellipse(sh, (0, 0, 0, 68), sh.get_rect())
            surf.blit(sh, (tx - R * 2, ty + R - 1))

            if is_cur:
                for gr in (R + 14, R + 9, R + 4):
                    pygame.draw.circle(surf, lerp_color(col, BG, 0.68), (tx, ty), gr)

            pygame.draw.circle(surf, col, (tx, ty), R)
            pygame.draw.circle(surf, lerp_color(col, WHITE, 0.42),
                               (tx - R // 4, ty - R // 4), R // 3)
            pygame.draw.circle(surf, WHITE, (tx, ty), R, 2)

            f = _fonts.get("small" if is_cur else "tiny")
            if f:
                draw_text(surf, f"P{pid + 1}", f, (8, 8, 18), tx, ty, "center")
            if is_cur and _fonts.get("small"):
                draw_text(surf, p.name, _fonts["small"], col,
                          tx, ty - R - 17, "center", shadow=True)


# ── 버튼 ─────────────────────────────────────────────────────────────────
class Button:
    def __init__(self, rect, label, color=ACCENT, radius=9, font_key="small"):
        self.rect     = pygame.Rect(rect)
        self.label    = label
        self.color    = color
        self.radius   = radius
        self.font_key = font_key
        self.enabled  = True

    def draw(self, surf, hovered=False):
        c = DIM if not self.enabled else (
            lerp_color(self.color, WHITE, 0.22) if hovered else self.color)

        sh_s = pygame.Surface((self.rect.width, self.rect.height), pygame.SRCALPHA)
        pygame.draw.rect(sh_s, (0, 0, 0, 68), sh_s.get_rect(), border_radius=self.radius)
        surf.blit(sh_s, (self.rect.x + 2, self.rect.y + 3))

        rounded_rect(surf, c, self.rect, self.radius)

        hi_s = pygame.Surface((self.rect.width - 4, self.rect.height // 2 - 2),
                               pygame.SRCALPHA)
        hi_s.fill((255, 255, 255, 20))
        surf.blit(hi_s, (self.rect.x + 2, self.rect.y + 2))

        pygame.draw.rect(surf, PANEL_BORDER, self.rect, 1, border_radius=self.radius)

        f = _fonts.get(self.font_key) or _fonts.get("small")
        if f:
            draw_text(surf, self.label, f,
                      WHITE if self.enabled else GRAY,
                      self.rect.centerx, self.rect.centery, "center", shadow=True)

    def hit(self, pos, event=None):
        if event:
            return (self.enabled
                    and event.type == pygame.MOUSEBUTTONDOWN
                    and event.button == 1
                    and self.rect.collidepoint(pos))
        return self.rect.collidepoint(pos)


# ── 카드 드로우 애니메이션 ────────────────────────────────────────────────
class DrawAnim:
    DURATION = 46

    def __init__(self, card, start, end):
        self.card  = card
        self.start = start
        self.end   = end
        self.frame = 0
        self.done  = False

    def update(self):
        self.frame += 1
        if self.frame >= self.DURATION:
            self.done = True

    def draw(self, surf):
        t   = self.frame / self.DURATION
        t   = t * t * (3 - 2 * t)
        x   = int(self.start[0] + (self.end[0] - self.start[0]) * t)
        y   = int(self.start[1] + (self.end[1] - self.start[1]) * t)
        col = SUPPLY_C if self.card.card_type == "supply" else HOME_C
        r   = pygame.Rect(x - 40, y - 28, 80, 56)
        rounded_rect(surf, col, r, 8)
        rounded_rect(surf, col, r, 8, border=2, bc=WHITE)
        if _fonts.get("small"):
            lbl = "보급" if self.card.card_type == "supply" else "집"
            draw_text(surf, f"{lbl}  +{self.card.value}", _fonts["small"],
                      PANEL_DARK, r.centerx, r.centery, "center")


# ── 카드 위젯 ─────────────────────────────────────────────────────────────
def draw_card_widget(surf, card, x, y, small=False):
    cw  = CARD_W - 14 if small else CARD_W
    ch  = CARD_H - 8  if small else CARD_H
    col = SUPPLY_C if card.card_type == "supply" else HOME_C
    r   = pygame.Rect(x, y, cw, ch)
    rounded_rect(surf, PANEL_DARK, r, 8)
    rounded_rect(surf, col, pygame.Rect(x, y + ch - 19, cw, 19), 0)
    rounded_rect(surf, DIM, r, 8, border=1, bc=col)
    lbl = "보급" if card.card_type == "supply" else "집"
    f_l = _fonts.get("tiny")
    f_v = _fonts.get("normal" if not small else "small")
    if f_l:
        draw_text(surf, lbl, f_l, col, x + 5, y + 4)
    if f_v:
        draw_text(surf, f"+{card.value}", f_v, WHITE,
                  x + cw // 2, y + ch // 2 - 6, "center")


def draw_deck_pile(surf, x, y):
    for i in range(3, 0, -1):
        r = pygame.Rect(x + i * 3, y + i * 3, CARD_W, CARD_H)
        rounded_rect(surf, (34, 41, 64), r, 8)
        pygame.draw.rect(surf, PANEL_BORDER, r, 1, border_radius=8)
    fr = pygame.Rect(x, y, CARD_W, CARD_H)
    rounded_rect(surf, (38, 46, 76), fr, 8)
    pygame.draw.rect(surf, ACCENT, fr, 2, border_radius=8)
    for i in range(3):
        ss = pygame.Surface((18, CARD_H - 16), pygame.SRCALPHA)
        ss.fill((*ACCENT[:3], 22))
        surf.blit(ss, (x + 8 + i * 24, y + 8))
    if _fonts.get("small"):
        draw_text(surf, "DECK", _fonts["small"], ACCENT,
                  fr.centerx, fr.centery, "center")


_hand_panel_surf: pygame.Surface | None = None


def _get_hand_panel():
    global _hand_panel_surf
    if _hand_panel_surf is None:
        _hand_panel_surf = pygame.Surface((802, 195), pygame.SRCALPHA)
        _hand_panel_surf.fill((9, 11, 19, 175))
    return _hand_panel_surf


# ════════════════════════════════════════════════════════════════════════════
# 설정 화면
# ════════════════════════════════════════════════════════════════════════════
class SetupScreen:
    def __init__(self, screen):
        self.screen    = screen
        self.n         = 2
        self.human_ids = [0]
        self._t        = 0
        self._build()

    def _build(self):
        cx = WIN_W // 2
        self.minus = Button((cx - 98, 214, 44, 44), "  -  ", DIM)
        self.plus  = Button((cx + 54, 214, 44, 44), "  +  ", DIM)
        self.start = Button((cx - 124, 578, 248, 58),
                            "게임 시작", GREEN, radius=14, font_key="normal")
        self._rebuild_toggles()

    def _rebuild_toggles(self):
        self.toggles = []
        sx = WIN_W // 2 - self.n * 61
        for i in range(self.n):
            is_h = i in self.human_ids
            lbl  = f"P{i + 1}  {'사람' if is_h else 'AI'}"
            self.toggles.append(
                (i, Button((sx + i * 122, 332, 110, 52),
                           lbl, ACCENT if is_h else DIM, radius=9))
            )

    def handle(self, event):
        pos = pygame.mouse.get_pos()
        if self.minus.hit(pos, event) and self.n > 2:
            self.n -= 1
            self.human_ids = [h for h in self.human_ids if h < self.n]
            self._rebuild_toggles()
        if self.plus.hit(pos, event) and self.n < 6:
            self.n += 1
            self._rebuild_toggles()
        for idx, btn in self.toggles:
            if btn.hit(pos, event):
                if idx in self.human_ids:
                    self.human_ids.remove(idx)
                else:
                    self.human_ids.append(idx)
                self._rebuild_toggles()
        if self.start.hit(pos, event):
            return "start"
        return None

    def draw(self):
        self._t += 1
        s   = self.screen
        pos = pygame.mouse.get_pos()
        _build_bg()
        s.blit(_bg_surf, (0, 0))

        IsoBoard.build_rings()
        ghost = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        ghost.blit(IsoBoard._cached_rings, (0, 0))
        rot = self._t * ROT_SPEED
        for k in range(SPOKE_N):
            ang    = math.pi * 2 * k / SPOKE_N + rot
            ex, ey = iso_point(1.0, ang)
            pygame.draw.line(ghost, (38, 44, 70), (BOARD_CX, BOARD_CY), (ex, ey), 1)
        ghost.set_alpha(28)
        s.blit(ghost, (0, 0))

        cx = WIN_W // 2

        for off in (3, 2, 1):
            draw_text(s, "TURN  STRATEGY",
                      _fonts["title"], lerp_color(ACCENT, BG, 0.72),
                      cx + off, 82 + off, "center")
        draw_text(s, "TURN  STRATEGY", _fonts["title"], WHITE,
                  cx, 82, "center", shadow=True)
        draw_text(s, "강화학습 AI   x   동적 난이도   x   아이소메트릭 보드",
                  _fonts["sub"], GRAY, cx, 130, "center")

        cr = pygame.Rect(cx - 188, 188, 376, 96)
        rounded_rect(s, PANEL_BG, cr, 14)
        pygame.draw.rect(s, PANEL_BORDER, cr, 1, border_radius=14)
        draw_text(s, "플레이어 수", _fonts["small"], GRAY, cx, 196, "center")
        draw_text(s, str(self.n), _fonts["large"], GOLD, cx, 220, "center", shadow=True)
        self.minus.draw(s, self.minus.hit(pos))
        self.plus.draw(s, self.plus.hit(pos))

        draw_text(s, "플레이어 유형   (클릭으로 사람 / AI 전환)",
                  _fonts["small"], GRAY, cx, 308, "center")
        for _, btn in self.toggles:
            btn.draw(s, btn.hit(pos))

        ry  = 410
        rr  = pygame.Rect(cx - 326, ry, 652, 152)
        rounded_rect(s, PANEL_BG, rr, 14)
        pygame.draw.rect(s, PANEL_BORDER, rr, 1, border_radius=14)
        rules = [
            ("목표", f"중심까지 {BOARD_SIZE}칸을 먼저 줄이면 승리"),
            ("행동", "이동 (1칸)  /  집카드  /  보급카드 (1회)  /  카드 뽑기"),
            ("카드", f"집 · 보급 카드 : 0 ~ 60 랜덤 이동   손패 최대 {MAX_HAND}장"),
            ("AI",   "강화학습으로 훈련된 AI,  동적 난이도 자동 조절"),
        ]
        for i, (k, v) in enumerate(rules):
            draw_text(s, k, _fonts["small"], GOLD, cx - 314, ry + 16 + i * 30)
            draw_text(s, v, _fonts["small"], WHITE, cx - 268, ry + 16 + i * 30)

        self.start.draw(s, self.start.hit(pos))
        pygame.display.flip()


# ════════════════════════════════════════════════════════════════════════════
# 게임 화면
# ════════════════════════════════════════════════════════════════════════════
class GameScreen:
    LOG_MAX = 18
    RIGHT_X = 802

    def __init__(self, screen, num_players, human_ids):
        self.screen      = screen
        self.n           = num_players
        self.human_ids   = human_ids
        self.board_angle = 0.0

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

        self.log: list[str]           = []
        self.result_msg               = ""
        self.dda_msg                  = ""
        self.anim: list               = []
        self.waiting_human            = False
        self.action_btns: list[tuple] = []

        self.menu_btn  = Button((WIN_W - 128, 8, 118, 36), "< 메뉴", DIM, radius=8)
        self.again_btn = Button((WIN_W // 2 - 104, WIN_H // 2 + 78, 208, 54),
                                "다시 시작", GREEN, radius=12, font_key="normal")

        IsoBoard.build_rings()
        self._refresh_buttons()
        self._maybe_ai()

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
            0: ("이동  +1칸",                         MOVE_C),
            1: (f"집카드  +{bh.value if bh else 0}",  HOME_C),
            2: (f"보급카드  +{bs.value if bs else 0}", SUPPLY_C),
            3: ("카드 뽑기",                           DRAW_C),
        }
        self.action_btns = []
        bx = 10
        for a in valid:
            lbl, col = info[a]
            self.action_btns.append(
                (a, Button((bx, WIN_H - 64, 174, 52), lbl, col, radius=9))
            )
            bx += 182

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
            acts = {0: "이동", 1: "집카드", 2: "보급카드", 3: "카드뽑기"}
            self._log(f"{name} : {acts[action]}  ({wp:.0%})")
            if drew:
                kind = "보급" if drew.card_type == "supply" else "집"
                self._log(f"  └ {kind} +{drew.value}")
            if done:
                self._on_end()
                return
        self.waiting_human = False

    def _log(self, msg: str):
        self.log.append(msg)
        if len(self.log) > self.LOG_MAX:
            self.log.pop(0)

    def _on_end(self):
        w = self.env.players[self.env.winner]
        self.result_msg = f"{w.name}  승리"
        for pid, ag in enumerate(self.agents):
            if pid not in self.human_ids:
                ag.record_result(ai_won=(self.env.winner != pid))
                msg = ag.adjust_difficulty()
                if msg:
                    self.dda_msg = msg

    def handle(self, event):
        pos = pygame.mouse.get_pos()
        if self.menu_btn.hit(pos, event):
            return "menu"

        if self.env.done:
            if self.again_btn.hit(pos, event):
                self.env.reset()
                self.log        = []
                self.result_msg = ""
                self.dda_msg    = ""
                self.anim       = []
                self.waiting_human = False
                self._maybe_ai()
            return None

        if (self.waiting_human
                and event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1):
            for action, btn in self.action_btns:
                if btn.hit(pos):
                    pid   = self.env.current_pid
                    _, done, drew = self.env.step(pid, action)
                    acts  = {0: "이동", 1: "집카드", 2: "보급카드", 3: "카드뽑기"}
                    self._log(f"{self.env.players[pid].name} : {acts[action]}")
                    if drew:
                        kind = "보급" if drew.card_type == "supply" else "집"
                        self._log(f"  └ {kind} +{drew.value}")
                        ex = 10 + (len(self.env.players[pid].hand) - 1) * (CARD_W + 6)
                        ey = WIN_H - 160
                        self.anim.append(
                            DrawAnim(drew,
                                     (DECK_X + CARD_W // 2, DECK_Y + CARD_H // 2),
                                     (ex + CARD_W // 2, ey + CARD_H // 2))
                        )
                    self.waiting_human = False
                    if done:
                        self._on_end()
                    else:
                        self._maybe_ai()
                    break
        return None

    def _draw_right_panel(self):
        s  = self.screen
        rx = self.RIGHT_X

        panel_r = pygame.Rect(rx - 10, 0, WIN_W - rx + 10, WIN_H)
        rounded_rect(s, PANEL_BG, panel_r, 0)
        pygame.draw.line(s, PANEL_BORDER, (rx - 10, 0), (rx - 10, WIN_H), 2)

        if not self.env.done:
            pid = self.env.current_pid
            col = PLAYER_COLORS[pid % len(PLAYER_COLORS)]
            hr  = pygame.Rect(rx, 8, WIN_W - rx - 10, 40)
            rounded_rect(s, col, hr, 8)
            shi = pygame.Surface((hr.width, hr.height // 2), pygame.SRCALPHA)
            shi.fill((255, 255, 255, 24))
            s.blit(shi, hr.topleft)
            draw_text(s, f"TURN {self.env.turn + 1}   {self.env.players[pid].name}",
                      _fonts["normal"], PANEL_DARK,
                      hr.centerx, hr.centery, "center")

        draw_deck_pile(s, DECK_X, DECK_Y)
        draw_text(s, "카드 덱", _fonts["tiny"], GRAY,
                  DECK_X + CARD_W // 2, DECK_Y + CARD_H + 7, "center")

        py = 64
        draw_text(s, "현황", _fonts["small"], GRAY, rx + 4, py)
        py += 20
        for i, p in enumerate(self.env.players):
            col    = PLAYER_COLORS[i % len(PLAYER_COLORS)]
            h      = 54
            is_cur = (i == self.env.current_pid and not self.env.done)
            bg_c   = lerp_color(PANEL_DARK, col, 0.07) if is_cur else PANEL_DARK
            br     = pygame.Rect(rx, py, WIN_W - rx - 8, h)
            rounded_rect(s, bg_c, br, 8)
            if is_cur:
                pygame.draw.rect(s, col, br, 2, border_radius=8)

            pygame.draw.circle(s, col, (rx + 16, py + h // 2), 10)
            draw_text(s, f"P{i + 1}", _fonts["tiny"], PANEL_DARK,
                      rx + 16, py + h // 2, "center")
            draw_text(s, p.name, _fonts["small"], WHITE, rx + 32, py + 6)
            draw_text(s, f"손패  {len(p.hand)} / {MAX_HAND}",
                      _fonts["tiny"], GRAY, rx + 32, py + 26)

            bw     = WIN_W - rx - 56
            filled = int(bw * (1 - p.position / BOARD_SIZE))
            pygame.draw.rect(s, DIM, (rx + 32, py + 40, bw, 8), border_radius=4)
            if filled > 0:
                pygame.draw.rect(s, col, (rx + 32, py + 40, filled, 8), border_radius=4)
            draw_text(s, f"{(1 - p.position / BOARD_SIZE) * 100:.0f}%",
                      _fonts["tiny"], col, rx + 34 + bw, py + 37)

            sup = "보급 사용완료" if p.supply_used else "보급 가능"
            draw_text(s, sup, _fonts["tiny"],
                      GRAY if p.supply_used else SUPPLY_C, WIN_W - 88, py + 6)
            py += h + 5

        if self.dda_msg:
            dr = pygame.Rect(rx, py + 4, WIN_W - rx - 8, 26)
            rounded_rect(s, (20, 48, 28), dr, 6)
            pygame.draw.rect(s, (55, 195, 95), dr, 1, border_radius=6)
            draw_text(s, self.dda_msg, _fonts["tiny"], (55, 195, 95), rx + 8, py + 10)
            py = dr.bottom + 6

        draw_text(s, "로그", _fonts["small"], GRAY, rx + 4, py + 4)
        py += 22
        for line in self.log[-(self.LOG_MAX - self.n * 3):]:
            col_t = (SUPPLY_C if "보급" in line
                     else HOME_C if "집카드" in line
                     else DRAW_C if "뽑" in line
                     else WHITE)
            draw_text(s, line, _fonts["tiny"], col_t, rx + 4, py)
            py += 17

    def _draw_hand(self):
        if self.env.done or not self.waiting_human:
            return
        pid = self.env.current_pid
        if pid not in self.human_ids:
            return
        me = self.env.players[pid]
        s  = self.screen

        s.blit(_get_hand_panel(), (0, WIN_H - 195))

        hx = 10
        hy = WIN_H - 183

        draw_text(s, f"손패   {len(me.hand)} / {MAX_HAND}",
                  _fonts["small"], GRAY, hx, hy - 2)
        if me.supply_used:
            draw_text(s, "보급카드 이미 사용", _fonts["tiny"], GRAY, hx + 226, hy)

        for i, card in enumerate(me.hand):
            draw_card_widget(s, card, hx + i * (CARD_W + 6), hy + 16)

        draw_text(s, "행동 선택", _fonts["small"], GRAY, hx, WIN_H - 82)
        pos = pygame.mouse.get_pos()
        for _, btn in self.action_btns:
            btn.draw(s, btn.hit(pos))

    def _draw_result(self):
        if not self.result_msg:
            return
        s  = self.screen
        ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        ov.fill((7, 9, 17, 185))
        s.blit(ov, (0, 0))

        br = pygame.Rect(WIN_W // 2 - 244, WIN_H // 2 - 104, 488, 224)
        rounded_rect(s, PANEL_BG, br, 18)
        pygame.draw.rect(s, GOLD, br, 2, border_radius=18)
        draw_text(s, self.result_msg, _fonts["large"], GOLD,
                  WIN_W // 2, WIN_H // 2 - 44, "center", shadow=True)
        if self.dda_msg:
            draw_text(s, self.dda_msg, _fonts["normal"], (55, 195, 95),
                      WIN_W // 2, WIN_H // 2 + 14, "center")
        self.again_btn.draw(s, self.again_btn.hit(pygame.mouse.get_pos()))

    def draw(self):
        self.board_angle += ROT_SPEED
        s = self.screen
        _build_bg()
        s.blit(_bg_surf, (0, 0))

        IsoBoard.draw(s, self.env.players, self.env.current_pid,
                      self.env.done, self.board_angle)
        self._draw_right_panel()
        self._draw_hand()

        for anim in self.anim[:]:
            anim.update()
            anim.draw(s)
            if anim.done:
                self.anim.remove(anim)

        self._draw_result()
        self.menu_btn.draw(s, self.menu_btn.hit(pygame.mouse.get_pos()))
        pygame.display.flip()


# ── 로딩 화면 ─────────────────────────────────────────────────────────────
def loading_screen(screen):
    _build_bg()
    screen.blit(_bg_surf, (0, 0))
    cx, cy = WIN_W // 2, WIN_H // 2
    draw_text(screen, "AI 학습 중", _fonts["title"], WHITE,
              cx, cy - 58, "center", shadow=True)
    draw_text(screen, "처음 실행 시 약 1 ~ 2분 소요됩니다.",
              _fonts["sub"], GRAY, cx, cy + 18, "center")
    bar_r = pygame.Rect(cx - 188, cy + 60, 376, 14)
    rounded_rect(screen, DIM, bar_r, 7)
    pygame.draw.rect(screen, ACCENT, bar_r, 1, border_radius=7)
    pygame.display.flip()
    train(episodes=8000, save_path=MODEL_PATH, verbose_every=9999)


# ── 메인 ─────────────────────────────────────────────────────────────────
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Turn Strategy")

    def load_font(size):
        for name in ["malgungothic", "nanumgothic", "gulim", "malgun gothic",
                     "notosanskr", "freesansbold", "arial"]:
            try:
                f = pygame.font.SysFont(name, size)
                if f:
                    return f
            except Exception:
                pass
        return pygame.font.Font(None, size)

    _fonts.update({
        "title":  load_font(44),
        "large":  load_font(33),
        "sub":    load_font(22),
        "normal": load_font(19),
        "small":  load_font(16),
        "tiny":   load_font(13),
    })

    clock = pygame.time.Clock()

    if not os.path.exists(MODEL_PATH):
        loading_screen(screen)

    setup = SetupScreen(screen)
    state = "setup"
    game: GameScreen | None = None

    while True:
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
                    IsoBoard._cached_rings = None
                    setup  = SetupScreen(screen)
                    state  = "setup"

        if state == "setup":
            setup.draw()
        elif state == "game" and game:
            game.draw()

        clock.tick(FPS)


if __name__ == "__main__":
    main()
