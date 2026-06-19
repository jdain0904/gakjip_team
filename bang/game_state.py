"""
Bang! 핵심 게임 로직 — 전체 규칙 구현.

턴 흐름:
  DYNAMITE → JAIL → CHAR_DRAW/KIT_PEEK → DRAW → PLAY
  → RESPONSE/DUEL/GEN_STORE → DISCARD → (다음 턴)

특수 단계:
  BEER_SAVE  – 사망 직전 플레이어가 즉시 맥주를 사용할 수 있는 단계
  CHAR_DRAW  – 제시 존스 / 페드로 라미레즈의 첫 번째 카드 선택
  KIT_PEEK   – 킷 칼슨이 상위 3장 중 2장을 선택
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
    """`GameState`가 현재 턴/반응 흐름의 어느 단계에 있는지를 나타낸다 —
    지금 어떤 입력이 유효한지와 UI가 무엇을 보여줘야 하는지를 결정한다."""
    DYNAMITE   = auto()
    JAIL       = auto()
    CHAR_DRAW  = auto()   # 제시 존스 / 페드로 라미레즈가 첫 드로우 방식을 선택
    KIT_PEEK   = auto()   # 킷 칼슨이 상위 3장 중 2장을 선택
    DRAW       = auto()
    PLAY       = auto()
    RESPONSE   = auto()   # BANG / 인디언! / 개틀링 반응
    DUEL       = auto()
    GEN_STORE  = auto()
    DISCARD    = auto()
    BEER_SAVE  = auto()   # 치명타 직전 맥주로 구사일생
    GAME_OVER  = auto()


class RespType(Enum):
    """Phase.RESPONSE가 어떤 공격에 반응하고 있는지를 나타낸다 — BANG!은
    대상 1명의 Missed! 한 장이 필요하고, 인디언!/개틀링은 나머지 전원이
    반응해야 한다 (인디언!은 BANG!으로, 개틀링은 Missed!로)."""
    BANG    = "bang"
    INDIANS = "indians"
    GATLING = "gatling"


@dataclass
class GameState:
    """한 경기 전체의 규칙 엔진. 모든 플레이어, 덱과 버림 더미, 현재 Phase를
    보유하며, 규칙에 따른 행동들(play_card, respond_with_missed,
    duel_play_bang, gen_store_pick 등)을 메서드로 제공한다 — 각 메서드는
    행동의 유효성을 검사하고, 상태를 변경하고, 단계를 진행시킨다. GUI
    (screens/game.py)와 화면 없는 AI 트레이너(train_ai.py) 모두 이 클래스의
    API만으로 게임을 진행시킨다."""
    num_players: int
    human_ids: list[int]
    mode: str            # 'local'(로컬 플레이) | 'ai'(AI 대전)

    players: list[Player] = field(default_factory=list)
    deck: list[Card]     = field(default_factory=list)
    discard: list[Card]  = field(default_factory=list)
    gen_store_pile: list[Card] = field(default_factory=list)

    current_pid: int = 0
    phase: Phase = Phase.DRAW
    turn_num: int = 0
    bang_used: bool = False

    # ── 반응(Response) 컨텍스트 ─────────────────────────────────────────────
    resp_type: Optional[RespType] = None
    resp_attacker: int = -1
    resp_targets: list[int] = field(default_factory=list)
    resp_current: int = -1
    barrel_checked: bool = False
    barrel_saved: bool = False
    barrel_attempts_left: int = 0
    needs_missed: bool = True
    resp_misses_needed: int = 1    # 공격자가 슬랩 더 킬러면 2
    resp_misses_played: int = 0

    # ── 결투(Duel) 컨텍스트 ─────────────────────────────────────────────────
    duel_challenger: int = -1
    duel_other: int = -1
    duel_current: int = -1

    # ── 잡화점(General Store) ───────────────────────────────────────────────
    gen_store_order: list[int] = field(default_factory=list)

    # ── 맥주를 이용한 치명타 구사일생 ─────────────────────────────────────────
    beer_save_pid: int = -1
    beer_save_killer: int = -1
    beer_save_resume: str = ""  # 'response', 'duel', 'dynamite', 'generic'

    # ── 캐릭터별 드로우 (제시 존스 / 페드로 라미레즈) ─────────────────────────
    char_draw_pid: int = -1
    char_draw_type: str = ""      # 'jesse' | 'pedro'
    char_draw_first_done: bool = False  # 첫 카드를 뽑은 후 True

    # ── 킷 칼슨 미리보기 ────────────────────────────────────────────────────
    kit_peek_cards: list[Card] = field(default_factory=list)
    kit_selected: list[int] = field(default_factory=list)   # kit_peek_cards 내 인덱스

    # ── 결과 ────────────────────────────────────────────────────────────────
    winner_role: Optional[Role] = None
    log: list[str] = field(default_factory=list)

    # ═════════════════════════════════════════════════════════════════════
    # 팩토리
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
        # 공식 규칙: 보안관이 항상 첫 턴을 가져간다. 역할이 무작위 자리에
        # 배정되므로, 0번 자리라고 가정하지 않고 보안관이 어느 자리에
        # 배정되었는지 직접 찾는다.
        gs.current_pid = next(p.pid for p in players if p.role == Role.SHERIFF)
        gs._enter_turn_start()
        return gs

    # ═════════════════════════════════════════════════════════════════════
    # 덱 보조 함수
    # ═════════════════════════════════════════════════════════════════════
    def _draw(self) -> Optional[Card]:
        if not self.deck:
            if len(self.discard) <= 1:
                return None
            top = self.discard.pop()
            self.deck = self.discard
            self.discard = [top]
            random.shuffle(self.deck)
            self.log_msg("■ 덱 소진 — 버림더미를 섞어 새 덱 생성")
        return self.deck.pop() if self.deck else None

    def _flip(self, pid: int = -1) -> Optional[Card]:
        """
        드로우! 판정(나무통, 감옥, 다이너마이트)을 위해 덱 맨 위 카드를 뒤집는다.
        럭키 듀크는 카드 2장을 뒤집어 더 유리한 쪽을 선택한다.
        판정에 '적용되는' 카드를 반환한다.
        """
        c1 = self._flip_single()
        if pid >= 0 and self.players[pid].is_lucky_duke():
            c2 = self._flip_single()
            if c2 is not None:
                chosen = self._lucky_duke_pick(c1, c2)
                other  = c2 if chosen is c1 else c1
                self.log_msg(f"★ 럭키 듀크: {c1} | {c2} > {chosen} 선택")
                # 선택되지 않은 카드는 버림 더미에 둔다 (_flip_single에서 이미 처리됨)
                return chosen
        return c1

    def _flip_single(self) -> Optional[Card]:
        c = self._draw()
        if c:
            self.discard.append(c)
        return c

    @staticmethod
    def _lucky_duke_pick(c1: Optional[Card], c2: Optional[Card]) -> Optional[Card]:
        """럭키 듀크를 위해 '더 나은' 카드를 고른다 — 상황에 무관하게 하트를 우선한다."""
        if c1 is None:
            return c2
        if c2 is None:
            return c1
        # 하트를 우선(나무통/감옥에 유리), 2-9♠는 피함(다이너마이트에 불리)
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
    # 로그
    # ═════════════════════════════════════════════════════════════════════
    def log_msg(self, msg: str):
        self.log.append(msg)
        if len(self.log) > 80:
            self.log.pop(0)

    # ═════════════════════════════════════════════════════════════════════
    # 거리 / 대상 선택
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
        # 로즈 둘란/폴 리그렛: 실제 조준경/무스탕 카드는 고유 능력과 중첩되어
        # 총합 2가 된다 (Player.scope_count() 참고).
        d -= self.players[from_id].scope_count()
        d += self.players[to_id].mustang_count()
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
    # 턴 흐름
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

    # ── 다이너마이트 ──────────────────────────────────────────────────────────
    def resolve_dynamite(self) -> dict:
        p       = self.players[self.current_pid]
        dyn     = p.get_dynamite()
        flipped = self._flip(self.current_pid)
        exploded = self._is_dynamite_explode(flipped)
        if exploded:
            p.remove_equipment(dyn)
            self.discard.append(dyn)
            self.log_msg(f"▲ {p.name} 다이너마이트 폭발! -3HP")
            died = p.take_damage(3)
            self._trigger_damage_reactions(self.current_pid, -1, 3)
            if died:
                self._handle_death(self.current_pid, -1, "dynamite")
                return {"flipped": flipped, "exploded": True}
        else:
            p.remove_equipment(dyn)
            nxt = self._next_alive(self.current_pid)
            self.players[nxt].equip(dyn)
            self.log_msg(f"▶ 다이너마이트 > {self.players[nxt].name}에게 전달")

        if self.phase == Phase.GAME_OVER:
            return {"flipped": flipped, "exploded": exploded}

        if self.players[self.current_pid].alive and self.players[self.current_pid].jailed:
            self.phase = Phase.JAIL
        elif self.players[self.current_pid].alive:
            self._enter_draw_phase()
        return {"flipped": flipped, "exploded": exploded}

    # ── 감옥 ──────────────────────────────────────────────────────────────
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
            self.log_msg(f"○ {p.name} 감옥 탈출!")
            self._enter_draw_phase()
        else:
            self.log_msg(f"● {p.name} 감옥에서 턴 스킵")
            self._advance_turn()
        return {"flipped": flipped, "escaped": escaped}

    # ── 캐릭터 특수 드로우 ─────────────────────────────────────────────────
    def _start_kit_peek(self):
        self.kit_peek_cards = []
        self.kit_selected   = []
        for _ in range(3):
            c = self._draw()
            if c:
                self.kit_peek_cards.append(c)
        if not self.kit_peek_cards:
            # 덱과 버림 더미가 모두 소진됨 — 공개할 카드가 없으므로 PLAY 단계로 바로 넘어간다.
            self.bang_used = False
            self.phase = Phase.PLAY
            return
        self.log_msg(f"◇ 킷 칼슨: 상위 {len(self.kit_peek_cards)}장 공개")
        self.phase = Phase.KIT_PEEK

    def kit_carlson_pick(self, card_idx: int) -> bool:
        if card_idx < 0 or card_idx >= len(self.kit_peek_cards):
            return False
        if card_idx in self.kit_selected:
            return False
        self.kit_selected.append(card_idx)
        if len(self.kit_selected) == 2 or len(self.kit_selected) >= len(self.kit_peek_cards):
            p = self.players[self.current_pid]
            for i in self.kit_selected:
                p.hand.append(self.kit_peek_cards[i])
            leftover = [c for i, c in enumerate(self.kit_peek_cards)
                        if i not in self.kit_selected]
            if leftover:
                self.deck.append(leftover[0])   # 덱 맨 위로 되돌림
            self.kit_peek_cards = []
            self.kit_selected   = []
            self.bang_used = False
            self.phase = Phase.PLAY
        return True

    # 제시 존스 / 페드로 라미레즈
    def char_draw_from_deck(self) -> bool:
        """덱에서 첫 번째 카드를 뽑는다 (제시 존스 / 페드로 라미레즈 선택지)."""
        if self.phase != Phase.CHAR_DRAW or self.char_draw_first_done:
            return False
        c = self._draw()
        if c:
            self.players[self.char_draw_pid].hand.append(c)
        self.char_draw_first_done = True
        self._finish_char_draw()
        return True

    def char_draw_from_player(self, target_pid: int) -> bool:
        """제시 존스: 대상의 손패에서 첫 번째 카드를 훔쳐온다."""
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
        self.log_msg(f"★ 제시 존스: {target.name}에게서 [{stolen.name}] 가져옴")
        self.char_draw_first_done = True
        self._finish_char_draw()
        return True

    def char_draw_from_discard(self) -> bool:
        """페드로 라미레즈: 버림 더미에서 첫 번째 카드를 뽑는다."""
        if self.phase != Phase.CHAR_DRAW or self.char_draw_type != "pedro":
            return False
        if self.char_draw_first_done:
            return False
        if not self.discard:
            return self.char_draw_from_deck()
        c = self.discard.pop()
        self.players[self.char_draw_pid].hand.append(c)
        self.log_msg(f"★ 페드로 라미레즈: 버림더미에서 [{c.name}] 가져옴")
        self.char_draw_first_done = True
        self._finish_char_draw()
        return True

    def _finish_char_draw(self):
        """덱에서 두 번째 카드를 뽑고 플레이 단계를 시작한다."""
        c = self._draw()
        if c:
            self.players[self.char_draw_pid].hand.append(c)
        self.char_draw_pid  = -1
        self.char_draw_type = ""
        self.char_draw_first_done = False
        self.bang_used = False
        self.phase = Phase.PLAY

    # ── 일반 드로우 ───────────────────────────────────────────────────────
    def do_draw(self):
        p  = self.players[self.current_pid]
        ct = p.character

        # 블랙 잭: 두 번째 카드를 공개; 빨간 무늬면 카드 1장 추가로 드로우
        if ct == CharacterType.BLACK_JACK:
            c1 = self._draw()
            c2 = self._draw()
            if c1: p.hand.append(c1)
            if c2:
                p.hand.append(c2)
                is_red = c2.suit in (Suit.HEARTS, Suit.DIAMONDS)
                self.log_msg(f"★ 블랙 잭: 2번째 카드 {c2} {'> 빨간 무늬! +1장 추가' if is_red else ''}")
                if is_red:
                    c3 = self._draw()
                    if c3:
                        p.hand.append(c3)
        else:
            for _ in range(2):
                c = self._draw()
                if c:
                    p.hand.append(c)
            self.log_msg(f"■ {p.name} 카드 2장 드로우")

        self.bang_used = False
        self.phase = Phase.PLAY

    # ═════════════════════════════════════════════════════════════════════
    # 카드 플레이 (PLAY 단계)
    # ═════════════════════════════════════════════════════════════════════
    def play_card(self, pid: int, card_idx: int, target_id: int = -1,
                  target_card_idx: int = -1) -> bool:
        p = self.players[pid]
        if card_idx < 0 or card_idx >= len(p.hand):
            return False
        card = p.hand[card_idx]
        ct   = card.card_type

        # 캘러미티 재닛: Missed!를 BANG!으로 사용 가능
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
        self.log_msg(f"▲ {p.name} > {self.players[target_id].name} {label}")
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
        self.log_msg(f"♥ {p.name} HP +1 ({p.hp}/{p.max_hp})")
        return True

    def _play_draw_cards(self, pid: int, card_idx: int, n: int, label: str) -> bool:
        self._discard_from_hand(pid, card_idx)
        p = self.players[pid]
        for _ in range(n):
            c = self._draw()
            if c:
                p.hand.append(c)
        self.log_msg(f"◆ {p.name} {label} > +{n}장")
        return True

    def _play_cat_balou(self, pid, card_idx, target_id, target_card_idx) -> bool:
        if target_id < 0 or not self.players[target_id].alive:
            return False
        target = self.players[target_id]
        if not target.all_cards():
            return False
        chosen = self._resolve_strip_target(target, target_card_idx)
        self._discard_from_hand(pid, card_idx)
        self._remove_card_from_player(target, chosen)
        self.discard.append(chosen)
        self.log_msg(f"◆ 캣 발루: {self.players[pid].name} > {target.name} [{chosen.name}] 버림")
        return True

    def _play_panic(self, pid, card_idx, target_id, target_card_idx) -> bool:
        if target_id < 0 or not self.players[target_id].alive:
            return False
        if self.distance(pid, target_id) != 1:
            return False
        target = self.players[target_id]
        if not target.all_cards():
            return False
        chosen = self._resolve_strip_target(target, target_card_idx)
        self._discard_from_hand(pid, card_idx)
        self._remove_card_from_player(target, chosen)
        self.players[pid].hand.append(chosen)
        self.log_msg(f"◆ 패닉: {self.players[pid].name} > {target.name} [{chosen.name}] 훔침")
        return True

    def _resolve_strip_target(self, target: Player, target_card_idx: int) -> Card:
        """캣 발루/패닉!: 유효 범위 내의 명시적 인덱스가 주어지면 대상이
        장착한(플레이 중인) 카드 중 하나를 선택한다. 인덱스가 없으면
        규칙서 기본값에 따라 대상의 손패에서 *무작위로* 카드를 가져온다 —
        장착 카드는 의도적으로 선택할 때만 빼앗을 수 있고, 무작위로
        빼앗기는 대상이 될 수 없다."""
        all_c = target.all_cards()
        if 0 <= target_card_idx < len(all_c):
            return all_c[target_card_idx]
        if target.hand:
            return random.choice(target.hand)
        return random.choice(all_c)

    def _remove_card_from_player(self, player: Player, card: Card):
        if card == player.jail_card:
            player.equipment.remove(card)
            player.jailed    = False
            player.jail_card = None
        elif card in player.hand:
            player.hand.remove(card)
        elif card in player.equipment:
            player.equipment.remove(card)

    def _play_indians(self, pid, card_idx) -> bool:
        self._discard_from_hand(pid, card_idx)
        self.log_msg(f"▲ 인디언: {self.players[pid].name} > 전원 BANG! 필요")
        targets = [i for i in self._alive_ids() if i != pid]
        self._start_group_response(RespType.INDIANS, pid, targets)
        return True

    def _play_gatling(self, pid, card_idx) -> bool:
        self._discard_from_hand(pid, card_idx)
        self.log_msg(f"▲▲ 개틀링: {self.players[pid].name} > 전원 Missed! 필요")
        targets = [i for i in self._alive_ids() if i != pid]
        self._start_group_response(RespType.GATLING, pid, targets)
        return True

    def _play_saloon(self, pid, card_idx) -> bool:
        self._discard_from_hand(pid, card_idx)
        for p in self.players:
            if p.alive:
                p.heal(1)
        self.log_msg("♥ 살롱: 전원 HP +1")
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
        self.log_msg(f"◇ 잡화점: {len(self.gen_store_pile)}장 공개")
        self.phase = Phase.GEN_STORE
        return True

    def gen_store_pick(self, pid: int, card_idx: int) -> bool:
        if self.phase != Phase.GEN_STORE:
            return False
        if not self.gen_store_order or self.gen_store_order[0] != pid:
            return False
        if not self.gen_store_pile:
            # 분배 중 덱과 버림 더미가 모두 소진됨 — gen_store_order에 남은
            # 누구에게도 더는 카드를 나눠줄 수 없으므로 라운드를 종료한다.
            self.gen_store_order = []
            self.phase = Phase.PLAY
            return True
        if card_idx < 0 or card_idx >= len(self.gen_store_pile):
            return False
        card = self.gen_store_pile.pop(card_idx)
        self.players[pid].hand.append(card)
        self.gen_store_order.pop(0)
        self.log_msg(f"  {self.players[pid].name} > [{card.name}] 선택")
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
        self.log_msg(f"▲ 결투: {self.players[pid].name} vs {self.players[target_id].name}")
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
            self.log_msg(f"● 감옥: {p.name} > {target.name}")
            return True
        p.hand.pop(card_idx)
        displaced = p.equip(card)
        self.discard.extend(displaced)
        if displaced:
            old_names = ", ".join(c.name for c in displaced)
            self.log_msg(f"● {p.name} [{card.name}] 장착 (기존 [{old_names}] 버림)")
        else:
            self.log_msg(f"● {p.name} [{card.name}] 장착")
        return True

    # ── 시드 케첨 액티브 능력 ─────────────────────────────────────────────
    def use_sid_ketchum(self, pid: int, idx1: int, idx2: int) -> bool:
        """카드 2장을 버려 HP 1을 회복한다. 자신의 PLAY 단계에서만 유효하다."""
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
        c1 = p.hand.pop(hi)
        c2 = p.hand.pop(lo)
        self.discard.extend([c1, c2])
        p.heal(1)
        self.log_msg(f"♥ {p.name} 시드 케첨 능력: +1HP ({p.hp}/{p.max_hp})")
        self._check_suzy_lafayette(pid)
        return True

    # ═════════════════════════════════════════════════════════════════════
    # 반응 시스템
    # ═════════════════════════════════════════════════════════════════════
    def _start_bang_response(self, attacker: int, target: int):
        self.resp_type        = RespType.BANG
        self.resp_attacker    = attacker
        self.resp_targets     = [target]
        self.resp_current     = target
        self.barrel_checked   = False
        self.barrel_saved     = False
        self.barrel_attempts_left = self.players[target].barrel_count()
        self.needs_missed     = True
        # 슬랩 더 킬러: 대상은 Missed! 2장이 필요함
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
            self.barrel_attempts_left = p.barrel_count()
            self.needs_missed     = True
            self.resp_misses_played = 0
            self.phase = Phase.RESPONSE
            return
        self.phase = Phase.PLAY

    def check_barrel(self) -> bool:
        p = self.players[self.resp_current]
        # 공식 규칙: 인디언!에 대해서는 "Missed!도 나무통도 효과가 없다"
        if self.resp_type == RespType.INDIANS or self.barrel_attempts_left <= 0:
            return False
        self.barrel_attempts_left -= 1
        flipped = self._flip(self.resp_current)
        saved   = self._is_heart(flipped)
        self.barrel_saved   = saved
        # 주르도네가 *실제* 나무통도 함께 장착하고 있으면 Missed!를 내거나
        # 피격을 감수하기 전에 두 번 뒤집을 수 있다 ("BANG!을 무효화할
        # 두 번의 기회") — 실패하고 시도 횟수도 남지 않았을 때, 또는
        # 이미 성공했을 때만 버튼을 잠근다.
        self.barrel_checked = saved or self.barrel_attempts_left <= 0
        if saved:
            self.needs_missed = False
            self.log_msg(f"○ {p.name} 나무통 발동! ({flipped}) > BANG! 회피")
        elif self.barrel_attempts_left > 0:
            self.log_msg(f"▼ {p.name} 나무통 실패 ({flipped}, 하트 아님) > 한 번 더 시도 가능")
        else:
            self.log_msg(f"▼ {p.name} 나무통 실패 ({flipped}, 하트 아님) > 직접 막아야 함")
        return saved

    def respond_with_missed(self, card_idx: int) -> bool:
        pid  = self.resp_current
        p    = self.players[pid]
        if card_idx < 0 or card_idx >= len(p.hand):
            return False
        card = p.hand[card_idx]

        # 유효한 반응 카드는 resp_type과 캘러미티 재닛 여부에 따라 달라짐
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
        self.log_msg(f"○ {p.name} [{card.name}] 사용 ({self.resp_misses_played}/{self.resp_misses_needed})")

        if self.resp_misses_played >= self.resp_misses_needed:
            self._finish_response(hit=False)
        # else: Missed!가 더 필요함 (슬랩 더 킬러) — RESPONSE 단계 유지
        return True

    def respond_take_hit(self):
        pid = self.resp_current
        p   = self.players[pid]
        self.log_msg(f"▲ {p.name} 피격! -1HP")
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
    # 결투
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
        self.log_msg(f"▲ {p.name} [{card.name}] >")
        self.duel_current = (self.duel_challenger
                             if self.duel_current == self.duel_other
                             else self.duel_other)
        return True

    def duel_take_hit(self):
        pid  = self.duel_current
        p    = self.players[pid]
        killer = self.duel_challenger if pid == self.duel_other else self.duel_other
        self.log_msg(f"▲ {p.name} 결투 패배! -1HP")
        died = p.take_damage(1)
        self._trigger_damage_reactions(pid, killer, 1)
        self.duel_challenger = self.duel_other = self.duel_current = -1
        if died:
            self._handle_death(pid, killer, "duel")
        elif self.phase != Phase.GAME_OVER:
            self.phase = Phase.PLAY

    # ═════════════════════════════════════════════════════════════════════
    # 맥주를 이용한 치명타 구사일생
    # ═════════════════════════════════════════════════════════════════════
    def _handle_death(self, pid: int, killer_id: int, resume: str):
        """탈락 처리 전에 맥주로 구사일생할 수 있는지 확인한다."""
        p = self.players[pid]
        alive_count = len(self._alive_ids())  # 이 시점에는 pid도 생존자로 집계됨
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
        self.log_msg(f"♥ {p.name} 맥주로 생존! HP 1/{p.max_hp}")
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
    # 캐릭터 발동 반응
    # ═════════════════════════════════════════════════════════════════════
    def _trigger_damage_reactions(self, pid: int, attacker_id: int, amount: int):
        p  = self.players[pid]
        ct = p.character

        # 바트 카시디: 잃은 HP당 카드 1장 드로우
        if ct == CharacterType.BART_CASSIDY and p.alive:
            for _ in range(amount):
                c = self._draw()
                if c:
                    p.hand.append(c)
            self.log_msg(f"★ 바트 카시디: +{amount}장 드로우")

        # 엘 그링고: 잃은 HP당 공격자에게서 카드 1장 훔침
        if ct == CharacterType.EL_GRINGO and p.alive and attacker_id >= 0:
            attacker = self.players[attacker_id]
            if attacker.hand:
                for _ in range(amount):
                    if not attacker.hand:
                        break
                    stolen = random.choice(attacker.hand)
                    attacker.hand.remove(stolen)
                    p.hand.append(stolen)
                self.log_msg(f"★ 엘 그링고: {attacker.name}에게서 {amount}장 훔침")

    def _check_suzy_lafayette(self, pid: int):
        p = self.players[pid]
        if p.character == CharacterType.SUZY_LAFAYETTE and p.alive and len(p.hand) == 0:
            c = self._draw()
            if c:
                p.hand.append(c)
                self.log_msg(f"★ 수지 라파예트: 손패 없음 > 카드 1장 드로우 [{c.name}]")

    # ═════════════════════════════════════════════════════════════════════
    # 탈락 & 승리 판정
    # ═════════════════════════════════════════════════════════════════════
    def _eliminate(self, pid: int, killer_id: int):
        p       = self.players[pid]
        p.alive = False
        p.role_revealed = True
        self.log_msg(f"▼ {p.name} 탈락! 역할: {p.role.value}")

        # 벌처 샘: 탈락한 플레이어의 모든 카드를 가져감
        vulture = next((pl for pl in self.players
                        if pl.alive and pl.character == CharacterType.VULTURE_SAM
                        and pl.pid != pid), None)
        if vulture:
            vulture.hand.extend(p.hand)
            vulture.hand.extend(p.equipment)
            self.log_msg(f"★ 벌처 샘: {p.name}의 카드 전부 획득")
        else:
            self.discard.extend(p.hand)
            self.discard.extend(p.equipment)

        # 처치자에게 주어지는 무법자 처치 보너스 — 위의 벌처 샘 능력과는
        # 독립적이다: 보너스 카드 3장은 죽은 플레이어의 손패가 아니라 덱에서
        # 새로 뽑으므로, 두 효과는 함께 적용된다.
        if p.role == Role.OUTLAW and killer_id >= 0 and self.players[killer_id].alive:
            for _ in range(3):
                c = self._draw()
                if c:
                    self.players[killer_id].hand.append(c)
            self.log_msg(f"◆ {self.players[killer_id].name} 무법자 처치 보너스 +3장")

        # 보안관이 부관을 처치했을 때의 페널티: "손패와 플레이 중인 카드를
        # 모두 버려야 한다" — 그냥 사라지는 것이 아니라 버림 더미로 간다.
        if p.role == Role.DEPUTY and killer_id >= 0:
            if self.players[killer_id].role == Role.SHERIFF:
                sheriff = self.players[killer_id]
                self.discard.extend(sheriff.hand)
                self.discard.extend(sheriff.equipment)
                sheriff.hand.clear()
                sheriff.equipment.clear()
                self.log_msg("▲ 보안관이 부관을 처치 > 패/장착 전부 버림!")

        # 감옥 카드(있는 경우)는 위의 `p.equipment` 확장을 통해 이미
        # (벌처의 손패 또는 버림 더미로) 처리되었다 — 여기서 다시 추가하면
        # 동일한 Card 객체가 동시에 두 곳에 중복으로 들어가게 된다.
        p.hand.clear()
        p.equipment.clear()
        p.jailed    = False
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
    # 턴 종료 버리기
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
    # 턴 진행
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
    # 편의 조회 함수
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
        # 캘러미티 재닛은 Missed!를 BANG!으로 사용
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

        # 캘러미티 재닛은 Missed!를 BANG!으로 사용 가능
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

    def player_won(self, pid: int) -> bool:
        """`pid`의 역할이 승리한 진영에 속하면 True를 반환한다 (부관은 보안관 승리로 집계된다)."""
        if self.winner_role is None:
            return False
        role = self.players[pid].role
        return role == self.winner_role or (role == Role.DEPUTY and self.winner_role == Role.SHERIFF)

    def winner_message(self) -> str:
        if self.winner_role == Role.SHERIFF:
            return "보안관 & 부관 승리! 무법자와 배신자를 처치했습니다."
        if self.winner_role == Role.OUTLAW:
            return "무법자 승리! 보안관을 처치했습니다!"
        if self.winner_role == Role.RENEGADE:
            return "배신자 승리! 마지막 생존자가 되었습니다!"
        return "게임 종료"
