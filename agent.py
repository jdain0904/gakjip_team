"""
강화학습 에이전트 - Q-Learning 기반
"""

import random
import math
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
        pos_me, pos_opp, supply_used, home_val, supply_val = state
        return (
            min(pos_me, 50) // 5,
            min(pos_opp, 50) // 5,
            int(supply_used),
            home_val // 10,
            supply_val // 10,
        )

    def choose_action(self, state: tuple, valid_actions: list) -> int:
        if random.random() < self.epsilon:
            return random.choice(valid_actions)
        s = self._discretize(state)
        return max(valid_actions, key=lambda a: self.q_table[s][a])

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

    def load(self, path: str):
        with open(path, "rb") as f:
            data = pickle.load(f)
        self.q_table = defaultdict(lambda: defaultdict(float), {
            k: defaultdict(float, v) for k, v in data.items()
        })

    def predict_win_prob(self, state: tuple, valid_actions: list) -> float:
        s = self._discretize(state)
        if not valid_actions:
            return 0.5
        max_q = max(self.q_table[s][a] for a in valid_actions)
        return 1 / (1 + math.exp(-max_q))


class DynamicDifficultyAgent(QLearningAgent):
    """
    동적 난이도 조정 에이전트
    플레이어 승률이 목표치보다 높으면 AI를 강하게, 낮으면 약하게 조절
    """

    def __init__(self, target_win_rate: float = 0.5, adjust_speed: float = 0.05, **kwargs):
        super().__init__(**kwargs)
        self.target_win_rate = target_win_rate
        self.adjust_speed = adjust_speed
        self.recent_results: list = []
        self.window = 20

    def record_result(self, ai_won: bool):
        self.recent_results.append(1 if ai_won else 0)
        if len(self.recent_results) > self.window:
            self.recent_results.pop(0)

    def adjust_difficulty(self) -> str:
        if len(self.recent_results) < 5:
            return ""
        ai_win_rate = sum(self.recent_results) / len(self.recent_results)
        player_win_rate = 1.0 - ai_win_rate
        if player_win_rate > self.target_win_rate + 0.1:
            self.epsilon = max(self.epsilon_min, self.epsilon - self.adjust_speed)
            return f"AI 강도 상승 (플레이어 승률 {player_win_rate:.0%})"
        elif player_win_rate < self.target_win_rate - 0.1:
            self.epsilon = min(0.6, self.epsilon + self.adjust_speed)
            return f"AI 강도 하락 (플레이어 승률 {player_win_rate:.0%})"
        return f"난이도 유지 (플레이어 승률 {player_win_rate:.0%})"
