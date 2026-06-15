"""Rule-based AI for Bang! — three difficulty levels with learning support."""
from __future__ import annotations
import random
import json
from pathlib import Path
from cards import CardType
from roles import Role
from characters import CharacterType
from game_state import GameState, Phase, RespType

WEIGHTS_FILE = Path(__file__).parent / "ai_weights.json"

DEFAULT_WEIGHTS = {
    "shoot_kill":          10.0,
    "shoot_enemy_low_hp":   7.0,
    "shoot_enemy":          5.0,
    "shoot_unknown":        3.5,
    "indians_multi":        7.0,
    "gatling_multi":        6.0,
    "duel_enemy":           5.0,
    "panic_bighand":        5.0,
    "panic_steal":          3.5,
    "catbalou_equip":       4.5,
    "catbalou_hand":        3.0,
    "equip_gun":            4.0,
    "equip_barrel":         3.5,
    "equip_scope":          3.0,
    "equip_mustang":        2.5,
    "equip_dynamite":       1.5,
    "beer_critical":        9.0,
    "beer_low_hp":          4.0,
    "stagecoach":           3.5,
    "wells_fargo":          4.0,
    "saloon":               2.5,
}


def _load_weights() -> dict:
    try:
        with open(WEIGHTS_FILE) as f:
            data = json.load(f)
        w = DEFAULT_WEIGHTS.copy()
        w.update(data)
        return w
    except Exception:
        return DEFAULT_WEIGHTS.copy()


