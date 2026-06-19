from enum import Enum
from dataclasses import dataclass
import random


class Suit(Enum):
    """카드가 가질 수 있는 4가지 무늬(♥♦♣♠) 중 하나."""
    HEARTS   = "♥"
    DIAMONDS = "♦"
    CLUBS    = "♣"
    SPADES   = "♠"


class CardType(Enum):
    """80장 덱에 포함된 모든 카드 종류 — 사용 후 버려지는 갈색(brown) 카드와
    계속 장착되어 있는 파란색(blue) 장비 카드로 나뉜다 (아래 BLUE_TYPES 참고)."""
    # 갈색 – 사용 후 버림
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
    # 파란색 – 장착 유지
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
    """실제 카드 한 장을 나타낸다: 효과를 결정하는 카드 종류(card_type),
    무늬(suit), 숫자(value)로 구성되며, 무늬·숫자는 다이너마이트나 감옥처럼
    그 값에 따라 결과가 달라지는 효과에 쓰인다."""
    card_type: CardType
    suit: Suit
    value: int   # 1=에이스 … 13=킹

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

    # BANG! – 25장
    for v in range(1, 14):   add(T.BANG, S.SPADES, v)     # 13장
    for v in range(1, 10):   add(T.BANG, S.DIAMONDS, v)   # 9장
    for v in [1, 2]:          add(T.BANG, S.CLUBS, v)      # 2장
    add(T.BANG, S.HEARTS, 1)                               # 1장  → 총 25장

    # Missed! – 12장
    for v in range(2, 10):    add(T.MISSED, S.CLUBS, v)    # 8장
    for v in [10, 11]:        add(T.MISSED, S.SPADES, v)   # 2장
    for v in [10, 11]:        add(T.MISSED, S.HEARTS, v)   # 2장  → 12장

    # 맥주 – 6장
    for v in range(6, 12):    add(T.BEER, S.HEARTS, v)

    # 역마차 – 2장
    add(T.STAGECOACH, S.SPADES, 9)
    add(T.STAGECOACH, S.CLUBS,  9)

    # 웰스 파고 – 1장
    add(T.WELLS_FARGO, S.HEARTS, 3)

    # 캣 발루 – 4장
    for v in [9, 10, 11, 13]: add(T.CAT_BALOU, S.DIAMONDS, v)

    # 패닉! – 4장
    add(T.PANIC, S.HEARTS, 11); add(T.PANIC, S.HEARTS, 12)
    add(T.PANIC, S.DIAMONDS, 1); add(T.PANIC, S.DIAMONDS, 8)

    # 인디언! – 2장
    add(T.INDIANS, S.DIAMONDS, 13); add(T.INDIANS, S.CLUBS, 13)

    # 개틀링 – 1장
    add(T.GATLING, S.HEARTS, 10)

    # 살롱 – 1장
    add(T.SALOON, S.HEARTS, 5)

    # 잡화점 – 2장
    add(T.GEN_STORE, S.CLUBS, 9); add(T.GEN_STORE, S.SPADES, 12)

    # 결투 – 3장
    add(T.DUEL, S.CLUBS, 11); add(T.DUEL, S.CLUBS, 12); add(T.DUEL, S.SPADES, 1)

    # 장비
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
