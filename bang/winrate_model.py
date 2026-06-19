"""승률 예측 모델 — 경사 하강법으로 학습되는 로지스틱 회귀.

    P(win | x) = sigma(w.x + b),     sigma(z) = 1 / (1 + e^-z)

w와 b는 이진 교차 엔트로피 손실(binary cross-entropy loss)을 최소화하여 적합시킨다

    L = -(y*log(p) + (1-y)*log(1-p))

배치 경사 하강법(batch gradient descent)을 통해 (fit() 참고). 순수 Python으로
작성되었으며 numpy를 사용하지 않는다: 이 모듈은 실제 게임(ai_agent.BangAI,
보통 난이도)에서 임포트되므로, 추론을 실행하기 위해 수치 계산용 의존성을
끌어들이지 않아야 한다. 대규모 자가대전 데이터셋에 대한 학습은 train_ai.py가
오프라인으로 수행하며, 이 특징 벡터의 크기에서는 일반 루프로도 충분히 빠르다.
"""
from __future__ import annotations
import json
import math
from pathlib import Path

MODEL_FILE = Path(__file__).parent / "winrate_model.json"


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


class WinRateModel:
    """게임 상태로부터 P(승리)를 예측하는 로지스틱 회귀 모델. train_ai.py가
    오프라인에서 자가대전 데이터로 학습시키고, 보통 난이도 AI가 실행 시점에
    불러와 최적의 수를 둘지 한 수 물러설지(동적 난이도 조절)를 결정한다."""
    def __init__(self, n_features: int):
        self.n_features = n_features
        self.w: list[float] = [0.0] * n_features
        self.b: float = 0.0
        self.mean: list[float] = [0.0] * n_features
        self.std: list[float] = [1.0] * n_features
        self.history: dict[str, list[float]] = {
            "loss": [], "accuracy": [], "val_loss": [], "val_accuracy": [],
        }

    # ── 추론 ────────────────────────────────────────────────────────
    def _normalize(self, x: list[float]) -> list[float]:
        return [(xi - m) / s if s > 1e-9 else 0.0
                for xi, m, s in zip(x, self.mean, self.std)]

    def predict_proba(self, x: list[float]) -> float:
        xn = self._normalize(x)
        z  = self.b + sum(wi * xi for wi, xi in zip(self.w, xn))
        return _sigmoid(z)

    # ── 학습 ─────────────────────────────────────────────────────────
    def fit(self, X: list[list[float]], y: list[int],
            X_val: list[list[float]] | None = None, y_val: list[int] | None = None,
            lr: float = 0.1, epochs: int = 300, l2: float = 1e-3,
            verbose: bool = False):
        """위에서 설명한 이진 교차 엔트로피 손실에 대한 배치 경사 하강법."""
        n = len(X)
        if n == 0:
            return

        self.mean = [sum(row[j] for row in X) / n for j in range(self.n_features)]
        self.std  = []
        for j in range(self.n_features):
            var = sum((row[j] - self.mean[j]) ** 2 for row in X) / n
            self.std.append(math.sqrt(var) if var > 1e-9 else 1.0)

        Xn = [self._normalize(row) for row in X]
        Xn_val = [self._normalize(row) for row in X_val] if X_val else None

        self.w = [0.0] * self.n_features
        self.b = 0.0
        self.history = {"loss": [], "accuracy": [], "val_loss": [], "val_accuracy": []}

        for epoch in range(epochs):
            grad_w = [0.0] * self.n_features
            grad_b = 0.0
            total_loss = 0.0
            correct = 0
            for xi, yi in zip(Xn, y):
                z = self.b + sum(wj * xij for wj, xij in zip(self.w, xi))
                p = _sigmoid(z)
                pc = min(max(p, 1e-12), 1 - 1e-12)
                total_loss += -(yi * math.log(pc) + (1 - yi) * math.log(1 - pc))
                correct += 1 if (p >= 0.5) == (yi == 1) else 0
                err = p - yi
                for j in range(self.n_features):
                    grad_w[j] += err * xi[j]
                grad_b += err

            for j in range(self.n_features):
                self.w[j] -= lr * (grad_w[j] / n + l2 * self.w[j])
            self.b -= lr * (grad_b / n)

            self.history["loss"].append(total_loss / n)
            self.history["accuracy"].append(correct / n)

            if Xn_val:
                vl, va = self._evaluate_normalized(Xn_val, y_val)
                self.history["val_loss"].append(vl)
                self.history["val_accuracy"].append(va)

            if verbose and (epoch % max(1, epochs // 10) == 0 or epoch == epochs - 1):
                msg = f"epoch {epoch:4d}  loss={self.history['loss'][-1]:.4f}  acc={self.history['accuracy'][-1]:.4f}"
                if Xn_val:
                    msg += f"  val_loss={self.history['val_loss'][-1]:.4f}  val_acc={self.history['val_accuracy'][-1]:.4f}"
                print(msg)

    def _evaluate_normalized(self, Xn: list[list[float]], y: list[int]) -> tuple[float, float]:
        n = len(Xn)
        if n == 0:
            return 0.0, 0.0
        total_loss = 0.0
        correct = 0
        for xi, yi in zip(Xn, y):
            z = self.b + sum(wj * xij for wj, xij in zip(self.w, xi))
            p = _sigmoid(z)
            pc = min(max(p, 1e-12), 1 - 1e-12)
            total_loss += -(yi * math.log(pc) + (1 - yi) * math.log(1 - pc))
            correct += 1 if (p >= 0.5) == (yi == 1) else 0
        return total_loss / n, correct / n

    def evaluate(self, X: list[list[float]], y: list[int]) -> tuple[float, float]:
        """원본(정규화되지 않은) 데이터셋에 대한 (BCE 손실, 정확도)를 반환한다."""
        return self._evaluate_normalized([self._normalize(row) for row in X], y)

    # ── 저장/불러오기 ──────────────────────────────────────────────────────
    def save(self, feature_names: list[str], path: Path = MODEL_FILE):
        data = {
            "feature_names": feature_names,
            "w": self.w, "b": self.b,
            "mean": self.mean, "std": self.std,
            "history": self.history,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: Path = MODEL_FILE) -> "WinRateModel | None":
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception:
            return None
        model = cls(len(data["w"]))
        model.w = data["w"]
        model.b = data["b"]
        model.mean = data["mean"]
        model.std = data["std"]
        model.history = data.get("history", {"loss": [], "accuracy": [], "val_loss": [], "val_accuracy": []})
        return model
