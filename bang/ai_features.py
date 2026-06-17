"""State-vector feature extraction for the win-rate prediction model.

Builds a fixed-length numeric vector describing the game state from one
player's point of view. Only information that player could legitimately
know goes in: their own public+private state, plus `ai_probability`
hypergeometric estimates for hidden opponent information. Opponents'
actual hand contents are never inspected — same epistemic-fairness rule
the rest of the AI already follows (see ai_probability.CardCounter).
"""
from __future__ import annotations
from roles import Role
from ai_probability import CardCounter

FEATURE_NAMES = [
    "hp_ratio", "alive_ratio", "hand_size_norm", "equip_count_norm",
    "gun_range_norm", "has_barrel", "has_mustang", "role_revealed",
    "role_sheriff", "role_deputy", "role_outlaw", "role_renegade",
    "avg_enemy_hp_ratio", "avg_enemy_dodge_prob", "avg_enemy_bang_prob",
    "turn_norm",
]


def state_vector(gs, pid: int) -> list[float]:
    """Feature vector x for player `pid` in game state `gs`. len(x) == len(FEATURE_NAMES)."""
    p      = gs.players[pid]
    alive  = gs._alive_ids()
    others = [i for i in alive if i != pid]
    counter = CardCounter(gs, pid)

    hp_ratio         = p.hp / p.max_hp if p.max_hp else 0.0
    alive_ratio      = len(alive) / max(1, gs.num_players)
    hand_size_norm   = min(len(p.hand), 10) / 10
    equip_count_norm = min(len(p.equipment), 4) / 4
    gun_range_norm   = (p.gun_range() - 1) / 4
    has_barrel       = 1.0 if p.has_barrel() else 0.0
    has_mustang      = 1.0 if p.has_mustang() else 0.0
    role_revealed    = 1.0 if p.role_revealed else 0.0
    role_oh = [1.0 if (p.role_revealed and p.role == r) else 0.0
               for r in (Role.SHERIFF, Role.DEPUTY, Role.OUTLAW, Role.RENEGADE)]

    if others:
        avg_enemy_hp    = sum(gs.players[i].hp / gs.players[i].max_hp for i in others) / len(others)
        avg_enemy_dodge = sum(counter.prob_dodge(i) for i in others) / len(others)
        avg_enemy_bang  = sum(counter.prob_has_bang_equivalent(i) for i in others) / len(others)
    else:
        avg_enemy_hp = avg_enemy_dodge = avg_enemy_bang = 0.5

    turn_norm = min(gs.turn_num, 40) / 40

    return [hp_ratio, alive_ratio, hand_size_norm, equip_count_norm, gun_range_norm,
            has_barrel, has_mustang, role_revealed, *role_oh,
            avg_enemy_hp, avg_enemy_dodge, avg_enemy_bang, turn_norm]
