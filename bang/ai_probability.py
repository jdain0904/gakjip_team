"""Card-counting probability engine for AI decision-making.

Estimates the odds that cards not currently visible to a given player
(still in the deck, in the discard-bound future, or in an opponent's
hand) match some property — e.g. "is a Missed!", "is a Heart" — using
the hypergeometric distribution over every card that player hasn't
already seen.
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
    """P(>=1 success) drawing `draw` cards from a `pool`-card population with `hits` successes."""
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
        """Probability a BANG! aimed at target_pid is avoided (Missed! or Barrel)."""
        target = self.gs.players[target_pid]
        types = (CardType.MISSED, CardType.BANG) if target.is_calamity_janet() else (CardType.MISSED,)
        p_card = self.prob_has_any_type(len(target.hand), *types)
        barrels = target.barrel_count()
        if barrels <= 0:
            return p_card
        hearts_unseen = self.unseen_matching(lambda c: c.suit == Suit.HEARTS)
        p_heart  = (hearts_unseen / self.unseen_total) if self.unseen_total > 0 else 0.0
        # Jourdonnais with a real Barrel also in play gets two independent
        # flip attempts (see Player.barrel_count()).
        p_barrel = 1 - (1 - p_heart) ** barrels
        return p_card + (1 - p_card) * p_barrel

    def prob_has_bang_equivalent(self, pid: int) -> float:
        """Probability `pid` can answer Indians!/a Duel with a BANG! (or Janet's Missed!)."""
        p = self.gs.players[pid]
        types = (CardType.BANG, CardType.MISSED) if p.is_calamity_janet() else (CardType.BANG,)
        return self.prob_has_any_type(len(p.hand), *types)

    def prob_useful_hand_card(self, pid: int) -> float:
        """Estimated odds a single unseen card from `pid`'s hand is generally useful."""
        return self.unseen_fraction(*USEFUL_TYPES)

    def prob_escape_jail(self) -> float:
        """Probability a Jail/Dynamite-style Heart flip succeeds."""
        hearts_unseen = self.unseen_matching(lambda c: c.suit == Suit.HEARTS)
        return (hearts_unseen / self.unseen_total) if self.unseen_total > 0 else 0.0

    def prob_dynamite_explodes(self) -> float:
        spade_2_9 = self.unseen_matching(lambda c: c.suit == Suit.SPADES and 2 <= c.value <= 9)
        return (spade_2_9 / self.unseen_total) if self.unseen_total > 0 else 0.0
