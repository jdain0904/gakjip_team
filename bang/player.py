from dataclasses import dataclass, field
from typing import Optional
from cards import Card, CardType
from roles import Role


@dataclass
class Player:
    """테이블의 한 자리를 나타낸다: 신원 정보(pid/이름/역할/캐릭터), 현재
    상태(체력, 손패, 장비, 감옥 상태)와, 다른 게임 로직이 각 캐릭터의 특수
    상황을 직접 알 필요 없이 사용할 수 있는 캐릭터 인지 조회 메서드(나무통/
    조준경/무스탕 개수, 사거리, 손패 제한 등)를 함께 가진다."""
    pid: int
    name: str
    role: Role
    is_human: bool

    max_hp: int = 4
    hp: int = 4

    character: Optional[object] = None   # CharacterType; 순환 임포트를 피하기 위해 Optional 처리

    hand: list[Card] = field(default_factory=list)
    equipment: list[Card] = field(default_factory=list)

    alive: bool = True
    role_revealed: bool = False
    jailed: bool = False
    jail_card: Optional[Card] = None

    # ── 캐릭터를 고려한 장비 확인 ──────────────────────────────────────────
    # 주르도네/로즈 둘란/폴 리그렛은 각자의 시그니처 아이템을 항상 가상으로
    # "장착 중인" 상태로 취급된다; 룰북에는 이들이 실제 카드를 *추가로*
    # 장착하면 둘 다 효과가 적용된다고 명시되어 있다 ("BANG!을 막을 기회가
    # 두 번", "모든 거리를 총 2만큼 줄임" 등) — 그래서 이 메서드들은 단순한
    # 불(bool)이 아니라 개수를 반환한다.
    def barrel_count(self) -> int:
        from characters import CharacterType
        n = sum(1 for c in self.equipment if c.card_type == CardType.BARREL)
        if self.character == CharacterType.JOURDONNAIS:
            n += 1
        return n

    def scope_count(self) -> int:
        from characters import CharacterType
        n = sum(1 for c in self.equipment if c.card_type == CardType.SCOPE)
        if self.character == CharacterType.ROSE_DOOLAN:
            n += 1
        return n

    def mustang_count(self) -> int:
        from characters import CharacterType
        n = sum(1 for c in self.equipment if c.card_type == CardType.MUSTANG)
        if self.character == CharacterType.PAUL_REGRET:
            n += 1
        return n

    def has_barrel(self) -> bool:
        return self.barrel_count() > 0

    def has_scope(self) -> bool:
        return self.scope_count() > 0

    def has_mustang(self) -> bool:
        return self.mustang_count() > 0

    def has_volcanic(self) -> bool:
        from characters import CharacterType
        if self.character == CharacterType.WILLY_KID:
            return True
        return any(c.card_type == CardType.VOLCANIC for c in self.equipment)

    def has_dynamite(self) -> bool:
        return any(c.card_type == CardType.DYNAMITE for c in self.equipment)

    def get_dynamite(self) -> Optional[Card]:
        return next((c for c in self.equipment if c.card_type == CardType.DYNAMITE), None)

    def is_slab_killer(self) -> bool:
        from characters import CharacterType
        return self.character == CharacterType.SLAB_KILLER

    def is_calamity_janet(self) -> bool:
        from characters import CharacterType
        return self.character == CharacterType.CALAMITY_JANET

    def is_lucky_duke(self) -> bool:
        from characters import CharacterType
        return self.character == CharacterType.LUCKY_DUKE

    def gun_range(self) -> int:
        for c in self.equipment:
            if c.is_gun:
                return c.gun_range
        return 1

    def hand_limit(self) -> int:
        return max(1, self.hp)

    def take_damage(self, amount: int = 1) -> bool:
        self.hp = max(0, self.hp - amount)
        return self.hp <= 0

    def heal(self, amount: int = 1):
        self.hp = min(self.max_hp, self.hp + amount)

    # 캘러미티 재닛: BANG!과 Missed!를 서로 대체해서 사용 가능
    def get_missed_cards(self) -> list[int]:
        """Missed!로 사용할 수 있는 카드들의 인덱스."""
        if self.is_calamity_janet():
            return [i for i, c in enumerate(self.hand)
                    if c.card_type in (CardType.MISSED, CardType.BANG)]
        return [i for i, c in enumerate(self.hand) if c.card_type == CardType.MISSED]

    def get_bang_cards(self) -> list[int]:
        """BANG!으로 사용할 수 있는 카드들의 인덱스."""
        if self.is_calamity_janet():
            return [i for i, c in enumerate(self.hand)
                    if c.card_type in (CardType.BANG, CardType.MISSED)]
        return [i for i, c in enumerate(self.hand) if c.card_type == CardType.BANG]

    def equip(self, card: Card) -> list[Card]:
        """`card`를 장착한다. 이로 인해 장착이 해제되는 장비가 있으면
        반환한다 (새 무기는 기존 무기를 대체하고, 같은 종류의 카드는 동시에
        장착될 수 없다) — 호출자는 이 카드들을 버림 더미로 옮겨야 한다."""
        removed = [c for c in self.equipment
                   if (card.is_gun and c.is_gun) or c.card_type == card.card_type]
        self.equipment = [c for c in self.equipment if c not in removed]
        self.equipment.append(card)
        return removed

    def remove_equipment(self, card: Card):
        if card in self.equipment:
            self.equipment.remove(card)

    def all_cards(self) -> list[Card]:
        # 감옥 카드(있다면)는 이미 `equipment` 안에 들어있다 — `jail_card`가
        # 할당되는 시점에 equip()에서 함께 거기 들어가므로, 여기서 다시
        # 추가하면 같은 실제 카드를 두 번 세게 된다.
        return self.hand + self.equipment
