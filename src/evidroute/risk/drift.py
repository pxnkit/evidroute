from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DriftReport:
    detected: bool
    severity: float
    statistics: dict[str, float]
    reason_codes: list[str]
    guarantee_status: str

    def as_dict(self) -> dict[str, object]:
        return {
            "detected": self.detected,
            "severity": self.severity,
            "statistics": self.statistics,
            "reason_codes": self.reason_codes,
            "guarantee_status": self.guarantee_status,
        }


def population_stability_index(
    reference: np.ndarray, observed: np.ndarray, bins: int = 10
) -> float:
    if reference.size == 0 or observed.size == 0:
        return 1.0
    boundaries = np.quantile(reference, np.linspace(0, 1, bins + 1))
    boundaries[0] = -np.inf
    boundaries[-1] = np.inf
    reference_counts, _ = np.histogram(reference, boundaries)
    observed_counts, _ = np.histogram(observed, boundaries)
    reference_rates = np.clip(reference_counts / reference.size, 1e-6, None)
    observed_rates = np.clip(observed_counts / observed.size, 1e-6, None)
    return float(
        np.sum((observed_rates - reference_rates) * np.log(observed_rates / reference_rates))
    )


def detect_source_shift(
    reference_scores: list[float],
    observed_scores: list[float],
    reference_error_rate: float,
    observed_error_rate: float,
    threshold: float = 0.2,
) -> DriftReport:
    reference = np.asarray(reference_scores, dtype=float)
    observed = np.asarray(observed_scores, dtype=float)
    psi = population_stability_index(reference, observed)
    mean_shift = (
        float(abs(observed.mean() - reference.mean())) if reference.size and observed.size else 1.0
    )
    error_shift = max(0.0, observed_error_rate - reference_error_rate)
    severity = min(1.0, max(psi, mean_shift, error_shift))
    codes = []
    if psi > threshold:
        codes.append("SCORE_DISTRIBUTION_SHIFT")
    if error_shift > threshold:
        codes.append("SOURCE_ERROR_RATE_SHIFT")
    if mean_shift > threshold:
        codes.append("MEAN_SCORE_SHIFT")
    detected = bool(codes)
    return DriftReport(
        detected=detected,
        severity=severity,
        statistics={"psi": psi, "mean_shift": mean_shift, "error_rate_shift": error_shift},
        reason_codes=codes,
        guarantee_status="unavailable_under_shift"
        if detected
        else "calibration_distribution_compatible",
    )
