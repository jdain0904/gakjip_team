"""
강화학습 에이전트 - Q-Learning
"""

import random, math, pickle
from collections import defaultdict


class QLearningAgent:
    def __init__(self, lr=0.1, discount=0.95, epsilon=1.0,
                 epsilon_min=0.05, epsilon_decay=0.995):
        self.lr = lr
        self.gamma = discount
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay
        self.q_table: dict = defaultdict(lambda: defaultdict(float))

    def _disc(self, state):
        pos_me, pos_opp, sup, hv, sv = state
        return (min(pos_me,50)//5, min(pos_opp,50)//5, int(sup), hv//10, sv//10)

    def choose_action(self, state, valid):
        if random.random() < self.epsilon:
            return random.choice(valid)
        s = self._disc(state)
        return max(valid, key=lambda a: self.q_table[s][a])

    def learn(self, s, a, r, ns, done, valid_ns):
        sd, nsd = self._disc(s), self._disc(ns)
        target = r if (done or not valid_ns) else r + self.gamma * max(self.q_table[nsd][x] for x in valid_ns)
        self.q_table[sd][a] += self.lr * (target - self.q_table[sd][a])

    def decay_epsilon(self):
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)

    def predict_win_prob(self, state, valid):
        s = self._disc(state)
        if not valid: return 0.5
        return 1 / (1 + math.exp(-max(self.q_table[s][a] for a in valid)))

    def save(self, path):
        with open(path, "wb") as f:
            pickle.dump(dict(self.q_table), f)

    def load(self, path):
        with open(path, "rb") as f:
            data = pickle.load(f)
        self.q_table = defaultdict(lambda: defaultdict(float),
                                   {k: defaultdict(float, v) for k, v in data.items()})


class DynamicDifficultyAgent(QLearningAgent):
    def __init__(self, target_win_rate=0.5, adjust_speed=0.05, **kw):
        super().__init__(**kw)
        self.target_win_rate = target_win_rate
        self.adjust_speed = adjust_speed
        self.recent: list = []
        self.window = 20

    def record_result(self, ai_won: bool):
        self.recent.append(1 if ai_won else 0)
        if len(self.recent) > self.window:
            self.recent.pop(0)

    def adjust_difficulty(self) -> str:
        if len(self.recent) < 5:
            return ""
        pwr = 1.0 - sum(self.recent) / len(self.recent)
        if pwr > self.target_win_rate + 0.1:
            self.epsilon = max(self.epsilon_min, self.epsilon - self.adjust_speed)
            return f"AI 강도↑  (플레이어 승률 {pwr:.0%})"
        elif pwr < self.target_win_rate - 0.1:
            self.epsilon = min(0.6, self.epsilon + self.adjust_speed)
            return f"AI 강도↓  (플레이어 승률 {pwr:.0%})"
        return f"난이도 유지  ({pwr:.0%})"
