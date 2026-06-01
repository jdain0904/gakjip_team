"""
시각화 분석 모듈 (계획서 3단계 시각화 요구사항)

1. 학습 곡선     - 에피소드 반복 횟수에 따른 AI 승률 변화
2. DDA 수렴 곡선 - 누적 게임에 따라 플레이어 승률이 50%에 수렴하는 추이
3. 행동 패턴 분포 - 이동/카드 사용 비율, 보급카드 사용 타이밍

실행: python3 visualize.py
결과: plots/ 폴더에 PNG 저장
"""

import os
import random
import statistics
import matplotlib
matplotlib.use("Agg")   # 디스플레이 없이 파일 저장
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np

from game import GameEnv, BOARD_SIZE
from agent import QLearningAgent, DynamicDifficultyAgent

OUT_DIR = "plots"
os.makedirs(OUT_DIR, exist_ok=True)

# ── 한글 폰트 설정 ─────────────────────────────────────────────────────────
def _set_korean_font():
    # 1) 시스템에 설치된 나눔/맑은고딕 TTF 직접 등록
    for root, _, files in os.walk("/usr/share/fonts"):
        for fname in files:
            if fname.endswith(".ttf") and any(k in fname.lower()
                    for k in ("nanum", "malgun", "gulim", "batang")):
                fm.fontManager.addfont(os.path.join(root, fname))

    # 2) matplotlib 캐시 새로 고침 후 후보 이름 탐색
    fm._load_fontmanager(try_read_cache=False)
    candidates = ["NanumGothic", "NanumBarunGothic", "Malgun Gothic",
                  "NanumSquareRound", "나눔고딕"]
    available  = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams["font.family"] = name
            return
    plt.rcParams["font.family"] = "DejaVu Sans"

_set_korean_font()
plt.rcParams["axes.unicode_minus"] = False


# ══════════════════════════════════════════════════════════════════════════
# 1. 학습 곡선
# ══════════════════════════════════════════════════════════════════════════
def collect_learning_data(total_episodes: int = 6000, window: int = 200) -> dict:
    """에피소드 진행하며 슬라이딩 윈도우 승률 기록"""
    env    = GameEnv(num_players=2)
    agents = [QLearningAgent(), QLearningAgent()]
    results: list[int] = []   # 0=P1승, 1=P0승
    curve_ep, curve_wr = [], []

    for ep in range(1, total_episodes + 1):
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

        results.append(1 if env.winner == 0 else 0)
        agents[0].decay_epsilon()
        agents[1].decay_epsilon()

        if ep >= window and ep % 50 == 0:
            recent = results[-window:]
            curve_ep.append(ep)
            curve_wr.append(sum(recent) / len(recent))

    return {"ep": curve_ep, "wr": curve_wr, "agents": agents}


def plot_learning_curve(data: dict, save_path: str):
    ep = data["ep"]
    wr = data["wr"]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(ep, wr, color="#5A9BFF", linewidth=1.8, label="P0 승률 (200게임 슬라이딩 평균)")

    # 이동 평균 (스무딩)
    k = 5
    smooth = np.convolve(wr, np.ones(k) / k, mode="valid")
    ax.plot(ep[k - 1:], smooth, color="#FF8C42", linewidth=2.5, label="스무딩 (추세선)")

    ax.axhline(0.5, color="gray", linestyle="--", linewidth=1, alpha=0.6, label="균형선 (50%)")
    ax.fill_between(ep, 0.45, 0.55, alpha=0.08, color="gray")

    ax.set_title("강화학습 학습 곡선 — 에피소드별 AI(P0) 승률 변화", fontsize=14, pad=12)
    ax.set_xlabel("학습 에피소드", fontsize=12)
    ax.set_ylabel("승률", fontsize=12)
    ax.set_ylim(0.3, 0.75)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    print(f"  저장: {save_path}")


# ══════════════════════════════════════════════════════════════════════════
# 2. DDA 수렴 곡선
# ══════════════════════════════════════════════════════════════════════════
def collect_dda_data(ai_agent: QLearningAgent, n_games: int = 150) -> dict:
    """
    사람 역할 = 약한 QLearningAgent (epsilon=0.6, 학습 없음)
    AI = DDA 에이전트
    """
    env      = GameEnv(num_players=2)
    dda      = DynamicDifficultyAgent(epsilon=0.15, epsilon_min=0.05)
    dda.q_table = ai_agent.q_table   # 학습된 가중치 공유

    human_ag = QLearningAgent(epsilon=0.55)
    human_ag.q_table = ai_agent.q_table

    game_nums: list[int] = []
    rolling_wr: list[float] = []
    results: list[int] = []   # 1=플레이어 승, 0=AI 승

    for g in range(1, n_games + 1):
        env.reset()
        states = [env.get_state(0), env.get_state(1)]
        done = False

        while not done:
            pid   = env.current_pid
            valid = env.get_valid_actions(pid)
            ag    = human_ag if pid == 0 else dda
            act   = ag.choose_action(states[pid], valid)
            _, done, _ = env.step(pid, act)
            if not done:
                states[pid] = env.get_state(pid)

        player_won = (env.winner == 0)
        results.append(1 if player_won else 0)
        dda.record_result(ai_won=not player_won)
        dda.adjust_difficulty()

        if g >= 10:
            game_nums.append(g)
            rolling_wr.append(sum(results[-20:]) / min(len(results), 20))

    return {"games": game_nums, "win_rate": rolling_wr, "final_epsilon": dda.epsilon}


