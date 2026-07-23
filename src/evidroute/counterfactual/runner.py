from __future__ import annotations

import json
from pathlib import Path

from evidroute.config import EngineConfig
from evidroute.datasets import CorpusStore
from evidroute.evaluation import exact_match, token_f1
from evidroute.models import (
    Budget,
    CounterfactualOutcome,
    TerminalAction,
    VerificationMode,
)
from evidroute.routes import RouteRegistry
from evidroute.routes.base import AcquisitionState
from evidroute.synthesis import DeterministicAnswerer


class CounterfactualRunner:
    def __init__(
        self,
        *,
        corpus: CorpusStore | None = None,
        config: EngineConfig | None = None,
        seed: int = 17,
    ) -> None:
        self.corpus = corpus or CorpusStore()
        self.config = config or EngineConfig()
        self.seed = seed
        self.registry = RouteRegistry(self.corpus)
        self.answerer = DeterministicAnswerer(self.config.confidence_level)

    def run(self, splits: set[str] | None = None) -> list[CounterfactualOutcome]:
        outcomes: list[CounterfactualOutcome] = []
        for case in self.corpus.cases:
            if splits is not None and case.split not in splits:
                continue
            metadata = {"case_id": case.case_id, "task_family": case.task_family, **case.metadata}
            for adapter in self.registry.all():
                state = AcquisitionState(
                    query=case.question,
                    snapshot_id=case.snapshot_id,
                    memory_namespace=str(case.metadata.get("namespace", "demo")),
                    budget=Budget(),
                    metadata=metadata,
                )
                bundle = adapter.acquire(state, state.budget)
                items = bundle.items
                mode = (
                    VerificationMode.BEST_EFFORT
                    if case.metadata.get("verified_external_required") is False
                    else VerificationMode.VERIFIED
                )
                decision, _ = self.answerer.decide(
                    query=case.question,
                    items=items,
                    mode=mode,
                    risk_target=0.5,
                    shift_detected=bool(case.metadata.get("shift")),
                )
                predicted_answer = (
                    decision.answer if decision.action is TerminalAction.ANSWER else None
                )
                em = exact_match(predicted_answer, case.gold_answer)
                f1 = token_f1(predicted_answer, case.gold_answer)
                correct_terminal = decision.action is case.gold_action
                correct = bool(
                    em == 1.0 if case.gold_action is TerminalAction.ANSWER else correct_terminal
                )
                cited_document_ids = {
                    str(item.metadata.get("document_id") or item.evidence_id.split(":")[-1])
                    for item in items
                    if item.evidence_id in decision.citations
                }
                gold = set(case.gold_support_ids)
                evidence_recall = (
                    len(cited_document_ids.intersection(gold)) / len(gold)
                    if gold
                    else float(not items)
                )
                citation_precision = (
                    len(cited_document_ids.intersection(gold)) / len(cited_document_ids)
                    if cited_document_ids
                    else float(not gold)
                )
                supported = bool(
                    decision.action is TerminalAction.ANSWER
                    and decision.citations
                    and evidence_recall > 0
                )
                if case.metadata.get("verified_external_required") is False:
                    supported = correct
                policy_compliant = not (
                    case.metadata.get("unsafe_evidence")
                    and decision.action is TerminalAction.ANSWER
                )
                utility = (
                    self.config.utility.supported_quality * float(supported)
                    + self.config.utility.action_success * float(correct_terminal)
                    - self.config.utility.cost * bundle.actual_monetary_cost
                    - self.config.utility.latency
                    * __import__("math").log1p(bundle.actual_latency_ms / 100)
                    - self.config.utility.contradiction
                    * float(bool(case.metadata.get("requires_conflict_display") and len(items) < 2))
                )
                outcomes.append(
                    CounterfactualOutcome(
                        case_id=case.case_id,
                        split=case.split,
                        route=adapter.name,
                        feasible=bundle.error_code is None,
                        answer=predicted_answer,
                        exact_match=em,
                        token_f1=f1,
                        correct=correct,
                        evidence_recall=evidence_recall,
                        citation_precision=citation_precision,
                        citation_recall=evidence_recall,
                        citation_completeness=evidence_recall,
                        supported=supported,
                        contradiction=bool(
                            case.metadata.get("requires_conflict_display") and len(items) < 2
                        ),
                        policy_compliant=policy_compliant,
                        action_success=correct_terminal,
                        monetary_cost=bundle.actual_monetary_cost,
                        latency_ms=bundle.actual_latency_ms,
                        route_calls=1,
                        error_code=bundle.error_code,
                        utility=utility,
                        source_version=case.snapshot_id,
                        seed=self.seed,
                        config_hash=self.config.digest(),
                    )
                )
        return outcomes

    @staticmethod
    def save(outcomes: list[CounterfactualOutcome], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for outcome in outcomes:
                handle.write(json.dumps(outcome.model_dump(mode="json"), sort_keys=True) + "\n")

    @staticmethod
    def oracle(outcomes: list[CounterfactualOutcome]) -> dict[str, CounterfactualOutcome]:
        by_case: dict[str, list[CounterfactualOutcome]] = {}
        for outcome in outcomes:
            if outcome.feasible:
                by_case.setdefault(outcome.case_id, []).append(outcome)
        return {
            case_id: max(rows, key=lambda row: (row.utility, -row.monetary_cost, row.route.value))
            for case_id, rows in by_case.items()
        }

    @staticmethod
    def regret(
        selected: dict[str, CounterfactualOutcome],
        oracle: dict[str, CounterfactualOutcome],
    ) -> dict[str, float]:
        return {
            case_id: oracle_row.utility - selected[case_id].utility
            for case_id, oracle_row in oracle.items()
            if case_id in selected
        }
