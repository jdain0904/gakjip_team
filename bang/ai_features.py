"""승률 예측 모델을 위한 상태 벡터 특징 추출.

한 플레이어의 시점에서 게임 상태를 설명하는 고정 길이의 숫자 벡터를
만든다. 그 플레이어가 정당하게 알 수 있는 정보만 포함된다: 자신의
공개+비공개 상태와, 상대측의 숨겨진 정보에 대한 `ai_probability`의
초기하분포 기반 추정값이 그것이다. 상대의 실제 손패 내용은 절대
들여다보지 않는다 — AI의 나머지 부분이 이미 따르고 있는 동일한
인식적 공정성(epistemic-fairness) 규칙이다 (ai_probability.CardCounter
참고).
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
    """게임 상태 `gs`에서 플레이어 `pid`에 대한 특징 벡터 x. len(x) == len(FEATURE_NAMES)."""
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