def _save_weights(w: dict):
    try:
        with open(WEIGHTS_FILE, "w", encoding="utf-8") as f:
            json.dump(w, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


class BangAI:
    def __init__(self, pid: int, difficulty: int = 1):
        """
        difficulty: 0 = 쉬움, 1 = 보통, 2 = 어려움
        Hard AI loads weights from disk and updates them after each game.
        """
        self.pid = pid
        self.difficulty = difficulty
        self._weights: dict = _load_weights() if difficulty == 2 else {}
        self._history: list[str] = []   # feature tags for weight updates (hard only)

    # ─────────────────────────────────────────────────────────────────────
    # Post-game learning (difficulty 2 only)
    # ─────────────────────────────────────────────────────────────────────
    def record_game_result(self, won: bool):
        """Call after game over to update Hard AI weights."""
        if self.difficulty != 2 or not self._history:
            return
        lr     = 0.06
        reward = 1.0 if won else -0.5
        for feat in set(self._history):
            if feat in self._weights:
                self._weights[feat] = max(0.5, min(15.0,
                    self._weights[feat] + lr * reward))
        _save_weights(self._weights)
        self._history.clear()

    def _hist(self, feat: str):
        if self.difficulty == 2:
            self._history.append(feat)

    def _w(self, feat: str) -> float:
        return self._weights.get(feat, DEFAULT_WEIGHTS.get(feat, 3.0))

    # ─────────────────────────────────────────────────────────────────────
    # PLAY phase — dispatch by difficulty
    # ─────────────────────────────────────────────────────────────────────
    def choose_action(self, gs: GameState) -> tuple | None:
        if self.difficulty == 0:
            return self._action_easy(gs)
        if self.difficulty == 2:
            return self._action_hard(gs)
        return self._action_medium(gs)

    # ── Easy: mostly random, rarely strategic ────────────────────────────
    def _action_easy(self, gs: GameState) -> tuple:
        p = gs.players[self.pid]

        # Only heal when about to die
        if p.hp == 1 and p.hp < p.max_hp and len(gs._alive_ids()) > 2:
            beer = self._find(p, CardType.BEER)
            if beer is not None:
                return ("play", beer)

        # 35% chance to just end turn (lazy)
        if random.random() < 0.35:
            return ("end_turn",)

        # Collect all currently playable cards
        playable = [i for i in range(len(p.hand)) if gs.can_play_card(self.pid, i)]
        if not playable:
            return ("end_turn",)

        ci   = random.choice(playable)
        card = p.hand[ci]

        if gs.cards_needing_target(card):
            targets = gs.valid_targets_for_card(self.pid, card)
            if not targets:
                return ("end_turn",)
            return ("play", ci, random.choice(targets))

        return ("play", ci)

    # ── Medium: solid rule-based (original behaviour) ────────────────────
    def _action_medium(self, gs: GameState) -> tuple:
        p    = gs.players[self.pid]
        role = p.role

        beer = self._find(p, CardType.BEER)
        if beer is not None and p.hp <= 1 and p.hp < p.max_hp and len(gs._alive_ids()) > 2:
            return ("play", beer)

        if p.character == CharacterType.SID_KETCHUM and p.hp < p.max_hp and len(p.hand) >= 3:
            i1, i2 = self._worst_two(p.hand)
            if i1 >= 0 and i2 >= 0:
                return ("sid_ketchum", i1, i2)

        action = self._equip(gs)
        if action:
            return action

        action = self._shoot(gs, role)
        if action:
            return action

        action = self._area(gs, role)
        if action:
            return action

        for ct in (CardType.WELLS_FARGO, CardType.STAGECOACH):
            idx = self._find(p, ct)
            if idx is not None:
                return ("play", idx)

        beer = self._find(p, CardType.BEER)
        if beer is not None and p.hp < p.max_hp and len(gs._alive_ids()) > 2:
            return ("play", beer)

        return ("end_turn",)

    # ── Hard: weighted scoring + learning ────────────────────────────────
    def _action_hard(self, gs: GameState) -> tuple:
        p    = gs.players[self.pid]
        role = p.role

        # Critical survival
        beer = self._find(p, CardType.BEER)
        if beer is not None and p.hp <= 1 and p.hp < p.max_hp and len(gs._alive_ids()) > 2:
            self._hist("beer_critical")
            return ("play", beer)

        # Sid Ketchum heal
        if p.character == CharacterType.SID_KETCHUM and p.hp < p.max_hp and len(p.hand) >= 3:
            i1, i2 = self._worst_two(p.hand)
            if i1 >= 0 and i2 >= 0:
                return ("sid_ketchum", i1, i2)

        # Try to finish off low-HP enemy first
        kill = self._hard_kill_shot(gs)
        if kill:
            return kill

        # Equip useful gear
        action = self._equip(gs)
        if action:
            return action

        # Area cards when advantageous
        action = self._hard_area(gs)
        if action:
            return action

        # Panic!/Cat Balou targeting
        action = self._hard_steal_discard(gs)
        if action:
            return action

        # Normal shooting (prefer enemies with lower HP)
        action = self._hard_shoot(gs, role)
        if action:
            return action

        # Draw cards
        for ct in (CardType.WELLS_FARGO, CardType.STAGECOACH):
            idx = self._find(p, ct)
            if idx is not None:
                return ("play", idx)

        # Saloon (heals everyone)
        idx = self._find(p, CardType.SALOON)
        if idx is not None and p.hp < p.max_hp:
            self._hist("saloon")
            return ("play", idx)

        # Non-critical beer
        if beer is not None and p.hp <= 2 and p.hp < p.max_hp and len(gs._alive_ids()) > 2:
            self._hist("beer_low_hp")
            return ("play", beer)

        return ("end_turn",)

    def _hard_kill_shot(self, gs: GameState) -> tuple | None:
        p = gs.players[self.pid]
        if not p.has_volcanic() and gs.bang_used:
            return None
        bang_candidates = [i for i, c in enumerate(p.hand)
                           if c.card_type == CardType.BANG
                           or (p.is_calamity_janet() and c.card_type == CardType.MISSED)]
        if not bang_candidates:
            return None
        enemies = self._known_enemies(gs)
        targets = gs.valid_bang_targets(self.pid)
        # Prefer enemies with exactly 1 HP (kill shot)
        for tid in targets:
            if tid in enemies and gs.players[tid].hp == 1:
                self._hist("shoot_kill")
                return ("play", bang_candidates[0], tid)
        return None

    def _hard_shoot(self, gs: GameState, role: Role) -> tuple | None:
        p = gs.players[self.pid]
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
        # Sort by: enemy + low HP first
        def sort_key(tid):
            is_enemy = tid in enemies
            hp       = gs.players[tid].hp
            return (-int(is_enemy), hp)
        targets.sort(key=sort_key)
        target = targets[0]
        feat = ("shoot_enemy_low_hp" if target in enemies and gs.players[target].hp <= 2
                else "shoot_enemy"   if target in enemies
                else "shoot_unknown")
        self._hist(feat)
        return ("play", bang_candidates[0], target)

    def _hard_area(self, gs: GameState, role: Role | None = None) -> tuple | None:
        p       = gs.players[self.pid]
        alive   = gs._alive_ids()
        enemies = self._known_enemies(gs)

        if len(enemies) >= 2:
            idx = self._find(p, CardType.INDIANS)
            if idx is not None:
                self._hist("indians_multi")
                return ("play", idx)
            idx = self._find(p, CardType.GATLING)
            if idx is not None and len(alive) - 1 >= 2:
                self._hist("gatling_multi")
                return ("play", idx)

        idx = self._find(p, CardType.DUEL)
        if idx is not None and enemies:
            # Only duel if we have 2+ bang cards (so we won't run dry)
            bangs = [c for c in p.hand if c.card_type in (CardType.BANG, CardType.MISSED)]
            if len(bangs) >= 2:
                target = min(enemies, key=lambda i: gs.players[i].hp)
                self._hist("duel_enemy")
                return ("play", idx, target)
        return None

    def _hard_steal_discard(self, gs: GameState) -> tuple | None:
        p       = gs.players[self.pid]
        enemies = self._known_enemies(gs)

        # Panic!: prefer enemy with biggest hand or valuable equipment
        pidx = self._find(p, CardType.PANIC)
        if pidx is not None:
            targets = gs.valid_panic_targets(self.pid)
            if targets:
                enemy_targets = [t for t in targets if t in enemies]
                pool = enemy_targets if enemy_targets else targets
                # Pick target with most cards total
                target = max(pool, key=lambda i: len(gs.players[i].all_cards()))
                all_c = gs.players[target].all_cards()
                if all_c:
                    feat = "panic_bighand" if len(all_c) >= 4 else "panic_steal"
                    self._hist(feat)
                    return ("play", pidx, target, random.randrange(len(all_c)))

        # Cat Balou: prefer removing enemy's Barrel/Scope/gun
        cbidx = self._find(p, CardType.CAT_BALOU)
        if cbidx is not None:
            targets = [i for i in gs._alive_ids()
                       if i != self.pid and gs.players[i].all_cards()]
            if targets:
                enemy_targets = [t for t in targets if t in enemies]
                pool = enemy_targets if enemy_targets else targets
                # Prefer targets with equipment
                equipped = [t for t in pool if gs.players[t].equipment]
                best = equipped[0] if equipped else pool[0]
                te   = gs.players[best]
                # Target a specific card: prefer removing barrel or gun
                all_c = te.all_cards()
                for i, c in enumerate(all_c):
                    if c.card_type in (CardType.BARREL, CardType.SCOPE) or c.is_gun:
                        self._hist("catbalou_equip")
                        return ("play", cbidx, best, i)
                self._hist("catbalou_hand")
                return ("play", cbidx, best, 0)

        return None

    # ─────────────────────────────────────────────────────────────────────
    # Shared helpers
    # ─────────────────────────────────────────────────────────────────────
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
        # Hard AI: don't exhaust all BANG!s if only 1 left and HP is OK
        if self.difficulty == 2 and len(bangs) == 1 and p.hp >= 3:
            return ("take_hit",)
        return ("bang", bangs[0]) if bangs else ("take_hit",)

    def choose_gen_store(self, gs: GameState) -> int:
        pile = gs.gen_store_pile
        if not pile:
            return 0

        if self.difficulty == 0:
            return random.randrange(len(pile))

        p = gs.players[self.pid]

        if self.difficulty == 2:
            # Hard: weigh each card by how useful it is right now
            best_i, best_s = 0, -1
            for i, c in enumerate(pile):
                score = 0.0
                if c.card_type == CardType.BANG:
                    score = self._w("shoot_enemy") if not gs.bang_used else 1.0
                elif c.card_type == CardType.BEER:
                    score = self._w("beer_critical") if p.hp <= 1 else self._w("beer_low_hp")
                elif c.card_type in (CardType.STAGECOACH, CardType.WELLS_FARGO):
                    score = self._w("stagecoach")
                elif c.card_type == CardType.MISSED:
                    score = 3.0
                elif c.is_gun and c.gun_range > p.gun_range():
                    score = self._w("equip_gun")
                elif c.card_type == CardType.BARREL and not p.has_barrel():
                    score = self._w("equip_barrel")
                else:
                    score = 2.0
                if score > best_s:
                    best_s, best_i = score, i
            return best_i

        # Medium: prefer useful cards
        prefer = (CardType.BANG, CardType.BEER, CardType.STAGECOACH, CardType.WELLS_FARGO)
        for i, c in enumerate(pile):
            if c.card_type in prefer:
                return i
        return 0

    # ── Beer save ─────────────────────────────────────────────────────────
    def should_use_beer_save(self, gs: GameState) -> bool:
        return True  # Always try to survive

    # ── Character special draw ────────────────────────────────────────────
    def jesse_jones_target(self, gs: GameState) -> int | None:
        enemies = self._known_enemies(gs)
        alive   = gs._alive_ids()
        candidates = enemies if enemies else [i for i in alive if i != self.pid]
        if not candidates:
            return None
        best = max(candidates, key=lambda i: len(gs.players[i].hand))
        if len(gs.players[best].hand) == 0:
            return None
        return best

    def pedro_ramirez_from_discard(self, gs: GameState) -> bool:
        if not gs.discard:
            return False
        top = gs.discard[-1]
        useful = {CardType.BANG, CardType.BEER, CardType.STAGECOACH,
                  CardType.WELLS_FARGO, CardType.MISSED}
        return top.card_type in useful

    def kit_carlson_picks(self, gs: GameState) -> list[int]:
        pile   = gs.kit_peek_cards
        prefer = {
            CardType.BANG: 5, CardType.BEER: 4, CardType.STAGECOACH: 4,
            CardType.WELLS_FARGO: 4, CardType.MISSED: 3, CardType.GATLING: 3,
        }
        scored = [(prefer.get(c.card_type, 2), i) for i, c in enumerate(pile)]
        scored.sort(reverse=True)
        return [scored[0][1], scored[1][1]] if len(scored) >= 2 else list(range(len(scored)))
