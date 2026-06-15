"""Rule-based AI for Bang! — character-aware."""
from __future__ import annotations
import random
from cards import CardType
from roles import Role
from characters import CharacterType
from game_state import GameState, Phase, RespType


class BangAI:
    def __init__(self, pid: int):
        self.pid = pid

    # ─────────────────────────────────────────────────────────────────────
    # PLAY phase decision
    # ─────────────────────────────────────────────────────────────────────
    def choose_action(self, gs: GameState) -> tuple | None:
        p    = gs.players[self.pid]
        role = p.role

        # Priority 1: Beer if HP critical
        beer = self._find(p, CardType.BEER)
        if beer is not None and p.hp <= 1 and p.hp < p.max_hp and len(gs._alive_ids()) > 2:
            return ("play", beer)

        # Priority 2: Sid Ketchum heal
        if p.character == CharacterType.SID_KETCHUM and p.hp < p.max_hp and len(p.hand) >= 3:
            i1, i2 = self._worst_two(p.hand)
            if i1 >= 0 and i2 >= 0:
                return ("sid_ketchum", i1, i2)

        # Priority 3: Equip useful cards
        action = self._equip(gs)
        if action:
            return action

        # Priority 4: Shoot enemy
        action = self._shoot(gs, role)
        if action:
            return action

        # Priority 5: Area cards
        action = self._area(gs, role)
        if action:
            return action

        # Priority 6: Draw cards
        for ct in (CardType.WELLS_FARGO, CardType.STAGECOACH):
            idx = self._find(p, ct)
            if idx is not None:
                return ("play", idx)

        # Priority 7: Beer (non-critical heal)
        beer = self._find(p, CardType.BEER)
        if beer is not None and p.hp < p.max_hp and len(gs._alive_ids()) > 2:
            return ("play", beer)

        return ("end_turn",)

    def _find(self, player, ct: CardType) -> int | None:
        for i, c in enumerate(player.hand):
            if c.card_type == ct:
                return i
        return None

    def _enemies(self, gs: GameState) -> list[int]:
        role  = gs.players[self.pid].role
        alive = gs._alive_ids()
        if role == Role.SHERIFF:
            return [i for i in alive if i != self.pid
                    and gs.players[i].role in (Role.OUTLAW, Role.RENEGADE)]
        if role == Role.DEPUTY:
            return [i for i in alive if i != self.pid
                    and gs.players[i].role == Role.OUTLAW]
        if role == Role.OUTLAW:
            sh = next((i for i in alive if gs.players[i].role == Role.SHERIFF), None)
            return [sh] if sh else [i for i in alive if i != self.pid
                                    and gs.players[i].role != Role.OUTLAW]
        # Renegade
        if len(alive) <= 2:
            return [i for i in alive if i != self.pid]
        return [i for i in alive if i != self.pid
                and gs.players[i].role == Role.OUTLAW]

    def _known_enemies(self, gs: GameState) -> list[int]:
        enemies = self._enemies(gs)
        known = [i for i in enemies if gs.players[i].role_revealed]
        return known or [i for i in gs._alive_ids() if i != self.pid]

    def _shoot(self, gs: GameState, role: Role) -> tuple | None:
        p = gs.players[self.pid]
        # Calamity Janet: Missed! can be used as BANG!
        bang_candidates = [i for i, c in enumerate(p.hand)
                           if c.card_type == CardType.BANG
                           or (p.is_calamity_janet() and c.card_type == CardType.MISSED)]
        if not bang_candidates:
            return None
        if not p.has_volcanic() and gs.bang_used:
            return None
        targets = gs.valid_bang_targets(self.pid)
        if not targets:
            return None
        enemies = self._known_enemies(gs)
        preferred = [t for t in targets if t in enemies]
        target = preferred[0] if preferred else targets[0]
        return ("play", bang_candidates[0], target)

    def _area(self, gs: GameState, role: Role) -> tuple | None:
        p      = gs.players[self.pid]
        alive  = gs._alive_ids()
        enemies = self._known_enemies(gs)

        if len(enemies) >= 2:
            idx = self._find(p, CardType.INDIANS)
            if idx is not None:
                return ("play", idx)
            idx = self._find(p, CardType.GATLING)
            if idx is not None and len(alive) - 1 >= 2:
                return ("play", idx)

        idx = self._find(p, CardType.DUEL)
        if idx is not None and enemies:
            return ("play", idx, enemies[0])
        return None

    def _equip(self, gs: GameState) -> tuple | None:
        p = gs.players[self.pid]
        for i, c in enumerate(p.hand):
            if c.is_gun and c.gun_range > p.gun_range():
                return ("play", i)
            if c.card_type == CardType.BARREL and not p.has_barrel():
                return ("play", i)
            if c.card_type == CardType.SCOPE and not p.has_scope():
                return ("play", i)
            if c.card_type == CardType.MUSTANG and not p.has_mustang():
                return ("play", i)
            if c.card_type == CardType.DYNAMITE and not p.has_dynamite() and p.hp > 2:
                return ("play", i)
        return None

    def _worst_two(self, hand) -> tuple[int, int]:
        priority = {CardType.MISSED: 0, CardType.BEER: 1}
        scored   = [(priority.get(c.card_type, 5), i) for i, c in enumerate(hand)]
        scored.sort()
        if len(scored) < 2:
            return -1, -1
        return scored[0][1], scored[1][1]

    # ─────────────────────────────────────────────────────────────────────
    # Response decisions
    # ─────────────────────────────────────────────────────────────────────
    def choose_response(self, gs: GameState) -> tuple:
        p = gs.players[self.pid]
        if gs.resp_type == RespType.INDIANS:
            bangs = p.get_bang_cards()
            if bangs:
                return ("missed", bangs[0])
            return ("take_hit",)
        else:
            misses = p.get_missed_cards()
            if misses:
                return ("missed", misses[0])
            return ("take_hit",)

    def choose_duel_response(self, gs: GameState) -> tuple:
        p     = gs.players[self.pid]
        bangs = p.get_bang_cards()
        return ("bang", bangs[0]) if bangs else ("take_hit",)

    def choose_gen_store(self, gs: GameState) -> int:
        pile = gs.gen_store_pile
        if not pile:
            return 0
        prefer = (CardType.BANG, CardType.BEER, CardType.STAGECOACH, CardType.WELLS_FARGO)
        for i, c in enumerate(pile):
            if c.card_type in prefer:
                return i
        return 0

    # ── Beer save ─────────────────────────────────────────────────────────
    def should_use_beer_save(self, gs: GameState) -> bool:
        return True  # AI always uses Beer to survive

    # ── Character special draw ────────────────────────────────────────────
    def jesse_jones_target(self, gs: GameState) -> int | None:
        """Return a target to steal from, or None to draw from deck."""
        enemies = self._known_enemies(gs)
        alive   = gs._alive_ids()
        # Prefer enemies with big hands
        candidates = enemies if enemies else [i for i in alive if i != self.pid]
        if not candidates:
            return None
        best = max(candidates, key=lambda i: len(gs.players[i].hand))
        if len(gs.players[best].hand) == 0:
            return None
        return best

    def pedro_ramirez_from_discard(self, gs: GameState) -> bool:
        """True if Pedro should draw from discard pile."""
        if not gs.discard:
            return False
        top = gs.discard[-1]
        useful = {CardType.BANG, CardType.BEER, CardType.STAGECOACH,
                  CardType.WELLS_FARGO, CardType.MISSED}
        return top.card_type in useful

    def kit_carlson_picks(self, gs: GameState) -> list[int]:
        """Return 2 indices from kit_peek_cards to keep."""
        pile = gs.kit_peek_cards
        scored = []
        prefer = {
            CardType.BANG: 5, CardType.BEER: 4, CardType.STAGECOACH: 4,
            CardType.WELLS_FARGO: 4, CardType.MISSED: 3, CardType.GATLING: 3,
        }
        for i, c in enumerate(pile):
            scored.append((prefer.get(c.card_type, 2), i))
        scored.sort(reverse=True)
        return [scored[0][1], scored[1][1]] if len(scored) >= 2 else list(range(len(scored)))
