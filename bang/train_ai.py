"""Offline self-play training pipeline for the Medium-difficulty win-rate
prediction model and the Hard-difficulty reinforcement-learned weights.

Two models come out of the same batch of self-play games:

1. winrate_model.json — a logistic regression P(win|x) = sigma(w.x+b)
   fit by gradient descent on binary cross-entropy loss (see
   winrate_model.WinRateModel), trained on (state vector, 1/0 win
   label) pairs snapshotted once per turn for every alive player.
   ai_agent.BangAI (Medium difficulty) uses this at runtime to predict
   the human side's win probability and dynamically ease off or play
   optimally — the project's dynamic difficulty adjustment.

2. ai_weights.json — the Hard-difficulty AI's scoring weights, updated
   via ai_agent.BangAI.record_game_result(): an every-visit Monte
   Carlo policy-improvement step over the linear value-function
   approximation in ai_strategy.score_play_actions. Every feature tag
   a game's policy fired gets nudged toward the actions that led to a
   win and away from the ones that led to a loss.

Every seat in every self-play game is Hard difficulty. This sidesteps
a circular dependency (Medium needs a trained win-rate model to make
any decision at all, so it can't generate the data used to train that
same model) and keeps the dataset free of skill-asymmetry — the only
thing distinguishing a winning state from a losing one is the game
state itself (role, HP, equipment, turn number, ...), which is exactly
what the win-rate model should learn to read.

Usage:
    python3 train_ai.py [n_games]
"""
from __future__ import annotations
import os
import random
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cards import CardType
from game_state import GameState, Phase
from ai_agent import BangAI, DEFAULT_WEIGHTS, _save_weights
from ai_features import state_vector, FEATURE_NAMES
from winrate_model import WinRateModel
from roles import Role

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR   = os.path.join(REPO_ROOT, "training_output")

BASE_SEED = 20260617
NAME_POOL = [f"P{i}" for i in range(7)]


def _worst_discard_idx(hand) -> int:
    """Same discard-priority heuristic as screens.game._worst_card_idx,
    reimplemented here so this headless trainer doesn't need to import
    pygame/the UI layer just to break end-of-turn discard ties."""
    priority = {CardType.MISSED: 0, CardType.BEER: 1}
    return min(range(len(hand)), key=lambda i: priority.get(hand[i].card_type, 5))


def play_one_game(gs: GameState, ais: dict[int, BangAI], max_steps: int = 20000):
    """Drive `gs` to GAME_OVER by phase dispatch, mirroring the turn flow
    screens/game.py drives interactively. Returns a list of
    (pid, state_vector) snapshots taken once per turn for every alive
    player, or None if the game didn't finish within max_steps.
    """
    samples: list[tuple[int, list[float]]] = []
    recorded_turn = -1
    steps = 0
    while gs.phase != Phase.GAME_OVER and steps < max_steps:
        steps += 1
        ph = gs.phase

        if ph == Phase.DYNAMITE:
            gs.resolve_dynamite(); continue
        if ph == Phase.JAIL:
            gs.resolve_jail(); continue
        if ph == Phase.CHAR_DRAW:
            pid = gs.char_draw_pid; ai = ais[pid]
            if gs.char_draw_type == "jesse":
                t = ai.jesse_jones_target(gs)
                gs.char_draw_from_player(t) if t is not None else gs.char_draw_from_deck()
            else:
                gs.char_draw_from_discard() if ai.pedro_ramirez_from_discard(gs) else gs.char_draw_from_deck()
            continue
        if ph == Phase.KIT_PEEK:
            pid = gs.current_pid
            for p in ais[pid].kit_carlson_picks(gs):
                if not gs.kit_peek_cards: break
                gs.kit_carlson_pick(p)
            continue
        if ph == Phase.DRAW:
            gs.do_draw(); continue
        if ph == Phase.BEER_SAVE:
            pid = gs.beer_save_pid
            gs.beer_save_use() if ais[pid].should_use_beer_save(gs) else gs.beer_save_decline()
            continue
        if ph == Phase.RESPONSE:
            pid = gs.resp_current
            if pid < 0: continue
            if not gs.barrel_checked and gs.players[pid].has_barrel():
                gs.check_barrel(); continue
            action = ais[pid].choose_response(gs)
            gs.respond_with_missed(action[1]) if action[0] == "missed" else gs.respond_take_hit()
            continue
        if ph == Phase.DUEL:
            pid = gs.duel_current
            if pid < 0: continue
            action = ais[pid].choose_duel_response(gs)
            gs.duel_play_bang(action[1]) if action[0] == "bang" else gs.duel_take_hit()
            continue
        if ph == Phase.GEN_STORE:
            pid = gs.gen_store_order[0] if gs.gen_store_order else -1
            if pid < 0: continue
            gs.gen_store_pick(pid, ais[pid].choose_gen_store(gs))
            continue
        if ph == Phase.DISCARD:
            pid = gs.current_pid; p = gs.players[pid]
            if len(p.hand) > p.hand_limit():
                gs.discard_card(_worst_discard_idx(p.hand))
            else:
                gs.enter_discard_phase()
            continue
        if ph == Phase.PLAY:
            if gs.turn_num != recorded_turn:
                recorded_turn = gs.turn_num
                for pid in gs._alive_ids():
                    samples.append((pid, state_vector(gs, pid)))
            pid = gs.current_pid
            action = ais[pid].choose_action(gs)
            if action is None or action[0] == "end_turn":
                gs.enter_discard_phase()
            elif action[0] == "sid_ketchum":
                gs.use_sid_ketchum(pid, action[1], action[2])
            elif len(action) == 2:
                gs.play_card(pid, action[1])
            elif len(action) == 3:
                gs.play_card(pid, action[1], target_id=action[2])
            elif len(action) == 4:
                gs.play_card(pid, action[1], target_id=action[2], target_card_idx=action[3])
            continue

    return samples if gs.phase == Phase.GAME_OVER else None


