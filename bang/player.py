from dataclasses import dataclass, field
from typing import Optional
from cards import Card, CardType
from roles import Role


@dataclass
class Player:
    pid: int
    name: str
    role: Role
    is_human: bool

    max_hp: int = 4
    hp: int = 4

    character: Optional[object] = None   # CharacterType; Optional to avoid circular import

    hand: list[Card] = field(default_factory=list)
    equipment: list[Card] = field(default_factory=list)

    alive: bool = True
    role_revealed: bool = False
    jailed: bool = False
    jail_card: Optional[Card] = None

    # ── Character-aware equipment checks ──────────────────────────────────
    # Jourdonnais/Rose Doolan/Paul Regret each have a virtual copy of their
    # signature item "in play" at all times; the rulebook explicitly says
    # that if they *also* equip a real one, both count ("two chances to
    # cancel the BANG!", "reducing all distances by a total of 2", etc.) —
    # so these return a count, not just a boolean.
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

    # Calamity Janet: BANG! and Missed! are interchangeable
    def get_missed_cards(self) -> list[int]:
        """Indices of cards playable as Missed!"""
        if self.is_calamity_janet():
            return [i for i, c in enumerate(self.hand)
                    if c.card_type in (CardType.MISSED, CardType.BANG)]
        return [i for i, c in enumerate(self.hand) if c.card_type == CardType.MISSED]

    def get_bang_cards(self) -> list[int]:
        """Indices of cards playable as BANG!"""
        if self.is_calamity_janet():
            return [i for i, c in enumerate(self.hand)
                    if c.card_type in (CardType.BANG, CardType.MISSED)]
        return [i for i, c in enumerate(self.hand) if c.card_type == CardType.BANG]

    def equip(self, card: Card) -> list[Card]:
        """Equip `card`. Returns any equipment it bumps out of play (a new
        weapon replaces the old one, a card can't share a name with one
        already in play) — caller must move these to the discard pile."""
        removed = [c for c in self.equipment
                   if (card.is_gun and c.is_gun) or c.card_type == card.card_type]
        self.equipment = [c for c in self.equipment if c not in removed]
        self.equipment.append(card)
        return removed

    def remove_equipment(self, card: Card):
        if card in self.equipment:
            self.equipment.remove(card)

    def all_cards(self) -> list[Card]:
        # The jail card (if any) is already inside `equipment` — it's set
        # there by equip() at the same time `jail_card` is assigned, so
        # appending it again here would count the same physical card twice.
        return self.hand + self.equipment
