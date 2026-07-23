from __future__ import annotations

import numpy as np
import pytest

from evidroute.evaluation import (
    aggregate_outcomes,
    bootstrap_mean_interval,
    exact_match,
    token_f1,
)
from evidroute.risk import SelectiveRiskController, detect_source_shift, wilson_upper_bound
from evidroute.shifts import ShiftSuite


def test_answer_metrics_normalize_and_score_partial_overlap() -> None:
    assert exact_match("The Zurich.", "zurich") == 0.0
    assert exact_match("Zurich!", "zurich") == 1.0
    assert token_f1("18 researchers", "18 researchers in Tycho crater") == pytest.approx(4 / 7)
    assert token_f1(None, None) == 1.0


def test_bootstrap_interval_is_seeded_and_contains_mean() -> None:
    first = bootstrap_mean_interval([0.1, 0.3, 0.5], seed=17, replicates=250)
    second = bootstrap_mean_interval([0.1, 0.3, 0.5], seed=17, replicates=250)

    assert first == second
    assert first[1] <= first[0] <= first[2]


def test_aggregate_outcomes_reports_quality_cost_and_abstention() -> None:
    rows = [
        {
            "exact_match": 1.0,
            "token_f1": 1.0,
            "supported": True,
            "utility": 0.9,
            "monetary_cost": 0.01,
            "latency_ms": 10,
            "answer": "Zurich",
        },
        {
            "exact_match": 0.0,
            "token_f1": 0.0,
            "supported": False,
            "utility": 0.1,
            "monetary_cost": 0.0,
            "latency_ms": 20,
            "answer": None,
        },
    ]

    metrics = aggregate_outcomes(rows)

    assert metrics["supported_accuracy"] == 0.5
    assert metrics["mean_cost"] == 0.005
    assert metrics["abstention_rate"] == 0.5
    assert metrics["latency_p50_ms"] == 15


def test_selective_risk_controller_finds_conservative_threshold() -> None:
    scores = [0.99] * 30 + [0.2] * 10
    losses = [0] * 30 + [1] * 10

    result = SelectiveRiskController().fit(scores, losses, 0.2, "t1")

    assert result.threshold == 0.99
    assert result.coverage == 0.75
    assert result.upper_bound <= result.risk_target
    assert wilson_upper_bound(0, 30) < 0.2


def test_selective_risk_controller_rejects_invalid_scores() -> None:
    with pytest.raises(ValueError):
        SelectiveRiskController().fit([1.2], [0], 0.2, "t1")


def test_shift_detection_invalidates_exchangeability_claim() -> None:
    report = detect_source_shift(
        [0.9, 0.88, 0.86, 0.84],
        [0.3, 0.25, 0.2, 0.15],
        reference_error_rate=0.05,
        observed_error_rate=0.4,
    )

    assert report.detected
    assert "SOURCE_ERROR_RATE_SHIFT" in report.reason_codes
    assert report.guarantee_status == "unavailable_under_shift"


def test_population_shift_suite_is_deterministic() -> None:
    manifests = ShiftSuite.built_in()

    assert len(manifests) == 10
    assert len({manifest.manifest_id for manifest in manifests}) == len(manifests)
    assert ShiftSuite.evaluate().detected
    assert np.mean([manifest.severity for manifest in manifests]) > 0.5
