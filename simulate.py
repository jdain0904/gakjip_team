"""
밸런스 시뮬레이션 - 학습된 AI끼리 대규모 대전
"""

import statistics
from game import GameEnv
from agent import QLearningAgent


def simulate(agents: list[QLearningAgent], n_games: int = 3000) -> dict:
    n = len(agents)
    env = GameEnv(num_players=n)
    win_counts = [0] * n
    turn_counts = []
    supply_usage = [0] * n

    for _ in range(n_games):
        env.reset()
        done = False
        states = [env.get_state(i) for i in range(n)]

        while not done:
            pid   = env.current_pid
            valid = env.get_valid_actions(pid)
            ag    = agents[pid]
            old_eps = ag.epsilon
            ag.epsilon = 0.0     # greedy
            action = ag.choose_action(states[pid], valid)
            ag.epsilon = old_eps
            _, done = env.step(pid, action)
            if not done:
                states[pid] = env.get_state(pid)

        if env.winner is not None:
            win_counts[env.winner] += 1
        turn_counts.append(env.turn)
        for i in range(n):
            if env.players[i].supply_used:
                supply_usage[i] += 1

    return {
        "games": n_games,
        "win_counts": win_counts,
        "win_rates": [w / n_games for w in win_counts],
        "avg_turns": statistics.mean(turn_counts),
        "supply_rates": [u / n_games for u in supply_usage],
    }


def print_report(report: dict):
    n = len(report["win_counts"])
    print("\n===== 밸런스 시뮬레이션 결과 =====")
    print(f"총 게임: {report['games']}  |  평균 턴: {report['avg_turns']:.1f}")
    for i in range(n):
        print(f"  P{i+1}: 승률 {report['win_rates'][i]:.1%}  보급 사용률 {report['supply_rates'][i]:.1%}")
    best = max(range(n), key=lambda i: report["win_rates"][i])
    if report["win_rates"][best] > 0.55:
        print(f"⚠️  P{best+1} 유리 ({report['win_rates'][best]:.1%}) — 선공 이점 조정 필요")
    else:
        print("✅ 밸런스 양호")


if __name__ == "__main__":
    from train import train
    agents = train(episodes=5000, verbose_every=1000)
    report = simulate(agents, n_games=2000)
    print_report(report)
