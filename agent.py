"""
강화학습 에이전트 - Q-Learning 기반
상태 공간: (내 위치, 상대 위치, 보급 사용 여부, 최대 집카드 값, 최대 보급카드 값)
행동 공간: 0(이동), 1(집카드), 2(보급카드)
"""

import random
import pickle
from collections import defaultdict


class QLearningAgent:
    def __init__(
        self,
        learning_rate: float = 0.1,
        discount: float = 0.95,
        epsilon: float = 1.0,
        epsilon_min: float = 0.05,
        epsilon_decay: float = 0.995,
    ):
        self.lr = learning_rate
        self.gamma = discount
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay
        self.q_table: dict = defaultdict(lambda: defaultdict(float))

    def _discretize(self, state: tuple) -> tuple:
        """연속적 값을 구간으로 이산화하여 Q-table 크기 제한"""
        pos_me, pos_opp, supply_used, home_val, supply_val = state
        return (
            min(pos_me, 50) // 5,       # 0~10
            min(pos_opp, 50) // 5,      # 0~10
            int(supply_used),
            home_val // 10,             # 0~6
            supply_val // 10,           # 0~6
        )

    def choose_action(self, state: tuple, valid_actions: list) -> int:
        if random.random() < self.epsilon:
            return random.choice(valid_actions)
        s = self._discretize(state)
        q_vals = {a: self.q_table[s][a] for a in valid_actions}
        return max(q_vals, key=q_vals.get)

    def learn(self, state, action, reward, next_state, done, valid_next_actions):
        s = self._discretize(state)
        ns = self._discretize(next_state)

        if done or not valid_next_actions:
            target = reward
        else:
            best_next = max(self.q_table[ns][a] for a in valid_next_actions)
            target = reward + self.gamma * best_next

        self.q_table[s][action] += self.lr * (target - self.q_table[s][action])

    def decay_epsilon(self):
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)

    def save(self, path: str):
        with open(path, "wb") as f:
            pickle.dump(dict(self.q_table), f)
        print(f"모델 저장 완료: {path}")

    def load(self, path: str):
        with open(path, "rb") as f:
            data = pickle.load(f)
        self.q_table = defaultdict(lambda: defaultdict(float), {
            k: defaultdict(float, v) for k, v in data.items()
        })
        print(f"모델 로드 완료: {path}")


class DynamicDifficultyAgent(QLearningAgent):
    """
    동적 난이도 조정 에이전트
    플레이어 승률을 실시간 추적하여 epsilon(탐험율)을 조절
    - 플레이어가 자주 이기면 epsilon 감소 → AI가 더 잘함
    - 플레이어가 자주 지면 epsilon 증가 → AI가 더 실수함
    """

    def __init__(self, target_win_rate: float = 0.5, adjust_speed: float = 0.05, **kwargs):
        super().__init__(**kwargs)
        self.target_win_rate = target_win_rate
        self.adjust_speed = adjust_speed
        self.recent_results: list = []   # 최근 20게임 결과 (1=AI승, 0=플레이어승)
        self.window = 20

    def record_result(self, ai_won: bool):
        self.recent_results.append(1 if ai_won else 0)
        if len(self.recent_results) > self.window:
            self.recent_results.pop(0)

    def adjust_difficulty(self):
        if len(self.recent_results) < 5:
            return
        ai_win_rate = sum(self.recent_results) / len(self.recent_results)
        player_win_rate = 1.0 - ai_win_rate

        if player_win_rate > self.target_win_rate + 0.1:
            # 플레이어가 너무 많이 이김 → AI를 강하게
            self.epsilon = max(self.epsilon_min, self.epsilon - self.adjust_speed)
        elif player_win_rate < self.target_win_rate - 0.1:
            # 플레이어가 너무 많이 짐 → AI를 약하게
            self.epsilon = min(0.6, self.epsilon + self.adjust_speed)

        print(f"  [DDA] 플레이어 최근 승률: {player_win_rate:.1%} | AI epsilon: {self.epsilon:.3f}")

    def predict_win_probability(self, state: tuple, valid_actions: list) -> float:
        """현재 상태에서 AI의 승리 확률 추정 (Q값 기반)"""
        s = self._discretize(state)
        if not valid_actions:
            return 0.5
        q_vals = [self.q_table[s][a] for a in valid_actions]
        max_q = max(q_vals) if q_vals else 0
        # sigmoid로 0~1 범위 변환
        import math
        return 1 / (1 + math.exp(-max_q))
