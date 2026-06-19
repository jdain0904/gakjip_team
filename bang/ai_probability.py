"""AI 의사결정을 위한 카드 카운팅 확률 엔진.

특정 플레이어에게 현재 보이지 않는 카드들(아직 덱에 있거나, 앞으로
버려질 운명이거나, 상대의 손패에 있는 카드)이 어떤 속성을
만족할 확률을 추정한다 — 예를 들어 "Missed!인가", "♥ 무늬인가" 등을,
그 플레이어가 아직 보지 못한 모든 카드에 대한 초기하분포
(hypergeometric distribution)를 이용해 계산한다.
"""
from __future__ import annotations
import math
from cards import Card, CardType, Suit, build_deck

USEFUL_TYPES = {CardType.BANG, CardType.MISSED, CardType.BEER,
                CardType.STAGECOACH, CardType.WELLS_FARGO}

_FULL_DECK: list[Card] | None = None


def _full_deck() -> list[Card]:
    global _FULL_DECK
    if _FULL_DECK is None:
        _FULL_DECK = build_deck()
    return _FULL_DECK


def _hypergeom_at_least_one(pool: int, hits: int, draw: int) -> float:
    """`hits`개의 성공 사례가 있는 `pool`장 중에서 `draw`장을 뽑을 때, 성공(성공
    사례 카드)이 1장 이상 나올 확률 P(>=1 success)."""
    if pool <= 0 or hits <= 0 or draw <= 0:
        return 0.0
    draw = min(draw, pool)
    if pool - hits < draw:
        return 1.0
    return 1.0 - (math.comb(pool - hits, draw) / math.comb(pool, draw))


class CardCounter:
    """`viewer_pid`에게 보이는 모든 카드를 추적하고, 나머지 카드들의 확률을
    추론한다.

    "보이는 카드"란 버림 더미, 테이블에 깔린 모든 장비(규칙상 공개 정보),
    공개된 잡화점 카드, 그리고 viewer 자신의 손패를 의미한다. 다른
    플레이어의 손패는 절대 들여다보지 않으며, AI는 항상 확률적으로만
    추론한다.
    """

    def __init__(self, gs, viewer_pid: int):
        self.gs = gs
        self.viewer_pid = viewer_pid
        visible: list[Card] = []
        visible.extend(gs.discard)
        visible.extend(gs.gen_store_pile)
        for p in gs.players:
            visible.extend(p.equipment)
        visible.extend(gs.players[viewer_pid].hand)
        self._visible = visible
        self.unseen_total = max(0, len(_full_deck()) - len(visible))

    def unseen_matching(self, predicate) -> int:
        total = sum(1 for c in _full_deck() if predicate(c))
        seen  = sum(1 for c in self._visible if predicate(c))
        return max(0, total - seen)

    def unseen_count_type(self, *types: CardType) -> int:
        ts = set(types)
        return self.unseen_matching(lambda c: c.card_type in ts)

    def unseen_fraction(self, *types: CardType) -> float:
        if self.unseen_total <= 0:
            return 0.0
        return self.unseen_count_type(*types) / self.unseen_total

    def prob_has_any_type(self, hand_size: int, *types: CardType) -> float:
        hits = self.unseen_count_type(*types)
        return _hypergeom_at_least_one(self.unseen_total, hits, hand_size)

    def prob_dodge(self, target_pid: int) -> float:
        """target_pid를 향한 BANG!이 회피될(Missed! 또는 나무통) 확률."""
        target = self.gs.players[target_pid]
        types = (CardType.MISSED, CardType.BANG) if target.is_calamity_janet() else (CardType.MISSED,)
        p_card = self.prob_has_any_type(len(target.hand), *types)
        barrels = target.barrel_count()
        if barrels <= 0:
            return p_card
        hearts_unseen = self.unseen_matching(lambda c: c.suit == Suit.HEARTS)
        p_heart  = (hearts_unseen / self.unseen_total) if self.unseen_total > 0 else 0.0
        # 실제 나무통도 함께 장착한 주르도네는 독립적인 뒤집기 시도를
        # 두 번 받는다 (Player.barrel_count() 참고).
        p_barrel = 1 - (1 - p_heart) ** barrels
        return p_card + (1 - p_card) * p_barrel

    def prob_has_bang_equivalent(self, pid: int) -> float:
        """`pid`가 인디언!/결투에 BANG!(또는 재닛의 Missed!)으로 응답할 수 있는 확률."""
        p = self.gs.players[pid]
        types = (CardType.BANG, CardType.MISSED) if p.is_calamity_janet() else (CardType.BANG,)
        return self.prob_has_any_type(len(p.hand), *types)

    def prob_useful_hand_card(self, pid: int) -> float:
        """`pid`의 손패에서 아직 보이지 않은 카드 1장이 대체로 유용할 추정 확률."""
        return self.unseen_fraction(*USEFUL_TYPES)

    def prob_escape_jail(self) -> float:
        """감옥/다이너마이트 방식의 ♥ 카드 뒤집기가 성공할 확률."""
        hearts_unseen = self.unseen_matching(lambda c: c.suit == Suit.HEARTS)
        return (hearts_unseen / self.unseen_total) if self.unseen_total > 0 else 0.0

    def prob_dynamite_explodes(self) -> float:
        spade_2_9 = self.unseen_matching(lambda c: c.suit == Suit.SPADES and 2 <= c.value <= 9)
        return (spade_2_9 / self.unseen_total) if self.unseen_total > 0 else 0.0
