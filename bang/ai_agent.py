"""Rule-based AI for Bang!"""
from __future__ import annotations
import random
from cards import CardType
from roles import Role
from game_state import GameState, Phase, RespType


class BangAI:
    """Decides actions for one AI-controlled player."""

    def __init__(self, pid: int):
        self.pid = pid

    # ─────────────────────────────────────────────────────────────────────
    # Main decision – PLAY phase
    # ─────────────────────────────────────────────────────────────────────
    def choose_action(self, gs: GameState) -> tuple | None:
        """
        Returns one of:
          ('play', card_idx)                     – no target needed
          ('play', card_idx, target_id)          – needs target
          ('play', card_idx, target_id, tc_idx)  – Cat Balou / Panic! (target card)
          ('end_turn',)                          – end turn
        """
        p = gs.players[self.pid]
        role = p.role

        # Priority 1: Beer if HP <= 1
        beer = self._find_card(p, CardType.BEER)
        if beer is not None and p.hp <= 1 and p.hp < p.max_hp and len(gs._alive_ids()) > 2:
            return ('play', beer)

        # Priority 2: Equip useful cards
        action = self._equip_action(gs)
        if action:
            return action

        # Priority 3: Shoot an enemy
        action = self._bang_action(gs, role)
        if action:
            return action

        # Priority 4: Use mass-damage cards if they help
        action = self._area_action(gs, role)
        if action:
            return action

        # Priority 5: Draw cards
        sc = self._find_card(p, CardType.STAGECOACH)
        if sc is not None:
            return ('play', sc)
        wf = self._find_card(p, CardType.WELLS_FARGO)
        if wf is not None:
            return ('play', wf)

        # Priority 6: Heal if needed
        beer = self._find_card(p, CardType.BEER)
        if beer is not None and p.hp < p.max_hp and len(gs._alive_ids()) > 2:
            return ('play', beer)

        return ('end_turn',)

    def _find_card(self, player, ct: CardType) -> int | None:
        for i, c in enumerate(player.hand):
            if c.card_type == ct:
                return i
        return None

    def _enemy_ids(self, gs: GameState) -> list[int]:
        role = gs.players[self.pid].role
        alive = gs._alive_ids()
        if role == Role.SHERIFF:
            return [i for i in alive if i != self.pid and gs.players[i].role in (Role.OUTLAW, Role.RENEGADE)]
        if role == Role.DEPUTY:
            return [i for i in alive if i != self.pid and gs.players[i].role == Role.OUTLAW]
        if role == Role.OUTLAW:
            # Primary: sheriff; secondary: any non-outlaw
            sheriff = next((i for i in alive if gs.players[i].role == Role.SHERIFF), None)
            if sheriff:
                return [sheriff]
            return [i for i in alive if i != self.pid and gs.players[i].role != Role.OUTLAW]
        if role == Role.RENEGADE:
            alive_count = len(alive)
            if alive_count <= 2:
                # Last survivor attempt: target sheriff
                return [i for i in alive if i != self.pid]
            # Eliminate outlaws first, avoid attacking sheriff early
            return [i for i in alive if i != self.pid and gs.players[i].role == Role.OUTLAW]
        return []

    def _visible_enemies(self, gs: GameState) -> list[int]:
        """Enemies whose role is known (revealed or sheriff)."""
        enemies = self._enemy_ids(gs)
        known = [i for i in enemies if gs.players[i].role_revealed]
        if known:
            return known
        # Fall back to targeting unknown non-self players
        return [i for i in gs._alive_ids() if i != self.pid]

    def _bang_action(self, gs: GameState, role: Role) -> tuple | None:
        p = gs.players[self.pid]
        bang_idx = self._find_card(p, CardType.BANG)
        if bang_idx is None:
            return None
        if not p.has_volcanic() and gs.bang_used:
            return None
        targets = gs.valid_bang_targets(self.pid)
        if not targets:
            return None
        enemies = self._visible_enemies(gs)
        preferred = [t for t in targets if t in enemies]
        target = preferred[0] if preferred else targets[0]
        return ('play', bang_idx, target)

    def _area_action(self, gs: GameState, role: Role) -> tuple | None:
        p = gs.players[self.pid]
        alive = gs._alive_ids()
        enemies = self._visible_enemies(gs)

        # Indians: good when we have no BANG! or enemies outnumber us
        if len(enemies) >= 2:
            idx = self._find_card(p, CardType.INDIANS)
            if idx is not None:
                return ('play', idx)
            idx = self._find_card(p, CardType.GATLING)
            if idx is not None and len(alive) - 1 >= 2:
                return ('play', idx)

        # Duel: use against a visible enemy at any range
        idx = self._find_card(p, CardType.DUEL)
        if idx is not None and enemies:
            return ('play', idx, enemies[0])

        return None

    def _equip_action(self, gs: GameState) -> tuple | None:
        p = gs.players[self.pid]
        # Equip guns with range > current
        for i, c in enumerate(p.hand):
            if c.is_gun and c.gun_range > p.gun_range():
                return ('play', i)
            if c.card_type == CardType.BARREL and not p.has_barrel():
                return ('play', i)
            if c.card_type == CardType.SCOPE and not p.has_scope():
                return ('play', i)
            if c.card_type == CardType.MUSTANG and not p.has_mustang():
                return ('play', i)
            if c.card_type == CardType.DYNAMITE and not p.has_dynamite():
                # Only place dynamite when reasonably safe (HP > 2)
                if p.hp > 2:
                    return ('play', i)
        return None

    # ─────────────────────────────────────────────────────────────────────
    # Response decisions
    # ─────────────────────────────────────────────────────────────────────
    def choose_response(self, gs: GameState) -> tuple:
        """
        Returns ('missed', card_idx) or ('take_hit',).
        For INDIANS response, returns ('bang', card_idx) or ('take_hit',).
        """
        p = gs.players[self.pid]
        if gs.resp_type == RespType.INDIANS:
            bang_idx = self._find_card(p, CardType.BANG)
            if bang_idx is not None:
                return ('bang', bang_idx)
            return ('take_hit',)
        else:
            # BANG or GATLING – play Missed!
            miss_idx = self._find_card(p, CardType.MISSED)
            if miss_idx is not None:
                return ('missed', miss_idx)
            return ('take_hit',)

    def choose_duel_response(self, gs: GameState) -> tuple:
        p = gs.players[self.pid]
        bang_idx = self._find_card(p, CardType.BANG)
        if bang_idx is not None:
            return ('bang', bang_idx)
        return ('take_hit',)

    def choose_gen_store(self, gs: GameState) -> int:
        """Pick a card from the gen store pile. Returns index."""
        pile = gs.gen_store_pile
        if not pile:
            return 0
        # Prefer BANG! or beer, otherwise first
        for i, c in enumerate(pile):
            if c.card_type in (CardType.BANG, CardType.BEER,
                               CardType.STAGECOACH, CardType.WELLS_FARGO):
                return i
        return 0
