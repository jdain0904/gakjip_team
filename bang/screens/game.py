"""Main game screen — character-aware, full phase support."""
from __future__ import annotations
import math, pygame
from constants import (
    BG, PANEL_BG, PANEL_DARK, WHITE, GRAY, GOLD, RED, GREEN, DIM,
    BLUE, PURPLE, ACCENT, ORANGE, DARK_RED,
    ROLE_COLORS, CARD_W, CARD_H, BOARD_CX, BOARD_CY, PLAYER_RADIUS,
    WIN_W, WIN_H, AI_STEP_MS,
    BG_TOP, BG_BOTTOM, WOOD_DRK, WOOD_LGT, FELT_DRK, FELT_LGT,
)
from cards import CardType, Suit
from roles import Role
from characters import CHARACTERS, CharacterType
from game_state import GameState, Phase, RespType
from ai_agent import BangAI
from ui_utils import draw_text, rounded_rect, Button, font, vertical_gradient, radial_vignette
from card_renderer import draw_game_card, draw_character_card, draw_heart


CARD_BROWN  = (100, 62, 20)
CARD_BLUE_C = (28, 55, 118)
HP_ON       = (210, 50, 42)
HP_OFF      = (55, 42, 30)


class PlayedCardPopup:
    """Large centered flash of a card the instant it's played — fades in,
    holds, fades out. A new popup simply replaces whatever is showing, so
    a brisk AI turn never has to queue or block on this purely cosmetic effect.
    """
    IN_MS    = 150
    HOLD_MS  = 500
    OUT_MS   = 220
    TOTAL_MS = IN_MS + HOLD_MS + OUT_MS

    def __init__(self, card, actor_name: str, target_name: str | None = None):
        self.card = card
        self.actor_name = actor_name
        self.target_name = target_name
        self.t = 0

    def update(self, dt_ms: int):
        self.t += dt_ms

    @property
    def done(self) -> bool:
        return self.t >= self.TOTAL_MS

    def draw(self, surf: pygame.Surface):
        t = self.t
        if t < self.IN_MS:
            e = t / self.IN_MS
            e = e * e * (3 - 2 * e)
            scale, alpha = 0.7 + 0.3 * e, e
        elif t < self.IN_MS + self.HOLD_MS:
            scale, alpha = 1.0, 1.0
        else:
            e = min(1.0, (t - self.IN_MS - self.HOLD_MS) / self.OUT_MS)
            e = e * e * (3 - 2 * e)
            scale, alpha = 1.0 + 0.06 * e, 1.0 - e
        a255 = max(0, min(255, int(255 * alpha)))

        if a255 > 3:
            dim = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            dim.fill((0, 0, 0, int(135 * alpha)))
            surf.blit(dim, (0, 0))

        cw, ch = int(CARD_W * 3.0), int(CARD_H * 3.0)
        cap_h  = 56
        content = pygame.Surface((cw + 24, ch + cap_h), pygame.SRCALPHA)
        card_rect = pygame.Rect(12, 8, cw, ch)
        shadow = card_rect.inflate(10, 10).move(4, 7)
        pygame.draw.rect(content, (0, 0, 0, 140), shadow, border_radius=16)
        draw_game_card(content, self.card, card_rect.x, card_rect.y, cw, ch)

        cx = content.get_width() // 2
        sub = f"{self.actor_name} 사용"
        if self.target_name:
            sub += f"  >  {self.target_name}"
        draw_text(content, self.card.name, "large", GOLD, cx, ch + 16, "center")
        draw_text(content, sub, "small", WHITE, cx, ch + 40, "center")

        sw = max(1, int(content.get_width() * scale))
        sh = max(1, int(content.get_height() * scale))
        scaled = pygame.transform.smoothscale(content, (sw, sh))
        scaled.set_alpha(a255)
        rect = scaled.get_rect(center=(WIN_W // 2, WIN_H // 2 - 6))
        surf.blit(scaled, rect)


class GameScreen:
    """The main table view and event-driven controller for an in-progress
    match: renders every player/hand/equipment from a GameState, routes
    pygame input events to the right phase handler (play, target pick,
    response, duel, ...), and drives AI turns through BangAI between
    frames via update()."""
    RIGHT_X      = 860
    LOG_MAX      = 22
    CARD_SPACING = 90

    def __init__(self, screen: pygame.Surface, gs: GameState, ai_difficulty: int = 1):
        self.screen = screen
        self.gs     = gs
        self.card_popup: PlayedCardPopup | None = None
        self._anim_clock = 0
        self._hover_pid: int | None = None
        self._hover_card = None
        self._hover_card_pos: tuple[int, int] | None = None

        self.ai: dict[int, BangAI] = {
            i: BangAI(i, difficulty=ai_difficulty)
            for i in range(gs.num_players) if i not in gs.human_ids
        }
        self.ai_timer = 0

        self.selected_card_idx: int = -1
        self.target_mode: bool = False
        self.target_candidates: list[int] = []
        self.kit_selected_local: list[int] = []   # which cards picked so far by human

        # Sid Ketchum: discard 2 cards -> heal 1 HP, usable on his own turn.
        self.sid_picking: bool = False
        self.sid_picked: list[int] = []

        # Cat Balou/Panic!: once a target with equipment is chosen, pause
        # here so the human can pick a *specific* in-play card (rulebook:
        # "choose and discard one card in play") instead of always hitting
        # whatever happens to sit at index 0.
        self.strip_mode: bool = False
        self.strip_card_idx: int = -1
        self.strip_target_id: int = -1

        self._player_positions = _compute_positions(gs.num_players)

        self._bg_surf    = _build_bg_surface()
        self._board_surf = _build_board_surface()
        self._board_pos  = (BOARD_CX - self._board_surf.get_width() // 2,
                             BOARD_CY - self._board_surf.get_height() // 2)
        self._panel_grad = vertical_gradient(
            WIN_W - self.RIGHT_X + 6, WIN_H,
            tuple(min(255, c + 12) for c in PANEL_BG), PANEL_DARK)

        # Pre-rendered character cards for the avatar hover tooltip (static
        # per player for the whole game, so build once instead of per frame).
        self._char_card_surfs: dict[int, pygame.Surface] = {}
        self.TIP_CARD_W, self.TIP_CARD_H = 150, 211
        for pid, pl in enumerate(gs.players):
            if pl.character is None:
                continue
            surf = pygame.Surface((self.TIP_CARD_W, self.TIP_CARD_H), pygame.SRCALPHA)
            draw_character_card(surf, pl.character, pl.max_hp,
                                pygame.Rect(0, 0, self.TIP_CARD_W, self.TIP_CARD_H))
            self._char_card_surfs[pid] = surf

        self.btn_menu    = Button((WIN_W - 118, 8, 108, 34), "< 메뉴", DIM, radius=7)
        self.btn_endturn = Button((self.RIGHT_X + 5, WIN_H - 55, 185, 44),
                                  "턴 종료", ACCENT, radius=9, fkey="normal")
        self.btn_takeit  = Button((self.RIGHT_X + 5, WIN_H - 55, 185, 44),
                                  "맞겠습니다", RED, radius=9, fkey="normal")
        self.btn_barrel  = Button((self.RIGHT_X + 5, WIN_H - 105, 185, 44),
                                  "나무통 시도", (110, 76, 28), radius=9, fkey="normal")
        self.btn_sid     = Button((self.RIGHT_X + 5, WIN_H - 105, 185, 44),
                                  "카드 2장 > HP+1", (110, 28, 90), radius=9, fkey="normal")
        self.btn_beer    = Button((self.RIGHT_X + 5, WIN_H - 55, 185, 44),
                                  "맥주 사용", GREEN, radius=9, fkey="normal")
        self.btn_die     = Button((self.RIGHT_X + 200, WIN_H - 55, 140, 44),
                                  "탈락", (100, 40, 40), radius=9, fkey="normal")
        # Character-draw buttons
        self.btn_from_deck    = Button((WIN_W // 2 - 180, WIN_H // 2 + 60, 160, 44),
                                       "덱에서", ACCENT, radius=9, fkey="normal")
        self.btn_from_discard = Button((WIN_W // 2 + 20, WIN_H // 2 + 60, 160, 44),
                                       "버림더미에서", (60, 100, 60), radius=9, fkey="normal")

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

    def consume_handoff(self) -> dict:
        self._need_handoff = False
        name = self._handoff_name
        self._handoff_name = ""
        p = next((pl for pl in self.gs.players if pl.name == name), None)
        if p:
            return {
                "name":      p.name,
                "role":      p.role,
                "character": p.character,
                "max_hp":    p.max_hp,
            }
        # fallback (shouldn't happen)
        from roles import Role
        from characters import CharacterType
        return {"name": name, "role": Role.OUTLAW,
                "character": CharacterType.BART_CASSIDY, "max_hp": 4}

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
    def _sid_ketchum_available(self, pid: int) -> bool:
        p = self.gs.players[pid]
        return (p.character == CharacterType.SID_KETCHUM
                and p.hp < p.max_hp and len(p.hand) >= 2)

    def _handle_play(self, event, pos, pid):
        gs = self.gs
        if self.strip_mode:
            self._handle_strip_pick(event, pos, pid)
            return

        if self._sid_ketchum_available(pid) and self.btn_sid.clicked(event, pos):
            self.sid_picking = not self.sid_picking
            self.sid_picked  = []
            return

        if self.sid_picking:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                ci = self._click_hand_card(pos, pid)
                if ci >= 0 and ci not in self.sid_picked:
                    self.sid_picked.append(ci)
                    if len(self.sid_picked) == 2:
                        gs.use_sid_ketchum(pid, self.sid_picked[0], self.sid_picked[1])
                        self.sid_picking = False
                        self.sid_picked  = []
                        self._on_phase_change()
            return

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
                card = gs.players[pid].hand[self.selected_card_idx]
                if (card.card_type in (CardType.CAT_BALOU, CardType.PANIC)
                        and gs.players[clicked].equipment):
                    self.strip_card_idx    = self.selected_card_idx
                    self.strip_target_id   = clicked
                    self.target_mode       = False
                    self.target_candidates = []
                    self.strip_mode        = True
                else:
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
                self._spawn_popup(card, pid)
                gs.play_card(pid, ci)
                self._on_phase_change()

    def _exec_with_target(self, pid, card_idx, target_id, target_card_idx=-1):
        card = self.gs.players[pid].hand[card_idx]
        self._spawn_popup(card, pid, target_id)
        self.gs.play_card(pid, card_idx, target_id=target_id, target_card_idx=target_card_idx)
        self._deselect()
        self._on_phase_change()

    # ── Cat Balou/Panic! strip-target picker ────────────────────────────────
    def _handle_strip_pick(self, event, pos, pid):
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        gs     = self.gs
        target = gs.players[self.strip_target_id]
        choice = self._click_strip_picker_card(pos, target)
        if choice is None:
            return
        self._exec_with_target(pid, self.strip_card_idx, self.strip_target_id,
                                target_card_idx=choice)

    def _spawn_popup(self, card, actor_pid: int, target_pid: int = -1):
        """Flash a large copy of the card that was just played at screen center."""
        actor  = self.gs.players[actor_pid].name
        target = self.gs.players[target_pid].name if target_pid >= 0 else None
        self.card_popup = PlayedCardPopup(card, actor, target)

    # ── RESPONSE ──────────────────────────────────────────────────────────
    def _handle_response(self, event, pos, pid):
        gs = self.gs
        if gs.resp_current != pid:
            return
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        # The Barrel draw is optional ("you may try"), not mandatory, and
        # doesn't apply against Indians! — so it must be its own button, not
        # something that silently eats whatever the player's first click was
        # meant for (that used to make the real card click look unresponsive).
        if (gs.resp_type != RespType.INDIANS and not gs.barrel_checked
                and gs.players[pid].has_barrel() and self.btn_barrel.clicked(event, pos)):
            saved = gs.check_barrel()
            if saved:
                self._on_phase_change()
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
                self._spawn_popup(card, pid)
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
                self._spawn_popup(card, pid)
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

        cx = WIN_W // 2
        cy = WIN_H // 2

        if self.btn_from_deck.clicked(event, pos):
            gs.char_draw_from_deck()
            self._on_phase_change()
            return

        if gs.char_draw_type == "pedro" and self.btn_from_discard.clicked(event, pos):
            gs.char_draw_from_discard()
            self._on_phase_change()
            return

        if gs.char_draw_type == "jesse":
            alive = gs._alive_ids()
            targets = [i for i in alive if i != pid and gs.players[i].hand]
            # Must match the dynamic panel_h in _draw_char_draw_overlay(),
            # or button hit-boxes drift out of sync with where they're drawn.
            panel_h = max(260, 76 + len(targets) * 42 + 56)
            panel_y = cy - panel_h // 2
            btn_y = panel_y + 76
            for ti in targets:
                btn = pygame.Rect(cx - 200, btn_y, 400, 34)
                if btn.collidepoint(pos):
                    gs.char_draw_from_player(ti)
                    self._on_phase_change()
                    return
                btn_y += 42

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
        self._anim_clock += dt_ms
        if self.card_popup:
            self.card_popup.update(dt_ms)
            if self.card_popup.done:
                self.card_popup = None

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
            if (gs.resp_type != RespType.INDIANS and not gs.barrel_checked
                    and gs.players[pid].has_barrel()):
                gs.check_barrel()
                return
            action = self.ai[pid].choose_response(gs)
            if action[0] == "missed":
                card = gs.players[pid].hand[action[1]]
                self._spawn_popup(card, pid)
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
                card = gs.players[pid].hand[action[1]]
                self._spawn_popup(card, pid)
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
                card = gs.players[pid].hand[action[1]]
                self._spawn_popup(card, pid)
                gs.play_card(pid, action[1])
            elif len(action) == 3:
                card = gs.players[pid].hand[action[1]]
                self._spawn_popup(card, pid, action[2])
                gs.play_card(pid, action[1], target_id=action[2])
            elif len(action) == 4:
                card = gs.players[pid].hand[action[1]]
                self._spawn_popup(card, pid, action[2])
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
            self._notify_ai_game_over()
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

    def _notify_ai_game_over(self):
        """Update Hard AI learning weights based on game outcome."""
        gs = self.gs
        if gs.winner_role is None:
            return
        for pid, ai in self.ai.items():
            ai.record_game_result(gs.player_won(pid))

    def _deselect(self):
        self.selected_card_idx = -1
        self.target_mode       = False
        self.target_candidates = []
        self.strip_mode        = False
        self.strip_card_idx    = -1
        self.strip_target_id   = -1
        self.sid_picking       = False
        self.sid_picked        = []

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

    def _click_strip_picker_card(self, pos, target) -> int | None:
        """Hit-test the Cat Balou/Panic! picker. Returns an `all_cards()`
        index for an equipment pick, -1 for the "random hand card" slot,
        or None if the click missed everything (layout mirrors the draw
        function below — keep both in sync)."""
        equip       = target.equipment
        show_random = bool(target.hand)
        n           = len(equip) + (1 if show_random else 0)
        cx          = WIN_W // 2
        ox          = cx - n * 48
        cy          = WIN_H // 2 - 60
        for i in range(len(equip)):
            if pygame.Rect(ox + i * 96, cy, CARD_W, CARD_H).collidepoint(pos):
                return len(target.hand) + i
        if show_random:
            x = ox + len(equip) * 96
            if pygame.Rect(x, cy, CARD_W, CARD_H).collidepoint(pos):
                return -1
        return None

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
        s.blit(self._bg_surf, (0, 0))
        self._hover_card = None
        self._hover_card_pos = None
        self._draw_board()
        self._draw_deck_discard()
        self._draw_players()
        self._draw_right_panel()
        self._draw_hand_area()
        self._draw_gen_store_overlay()
        self._draw_strip_picker_overlay()
        self._draw_kit_peek_overlay()
        self._draw_char_draw_overlay()
        self._draw_phase_banner()
        if (self._hover_pid is not None and self.gs.phase not in
                (Phase.GEN_STORE, Phase.KIT_PEEK, Phase.CHAR_DRAW, Phase.GAME_OVER)):
            self._draw_player_tooltip(self._hover_pid)
        if self._hover_card is not None:
            self._draw_card_tooltip(self._hover_card, *self._hover_card_pos)
        if self.card_popup:
            self.card_popup.draw(s)
        if self.gs.phase == Phase.GAME_OVER:
            self._draw_game_over()
        pos = pygame.mouse.get_pos()
        self.btn_menu.draw(s, self.btn_menu.is_hovered(pos))
        pygame.display.flip()

    def _draw_board(self):
        self.screen.blit(self._board_surf, self._board_pos)

    def _draw_deck_discard(self):
        """Draw pile (center-left) + discard pile (center-right) on the felt."""
        s, gs = self.screen, self.gs
        dw, dh = int(CARD_W * 0.85), int(CARD_H * 0.85)
        gap = 20
        deck_x = BOARD_CX - dw - gap // 2
        disc_x = BOARD_CX + gap // 2
        y = BOARD_CY - dh // 2

        n_deck = len(gs.deck)
        if n_deck > 0:
            layers = 3 if n_deck > 8 else (2 if n_deck > 2 else 1)
            for i in range(layers - 1, -1, -1):
                off = i * 2
                draw_game_card(s, None, deck_x - off, y - off, dw, dh, face_down=True)
        else:
            rect = pygame.Rect(deck_x, y, dw, dh)
            rounded_rect(s, (20, 14, 6), rect, 8)
            pygame.draw.rect(s, DIM, rect, 2, border_radius=8)
        draw_text(s, f"덱 {n_deck}장", "tiny", GOLD, deck_x + dw // 2, y + dh + 8, "center")

        n_disc = len(gs.discard)
        if n_disc > 0:
            layers = 3 if n_disc > 8 else (2 if n_disc > 2 else 1)
            for i in range(layers - 1, 0, -1):
                off = i * 2
                draw_game_card(s, None, disc_x + off, y - off, dw, dh, face_down=True)
            draw_game_card(s, gs.discard[-1], disc_x, y, dw, dh)
            if (gs.phase not in (Phase.GEN_STORE, Phase.KIT_PEEK, Phase.CHAR_DRAW, Phase.GAME_OVER)
                    and pygame.Rect(disc_x, y, dw, dh).collidepoint(pygame.mouse.get_pos())):
                self._hover_card = gs.discard[-1]
                self._hover_card_pos = (disc_x + dw // 2, y)
        else:
            rect = pygame.Rect(disc_x, y, dw, dh)
            rounded_rect(s, (20, 14, 6), rect, 8)
            pygame.draw.rect(s, DIM, rect, 2, border_radius=8)
        draw_text(s, f"버림 {n_disc}장", "tiny", GOLD, disc_x + dw // 2, y + dh + 8, "center")

    def _human_viewer_pid(self) -> int:
        """The human player whose perspective the table should be drawn from
        right now (-1 if it's nobody's human turn, e.g. pure AI spectating).

        Same phase-based resolution _draw_hand_area uses to decide whose
        hand to reveal — factored out so other drawing (e.g. per-opponent
        distance) can use the same "whose point of view is this" notion.
        """
        gs = self.gs
        if gs.phase == Phase.RESPONSE:
            show_pid = gs.resp_current
        elif gs.phase == Phase.DUEL:
            show_pid = gs.duel_current
        elif gs.phase == Phase.BEER_SAVE:
            show_pid = gs.beer_save_pid
        else:
            show_pid = gs.current_pid
        if show_pid < 0 or not gs.players[show_pid].alive or show_pid not in gs.human_ids:
            return -1
        return show_pid

    def _role_reveal_pids(self) -> set:
        """Players whose own (otherwise-secret) role should be shown right
        now, on top of anyone already revealed (Sheriff, eliminated).

        Solo vs AI: the one human always sees their own role — it's their
        own information, not something they need to "discover" by acting.
        Local hotseat: everyone is human, so revealing all roles all the
        time would spoil the secret for whoever is glancing at the shared
        screen; only the player whose turn/response it currently is gets
        to see their own role, mirroring _human_viewer_pid().
        """
        gs = self.gs
        if len(gs.human_ids) <= 1:
            return set(gs.human_ids)
        vp = self._human_viewer_pid()
        return {vp} if vp >= 0 else set()

    def _draw_players(self):
        s   = self.screen
        gs  = self.gs
        pos = pygame.mouse.get_pos()
        pulse = (math.sin(self._anim_clock / 260.0) + 1) / 2   # 0..1 breathing glow
        self._hover_pid = None
        viewer_pid  = self._human_viewer_pid()
        reveal_pids = self._role_reveal_pids()

        for pid, (px, py) in self._player_positions.items():
            p      = gs.players[pid]
            # You always know your own role — only other players' roles stay
            # hidden until revealed (official rule: "look at your role but
            # keep it secret", which only restricts what others can see).
            reveal = p.role_revealed or pid in reveal_pids
            col = ROLE_COLORS.get(p.role.value, GRAY) if reveal else GRAY
            dim = 1.0 if p.alive else 0.35

            is_active    = (pid == gs.current_pid and gs.phase not in
                            (Phase.RESPONSE, Phase.DUEL, Phase.GEN_STORE))
            is_responder = (pid == gs.resp_current and gs.phase in (Phase.RESPONSE, Phase.DUEL))
            is_beer_save = pid == gs.beer_save_pid
            is_target    = pid in self.target_candidates

            R = 42
            hovered = p.alive and math.hypot(pos[0] - px, pos[1] - py) <= R + 8
            if hovered:
                self._hover_pid = pid
            glow_k = 0.32 + 0.22 * pulse
            # Glows
            if is_active:
                for gr in (R+18, R+12, R+6):
                    pygame.draw.circle(s, tuple(int(c * glow_k) for c in GOLD), (px, py), gr)
            if is_responder or is_beer_save:
                for gr in (R+18, R+12, R+6):
                    pygame.draw.circle(s, tuple(int(c * glow_k) for c in RED), (px, py), gr)
            if is_target:
                for gr in (R+20, R+13, R+6):
                    pygame.draw.circle(s, (60, 140, 60), (px, py), gr)

            base = tuple(int(c * dim) for c in col)

            # Grounding shadow + seat disc
            pygame.draw.circle(s, (8, 5, 2), (px + 3, py + 5), R + 3)
            pygame.draw.circle(s, (20, 14, 6), (px, py), R)
            pygame.draw.circle(s, base, (px, py), R, 3 if p.alive else 1)
            if p.alive:
                # Soft upper-left sheen for a glossy, less flat token
                sheen = pygame.Rect(px - R + 5, py - R + 5, (R - 5) * 2, (R - 5) * 2)
                pygame.draw.arc(s, tuple(min(255, c + 55) for c in base),
                                sheen, math.radians(110), math.radians(195), 2)
            if hovered:
                pygame.draw.circle(s, WHITE, (px, py), R + 5, 2)

            if not p.alive:
                # Draw X using lines (no unicode needed)
                xr = 10
                pygame.draw.line(s, (100, 50, 50), (px - xr, py - xr), (px + xr, py + xr), 3)
                pygame.draw.line(s, (100, 50, 50), (px + xr, py - xr), (px - xr, py + xr), 3)
            else:
                draw_text(s, f"P{pid+1}", "small", WHITE, px, py - 8, "center")

            # Nameplate panel (sized to fit the text it holds)
            role_lbl = p.role.value if reveal else "?"
            char_lbl = CHARACTERS[p.character].name_ko if p.character else None
            dist     = gs.distance(viewer_pid, pid) if (p.alive and pid != viewer_pid
                                                         and viewer_pid >= 0) else None
            dist_lbl = f"거리 {dist}" if dist is not None else None
            lines    = ([p.name, role_lbl] + ([char_lbl] if char_lbl else [])
                        + ([dist_lbl] if dist_lbl else []))
            fnt      = font("tiny")
            plate_w  = max(fnt.size(t)[0] for t in lines) + 18
            plate_h  = 14 * len(lines) + 10
            plate    = pygame.Rect(0, 0, plate_w, plate_h)
            plate.midtop = (px, py + R + 2)
            rounded_rect(s, (14, 9, 4), plate, 6)
            pygame.draw.rect(s, base if p.alive else DIM, plate, 1, border_radius=6)

            ly = plate.y + 7
            draw_text(s, p.name, "tiny", col if p.alive else GRAY, px, ly, "center")
            ly += 14
            draw_text(s, role_lbl, "tiny", col if reveal else DIM, px, ly, "center")
            if char_lbl:
                ly += 14
                draw_text(s, char_lbl, "tiny", (190, 165, 100), px, ly, "center")
            if dist_lbl:
                ly += 14
                in_range = dist <= gs.players[viewer_pid].gun_range()
                dist_col = (110, 200, 110) if in_range else (205, 110, 100)
                draw_text(s, dist_lbl, "tiny", dist_col, px, ly, "center")

            self._draw_hp(s, px, py - R - 22, p)

            # Equipment icons
            eq_x = px - len(p.equipment) * 14
            eq_y = plate.bottom + 6
            for ci2, c in enumerate(p.equipment):
                eq_col = (80, 80, 180) if c.is_blue else ORANGE
                eq_r   = pygame.Rect(eq_x + ci2 * 28, eq_y, 26, 16)
                rounded_rect(s, eq_col, eq_r, 3)
                draw_text(s, c.name[:4], "tiny", WHITE,
                          eq_r.centerx, eq_r.centery, "center")
                if eq_r.collidepoint(pos):
                    self._hover_card = c
                    self._hover_card_pos = (eq_r.centerx, eq_r.top)

    def _draw_hp(self, s, cx, cy, player):
        r   = 8
        gap = 4
        tw  = player.max_hp * (r * 2 + gap) - gap
        sx  = cx - tw // 2 + r
        for i in range(player.max_hp):
            on = i < player.hp
            bx = sx + i * (r * 2 + gap)
            draw_heart(s, bx, cy, r, HP_ON if on else HP_OFF)
            if on:
                draw_heart(s, bx, cy, r, (240, 110, 100), filled=False)

    # ── Avatar hover tooltip (character card + UNO-style hand fan) ─────────
    def _draw_player_tooltip(self, pid: int):
        s, gs = self.screen, self.gs
        p = gs.players[pid]
        px, py = self._player_positions[pid]

        cw, ch = self.TIP_CARD_W, self.TIP_CARD_H
        pad = 12
        name_h, fan_label_h, fan_h = 24, 16, 50
        panel_w = cw + pad * 2
        panel_h = pad + name_h + ch + 10 + fan_label_h + 18 + fan_h + pad

        bx = px - panel_w // 2
        by = py - 50 - panel_h
        if by < 6:
            by = py + 50
        bx = max(6, min(WIN_W - panel_w - 6, bx))
        by = max(6, min(WIN_H - panel_h - 6, by))

        panel = pygame.Rect(bx, by, panel_w, panel_h)
        shadow = panel.inflate(8, 8).move(0, 5)
        rounded_rect(s, (8, 5, 2), shadow, 14)
        rounded_rect(s, PANEL_BG, panel, 14)
        pygame.draw.rect(s, GOLD, panel, 2, border_radius=14)

        draw_text(s, p.name, "small", GOLD, panel.centerx, panel.y + pad, "center")

        card_x = panel.centerx - cw // 2
        card_y = panel.y + pad + name_h
        char_surf = self._char_card_surfs.get(pid)
        if char_surf:
            s.blit(char_surf, (card_x, card_y))

        fan_label_y = card_y + ch + 10
        draw_text(s, f"손패 {len(p.hand)}장", "tiny", WHITE,
                  panel.centerx, fan_label_y, "center")
        self._draw_hand_fan(s, len(p.hand), panel.centerx, fan_label_y + 18)

    def _draw_hand_fan(self, surf, n, cx, top_y):
        """UNO-mobile-style fan of face-down mini cards + a count badge."""
        mini_w, mini_h = 30, 42
        if n == 0:
            draw_text(surf, "(없음)", "tiny", DIM, cx, top_y + mini_h // 2, "center")
            return
        shown   = min(n, 6)
        spacing = 14
        fan_w   = mini_w + (shown - 1) * spacing
        badge_r = 13
        total_w = fan_w + 10 + badge_r * 2
        sx = cx - total_w // 2
        for i in range(shown):
            t   = i / (shown - 1) if shown > 1 else 0.5
            bow = int(6 * (1 - (2 * t - 1) ** 2))
            draw_game_card(surf, None, sx + i * spacing, top_y - bow,
                           mini_w, mini_h, face_down=True)
        bx = sx + fan_w + 10 + badge_r
        by = top_y + mini_h // 2
        pygame.draw.circle(surf, (205, 40, 35), (bx, by), badge_r)
        pygame.draw.circle(surf, WHITE, (bx, by), badge_r, 2)
        draw_text(surf, str(n), "tiny", WHITE, bx, by, "center")

    # ── Card hover tooltip (name + rule summary) ────────────────────────────
    def _draw_card_tooltip(self, card, anchor_x: int, anchor_y: int):
        """Small popup with a card's full name + a brief rule summary, shown
        while the mouse hovers over any rendered copy of that card."""
        s = self.screen
        lines = _wrap_text(card.desc, "tiny", 220)

        pad, name_h, line_h = 10, 20, 16
        text_w  = max([font("tiny").size(l)[0] for l in lines] +
                      [font("small").size(card.name)[0]])
        panel_w = text_w + pad * 2
        panel_h = pad + name_h + len(lines) * line_h + pad

        bx = anchor_x - panel_w // 2
        by = anchor_y - panel_h - 10
        if by < 6:
            by = anchor_y + 20
        bx = max(6, min(WIN_W - panel_w - 6, bx))
        by = max(6, min(WIN_H - panel_h - 6, by))

        panel  = pygame.Rect(bx, by, panel_w, panel_h)
        shadow = panel.inflate(6, 6).move(0, 4)
        rounded_rect(s, (8, 5, 2), shadow, 10)
        rounded_rect(s, PANEL_BG, panel, 10)
        pygame.draw.rect(s, GOLD, panel, 2, border_radius=10)

        ty = panel.y + pad
        draw_text(s, card.name, "small", GOLD, panel.centerx, ty, "center")
        ty += name_h
        for line in lines:
            draw_text(s, line, "tiny", WHITE, panel.centerx, ty, "center")
            ty += line_h

    # ── Right panel ───────────────────────────────────────────────────────
    def _draw_right_panel(self):
        s  = self.screen
        gs = self.gs
        rx = self.RIGHT_X
        s.blit(self._panel_grad, (rx - 6, 0))
        pygame.draw.line(s, (70, 46, 18), (rx - 6, 0), (rx - 6, WIN_H), 2)

        reveal_pids = self._role_reveal_pids()

        if gs.phase not in (Phase.GAME_OVER,):
            pid = gs.current_pid
            col = ROLE_COLORS.get(gs.players[pid].role.value, ACCENT) \
                if (gs.players[pid].role_revealed or pid in reveal_pids) else ACCENT
            banner = pygame.Rect(rx, 8, WIN_W - rx - 10, 36)
            shadow = banner.inflate(4, 4).move(0, 2)
            rounded_rect(s, (10, 6, 2), shadow, 9)
            rounded_rect(s, col, banner, 8)
            pygame.draw.line(s, tuple(min(255, c + 40) for c in col),
                              (banner.x + 6, banner.y + 2), (banner.right - 6, banner.y + 2), 1)
            draw_text(s, f"Turn {gs.turn_num + 1}  —  {gs.players[pid].name}",
                      "normal", BG, rx + (WIN_W - rx - 10) // 2, 26, "center")

        py2 = 54
        for pid, p in enumerate(gs.players):
            reveal = p.role_revealed or pid in reveal_pids
            col   = ROLE_COLORS.get(p.role.value, GRAY) if reveal else GRAY
            h     = 58
            bg_c  = (35, 22, 8) if p.alive else (20, 14, 6)
            row   = pygame.Rect(rx, py2, WIN_W - rx - 8, h)
            rounded_rect(s, bg_c, row, 6)
            # Role-colored accent tab on the left edge of every row
            accent = pygame.Rect(row.x, row.y + 4, 4, row.h - 8)
            rounded_rect(s, col if p.alive else DIM, accent, 2)
            if pid == gs.current_pid and p.alive:
                pygame.draw.rect(s, col, row, 2, border_radius=6)

            pygame.draw.circle(s, col if p.alive else DIM, (rx + 16, py2 + h // 2), 8)
            if p.alive:
                pygame.draw.circle(s, (235, 225, 200), (rx + 14, py2 + h // 2 - 2), 2)
            draw_text(s, p.name, "small", WHITE if p.alive else GRAY, rx + 28, py2 + 4)

            role_lbl = p.role.value if reveal else "?"
            char_lbl = CHARACTERS[p.character].name_ko if p.character else ""
            draw_text(s, f"{role_lbl}  {char_lbl}", "tiny", col, rx + 28, py2 + 22)

            bar_w    = WIN_W - rx - 67
            filled   = int(bar_w * (p.hp / p.max_hp)) if p.max_hp else 0
            bar_rect = pygame.Rect(rx + 28, py2 + 40, bar_w, 8)
            pygame.draw.rect(s, DIM,   bar_rect, border_radius=4)
            if filled > 0:
                fill_rect = pygame.Rect(rx + 28, py2 + 40, filled, 8)
                pygame.draw.rect(s, HP_ON, fill_rect, border_radius=4)
                pygame.draw.line(s, (250, 140, 130),
                                  (fill_rect.x + 2, fill_rect.y + 2),
                                  (fill_rect.right - 2, fill_rect.y + 2), 1)
            draw_text(s, f"{p.hp}/{p.max_hp}", "tiny", col,
                      rx + 30 + bar_w, py2 + 37)
            py2 += h + 3

        py2 += 6
        pygame.draw.line(s, (70, 46, 18), (rx + 2, py2), (WIN_W - 10, py2), 1)
        py2 += 10
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

        show_pid = self._human_viewer_pid()
        if show_pid < 0:
            return

        p  = gs.players[show_pid]
        s  = self.screen
        hx, hy = self._hand_origin(show_pid)
        hand_w  = len(p.hand) * self.CARD_SPACING + (CARD_W - self.CARD_SPACING)
        panel = pygame.Rect(hx - 8, hy - 30, max(hand_w + 16, 200), CARD_H + 64)
        rounded_rect(s, (10, 6, 2), panel.inflate(6, 6).move(0, 4), 12)
        rounded_rect(s, PANEL_DARK, panel, 10)
        pygame.draw.rect(s, (96, 64, 26), panel, 1, border_radius=10)

        char_lbl = f" [{CHARACTERS[p.character].name_ko}]" if p.character else ""
        labels = {
            Phase.DRAW:      f"{p.name}{char_lbl} — 클릭하여 드로우",
            Phase.PLAY:      f"{p.name}{char_lbl} — 손패 ({len(p.hand)}장)  HP {p.hp}/{p.max_hp}  사거리 {p.gun_range()}",
            Phase.RESPONSE:  f"{p.name} — {'BANG!' if gs.resp_type == RespType.INDIANS else 'Missed!'} 로 반응 또는 맞기",
            Phase.DUEL:      f"{p.name} — 결투: BANG! 내거나 맞기",
            Phase.DISCARD:   f"{p.name} — 버릴 카드 선택 ({len(p.hand) - p.hand_limit()}장 더)",
            Phase.BEER_SAVE: f"{p.name} — 맥주로 살아남겠습니까?",
        }
        draw_text(s, labels.get(gs.phase, ""), "small", GOLD, hx - 8, hy - 26)

        pos = pygame.mouse.get_pos()
        for i, card in enumerate(p.hand):
            is_sel  = (i == self.selected_card_idx) or (i in self.sid_picked)
            playable = gs.can_play_card(show_pid, i) if gs.phase == Phase.PLAY else False
            is_resp  = self._is_valid_resp_card(show_pid, i)
            is_beer  = (gs.phase == Phase.BEER_SAVE and card.card_type == CardType.BEER)
            hover    = pygame.Rect(hx + i * self.CARD_SPACING, hy, CARD_W, CARD_H).collidepoint(pos)
            lift     = -14 if (is_sel or hover) else 0
            self._draw_card(s, card, hx + i * self.CARD_SPACING, hy + lift,
                            is_sel, playable or is_resp or is_beer or self.sid_picking,
                            gs.phase == Phase.DISCARD)
            if hover:
                self._hover_card = card
                self._hover_card_pos = (hx + i * self.CARD_SPACING + CARD_W // 2, hy + lift)

        if gs.phase == Phase.PLAY:
            self.btn_endturn.draw(s, self.btn_endturn.is_hovered(pos))
        if gs.phase in (Phase.RESPONSE, Phase.DUEL):
            self.btn_takeit.draw(s, self.btn_takeit.is_hovered(pos))
        if (gs.phase == Phase.RESPONSE and gs.resp_type != RespType.INDIANS
                and not gs.barrel_checked and p.has_barrel()):
            self.btn_barrel.draw(s, self.btn_barrel.is_hovered(pos))
        if gs.phase == Phase.PLAY and self._sid_ketchum_available(show_pid):
            self.btn_sid.draw(s, self.btn_sid.is_hovered(pos))
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
        draw_game_card(surf, card, x, y, CARD_W, CARD_H,
                       selected=selected, playable=playable,
                       discard_mode=discard_mode)

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
            if hover:
                self._hover_card = card
                self._hover_card_pos = (ox + i * 96 + CARD_W // 2, cy - 60)

    # ── Cat Balou/Panic! strip-target picker overlay ───────────────────────
    def _draw_strip_picker_overlay(self):
        if not self.strip_mode:
            return
        gs          = self.gs
        s           = self.screen
        target      = gs.players[self.strip_target_id]
        equip       = target.equipment
        show_random = bool(target.hand)
        n           = len(equip) + (1 if show_random else 0)
        if n == 0:
            return
        cx, cy = WIN_W // 2, WIN_H // 2
        ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 140))
        s.blit(ov, (0, 0))
        pw = n * 96 + 40
        panel = pygame.Rect(cx - pw // 2, cy - 100, pw, 220)
        rounded_rect(s, PANEL_BG, panel, 14)
        pygame.draw.rect(s, GOLD, panel, 2, border_radius=14)
        draw_text(s, f"{target.name}에게서 빼앗을 카드 선택", "normal", GOLD, cx, cy - 88, "center")
        ox  = cx - n * 48
        pos = pygame.mouse.get_pos()
        for i, card in enumerate(equip):
            x     = ox + i * 96
            hover = pygame.Rect(x, cy - 60, CARD_W, CARD_H).collidepoint(pos)
            self._draw_card(s, card, x, cy - 60, False, hover)
            if hover:
                self._hover_card = card
                self._hover_card_pos = (x + CARD_W // 2, cy - 60)
        if show_random:
            x     = ox + len(equip) * 96
            hover = pygame.Rect(x, cy - 60, CARD_W, CARD_H).collidepoint(pos)
            draw_game_card(s, None, x, cy - 60, CARD_W, CARD_H, face_down=True)
            if hover:
                pygame.draw.rect(s, GOLD, pygame.Rect(x, cy - 60, CARD_W, CARD_H), 3, border_radius=8)
            draw_text(s, "무작위 패", "small", WHITE, x + CARD_W // 2, cy - 60 + CARD_H + 14, "center")

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
            if hover:
                self._hover_card = card
                self._hover_card_pos = (ox + i * 100 + CARD_W // 2, cy - 65)

    # ── Character draw overlay ────────────────────────────────────────────
    def _draw_char_draw_overlay(self):
        gs = self.gs
        if gs.phase != Phase.CHAR_DRAW:
            return
        s = self.screen
        cx, cy = WIN_W // 2, WIN_H // 2
        ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 130))
        s.blit(ov, (0, 0))

        pid = gs.char_draw_pid
        p = gs.players[pid]
        from characters import CHARACTERS
        char = CHARACTERS.get(p.character)
        char_name = char.name_ko if char else p.name

        # Jesse Jones lists one row per eligible target — in 5+ player games
        # this can exceed the space a fixed panel height assumed, so grow the
        # panel (and the bottom deck-button row, anchored to panel.bottom)
        # to fit instead of overlapping the last row.
        alive = gs._alive_ids()
        targets = ([i for i in alive if i != pid and gs.players[i].hand]
                   if gs.char_draw_type == "jesse" else [])
        panel_w = 560
        panel_h = max(260, 76 + len(targets) * 42 + 56)
        panel = pygame.Rect(cx - panel_w // 2, cy - panel_h // 2, panel_w, panel_h)
        rounded_rect(s, PANEL_BG, panel, 14)
        pygame.draw.rect(s, GOLD, panel, 2, border_radius=14)

        draw_text(s, f"[ {char_name} ] 첫 번째 카드 출처 선택", "normal", GOLD,
                  cx, panel.y + 16, "center")

        if gs.char_draw_type == "jesse":
            draw_text(s, "다른 플레이어 손패에서 가져오거나, 덱에서 뽑기", "small", GRAY,
                      cx, panel.y + 46, "center")
            # List valid targets as buttons
            btn_y = panel.y + 76
            mouse = pygame.mouse.get_pos()
            for ti in targets:
                tp = gs.players[ti]
                btn = pygame.Rect(cx - 200, btn_y, 400, 34)
                hovered = btn.collidepoint(mouse)
                bg = (70, 110, 55) if hovered else (45, 75, 35)
                rounded_rect(s, bg, btn, 7)
                pygame.draw.rect(s, (100, 170, 80), btn, 1, border_radius=7)
                hand_n = len(tp.hand)
                draw_text(s, f"{tp.name}  (손패 {hand_n}장)",
                          "small", WHITE, btn.centerx, btn.centery, "center")
                btn_y += 42
            if not targets:
                draw_text(s, "(가져올 수 있는 플레이어 없음 — 덱에서 뽑기)", "small",
                          (180, 140, 80), cx, panel.y + 76, "center")
        else:  # pedro
            draw_text(s, "버림더미 맨 위 카드를 가져오거나, 덱에서 뽑기", "small", GRAY,
                      cx, panel.y + 46, "center")
            if gs.discard:
                top = gs.discard[-1]
                from cards import Suit
                from ui_utils import draw_suit_icon
                suit_col = (190, 45, 38) if top.suit in (Suit.HEARTS, Suit.DIAMONDS) else (230, 220, 200)
                val_str = {1: "A", 11: "J", 12: "Q", 13: "K"}.get(top.value, str(top.value))
                # Draw card info: name + suit icon + value, centered
                icon_y = panel.y + 76
                left_r  = draw_text(s, f"[ {top.name}", "sub", suit_col, cx - 10, icon_y, "midright")
                draw_suit_icon(s, top.suit.value, cx - 2, icon_y, 14, suit_col)
                draw_text(s, f"{val_str} ]", "sub", suit_col, cx + 8, icon_y, "midleft")
            else:
                draw_text(s, "(버림더미 비어있음)", "small", GRAY, cx, panel.y + 76, "center")

        pos = pygame.mouse.get_pos()
        btn_row_y = panel.bottom - 56
        self.btn_from_deck.rect.topleft = (cx - 180, btn_row_y)
        self.btn_from_deck.draw(s, self.btn_from_deck.is_hovered(pos))
        if gs.char_draw_type == "pedro":
            self.btn_from_discard.rect.topleft = (cx + 10, btn_row_y)
            self.btn_from_discard.draw(s, self.btn_from_discard.is_hovered(pos))

    # ── Phase banner ──────────────────────────────────────────────────────
    def _draw_phase_banner(self):
        gs = self.gs
        if gs.phase == Phase.GAME_OVER:
            return
        banners = {
            Phase.DYNAMITE:  ("다이너마이트 체크! 클릭하세요", RED),
            Phase.JAIL:      ("감옥 탈출 시도! 클릭하세요", BLUE),
            Phase.DRAW:      ("클릭하여 카드 2장 드로우", GOLD),
            Phase.RESPONSE:  ("반응 카드를 내거나 맞으세요", RED),
            Phase.DUEL:      ("결투 — BANG! 내거나 맞기", ORANGE),
            Phase.DISCARD:   ("버릴 카드 선택", ACCENT),
            Phase.BEER_SAVE: ("치명타! 맥주로 살아남겠습니까?", GREEN),
            Phase.KIT_PEEK:  ("킷 칼슨: 카드 2장 선택", GOLD),
            Phase.CHAR_DRAW: ("특수 드로우", GOLD),
        }
        if gs.phase in banners:
            label, col = banners[gs.phase]
            s   = self.screen
            fnt = font("small")
            tw, th = fnt.size(label)
            pill = pygame.Rect(0, 0, tw + 44, th + 16)
            pill.midtop = (BOARD_CX, 6)
            rounded_rect(s, (10, 6, 2), pill.inflate(4, 4).move(0, 2), pill.h // 2)
            rounded_rect(s, (18, 12, 5), pill, pill.h // 2)
            pygame.draw.rect(s, col, pill, 2, border_radius=pill.h // 2)
            draw_text(s, label, "small", col, pill.centerx, pill.centery, "center")

    # ── Game over ─────────────────────────────────────────────────────────
    def _draw_game_over(self):
        s     = self.screen
        cx, cy = WIN_W // 2, WIN_H // 2
        ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 190))
        s.blit(ov, (0, 0))
        # Reveal all roles
        alive_roles = [(p.name, p.role.value, p.character)
                       for p in self.gs.players]
        # Role list grows with player count (4-7) — panel must grow to match,
        # or the last row collides with the instruction line anchored below it.
        panel_h = 220 + max(0, len(alive_roles) - 4) * 20
        panel = pygame.Rect(cx - 300, cy - panel_h // 2, 600, panel_h)
        rounded_rect(s, PANEL_BG, panel, 18)
        pygame.draw.rect(s, GOLD, panel, 2, border_radius=18)
        draw_text(s, "게임 종료!", "large", GOLD, cx, panel.y + 20, "center")
        draw_text(s, self.gs.winner_message(), "normal", WHITE, cx, panel.y + 72, "center")
        for i, (name, role, char) in enumerate(alive_roles):
            char_lbl = f" [{CHARACTERS[char].name_ko}]" if char else ""
            draw_text(s, f"{name}: {role}{char_lbl}", "small", GRAY,
                      cx, panel.y + 120 + i * 20, "center")
        draw_text(s, "[< 메뉴] 버튼으로 돌아가세요", "small", GRAY,
                  cx, panel.bottom - 20, "center")


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


def _wrap_text(text: str, fkey: str, max_w: int) -> list[str]:
    """Break text into lines that each fit within max_w pixels at font fkey."""
    f = font(fkey)
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if not cur or f.size(trial)[0] <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _build_bg_surface() -> pygame.Surface:
    """Backdrop gradient + vignette, built once and reused every frame."""
    surf = vertical_gradient(WIN_W, WIN_H, BG_TOP, BG_BOTTOM)
    surf.blit(radial_vignette(WIN_W, WIN_H, max_alpha=140), (0, 0))
    return surf


def _build_board_surface() -> pygame.Surface:
    """Wooden-rimmed felt table, built once and blitted at board position."""
    outer_w, outer_h = 560, 400
    felt_w, felt_h   = 492, 348
    core_w, core_h   = 150, 100
    pad = 36
    w, h = outer_w + pad * 2, outer_h + pad * 2
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    cx, cy = w // 2, h // 2

    # Soft contact shadow under the table
    for i in range(12, 0, -1):
        a = min(85, 7 * i)
        rect = pygame.Rect(0, 0, outer_w + i * 5, outer_h + i * 5)
        rect.center = (cx, cy + 12)
        pygame.draw.ellipse(surf, (0, 0, 0, a), rect)

    # Wooden rim — gradient bands from dark outer edge to lighter inner edge
    rim_steps = 16
    for i in range(rim_steps):
        t = i / (rim_steps - 1)
        col = tuple(int(WOOD_DRK[c] + (WOOD_LGT[c] - WOOD_DRK[c]) * t) for c in range(3))
        rw = int(outer_w + (felt_w - outer_w) * t)
        rh = int(outer_h + (felt_h - outer_h) * t)
        rect = pygame.Rect(0, 0, rw, rh)
        rect.center = (cx, cy)
        pygame.draw.ellipse(surf, col, rect)

    # Felt interior — gradient from shadowed edge to lit center
    felt_steps = 18
    for i in range(felt_steps, -1, -1):
        t = i / felt_steps
        col = tuple(int(FELT_LGT[c] + (FELT_DRK[c] - FELT_LGT[c]) * t) for c in range(3))
        rw = int(core_w + (felt_w - core_w) * t)
        rh = int(core_h + (felt_h - core_h) * t)
        rect = pygame.Rect(0, 0, rw, rh)
        rect.center = (cx, cy)
        pygame.draw.ellipse(surf, col, rect)

    # Crisp rim edge + faint inner highlight ring
    outer_rect = pygame.Rect(0, 0, outer_w, outer_h); outer_rect.center = (cx, cy)
    pygame.draw.ellipse(surf, (32, 19, 8), outer_rect, 3)
    felt_rect = pygame.Rect(0, 0, felt_w, felt_h); felt_rect.center = (cx, cy)
    pygame.draw.ellipse(surf, (96, 168, 92), felt_rect, 2)

    return surf
