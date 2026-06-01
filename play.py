"""
사람 vs AI 대전 - 동적 난이도 조정 포함
"""

import os
from game import GameEnv, BOARD_SIZE
from agent import DynamicDifficultyAgent

MODEL_PATH = "model.pkl"


def human_turn(env: GameEnv, pid: int) -> int:
    valid = env.get_valid_actions(pid)
    me = env.players[pid]
    opp = env.players[1 - pid]

    print(f"\n--- 당신의 턴 ---")
    print(f"  내 위치: {me.position}칸 남음 | 상대 위치: {opp.position}칸 남음")
    print(f"  손패: {me.hand}")
    print(f"  보급 카드 사용 여부: {'사용함' if me.supply_used else '미사용'}")
    print()

    action_map = {0: "이동 (1칸)", 1: "집 카드 사용", 2: "보급 카드 사용"}
    print("가능한 행동:")
    for a in valid:
        print(f"  {a}: {action_map[a]}")

    while True:
        try:
            choice = int(input("행동 선택: "))
            if choice in valid:
                return choice
            print("유효하지 않은 행동입니다.")
        except ValueError:
            print("숫자를 입력하세요.")


def ai_turn(env: GameEnv, pid: int, agent: DynamicDifficultyAgent) -> int:
    state = env._get_state(pid)
    valid = env.get_valid_actions(pid)
    action = agent.choose_action(state, valid)

    win_prob = agent.predict_win_probability(state, valid)
    action_names = {0: "이동", 1: "집카드", 2: "보급카드"}
    print(f"\n--- AI 턴 ---  행동: {action_names[action]}  |  AI 승리 예측: {win_prob:.1%}")
    return action


def play_game(agent: DynamicDifficultyAgent) -> bool:
    """한 게임 진행. 플레이어(P0) 승리시 True 반환"""
    env = GameEnv()
    env.reset()

    print(f"\n{'='*40}")
    print(f"게임 시작! 목표까지 {BOARD_SIZE}칸")
    print(f"{'='*40}")

    done = False
    while not done:
        env.render()
        # 플레이어 턴
        action = human_turn(env, 0)
        _, _, done = env.step(0, action)
        if done:
            break
        # AI 턴
        action = ai_turn(env, 1, agent)
        _, _, done = env.step(1, action)

    player_won = env.winner == 0
    if player_won:
        print("\n🎉 당신이 이겼습니다!")
    else:
        print("\n🤖 AI가 이겼습니다.")

    return player_won


def main():
    agent = DynamicDifficultyAgent(epsilon=0.0, epsilon_min=0.0)

    if os.path.exists(MODEL_PATH):
        agent.load(MODEL_PATH)
        agent.epsilon = 0.1
        agent.epsilon_min = 0.05
        print("학습된 모델을 로드했습니다.")
    else:
        print("학습된 모델이 없습니다. 먼저 train.py를 실행하세요.")
        print("랜덤 AI로 진행합니다.\n")
        agent.epsilon = 1.0

    print("\n===== 턴제 전략 게임 =====")
    print("목표: 50칸 거리를 먼저 줄이면 승리")
    print("카드로 한 번에 여러 칸 이동 가능, 보급 카드는 1회 사용 제한\n")

    while True:
        player_won = play_game(agent)
        agent.record_result(ai_won=not player_won)
        agent.adjust_difficulty()

        again = input("\n다시 플레이하시겠습니까? (y/n): ").strip().lower()
        if again != "y":
            break

    print("\n게임을 종료합니다.")


if __name__ == "__main__":
    main()
