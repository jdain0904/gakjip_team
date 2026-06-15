"""Main game screen — character-aware, full phase support."""
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
from characters import CHARACTERS, CharacterType
from game_state import GameState, Phase, RespType
from ai_agent import BangAI
from ui_utils import draw_text, rounded_rect, Button, font


CARD_BROWN  = (100, 62, 20)
CARD_BLUE_C = (28, 55, 118)
HP_ON       = (210, 50, 42)
HP_OFF      = (55, 42, 30)


class CardAnim:
    FRAMES = 28
    def __init__(self, label, start, end, color):
        self.label = label; self.start = start; self.end = end
        self.color = color; self.frame = 0
    def update(self): self.frame += 1
    @property
    def done(self): return self.frame >= self.FRAMES
    def draw(self, surf):
        t = self.frame / self.FRAMES
        t = t * t * (3 - 2 * t)
        x = int(self.start[0] + (self.end[0] - self.start[0]) * t)
        y = int(self.start[1] + (self.end[1] - self.start[1]) * t)
        r = pygame.Rect(x - 32, y - 22, 64, 44)
        rounded_rect(surf, self.color, r, 6)
        draw_text(surf, self.label, "tiny", WHITE, r.centerx, r.centery, "center")


class GameScreen:
    RIGHT_X      = 860
    LOG_MAX      = 22
    CARD_SPACING = 90

    def __init__(self, screen: pygame.Surface, gs: GameState):
        self.screen = screen
        self.gs     = gs
        self.anims: list[CardAnim] = []

        self.ai: dict[int, BangAI] = {
            i: BangAI(i) for i in range(gs.num_players) if i not in gs.human_ids
        }
        self.ai_timer = 0

        self.selected_card_idx: int = -1
        self.target_mode: bool = False
        self.target_candidates: list[int] = []
        self.kit_selected_local: list[int] = []   # which cards picked so far by human

        self._player_positions = _compute_positions(gs.num_players)

        self.btn_menu    = Button((WIN_W - 118, 8, 108, 34), "← 메뉴", DIM, radius=7)
        self.btn_endturn = Button((self.RIGHT_X + 5, WIN_H - 55, 185, 44),
                                  "턴 종료", ACCENT, radius=9, fkey="normal")
        self.btn_takeit  = Button((self.RIGHT_X + 5, WIN_H - 55, 185, 44),
                                  "맞겠습니다", RED, radius=9, fkey="normal")
        self.btn_beer    = Button((self.RIGHT_X + 5, WIN_H - 55, 185, 44),
                                  "🍺 맥주 사용", GREEN, radius=9, fkey="normal")
        self.btn_die     = Button((self.RIGHT_X + 200, WIN_H - 55, 140, 44),
                                  "탈락", (100, 40, 40), radius=9, fkey="normal")
        # Character-draw buttons
        self.btn_from_deck    = Button((WIN_W // 2 - 180, WIN_H // 2 + 60, 160, 44),
                                       "📥 덱에서", ACCENT, radius=9, fkey="normal")
        self.btn_from_discard = Button((WIN_W // 2 + 20, WIN_H // 2 + 60, 160, 44),
                                       "🗑 버림더미에서", (60, 100, 60), radius=9, fkey="normal")

        self._need_handoff = False
        self._handoff_name = ""
        self._auto_start()

    # ── Handoff ───────────────────────────────────────────────────────────
    def _auto_start(self):
        self._check_handoff_needed()

    def _check_handoff_needed(self):
        gs = self.gs
        if gs.mode == "local" and gs.phase not in (Phase.GAME_OVER,):
            p = gs.current_player()
            if p.alive:
                self._need_handoff = True
                self._handoff_name = p.name

    def needs_handoff(self) -> bool:
        return self._need_handoff

    def consume_handoff(self) -> str:
        self._need_handoff = False
        name = self._handoff_name
        self._handoff_name = ""
        return name

    # ═════════════════════════════════════════════════════════════════════
    # Event handling
    # ═════════════════════════════════════════════════════════════════════
    def handle(self, event) -> str | None:
        pos = pygame.mouse.get_pos()
        if self.btn_menu.clicked(event, pos):
            return "menu"

        gs = self.gs
        if gs.phase == Phase.GAME_OVER:
            return None

        active = self._active_human_pid()
        if active is None:
            return None

        if gs.phase == Phase.DRAW:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                gs.do_draw()
                self._on_phase_change()

        elif gs.phase in (Phase.DYNAMITE, Phase.JAIL):
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._resolve_auto_phase()

        elif gs.phase == Phase.PLAY:
            self._handle_play(event, pos, active)

        elif gs.phase == Phase.RESPONSE:
            self._handle_response(event, pos, active)

        elif gs.phase == Phase.DUEL:
            self._handle_duel(event, pos, active)

        elif gs.phase == Phase.GEN_STORE:
            self._handle_gen_store(event, pos, active)

        elif gs.phase == Phase.DISCARD:
            self._handle_discard(event, pos, active)

        elif gs.phase == Phase.BEER_SAVE:
            self._handle_beer_save(event, pos, active)

        elif gs.phase == Phase.CHAR_DRAW:
            self._handle_char_draw(event, pos, active)

        elif gs.phase == Phase.KIT_PEEK:
            self._handle_kit_peek(event, pos, active)

        return None

    def _active_human_pid(self) -> int | None:
        gs = self.gs
        if gs.phase in (Phase.RESPONSE,):
            r = gs.resp_current
            if r >= 0 and r in gs.human_ids:
                return r
        elif gs.phase == Phase.DUEL:
            r = gs.duel_current
            if r >= 0 and r in gs.human_ids:
                return r
        elif gs.phase == Phase.GEN_STORE:
            if gs.gen_store_order and gs.gen_store_order[0] in gs.human_ids:
                return gs.gen_store_order[0]
        elif gs.phase == Phase.BEER_SAVE:
            if gs.beer_save_pid in gs.human_ids:
                return gs.beer_save_pid
        elif gs.phase in (Phase.CHAR_DRAW, Phase.KIT_PEEK):
            pid = gs.char_draw_pid if gs.phase == Phase.CHAR_DRAW else gs.current_pid
            if pid in gs.human_ids:
                return pid
        elif gs.phase == Phase.DISCARD:
            if gs.current_pid in gs.human_ids:
                return gs.current_pid
        else:
            if gs.current_pid in gs.human_ids:
                return gs.current_pid
        return None

    # ── PLAY ──────────────────────────────────────────────────────────────
    def _handle_play(self, event, pos, pid):
        gs = self.gs
        if self.btn_endturn.clicked(event, pos):
            self._deselect()
            gs.enter_discard_phase()
            self._on_phase_change()
            return

        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return

        if self.target_mode:
            clicked = self._click_player(pos)
            if clicked is not None and clicked in self.target_candidates:
                self._exec_with_target(pid, self.selected_card_idx, clicked)
            else:
                self._deselect()
            return

        ci = self._click_hand_card(pos, pid)
        if ci >= 0:
            if not gs.can_play_card(pid, ci):
                return
            card = gs.players[pid].hand[ci]
            if gs.cards_needing_target(card):
                tgts = gs.valid_targets_for_card(pid, card)
                if not tgts:
                    return
                self.selected_card_idx = ci
                self.target_mode = True
                self.target_candidates = tgts
            else:
                gs.play_card(pid, ci)
                self._on_phase_change()

    def _exec_with_target(self, pid, card_idx, target_id):
        self.gs.play_card(pid, card_idx, target_id=target_id, target_card_idx=0)
        self._deselect()
        self._on_phase_change()

    # ── RESPONSE ──────────────────────────────────────────────────────────
    def _handle_response(self, event, pos, pid):
        gs = self.gs
        if gs.resp_current != pid:
            return
        if not gs.barrel_checked and gs.players[pid].has_barrel():
            if event.type == pygame.MOUSEBUTTONDOWN:
                saved = gs.check_barrel()
                if saved:
                    self._on_phase_change()
            return
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        if self.btn_takeit.clicked(event, pos):
            gs.respond_take_hit()
            self._on_phase_change()
            return
        ci = self._click_hand_card(pos, pid)
        if ci >= 0:
            card = gs.players[pid].hand[ci]
            p    = gs.players[pid]
            need_bang = gs.resp_type == RespType.INDIANS
            valid = (card.card_type in (CardType.BANG, CardType.MISSED)
                     and (card.card_type == (CardType.BANG if need_bang else CardType.MISSED)
                          or p.is_calamity_janet()))
            if valid:
                gs.respond_with_missed(ci)
                self._on_phase_change()

    # ── DUEL ──────────────────────────────────────────────────────────────
    def _handle_duel(self, event, pos, pid):
        gs = self.gs
        if gs.duel_current != pid:
            return
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        if self.btn_takeit.clicked(event, pos):
            gs.duel_take_hit()
            self._on_phase_change()
            return
        ci = self._click_hand_card(pos, pid)
        if ci >= 0:
            card = gs.players[pid].hand[ci]
            p    = gs.players[pid]
            valid = (card.card_type == CardType.BANG
                     or (p.is_calamity_janet() and card.card_type == CardType.MISSED))
            if valid:
                gs.duel_play_bang(ci)
                self._on_phase_change()

    # ── GEN STORE ─────────────────────────────────────────────────────────
    def _handle_gen_store(self, event, pos, pid):
        gs = self.gs
        if not gs.gen_store_order or gs.gen_store_order[0] != pid:
            return
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        ci = self._click_gen_store_card(pos)
        if ci >= 0:
            gs.gen_store_pick(pid, ci)
            self._on_phase_change()

    # ── DISCARD ───────────────────────────────────────────────────────────
    def _handle_discard(self, event, pos, pid):
        gs = self.gs
        if gs.current_pid != pid:
            return
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        ci = self._click_hand_card(pos, pid)
        if ci >= 0:
            gs.discard_card(ci)
            self._on_phase_change()

    # ── BEER SAVE ─────────────────────────────────────────────────────────
    def _handle_beer_save(self, event, pos, pid):
        gs = self.gs
        if gs.beer_save_pid != pid:
            return
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        if self.btn_beer.clicked(event, pos):
            gs.beer_save_use()
            self._on_phase_change()
            return
        if self.btn_die.clicked(event, pos):
            gs.beer_save_decline()
            self._on_phase_change()
            return
        # Also allow clicking a Beer card in hand
        ci = self._click_hand_card(pos, pid)
        if ci >= 0 and gs.players[pid].hand[ci].card_type == CardType.BEER:
            gs.beer_save_use()
            self._on_phase_change()

    # ── CHAR DRAW ─────────────────────────────────────────────────────────
    def _handle_char_draw(self, event, pos, pid):
        gs = self.gs
        if gs.char_draw_pid != pid:
            return
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return

        if self.btn_from_deck.clicked(event, pos):
            gs.char_draw_from_deck()
            self._on_phase_change()
            return

        if gs.char_draw_type == "pedro" and self.btn_from_discard.clicked(event, pos):
            gs.char_draw_from_discard()
            self._on_phase_change()
            return

        if gs.char_draw_type == "jesse":
            clicked = self._click_player(pos)
            if clicked is not None and clicked != pid and gs.players[clicked].hand:
                gs.char_draw_from_player(clicked)
                self._on_phase_change()

    # ── KIT PEEK ──────────────────────────────────────────────────────────
    def _handle_kit_peek(self, event, pos, pid):
        gs = self.gs
        if gs.current_pid != pid:
            return
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        ci = self._click_kit_peek_card(pos)
        if ci >= 0 and ci not in self.kit_selected_local:
            self.kit_selected_local.append(ci)
            gs.kit_carlson_pick(ci)
            if gs.phase != Phase.KIT_PEEK:
                self.kit_selected_local = []
                self._on_phase_change()

    # ═════════════════════════════════════════════════════════════════════
    # AI processing
    # ═════════════════════════════════════════════════════════════════════
    def update(self, dt_ms: int):
        for a in self.anims[:]:
            a.update()
            if a.done:
                self.anims.remove(a)

        gs = self.gs
        if gs.phase == Phase.GAME_OVER:
            return
        if self._active_human_pid() is not None:
            return

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

        if gs.phase in (Phase.CHAR_DRAW,):
            pid = gs.char_draw_pid
            if pid not in self.ai:
                return
            ai = self.ai[pid]
            if gs.char_draw_type == "jesse":
                target = ai.jesse_jones_target(gs)
                if target is not None:
                    gs.char_draw_from_player(target)
                else:
                    gs.char_draw_from_deck()
            else:  # pedro
                if ai.pedro_ramirez_from_discard(gs):
                    gs.char_draw_from_discard()
                else:
                    gs.char_draw_from_deck()
            self._on_phase_change()
            return

        if gs.phase == Phase.KIT_PEEK:
            pid = gs.current_pid
            if pid not in self.ai:
                return
            ai = self.ai[pid]
            picks = ai.kit_carlson_picks(gs)
            for p in picks:
                if not gs.kit_peek_cards:
                    break
                gs.kit_carlson_pick(p)
            self._on_phase_change()
            return

        if gs.phase == Phase.DRAW:
            gs.do_draw()
            self._on_phase_change()
            return

        if gs.phase == Phase.BEER_SAVE:
            pid = gs.beer_save_pid
            if pid not in self.ai:
                return
            if self.ai[pid].should_use_beer_save(gs):
                gs.beer_save_use()
            else:
                gs.beer_save_decline()
            self._on_phase_change()
            return

        if gs.phase == Phase.RESPONSE:
            pid = gs.resp_current
            if pid < 0 or pid not in self.ai:
                return
            if not gs.barrel_checked and gs.players[pid].has_barrel():
                gs.check_barrel()
                return
            action = self.ai[pid].choose_response(gs)
            if action[0] == "missed":
                gs.respond_with_missed(action[1])
            else:
                gs.respond_take_hit()
            self._on_phase_change()
            return

        if gs.phase == Phase.DUEL:
            pid = gs.duel_current
            if pid < 0 or pid not in self.ai:
                return
            action = self.ai[pid].choose_duel_response(gs)
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
            gs.gen_store_pick(pid, self.ai[pid].choose_gen_store(gs))
            self._on_phase_change()
            return

        if gs.phase == Phase.DISCARD:
            pid = gs.current_pid
            if pid not in self.ai:
                return
            p = gs.players[pid]
            if len(p.hand) > p.hand_limit():
                gs.discard_card(_worst_card_idx(p.hand))
            else:
                gs.enter_discard_phase()
            self._on_phase_change()
            return

        if gs.phase == Phase.PLAY:
            pid = gs.current_pid
            if pid not in self.ai:
                return
            ai  = self.ai[pid]
            action = ai.choose_action(gs)
            if action is None or action[0] == "end_turn":
                gs.enter_discard_phase()
            elif action[0] == "sid_ketchum":
                gs.use_sid_ketchum(pid, action[1], action[2])
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
            gs.resolve_dynamite()
        elif gs.phase == Phase.JAIL:
            gs.resolve_jail()
        self._on_phase_change()

    def _on_phase_change(self):
        gs = self.gs
        self._deselect()
        if gs.phase == Phase.GAME_OVER:
            return
        if gs.mode == "local":
            if gs.phase in (Phase.DRAW, Phase.DYNAMITE, Phase.JAIL,
                            Phase.CHAR_DRAW, Phase.KIT_PEEK):
                p = gs.players[gs.current_pid]
                if p.alive and p.is_human:
                    self._need_handoff = True
                    self._handoff_name = p.name
            elif gs.phase == Phase.RESPONSE:
                r = gs.resp_current
                if r >= 0 and gs.players[r].is_human:
                    self._need_handoff = True
                    self._handoff_name = gs.players[r].name
            elif gs.phase == Phase.BEER_SAVE:
                r = gs.beer_save_pid
                if r >= 0 and gs.players[r].is_human:
                    self._need_handoff = True
                    self._handoff_name = gs.players[r].name

    def _deselect(self):
        self.selected_card_idx = -1
        self.target_mode       = False
        self.target_candidates = []

    # ═════════════════════════════════════════════════════════════════════
    # Hit testing
    # ═════════════════════════════════════════════════════════════════════
    def _click_player(self, pos) -> int | None:
        for pid, (px, py) in self._player_positions.items():
            if math.hypot(pos[0] - px, pos[1] - py) < 50:
                return pid
        return None

    def _click_hand_card(self, pos, pid: int) -> int:
        p = self.gs.players[pid]
        hx, hy = self._hand_origin(pid)
        for i in range(len(p.hand)):
            if pygame.Rect(hx + i * self.CARD_SPACING, hy, CARD_W, CARD_H).collidepoint(pos):
                return i
        return -1

    def _click_gen_store_card(self, pos) -> int:
        pile = self.gs.gen_store_pile
        ox   = WIN_W // 2 - len(pile) * 48
        oy   = WIN_H // 2 - 60
        for i in range(len(pile)):
            if pygame.Rect(ox + i * 96, oy, CARD_W, CARD_H).collidepoint(pos):
                return i
        return -1

    def _click_kit_peek_card(self, pos) -> int:
        pile = self.gs.kit_peek_cards
        ox   = WIN_W // 2 - len(pile) * 50
        oy   = WIN_H // 2 - 60
        for i in range(len(pile)):
            if pygame.Rect(ox + i * 100, oy, CARD_W, CARD_H).collidepoint(pos):
                return i
        return -1

    def _hand_origin(self, pid: int) -> tuple[int, int]:
        p     = self.gs.players[pid]
        total = len(p.hand) * self.CARD_SPACING - (self.CARD_SPACING - CARD_W)
        hx    = max(10, self.RIGHT_X // 2 - total // 2)
        return hx, WIN_H - CARD_H - 60

    # ═════════════════════════════════════════════════════════════════════
    # Drawing
    # ═════════════════════════════════════════════════════════════════════
    def draw(self):
        s = self.screen
        s.fill(BG)
        self._draw_board()
        self._draw_players()
        self._draw_right_panel()
        self._draw_hand_area()
        self._draw_gen_store_overlay()
        self._draw_kit_peek_overlay()
        self._draw_char_draw_overlay()
        self._draw_phase_banner()
        for a in self.anims:
            a.draw(s)
        if self.gs.phase == Phase.GAME_OVER:
            self._draw_game_over()
        pos = pygame.mouse.get_pos()
        self.btn_menu.draw(s, self.btn_menu.is_hovered(pos))
        pygame.display.flip()

    def _draw_board(self):
        s = self.screen
        pygame.draw.ellipse(s, (18, 48, 22),
                            pygame.Rect(BOARD_CX - 280, BOARD_CY - 200, 560, 400))
        pygame.draw.ellipse(s, (28, 68, 32),
                            pygame.Rect(BOARD_CX - 275, BOARD_CY - 195, 550, 390), 2)

    def _draw_players(self):
        s   = self.screen
        gs  = self.gs
        pos = pygame.mouse.get_pos()

        for pid, (px, py) in self._player_positions.items():
            p   = gs.players[pid]
            col = ROLE_COLORS.get(p.role.value, GRAY) if p.role_revealed else GRAY
            dim = 1.0 if p.alive else 0.35

            is_active    = (pid == gs.current_pid and gs.phase not in
                            (Phase.RESPONSE, Phase.DUEL, Phase.GEN_STORE))
            is_responder = (pid == gs.resp_current and gs.phase in (Phase.RESPONSE, Phase.DUEL))
            is_beer_save = pid == gs.beer_save_pid
            is_target    = pid in self.target_candidates

            R = 42
            # Glows
            if is_active:
                for gr in (R+16, R+10, R+5):
                    pygame.draw.circle(s, tuple(int(c * .45) for c in GOLD), (px, py), gr)
            if is_responder or is_beer_save:
                for gr in (R+16, R+10, R+5):
                    pygame.draw.circle(s, tuple(int(c * .45) for c in RED), (px, py), gr)
            if is_target:
                for gr in (R+18, R+11, R+5):
                    pygame.draw.circle(s, (60, 140, 60), (px, py), gr)

            base = tuple(int(c * dim) for c in col)
            pygame.draw.circle(s, (20, 14, 6), (px, py), R)
            pygame.draw.circle(s, base, (px, py), R, 3 if p.alive else 1)

            if not p.alive:
                draw_text(s, "✕", "large", (100, 50, 50), px, py, "center")
            else:
                draw_text(s, f"P{pid+1}", "small", WHITE, px, py - 8, "center")

            draw_text(s, p.name, "tiny", col if p.alive else GRAY, px, py + R + 4, "center")
            role_lbl = p.role.value if p.role_revealed else "?"
            draw_text(s, role_lbl, "tiny", col if p.role_revealed else DIM,
                      px, py + R + 18, "center")

            # Character name
            if p.character:
                info = CHARACTERS[p.character]
                draw_text(s, info.name_ko, "tiny", (160, 140, 80),
                          px, py + R + 32, "center")

            self._draw_hp(s, px, py - R - 22, p)

            # Hand count badge
            if p.alive:
                badge = pygame.Rect(px + R - 12, py - R - 12, 26, 20)
                rounded_rect(s, PANEL_DARK, badge, 5)
                draw_text(s, str(len(p.hand)), "tiny", YELLOW,
                          badge.centerx, badge.centery, "center")

            # Equipment icons
            eq_x = px - len(p.equipment) * 14
            for ci2, c in enumerate(p.equipment):
                eq_col = (80, 80, 180) if c.is_blue else ORANGE
                eq_r   = pygame.Rect(eq_x + ci2 * 28, py + R + 48, 26, 16)
                rounded_rect(s, eq_col, eq_r, 3)
                draw_text(s, c.name[:4], "tiny", WHITE,
                          eq_r.centerx, eq_r.centery, "center")

    def _draw_hp(self, s, cx, cy, player):
        r  = 7
        tw = player.max_hp * (r * 2 + 3) - 3
        sx = cx - tw // 2
        for i in range(player.max_hp):
            col = HP_ON if i < player.hp else HP_OFF
            bx  = sx + i * (r * 2 + 3) + r
            pygame.draw.circle(s, col, (bx, cy), r)
            if i < player.hp:
                pygame.draw.circle(s, (240, 90, 80), (bx, cy), r, 1)

    # ── Right panel ───────────────────────────────────────────────────────
    def _draw_right_panel(self):
        s  = self.screen
        gs = self.gs
        rx = self.RIGHT_X
        pygame.draw.rect(s, PANEL_BG, pygame.Rect(rx - 6, 0, WIN_W - rx + 6, WIN_H))

        if gs.phase not in (Phase.GAME_OVER,):
            pid = gs.current_pid
            col = ROLE_COLORS.get(gs.players[pid].role.value, ACCENT) \
                if gs.players[pid].role_revealed else ACCENT
            rounded_rect(s, col, pygame.Rect(rx, 8, WIN_W - rx - 10, 36), 8)
            draw_text(s, f"Turn {gs.turn_num + 1}  —  {gs.players[pid].name}",
                      "normal", BG, rx + (WIN_W - rx - 10) // 2, 26, "center")

        py2 = 54
        for pid, p in enumerate(gs.players):
            col   = ROLE_COLORS.get(p.role.value, GRAY) if p.role_revealed else GRAY
            h     = 58
            bg_c  = (35, 22, 8) if p.alive else (20, 14, 6)
            rounded_rect(s, bg_c, pygame.Rect(rx, py2, WIN_W - rx - 8, h), 6)
            if pid == gs.current_pid and p.alive:
                pygame.draw.rect(s, col, pygame.Rect(rx, py2, WIN_W - rx - 8, h), 2, border_radius=6)

            pygame.draw.circle(s, col if p.alive else DIM, (rx + 14, py2 + h // 2), 8)
            draw_text(s, p.name, "small", WHITE if p.alive else GRAY, rx + 26, py2 + 4)

            role_lbl = p.role.value if p.role_revealed else "?"
            char_lbl = CHARACTERS[p.character].name_ko if p.character else ""
            draw_text(s, f"{role_lbl}  {char_lbl}", "tiny", col, rx + 26, py2 + 22)

            bar_w    = WIN_W - rx - 65
            filled   = int(bar_w * (p.hp / p.max_hp)) if p.max_hp else 0
            pygame.draw.rect(s, DIM,   (rx + 26, py2 + 40, bar_w, 8), border_radius=4)
            pygame.draw.rect(s, HP_ON, (rx + 26, py2 + 40, filled, 8), border_radius=4)
            draw_text(s, f"{p.hp}/{p.max_hp}", "tiny", col,
                      rx + 28 + bar_w, py2 + 37)
            py2 += h + 3

        py2 += 6
        draw_text(s, "게임 로그", "small", GRAY, rx + 2, py2)
        py2 += 20
        for line in gs.log[-(self.LOG_MAX - gs.num_players * 2):]:
            col_txt = (RED   if any(k in line for k in ("탈락", "폭발", "피격", "패배"))
                       else GREEN if any(k in line for k in ("회피", "탈출", "보너스", "생존", "획득"))
                       else GOLD  if "BANG" in line
                       else (160, 130, 60) if "캐릭터" in line or "능력" in line or "카시디" in line or "그링고" in line or "라파예트" in line or "샘" in line
                       else WHITE)
            draw_text(s, line[:42], "tiny", col_txt, rx + 2, py2)
            py2 += 15
            if py2 > WIN_H - 10:
                break

    # ── Hand area ─────────────────────────────────────────────────────────
    def _draw_hand_area(self):
        gs = self.gs
        if gs.phase in (Phase.GAME_OVER, Phase.KIT_PEEK, Phase.CHAR_DRAW,
                        Phase.GEN_STORE):
            return

        if gs.phase in (Phase.RESPONSE,):
            show_pid = gs.resp_current
        elif gs.phase == Phase.DUEL:
            show_pid = gs.duel_current
        elif gs.phase == Phase.BEER_SAVE:
            show_pid = gs.beer_save_pid
        else:
            show_pid = gs.current_pid

        if show_pid < 0 or not gs.players[show_pid].alive:
            return

        p  = gs.players[show_pid]
        s  = self.screen
        hx, hy = self._hand_origin(show_pid)
        hand_w  = len(p.hand) * self.CARD_SPACING + (CARD_W - self.CARD_SPACING)
        rounded_rect(s, PANEL_DARK,
                     pygame.Rect(hx - 8, hy - 30, max(hand_w + 16, 200), CARD_H + 64), 10)

        char_lbl = f" [{CHARACTERS[p.character].name_ko}]" if p.character else ""
        labels = {
            Phase.DRAW:      f"{p.name}{char_lbl} — 클릭하여 드로우",
            Phase.PLAY:      f"{p.name}{char_lbl} — 손패 ({len(p.hand)}장)  HP {p.hp}/{p.max_hp}",
            Phase.RESPONSE:  f"{p.name} — {'BANG!' if gs.resp_type == RespType.INDIANS else 'Missed!'} 로 반응 또는 맞기",
            Phase.DUEL:      f"{p.name} — 결투: BANG! 내거나 맞기",
            Phase.DISCARD:   f"{p.name} — 버릴 카드 선택 ({len(p.hand) - p.hand_limit()}장 더)",
            Phase.BEER_SAVE: f"🍺 {p.name} — 맥주로 살아남겠습니까?",
        }
        draw_text(s, labels.get(gs.phase, ""), "small", GOLD, hx - 8, hy - 26)

        pos = pygame.mouse.get_pos()
        for i, card in enumerate(p.hand):
            is_sel  = (i == self.selected_card_idx)
            playable = gs.can_play_card(show_pid, i) if gs.phase == Phase.PLAY else False
            is_resp  = self._is_valid_resp_card(show_pid, i)
            is_beer  = (gs.phase == Phase.BEER_SAVE and card.card_type == CardType.BEER)
            hover    = pygame.Rect(hx + i * self.CARD_SPACING, hy, CARD_W, CARD_H).collidepoint(pos)
            lift     = -14 if (is_sel or hover) else 0
            self._draw_card(s, card, hx + i * self.CARD_SPACING, hy + lift,
                            is_sel, playable or is_resp or is_beer,
                            gs.phase == Phase.DISCARD)

        if gs.phase == Phase.PLAY:
            self.btn_endturn.draw(s, self.btn_endturn.is_hovered(pos))
        if gs.phase in (Phase.RESPONSE, Phase.DUEL):
            self.btn_takeit.draw(s, self.btn_takeit.is_hovered(pos))
        if gs.phase == Phase.BEER_SAVE:
            self.btn_beer.draw(s, self.btn_beer.is_hovered(pos))
            self.btn_die.draw(s, self.btn_die.is_hovered(pos))

    def _is_valid_resp_card(self, pid: int, card_idx: int) -> bool:
        gs = self.gs
        if gs.phase == Phase.RESPONSE and pid == gs.resp_current:
            card  = gs.players[pid].hand[card_idx]
            janet = gs.players[pid].is_calamity_janet()
            if gs.resp_type == RespType.INDIANS:
                return card.card_type == CardType.BANG or (janet and card.card_type == CardType.MISSED)
            return card.card_type == CardType.MISSED or (janet and card.card_type == CardType.BANG)
        if gs.phase == Phase.DUEL and pid == gs.duel_current:
            card  = gs.players[pid].hand[card_idx]
            janet = gs.players[pid].is_calamity_janet()
            return card.card_type == CardType.BANG or (janet and card.card_type == CardType.MISSED)
        return False

    def _draw_card(self, surf, card, x, y, selected, playable, discard_mode=False):
        col = CARD_BLUE_C if card.is_blue else CARD_BROWN
        r   = pygame.Rect(x, y, CARD_W, CARD_H)
        pygame.draw.rect(surf, (8, 4, 2), r.move(3, 4), border_radius=8)
        rounded_rect(surf, col, r, 8)
        bc = GOLD if selected else (GREEN if playable else (RED if discard_mode else (150, 100, 40)))
        pygame.draw.rect(surf, bc, r, 2, border_radius=8)
        suit_col = RED if card.suit in (Suit.HEARTS, Suit.DIAMONDS) else WHITE
        draw_text(surf, card.suit.value, "tiny", suit_col, x + 4, y + 3)
        draw_text(surf, str(card.value), "tiny", suit_col, x + 4, y + 14)
        name = card.name
        if len(name) > 9:
            mid = name.find(" ", len(name) // 2)
            if mid == -1:
                mid = len(name) // 2
            draw_text(surf, name[:mid], "tiny", WHITE, x + CARD_W // 2, y + 44, "center")
            draw_text(surf, name[mid:], "tiny", WHITE, x + CARD_W // 2, y + 58, "center")
        else:
            draw_text(surf, name, "small", WHITE, x + CARD_W // 2, y + 52, "center")
        type_col = (50, 80, 160) if card.is_blue else (100, 55, 10)
        badge    = pygame.Rect(x + 6, y + CARD_H - 22, CARD_W - 12, 16)
        rounded_rect(surf, type_col, badge, 4)
        draw_text(surf, "장착" if card.is_blue else "액션",
                  "tiny", GRAY, badge.centerx, badge.centery, "center")

    # ── Gen store overlay ─────────────────────────────────────────────────
    def _draw_gen_store_overlay(self):
        gs = self.gs
        if gs.phase != Phase.GEN_STORE:
            return
        s    = self.screen
        pile = gs.gen_store_pile
        if not pile:
            return
        who    = gs.gen_store_order[0] if gs.gen_store_order else -1
        cx, cy = WIN_W // 2, WIN_H // 2
        ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 140))
        s.blit(ov, (0, 0))
        pw = len(pile) * 96 + 40
        rounded_rect(s, PANEL_BG, pygame.Rect(cx - pw // 2, cy - 100, pw, 220), 14)
        pygame.draw.rect(s, GOLD, pygame.Rect(cx - pw // 2, cy - 100, pw, 220), 2, border_radius=14)
        name = gs.players[who].name if who >= 0 else ""
        draw_text(s, f"잡화점 — {name} 선택", "normal", GOLD, cx, cy - 88, "center")
        ox  = cx - len(pile) * 48
        pos = pygame.mouse.get_pos()
        for i, card in enumerate(pile):
            hover = pygame.Rect(ox + i * 96, cy - 60, CARD_W, CARD_H).collidepoint(pos)
            self._draw_card(s, card, ox + i * 96, cy - 60, False, hover)

    # ── Kit Carlson peek overlay ───────────────────────────────────────────
    def _draw_kit_peek_overlay(self):
        gs = self.gs
        if gs.phase != Phase.KIT_PEEK:
            return
        s    = self.screen
        pile = gs.kit_peek_cards
        cx, cy = WIN_W // 2, WIN_H // 2
        ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 150))
        s.blit(ov, (0, 0))
        pw = len(pile) * 100 + 40
        rounded_rect(s, PANEL_BG, pygame.Rect(cx - pw // 2, cy - 110, pw, 240), 14)
        pygame.draw.rect(s, GOLD, pygame.Rect(cx - pw // 2, cy - 110, pw, 240), 2, border_radius=14)
        remaining = 2 - len(self.kit_selected_local)
        draw_text(s, f"킷 칼슨: 2장 선택  (남은 선택: {remaining})",
                  "normal", GOLD, cx, cy - 96, "center")
        ox  = cx - len(pile) * 50
        pos = pygame.mouse.get_pos()
        for i, card in enumerate(pile):
            already = i in self.kit_selected_local
            hover   = pygame.Rect(ox + i * 100, cy - 65, CARD_W, CARD_H).collidepoint(pos)
            self._draw_card(s, card, ox + i * 100, cy - 65,
                            selected=already, playable=hover and not already)

    # ── Character draw overlay ────────────────────────────────────────────
    def _draw_char_draw_overlay(self):
        gs = self.gs
        if gs.phase != Phase.CHAR_DRAW:
            return
        s     = self.screen
        cx, cy = WIN_W // 2, WIN_H // 2
        ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 130))
        s.blit(ov, (0, 0))
        rounded_rect(s, PANEL_BG, pygame.Rect(cx - 260, cy - 100, 520, 220), 14)
        pygame.draw.rect(s, GOLD, pygame.Rect(cx - 260, cy - 100, 520, 220), 2, border_radius=14)

        pid  = gs.char_draw_pid
        p    = gs.players[pid]
        char = CHARACTERS.get(p.character)
        name = char.name_ko if char else ""

        if gs.char_draw_type == "jesse":
            draw_text(s, f"제시 존스 — 1번째 카드 출처 선택", "normal", GOLD, cx, cy - 82, "center")
            draw_text(s, "또는 플레이어를 클릭해 그 손패에서 가져오기", "small", GRAY, cx, cy + 20, "center")
        else:
            draw_text(s, f"페드로 라미레즈 — 1번째 카드 출처 선택", "normal", GOLD, cx, cy - 82, "center")
            top = gs.discard[-1].name if gs.discard else "없음"
            draw_text(s, f"버림더미 맨 위: [{top}]", "small", (160, 140, 80), cx, cy + 20, "center")

        pos = pygame.mouse.get_pos()
        self.btn_from_deck.draw(s, self.btn_from_deck.is_hovered(pos))
        if gs.char_draw_type == "pedro":
            self.btn_from_discard.draw(s, self.btn_from_discard.is_hovered(pos))

    # ── Phase banner ──────────────────────────────────────────────────────
    def _draw_phase_banner(self):
        gs = self.gs
        if gs.phase == Phase.GAME_OVER:
            return
        banners = {
            Phase.DYNAMITE:  ("💥 다이너마이트 체크! 클릭하세요", RED),
            Phase.JAIL:      ("🔒 감옥 탈출 시도! 클릭하세요", BLUE),
            Phase.DRAW:      ("📥 클릭하여 카드 2장 드로우", GOLD),
            Phase.RESPONSE:  ("⚡ 반응 카드를 내거나 맞으세요", RED),
            Phase.DUEL:      ("⚔️ 결투 — BANG! 내거나 맞기", ORANGE),
            Phase.DISCARD:   ("🗑️ 버릴 카드 선택", ACCENT),
            Phase.BEER_SAVE: ("🍺 치명타! 맥주로 살아남겠습니까?", GREEN),
            Phase.KIT_PEEK:  ("🔍 킷 칼슨: 카드 2장 선택", GOLD),
            Phase.CHAR_DRAW: ("🤠 특수 드로우", GOLD),
        }
        if gs.phase in banners:
            label, col = banners[gs.phase]
            draw_text(self.screen, label, "small", col, BOARD_CX, 14, "center")

    # ── Game over ─────────────────────────────────────────────────────────
    def _draw_game_over(self):
        s     = self.screen
        cx, cy = WIN_W // 2, WIN_H // 2
        ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 190))
        s.blit(ov, (0, 0))
        rounded_rect(s, PANEL_BG, pygame.Rect(cx - 300, cy - 110, 600, 220), 18)
        pygame.draw.rect(s, GOLD, pygame.Rect(cx - 300, cy - 110, 600, 220), 2, border_radius=18)
        draw_text(s, "게임 종료!", "large", GOLD, cx, cy - 90, "center")
        draw_text(s, self.gs.winner_message(), "normal", WHITE, cx, cy - 38, "center")
        # Reveal all roles
        alive_roles = [(p.name, p.role.value, p.character)
                       for p in self.gs.players]
        for i, (name, role, char) in enumerate(alive_roles):
            char_lbl = f" [{CHARACTERS[char].name_ko}]" if char else ""
            draw_text(s, f"{name}: {role}{char_lbl}", "small", GRAY,
                      cx, cy + 10 + i * 20, "center")
        draw_text(s, "[← 메뉴] 버튼으로 돌아가세요", "small", GRAY, cx, cy + 90, "center")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _compute_positions(n: int) -> dict[int, tuple[int, int]]:
    positions = {}
    for i in range(n):
        angle = math.radians(90 + 360 * i / n)
        positions[i] = (
            int(BOARD_CX + math.cos(angle) * PLAYER_RADIUS),
            int(BOARD_CY + math.sin(angle) * PLAYER_RADIUS),
        )
    return positions


def _worst_card_idx(hand) -> int:
    priority = {CardType.MISSED: 0, CardType.BEER: 1}
    return min(range(len(hand)), key=lambda i: priority.get(hand[i].card_type, 5))
