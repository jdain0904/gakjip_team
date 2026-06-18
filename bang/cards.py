from enum import Enum
from dataclasses import dataclass
import random


class Suit(Enum):
    """One of the four standard playing-card suits a `Card` can have."""
    HEARTS   = "♥"
    DIAMONDS = "♦"
    CLUBS    = "♣"
    SPADES   = "♠"


class CardType(Enum):
    """Every distinct card name in the 80-card deck — brown (play-and-discard)
    or blue (equipment that stays in play; see BLUE_TYPES below)."""
    # Brown – play and discard
    BANG        = "BANG!"
    MISSED      = "Missed!"
    BEER        = "Beer"
    STAGECOACH  = "Stagecoach"
    WELLS_FARGO = "Wells Fargo"
    CAT_BALOU   = "Cat Balou"
    PANIC       = "Panic!"
    INDIANS     = "Indians!"
    GATLING     = "Gatling"
    SALOON      = "Saloon"
    GEN_STORE   = "Gen. Store"
    DUEL        = "Duel"
    # Blue – stay in play
    VOLCANIC    = "Volcanic"
    SCHOFIELD   = "Schofield"
    REMINGTON   = "Remington"
    CARABINE    = "Rev. Carabine"
    WINCHESTER  = "Winchester"
    BARREL      = "Barrel"
    SCOPE       = "Scope"
    MUSTANG     = "Mustang"
    JAIL        = "Jail"
    DYNAMITE    = "Dynamite"


BLUE_TYPES = {
    CardType.VOLCANIC, CardType.SCHOFIELD, CardType.REMINGTON,
    CardType.CARABINE, CardType.WINCHESTER, CardType.BARREL,
    CardType.SCOPE, CardType.MUSTANG, CardType.JAIL, CardType.DYNAMITE,
}

GUN_RANGE = {
    CardType.VOLCANIC:  1,
    CardType.SCHOFIELD: 2,
    CardType.REMINGTON: 3,
    CardType.CARABINE:  4,
    CardType.WINCHESTER: 5,
}

CARD_NAMES_KO = {
    CardType.BANG:        "BANG!",
    CardType.MISSED:      "Missed!",
    CardType.BEER:        "맥주",
    CardType.STAGECOACH:  "역마차",
    CardType.WELLS_FARGO: "웰스 파고",
    CardType.CAT_BALOU:   "캣 발루",
    CardType.PANIC:       "패닉!",
    CardType.INDIANS:     "인디언!",
    CardType.GATLING:     "개틀링",
    CardType.SALOON:      "살롱",
    CardType.GEN_STORE:   "잡화점",
    CardType.DUEL:        "결투",
    CardType.VOLCANIC:    "볼케이닉",
    CardType.SCHOFIELD:   "스코필드",
    CardType.REMINGTON:   "레밍턴",
    CardType.CARABINE:    "카라빈",
    CardType.WINCHESTER:  "윈체스터",
    CardType.BARREL:      "나무통",
    CardType.SCOPE:       "조준경",
    CardType.MUSTANG:     "무스탕",
    CardType.JAIL:        "감옥",
    CardType.DYNAMITE:    "다이너마이트",
}

CARD_DESC_KO = {
    CardType.BANG:        "사거리 내 플레이어 1명 공격",
    CardType.MISSED:      "BANG! 공격 회피 (반응용)",
    CardType.BEER:        "HP 1 회복 (2명 이하 사용불가)",
    CardType.STAGECOACH:  "카드 2장 드로우",
    CardType.WELLS_FARGO: "카드 3장 드로우",
    CardType.CAT_BALOU:   "누구의 카드든 1장 버리게 함",
    CardType.PANIC:       "거리 1의 플레이어 카드 1장 훔침",
    CardType.INDIANS:     "모든 플레이어 BANG! 내거나 -1HP",
    CardType.GATLING:     "모든 플레이어 Missed! 내거나 -1HP",
    CardType.SALOON:      "모든 플레이어 HP 1 회복",
    CardType.GEN_STORE:   "인원수만큼 카드 공개, 차례로 선택",
    CardType.DUEL:        "지목한 플레이어와 BANG! 대결",
    CardType.VOLCANIC:    "장착: 매 턴 BANG! 무제한 사용",
    CardType.SCHOFIELD:   "장착: 공격 사거리 2",
    CardType.REMINGTON:   "장착: 공격 사거리 3",
    CardType.CARABINE:    "장착: 공격 사거리 4",
    CardType.WINCHESTER:  "장착: 공격 사거리 5",
    CardType.BARREL:      "장착: 공격받을 때 ♥카드 뽑으면 Missed!",
    CardType.SCOPE:       "장착: 타인 거리 -1 (가깝게 보임)",
    CardType.MUSTANG:     "장착: 타인에게 내 거리 +1",
    CardType.JAIL:        "보안관 외 플레이어에게 장착, ♥ 아니면 턴 스킵",
    CardType.DYNAMITE:    "장착: 턴 시작 시 2-9♠면 3데미지 폭발",
}


