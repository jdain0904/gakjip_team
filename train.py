"""
AI 학습 스크립트 - 셀프 플레이 (2인 환경)
"""

from game import GameEnv
from agent import QLearningAgent


def train(episodes: int = 8000, save_path: str = "model.pkl", verbose_every: int = 1000):
    env = GameEnv(num_players=2)
    agents = [QLearningAgent(), QLearningAgent()]
    win_counts = [0, 0]
    recent_wins = [0, 0]

    print(f"학습 시작: {episodes} 에피소드")
    for ep in range(1, episodes + 1):
        env.reset()
        states = [env.get_state(i) for i in range(2)]
        done = False

        while not done:
            pid    = env.current_pid
            valid  = env.get_valid_actions(pid)
            action = agents[pid].choose_action(states[pid], valid)
            prev   = states[pid]
            reward, done = env.step(pid, action)
            states[pid]  = env.get_state(pid) if not done else states[pid]
            valid_next   = env.get_valid_actions(pid) if not done else []
            agents[pid].learn(prev, action, reward, states[pid], done, valid_next)

        if env.winner is not None:
            win_counts[env.winner] += 1
            recent_wins[env.winner] += 1

        agents[0].decay_epsilon()
        agents[1].decay_epsilon()

        if verbose_every and ep % verbose_every == 0:
            print(f"  에피소드 {ep:6d} | P0:{recent_wins[0]}승 P1:{recent_wins[1]}승"
                  f" | ε={agents[0].epsilon:.4f}")
            recent_wins = [0, 0]

    print(f"학습 완료 | P0:{win_counts[0]}승 P1:{win_counts[1]}승")
    agents[0].save(save_path)
    return agents


if __name__ == "__main__":
    train()
