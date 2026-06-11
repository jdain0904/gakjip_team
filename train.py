"""
Q-Learning 에이전트 학습
"""

from game import GameEnv
from agent import QLearningAgent


def train(episodes: int = 8000, save_path: str = "model.pkl", verbose_every: int = 500):
    env   = GameEnv(num_players=2, human_ids=[])
    agent = QLearningAgent()

    for ep in range(1, episodes + 1):
        env.reset()
        states = [env.get_state(i) for i in range(env.num_players)]

        while not env.done:
            pid    = env.current_pid
            valid  = env.get_valid_actions(pid)
            action = agent.choose_action(states[pid], valid)
            r, done, _ = env.step(pid, action)

            ns        = env.get_state(pid)
            valid_ns  = env.get_valid_actions(pid) if not done else []
            agent.learn(states[pid], action, r, ns, done, valid_ns)
            states[pid] = ns

        agent.decay_epsilon()

        if verbose_every and ep % verbose_every == 0:
            print(f"[train] episode {ep}/{episodes}  ε={agent.epsilon:.3f}")

    agent.save(save_path)
    print(f"[train] 완료 → {save_path}")


if __name__ == "__main__":
    train()