@dataclass
class Card:
    """A single physical playing card: a type (what it does), a suit and
    a value (used by suit/value-dependent effects like Dynamite or Jail)."""
    card_type: CardType
    suit: Suit
    value: int   # 1=Ace … 13=King

    @property
    def is_blue(self):
        return self.card_type in BLUE_TYPES

    @property
    def is_gun(self):
        return self.card_type in GUN_RANGE

    @property
    def gun_range(self):
        return GUN_RANGE.get(self.card_type, 0)

    @property
    def name(self):
        return CARD_NAMES_KO[self.card_type]

    @property
    def desc(self):
        return CARD_DESC_KO[self.card_type]

    def __repr__(self):
        return f"{self.name}({self.suit.value}{self.value})"


def build_deck() -> list[Card]:
    cards = []

    def add(ct, suit, value):
        cards.append(Card(ct, suit, value))

    T, S = CardType, Suit

    # BANG! – 25
    for v in range(1, 14):   add(T.BANG, S.SPADES, v)     # 13
    for v in range(1, 10):   add(T.BANG, S.DIAMONDS, v)   # 9
    for v in [1, 2]:          add(T.BANG, S.CLUBS, v)      # 2
    add(T.BANG, S.HEARTS, 1)                               # 1  → total 25

    # Missed! – 12
    for v in range(2, 10):    add(T.MISSED, S.CLUBS, v)    # 8
    for v in [10, 11]:        add(T.MISSED, S.SPADES, v)   # 2
    for v in [10, 11]:        add(T.MISSED, S.HEARTS, v)   # 2  → 12

    # Beer – 6
    for v in range(6, 12):    add(T.BEER, S.HEARTS, v)

    # Stagecoach – 2
    add(T.STAGECOACH, S.SPADES, 9)
    add(T.STAGECOACH, S.CLUBS,  9)

    # Wells Fargo – 1
    add(T.WELLS_FARGO, S.HEARTS, 3)

    # Cat Balou – 4
    for v in [9, 10, 11, 13]: add(T.CAT_BALOU, S.DIAMONDS, v)

    # Panic! – 4
    add(T.PANIC, S.HEARTS, 11); add(T.PANIC, S.HEARTS, 12)
    add(T.PANIC, S.DIAMONDS, 1); add(T.PANIC, S.DIAMONDS, 8)

    # Indians! – 2
    add(T.INDIANS, S.DIAMONDS, 13); add(T.INDIANS, S.CLUBS, 13)

    # Gatling – 1
    add(T.GATLING, S.HEARTS, 10)

    # Saloon – 1
    add(T.SALOON, S.HEARTS, 5)

    # General Store – 2
    add(T.GEN_STORE, S.CLUBS, 9); add(T.GEN_STORE, S.SPADES, 12)

    # Duel – 3
    add(T.DUEL, S.CLUBS, 11); add(T.DUEL, S.CLUBS, 12); add(T.DUEL, S.SPADES, 1)

    # Equipment
    add(T.VOLCANIC,  S.SPADES, 10); add(T.VOLCANIC,  S.CLUBS,  10)
    add(T.SCHOFIELD, S.CLUBS,  11); add(T.SCHOFIELD, S.SPADES, 12); add(T.SCHOFIELD, S.HEARTS, 12)
    add(T.REMINGTON, S.CLUBS,  13)
    add(T.CARABINE,  S.DIAMONDS, 1)
    add(T.WINCHESTER,S.SPADES,  8)
    add(T.BARREL,    S.SPADES, 12); add(T.BARREL,    S.SPADES, 13)
    add(T.SCOPE,     S.SPADES, 13)
    add(T.MUSTANG,   S.HEARTS,  8); add(T.MUSTANG,   S.HEARTS,  9)
    add(T.JAIL,      S.SPADES, 11); add(T.JAIL,      S.SPADES, 12); add(T.JAIL, S.HEARTS, 4)
    add(T.DYNAMITE,  S.HEARTS,  2)

    random.shuffle(cards)
    return cards
