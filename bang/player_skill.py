"""Tracks human decision quality to drive the Medium AI's dynamic difficulty.

Every time a human plays a card during the PLAY phase, `screens/game.py`
ranks that choice against `ai_strategy.score_play_actions()`'s full
ranking and feeds the resulting rank into `update_skill()`. The resulting
skill score (0 = consistently picks weak moves, 1 = consistently picks
the top-EV move) is persisted across sessions and converted into an
"optimality strength" that scales how often Medium AI settles for a
weaker move via `ai_strategy.pick_by_strength()`.
"""
import json
from pathlib import Path

SKILL_FILE = Path(__file__).parent / "player_skill.json"
_DEFAULT = {"skill": 0.5, "samples": 0}


def load_skill() -> dict:
    try:
        with open(SKILL_FILE) as f:
            data = json.load(f)
        return {"skill": float(data.get("skill", 0.5)),
                "samples": int(data.get("samples", 0))}
    except Exception:
        return dict(_DEFAULT)


def save_skill(state: dict):
    try:
        with open(SKILL_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


def update_skill(state: dict, rank: int, total: int) -> dict:
    """EMA update: quality=1.0 means the human picked the top-EV action."""
    quality = 1.0 if total <= 1 else 1.0 - (rank / (total - 1))
    alpha = 0.15
    new_skill = state["skill"] * (1 - alpha) + quality * alpha
    state["skill"]   = max(0.0, min(1.0, new_skill))
    state["samples"] = state.get("samples", 0) + 1
    return state


def strength_for_skill(skill: float) -> float:
    """Map human skill [0, 1] to Medium AI optimality strength [0.25, 0.9]."""
    return max(0.25, min(0.9, 0.25 + skill * 0.65))
