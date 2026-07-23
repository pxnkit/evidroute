from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from statistics import mean

import numpy as np


def normalize_answer(text: str | None) -> str:
    if text is None:
        return ""
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def exact_match(prediction: str | None, reference: str | None) -> float:
    return float(normalize_answer(prediction) == normalize_answer(reference))


def token_f1(prediction: str | None, reference: str | None) -> float:
    prediction_tokens = normalize_answer(prediction).split()
    reference_tokens = normalize_answer(reference).split()
    if not prediction_tokens and not reference_tokens:
        return 1.0
    if not prediction_tokens or not reference_tokens:
        return 0.0
    common = Counter(prediction_tokens) & Counter(reference_tokens)
    overlap = sum(common.values())
    if overlap == 0:
        return 0.0
    precision = overlap / len(prediction_tokens)
    recall = overlap / len(reference_tokens)
    return 2 * precision * recall / (precision + recall)


def bootstrap_mean_interval(
    values: Iterable[float],
    *,
    seed: int = 17,
    replicates: int = 1000,
    confidence: float = 0.95,
) -> tuple[float, float, float]:
    array = np.asarray(list(values), dtype=float)
    if array.size == 0:
        return (0.0, 0.0, 0.0)
    generator = np.random.default_rng(seed)
    samples = generator.choice(array, size=(replicates, array.size), replace=True).mean(axis=1)
    alpha = (1 - confidence) / 2
    return (
        float(array.mean()),
        float(np.quantile(samples, alpha)),
        float(np.quantile(samples, 1 - alpha)),
    )


def aggregate_outcomes(rows: list[dict[str, float | bool | str | int | None]]) -> dict[str, float]:
    if not rows:
        return {}

    def average(name: str) -> float:
        values = []
        for row in rows:
            value = row[name]
            if not isinstance(value, (bool, int, float)):
                raise TypeError(f"{name} must be numeric")
            values.append(float(value))
        return mean(values)

    latencies = []
    for row in rows:
        value = row["latency_ms"]
        if not isinstance(value, (bool, int, float)):
            raise TypeError("latency_ms must be numeric")
        latencies.append(float(value))
    latencies.sort()
    return {
        "count": float(len(rows)),
        "exact_match": average("exact_match"),
        "token_f1": average("token_f1"),
        "supported_accuracy": average("supported"),
        "mean_utility": average("utility"),
        "mean_cost": average("monetary_cost"),
        "latency_p50_ms": float(np.quantile(latencies, 0.5)),
        "latency_p90_ms": float(np.quantile(latencies, 0.9)),
        "abstention_rate": mean(1.0 if row.get("answer") in (None, "") else 0.0 for row in rows),
    }
