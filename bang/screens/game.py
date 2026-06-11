"""Main game screen."""
from __future__ import annotations
import math, pygame
from constants import (
    BG, PANEL_BG, PANEL_DARK, WHITE, GRAY, GOLD, RED, GREEN, DIM,
    BLUE, PURPLE, ACCENT, YELLOW, ORANGE, DARK_RED,
    ROLE_COLORS, CARD_W, CARD_H, BOARD_CX, BOARD_CY, PLAYER_RADIUS,
    WIN_W, WIN_H, AI_STEP_MS,
)
from cards import CardType, Suit
from roles import Role
from game_state import GameState, Phase, RespType
from ai_agent import BangAI
from ui_utils import draw_text, rounded_rect, Button, font


# Colour overrides
CARD_BROWN  = (100, 62, 20)
CARD_BLUE_C = (28, 55, 118)
HP_ON       = (210, 50, 42)
HP_OFF      = (55, 42, 30)


class CardAnim:
    """Slides a card from one position to another."""
    FRAMES = 30

    def __init__(self, label: str, start: tuple, end: tuple, color):
        self.label = label
        self.start = start
        self.end   = end
        self.color = color
        self.frame = 0

    def update(self):
        self.frame += 1

    @property
    def done(self):
        return self.frame >= self.FRAMES

    def draw(self, surf):
        t = self.frame / self.FRAMES
        t = t * t * (3 - 2 * t)
        x = int(self.start[0] + (self.end[0] - self.start[0]) * t)
        y = int(self.start[1] + (self.end[1] - self.start[1]) * t)
        r = pygame.Rect(x - 32, y - 22, 64, 44)
        rounded_rect(surf, self.color, r, 6)
        draw_text(surf, self.label, "tiny", WHITE, r.centerx, r.centery, "center")


