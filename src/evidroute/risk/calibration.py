from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np


def wilson_upper_bound(errors: int, total: int, confidence: float = 0.95) -> float:
    if total <= 0:
        return 1.0
    z = NormalDist().inv_cdf(confidence)
    proportion = errors / total
    denominator = 1 + z * z / total
    center = proportion + z * z / (2 * total)
    radius = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total))
    return min(1.0, (center + radius) / denominator)


@dataclass(frozen=True)
class RiskCalibration:
    threshold: float
    risk_target: float
    empirical_risk: float
    upper_bound: float
    coverage: float
    calibration_size: int
    confidence: float
    loss_definition: str
    snapshot_id: str
    guarantee_status: str

    def as_dict(self) -> dict[str, float | int | str]:
        return {
            "threshold": self.threshold,
            "risk_target": self.risk_target,
            "empirical_risk": self.empirical_risk,
            "upper_bound": self.upper_bound,
            "coverage": self.coverage,
            "calibration_size": self.calibration_size,
            "confidence": self.confidence,
            "loss_definition": self.loss_definition,
            "snapshot_id": self.snapshot_id,
            "guarantee_status": self.guarantee_status,
        }


class SelectiveRiskController:
    def __init__(self, confidence: float = 0.95) -> None:
        self.confidence = confidence

    def fit(
        self,
        scores: list[float],
        losses: list[int],
        risk_target: float,
        snapshot_id: str,
    ) -> RiskCalibration:
        if len(scores) != len(losses) or not scores:
            raise ValueError("scores and losses must have the same non-zero length")
        score_array = np.asarray(scores, dtype=float)
        loss_array = np.asarray(losses, dtype=int)
        if np.any((score_array < 0) | (score_array > 1)):
            raise ValueError("scores must be probabilities in [0, 1]")
        if np.any((loss_array != 0) & (loss_array != 1)):
            raise ValueError("losses must be binary")

        best: RiskCalibration | None = None
        thresholds = sorted(set(float(value) for value in score_array), reverse=True)
        for threshold in thresholds:
            accepted = score_array >= threshold
            total = int(accepted.sum())
            errors = int(loss_array[accepted].sum())
            empirical = errors / total if total else 1.0
            upper = wilson_upper_bound(errors, total, self.confidence)
            calibration = RiskCalibration(
                threshold=threshold,
                risk_target=risk_target,
                empirical_risk=empirical,
                upper_bound=upper,
                coverage=total / len(scores),
                calibration_size=len(scores),
                confidence=self.confidence,
                loss_definition="unsupported_or_incorrect",
                snapshot_id=snapshot_id,
                guarantee_status="exchangeable_calibration",
            )
            if upper <= risk_target and (best is None or calibration.coverage > best.coverage):
                best = calibration

        if best is not None:
            return best
        return RiskCalibration(
            threshold=1.0,
            risk_target=risk_target,
            empirical_risk=0.0,
            upper_bound=1.0,
            coverage=0.0,
            calibration_size=len(scores),
            confidence=self.confidence,
            loss_definition="unsupported_or_incorrect",
            snapshot_id=snapshot_id,
            guarantee_status="no_safe_threshold",
        )

    def conservative_upper(self, predicted_risk: float, effective_n: int = 100) -> float:
        errors = max(0, min(effective_n, round(predicted_risk * effective_n)))
        return wilson_upper_bound(errors, effective_n, self.confidence)
