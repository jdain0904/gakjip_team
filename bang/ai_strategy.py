"""보통과 어려움 AI가 공유하는, 확률 기반의 기댓값(EV) 점수화 로직.

플레이어가 취할 수 있는 모든 합법적 행동은 동일한 방식으로 점수가
매겨지며, `ai_probability.CardCounter`를 사용해 "이미 사용된 카드" +
"내가 들고 있는 카드" 정보를 실제 확률로 변환한다. 쉬움을 제외한 두
난이도는 오직 *어떤* 순위의 행동을 최종적으로 선택하는지에서만
차이가 난다:

  - 어려움은 항상 순위 0(가장 높은 점수의 행동)을 선택하며, 자가대전을
    통해 강화학습으로 학습된 가중치를 사용한다 (ai_agent.BangAI.
    record_game_result와 train_ai.py 참고).
  - 보통은 winrate_model.WinRateModel이 예측한 인간 측 승률(ai_agent.
    BangAI._predict_human_winrate 참고)을 기준으로 순위 0과 순위 1
    사이에서 선택한다 — 이것이 바로 이 프로젝트의 동적 난이도 조절
    기능이다.

자신의 역할에 충실하게 행동하는 것은 점수상의 선호가 아니라 강한
제약(hard constraint)으로 취급된다: 단일 대상 해로운 카드(BANG!,
결투, 캣 발루, 패닉!, 감옥)는 이미 동료로 확인된 플레이어를 그냥
건너뛴다. 범위 카드(인디언!, 개틀링)는 게임 규칙상 동료를 맞히지
않을 방법이 없으므로, 대신 동료에게 입히는 부수 피해에 대해
페널티를 받는다.
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
    """점수가 매겨진 후보 행동 1개를 나타낸다."""
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
    """현재 `pid`가 사용할 수 있는 모든 합법적 플레이와 'end_turn'에 점수를 매긴다.

    점수 내림차순으로 정렬된 `Action` 리스트를 반환한다.
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

        # 대상이 필요 없는 플레이
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
# 카드 종류별 점수 계산 함수
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
    """`tid`로부터 어떤 카드를 가져올지(패닉!/캣 발루) 결정하고 점수를 매긴다."""
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

    # 가치가 낮은 장비만 남아있는 경우(예: 감옥/다이너마이트) — 그래도 가져가긴 하되 우선순위는 낮춤
    return 0, 1.0 * (1.1 if enemy else 0.6), feat_equip


def _score_jail(counter, w, enemy):
    p_skip = 1.0 - counter.prob_escape_jail()
    return w("jail") * p_skip * (1.3 if enemy else 0.4), "jail"


def _score_area(gs, pid, counter, w, known_enemies, known_allies, feat, dodge_prob_fn):
    """인디언!/개틀링이 공유하는 EV 모델: 두 카드 모두 적절한 카드를 내지
    못하는 다른 모든 생존 플레이어를 맞히며, 카드를 낸 본인은 둘 다
    위험에 노출되지 않는다.
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
    """플레이 단계 점수화 로직을 앞면이 보이는 잡화점 카드에 그대로 적용한 버전."""
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
    # has_barrel()/has_scope()/has_mustang()가 아니라 *실제* 카드 보유 여부를
    # 명확히 확인한다 — 그 함수들은 주르도네/로즈 둘란/폴 리그렛이 선천적으로
    # 가지는 가상의 카드도 함께 집계하므로, 이 세 캐릭터가 실제 카드를 한 장
    # 더 얻었을 때 진짜로 이득을 보는 사실(스택 가능, Player.barrel_count()
    # 참고)을 잘못 가려버리게 된다.
    if ct == CardType.BARREL and not any(c.card_type == CardType.BARREL for c in player.equipment):
        return w("equip_barrel")
    if ct == CardType.SCOPE and not any(c.card_type == CardType.SCOPE for c in player.equipment):
        return w("equip_scope")
    if ct == CardType.MUSTANG and not any(c.card_type == CardType.MUSTANG for c in player.equipment):
        return w("equip_mustang")
    if ct in (CardType.INDIANS, CardType.GATLING, CardType.DUEL):
        return 3.0
    return 1.5