def plot_dda_convergence(data: dict, save_path: str):
    games = data["games"]
    wr    = data["win_rate"]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), gridspec_kw={"height_ratios": [3, 1]})

    # 승률 곡선
    ax1.plot(games, wr, color="#64C896", linewidth=1.8, label="플레이어 승률 (최근 20게임)")

    # 스무딩
    k = 7
    if len(wr) >= k:
        smooth = np.convolve(wr, np.ones(k) / k, mode="valid")
        ax1.plot(games[k - 1:], smooth, color="#FF6B6B", linewidth=2.5, label="추세선")

    ax1.axhline(0.5, color="gold", linestyle="--", linewidth=1.5, alpha=0.9, label="목표 승률 (50%)")
    ax1.fill_between(games, 0.4, 0.6, alpha=0.08, color="gold", label="±10% 허용 범위")

    ax1.set_title("동적 난이도 조정(DDA) — 플레이어 승률 50% 수렴 추이", fontsize=14, pad=12)
    ax1.set_ylabel("플레이어 승률", fontsize=12)
    ax1.set_ylim(0.1, 0.9)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax1.legend(fontsize=10)
    ax1.grid(True, alpha=0.3)

    # AI epsilon 추이 (아래 subplot)
    # epsilon은 저장하지 않았으므로 최종값만 표시
    ax2.text(0.5, 0.5,
             f"최종 AI epsilon: {data['final_epsilon']:.3f}\n"
             f"(낮을수록 AI가 더 최적 전략 사용)",
             ha="center", va="center", fontsize=11,
             transform=ax2.transAxes,
             bbox=dict(boxstyle="round,pad=0.5", facecolor="#2A2F4A", edgecolor="#5A9BFF"))
    ax2.set_axis_off()

    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    print(f"  저장: {save_path}")


# ══════════════════════════════════════════════════════════════════════════
# 3. 행동 패턴 분포
# ══════════════════════════════════════════════════════════════════════════
def collect_action_data(agent: QLearningAgent, n_games: int = 3000) -> dict:
    """AI-AI 시뮬레이션으로 행동 패턴 수집"""
    env = GameEnv(num_players=2)
    action_counts = {0: 0, 1: 0, 2: 0, 3: 0}
    supply_timing: list[int] = []    # 보급카드 사용 시점의 남은 거리
    home_values: list[int] = []      # 집카드 사용 시 이동 거리
    turn_counts: list[int] = []
    win_counts = [0, 0]

    ag0 = QLearningAgent(epsilon=0.0)
    ag0.q_table = agent.q_table
    ag1 = QLearningAgent(epsilon=0.0)
    ag1.q_table = agent.q_table

    for _ in range(n_games):
        env.reset()
        states = [env.get_state(i) for i in range(2)]
        done = False

        while not done:
            pid   = env.current_pid
            valid = env.get_valid_actions(pid)
            ag    = ag0 if pid == 0 else ag1
            act   = ag.choose_action(states[pid], valid)
            action_counts[act] = action_counts.get(act, 0) + 1

            me = env.players[pid]
            if act == 2:
                supply_timing.append(me.position)
            if act == 1:
                card = me.get_best_home_card()
                if card:
                    home_values.append(card.value)

            _, done, _ = env.step(pid, act)
            if not done:
                states[pid] = env.get_state(pid)

        if env.winner is not None:
            win_counts[env.winner] += 1
        turn_counts.append(env.turn)

    return {
        "action_counts": action_counts,
        "supply_timing": supply_timing,
        "home_values": home_values,
        "turn_counts": turn_counts,
        "win_counts": win_counts,
        "n_games": n_games,
    }


