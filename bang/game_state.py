"""
Bang! core game logic — full rule implementation.

Turn flow:
  DYNAMITE → JAIL → CHAR_DRAW/KIT_PEEK → DRAW → PLAY
  → RESPONSE/DUEL/GEN_STORE → DISCARD → (next turn)

Special phases:
  BEER_SAVE  – player can play Beer immediately before dying
  CHAR_DRAW  – Jesse Jones / Pedro Ramirez first-card choice
  KIT_PEEK   – Kit Carlson picks 2 of top 3
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional
import random

from cards import Card, CardType, Suit, build_deck
from roles import Role, assign_roles
from player import Player
from characters import CharacterType, CharacterInfo, CHARACTERS, assign_characters


class Phase(Enum):
    DYNAMITE   = auto()
    JAIL       = auto()
    CHAR_DRAW  = auto()   # Jesse Jones / Pedro Ramirez choose 1st draw source
    KIT_PEEK   = auto()   # Kit Carlson picks 2 of top 3
    DRAW       = auto()
    PLAY       = auto()
    RESPONSE   = auto()   # BANG / INDIANS / GATLING response
    DUEL       = auto()
    GEN_STORE  = auto()
    DISCARD    = auto()
    BEER_SAVE  = auto()   # lethal-hit Beer rescue
    GAME_OVER  = auto()


class RespType(Enum):
    BANG    = "bang"
    INDIANS = "indians"
    GATLING = "gatling"


@dataclass
class GameState:
    num_players: int
    human_ids: list[int]
    mode: str            # 'local' | 'ai'

    players: list[Player] = field(default_factory=list)
    deck: list[Card]     = field(default_factory=list)
    discard: list[Card]  = field(default_factory=list)
    gen_store_pile: list[Card] = field(default_factory=list)

    current_pid: int = 0
    phase: Phase = Phase.DRAW
    turn_num: int = 0
    bang_used: bool = False

    # ── Response context ───────────────────────────────────────────────────
    resp_type: Optional[RespType] = None
    resp_attacker: int = -1
    resp_targets: list[int] = field(default_factory=list)
    resp_current: int = -1
    barrel_checked: bool = False
    barrel_saved: bool = False
    needs_missed: bool = True
    resp_misses_needed: int = 1    # 2 when attacker is Slab the Killer
    resp_misses_played: int = 0

    # ── Duel context ───────────────────────────────────────────────────────
    duel_challenger: int = -1
    duel_other: int = -1
    duel_current: int = -1

    # ── General Store ──────────────────────────────────────────────────────
    gen_store_order: list[int] = field(default_factory=list)

    # ── Beer lethal-hit rescue ─────────────────────────────────────────────
    beer_save_pid: int = -1
    beer_save_killer: int = -1
    beer_save_resume: str = ""  # 'response', 'duel', 'dynamite', 'generic'

    # ── Character-specific draw (Jesse Jones / Pedro Ramirez) ──────────────
    char_draw_pid: int = -1
    char_draw_type: str = ""      # 'jesse' | 'pedro'
    char_draw_first_done: bool = False  # True after 1st card drawn

    # ── Kit Carlson peek ──────────────────────────────────────────────────
    kit_peek_cards: list[Card] = field(default_factory=list)
    kit_selected: list[int] = field(default_factory=list)   # indices in kit_peek_cards

    # ── Outcome ───────────────────────────────────────────────────────────
    winner_role: Optional[Role] = None
    log: list[str] = field(default_factory=list)

    # ═════════════════════════════════════════════════════════════════════
    # Factory
    # ═════════════════════════════════════════════════════════════════════
    @classmethod
    def new_game(cls, num_players: int, human_ids: list[int], mode: str,
                 names: list[str]) -> "GameState":
        roles  = assign_roles(num_players)
        chars  = assign_characters(num_players)
        players = []
        for i, (name, role, char_type) in enumerate(zip(names, roles, chars)):
            info    = CHARACTERS[char_type]
            max_hp  = info.base_hp + (1 if role == Role.SHERIFF else 0)
            p = Player(pid=i, name=name, role=role,
                       is_human=i in human_ids,
                       character=char_type,
                       max_hp=max_hp, hp=max_hp)
            if role == Role.SHERIFF:
                p.role_revealed = True
            players.append(p)

        deck = build_deck()
        for p in players:
            for _ in range(p.max_hp):
                if deck:
                    p.hand.append(deck.pop())

        gs = cls(num_players=num_players, human_ids=human_ids, mode=mode)
        gs.players  = players
        gs.deck     = deck
        gs.current_pid = 0
        gs._enter_turn_start()
        return gs

    # ═════════════════════════════════════════════════════════════════════
    # Deck helpers
    # ═════════════════════════════════════════════════════════════════════
    def _draw(self) -> Optional[Card]:
        if not self.deck:
            if len(self.discard) <= 1:
                return None
            top = self.discard.pop()
            self.deck = self.discard
            self.discard = [top]
            random.shuffle(self.deck)
        return self.deck.pop() if self.deck else None

    def _flip(self, pid: int = -1) -> Optional[Card]:
        """
        Flip top card for draw! checks (barrel, jail, dynamite).
        Lucky Duke flips 2 and the caller picks the better one.
        Returns the card that 'counts' for the check.
        """
        c1 = self._flip_single()
        if pid >= 0 and self.players[pid].is_lucky_duke():
            c2 = self._flip_single()
            if c2 is not None:
                chosen = self._lucky_duke_pick(c1, c2)
                other  = c2 if chosen is c1 else c1
                self.log_msg(f"🎲 럭키 듀크: {c1} | {c2} → {chosen} 선택")
                # Put the unchosen in discard (already there via _flip_single)
                return chosen
        return c1

    def _flip_single(self) -> Optional[Card]:
        c = self._draw()
        if c:
            self.discard.append(c)
        return c

    @staticmethod
    def _lucky_duke_pick(c1: Optional[Card], c2: Optional[Card]) -> Optional[Card]:
        """Pick the 'better' card for Lucky Duke — context-agnostic, prefer Heart."""
        if c1 is None:
            return c2
        if c2 is None:
            return c1
        # Prefer Heart (good for barrel/jail), avoid 2-9♠ (bad for dynamite)
        def score(c: Card) -> int:
            if c.suit == Suit.HEARTS:
                return 2
            if c.suit == Suit.SPADES and 2 <= c.value <= 9:
                return 0
            return 1
        return c1 if score(c1) >= score(c2) else c2

    @staticmethod
    def _is_heart(c: Optional[Card]) -> bool:
        return c is not None and c.suit == Suit.HEARTS

    @staticmethod
    def _is_dynamite_explode(c: Optional[Card]) -> bool:
        return c is not None and c.suit == Suit.SPADES and 2 <= c.value <= 9

    # ═════════════════════════════════════════════════════════════════════
    # Logging
    # ═════════════════════════════════════════════════════════════════════
    def log_msg(self, msg: str):
        self.log.append(msg)
        if len(self.log) > 80:
            self.log.pop(0)

    # ═════════════════════════════════════════════════════════════════════
    # Distance / targeting
    # ═════════════════════════════════════════════════════════════════════
    def _alive_ids(self) -> list[int]:
        return [p.pid for p in self.players if p.alive]

    def distance(self, from_id: int, to_id: int) -> int:
        alive = self._alive_ids()
        if to_id not in alive or from_id not in alive:
            return 999
        n  = len(alive)
        fi = alive.index(from_id)
        ti = alive.index(to_id)
        d  = min((ti - fi) % n, (fi - ti) % n)
        if self.players[from_id].has_scope():
            d -= 1
        if self.players[to_id].has_mustang():
            d += 1
        return max(1, d)

    def can_shoot(self, from_id: int, to_id: int) -> bool:
        return self.distance(from_id, to_id) <= self.players[from_id].gun_range()

    def valid_bang_targets(self, pid: int) -> list[int]:
        return [i for i in self._alive_ids() if i != pid and self.can_shoot(pid, i)]

    def valid_panic_targets(self, pid: int) -> list[int]:
        return [i for i in self._alive_ids()
                if i != pid and self.distance(pid, i) == 1 and self.players[i].all_cards()]

    def valid_jail_targets(self, pid: int) -> list[int]:
        return [i for i in self._alive_ids()
                if i != pid
                and self.players[i].role != Role.SHERIFF
                and not self.players[i].jailed]

    # ═════════════════════════════════════════════════════════════════════
    # Turn flow
    # ═════════════════════════════════════════════════════════════════════
    def _enter_turn_start(self):
        p = self.players[self.current_pid]
        if p.has_dynamite():
            self.phase = Phase.DYNAMITE
        elif p.jailed:
            self.phase = Phase.JAIL
        else:
            self._enter_draw_phase()

    def _enter_draw_phase(self):
        pid = self.current_pid
        ct  = self.players[pid].character
        if ct == CharacterType.KIT_CARLSON:
            self._start_kit_peek()
        elif ct in (CharacterType.JESSE_JONES, CharacterType.PEDRO_RAMIREZ):
            self.char_draw_pid  = pid
            self.char_draw_type = "jesse" if ct == CharacterType.JESSE_JONES else "pedro"
            self.char_draw_first_done = False
            self.phase = Phase.CHAR_DRAW
        else:
            self.phase = Phase.DRAW

    # ── Dynamite ──────────────────────────────────────────────────────────
    def resolve_dynamite(self) -> dict:
        p       = self.players[self.current_pid]
        dyn     = p.get_dynamite()
        flipped = self._flip(self.current_pid)
        exploded = self._is_dynamite_explode(flipped)
        if exploded:
            p.remove_equipment(dyn)
            self.discard.append(dyn)
            self.log_msg(f"💥 {p.name} 다이너마이트 폭발! -3HP")
            died = p.take_damage(3)
            self._trigger_damage_reactions(self.current_pid, -1, 3)
            if died:
                self._handle_death(self.current_pid, -1, "dynamite")
                return {"flipped": flipped, "exploded": True}
        else:
            p.remove_equipment(dyn)
            nxt = self._next_alive(self.current_pid)
            self.players[nxt].equip(dyn)
            self.log_msg(f"🧨 다이너마이트 → {self.players[nxt].name}에게 전달")

        if self.phase == Phase.GAME_OVER:
            return {"flipped": flipped, "exploded": exploded}

        if self.players[self.current_pid].alive and self.players[self.current_pid].jailed:
            self.phase = Phase.JAIL
        elif self.players[self.current_pid].alive:
            self._enter_draw_phase()
        return {"flipped": flipped, "exploded": exploded}

    # ── Jail ──────────────────────────────────────────────────────────────
    def resolve_jail(self) -> dict:
        p       = self.players[self.current_pid]
        flipped = self._flip(self.current_pid)
        escaped = self._is_heart(flipped)
        jail_c  = p.jail_card
        p.jailed    = False
        p.jail_card = None
        if jail_c and jail_c in p.equipment:
            p.remove_equipment(jail_c)
            self.discard.append(jail_c)
        if escaped:
            self.log_msg(f"🔓 {p.name} 감옥 탈출!")
            self._enter_draw_phase()
        else:
            self.log_msg(f"🔒 {p.name} 감옥에서 턴 스킵")
            self._advance_turn()
        return {"flipped": flipped, "escaped": escaped}

    # ── Character special draw ─────────────────────────────────────────────
    def _start_kit_peek(self):
        self.kit_peek_cards = []
        self.kit_selected   = []
        for _ in range(3):
            c = self._draw()
            if c:
                self.kit_peek_cards.append(c)
        self.log_msg(f"🔍 킷 칼슨: 상위 {len(self.kit_peek_cards)}장 공개")
        self.phase = Phase.KIT_PEEK

    def kit_carlson_pick(self, card_idx: int) -> bool:
        if card_idx < 0 or card_idx >= len(self.kit_peek_cards):
            return False
        if card_idx in self.kit_selected:
            return False
        self.kit_selected.append(card_idx)
        if len(self.kit_selected) == 2:
            p = self.players[self.current_pid]
            for i in self.kit_selected:
                p.hand.append(self.kit_peek_cards[i])
            leftover = [c for i, c in enumerate(self.kit_peek_cards)
                        if i not in self.kit_selected]
            if leftover:
                self.deck.append(leftover[0])   # put back on top
            self.kit_peek_cards = []
            self.kit_selected   = []
            self.bang_used = False
            self.phase = Phase.PLAY
        return True

    # Jesse Jones / Pedro Ramirez
    def char_draw_from_deck(self) -> bool:
        """Draw 1st card from deck (Jesse Jones / Pedro Ramirez option)."""
        if self.phase != Phase.CHAR_DRAW or self.char_draw_first_done:
            return False
        c = self._draw()
        if c:
            self.players[self.char_draw_pid].hand.append(c)
        self.char_draw_first_done = True
        self._finish_char_draw()
        return True

    def char_draw_from_player(self, target_pid: int) -> bool:
        """Jesse Jones: steal first card from target's hand."""
        if self.phase != Phase.CHAR_DRAW or self.char_draw_type != "jesse":
            return False
        if self.char_draw_first_done:
            return False
        target = self.players[target_pid]
        if not target.hand or not target.alive:
            return False
        stolen = random.choice(target.hand)
        target.hand.remove(stolen)
        self.players[self.char_draw_pid].hand.append(stolen)
        self.log_msg(f"🤠 제시 존스: {target.name}에게서 [{stolen.name}] 가져옴")
        self.char_draw_first_done = True
        self._finish_char_draw()
        return True

    def char_draw_from_discard(self) -> bool:
        """Pedro Ramirez: draw first card from discard pile."""
        if self.phase != Phase.CHAR_DRAW or self.char_draw_type != "pedro":
            return False
        if self.char_draw_first_done:
            return False
        if not self.discard:
            return self.char_draw_from_deck()
        c = self.discard.pop()
        self.players[self.char_draw_pid].hand.append(c)
        self.log_msg(f"🤠 페드로 라미레즈: 버림더미에서 [{c.name}] 가져옴")
        self.char_draw_first_done = True
        self._finish_char_draw()
        return True

    def _finish_char_draw(self):
        """Draw 2nd card from deck and start play phase."""
        c = self._draw()
        if c:
            self.players[self.char_draw_pid].hand.append(c)
        self.char_draw_pid  = -1
        self.char_draw_type = ""
        self.char_draw_first_done = False
        self.bang_used = False
        self.phase = Phase.PLAY

    # ── Normal draw ───────────────────────────────────────────────────────
    def do_draw(self):
        p  = self.players[self.current_pid]
        ct = p.character

        # Black Jack: reveal 2nd card; if red suit draw an extra card
        if ct == CharacterType.BLACK_JACK:
            c1 = self._draw()
            c2 = self._draw()
            if c1: p.hand.append(c1)
            if c2:
                p.hand.append(c2)
                is_red = c2.suit in (Suit.HEARTS, Suit.DIAMONDS)
                self.log_msg(f"🃏 블랙 잭: 2번째 카드 {c2} {'→ 빨간 무늬! +1장 추가' if is_red else ''}")
                if is_red:
                    c3 = self._draw()
                    if c3:
                        p.hand.append(c3)
        else:
            for _ in range(2):
                c = self._draw()
                if c:
                    p.hand.append(c)
            self.log_msg(f"📥 {p.name} 카드 2장 드로우")

        self.bang_used = False
        self.phase = Phase.PLAY

    # ═════════════════════════════════════════════════════════════════════
    # Playing cards (PLAY phase)
    # ═════════════════════════════════════════════════════════════════════
    def play_card(self, pid: int, card_idx: int, target_id: int = -1,
                  target_card_idx: int = -1) -> bool:
        p = self.players[pid]
        if card_idx < 0 or card_idx >= len(p.hand):
            return False
        card = p.hand[card_idx]
        ct   = card.card_type

        # Calamity Janet: Missed! can be used as BANG!
        if ct == CardType.MISSED and p.is_calamity_janet():
            return self._play_bang(pid, card_idx, target_id, as_missed=True)

        if ct == CardType.BANG:
            return self._play_bang(pid, card_idx, target_id)
        if ct == CardType.BEER:
            return self._play_beer(pid, card_idx)
        if ct == CardType.STAGECOACH:
            return self._play_draw_cards(pid, card_idx, 2, "역마차")
        if ct == CardType.WELLS_FARGO:
            return self._play_draw_cards(pid, card_idx, 3, "웰스 파고")
        if ct == CardType.CAT_BALOU:
            return self._play_cat_balou(pid, card_idx, target_id, target_card_idx)
        if ct == CardType.PANIC:
            return self._play_panic(pid, card_idx, target_id, target_card_idx)
        if ct == CardType.INDIANS:
            return self._play_indians(pid, card_idx)
        if ct == CardType.GATLING:
            return self._play_gatling(pid, card_idx)
        if ct == CardType.SALOON:
            return self._play_saloon(pid, card_idx)
        if ct == CardType.GEN_STORE:
            return self._play_gen_store(pid, card_idx)
        if ct == CardType.DUEL:
            return self._play_duel(pid, card_idx, target_id)
        if card.is_blue:
            return self._play_equipment(pid, card_idx, target_id)
        return False

    def _discard_from_hand(self, pid: int, card_idx: int) -> Card:
        card = self.players[pid].hand.pop(card_idx)
        self.discard.append(card)
        self._check_suzy_lafayette(pid)
        return card

    def _play_bang(self, pid: int, card_idx: int, target_id: int,
                   as_missed: bool = False) -> bool:
        p = self.players[pid]
        if not p.has_volcanic() and self.bang_used:
            return False
        if target_id < 0 or not self.players[target_id].alive:
            return False
        if not self.can_shoot(pid, target_id):
            return False

        self._discard_from_hand(pid, card_idx)
        if not p.has_volcanic():
            self.bang_used = True
        label = "Missed!(뱅)" if as_missed else "BANG!"
        self.log_msg(f"🔫 {p.name} → {self.players[target_id].name} {label}")
        self._start_bang_response(pid, target_id)
        return True

    def _play_beer(self, pid: int, card_idx: int) -> bool:
        if len(self._alive_ids()) <= 2:
            return False
        p = self.players[pid]
        if p.hp >= p.max_hp:
            return False
        self._discard_from_hand(pid, card_idx)
        p.heal(1)
        self.log_msg(f"🍺 {p.name} HP +1 ({p.hp}/{p.max_hp})")
        return True

    def _play_draw_cards(self, pid: int, card_idx: int, n: int, label: str) -> bool:
        self._discard_from_hand(pid, card_idx)
        p = self.players[pid]
        for _ in range(n):
            c = self._draw()
            if c:
                p.hand.append(c)
        self.log_msg(f"📦 {p.name} {label} → +{n}장")
        return True

    def _play_cat_balou(self, pid, card_idx, target_id, target_card_idx) -> bool:
        if target_id < 0 or not self.players[target_id].alive:
            return False
        target = self.players[target_id]
        all_c  = target.all_cards()
        if not all_c:
            return False
        if target_card_idx < 0 or target_card_idx >= len(all_c):
            target_card_idx = random.randint(0, len(all_c) - 1)
        chosen = all_c[target_card_idx]
        self._discard_from_hand(pid, card_idx)
        self._remove_card_from_player(target, chosen)
        self.discard.append(chosen)
        self.log_msg(f"🃏 캣 발루: {self.players[pid].name} → {target.name} [{chosen.name}] 버림")
        return True

    def _play_panic(self, pid, card_idx, target_id, target_card_idx) -> bool:
        if target_id < 0 or not self.players[target_id].alive:
            return False
        if self.distance(pid, target_id) != 1:
            return False
        target = self.players[target_id]
        all_c  = target.all_cards()
        if not all_c:
            return False
        if target_card_idx < 0 or target_card_idx >= len(all_c):
            target_card_idx = random.randint(0, len(all_c) - 1)
        chosen = all_c[target_card_idx]
        self._discard_from_hand(pid, card_idx)
        self._remove_card_from_player(target, chosen)
        self.players[pid].hand.append(chosen)
        self.log_msg(f"😱 패닉: {self.players[pid].name} → {target.name} [{chosen.name}] 훔침")
        return True

    def _remove_card_from_player(self, player: Player, card: Card):
        if card in player.hand:
            player.hand.remove(card)
        elif card in player.equipment:
            player.equipment.remove(card)
        elif card == player.jail_card:
            player.jailed    = False
            player.jail_card = None

    def _play_indians(self, pid, card_idx) -> bool:
        self._discard_from_hand(pid, card_idx)
        self.log_msg(f"🪃 인디언: {self.players[pid].name} → 전원 BANG! 필요")
        targets = [i for i in self._alive_ids() if i != pid]
        self._start_group_response(RespType.INDIANS, pid, targets)
        return True

    def _play_gatling(self, pid, card_idx) -> bool:
        self._discard_from_hand(pid, card_idx)
        self.log_msg(f"🔫🔫 개틀링: {self.players[pid].name} → 전원 Missed! 필요")
        targets = [i for i in self._alive_ids() if i != pid]
        self._start_group_response(RespType.GATLING, pid, targets)
        return True

    def _play_saloon(self, pid, card_idx) -> bool:
        self._discard_from_hand(pid, card_idx)
        for p in self.players:
            if p.alive:
                p.heal(1)
        self.log_msg("🥃 살롱: 전원 HP +1")
        return True

    def _play_gen_store(self, pid, card_idx) -> bool:
        self._discard_from_hand(pid, card_idx)
        alive = self._alive_ids()
        self.gen_store_pile = []
        for _ in range(len(alive)):
            c = self._draw()
            if c:
                self.gen_store_pile.append(c)
        ci = alive.index(pid)
        self.gen_store_order = alive[ci:] + alive[:ci]
        self.log_msg(f"🏪 잡화점: {len(self.gen_store_pile)}장 공개")
        self.phase = Phase.GEN_STORE
        return True

    def gen_store_pick(self, pid: int, card_idx: int) -> bool:
        if self.phase != Phase.GEN_STORE:
            return False
        if not self.gen_store_order or self.gen_store_order[0] != pid:
            return False
        if card_idx < 0 or card_idx >= len(self.gen_store_pile):
            return False
        card = self.gen_store_pile.pop(card_idx)
        self.players[pid].hand.append(card)
        self.gen_store_order.pop(0)
        self.log_msg(f"  {self.players[pid].name} → [{card.name}] 선택")
        if not self.gen_store_order:
            self.discard.extend(self.gen_store_pile)
            self.gen_store_pile = []
            self.phase = Phase.PLAY
        return True

    def _play_duel(self, pid, card_idx, target_id) -> bool:
        if target_id < 0 or not self.players[target_id].alive:
            return False
        self._discard_from_hand(pid, card_idx)
        self.duel_challenger = pid
        self.duel_other      = target_id
        self.duel_current    = target_id
        self.log_msg(f"⚔️ 결투: {self.players[pid].name} vs {self.players[target_id].name}")
        self.phase = Phase.DUEL
        return True

    def _play_equipment(self, pid, card_idx, target_id=-1) -> bool:
        p    = self.players[pid]
        card = p.hand[card_idx]
        if card.card_type == CardType.JAIL:
            if target_id < 0 or target_id not in self.valid_jail_targets(pid):
                return False
            p.hand.pop(card_idx)
            target = self.players[target_id]
            target.equip(card)
            target.jailed    = True
            target.jail_card = card
            self.log_msg(f"🔒 감옥: {p.name} → {target.name}")
            return True
        p.hand.pop(card_idx)
        p.equip(card)
        self.log_msg(f"🔧 {p.name} [{card.name}] 장착")
        return True

    # ── Sid Ketchum active ability ─────────────────────────────────────────
    def use_sid_ketchum(self, pid: int, idx1: int, idx2: int) -> bool:
        """Discard 2 cards to gain 1 HP. Valid only during own PLAY phase."""
        from characters import CharacterType as CT
        p = self.players[pid]
        if p.character != CT.SID_KETCHUM:
            return False
        if self.phase != Phase.PLAY or self.current_pid != pid:
            return False
        if p.hp >= p.max_hp:
            return False
        hi, lo = max(idx1, idx2), min(idx1, idx2)
        if hi >= len(p.hand) or lo < 0 or hi == lo:
            return False
        p.hand.pop(hi)
        p.hand.pop(lo)
        self.discard.extend(p.hand[lo:lo])  # already popped
        p.heal(1)
        self.log_msg(f"💊 {p.name} 시드 케첨 능력: +1HP ({p.hp}/{p.max_hp})")
        self._check_suzy_lafayette(pid)
        return True

    # ═════════════════════════════════════════════════════════════════════
    # Response system
    # ═════════════════════════════════════════════════════════════════════
    def _start_bang_response(self, attacker: int, target: int):
        self.resp_type        = RespType.BANG
        self.resp_attacker    = attacker
        self.resp_targets     = [target]
        self.resp_current     = target
        self.barrel_checked   = False
        self.barrel_saved     = False
        self.needs_missed     = True
        # Slab the Killer: target needs 2 Missed!
        self.resp_misses_needed = 2 if self.players[attacker].is_slab_killer() else 1
        self.resp_misses_played = 0
        self.phase = Phase.RESPONSE

    def _start_group_response(self, rtype: RespType, attacker: int, targets: list[int]):
        self.resp_type    = rtype
        self.resp_attacker = attacker
        self.resp_targets  = list(targets)
        self.resp_misses_needed = 1
        self.resp_misses_played = 0
        self._next_responder()

    def _next_responder(self):
        while self.resp_targets:
            self.resp_current = self.resp_targets[0]
            p = self.players[self.resp_current]
            if not p.alive:
                self.resp_targets.pop(0)
                continue
            self.barrel_checked   = False
            self.barrel_saved     = False
            self.needs_missed     = True
            self.resp_misses_played = 0
            self.phase = Phase.RESPONSE
            return
        self.phase = Phase.PLAY

    def check_barrel(self) -> bool:
        p = self.players[self.resp_current]
        if not p.has_barrel() or self.barrel_checked:
            return False
        self.barrel_checked = True
        flipped = self._flip(self.resp_current)
        saved   = self._is_heart(flipped)
        self.barrel_saved = saved
        if saved:
            self.needs_missed = False
            self.log_msg(f"🛢️ {p.name} 나무통 발동! ({flipped}) → 회피")
        else:
            self.log_msg(f"🛢️ {p.name} 나무통 실패 ({flipped})")
        return saved

    def respond_with_missed(self, card_idx: int) -> bool:
        pid  = self.resp_current
        p    = self.players[pid]
        if card_idx < 0 or card_idx >= len(p.hand):
            return False
        card = p.hand[card_idx]

        # Valid response cards depend on resp_type and Calamity Janet
        need_bang   = self.resp_type == RespType.INDIANS
        janet       = p.is_calamity_janet()
        valid_bang  = card.card_type == CardType.BANG or (janet and card.card_type == CardType.MISSED)
        valid_miss  = card.card_type == CardType.MISSED or (janet and card.card_type == CardType.BANG)

        if need_bang and not valid_bang:
            return False
        if not need_bang and not valid_miss:
            return False

        p.hand.pop(card_idx)
        self.discard.append(card)
        self._check_suzy_lafayette(pid)
        self.resp_misses_played += 1
        self.log_msg(f"✋ {p.name} [{card.name}] 사용 ({self.resp_misses_played}/{self.resp_misses_needed})")

        if self.resp_misses_played >= self.resp_misses_needed:
            self._finish_response(hit=False)
        # else: need more Missed! (Slab the Killer) — stay in RESPONSE phase
        return True

    def respond_take_hit(self):
        pid = self.resp_current
        p   = self.players[pid]
        self.log_msg(f"💥 {p.name} 피격! -1HP")
        died = p.take_damage(1)
        self._trigger_damage_reactions(pid, self.resp_attacker, 1)
        if died:
            self._handle_death(pid, self.resp_attacker, "response")
        else:
            self._finish_response(hit=True)

    def _finish_response(self, hit: bool):
        if self.resp_type == RespType.BANG:
            self.resp_targets.clear()
            self.phase = Phase.PLAY
        else:
            if self.resp_targets:
                self.resp_targets.pop(0)
            self._next_responder()

    # ═════════════════════════════════════════════════════════════════════
    # Duel
    # ═════════════════════════════════════════════════════════════════════
    def duel_play_bang(self, card_idx: int) -> bool:
        pid  = self.duel_current
        p    = self.players[pid]
        if card_idx < 0 or card_idx >= len(p.hand):
            return False
        card  = p.hand[card_idx]
        janet = p.is_calamity_janet()
        valid = card.card_type == CardType.BANG or (janet and card.card_type == CardType.MISSED)
        if not valid:
            return False
        p.hand.pop(card_idx)
        self.discard.append(card)
        self._check_suzy_lafayette(pid)
        self.log_msg(f"⚔️ {p.name} [{card.name}] →")
        self.duel_current = (self.duel_challenger
                             if self.duel_current == self.duel_other
                             else self.duel_other)
        return True

    def duel_take_hit(self):
        pid  = self.duel_current
        p    = self.players[pid]
        killer = self.duel_challenger if pid == self.duel_other else self.duel_other
        self.log_msg(f"⚔️ {p.name} 결투 패배! -1HP")
        died = p.take_damage(1)
        self._trigger_damage_reactions(pid, killer, 1)
        self.duel_challenger = self.duel_other = self.duel_current = -1
        if died:
            self._handle_death(pid, killer, "duel")
        elif self.phase != Phase.GAME_OVER:
            self.phase = Phase.PLAY

    # ═════════════════════════════════════════════════════════════════════
    # Beer lethal-hit rescue
    # ═════════════════════════════════════════════════════════════════════
    def _handle_death(self, pid: int, killer_id: int, resume: str):
        """Check Beer save before eliminating."""
        p = self.players[pid]
        alive_count = len(self._alive_ids())  # pid still counts as alive here
        has_beer = any(c.card_type == CardType.BEER for c in p.hand)
        if has_beer and alive_count > 2:
            self.beer_save_pid    = pid
            self.beer_save_killer = killer_id
            self.beer_save_resume = resume
            self.phase = Phase.BEER_SAVE
        else:
            self._eliminate(pid, killer_id)
            if self.phase != Phase.GAME_OVER:
                self._resume_after_death(resume)

    def beer_save_use(self) -> bool:
        pid = self.beer_save_pid
        p   = self.players[pid]
        beer_idx = next((i for i, c in enumerate(p.hand)
                         if c.card_type == CardType.BEER), -1)
        if beer_idx == -1:
            return False
        beer = p.hand.pop(beer_idx)
        self.discard.append(beer)
        p.hp = 1
        self.log_msg(f"🍺 {p.name} 맥주로 생존! HP 1/{p.max_hp}")
        self._check_suzy_lafayette(pid)
        resume = self.beer_save_resume
        self.beer_save_pid    = -1
        self.beer_save_killer = -1
        self.beer_save_resume = ""
        self._resume_after_death(resume)
        return True

    def beer_save_decline(self):
        pid    = self.beer_save_pid
        killer = self.beer_save_killer
        resume = self.beer_save_resume
        self.beer_save_pid    = -1
        self.beer_save_killer = -1
        self.beer_save_resume = ""
        self._eliminate(pid, killer)
        if self.phase != Phase.GAME_OVER:
            self._resume_after_death(resume)

    def _resume_after_death(self, resume: str):
        if resume == "response":
            self._finish_response(hit=True)
        elif resume == "duel":
            self.duel_challenger = self.duel_other = self.duel_current = -1
            if self.players[self.current_pid].alive:
                self.phase = Phase.PLAY
            else:
                self._advance_turn()
        elif resume == "dynamite":
            if self.players[self.current_pid].alive:
                self._enter_draw_phase()
            else:
                self._advance_turn()
        else:
            self.phase = Phase.PLAY

    # ═════════════════════════════════════════════════════════════════════
    # Character-triggered reactions
    # ═════════════════════════════════════════════════════════════════════
    def _trigger_damage_reactions(self, pid: int, attacker_id: int, amount: int):
        p  = self.players[pid]
        ct = p.character

        # Bart Cassidy: draw card per HP lost
        if ct == CharacterType.BART_CASSIDY and p.alive:
            for _ in range(amount):
                c = self._draw()
                if c:
                    p.hand.append(c)
            self.log_msg(f"🤠 바트 카시디: +{amount}장 드로우")

        # El Gringo: steal 1 card per HP lost from attacker
        if ct == CharacterType.EL_GRINGO and p.alive and attacker_id >= 0:
            attacker = self.players[attacker_id]
            if attacker.hand:
                for _ in range(amount):
                    if not attacker.hand:
                        break
                    stolen = random.choice(attacker.hand)
                    attacker.hand.remove(stolen)
                    p.hand.append(stolen)
                self.log_msg(f"🤠 엘 그링고: {attacker.name}에게서 {amount}장 훔침")

    def _check_suzy_lafayette(self, pid: int):
        p = self.players[pid]
        if p.character == CharacterType.SUZY_LAFAYETTE and p.alive and len(p.hand) == 0:
            c = self._draw()
            if c:
                p.hand.append(c)
                self.log_msg(f"🤠 수지 라파예트: 손패 없음 → 카드 1장 드로우 [{c.name}]")

    # ═════════════════════════════════════════════════════════════════════
    # Elimination & win
    # ═════════════════════════════════════════════════════════════════════
    def _eliminate(self, pid: int, killer_id: int):
        p       = self.players[pid]
        p.alive = False
        p.role_revealed = True
        self.log_msg(f"💀 {p.name} 탈락! 역할: {p.role.value}")

        # Vulture Sam: gets ALL cards from eliminated player
        vulture = next((pl for pl in self.players
                        if pl.alive and pl.character == CharacterType.VULTURE_SAM
                        and pl.pid != pid), None)
        if vulture:
            vulture.hand.extend(p.hand)
            vulture.hand.extend(p.equipment)
            self.log_msg(f"🦅 벌처 샘: {p.name}의 카드 전부 획득")
        else:
            # Outlaw kill bonus for the killer
            if p.role == Role.OUTLAW and killer_id >= 0 and self.players[killer_id].alive:
                for _ in range(3):
                    c = self._draw()
                    if c:
                        self.players[killer_id].hand.append(c)
                self.log_msg(f"🎁 {self.players[killer_id].name} 무법자 처치 보너스 +3장")
            self.discard.extend(p.hand)
            self.discard.extend(p.equipment)

        # Sheriff kills Deputy penalty
        if p.role == Role.DEPUTY and killer_id >= 0:
            if self.players[killer_id].role == Role.SHERIFF:
                self.players[killer_id].hand.clear()
                self.players[killer_id].equipment.clear()
                self.log_msg("⚠️ 보안관이 부관을 처치 → 패 전부 버림!")

        p.hand.clear()
        p.equipment.clear()
        if p.jail_card:
            self.discard.append(p.jail_card)
            p.jail_card = None

        winner = self._check_win()
        if winner is not None:
            self.winner_role = winner
            self.phase = Phase.GAME_OVER

    def _check_win(self) -> Optional[Role]:
        alive           = [(i, p) for i, p in enumerate(self.players) if p.alive]
        sheriff_alive   = any(p.role == Role.SHERIFF   for _, p in alive)
        outlaws_alive   = any(p.role == Role.OUTLAW    for _, p in alive)
        renegades_alive = any(p.role == Role.RENEGADE  for _, p in alive)

        if not sheriff_alive:
            if len(alive) == 1 and renegades_alive:
                return Role.RENEGADE
            return Role.OUTLAW
        if not outlaws_alive and not renegades_alive:
            return Role.SHERIFF
        return None

    # ═════════════════════════════════════════════════════════════════════
    # End-of-turn discard
    # ═════════════════════════════════════════════════════════════════════
    def enter_discard_phase(self):
        p = self.players[self.current_pid]
        if len(p.hand) > p.hand_limit():
            self.phase = Phase.DISCARD
        else:
            self._advance_turn()

    def discard_card(self, card_idx: int) -> bool:
        p = self.players[self.current_pid]
        if card_idx < 0 or card_idx >= len(p.hand):
            return False
        card = p.hand.pop(card_idx)
        self.discard.append(card)
        self._check_suzy_lafayette(self.current_pid)
        if len(p.hand) <= p.hand_limit():
            self._advance_turn()
        return True

    # ═════════════════════════════════════════════════════════════════════
    # Turn advance
    # ═════════════════════════════════════════════════════════════════════
    def _next_alive(self, from_pid: int) -> int:
        alive = self._alive_ids()
        if not alive:
            return from_pid
        ci = alive.index(from_pid) if from_pid in alive else 0
        return alive[(ci + 1) % len(alive)]

    def _advance_turn(self):
        self.turn_num  += 1
        self.current_pid = self._next_alive(self.current_pid)
        self._enter_turn_start()

    # ═════════════════════════════════════════════════════════════════════
    # Convenience queries
    # ═════════════════════════════════════════════════════════════════════
    def current_player(self) -> Player:
        return self.players[self.current_pid]

    def cards_needing_target(self, card: Card) -> bool:
        return card.card_type in {
            CardType.BANG, CardType.CAT_BALOU, CardType.PANIC,
            CardType.DUEL, CardType.JAIL,
        } or (card.card_type == CardType.MISSED
              and self.players[self.current_pid].is_calamity_janet())

    def valid_targets_for_card(self, pid: int, card: Card) -> list[int]:
        ct = card.card_type
        # Calamity Janet uses Missed! as BANG!
        if ct == CardType.MISSED and self.players[pid].is_calamity_janet():
            ct = CardType.BANG
        if ct == CardType.BANG:
            return self.valid_bang_targets(pid)
        if ct == CardType.CAT_BALOU:
            return [i for i in self._alive_ids()
                    if i != pid and self.players[i].all_cards()]
        if ct == CardType.PANIC:
            return self.valid_panic_targets(pid)
        if ct == CardType.DUEL:
            return [i for i in self._alive_ids() if i != pid]
        if ct == CardType.JAIL:
            return self.valid_jail_targets(pid)
        return []

    def can_play_card(self, pid: int, card_idx: int) -> bool:
        p = self.players[pid]
        if card_idx >= len(p.hand):
            return False
        card = p.hand[card_idx]
        ct   = card.card_type

        # Calamity Janet can use Missed! as BANG!
        if ct == CardType.MISSED and p.is_calamity_janet():
            if p.has_volcanic() or not self.bang_used:
                return bool(self.valid_bang_targets(pid))
            return False

        if ct == CardType.MISSED:
            return False
        if ct == CardType.BANG:
            if not p.has_volcanic() and self.bang_used:
                return False
            return bool(self.valid_bang_targets(pid))
        if ct == CardType.BEER:
            return p.hp < p.max_hp and len(self._alive_ids()) > 2
        if ct == CardType.BARREL:
            return not any(c.card_type == CardType.BARREL for c in p.equipment)
        if ct == CardType.SCOPE:
            return not any(c.card_type == CardType.SCOPE for c in p.equipment)
        if ct == CardType.MUSTANG:
            return not any(c.card_type == CardType.MUSTANG for c in p.equipment)
        if ct == CardType.DYNAMITE:
            return not p.has_dynamite()
        if card.is_gun:
            return True
        if self.cards_needing_target(card):
            return bool(self.valid_targets_for_card(pid, card))
        return True

    def winner_message(self) -> str:
        if self.winner_role == Role.SHERIFF:
            return "보안관 & 부관 승리! 무법자와 배신자를 처치했습니다."
        if self.winner_role == Role.OUTLAW:
            return "무법자 승리! 보안관을 처치했습니다!"
        if self.winner_role == Role.RENEGADE:
            return "배신자 승리! 마지막 생존자가 되었습니다!"
        return "게임 종료"
