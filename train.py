"""
AI 학습 스크립트
두 Q-Learning 에이전트가 셀프 플레이로 학습
"""

import random
from game import GameEnv
from agent import QLearningAgent


def train(episodes: int = 10000, save_path: str = "model.pkl", verbose_every: int = 1000):
    env = GameEnv()
    agents = [QLearningAgent(), QLearningAgent()]

    win_counts = [0, 0]
    recent_wins = [0, 0]

    print(f"학습 시작: {episodes}에피소드")

    for ep in range(1, episodes + 1):
        states = list(env.reset())
        done = False

        while not done:
            for pid in [0, 1]:
                if done:
                    break
                valid = env.get_valid_actions(pid)
                action = agents[pid].choose_action(states[pid], valid)
                next_state, reward, done = env.step(pid, action)
                valid_next = env.get_valid_actions(pid) if not done else []
                agents[pid].learn(states[pid], action, reward, next_state, done, valid_next)
                states[pid] = next_state

        if env.winner is not None:
            win_counts[env.winner] += 1
            recent_wins[env.winner] += 1

        agents[0].decay_epsilon()
        agents[1].decay_epsilon()

        if ep % verbose_every == 0:
            print(
                f"에피소드 {ep:6d} | "
                f"P0 승: {recent_wins[0]:4d} | P1 승: {recent_wins[1]:4d} | "
                f"epsilon: {agents[0].epsilon:.4f}"
            )
            recent_wins = [0, 0]

    print(f"\n학습 완료 | 총 P0 승: {win_counts[0]} | 총 P1 승: {win_counts[1]}")
    agents[0].save(save_path)
    return agents


if __name__ == "__main__":
    train(episodes=10000)
