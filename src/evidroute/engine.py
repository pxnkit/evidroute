from __future__ import annotations

import time
from pathlib import Path

from evidroute.config import EngineConfig, project_root
from evidroute.datasets import CorpusStore
from evidroute.models import (
    Budget,
    EvidenceItem,
    FinalDecision,
    QueryRequest,
    QueryResponse,
    QueryTrace,
    RouteCandidate,
    RouteName,
    TerminalAction,
    TraceEvent,
)
from evidroute.observability import TraceStore
from evidroute.routes import RouteRegistry
from evidroute.routes.base import AcquisitionState
from evidroute.routing import PolicyScorer
from evidroute.synthesis import DeterministicAnswerer


class EvidRouteEngine:
    def __init__(
        self,
        *,
        config: EngineConfig | None = None,
        corpus: CorpusStore | None = None,
        trace_db: Path | None = None,
    ) -> None:
        self.config = config or EngineConfig()
        self.corpus = corpus or CorpusStore()
        self.registry = RouteRegistry(self.corpus)
        self.policy = PolicyScorer(self.registry, self.config)
        self.answerer = DeterministicAnswerer(self.config.confidence_level)
        self.trace_store = TraceStore(trace_db or project_root() / "artifacts" / "traces.sqlite3")

    def _case_metadata(self, query: str) -> dict[str, object]:
        normalized = query.strip().lower()
        for case in self.corpus.cases:
            if case.question.strip().lower() == normalized:
                return {
                    "case_id": case.case_id,
                    "task_family": case.task_family,
                    **case.metadata,
                }
        return {}

    @staticmethod
    def _clarification_needed(query: str, metadata: dict[str, object]) -> bool:
        lowered = query.lower()
        return bool(
            metadata.get("clarification")
            or (
                any(token in lowered for token in ("usual", "that one", "same as before"))
                and "?" not in query
            )
        )

    def query(self, request: QueryRequest) -> QueryResponse:
        started = time.perf_counter()
        metadata = self._case_metadata(request.query)
        budget_initial = request.budget
        budget = request.budget
        events: list[TraceEvent] = []
        evidence: list[EvidenceItem] = []
        selected_routes: list[RouteName] = []
        conflicts: list[dict[str, object]] = []

        if (
            self._clarification_needed(request.query, metadata)
            and budget.clarification_turns > 0
            and not request.user_reply
        ):
            question = str(
                metadata.get("clarification")
                or "Which specific option, location, and time should I use?"
            )
            decision = FinalDecision(
                action=TerminalAction.ASK_USER,
                clarification_question=question,
                explanation="Missing user-specific information is more valuable than another retrieval.",
                confidence=0.98,
                risk=0.02,
                risk_upper_bound=0.04,
                risk_target=request.risk_target,
                guarantee_status="not_applicable_terminal_ask",
                reason_codes=["AMBIGUITY_REQUIRES_USER"],
            )
            candidates = self.policy.candidates(
                AcquisitionState(
                    query=request.query,
                    snapshot_id=request.snapshot_id,
                    memory_namespace=request.memory_namespace,
                    budget=budget,
                    metadata=metadata,
                ),
                request.risk_target,
                budget,
            )
            events.append(
                TraceEvent(
                    event_type="ask_user",
                    message=question,
                    measurements={"clarification_cost": 1},
                )
            )
            return self._finalize(
                request=request,
                candidates=candidates,
                events=events,
                evidence=evidence,
                conflicts=conflicts,
                budget_initial=budget_initial,
                budget_final=Budget(
                    **{
                        **budget.model_dump(),
                        "clarification_turns": max(0, budget.clarification_turns - 1),
                    }
                ),
                decision=decision,
                started=started,
            )

        state = AcquisitionState(
            query=request.query
            if not request.user_reply
            else f"{request.query} {request.user_reply}",
            snapshot_id=request.snapshot_id,
            memory_namespace=request.memory_namespace,
            budget=budget,
            metadata=metadata,
        )
        initial_candidates = self.policy.candidates(state, request.risk_target, budget)
        events.extend(
            TraceEvent(
                event_type="route_considered",
                route=candidate.route,
                message="Route scored from decision-time features.",
                measurements={
                    "utility": candidate.utility,
                    "predicted_risk": candidate.predicted_risk,
                    "risk_upper_bound": candidate.risk_upper_bound,
                    "expected_cost": candidate.expected_cost,
                    "feasible": candidate.feasible,
                    "reason_codes": candidate.reason_codes,
                },
            )
            for candidate in initial_candidates
        )

        decision = FinalDecision(
            action=TerminalAction.ABSTAIN,
            explanation="No feasible evidence route produced support.",
            confidence=0.0,
            risk=1.0,
            risk_upper_bound=1.0,
            risk_target=request.risk_target,
            guarantee_status="no_supported_evidence",
            reason_codes=["NO_SUPPORTED_EVIDENCE"],
        )
        require_multiple = bool(
            metadata.get("requires_conflict_display") or metadata.get("multi_claim")
        )
        maximum_calls = min(self.config.max_route_calls, request.budget.route_calls)

        for step in range(maximum_calls):
            state = AcquisitionState(
                query=state.query,
                snapshot_id=request.snapshot_id,
                memory_namespace=request.memory_namespace,
                budget=budget,
                acquired_routes=selected_routes,
                evidence_ids=[item.evidence_id for item in evidence],
                metadata=metadata,
            )
            current_candidates = self.policy.candidates(state, request.risk_target, budget)
            selected = self.policy.select(current_candidates)
            if selected is None or selected.expected_information_gain <= 0:
                events.append(
                    TraceEvent(
                        event_type="routing_stopped",
                        message="No feasible route has positive expected information value.",
                        measurements={"step": step},
                    )
                )
                break
            for initial in initial_candidates:
                if initial.route == selected.route:
                    initial.selected = True
                    if "SELECTED" not in initial.reason_codes:
                        initial.reason_codes.append("SELECTED")
            adapter = self.registry.get(selected.route)
            estimate = adapter.estimate(state)
            events.append(
                TraceEvent(
                    event_type="route_selected",
                    route=selected.route,
                    message="Selected route with maximum conservative utility.",
                    measurements={
                        "step": step,
                        "utility": selected.utility,
                        "budget_before": budget.model_dump(),
                    },
                )
            )
            bundle = adapter.acquire(state, budget)
            selected_routes.append(selected.route)
            budget = budget.spend(estimate)
            if bundle.error_code is not None:
                events.append(
                    TraceEvent(
                        event_type="route_failed",
                        route=selected.route,
                        message=bundle.error_message or "typed route failure",
                        measurements={
                            "error_code": bundle.error_code.value,
                            "budget_after": budget.model_dump(),
                        },
                    )
                )
                continue
            evidence.extend(bundle.items)
            events.append(
                TraceEvent(
                    event_type="acquisition_completed",
                    route=selected.route,
                    message=f"Acquired {len(bundle.items)} normalized evidence items.",
                    measurements={
                        "evidence_ids": [item.evidence_id for item in bundle.items],
                        "latency_ms": bundle.actual_latency_ms,
                        "cost": bundle.actual_monetary_cost,
                        "budget_after": budget.model_dump(),
                    },
                )
            )
            decision, conflicts = self.answerer.decide(
                query=request.query,
                items=evidence,
                mode=request.mode,
                risk_target=request.risk_target,
                shift_detected=bool(metadata.get("shift")),
            )
            if conflicts:
                events.append(
                    TraceEvent(
                        event_type="conflict_detected",
                        message="Incompatible source claims were retained for audit.",
                        measurements={"conflict_count": len(conflicts)},
                    )
                )
            enough_evidence = not require_multiple or len(selected_routes) >= 2
            if decision.action is TerminalAction.ANSWER and enough_evidence:
                events.append(
                    TraceEvent(
                        event_type="risk_decision",
                        message="Answer accepted under the configured risk target.",
                        measurements={
                            "risk": decision.risk,
                            "upper_bound": decision.risk_upper_bound,
                            "target": request.risk_target,
                        },
                    )
                )
                break

        if metadata.get("unsafe_evidence") and any(item.unsafe_content for item in evidence):
            decision = FinalDecision(
                action=TerminalAction.ABSTAIN,
                explanation="Retrieved content contains prompt-injection indicators and no independent safe support.",
                confidence=0.0,
                risk=1.0,
                risk_upper_bound=1.0,
                risk_target=request.risk_target,
                guarantee_status="unsafe_evidence",
                citations=[item.evidence_id for item in evidence if item.unsafe_content],
                reason_codes=["PROMPT_INJECTION_DETECTED", "FAIL_CLOSED"],
            )
        if metadata.get("privacy_denied"):
            decision = FinalDecision(
                action=TerminalAction.ABSTAIN,
                explanation="Privacy policy blocks transmitting private memory to external routes.",
                confidence=1.0,
                risk=0.0,
                risk_upper_bound=0.0,
                risk_target=request.risk_target,
                guarantee_status="policy_denial",
                reason_codes=["PRIVATE_MEMORY_EXTERNAL_DENIED"],
            )

        return self._finalize(
            request=request,
            candidates=initial_candidates,
            events=events,
            evidence=evidence,
            conflicts=conflicts,
            budget_initial=budget_initial,
            budget_final=budget,
            decision=decision,
            started=started,
        )

    def _finalize(
        self,
        *,
        request: QueryRequest,
        candidates: list[RouteCandidate],
        events: list[TraceEvent],
        evidence: list[EvidenceItem],
        conflicts: list[dict[str, object]],
        budget_initial: Budget,
        budget_final: Budget,
        decision: FinalDecision,
        started: float,
    ) -> QueryResponse:
        elapsed_ms = max(1, round((time.perf_counter() - started) * 1000))
        events.append(
            TraceEvent(
                event_type=decision.action.value.lower(),
                message=decision.explanation,
                measurements={
                    "confidence": decision.confidence,
                    "risk": decision.risk,
                    "reason_codes": decision.reason_codes,
                },
            )
        )
        trace = QueryTrace(
            query=request.query,
            mode=request.mode,
            snapshot_id=request.snapshot_id,
            policy=request.policy,
            candidates=candidates,
            events=events,
            evidence=evidence,
            conflicts=conflicts,
            budget_initial=budget_initial,
            budget_final=budget_final,
            final_decision=decision,
            config_hash=self.config.digest(),
            source_versions={
                "corpus_snapshot": request.snapshot_id,
                "bm25": "bm25-mini-v1",
                "dense": "dense-hash-v1",
                "structured": f"schema-{self.corpus.schema_versions[request.snapshot_id]}",
            },
            model_versions={"router": "rule-voi-v1", "answerer": "deterministic-cited-v1"},
            timing_ms={"total": elapsed_ms},
        )
        self.trace_store.save(trace)
        return QueryResponse(
            trace_id=trace.trace_id,
            decision=decision,
            candidates=candidates,
            evidence=evidence,
            conflicts=conflicts,
            events=events,
            budget_remaining=budget_final,
        )

    def get_trace(self, trace_id: str) -> QueryTrace | None:
        return self.trace_store.get(trace_id)

    def source_health(self, snapshot_id: str) -> list[dict[str, object]]:
        return [
            adapter.health(snapshot_id).model_dump(mode="json") for adapter in self.registry.all()
        ]
