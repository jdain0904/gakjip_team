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

    hand: list[Card] = field(default_factory=list)
    equipment: list[Card] = field(default_factory=list)  # blue cards in play

    alive: bool = True
    role_revealed: bool = False   # True when sheriff or when eliminated
    jailed: bool = False          # currently in jail

    # Track which jail card is placed on this player
    jail_card: Optional[Card] = None

    def has_barrel(self) -> bool:
        return any(c.card_type == CardType.BARREL for c in self.equipment)

    def has_scope(self) -> bool:
        return any(c.card_type == CardType.SCOPE for c in self.equipment)

    def has_mustang(self) -> bool:
        return any(c.card_type == CardType.MUSTANG for c in self.equipment)

    def has_volcanic(self) -> bool:
        return any(c.card_type == CardType.VOLCANIC for c in self.equipment)

    def has_dynamite(self) -> bool:
        return any(c.card_type == CardType.DYNAMITE for c in self.equipment)

    def get_dynamite(self) -> Optional[Card]:
        return next((c for c in self.equipment if c.card_type == CardType.DYNAMITE), None)

    def gun_range(self) -> int:
        for c in self.equipment:
            if c.is_gun:
                return c.gun_range
        return 1

    def hand_limit(self) -> int:
        return max(1, self.hp)

    def take_damage(self, amount: int = 1) -> bool:
        """Returns True if player died."""
        self.hp = max(0, self.hp - amount)
        return self.hp <= 0

    def heal(self, amount: int = 1):
        self.hp = min(self.max_hp, self.hp + amount)

    def get_missed_cards(self) -> list[int]:
        """Indices of Missed! cards in hand."""
        return [i for i, c in enumerate(self.hand) if c.card_type == CardType.MISSED]

    def get_bang_cards(self) -> list[int]:
        return [i for i, c in enumerate(self.hand) if c.card_type == CardType.BANG]

    def equip(self, card: Card):
        """Replace existing gun / unique equipment if needed."""
        if card.is_gun:
            self.equipment = [c for c in self.equipment if not c.is_gun]
        # Only one barrel, scope, mustang each
        self.equipment = [c for c in self.equipment if c.card_type != card.card_type]
        self.equipment.append(card)

    def remove_equipment(self, card: Card):
        if card in self.equipment:
            self.equipment.remove(card)

    def all_cards(self) -> list[Card]:
        """All cards that can be targeted by Cat Balou / Panic!"""
        return self.hand + self.equipment + ([self.jail_card] if self.jail_card else [])
