"""Probability-driven expected-value scoring shared by the Medium and Hard AI.

Every legal action available to a player is scored from the same
playbook, using `ai_probability.CardCounter` to turn "cards already
played" + "cards I'm holding" into real odds. The two non-Easy
difficulties only differ in *which* ranked action they ultimately
commit to (see `pick_by_strength`):

  - Hard always takes rank 0 (the highest-scoring action).
  - Medium samples from the ranking with a strength in [0, 1] that
    tracks the human player's own decision quality (see player_skill.py).

Staying faithful to one's own role is treated as a hard constraint, not
a scoring preference: single-target harmful cards (BANG!, Duel, Cat
Balou, Panic!, Jail) simply skip any player already confirmed to be an
ally. Area cards (Indians!, Gatling) can't avoid hitting allies by the
game's own rules, so they're penalised for ally splash damage instead.
"""
from __future__ import annotations
import random
from cards import CardType, Suit
from ai_probability import CardCounter

VALUABLE_EQUIP = {
    CardType.BARREL, CardType.SCOPE, CardType.MUSTANG, CardType.VOLCANIC,
    CardType.SCHOFIELD, CardType.REMINGTON, CardType.CARABINE, CardType.WINCHESTER,
}

END_TURN_SCORE = 1.0


class Action:
    """One scored candidate move."""
    __slots__ = ("score", "tuple", "feat", "card_type", "target_id")

    def __init__(self, score, action_tuple, feat, card_type, target_id=-1):
        self.score     = score
        self.tuple     = action_tuple
        self.feat      = feat
        self.card_type = card_type
        self.target_id = target_id

    def __repr__(self):
        return f"Action({self.score:.2f}, {self.tuple}, {self.feat})"


def score_play_actions(gs, pid, counter: CardCounter, w, known_enemies: set[int],
                        known_allies: set[int]) -> list[Action]:
    """Score every legal play available to `pid` right now, plus 'end_turn'.

    Returns a list of `Action`s sorted by score, descending.
    """
    p     = gs.players[pid]
    out: list[Action] = []

    def is_enemy(tid):
        return tid in known_enemies

    for ci, card in enumerate(p.hand):
        if not gs.can_play_card(pid, ci):
            continue
        ct = card.card_type
        treat_as_bang = ct == CardType.BANG or (ct == CardType.MISSED and p.is_calamity_janet())

        if gs.cards_needing_target(card):
            for tid in gs.valid_targets_for_card(pid, card):
                if tid in known_allies:
                    continue
                if treat_as_bang:
                    score, feat = _score_bang(gs, tid, counter, w, is_enemy(tid))
                    out.append(Action(score, ("play", ci, tid), feat, CardType.BANG, tid))
                elif ct == CardType.DUEL:
                    score, feat = _score_duel(gs, pid, tid, counter, w, is_enemy(tid))
                    out.append(Action(score, ("play", ci, tid), feat, ct, tid))
                elif ct in (CardType.CAT_BALOU, CardType.PANIC):
                    tci, score, feat = _score_strip(tid, gs, counter, w, is_enemy(tid), ct)
                    out.append(Action(score, ("play", ci, tid, tci), feat, ct, tid))
                elif ct == CardType.JAIL:
                    score, feat = _score_jail(counter, w, is_enemy(tid))
                    out.append(Action(score, ("play", ci, tid), feat, ct, tid))
            continue

        # No-target plays
        if ct == CardType.BEER:
            score, feat = _score_beer(p, w)
            out.append(Action(score, ("play", ci), feat, ct))
        elif ct == CardType.STAGECOACH:
            out.append(Action(w("stagecoach"), ("play", ci), "stagecoach", ct))
        elif ct == CardType.WELLS_FARGO:
            out.append(Action(w("wells_fargo"), ("play", ci), "wells_fargo", ct))
        elif ct == CardType.GEN_STORE:
            out.append(Action(w("gen_store"), ("play", ci), "gen_store", ct))
        elif ct == CardType.INDIANS:
            score, feat = _score_area(gs, pid, counter, w, known_enemies, known_allies,
                                       "indians_multi", counter.prob_has_bang_equivalent)
            out.append(Action(score, ("play", ci), feat, ct))
        elif ct == CardType.GATLING:
            score, feat = _score_area(gs, pid, counter, w, known_enemies, known_allies,
                                       "gatling_multi", counter.prob_dodge)
            out.append(Action(score, ("play", ci), feat, ct))
        elif ct == CardType.SALOON:
            score, feat = _score_saloon(gs, pid, w, known_enemies, known_allies)
            out.append(Action(score, ("play", ci), feat, ct))
        elif card.is_gun:
            out.append(Action(_score_gun(p, card, w), ("play", ci), "equip_gun", ct))
        elif ct == CardType.BARREL:
            out.append(Action(w("equip_barrel"), ("play", ci), "equip_barrel", ct))
        elif ct == CardType.SCOPE:
            out.append(Action(w("equip_scope"), ("play", ci), "equip_scope", ct))
        elif ct == CardType.MUSTANG:
            out.append(Action(w("equip_mustang"), ("play", ci), "equip_mustang", ct))
        elif ct == CardType.DYNAMITE and p.hp > 2:
            score, feat = _score_dynamite(counter, w)
            out.append(Action(score, ("play", ci), feat, ct))

    out.append(Action(END_TURN_SCORE, ("end_turn",), "end_turn", None))
    out.sort(key=lambda a: a.score, reverse=True)
    return out


