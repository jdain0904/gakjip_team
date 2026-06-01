"""
턴제 전략 게임 - 게임 환경 및 규칙 정의
두 플레이어가 50칸 거리에서 시작하여 먼저 목표 지점에 도달하면 승리
"""

import random
from dataclasses import dataclass, field
from typing import Optional


BOARD_SIZE = 50        # 초기 플레이어 간 거리
CARD_MIN = 0
CARD_MAX = 60
HAND_SIZE = 5          # 초기 손패 수


@dataclass
class Card:
    card_type: str      # 'supply' or 'home'
    value: int

    def __repr__(self):
        t = "보급" if self.card_type == "supply" else "집"
        return f"[{t} +{self.value}]"


def draw_card() -> Card:
    card_type = random.choice(["supply", "home"])
    value = random.randint(CARD_MIN, CARD_MAX)
    return Card(card_type=card_type, value=value)


@dataclass
class PlayerState:
    player_id: int
    position: int           # 목표 지점 기준 남은 거리 (0이면 도착)
    hand: list = field(default_factory=list)
    supply_used: bool = False   # 보급 카드 사용 여부 (게임당 1회)
    total_moves: int = 0

    def draw_initial_hand(self):
        self.hand = [draw_card() for _ in range(HAND_SIZE)]

    def can_use_supply(self) -> bool:
        return not self.supply_used and any(c.card_type == "supply" for c in self.hand)

    def get_supply_card(self) -> Optional[Card]:
        for c in self.hand:
            if c.card_type == "supply":
                return c
        return None

    def get_best_home_card(self) -> Optional[Card]:
        home_cards = [c for c in self.hand if c.card_type == "home"]
        return max(home_cards, key=lambda c: c.value) if home_cards else None

    def arrived(self) -> bool:
        return self.position <= 0


class GameEnv:
    """
    게임 환경: 상태 반환, 행동 적용, 승패 판정

    행동 공간:
        0 - 1칸 이동
        1 - 집 카드 사용 (최댓값)
        2 - 보급 카드 사용 (1회 제한)
    """

    def __init__(self):
        self.players: list[PlayerState] = []
        self.turn = 0
        self.done = False
        self.winner: Optional[int] = None

    def reset(self) -> tuple:
        p0 = PlayerState(player_id=0, position=BOARD_SIZE)
        p1 = PlayerState(player_id=1, position=BOARD_SIZE)
        p0.draw_initial_hand()
        p1.draw_initial_hand()
        self.players = [p0, p1]
        self.turn = 0
        self.done = False
        self.winner = None
        return self._get_state(0), self._get_state(1)

    def _get_state(self, pid: int) -> tuple:
        """
        상태 벡터: (내 위치, 상대 위치, 보급카드 사용 여부,
                    손패 중 최대 집카드 값, 손패 중 최대 보급카드 값)
        """
        me = self.players[pid]
        opp = self.players[1 - pid]
        best_home = me.get_best_home_card()
        best_supply = me.get_supply_card()
        return (
            me.position,
            opp.position,
            int(me.supply_used),
            best_home.value if best_home else 0,
            best_supply.value if best_supply else 0,
        )

    def get_valid_actions(self, pid: int) -> list:
        me = self.players[pid]
        actions = [0]   # 이동은 항상 가능
        if me.get_best_home_card():
            actions.append(1)
        if me.can_use_supply():
            actions.append(2)
        return actions

    def step(self, pid: int, action: int) -> tuple:
        """행동 적용 후 (next_state, reward, done) 반환"""
        me = self.players[pid]
        reward = 0

        if action == 0:
            # 1칸 이동
            me.position -= 1
            me.total_moves += 1
            reward = 0.1

        elif action == 1:
            # 집 카드 사용
            card = me.get_best_home_card()
            if card:
                me.position -= card.value
                me.hand.remove(card)
                me.hand.append(draw_card())
                me.total_moves += 1
                reward = 0.3

        elif action == 2:
            # 보급 카드 사용 (1회 제한)
            card = me.get_supply_card()
            if card and not me.supply_used:
                me.position -= card.value
                me.hand.remove(card)
                me.hand.append(draw_card())
                me.supply_used = True
                me.total_moves += 1
                reward = 0.5

        # 위치 최솟값 0
        me.position = max(0, me.position)

        # 승패 확인
        if me.arrived():
            self.done = True
            self.winner = pid
            reward = 10.0
        elif self.players[1 - pid].arrived():
            self.done = True
            self.winner = 1 - pid
            reward = -5.0

        self.turn += 1
        next_state = self._get_state(pid)
        return next_state, reward, self.done

    def render(self):
        p0, p1 = self.players
        print(f"턴 {self.turn:3d} | P0 위치: {p0.position:3d} | P1 위치: {p1.position:3d}")