def plot_action_patterns(data: dict, save_path: str):
    ac    = data["action_counts"]
    total = sum(ac.values())

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    # ── 행동 비율 파이차트 ─────────────────────────────────────────
    ax = axes[0]
    labels = ["이동 (+1칸)", "집 카드", "보급 카드", "카드 뽑기"]
    colors = ["#5A9BFF", "#FF8C42", "#5ACEFF", "#A06BFF"]
    sizes  = [ac.get(i, 0) for i in range(4)]
    non_zero = [(s, l, c) for s, l, c in zip(sizes, labels, colors) if s > 0]
    if non_zero:
        s_, l_, c_ = zip(*non_zero)
        wedges, texts, autotexts = ax.pie(
            s_, labels=l_, colors=c_, autopct="%1.1f%%",
            startangle=140, pctdistance=0.75,
            wedgeprops={"edgecolor": "white", "linewidth": 1.2}
        )
        for at in autotexts:
            at.set_fontsize(10)
    ax.set_title("행동 선택 비율", fontsize=13, pad=10)

    # ── 보급카드 사용 시점 히스토그램 ─────────────────────────────
    ax = axes[1]
    if data["supply_timing"]:
        bins = range(0, BOARD_SIZE + 6, 5)
        ax.hist(data["supply_timing"], bins=bins, color="#5ACEFF",
                edgecolor="white", linewidth=0.8, alpha=0.85)
        ax.axvline(np.mean(data["supply_timing"]), color="#FF6B6B",
                   linestyle="--", linewidth=2,
                   label=f"평균 {np.mean(data['supply_timing']):.1f}칸")
        ax.legend(fontsize=10)
    ax.set_title("보급카드 사용 시점\n(사용 당시 남은 거리)", fontsize=13, pad=10)
    ax.set_xlabel("남은 거리 (칸)", fontsize=11)
    ax.set_ylabel("빈도", fontsize=11)
    ax.set_xlim(0, BOARD_SIZE)
    ax.grid(True, alpha=0.3, axis="y")

    # ── 게임 길이 분포 + 밸런스 ───────────────────────────────────
    ax = axes[2]
    tc = data["turn_counts"]
    if tc:
        bins2 = range(min(tc), max(tc) + 3, 2)
        ax.hist(tc, bins=bins2, color="#64C896", edgecolor="white",
                linewidth=0.8, alpha=0.85)
        ax.axvline(np.mean(tc), color="#FF6B6B", linestyle="--", linewidth=2,
                   label=f"평균 {np.mean(tc):.1f}턴")
        ax.legend(fontsize=10)
    n   = data["n_games"]
    wc  = data["win_counts"]
    ax.set_title(
        f"게임 길이 분포\nP0: {wc[0]/n:.1%}승  P1: {wc[1]/n:.1%}승",
        fontsize=13, pad=10
    )
    ax.set_xlabel("게임 턴 수", fontsize=11)
    ax.set_ylabel("빈도", fontsize=11)
    ax.grid(True, alpha=0.3, axis="y")

    fig.suptitle("AI 대규모 시뮬레이션 행동 패턴 분석", fontsize=15, y=1.02)
    fig.tight_layout()
    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  저장: {save_path}")


# ══════════════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════════════
def main():
    print("=" * 50)
    print("시각화 분석 시작")
    print("=" * 50)

    # ── 1. 학습 곡선 ─────────────────────────────────────────────
    print("\n[1/3] 학습 곡선 생성 중... (6000 에피소드)")
    ldata = collect_learning_data(total_episodes=6000, window=200)
    plot_learning_curve(ldata, f"{OUT_DIR}/1_learning_curve.png")

    trained_agent = ldata["agents"][0]

    # ── 2. DDA 수렴 곡선 ─────────────────────────────────────────
    print("\n[2/3] DDA 수렴 곡선 생성 중... (150 게임)")
    ddata = collect_dda_data(trained_agent, n_games=150)
    plot_dda_convergence(ddata, f"{OUT_DIR}/2_dda_convergence.png")

    # ── 3. 행동 패턴 분포 ────────────────────────────────────────
    print("\n[3/3] 행동 패턴 분석 중... (3000 게임)")
    adata = collect_action_data(trained_agent, n_games=3000)
    plot_action_patterns(adata, f"{OUT_DIR}/3_action_patterns.png")

    # ── 요약 출력 ────────────────────────────────────────────────
    print(f"\n{'=' * 50}")
    print("분석 완료 요약")
    print(f"{'=' * 50}")
    ac = adata["action_counts"]
    tot = sum(ac.values())
    print(f"  이동    : {ac.get(0,0)/tot:.1%}")
    print(f"  집카드  : {ac.get(1,0)/tot:.1%}")
    print(f"  보급카드: {ac.get(2,0)/tot:.1%}")
    print(f"  카드뽑기: {ac.get(3,0)/tot:.1%}")
    wc = adata["win_counts"]
    n  = adata["n_games"]
    print(f"  P0 승률 : {wc[0]/n:.1%}  P1 승률 : {wc[1]/n:.1%}")
    print(f"\n그래프 저장 위치: {os.path.abspath(OUT_DIR)}/")


if __name__ == "__main__":
    main()
