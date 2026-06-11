"""
Core game logic for Bang!
State machine phases:
  TURN_START → DYNAMITE → JAIL → DRAW → PLAY → RESPONSE → DISCARD → TURN_START
  RESPONSE subtypes: bang / indians / gatling / duel
  GEN_STORE is handled inside PLAY
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional
import random

from cards import Card, CardType, Suit, build_deck
from roles import Role, assign_roles
from player import Player


class Phase(Enum):
    DYNAMITE   = auto()
    JAIL       = auto()
    DRAW       = auto()
    PLAY       = auto()
    RESPONSE   = auto()   # BANG / INDIANS / GATLING
    DUEL       = auto()
    GEN_STORE  = auto()
    DISCARD    = auto()
    GAME_OVER  = auto()


class RespType(Enum):
    BANG    = "bang"
    INDIANS = "indians"
    GATLING = "gatling"


@dataclass
class GameState:
    num_players: int
    human_ids: list[int]        # indices of human players
    mode: str                   # 'local' | 'ai'

    players: list[Player] = field(default_factory=list)
    deck: list[Card]     = field(default_factory=list)
    discard: list[Card]  = field(default_factory=list)
    gen_store_pile: list[Card] = field(default_factory=list)

    current_pid: int = 0
    phase: Phase = Phase.DRAW
    turn_num: int = 0
    bang_used: bool = False       # has current player used BANG! this turn

    # ── Response context ───────────────────────────────────────────────────
    resp_type: Optional[RespType] = None
    resp_attacker: int = -1
    resp_targets: list[int] = field(default_factory=list)   # queue of pending responders
    resp_current: int = -1
    # barrel check state
    barrel_checked: bool = False
    barrel_saved: bool = False
    # after barrel, still needs missed?
    needs_missed: bool = True

    # ── Duel context ───────────────────────────────────────────────────────
    duel_challenger: int = -1
    duel_other: int = -1
    duel_current: int = -1

    # ── General Store context ──────────────────────────────────────────────
    gen_store_order: list[int] = field(default_factory=list)

    # ── Outcome ───────────────────────────────────────────────────────────
    winner_role: Optional[Role] = None
    log: list[str] = field(default_factory=list)

    # ─────────────────────────────────────────────────────────────────────
    # Factory
    # ─────────────────────────────────────────────────────────────────────
    @classmethod
    def new_game(cls, num_players: int, human_ids: list[int], mode: str,
                 names: list[str]) -> "GameState":
        roles = assign_roles(num_players)
        players = []
        for i, (name, role) in enumerate(zip(names, roles)):
            is_human = i in human_ids
            max_hp = 5 if role == Role.SHERIFF else 4
            p = Player(pid=i, name=name, role=role, is_human=is_human,
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
        gs.players = players
        gs.deck = deck
        gs.current_pid = 0  # sheriff goes first
        gs._enter_turn_start()
        return gs

    # ─────────────────────────────────────────────────────────────────────
    # Deck helpers
    # ─────────────────────────────────────────────────────────────────────
    def _draw(self) -> Optional[Card]:
        if not self.deck:
            if len(self.discard) <= 1:
                return None
            top = self.discard.pop()
            self.deck = self.discard
            self.discard = [top]
            random.shuffle(self.deck)
        return self.deck.pop() if self.deck else None

    def _flip(self) -> Optional[Card]:
        """Flip top card (for dynamite/jail/barrel) – goes to discard."""
        c = self._draw()
        if c:
            self.discard.append(c)
        return c

    @staticmethod
    def _is_heart(c: Optional[Card]) -> bool:
        return c is not None and c.suit == Suit.HEARTS

    @staticmethod
    def _is_dynamite_explode(c: Optional[Card]) -> bool:
        return c is not None and c.suit == Suit.SPADES and 2 <= c.value <= 9

    # ─────────────────────────────────────────────────────────────────────
    # Logging
    # ─────────────────────────────────────────────────────────────────────
    def log_msg(self, msg: str):
        self.log.append(msg)
        if len(self.log) > 60:
            self.log.pop(0)

    # ─────────────────────────────────────────────────────────────────────
    # Distance / targeting
    # ─────────────────────────────────────────────────────────────────────
    def _alive_ids(self) -> list[int]:
        return [p.pid for p in self.players if p.alive]

    def distance(self, from_id: int, to_id: int) -> int:
        alive = self._alive_ids()
        if to_id not in alive or from_id not in alive:
            return 999
        n = len(alive)
        fi = alive.index(from_id)
        ti = alive.index(to_id)
        cw = (ti - fi) % n
        ccw = (fi - ti) % n
        d = min(cw, ccw)
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
        # Can't jail the sheriff or yourself
        return [i for i in self._alive_ids()
                if i != pid
                and self.players[i].role != Role.SHERIFF
                and not self.players[i].jailed]

    # ─────────────────────────────────────────────────────────────────────
    # Turn flow
    # ─────────────────────────────────────────────────────────────────────
    def _enter_turn_start(self):
        """Advance current_pid and start their turn (dynamite → jail → draw)."""
        p = self.players[self.current_pid]
        if p.has_dynamite():
            self.phase = Phase.DYNAMITE
        elif p.jailed:
            self.phase = Phase.JAIL
        else:
            self.phase = Phase.DRAW

    def resolve_dynamite(self) -> dict:
        """
        Flip for dynamite. Returns info dict for UI.
        Call this at Phase.DYNAMITE.
        Returns {'flipped': Card, 'exploded': bool}
        """
        p = self.players[self.current_pid]
        dyn = p.get_dynamite()
        flipped = self._flip()
        exploded = self._is_dynamite_explode(flipped)
        info = {"flipped": flipped, "exploded": exploded}
        if exploded:
            p.remove_equipment(dyn)
            self.discard.append(dyn)
            died = p.take_damage(3)
            self.log_msg(f"💥 {p.name} 다이너마이트 폭발! -3HP")
            if died:
                self._eliminate(self.current_pid, -1)
                if self.phase == Phase.GAME_OVER:
                    return info
        else:
            # Pass dynamite to next alive player
            p.remove_equipment(dyn)
            nxt = self._next_alive(self.current_pid)
            self.players[nxt].equip(dyn)
            self.log_msg(f"🧨 다이너마이트 → {self.players[nxt].name}에게 전달")

        # After dynamite, check jail
        if self.players[self.current_pid].alive:
            if self.players[self.current_pid].jailed:
                self.phase = Phase.JAIL
            else:
                self.phase = Phase.DRAW
        return info

    def resolve_jail(self) -> dict:
        """Flip for jail. Returns {'flipped': Card, 'escaped': bool}."""
        p = self.players[self.current_pid]
        flipped = self._flip()
        escaped = self._is_heart(flipped)
        jail_card = p.jail_card
        p.jailed = False
        p.jail_card = None
        if jail_card and jail_card in p.equipment:
            p.remove_equipment(jail_card)
            self.discard.append(jail_card)
        if escaped:
            self.log_msg(f"🔓 {p.name} 감옥 탈출!")
            self.phase = Phase.DRAW
        else:
            self.log_msg(f"🔒 {p.name} 감옥에서 턴 스킵")
            self._advance_turn()
        return {"flipped": flipped, "escaped": escaped}

    def do_draw(self):
        """Draw 2 cards for current player."""
        p = self.players[self.current_pid]
        for _ in range(2):
            c = self._draw()
            if c:
                p.hand.append(c)
        self.log_msg(f"📥 {p.name} 카드 2장 드로우")
        self.bang_used = False
        self.phase = Phase.PLAY

    # ─────────────────────────────────────────────────────────────────────
    # Playing cards (PLAY phase)
    # ─────────────────────────────────────────────────────────────────────
    def play_card(self, pid: int, card_idx: int, target_id: int = -1,
                  target_card_idx: int = -1) -> bool:
        """
        Play a card from hand. Returns True if successful.
        target_id: for cards requiring a target player
        target_card_idx: for Cat Balou / Panic! (index into target's all_cards())
        """
        p = self.players[pid]
        if card_idx < 0 or card_idx >= len(p.hand):
            return False
        card = p.hand[card_idx]
        ct = card.card_type

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
        p = self.players[pid]
        card = p.hand.pop(card_idx)
        self.discard.append(card)
        return card

    def _play_bang(self, pid: int, card_idx: int, target_id: int) -> bool:
        p = self.players[pid]
        if not p.has_volcanic() and self.bang_used:
            return False
        if target_id < 0 or not self.players[target_id].alive:
            return False
        if not self.can_shoot(pid, target_id):
            return False

        card = self._discard_from_hand(pid, card_idx)
        if not p.has_volcanic():
            self.bang_used = True
        self.log_msg(f"🔫 {p.name} → {self.players[target_id].name} BANG!")
        self._start_bang_response(pid, target_id, card)
        return True

    def _play_beer(self, pid: int, card_idx: int) -> bool:
        alive = len(self._alive_ids())
        if alive <= 2:
            return False  # Beer has no effect at 2 players remaining
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

    def _play_cat_balou(self, pid: int, card_idx: int, target_id: int,
                        target_card_idx: int) -> bool:
        if target_id < 0 or not self.players[target_id].alive:
            return False
        target = self.players[target_id]
        all_cards = target.all_cards()
        if not all_cards:
            return False
        if target_card_idx < 0 or target_card_idx >= len(all_cards):
            target_card_idx = random.randint(0, len(all_cards) - 1)
        chosen = all_cards[target_card_idx]
        self._discard_from_hand(pid, card_idx)
        self._remove_card_from_player(target, chosen)
        self.discard.append(chosen)
        self.log_msg(f"🃏 캣 발루: {self.players[pid].name} → {target.name} [{chosen.name}] 버림")
        return True

    def _play_panic(self, pid: int, card_idx: int, target_id: int,
                    target_card_idx: int) -> bool:
        if target_id < 0 or not self.players[target_id].alive:
            return False
        if self.distance(pid, target_id) != 1:
            return False
        target = self.players[target_id]
        all_cards = target.all_cards()
        if not all_cards:
            return False
        if target_card_idx < 0 or target_card_idx >= len(all_cards):
            target_card_idx = random.randint(0, len(all_cards) - 1)
        chosen = all_cards[target_card_idx]
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
            if card.card_type == CardType.DYNAMITE:
                player  # no side effect needed
        elif card == player.jail_card:
            player.jailed = False
            player.jail_card = None

    def _play_indians(self, pid: int, card_idx: int) -> bool:
        self._discard_from_hand(pid, card_idx)
        self.log_msg(f"🪃 인디언: {self.players[pid].name} → 전원 BANG! 대응 필요")
        targets = [i for i in self._alive_ids() if i != pid]
        self._start_group_response(RespType.INDIANS, pid, targets)
        return True

    def _play_gatling(self, pid: int, card_idx: int) -> bool:
        self._discard_from_hand(pid, card_idx)
        self.log_msg(f"🔫🔫 개틀링: {self.players[pid].name} → 전원 Missed! 대응 필요")
        targets = [i for i in self._alive_ids() if i != pid]
        self._start_group_response(RespType.GATLING, pid, targets)
        return True

    def _play_saloon(self, pid: int, card_idx: int) -> bool:
        self._discard_from_hand(pid, card_idx)
        for p in self.players:
            if p.alive:
                p.heal(1)
        self.log_msg(f"🥃 살롱: 전원 HP +1")
        return True

    def _play_gen_store(self, pid: int, card_idx: int) -> bool:
        self._discard_from_hand(pid, card_idx)
        alive = self._alive_ids()
        self.gen_store_pile = []
        for _ in range(len(alive)):
            c = self._draw()
            if c:
                self.gen_store_pile.append(c)
        # Order: current player first, then clockwise
        ci = alive.index(pid)
        self.gen_store_order = alive[ci:] + alive[:ci]
        self.log_msg(f"🏪 잡화점: {self.players[pid].name} → 카드 {len(self.gen_store_pile)}장 공개")
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
            # Any leftover goes to discard
            self.discard.extend(self.gen_store_pile)
            self.gen_store_pile = []
            self.phase = Phase.PLAY
        return True

    def _play_duel(self, pid: int, card_idx: int, target_id: int) -> bool:
        if target_id < 0 or not self.players[target_id].alive:
            return False
        self._discard_from_hand(pid, card_idx)
        self.duel_challenger = pid
        self.duel_other = target_id
        self.duel_current = target_id   # target responds first
        self.log_msg(f"⚔️ 결투: {self.players[pid].name} vs {self.players[target_id].name}")
        self.phase = Phase.DUEL
        return True

    def _play_equipment(self, pid: int, card_idx: int, target_id: int = -1) -> bool:
        p = self.players[pid]
        card = p.hand[card_idx]
        ct = card.card_type

        if ct == CardType.JAIL:
            # Place on another player
            if target_id < 0:
                return False
            valid = self.valid_jail_targets(pid)
            if target_id not in valid:
                return False
            target = self.players[target_id]
            p.hand.pop(card_idx)
            target.equip(card)
            target.jailed = True
            target.jail_card = card
            self.log_msg(f"🔒 감옥: {p.name} → {target.name}")
            return True

        # Other blue cards: equip to self
        p.hand.pop(card_idx)
        p.equip(card)
        self.log_msg(f"🔧 {p.name} [{card.name}] 장착")
        return True

    # ─────────────────────────────────────────────────────────────────────
    # Response system
    # ─────────────────────────────────────────────────────────────────────
    def _start_bang_response(self, attacker: int, target: int, card: Card):
        self.resp_type = RespType.BANG
        self.resp_attacker = attacker
        self.resp_targets = [target]
        self.resp_current = target
        self.barrel_checked = False
        self.barrel_saved = False
        self.needs_missed = True
        self.phase = Phase.RESPONSE

    def _start_group_response(self, rtype: RespType, attacker: int, targets: list[int]):
        self.resp_type = rtype
        self.resp_attacker = attacker
        self.resp_targets = list(targets)
        self._next_responder()

    def _next_responder(self):
        while self.resp_targets:
            self.resp_current = self.resp_targets[0]
            p = self.players[self.resp_current]
            if not p.alive:
                self.resp_targets.pop(0)
                continue
            self.barrel_checked = False
            self.barrel_saved = False
            self.needs_missed = True
            self.phase = Phase.RESPONSE
            return
        # All responded
        self.phase = Phase.PLAY

    def check_barrel(self) -> bool:
        """
        Auto-check barrel for resp_current.
        Returns True if barrel saved them.
        """
        p = self.players[self.resp_current]
        if not p.has_barrel() or self.barrel_checked:
            return False
        self.barrel_checked = True
        flipped = self._flip()
        saved = self._is_heart(flipped)
        self.barrel_saved = saved
        if saved:
            self.needs_missed = False
            self.log_msg(f"🛢️ {p.name} 나무통 발동! ({flipped}) → 회피")
        else:
            self.log_msg(f"🛢️ {p.name} 나무통 실패 ({flipped})")
        return saved

    def respond_with_missed(self, card_idx: int) -> bool:
        """Current responder plays a Missed! card."""
        pid = self.resp_current
        p = self.players[pid]
        if card_idx < 0 or card_idx >= len(p.hand):
            return False
        card = p.hand[card_idx]
        need_ct = CardType.BANG if self.resp_type in (RespType.INDIANS,) else CardType.MISSED
        if card.card_type != need_ct:
            return False
        p.hand.pop(card_idx)
        self.discard.append(card)
        self.log_msg(f"✋ {p.name} [{card.name}] 사용 → 회피")
        self._finish_response(hit=False)
        return True

    def respond_take_hit(self):
        """Current responder takes the hit."""
        pid = self.resp_current
        p = self.players[pid]
        self.log_msg(f"💥 {p.name} 피격! -1HP ({p.hp - 1}/{p.max_hp})")
        # Try beer auto-save only if player will die (hp==1) – AI might use it;
        # for human, we just take damage here
        died = p.take_damage(1)
        if died:
            self._eliminate(pid, self.resp_attacker)
            if self.phase == Phase.GAME_OVER:
                return
        self._finish_response(hit=True)

    def _finish_response(self, hit: bool):
        if self.resp_type == RespType.BANG:
            # Single target done
            self.resp_targets.clear()
            self.phase = Phase.PLAY
        else:
            # Indians / Gatling: advance to next target
            if self.resp_targets:
                self.resp_targets.pop(0)
            self._next_responder()

    # ─────────────────────────────────────────────────────────────────────
    # Duel resolution
    # ─────────────────────────────────────────────────────────────────────
    def duel_play_bang(self, card_idx: int) -> bool:
        """Current duel participant plays a BANG!."""
        pid = self.duel_current
        p = self.players[pid]
        if card_idx < 0 or card_idx >= len(p.hand):
            return False
        card = p.hand[card_idx]
        if card.card_type != CardType.BANG:
            return False
        p.hand.pop(card_idx)
        self.discard.append(card)
        self.log_msg(f"⚔️ {p.name} BANG! →")
        # Switch sides
        self.duel_current = (self.duel_challenger
                             if self.duel_current == self.duel_other
                             else self.duel_other)
        return True

    def duel_take_hit(self):
        """Current duel participant can't / won't play BANG! → takes damage."""
        pid = self.duel_current
        p = self.players[pid]
        self.log_msg(f"⚔️ {p.name} 결투 패배! -1HP")
        died = p.take_damage(1)
        if died:
            self._eliminate(pid, self.duel_challenger if pid == self.duel_other
                            else self.duel_other)
        self.duel_challenger = self.duel_other = self.duel_current = -1
        if self.phase != Phase.GAME_OVER:
            self.phase = Phase.PLAY

    # ─────────────────────────────────────────────────────────────────────
    # Elimination and win check
    # ─────────────────────────────────────────────────────────────────────
    def _eliminate(self, pid: int, killer_id: int):
        p = self.players[pid]
        p.alive = False
        p.role_revealed = True
        self.log_msg(f"💀 {p.name} 탈락! 역할: {p.role.value}")

        # Outlaw kill bonus
        if p.role == Role.OUTLAW and killer_id >= 0 and self.players[killer_id].alive:
            for _ in range(3):
                c = self._draw()
                if c:
                    self.players[killer_id].hand.append(c)
            self.log_msg(f"🎁 {self.players[killer_id].name} 무법자 처치 보너스 +3장")

        # Sheriff killed deputy: discard everything
        if p.role == Role.DEPUTY and killer_id >= 0:
            if self.players[killer_id].role == Role.SHERIFF:
                self.players[killer_id].hand.clear()
                self.players[killer_id].equipment.clear()
                self.log_msg(f"⚠️ 보안관이 부관을 처치 → 패 전부 버림!")

        # Move eliminated player's cards to discard
        self.discard.extend(p.hand)
        self.discard.extend(p.equipment)
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
        alive = [(i, p) for i, p in enumerate(self.players) if p.alive]
        sheriff_alive = any(p.role == Role.SHERIFF for _, p in alive)
        outlaws_alive = any(p.role == Role.OUTLAW  for _, p in alive)
        renegades_alive = any(p.role == Role.RENEGADE for _, p in alive)

        if not sheriff_alive:
            if len(alive) == 1 and renegades_alive:
                return Role.RENEGADE
            return Role.OUTLAW

        if not outlaws_alive and not renegades_alive:
            return Role.SHERIFF

        return None

    # ─────────────────────────────────────────────────────────────────────
    # End-of-turn discard
    # ─────────────────────────────────────────────────────────────────────
    def enter_discard_phase(self):
        p = self.players[self.current_pid]
        limit = p.hand_limit()
        if len(p.hand) > limit:
            self.phase = Phase.DISCARD
        else:
            self._advance_turn()

    def discard_card(self, card_idx: int) -> bool:
        p = self.players[self.current_pid]
        if card_idx < 0 or card_idx >= len(p.hand):
            return False
        card = p.hand.pop(card_idx)
        self.discard.append(card)
        if len(p.hand) <= p.hand_limit():
            self._advance_turn()
        return True

    # ─────────────────────────────────────────────────────────────────────
    # Advance to next turn
    # ─────────────────────────────────────────────────────────────────────
    def _next_alive(self, from_pid: int) -> int:
        alive = self._alive_ids()
        n = len(alive)
        if n == 0:
            return from_pid
        ci = alive.index(from_pid) if from_pid in alive else 0
        return alive[(ci + 1) % n]

    def _advance_turn(self):
        self.turn_num += 1
        self.current_pid = self._next_alive(self.current_pid)
        self._enter_turn_start()

    # ─────────────────────────────────────────────────────────────────────
    # Convenience queries
    # ─────────────────────────────────────────────────────────────────────
    def current_player(self) -> Player:
        return self.players[self.current_pid]

    def responder(self) -> Optional[Player]:
        if self.resp_current >= 0:
            return self.players[self.resp_current]
        return None

    def duel_player(self) -> Optional[Player]:
        if self.duel_current >= 0:
            return self.players[self.duel_current]
        return None

    def cards_needing_target(self, card: Card) -> bool:
        return card.card_type in {
            CardType.BANG, CardType.CAT_BALOU, CardType.PANIC,
            CardType.DUEL, CardType.JAIL,
        }

    def valid_targets_for_card(self, pid: int, card: Card) -> list[int]:
        ct = card.card_type
        if ct == CardType.BANG:
            return self.valid_bang_targets(pid)
        if ct == CardType.CAT_BALOU:
            return [i for i in self._alive_ids() if i != pid and self.players[i].all_cards()]
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
        ct = card.card_type
        if ct == CardType.MISSED:
            return False  # can only be played as response
        if ct == CardType.BANG and not p.has_volcanic() and self.bang_used:
            return False
        if ct == CardType.BEER:
            return p.hp < p.max_hp and len(self._alive_ids()) > 2
        if ct == CardType.BARREL:
            return not p.has_barrel()
        if card.is_gun:
            return True  # can always equip gun (replaces old)
        if ct in {CardType.SCOPE, CardType.MUSTANG}:
            # check if not already equipped
            return not any(c.card_type == ct for c in p.equipment)
        if ct == CardType.DYNAMITE:
            return not p.has_dynamite()
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