# ─────────────────────────────────────────────────────────────────────────
# Per-card-type scorers
# ─────────────────────────────────────────────────────────────────────────
def _score_bang(gs, tid, counter, w, enemy):
    target = gs.players[tid]
    dodge  = counter.prob_dodge(tid)
    hit    = 1.0 - dodge
    if target.hp <= 1:
        feat = "shoot_kill"
        base = w(feat) if enemy else w(feat) * 0.6
    elif enemy and target.hp <= 2:
        feat, base = "shoot_enemy_low_hp", w("shoot_enemy_low_hp")
    elif enemy:
        feat, base = "shoot_enemy", w("shoot_enemy")
    else:
        feat, base = "shoot_unknown", w("shoot_unknown")
    return base * hit - dodge * 1.0, feat


def _score_duel(gs, pid, tid, counter, w, enemy):
    p         = gs.players[pid]
    my_bangs  = len(p.get_bang_cards())
    their_p   = counter.prob_has_bang_equivalent(tid)
    win_p     = max(0.05, min(0.95, 0.5 + 0.15 * my_bangs - 0.3 * their_p))
    feat      = "duel_enemy"
    base      = w(feat) if enemy else w(feat) * 0.6
    return base * win_p - (1 - win_p) * 1.0, feat


def _score_strip(tid, gs, counter, w, enemy, ct):
    """Choose which card to take from `tid` (Panic!/Cat Balou) and score it."""
    target = gs.players[tid]
    all_c  = target.all_cards()
    equip_idx = next((i for i, c in enumerate(all_c) if c.card_type in VALUABLE_EQUIP), None)
    feat_equip = "panic_bighand" if ct == CardType.PANIC else "catbalou_equip"
    feat_hand  = "panic_steal"   if ct == CardType.PANIC else "catbalou_hand"

    if equip_idx is not None:
        removed = all_c[equip_idx]
        value   = 4.0 if removed.is_gun else 3.5 if removed.card_type == CardType.BARREL else 3.0
        return equip_idx, value * (1.3 if enemy else 0.75), feat_equip

    if target.hand:
        tci  = random.randrange(len(target.hand))
        base = 2.0 + 3.0 * counter.prob_useful_hand_card(tid)
        return tci, base * (1.25 if enemy else 0.7), feat_hand

    # Only low-value equipment remains (e.g. Jail/Dynamite) — still take it, low priority
    return 0, 1.0 * (1.1 if enemy else 0.6), feat_equip


def _score_jail(counter, w, enemy):
    p_skip = 1.0 - counter.prob_escape_jail()
    return w("jail") * p_skip * (1.3 if enemy else 0.4), "jail"


