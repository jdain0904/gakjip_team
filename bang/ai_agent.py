"""Rule-based AI for Bang! — three difficulty levels with learning support."""
from __future__ import annotations
import random
import json
from pathlib import Path
from cards import CardType
from roles import Role
from characters import CharacterType
from game_state import GameState, Phase, RespType
from ai_probability import CardCounter
from ai_strategy import score_play_actions, score_gen_store_card, pick_by_strength
import player_skill

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
    "jail":                 4.0,
    "gen_store":            2.5,
}


def _default_w(feat: str) -> float:
    return DEFAULT_WEIGHTS.get(feat, 3.0)


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
        return self._action_scored(gs)

    # ── Medium/Hard: probability-scored EV ranking ────────────────────────
    def _action_scored(self, gs: GameState) -> tuple:
        p = gs.players[self.pid]

        # Sid Ketchum heal is a deterministic utility play shared by both tiers
        if p.character == CharacterType.SID_KETCHUM and p.hp < p.max_hp and len(p.hand) >= 3:
            i1, i2 = self._worst_two(p.hand)
            if i1 >= 0 and i2 >= 0:
                return ("sid_ketchum", i1, i2)

        counter       = CardCounter(gs, self.pid)
        known_enemies = set(self._known_enemies(gs))
        known_allies  = self._known_allies(gs)
        w             = self._w if self.difficulty == 2 else _default_w
        ranked        = score_play_actions(gs, self.pid, counter, w, known_enemies, known_allies)

        if self.difficulty == 2:
            chosen = ranked[0]
        else:
            skill    = player_skill.load_skill()["skill"]
            strength = player_skill.strength_for_skill(skill)
            chosen   = pick_by_strength(ranked, strength)

        self._hist(chosen.feat)
        return chosen.tuple

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

    def _known_allies(self, gs: GameState) -> set[int]:
        """Players whose *revealed* role guarantees they share my win condition.

        This is the hard "stay faithful to my role" filter: harmful
        single-target cards skip anyone in this set outright, regardless
        of how attractive the EV score would otherwise be. Roles that
        aren't revealed yet are never assumed — only confirmed teammates
        count, exactly like a human player would only spare a partner
        once their role is actually known.
        """
        role   = gs.players[self.pid].role
        alive  = len(gs._alive_ids())
        allies: set[int] = set()
        for other in gs._alive_ids():
            if other == self.pid:
                continue
            op = gs.players[other]
            if not op.role_revealed:
                continue
            if role == Role.SHERIFF and op.role == Role.DEPUTY:
                allies.add(other)
            elif role == Role.DEPUTY and op.role in (Role.SHERIFF, Role.DEPUTY):
                allies.add(other)
            elif role == Role.OUTLAW and op.role == Role.OUTLAW:
                allies.add(other)
            elif role == Role.RENEGADE and alive > 2 and op.role in (Role.SHERIFF, Role.DEPUTY):
                # Classic Renegade play: let the Sheriff's side clear the Outlaws
                # first, only turn on them once it's down to a final 1-on-1.
                allies.add(other)
        return allies

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
        if self.difficulty == 0:
            return ("bang", bangs[0]) if bangs else ("take_hit",)
        if not bangs:
            return ("take_hit",)

        # Conserving the last BANG! is only correct when survival isn't on the line
        conserve = len(bangs) == 1 and p.hp >= 3
        if self.difficulty == 2:
            return ("take_hit",) if conserve else ("bang", bangs[0])

        skill    = player_skill.load_skill()["skill"]
        strength = player_skill.strength_for_skill(skill)
        if conserve and random.random() < strength:
            return ("take_hit",)
        return ("bang", bangs[0])

    def choose_gen_store(self, gs: GameState) -> int:
        pile = gs.gen_store_pile
        if not pile:
            return 0
        if self.difficulty == 0:
            return random.randrange(len(pile))

        p       = gs.players[self.pid]
        counter = CardCounter(gs, self.pid)
        w       = self._w if self.difficulty == 2 else _default_w
        order   = sorted(range(len(pile)),
                          key=lambda i: score_gen_store_card(pile[i], p, counter, w),
                          reverse=True)

        if self.difficulty == 2:
            return order[0]

        skill    = player_skill.load_skill()["skill"]
        strength = player_skill.strength_for_skill(skill)
        return pick_by_strength(order, strength)

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
