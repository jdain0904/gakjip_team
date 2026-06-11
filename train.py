"""AI 학습 - 셀프 플레이"""
from game import GameEnv
from agent import QLearningAgent


def train(episodes=8000, save_path="model.pkl", verbose_every=1000):
    env = GameEnv(num_players=2)
    agents = [QLearningAgent(), QLearningAgent()]
    wins = [0, 0]
    rw   = [0, 0]
    print(f"학습 시작: {episodes}ep")
    for ep in range(1, episodes + 1):
        env.reset()
        states = [env.get_state(i) for i in range(2)]
        done = False
        while not done:
            pid   = env.current_pid
            valid = env.get_valid_actions(pid)
            act   = agents[pid].choose_action(states[pid], valid)
            prev  = states[pid]
            r, done, _ = env.step(pid, act)
            states[pid] = env.get_state(pid) if not done else prev
            vn = env.get_valid_actions(pid) if not done else []
            agents[pid].learn(prev, act, r, states[pid], done, vn)
        if env.winner is not None:
            wins[env.winner] += 1
            rw[env.winner]   += 1
        agents[0].decay_epsilon()
        agents[1].decay_epsilon()
        if verbose_every and ep % verbose_every == 0:
            print(f"  ep{ep:6d} | P0:{rw[0]} P1:{rw[1]} | ε={agents[0].epsilon:.4f}")
            rw = [0, 0]
    print(f"완료 P0:{wins[0]} P1:{wins[1]}")
    agents[0].save(save_path)
    return agents


if __name__ == "__main__":
    train()