def run_self_play(n_games: int, shared_weights: dict, verbose_every: int = 200):
    X: list[list[float]] = []
    y: list[int] = []
    role_wins = {Role.SHERIFF: 0, Role.OUTLAW: 0, Role.RENEGADE: 0}
    finished = timed_out = errored = 0
    turns_total = 0
    error_examples = []

    for gi in range(n_games):
        random.seed(BASE_SEED + gi)
        n = random.choice([4, 5, 6, 7])
        names = NAME_POOL[:n]
        try:
            gs  = GameState.new_game(num_players=n, human_ids=[], mode="ai", names=names)
            ais = {i: BangAI(i, difficulty=2) for i in range(n)}
            for ai in ais.values():
                ai._weights = shared_weights   # one shared dict — avoids a save race

            samples = play_one_game(gs, ais)
            if samples is None:
                timed_out += 1
                continue

            for pid, ai in ais.items():
                ai.record_game_result(gs.player_won(pid), persist=False)
            for pid, vec in samples:
                X.append(vec)
                y.append(1 if gs.player_won(pid) else 0)

            role_wins[gs.winner_role] = role_wins.get(gs.winner_role, 0) + 1
            finished += 1
            turns_total += gs.turn_num
        except Exception:
            errored += 1
            if len(error_examples) < 3:
                error_examples.append(traceback.format_exc())

        if verbose_every and (gi + 1) % verbose_every == 0:
            print(f"  [{gi + 1}/{n_games}] finished={finished} timed_out={timed_out} "
                  f"errored={errored} samples={len(X)}")

    if error_examples:
        print(f"\n{errored} games raised an exception; first {len(error_examples)}:")
        for tb in error_examples:
            print(tb)

    return X, y, role_wins, finished, turns_total