def _score_area(gs, pid, counter, w, known_enemies, known_allies, feat, dodge_prob_fn):
    """Shared EV model for Indians!/Gatling: both hit every other living player
    who can't produce the right card, and neither one risks the player who plays it.
    """
    enemy_hits = ally_hits = neutral_hits = 0.0
    for tid in gs._alive_ids():
        if tid == pid:
            continue
        p_hit = 1.0 - dodge_prob_fn(tid)
        if tid in known_allies:
            ally_hits += p_hit
        elif tid in known_enemies:
            enemy_hits += p_hit
        else:
            neutral_hits += p_hit
    base  = w(feat)
    score = enemy_hits * base - ally_hits * base * 1.2 + neutral_hits * base * 0.3
    return score, feat


def _score_saloon(gs, pid, w, known_enemies, known_allies):
    self_heal = ally_heal = enemy_heal = 0.0
    for tid in gs._alive_ids():
        pl      = gs.players[tid]
        missing = pl.max_hp - pl.hp
        if missing <= 0:
            continue
        gain = min(1, missing)
        if tid == pid:
            self_heal += gain
        elif tid in known_allies:
            ally_heal += gain
        elif tid in known_enemies:
            enemy_heal += gain
    base  = w("saloon")
    score = (self_heal + ally_heal) * base - enemy_heal * base * 0.7
    return score, "saloon"


def _score_beer(p, w):
    if p.hp <= 1:
        return w("beer_critical"), "beer_critical"
    urgency = 1.0 - (p.hp - 1) / max(1, p.max_hp - 1)
    return w("beer_low_hp") * urgency, "beer_low_hp"


def _score_gun(p, card, w):
    upgrade = card.gun_range > p.gun_range()
    if card.card_type == CardType.VOLCANIC and not p.has_volcanic():
        return w("equip_gun") + (1.5 if not upgrade else 0.5)
    return w("equip_gun") if upgrade else w("equip_gun") * 0.3


def _score_dynamite(counter, w):
    p_explode = counter.prob_dynamite_explodes()
    return w("equip_dynamite") * (1.0 - p_explode), "equip_dynamite"


def score_gen_store_card(c, player, counter, w) -> float:
    """Mirror of the play-phase scoring logic, applied to a face-up General Store card."""
    ct = c.card_type
    if ct == CardType.BANG:
        return w("shoot_enemy")
    if ct == CardType.MISSED:
        return 4.0 if player.hp <= 2 else 2.5
    if ct == CardType.BEER:
        return w("beer_critical") if player.hp <= 1 else w("beer_low_hp")
    if ct in (CardType.STAGECOACH, CardType.WELLS_FARGO):
        return w("stagecoach")
    if c.is_gun and c.gun_range > player.gun_range():
        return w("equip_gun")
    if ct == CardType.BARREL and not player.has_barrel():
        return w("equip_barrel")
    if ct == CardType.SCOPE and not player.has_scope():
        return w("equip_scope")
    if ct == CardType.MUSTANG and not player.has_mustang():
        return w("equip_mustang")
    if ct in (CardType.INDIANS, CardType.GATLING, CardType.DUEL):
        return 3.0
    return 1.5


# ─────────────────────────────────────────────────────────────────────────
# Difficulty-shared selection helpers
# ─────────────────────────────────────────────────────────────────────────
def pick_by_strength(ranked: list, strength: float):
    """Pick from `ranked` (best-first). `strength` in [0, 1]: 1.0 always takes
    the top entry; lower values increasingly likely to settle for a weaker
    one, modelling an imperfect (but never actively self-sabotaging) player.
    """
    if strength >= 0.999:
        return ranked[0]
    cur = max(0.05, min(0.95, strength))
    for item in ranked:
        if random.random() < cur:
            return item
        cur = min(0.95, cur + 0.18)
    return ranked[-1]


def rank_of_action(ranked: list[Action], card_type, target_id: int = -1) -> int:
    """Index of the first action matching (card_type, target_id); last rank if absent."""
    for i, a in enumerate(ranked):
        if a.card_type == card_type and a.target_id == target_id:
            return i
    return len(ranked) - 1
