"""
턴제 전략 게임 - 게임 환경
행동: 0=이동, 1=집카드, 2=보급카드, 3=카드뽑기
"""

import random
from dataclasses import dataclass, field
from typing import Optional

BOARD_SIZE = 50
CARD_MIN   = 0
CARD_MAX   = 60
HAND_SIZE  = 5
MAX_HAND   = 7   # 카드 뽑기로 최대 보유 가능 수


@dataclass
class Card:
    card_type: str   # 'supply' | 'home'
    value: int

    def label(self):
        t = "보급" if self.card_type == "supply" else "집"
        return f"{t} +{self.value}"


def draw_card() -> Card:
    card_type = random.choice(["supply", "home"])
    value = random.randint(CARD_MIN, CARD_MAX)
    return Card(card_type=card_type, value=value)


@dataclass
class PlayerState:
    player_id: int
    name: str
    position: int = BOARD_SIZE
    hand: list = field(default_factory=list)
    supply_used: bool = False
    total_moves: int = 0
    is_human: bool = False
    last_drew: int = -1   # 마지막으로 드로우한 턴

    def draw_initial_hand(self):
        self.hand = [draw_card() for _ in range(HAND_SIZE)]

    def can_use_supply(self) -> bool:
        return not self.supply_used and any(c.card_type == "supply" for c in self.hand)

    def get_supply_card(self) -> Optional[Card]:
        return next((c for c in self.hand if c.card_type == "supply"), None)

    def get_best_home_card(self) -> Optional[Card]:
        cards = [c for c in self.hand if c.card_type == "home"]
        return max(cards, key=lambda c: c.value) if cards else None

    def can_draw(self, current_turn: int) -> bool:
        return len(self.hand) < MAX_HAND and self.last_drew != current_turn

    def arrived(self) -> bool:
        return self.position <= 0


class GameEnv:
    def __init__(self, num_players: int = 2, human_ids: Optional[list] = None):
        assert 2 <= num_players <= 6
        self.num_players = num_players
        self.human_ids: list = human_ids or []
        self.players: list[PlayerState] = []
        self.current_pid: int = 0
        self.turn: int = 0
        self.done: bool = False
        self.winner: Optional[int] = None

    def reset(self):
        self.players = []
        for i in range(self.num_players):
            is_human = i in self.human_ids
            name = f"플레이어{i+1}" if is_human else f"AI {i+1}"
            p = PlayerState(player_id=i, name=name, is_human=is_human)
            p.draw_initial_hand()
            self.players.append(p)
        self.current_pid = 0
        self.turn = 0
        self.done = False
        self.winner = None

    def get_state(self, pid: int) -> tuple:
        me = self.players[pid]
        opp_pos = [self.players[j].position for j in range(self.num_players) if j != pid]
        bh = me.get_best_home_card()
        bs = me.get_supply_card()
        return (
            me.position,
            min(opp_pos),
            int(me.supply_used),
            bh.value if bh else 0,
            bs.value if bs else 0,
        )

    def get_valid_actions(self, pid: int) -> list:
        me = self.players[pid]
        actions = [0]
        if me.get_best_home_card():
            actions.append(1)
        if me.can_use_supply():
            actions.append(2)
        if me.can_draw(self.turn):
            actions.append(3)
        return actions

    def step(self, pid: int, action: int) -> tuple:
        """(reward, done, drew_card) 반환"""
        me = self.players[pid]
        reward = 0
        drew_card = None

        if action == 0:
            me.position -= 1
            reward = 0.1

        elif action == 1:
            card = me.get_best_home_card()
            if card:
                me.position -= card.value
                me.hand.remove(card)
                me.hand.append(draw_card())
                reward = 0.3

        elif action == 2:
            card = me.get_supply_card()
            if card and not me.supply_used:
                me.position -= card.value
                me.hand.remove(card)
                me.hand.append(draw_card())
                me.supply_used = True
                reward = 0.5

        elif action == 3:
            # 카드 뽑기 (턴 소모)
            if me.can_draw(self.turn):
                new_card = draw_card()
                me.hand.append(new_card)
                me.last_drew = self.turn
                drew_card = new_card
                reward = 0.05

        me.position = max(0, me.position)
        me.total_moves += 1

        if me.arrived():
            self.done = True
            self.winner = pid
            reward = 10.0

        if not self.done:
            self.current_pid = (self.current_pid + 1) % self.num_players
            self.turn += 1

        return reward, self.done, drew_card