def make_charts(model: WinRateModel, X_val, y_val, role_wins: dict, finished: int,
                 default_weights: dict, trained_weights: dict):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available — skipping chart generation.")
        return

    os.makedirs(OUT_DIR, exist_ok=True)

    # 1) Loss / accuracy curves over training epochs (train vs validation)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    epochs = range(1, len(model.history["loss"]) + 1)
    axes[0].plot(epochs, model.history["loss"], label="train")
    if model.history.get("val_loss"):
        axes[0].plot(epochs, model.history["val_loss"], label="validation")
    axes[0].set_xlabel("epoch"); axes[0].set_ylabel("binary cross-entropy loss")
    axes[0].set_title("Win-rate model training loss"); axes[0].legend()

    axes[1].plot(epochs, model.history["accuracy"], label="train")
    if model.history.get("val_accuracy"):
        axes[1].plot(epochs, model.history["val_accuracy"], label="validation")
    axes[1].set_xlabel("epoch"); axes[1].set_ylabel("accuracy")
    axes[1].set_title("Win-rate model training accuracy"); axes[1].legend()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "loss_accuracy.png"), dpi=130)
    plt.close(fig)

    # 2) Calibration plot: predicted-probability bucket vs actual win fraction
    if X_val:
        n_bins = 10
        bins: list[list[int]] = [[] for _ in range(n_bins)]
        for x, yi in zip(X_val, y_val):
            p = model.predict_proba(x)
            b = min(n_bins - 1, int(p * n_bins))
            bins[b].append(yi)
        xs, ys, counts = [], [], []
        for b in range(n_bins):
            if bins[b]:
                xs.append((b + 0.5) / n_bins)
                ys.append(sum(bins[b]) / len(bins[b]))
                counts.append(len(bins[b]))
        fig, ax = plt.subplots(figsize=(5.5, 5))
        ax.plot([0, 1], [0, 1], "--", color="gray", label="perfect calibration")
        max_count = max(counts)
        sizes = [40 + 360 * (c / max_count) for c in counts]
        ax.scatter(xs, ys, s=sizes, color="tab:blue", alpha=0.75, label="validation buckets", zorder=3)
        ax.set_xlabel("predicted P(win)"); ax.set_ylabel("actual win fraction")
        ax.set_title("Win-rate model calibration (validation set)")
        ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.legend()
        fig.tight_layout()
        fig.savefig(os.path.join(OUT_DIR, "calibration.png"), dpi=130)
        plt.close(fig)

    # 3) Win rate by role across self-play games (balance check)
    labels = ["Sheriff+Deputy", "Outlaw", "Renegade"]
    vals = [role_wins.get(Role.SHERIFF, 0), role_wins.get(Role.OUTLAW, 0), role_wins.get(Role.RENEGADE, 0)]
    pct = [100 * v / finished if finished else 0 for v in vals]
    fig, ax = plt.subplots(figsize=(6, 4.2))
    bars = ax.bar(labels, pct, color=["#3a6fb0", "#b04a3a", "#7a3ab0"])
    for bar, v, p in zip(bars, vals, pct):
        ax.text(bar.get_x() + bar.get_width() / 2, p + 1, f"{p:.1f}%\n(n={v})", ha="center", fontsize=9)
    ax.set_ylabel("win rate (%)"); ax.set_title(f"Self-play win rate by role (n={finished} games)")
    ax.set_ylim(0, max(pct) * 1.25 if pct else 1)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "role_winrates.png"), dpi=130)
    plt.close(fig)

    # 4) RL weight drift: default vs self-play-trained Hard AI weights
    feats    = list(default_weights.keys())
    defaults = [default_weights[f] for f in feats]
    trained  = [trained_weights.get(f, default_weights[f]) for f in feats]
    fig, ax = plt.subplots(figsize=(11, 5))
    idx = range(len(feats))
    ax.bar([i - 0.2 for i in idx], defaults, width=0.4, label="default", color="#999")
    ax.bar([i + 0.2 for i in idx], trained, width=0.4, label="RL-trained", color="#3a8f5a")
    ax.set_xticks(list(idx)); ax.set_xticklabels(feats, rotation=60, ha="right", fontsize=8)
    ax.set_ylabel("weight"); ax.set_title("Hard AI scoring weights: default vs self-play RL-trained")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "weight_drift.png"), dpi=130)
    plt.close(fig)

    print(f"Charts written to {OUT_DIR}/")


def main():
    n_games = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    print(f"Self-play training: {n_games} games, all Hard-difficulty AI...")
    t0 = time.time()

    shared_weights = DEFAULT_WEIGHTS.copy()
    X, y, role_wins, finished, turns_total = run_self_play(n_games, shared_weights)

    elapsed = time.time() - t0
    print(f"\nSelf-play done in {elapsed:.1f}s — {finished}/{n_games} finished, "
          f"{len(X)} state samples, avg {turns_total / max(1, finished):.1f} turns/game")

    _save_weights(shared_weights)
    print("Saved RL-trained Hard AI weights -> ai_weights.json")

    # ── Train the win-rate model ─────────────────────────────────────────
    combined = list(zip(X, y))
    rng = random.Random(BASE_SEED)
    rng.shuffle(combined)
    split = max(1, int(len(combined) * 0.85))
    train, val = combined[:split], combined[split:]
    X_train, y_train = [t[0] for t in train], [t[1] for t in train]
    X_val, y_val     = [t[0] for t in val],   [t[1] for t in val]

    print(f"\nTraining win-rate model: {len(X_train)} train / {len(X_val)} validation samples...")
    model = WinRateModel(len(FEATURE_NAMES))
    model.fit(X_train, y_train, X_val, y_val, lr=0.15, epochs=400, l2=1e-3, verbose=True)
    model.save(FEATURE_NAMES)
    print("Saved win-rate model -> winrate_model.json")

    if X_val:
        vl, va = model.evaluate(X_val, y_val)
        print(f"Final validation: loss={vl:.4f} accuracy={va:.4f}")

    make_charts(model, X_val, y_val, role_wins, finished, DEFAULT_WEIGHTS, shared_weights)


if __name__ == "__main__":
    main()
