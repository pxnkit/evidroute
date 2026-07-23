from __future__ import annotations

from pathlib import Path

import pytest

from evidroute.counterfactual import CounterfactualRunner
from evidroute.datasets import CorpusStore
from evidroute.engine import EvidRouteEngine
from evidroute.models import (
    Budget,
    QueryRequest,
    RouteErrorCode,
    RouteName,
    TerminalAction,
    VerificationMode,
)
from evidroute.routes import RouteRegistry
from evidroute.routes.base import AcquisitionState
from evidroute.routing.learned import PotentialOutcomeRouter


def test_route_registry_exposes_all_required_sources() -> None:
    routes = {adapter.name for adapter in RouteRegistry(CorpusStore()).all()}
    assert routes == set(RouteName)


def test_bm25_returns_exact_token_with_normalized_provenance() -> None:
    adapter = RouteRegistry(CorpusStore()).get(RouteName.BM25)
    state = AcquisitionState(
        query="What is the exact verification token for the Heliotrope gate?",
        snapshot_id="t1",
    )

    bundle = adapter.acquire(state, Budget())

    assert bundle.error_code is None
    assert bundle.items[0].metadata["answer"] == "VIOLET-731"
    assert bundle.items[0].source_uri.startswith("miniroute://")
    assert bundle.items[0].route is RouteName.BM25


def test_live_web_is_disabled_and_typed_in_offline_mode() -> None:
    adapter = RouteRegistry(CorpusStore()).get(RouteName.LIVE_WEB)
    state = AcquisitionState(query="latest news", snapshot_id="t1")

    assert adapter.availability(state) is False
    assert adapter.acquire(state, Budget()).error_code is RouteErrorCode.UNAVAILABLE


@pytest.mark.integration
def test_engine_answers_temporal_snapshot_with_exact_citation(
    engine: EvidRouteEngine,
) -> None:
    response = engine.query(
        QueryRequest(
            query=(
                "According to the latest snapshot, which Dresden venue will host "
                "the fictional Elbe AI Systems Workshop?"
            ),
            risk_target=0.3,
        )
    )

    assert response.decision.action is TerminalAction.ANSWER
    assert response.decision.answer == "TU Dresden"
    assert response.decision.citations == ["frozen_web:elbe_workshop_t1"]
    assert response.decision.risk_upper_bound <= 0.3
    assert any(
        candidate.route is RouteName.FROZEN_WEB and candidate.selected
        for candidate in response.candidates
    )


@pytest.mark.integration
def test_engine_respects_historical_snapshot(engine: EvidRouteEngine) -> None:
    response = engine.query(
        QueryRequest(
            query=(
                "According to the initial snapshot, which Dresden venue was planned "
                "for the fictional Elbe AI Systems Workshop?"
            ),
            snapshot_id="t0",
            risk_target=0.35,
        )
    )

    assert response.decision.action is TerminalAction.ANSWER
    assert response.decision.answer == "Dresden City Lab"
    assert all(item.snapshot_id == "t0" for item in response.evidence)


@pytest.mark.integration
def test_engine_asks_for_high_value_missing_user_information(
    engine: EvidRouteEngine,
) -> None:
    response = engine.query(QueryRequest(query="Book the usual briefing room."))

    assert response.decision.action is TerminalAction.ASK_USER
    assert "location and time" in (response.decision.clarification_question or "")
    assert response.budget_remaining.clarification_turns == 0


@pytest.mark.failure_injection
def test_prompt_injection_fails_closed(engine: EvidRouteEngine) -> None:
    response = engine.query(
        QueryRequest(query="What version is the Redwood protocol?", risk_target=0.5)
    )

    assert response.decision.action is TerminalAction.ABSTAIN
    assert "PROMPT_INJECTION_DETECTED" in response.decision.reason_codes
    assert any(item.unsafe_content for item in response.evidence)


@pytest.mark.failure_injection
def test_all_route_outage_abstains_without_fabrication(engine: EvidRouteEngine) -> None:
    response = engine.query(
        QueryRequest(query="Run the all-routes outage scenario.", risk_target=0.5)
    )

    assert response.decision.action is TerminalAction.ABSTAIN
    assert response.decision.answer is None
    assert "NO_SUPPORTED_EVIDENCE" in response.decision.reason_codes


def test_trace_is_persisted_and_canonical(engine: EvidRouteEngine) -> None:
    response = engine.query(
        QueryRequest(
            query="What is the exact verification token for the Heliotrope gate?",
            risk_target=0.4,
        )
    )
    trace = engine.get_trace(response.trace_id)

    assert trace is not None
    assert trace.final_decision == response.decision
    assert trace.config_hash == engine.config.digest()
    assert '"trace_id":' in trace.canonical_json()


def test_counterfactual_runner_and_router_are_reproducible(tmp_path: Path) -> None:
    corpus = CorpusStore()
    outcomes = CounterfactualRunner(corpus=corpus, seed=17).run({"train", "calibration"})
    repeated = CounterfactualRunner(corpus=corpus, seed=17).run({"train", "calibration"})
    assert outcomes == repeated

    router = PotentialOutcomeRouter().fit(outcomes, corpus)
    path = tmp_path / "router.pkl"
    router.save(path)
    loaded = PotentialOutcomeRouter.load(path)
    predictions = loaded.predict(
        query="Which Dresden venue will host the fictional Elbe AI Systems Workshop?",
        task_family="temporal_update",
        snapshot_id="t1",
        feasible_routes=[RouteName.BM25, RouteName.FROZEN_WEB],
    )

    assert len(predictions) == 2
    assert predictions == sorted(
        predictions,
        key=lambda row: (-row.expected_utility, row.route.value),
    )


def test_verified_mode_blocks_unsupported_parametric_answer(
    engine: EvidRouteEngine,
) -> None:
    response = engine.query(
        QueryRequest(
            query="What is two plus two?",
            mode=VerificationMode.VERIFIED,
            budget=Budget(route_calls=1),
            risk_target=0.5,
        )
    )
    assert response.decision.action is TerminalAction.ABSTAIN
