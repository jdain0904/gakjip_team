"""Bang! AI — 세 가지 난이도 등급.

쉬움(Easy)   — 순수 무작위 플레이.
보통(Medium) — 동적 난이도 조절. 매 의사결정 시점마다
    winrate_model.WinRateModel에게 인간 측의 현재 예측 승률 p를 물어보고,
    p >= 0.5(인간이 이기고 있음 — 도전 난이도를 높임)이면 EV가 최적인
    행동을 플레이하고, p < 0.5(인간이 지고 있음 — 봐줌)이면 차선의
    행동으로 한 단계 봐준다.
어려움(Hard) — 항상 EV가 최적인 행동(순위 0)을 선택하며, 자가대전을 통해
    강화학습으로 학습된 가중치로 점수를 매긴다 (record_game_result()와
    train_ai.py 참고).
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


# 어려움 AI의 보상 신호를 위한 누적 베이스라인 — record_game_result() 참고.
# (항상 새로 시작하는 자가대전과 달리) 대화형 세션 간에는 영속화되므로,
# 게임을 다시 실행할 때마다 EMA가 0.5로 초기화되지 않는다.
_baseline_winrate = _load_baseline()


def _get_winrate_model() -> WinRateModel | None:
    """지연 로딩 싱글턴 — AI 인스턴스마다 winrate_model.json을 다시 읽지 않도록 한다."""
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
    """AI가 조작하는 한 자리의 의사결정기. 난이도(0~2, 위 모듈 docstring
    참고)에 따라 choose_* 메서드들이 현재 GameState를 살펴보고 원하는
    행동을 반환한다. 어려움 난이도는 record_game_result()를 통해 경기를
    거치며 학습도 한다."""
    def __init__(self, pid: int, difficulty: int = 1):
        """
        difficulty: 0 = 쉬움, 1 = 보통, 2 = 어려움
        어려움 AI는 디스크에서 가중치를 불러오고, 매 게임 후 이를 갱신한다.
        """
        self.pid = pid
        self.difficulty = difficulty
        self._weights: dict = _load_weights() if difficulty == 2 else {}
        self._history: list[str] = []   # 가중치 갱신용 특징 태그 목록 (어려움 전용)

    # ─────────────────────────────────────────────────────────────────────
    # 게임 종료 후 학습 (난이도 2, 어려움 전용)
    # ─────────────────────────────────────────────────────────────────────
    def record_game_result(self, won: bool, persist: bool = True):
        """게임 종료 후 호출하여 어려움 AI의 가중치를 갱신한다.

        이것은 ai_strategy.score_play_actions의 선형 점수화 함수에 대한
        every-visit 몬테카를로 제어(Monte Carlo control)의 정책 개선
        단계이다: 이번 게임의 정책이 실제로 발동시킨 모든 특징 태그
        (self._history)는 승리로 이어진 행동 쪽으로 살짝 밀어 올려지고,
        패배로 이어진 행동 쪽에서는 밀려 내려간다. train_ai.py는 이를
        자가대전 규모로 실행하며 `persist`를 비활성화하는데, 이는 하나의
        가중치 딕셔너리를 공유하는 다수의 자가대전 AI 인스턴스들이
        중복된 디스크 쓰기로 서로의 갱신 내용을 덮어쓰지 않도록 하기
        위함이다 — train_ai.py는 한 게임에 대해 모든 인스턴스의 갱신을
        적용한 뒤 자체적으로 한 번만 저장한다.

        보상(reward)은 단순한 +1/-0.5 분할이 아니라, 누적되는 승률
        베이스라인(REINFORCE 방식의 분산 감소용 베이스라인)을 기준으로
        중심화(centering)된다. 중심화를 하지 않으면, 승자와 패자 모두에게서
        똑같이 발동되는 특징이라도 다인용 게임에서는 자리당 승률이
        50%보다 훨씬 낮게 형성된다는 사실(대부분의 게임에서 패자 수가
        승자 수보다 많다)만으로 한쪽 방향으로 계속 떠밀려가게 되고, 이는
        어떤 행동이 실제로 좋은지에 대한 진짜 신호를 모두 압도해버린다.
        베이스라인을 빼주면, 어떤 특징이 승자들 사이에서 실제로 과대
        혹은 과소 대표되지 않는 한 그 특징의 기대 갱신값은 거의 0이 된다.

        또한 매 갱신마다 가중치는 작은 `decay` 비율만큼 DEFAULT_WEIGHTS
        값 쪽으로 다시 줄어든다. 중심화만으로도 중립적인 특징에 대한
        '터치당 기대' 갱신값은 0이 되지만, 수천 번의 자가대전 게임이
        누적되면 평균이 0인 나머지 잡음(noise)도 결국에는 경계가 없는
        무작위 행보(random walk)가 되어, 언젠가는 [0.5, 15.0] 클램프
        범위로 흘러들어가 거기서 멈춰버리게 된다 — 즉 충분히 긴
        시간축에서는 실제로 중요한지 여부와 무관하게 모든 특징이 결국
        포화 상태에 도달하게 된다는 뜻이다. decay 항은 이 무작위 행보에
        원래 값(prior)으로 되돌아가려는 복원력을 부여하므로, 각 가중치는
        해당 특징의 보상 신호가 기본값으로 끌어당기는 힘을 실제로 얼마나
        강하게 압도하는지에 따라(lr/decay에 비례하여) 결정되는 안정적인
        평형점에 정착하게 되며, 자가대전 게임 수가 늘어나도 계속
        떠돌아다니지 않게 된다.
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
        """DDA(동적 난이도 조절) 제어 신호: 인간 측의 예측 승률.

        승률 모델이 아직 학습되지 않았거나 이 게임에 인간 플레이어가
        전혀 없는 경우(예: train_ai.py 자가대전)에는 중립값 0.5(조절 없음)로
        대체된다.
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
    # PLAY 단계 — 난이도별 분기
    # ─────────────────────────────────────────────────────────────────────
    def choose_action(self, gs: GameState) -> tuple | None:
        if self.difficulty == 0:
            return self._action_easy(gs)
        return self._action_scored(gs)

    # ── 보통/어려움: 확률 기반 EV 순위 산정 ────────────────────────
    def _action_scored(self, gs: GameState) -> tuple:
        p = gs.players[self.pid]

        # 시드 케첨 회복은 두 난이도 모두 공유하는 결정적(deterministic) 유틸리티 플레이
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

    # ── 쉬움: 대부분 무작위, 전략적 판단은 거의 없음 ────────────────────────
    def _action_easy(self, gs: GameState) -> tuple:
        p = gs.players[self.pid]

        # 죽을 위기일 때만 회복
        if p.hp == 1 and p.hp < p.max_hp and len(gs._alive_ids()) > 2:
            beer = self._find(p, CardType.BEER)
            if beer is not None:
                return ("play", beer)

        # 35% 확률로 그냥 턴 종료 (게으름)
        if random.random() < 0.35:
            return ("end_turn",)

        # 현재 플레이 가능한 모든 카드를 모음
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
    # 공용 헬퍼
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
        # 배신자
        if len(alive) <= 2:
            return [i for i in alive if i != self.pid]
        return [i for i in alive if i != self.pid
                and gs.players[i].role == Role.OUTLAW]

    def _known_enemies(self, gs: GameState) -> list[int]:
        enemies = self._enemies(gs)
        known = [i for i in enemies if gs.players[i].role_revealed]
        return known or [i for i in gs._alive_ids() if i != self.pid]

    def _known_allies(self, gs: GameState) -> set[int]:
        """*공개된* 역할이 나와 동일한 승리 조건을 공유함을 보장하는 플레이어들.

        이것이 바로 "내 역할에 충실하게 행동한다"는 강한 제약(hard
        constraint) 필터이다: 단일 대상 해로운 카드는 EV 점수가 아무리
        매력적이더라도 이 집합에 속한 플레이어를 무조건 건너뛴다. 아직
        공개되지 않은 역할은 절대 추측하지 않는다 — 인간 플레이어가
        상대의 역할이 실제로 밝혀진 뒤에야 그를 살려주는 것과 정확히
        동일하게, 확인된 동료만이 인정된다.
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
                # 배신자의 전형적인 전략: 보안관 측이 먼저 무법자들을 정리하게
                # 두고, 최종 1대1 상황이 되었을 때만 그들에게 칼끝을 돌린다.
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
    # 반응(response) 결정
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

        # 마지막 BANG!을 아껴두는 것은 생존이 위태롭지 않을 때만 올바른 선택이다
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

    # ── 맥주로 살아남기 ─────────────────────────────────────────────────────────
    def should_use_beer_save(self, gs: GameState) -> bool:
        return True  # 항상 생존을 시도한다

    # ── 캐릭터별 특수 드로우 ────────────────────────────────────────────
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