class GameScreen:
    RIGHT_X = 860
    LOG_MAX  = 22
    CARD_SPACING = 90

    def __init__(self, screen: pygame.Surface, gs: GameState):
        self.screen = screen
        self.gs     = gs
        self.anims: list[CardAnim] = []

        # AI agents for non-human players
        self.ai: dict[int, BangAI] = {
            i: BangAI(i) for i in range(gs.num_players) if i not in gs.human_ids
        }
        self.ai_timer = 0

        # Selection state
        self.selected_card_idx: int = -1   # card in hand selected
        self.target_mode: bool = False     # waiting for target click
        self.target_candidates: list[int] = []

        # Precompute player positions (circular arrangement)
        self._player_positions = _compute_player_positions(gs.num_players)

        self.btn_menu   = Button((WIN_W - 118, 8, 108, 34), "← 메뉴", DIM, radius=7)
        self.btn_endturn = Button((self.RIGHT_X + 5, WIN_H - 55, 185, 44),
                                  "턴 종료", ACCENT, radius=9, fkey="normal")
        self.btn_takeit  = Button((self.RIGHT_X + 5, WIN_H - 55, 185, 44),
                                  "맞겠습니다", RED, radius=9, fkey="normal")

        # Barrel-check notice
        self._barrel_notice: str = ""
        self._barrel_timer: int  = 0

        # Handoff pending for local mode
        self._need_handoff: bool = False
        self._handoff_name: str  = ""

        # Resolve any automatic phases at game start
        self._auto_start()

    # ──────────────────────────────────────────────────────────────────────
    # Initialization helpers
    # ──────────────────────────────────────────────────────────────────────
    def _auto_start(self):
        self._check_handoff_needed()

    def _check_handoff_needed(self):
        gs = self.gs
        if gs.mode == "local" and gs.phase not in (Phase.GAME_OVER,):
            p = gs.current_player()
            if p.alive:
                self._need_handoff = True
                self._handoff_name = p.name

    # ──────────────────────────────────────────────────────────────────────
    # Handoff query (main.py checks this)
    # ──────────────────────────────────────────────────────────────────────
    def needs_handoff(self) -> bool:
        return self._need_handoff

    def consume_handoff(self) -> str:
        self._need_handoff = False
        name = self._handoff_name
        self._handoff_name = ""
        return name

    # ──────────────────────────────────────────────────────────────────────
    # Event handling
    # ──────────────────────────────────────────────────────────────────────
    def handle(self, event) -> str | None:
        pos = pygame.mouse.get_pos()

        if self.btn_menu.clicked(event, pos):
            return "menu"

        gs = self.gs
        if gs.phase == Phase.GAME_OVER:
            return None

        # Only handle human input
        active_pid = self._active_human_pid()
        if active_pid is None:
            return None

        if gs.phase == Phase.DRAW:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                gs.do_draw()
                self._on_phase_change()
            return None

        if gs.phase in (Phase.DYNAMITE, Phase.JAIL):
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._resolve_auto_phase()
            return None

        if gs.phase == Phase.PLAY:
            self._handle_play_input(event, pos, active_pid)

        elif gs.phase == Phase.RESPONSE:
            self._handle_response_input(event, pos, active_pid)

        elif gs.phase == Phase.DUEL:
            self._handle_duel_input(event, pos, active_pid)

        elif gs.phase == Phase.GEN_STORE:
            self._handle_gen_store_input(event, pos, active_pid)

        elif gs.phase == Phase.DISCARD:
            self._handle_discard_input(event, pos, active_pid)

        return None

    def _active_human_pid(self) -> int | None:
        gs = self.gs
        if gs.phase in (Phase.RESPONSE, Phase.DUEL):
            r = gs.resp_current if gs.phase == Phase.RESPONSE else gs.duel_current
            if r >= 0 and r in gs.human_ids:
                return r
        elif gs.phase == Phase.GEN_STORE:
            if gs.gen_store_order and gs.gen_store_order[0] in gs.human_ids:
                return gs.gen_store_order[0]
        elif gs.phase == Phase.DISCARD:
            if gs.current_pid in gs.human_ids:
                return gs.current_pid
        else:
            if gs.current_pid in gs.human_ids:
                return gs.current_pid
        return None

    def _handle_play_input(self, event, pos, pid):
        gs = self.gs
        p  = gs.players[pid]

        # End turn button
        if self.btn_endturn.clicked(event, pos):
            self._deselect()
            gs.enter_discard_phase()
            self._on_phase_change()
            return

        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return

        # Target selection mode
        if self.target_mode:
            clicked_pid = self._click_player(pos)
            if clicked_pid is not None and clicked_pid in self.target_candidates:
                self._execute_play_with_target(pid, self.selected_card_idx, clicked_pid)
            else:
                self._deselect()
            return

        # Click a card in hand
        card_idx = self._click_hand_card(pos, pid)
        if card_idx >= 0:
            if not gs.can_play_card(pid, card_idx):
                return
            card = p.hand[card_idx]
            if gs.cards_needing_target(card):
                targets = gs.valid_targets_for_card(pid, card)
                if not targets:
                    return
                self.selected_card_idx = card_idx
                self.target_mode = True
                self.target_candidates = targets
            else:
                gs.play_card(pid, card_idx)
                self._on_phase_change()

    def _execute_play_with_target(self, pid, card_idx, target_id):
        gs = self.gs
        p  = gs.players[pid]
        card = p.hand[card_idx]
        ct = card.card_type
        if ct in (CardType.CAT_BALOU, CardType.PANIC):
            # Pick random card from target automatically (AI behaviour)
            # For human: could show a submenu – simplified to first card
            gs.play_card(pid, card_idx, target_id=target_id, target_card_idx=0)
        else:
            gs.play_card(pid, card_idx, target_id=target_id)
        self._deselect()
        self._on_phase_change()

    def _handle_response_input(self, event, pos, pid):
        gs = self.gs
        if gs.resp_current != pid:
            return

        # Check barrel first (auto, no input needed but show notice)
        if not gs.barrel_checked and gs.players[pid].has_barrel():
            if event.type == pygame.MOUSEBUTTONDOWN:
                saved = gs.check_barrel()
                if saved:
                    self._on_phase_change()
                return

        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return

        # Take hit button
        if self.btn_takeit.clicked(event, pos):
            gs.respond_take_hit()
            self._on_phase_change()
            return

        # Click Missed! (or BANG! for Indians) from hand
        card_idx = self._click_hand_card(pos, pid)
        if card_idx >= 0:
            p = gs.players[pid]
            card = p.hand[card_idx]
            need = (CardType.BANG if gs.resp_type == RespType.INDIANS
                    else CardType.MISSED)
            if card.card_type == need:
                gs.respond_with_missed(card_idx)
                self._on_phase_change()

    def _handle_duel_input(self, event, pos, pid):
        gs = self.gs
        if gs.duel_current != pid:
            return
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        if self.btn_takeit.clicked(event, pos):
            gs.duel_take_hit()
            self._on_phase_change()
            return
        card_idx = self._click_hand_card(pos, pid)
        if card_idx >= 0:
            p = gs.players[pid]
            if p.hand[card_idx].card_type == CardType.BANG:
                gs.duel_play_bang(card_idx)
                self._on_phase_change()

    def _handle_gen_store_input(self, event, pos, pid):
        gs = self.gs
        if not gs.gen_store_order or gs.gen_store_order[0] != pid:
            return
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        card_idx = self._click_gen_store_card(pos)
        if card_idx >= 0:
            gs.gen_store_pick(pid, card_idx)
            self._on_phase_change()

    def _handle_discard_input(self, event, pos, pid):
        gs = self.gs
        if gs.current_pid != pid:
            return
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        card_idx = self._click_hand_card(pos, pid)
        if card_idx >= 0:
            gs.discard_card(card_idx)
            self._on_phase_change()

    # ──────────────────────────────────────────────────────────────────────
    # AI processing
    # ──────────────────────────────────────────────────────────────────────
    def update(self, dt_ms: int):
        # Update card anims
        for a in self.anims[:]:
            a.update()
            if a.done:
                self.anims.remove(a)

        gs = self.gs
        if gs.phase == Phase.GAME_OVER:
            return

        # Auto-resolve instant phases for the current player
        active = self._active_human_pid()
        if active is not None:
            return  # waiting for human

        # AI timer
        self.ai_timer -= dt_ms
        if self.ai_timer > 0:
            return
        self.ai_timer = AI_STEP_MS

        self._ai_step()

    def _ai_step(self):
        gs = self.gs
        if gs.phase == Phase.GAME_OVER:
            return

        if gs.phase in (Phase.DYNAMITE, Phase.JAIL):
            self._resolve_auto_phase()
            return

        if gs.phase == Phase.DRAW:
            gs.do_draw()
            self._on_phase_change()
            return

        if gs.phase == Phase.RESPONSE:
            pid = gs.resp_current
            if pid < 0 or pid not in self.ai:
                return
            ai = self.ai[pid]
            if not gs.barrel_checked and gs.players[pid].has_barrel():
                gs.check_barrel()
                return
            action = ai.choose_response(gs)
            if action[0] == "missed":
                gs.respond_with_missed(action[1])
            elif action[0] == "bang":
                gs.respond_with_missed(action[1])
            else:
                gs.respond_take_hit()
            self._on_phase_change()
            return

        if gs.phase == Phase.DUEL:
            pid = gs.duel_current
            if pid < 0 or pid not in self.ai:
                return
            ai = self.ai[pid]
            action = ai.choose_duel_response(gs)
            if action[0] == "bang":
                gs.duel_play_bang(action[1])
            else:
                gs.duel_take_hit()
            self._on_phase_change()
            return

        if gs.phase == Phase.GEN_STORE:
            pid = gs.gen_store_order[0] if gs.gen_store_order else -1
            if pid < 0 or pid not in self.ai:
                return
            ai = self.ai[pid]
            idx = ai.choose_gen_store(gs)
            gs.gen_store_pick(pid, idx)
            self._on_phase_change()
            return

        if gs.phase == Phase.DISCARD:
            pid = gs.current_pid
            if pid not in self.ai:
                return
            p = gs.players[pid]
            if len(p.hand) > p.hand_limit():
                # Discard weakest card
                worst = _worst_card_idx(p.hand)
                gs.discard_card(worst)
                self._on_phase_change()
            else:
                gs.enter_discard_phase()
                self._on_phase_change()
            return

        if gs.phase == Phase.PLAY:
            pid = gs.current_pid
            if pid not in self.ai:
                return
            ai = self.ai[pid]
            action = ai.choose_action(gs)
            if action is None or action[0] == "end_turn":
                gs.enter_discard_phase()
            elif len(action) == 2:
                gs.play_card(pid, action[1])
            elif len(action) == 3:
                gs.play_card(pid, action[1], target_id=action[2])
            elif len(action) == 4:
                gs.play_card(pid, action[1], target_id=action[2], target_card_idx=action[3])
            self._on_phase_change()

    def _resolve_auto_phase(self):
        gs = self.gs
        if gs.phase == Phase.DYNAMITE:
            info = gs.resolve_dynamite()
        elif gs.phase == Phase.JAIL:
            info = gs.resolve_jail()
        self._on_phase_change()

    def _on_phase_change(self):
        gs = self.gs
        self._deselect()
        if gs.phase == Phase.GAME_OVER:
            return
        # Local mode: after turn advances, show handoff if needed
        if gs.mode == "local":
            # Check if it's a human's active turn and phase is player-facing
            if gs.phase in (Phase.DRAW, Phase.DYNAMITE, Phase.JAIL):
                p = gs.players[gs.current_pid]
                if p.is_human:
                    self._need_handoff = True
                    self._handoff_name = p.name
            elif gs.phase == Phase.DISCARD:
                p = gs.players[gs.current_pid]
                if p.is_human and p.alive:
                    pass  # no handoff during discard of same player
            elif gs.phase == Phase.RESPONSE:
                r = gs.resp_current
                if r >= 0 and gs.players[r].is_human:
                    self._need_handoff = True
                    self._handoff_name = gs.players[r].name

    def _deselect(self):
        self.selected_card_idx = -1
        self.target_mode = False
        self.target_candidates = []

    # ──────────────────────────────────────────────────────────────────────
    # Hit-testing
    # ──────────────────────────────────────────────────────────────────────
    def _click_player(self, pos) -> int | None:
        for pid, (px, py) in self._player_positions.items():
            if math.hypot(pos[0] - px, pos[1] - py) < 50:
                return pid
        return None

    def _click_hand_card(self, pos, pid: int) -> int:
        p = self.gs.players[pid]
        hx, hy = self._hand_origin(pid)
        for i in range(len(p.hand)):
            r = pygame.Rect(hx + i * self.CARD_SPACING, hy, CARD_W, CARD_H)
            if r.collidepoint(pos):
                return i
        return -1

    def _click_gen_store_card(self, pos) -> int:
        pile = self.gs.gen_store_pile
        ox, oy = WIN_W // 2 - len(pile) * 48, WIN_H // 2 - 60
        for i in range(len(pile)):
            r = pygame.Rect(ox + i * 96, oy, CARD_W, CARD_H)
            if r.collidepoint(pos):
                return i
        return -1

    def _hand_origin(self, pid: int) -> tuple[int, int]:
        p = self.gs.players[pid]
        total = len(p.hand) * self.CARD_SPACING - (self.CARD_SPACING - CARD_W)
        hx = max(10, self.RIGHT_X // 2 - total // 2)
        hy = WIN_H - CARD_H - 60
        return hx, hy

    # ──────────────────────────────────────────────────────────────────────
    # Drawing
    # ──────────────────────────────────────────────────────────────────────
    def draw(self):
        s = self.screen
        s.fill(BG)

        self._draw_board()
        self._draw_players()
        self._draw_right_panel()
        self._draw_hand_area()
        self._draw_gen_store_overlay()
        self._draw_phase_banner()

        # Animations
        for a in self.anims:
            a.draw(s)

        # Game over overlay
        if self.gs.phase == Phase.GAME_OVER:
            self._draw_game_over()

        # Buttons
        pos = pygame.mouse.get_pos()
        self.btn_menu.draw(s, self.btn_menu.is_hovered(pos))
        pygame.display.flip()

    def _draw_board(self):
        s = self.screen
        # Table felt
        pygame.draw.ellipse(s, (18, 48, 22),
                            pygame.Rect(BOARD_CX - 280, BOARD_CY - 200, 560, 400))
        pygame.draw.ellipse(s, (28, 68, 32),
                            pygame.Rect(BOARD_CX - 275, BOARD_CY - 195, 550, 390), 2)

    def _draw_players(self):
        s   = self.screen
        gs  = self.gs
        pos = pygame.mouse.get_pos()

        for pid, (px, py) in self._player_positions.items():
            p = gs.players[pid]
            # Fade dead players
            alpha_mod = 1.0 if p.alive else 0.35

            is_active = (pid == gs.current_pid and gs.phase not in
                         (Phase.RESPONSE, Phase.DUEL, Phase.GEN_STORE))
            is_responder = (pid == gs.resp_current and
                            gs.phase in (Phase.RESPONSE, Phase.DUEL))
            is_target = pid in self.target_candidates

            col = ROLE_COLORS.get(p.role.value, GRAY) if p.role_revealed else GRAY
            radius = 42

            # Glow for active / target
            if is_active:
                for gr in [radius + 16, radius + 10, radius + 5]:
                    gc = tuple(int(c * 0.45) for c in GOLD)
                    pygame.draw.circle(s, gc, (px, py), gr)
            if is_responder:
                for gr in [radius + 16, radius + 10, radius + 5]:
                    gc = tuple(int(c * 0.45) for c in RED)
                    pygame.draw.circle(s, gc, (px, py), gr)
            if is_target:
                for gr in [radius + 18, radius + 11, radius + 5]:
                    pygame.draw.circle(s, (60, 140, 60), (px, py), gr)

            # Player circle
            base_col = tuple(int(c * alpha_mod) for c in col)
            pygame.draw.circle(s, (20, 14, 6), (px, py), radius)
            pygame.draw.circle(s, base_col, (px, py), radius, 3 if p.alive else 1)

            if not p.alive:
                draw_text(s, "✕", "large", (100, 50, 50), px, py, "center")
            else:
                draw_text(s, f"P{pid+1}", "small", WHITE, px, py - 10, "center")

            # Name
            draw_text(s, p.name, "tiny", col if p.alive else GRAY,
                      px, py + radius + 4, "center")

            # Role (if revealed)
            role_label = p.role.value if p.role_revealed else "?"
            draw_text(s, role_label, "tiny",
                      col if p.role_revealed else DIM,
                      px, py + radius + 18, "center")

            # HP bullets
            self._draw_hp(s, px, py - radius - 22, p)

            # Hand count badge
            if p.alive:
                badge_r = pygame.Rect(px + radius - 12, py - radius - 12, 26, 20)
                rounded_rect(s, PANEL_DARK, badge_r, 5)
                draw_text(s, str(len(p.hand)), "tiny", YELLOW,
                          badge_r.centerx, badge_r.centery, "center")

            # Equipment icons below name
            eq_x = px - len(p.equipment) * 14
            for ci, c in enumerate(p.equipment):
                eq_col = (80, 80, 180) if c.is_blue else ORANGE
                eq_r = pygame.Rect(eq_x + ci * 28, py + radius + 32, 26, 16)
                rounded_rect(s, eq_col, eq_r, 3)
                draw_text(s, c.name[:4], "tiny", WHITE,
                          eq_r.centerx, eq_r.centery, "center")

    def _draw_hp(self, s, cx, cy, player):
        total = player.max_hp
        bullet_r = 7
        total_w = total * (bullet_r * 2 + 3) - 3
        sx = cx - total_w // 2
        for i in range(total):
            col = HP_ON if i < player.hp else HP_OFF
            bx = sx + i * (bullet_r * 2 + 3) + bullet_r
            pygame.draw.circle(s, col, (bx, cy), bullet_r)
            if i < player.hp:
                pygame.draw.circle(s, (240, 90, 80), (bx, cy), bullet_r, 1)

    # ─── Right panel ───────────────────────────────────────────────────────
    def _draw_right_panel(self):
        s  = self.screen
        gs = self.gs
        rx = self.RIGHT_X
        pygame.draw.rect(s, PANEL_BG, pygame.Rect(rx - 6, 0, WIN_W - rx + 6, WIN_H))

        # Turn header
        if gs.phase not in (Phase.GAME_OVER,):
            pid = gs.current_pid
            col = ROLE_COLORS.get(gs.players[pid].role.value, ACCENT) if gs.players[pid].role_revealed else ACCENT
            rounded_rect(s, col, pygame.Rect(rx, 8, WIN_W - rx - 10, 36), 8)
            draw_text(s, f"Turn {gs.turn_num + 1}  —  {gs.players[pid].name}",
                      "normal", BG, rx + (WIN_W - rx - 10) // 2, 26, "center")

        # Status per player
        py2 = 54
        for pid, p in enumerate(gs.players):
            col  = ROLE_COLORS.get(p.role.value, GRAY) if p.role_revealed else GRAY
            h    = 56
            alpha = 1.0 if p.alive else 0.5
            bg_c = tuple(int(c * alpha) for c in (35, 22, 8))
            rounded_rect(s, bg_c, pygame.Rect(rx, py2, WIN_W - rx - 8, h), 6)
            if pid == gs.current_pid and p.alive:
                pygame.draw.rect(s, col, pygame.Rect(rx, py2, WIN_W - rx - 8, h), 2, border_radius=6)

            pygame.draw.circle(s, col if p.alive else DIM, (rx + 14, py2 + h // 2), 8)
            draw_text(s, p.name, "small", WHITE if p.alive else GRAY, rx + 26, py2 + 6)

            role_lbl = p.role.value if p.role_revealed else "?"
            draw_text(s, role_lbl, "tiny", col, rx + 26, py2 + 24)

            # HP bar
            bar_w = WIN_W - rx - 65
            filled = int(bar_w * (p.hp / p.max_hp)) if p.max_hp else 0
            pygame.draw.rect(s, DIM,   (rx + 26, py2 + 40, bar_w, 8), border_radius=4)
            pygame.draw.rect(s, HP_ON, (rx + 26, py2 + 40, filled, 8), border_radius=4)
            draw_text(s, f"{p.hp}/{p.max_hp}", "tiny", col,
                      rx + 28 + bar_w, py2 + 37)

            py2 += h + 3

        # Log
        py2 += 6
        draw_text(s, "게임 로그", "small", GRAY, rx + 2, py2)
        py2 += 20
        for line in self.gs.log[-(self.LOG_MAX - self.gs.num_players * 2):]:
            col_txt = (RED if "탈락" in line or "폭발" in line or "피격" in line
                       else GREEN if "회피" in line or "탈출" in line or "보너스" in line
                       else GOLD if "BANG" in line
                       else WHITE)
            draw_text(s, line[:42], "tiny", col_txt, rx + 2, py2)
            py2 += 15
            if py2 > WIN_H - 10:
                break

    # ─── Hand area ────────────────────────────────────────────────────────
    def _draw_hand_area(self):
        gs = self.gs
        if gs.phase == Phase.GAME_OVER:
            return

        # Determine which player's hand to show
        if gs.phase in (Phase.RESPONSE,):
            show_pid = gs.resp_current
        elif gs.phase == Phase.DUEL:
            show_pid = gs.duel_current
        elif gs.phase == Phase.GEN_STORE:
            show_pid = gs.gen_store_order[0] if gs.gen_store_order else gs.current_pid
        else:
            show_pid = gs.current_pid

        if show_pid < 0 or not gs.players[show_pid].alive:
            return

        p = gs.players[show_pid]
        s = self.screen
        hx, hy = self._hand_origin(show_pid)

        # Hand background bar
        hand_w = len(p.hand) * self.CARD_SPACING + (CARD_W - self.CARD_SPACING)
        rounded_rect(s, PANEL_DARK, pygame.Rect(hx - 8, hy - 28, max(hand_w + 16, 200), CARD_H + 60), 10)

        # Phase label
        phase_labels = {
            Phase.DRAW:     f"{p.name} 의 손패  — 클릭해서 드로우",
            Phase.PLAY:     f"{p.name} 의 손패  ({len(p.hand)}장)  |  HP {p.hp}/{p.max_hp}",
            Phase.RESPONSE: f"{p.name} — {'BANG!' if gs.resp_type == RespType.INDIANS else 'Missed!'} 로 반응하거나 맞기",
            Phase.DUEL:     f"{p.name} — 결투: BANG! 내거나 맞기",
            Phase.DISCARD:  f"{p.name} — 버릴 카드 선택  ({len(p.hand) - p.hand_limit()}장 더 버려야 함)",
            Phase.GEN_STORE:f"{p.name} — 잡화점: 카드 선택",
        }
        draw_text(s, phase_labels.get(gs.phase, ""), "small", GOLD, hx - 8, hy - 24)

        pos = pygame.mouse.get_pos()
        for i, card in enumerate(p.hand):
            cx2 = hx + i * self.CARD_SPACING
            is_selected = (i == self.selected_card_idx)
            is_playable = gs.can_play_card(show_pid, i) if gs.phase == Phase.PLAY else False
            is_valid_response = self._is_valid_response_card(show_pid, i)
            hover = pygame.Rect(cx2, hy, CARD_W, CARD_H).collidepoint(pos)
            lift = -14 if (is_selected or hover) else 0
            self._draw_card(s, card, cx2, hy + lift, is_selected,
                            is_playable or is_valid_response, gs.phase == Phase.DISCARD)

        # Action buttons
        if gs.phase == Phase.PLAY:
            self.btn_endturn.draw(s, self.btn_endturn.is_hovered(pos))
        if gs.phase in (Phase.RESPONSE, Phase.DUEL):
            self.btn_takeit.draw(s, self.btn_takeit.is_hovered(pos))

    def _is_valid_response_card(self, pid: int, card_idx: int) -> bool:
        gs = self.gs
        if gs.phase == Phase.RESPONSE:
            if pid != gs.resp_current:
                return False
            card = gs.players[pid].hand[card_idx]
            need = (CardType.BANG if gs.resp_type == RespType.INDIANS
                    else CardType.MISSED)
            return card.card_type == need
        if gs.phase == Phase.DUEL:
            if pid != gs.duel_current:
                return False
            return gs.players[pid].hand[card_idx].card_type == CardType.BANG
        return False

    def _draw_card(self, surf, card, x, y, selected, playable, discard_mode=False):
        col = CARD_BLUE_C if card.is_blue else CARD_BROWN
        r   = pygame.Rect(x, y, CARD_W, CARD_H)

        # Shadow
        pygame.draw.rect(surf, (8, 4, 2), r.move(3, 4), border_radius=8)
        rounded_rect(surf, col, r, 8)

        # Border
        border_col = GOLD if selected else (GREEN if playable else (150, 100, 40))
        if discard_mode:
            border_col = RED
        pygame.draw.rect(surf, border_col, r, 2, border_radius=8)

        # Suit + value in corners
        suit_col = RED if card.suit in (Suit.HEARTS, Suit.DIAMONDS) else WHITE
        draw_text(surf, card.suit.value, "tiny", suit_col, x + 4, y + 3)
        draw_text(surf, str(card.value), "tiny", suit_col, x + 4, y + 14)

        # Card name
        name = card.name
        if len(name) > 9:
            # Wrap
            mid = name.find(" ", len(name) // 2)
            if mid == -1:
                mid = len(name) // 2
            draw_text(surf, name[:mid], "tiny", WHITE, x + CARD_W // 2, y + 44, "center")
            draw_text(surf, name[mid:], "tiny", WHITE, x + CARD_W // 2, y + 58, "center")
        else:
            draw_text(surf, name, "small", WHITE, x + CARD_W // 2, y + 52, "center")

        # Type badge
        type_col = (50, 80, 160) if card.is_blue else (100, 55, 10)
        badge = pygame.Rect(x + 6, y + CARD_H - 22, CARD_W - 12, 16)
        rounded_rect(surf, type_col, badge, 4)
        label = "장착" if card.is_blue else "액션"
        draw_text(surf, label, "tiny", GRAY, badge.centerx, badge.centery, "center")

    # ─── Gen store overlay ────────────────────────────────────────────────
    def _draw_gen_store_overlay(self):
        gs = self.gs
        if gs.phase != Phase.GEN_STORE:
            return
        s = self.screen
        pile = gs.gen_store_pile
        if not pile:
            return

        who = gs.gen_store_order[0] if gs.gen_store_order else -1
        overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        s.blit(overlay, (0, 0))

        cx, cy = WIN_W // 2, WIN_H // 2
        panel_w = len(pile) * 96 + 40
        rounded_rect(s, PANEL_BG, pygame.Rect(cx - panel_w // 2, cy - 100, panel_w, 220), 14)
        pygame.draw.rect(s, GOLD, pygame.Rect(cx - panel_w // 2, cy - 100, panel_w, 220), 2, border_radius=14)

        name = gs.players[who].name if who >= 0 else ""
        draw_text(s, f"잡화점 — {name} 카드를 선택하세요", "normal", GOLD, cx, cy - 88, "center")

        ox = cx - len(pile) * 48
        pos = pygame.mouse.get_pos()
        for i, card in enumerate(pile):
            hover = pygame.Rect(ox + i * 96, cy - 60, CARD_W, CARD_H).collidepoint(pos)
            self._draw_card(s, card, ox + i * 96, cy - 60, False, hover)

    # ─── Phase banner ─────────────────────────────────────────────────────
    def _draw_phase_banner(self):
        gs  = self.gs
        s   = self.screen
        if gs.phase == Phase.GAME_OVER:
            return

        banners = {
            Phase.DYNAMITE:  ("💥 다이너마이트 체크!", RED),
            Phase.JAIL:      ("🔒 감옥 탈출 시도...", BLUE),
            Phase.DRAW:      ("📥 클릭해서 카드 2장 드로우", GOLD),
            Phase.RESPONSE:  ("⚡ 반응 카드를 내거나 맞으세요", RED),
            Phase.DUEL:      ("⚔️ 결투 진행 중 — BANG! 내거나 맞기", ORANGE),
            Phase.DISCARD:   ("🗑️ 버릴 카드를 선택하세요", ACCENT),
        }
        if gs.phase in banners:
            label, col = banners[gs.phase]
            draw_text(s, label, "small", col, BOARD_CX, 14, "center")

    # ─── Game over overlay ────────────────────────────────────────────────
    def _draw_game_over(self):
        s  = self.screen
        cx, cy = WIN_W // 2, WIN_H // 2
        overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 190))
        s.blit(overlay, (0, 0))

        rounded_rect(s, PANEL_BG, pygame.Rect(cx - 300, cy - 100, 600, 200), 18)
        pygame.draw.rect(s, GOLD, pygame.Rect(cx - 300, cy - 100, 600, 200), 2, border_radius=18)

        draw_text(s, "게임 종료!", "large", GOLD, cx, cy - 78, "center")
        draw_text(s, self.gs.winner_message(), "normal", WHITE, cx, cy - 28, "center")

        draw_text(s, "[메뉴 버튼]으로 돌아가세요", "small", GRAY, cx, cy + 42, "center")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _compute_player_positions(n: int) -> dict[int, tuple[int, int]]:
    """Arrange players in a circle; player 0 at bottom."""
    positions = {}
    for i in range(n):
        # 0 → bottom, others go clockwise
        angle = math.radians(90 + 360 * i / n)
        x = int(BOARD_CX + math.cos(angle) * PLAYER_RADIUS)
        y = int(BOARD_CY + math.sin(angle) * PLAYER_RADIUS)
        positions[i] = (x, y)
    return positions


def _worst_card_idx(hand) -> int:
    priority = {
        CardType.MISSED: 0,
        CardType.BEER:   1,
    }
    worst_score = 999
    worst_idx   = 0
    for i, c in enumerate(hand):
        score = priority.get(c.card_type, 5)
        if score < worst_score:
            worst_score = score
            worst_idx = i
    return worst_idx
