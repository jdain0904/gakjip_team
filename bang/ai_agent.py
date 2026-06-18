"""Bang! AI — three difficulty tiers.

쉬움(Easy)   — pure random play.
보통(Medium) — dynamic difficulty adjustment. At every decision point,
    asks winrate_model.WinRateModel for the human side's current
    predicted win probability p and plays the EV-optimal action when
    p >= 0.5 (human winning — raise the challenge), or eases off to
    the next-best action when p < 0.5 (human losing — ease off).
어려움(Hard) — always the EV-optimal action (rank 0), scored with
    weights learned by reinforcement learning over self-play (see
    record_game_result() and train_ai.py).
"""
from __future__ import annotations
import random
import json
from pathlib import Path
from cards import CardType
from roles import Role
from characters import CharacterType
from game_state import GameState, Phase, RespType
from ai_probability import CardCounter
from ai_strategy import score_play_actions, score_gen_store_card
from ai_features import state_vector
from winrate_model import WinRateModel

WEIGHTS_FILE  = Path(__file__).parent / "ai_weights.json"
BASELINE_FILE = Path(__file__).parent / "ai_baseline.json"

_winrate_model: WinRateModel | None = None
_winrate_model_loaded = False


def _load_baseline() -> float:
    try:
        with open(BASELINE_FILE) as f:
            return float(json.load(f)["baseline_winrate"])
    except Exception:
        return 0.5


def _save_baseline(v: float):
    try:
        with open(BASELINE_FILE, "w", encoding="utf-8") as f:
            json.dump({"baseline_winrate": v}, f)
    except Exception:
        pass


# Running baseline for the Hard AI's reward signal — see record_game_result().
# Persisted across interactive sessions (not self-play, which always starts
# fresh) so the EMA doesn't reset to 0.5 every time the game is relaunched.
_baseline_winrate = _load_baseline()


def _get_winrate_model() -> WinRateModel | None:
    """Lazy-loaded singleton — avoids re-reading winrate_model.json per AI instance."""
    global _winrate_model, _winrate_model_loaded
    if not _winrate_model_loaded:
        _winrate_model = WinRateModel.load()
        _winrate_model_loaded = True
    return _winrate_model


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
    """Decision-maker for one AI-controlled seat. Given a difficulty (0-2,
    see the module docstring above), its choose_* methods inspect the
    current GameState and return the action it wants to take; Hard
    difficulty also learns across games via record_game_result()."""
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
    def record_game_result(self, won: bool, persist: bool = True):
        """Call after game over to update Hard AI weights.

        This is the policy-improvement step of an every-visit Monte
        Carlo control over the linear scoring function in
        ai_strategy.score_play_actions: every feature tag this game's
        policy actually fired (self._history) gets nudged toward the
        actions that led to a win and away from the ones that led to
        a loss. train_ai.py runs this at self-play scale and disables
        `persist` so many self-play AI instances sharing one weights
        dict don't clobber each other's update with redundant disk
        writes — it saves once itself after applying every instance's
        update for a game.

        The reward is centered on a running win-rate baseline (a
        REINFORCE-style variance-reduction baseline) instead of a raw
        +1/-0.5 split. Without centering, a feature fired by winners
        and losers alike would still drift in one fixed direction
        purely because a multi-player game's per-seat win rate sits
        well below 50% (most games have more losers than winners),
        swamping any real signal about which actions are actually
        good. Subtracting the baseline makes a feature's expected
        update ~0 unless it's genuinely over- or under-represented
        among winners.

        Each update also shrinks the weight back toward its
        DEFAULT_WEIGHTS value by a small `decay` fraction. Centering
        alone zeroes the *expected* per-touch update for a neutral
        feature, but over thousands of self-play games the remaining
        zero-mean noise is still an unbounded random walk that, sooner
        or later, drifts into the [0.5, 15.0] clamp and gets stuck —
        every feature would eventually saturate regardless of whether
        it actually matters, just on a long enough timeline. The decay
        term gives the random walk a restoring force back to its
        prior, so each weight settles at a stable equilibrium set by
        how strongly that feature's reward signal actually outweighs
        the pull of its default — proportional to lr/decay — rather
        than continuing to wander as more self-play games are added.
        """
        global _baseline_winrate
        if self.difficulty != 2 or not self._history:
            return
        lr      = 0.02
        decay   = 0.0015
        outcome = 1.0 if won else 0.0
        reward  = outcome - _baseline_winrate
        for feat in set(self._history):
            if feat in self._weights:
                default = DEFAULT_WEIGHTS.get(feat, 3.0)
                current = self._weights[feat]
                updated = current + lr * reward - decay * (current - default)
                self._weights[feat] = max(0.5, min(15.0, updated))
        _baseline_winrate += 0.01 * (outcome - _baseline_winrate)
        if persist:
            _save_weights(self._weights)
            _save_baseline(_baseline_winrate)
        self._history.clear()

    def _predict_human_winrate(self, gs: GameState) -> float:
        """DDA control signal: predicted win probability for the human side.

        Falls back to a neutral 0.5 (no adjustment) if the win-rate
        model hasn't been trained yet, or there's no human in this
        game at all (e.g. train_ai.py self-play).
        """
        model  = _get_winrate_model()
        humans = [i for i in gs._alive_ids() if i in gs.human_ids]
        if model is None or not humans:
            return 0.5
        return sum(model.predict_proba(state_vector(gs, h)) for h in humans) / len(humans)

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
            p_human = self._predict_human_winrate(gs)
            chosen  = ranked[0] if p_human >= 0.5 else (ranked[1] if len(ranked) > 1 else ranked[0])

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

        p_human  = self._predict_human_winrate(gs)
        take_hit = conserve if p_human >= 0.5 else not conserve
        return ("take_hit",) if take_hit else ("bang", bangs[0])

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

        p_human = self._predict_human_winrate(gs)
        return order[0] if p_human >= 0.5 else (order[1] if len(order) > 1 else order[0])

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
