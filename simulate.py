"""
밸런스 시뮬레이션 스크립트
학습된 AI끼리 대규모 대전을 통해 게임 밸런스 분석
"""

import statistics
from game import GameEnv
from agent import QLearningAgent


def simulate(agent0: QLearningAgent, agent1: QLearningAgent, n_games: int = 5000) -> dict:
    env = GameEnv()
    win_counts = [0, 0]
    turn_counts = []
    supply_usage = [0, 0]

    for _ in range(n_games):
        states = list(env.reset())
        done = False

        while not done:
            for pid in [0, 1]:
                if done:
                    break
                valid = env.get_valid_actions(pid)
                # 탐험 없이 greedy 선택
                action = agent0.choose_action(states[pid], valid) if pid == 0 else agent1.choose_action(states[pid], valid)
                next_state, _, done = env.step(pid, action)
                states[pid] = next_state

        if env.winner is not None:
            win_counts[env.winner] += 1
        turn_counts.append(env.turn)
        for pid in [0, 1]:
            if env.players[pid].supply_used:
                supply_usage[pid] += 1

    report = {
        "games": n_games,
        "p0_wins": win_counts[0],
        "p1_wins": win_counts[1],
        "p0_win_rate": win_counts[0] / n_games,
        "p1_win_rate": win_counts[1] / n_games,
        "avg_turns": statistics.mean(turn_counts),
        "median_turns": statistics.median(turn_counts),
        "p0_supply_rate": supply_usage[0] / n_games,
        "p1_supply_rate": supply_usage[1] / n_games,
    }
    return report


def print_report(report: dict):
    print("\n===== 게임 밸런스 시뮬레이션 결과 =====")
    print(f"총 게임 수     : {report['games']}")
    print(f"P0 승리        : {report['p0_wins']} ({report['p0_win_rate']:.1%})")
    print(f"P1 승리        : {report['p1_wins']} ({report['p1_win_rate']:.1%})")
    print(f"평균 턴 수     : {report['avg_turns']:.1f}")
    print(f"중간값 턴 수   : {report['median_turns']:.1f}")
    print(f"P0 보급카드 사용률 : {report['p0_supply_rate']:.1%}")
    print(f"P1 보급카드 사용률 : {report['p1_supply_rate']:.1%}")

    p0_rate = report["p0_win_rate"]
    if 0.45 <= p0_rate <= 0.55:
        print("\n✅ 밸런스 양호 (승률 45~55%)")
    elif p0_rate > 0.55:
        print(f"\n⚠️  P0 유리 ({p0_rate:.1%}) - 선공 이점 조정 필요")
    else:
        print(f"\n⚠️  P1 유리 ({1-p0_rate:.1%}) - 후공 보정 필요")


if __name__ == "__main__":
    from train import train
    print("AI 학습 중...")
    agents = train(episodes=5000, verbose_every=1000)

    # 동일 모델로 밸런스 테스트
    report = simulate(agents[0], agents[1], n_games=3000)
    print_report(report)
