from __future__ import annotations

import pickle
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.feature_extraction import DictVectorizer
from sklearn.pipeline import Pipeline

from evidroute.datasets import CorpusStore
from evidroute.models import CounterfactualOutcome, RouteName


@dataclass(frozen=True)
class RoutePrediction:
    route: RouteName
    expected_utility: float


class PotentialOutcomeRouter:
    def __init__(self) -> None:
        self.pipeline: Pipeline | None = None

    @staticmethod
    def _rows(
        outcomes: list[CounterfactualOutcome],
        corpus: CorpusStore,
    ) -> tuple[list[dict[str, str | float]], np.ndarray]:
        case_map = {case.case_id: case for case in corpus.cases}
        rows: list[dict[str, str | float]] = []
        for outcome in outcomes:
            case = case_map[outcome.case_id]
            row: dict[str, str | float] = {
                "query": case_map[outcome.case_id].question,
                "route": outcome.route.value,
                "snapshot": outcome.source_version,
                "task_family": case.task_family,
            }
            for token in re.findall(r"[a-z0-9-]+", case.question.lower()):
                row[f"token={token}"] = 1.0
            rows.append(row)
        targets = np.asarray([outcome.utility for outcome in outcomes], dtype=float)
        return rows, targets

    def fit(
        self, outcomes: list[CounterfactualOutcome], corpus: CorpusStore
    ) -> PotentialOutcomeRouter:
        feasible = [outcome for outcome in outcomes if outcome.feasible]
        if len(feasible) < 8:
            raise ValueError("at least eight feasible counterfactual outcomes are required")
        rows, targets = self._rows(feasible, corpus)
        self.pipeline = Pipeline(
            [
                ("features", DictVectorizer(sparse=False)),
                (
                    "regressor",
                    HistGradientBoostingRegressor(
                        max_iter=80,
                        max_depth=4,
                        learning_rate=0.08,
                        l2_regularization=0.1,
                        random_state=17,
                    ),
                ),
            ]
        )
        self.pipeline.fit(rows, targets)
        return self

    def predict(
        self,
        *,
        query: str,
        task_family: str,
        snapshot_id: str,
        feasible_routes: list[RouteName],
    ) -> list[RoutePrediction]:
        if self.pipeline is None:
            raise RuntimeError("router has not been fitted")
        rows = []
        for route in feasible_routes:
            row: dict[str, str | float] = {
                "query": query,
                "route": route.value,
                "snapshot": snapshot_id,
                "task_family": task_family,
            }
            for token in re.findall(r"[a-z0-9-]+", query.lower()):
                row[f"token={token}"] = 1.0
            rows.append(row)
        predictions = self.pipeline.predict(rows)
        return sorted(
            [
                RoutePrediction(route=route, expected_utility=float(value))
                for route, value in zip(feasible_routes, predictions, strict=True)
            ],
            key=lambda row: (-row.expected_utility, row.route.value),
        )

    def save(self, path: Path) -> None:
        if self.pipeline is None:
            raise RuntimeError("router has not been fitted")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pickle.dumps(self.pipeline, protocol=pickle.HIGHEST_PROTOCOL))

    @classmethod
    def load(cls, path: Path) -> PotentialOutcomeRouter:
        instance = cls()
        pipeline = pickle.loads(path.read_bytes())
        if not isinstance(pipeline, Pipeline):
            raise TypeError("model checkpoint does not contain an sklearn Pipeline")
        instance.pipeline = pipeline
        return instance

    @staticmethod
    def pairwise_regret_loss(
        predicted: np.ndarray,
        observed: np.ndarray,
        groups: np.ndarray,
    ) -> float:
        losses = []
        for group in np.unique(groups):
            mask = groups == group
            pred = predicted[mask]
            gold = observed[mask]
            for left in range(len(pred)):
                for right in range(left + 1, len(pred)):
                    gold_sign = np.sign(gold[left] - gold[right])
                    if gold_sign == 0:
                        continue
                    margin = gold_sign * (pred[left] - pred[right])
                    losses.append(max(0.0, 1.0 - margin))
        return float(np.mean(losses)) if losses else 0.0


def query_features(query: str) -> dict[str, float]:
    tokens = re.findall(r"[a-z0-9]+", query.lower())
    return {
        "length": float(len(tokens)),
        "temporal": float(
            any(token in {"latest", "current", "today", "2025", "2026"} for token in tokens)
        ),
        "relational": float(
            any(token in {"who", "founded", "directs", "identifier"} for token in tokens)
        ),
        "personal": float(any(token in {"my", "user", "prefer", "usual"} for token in tokens)),
    }
