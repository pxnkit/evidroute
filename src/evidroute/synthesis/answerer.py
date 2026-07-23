from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from evidroute.models import (
    EvidenceItem,
    FinalDecision,
    TerminalAction,
    VerificationMode,
)
from evidroute.risk import SelectiveRiskController


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


class DeterministicAnswerer:
    def __init__(self, confidence: float = 0.95) -> None:
        self.risk_controller = SelectiveRiskController(confidence)

    @staticmethod
    def deduplicate(items: list[EvidenceItem]) -> list[EvidenceItem]:
        seen: set[str] = set()
        output: list[EvidenceItem] = []
        for item in sorted(items, key=lambda row: -row.retrieval_score):
            group = str(item.metadata.get("duplicate_group") or item.integrity_hash)
            if group in seen:
                continue
            seen.add(group)
            output.append(item)
        return output

    @staticmethod
    def conflicts(items: list[EvidenceItem]) -> list[dict[str, Any]]:
        grouped: dict[str, list[EvidenceItem]] = defaultdict(list)
        for item in items:
            key = item.metadata.get("conflict_key")
            if key:
                grouped[str(key)].append(item)
        conflicts: list[dict[str, Any]] = []
        for key, group in grouped.items():
            answers = {
                str(item.metadata.get("answer")) for item in group if item.metadata.get("answer")
            }
            if len(answers) > 1:
                conflicts.append(
                    {
                        "conflict_key": key,
                        "claims": [
                            {
                                "answer": item.metadata.get("answer"),
                                "evidence_id": item.evidence_id,
                                "updated_at": item.source_updated_at.isoformat()
                                if item.source_updated_at
                                else None,
                                "reliability": item.metadata.get("reliability", 0.5),
                            }
                            for item in group
                        ],
                        "policy_response": "prefer current, higher-reliability evidence and expose conflict",
                    }
                )
        return conflicts

    @staticmethod
    def _rank(item: EvidenceItem) -> tuple[float, float, float]:
        reliability = float(item.metadata.get("reliability", 0.8))
        stale_penalty = 0.45 if item.metadata.get("stale") else 1.0
        unsafe_penalty = 0.0 if item.unsafe_content else 1.0
        return (
            unsafe_penalty,
            reliability * stale_penalty,
            item.retrieval_score,
        )

    def decide(
        self,
        *,
        query: str,
        items: list[EvidenceItem],
        mode: VerificationMode,
        risk_target: float,
        shift_detected: bool = False,
    ) -> tuple[FinalDecision, list[dict[str, Any]]]:
        deduplicated = self.deduplicate(items)
        conflicts = self.conflicts(deduplicated)
        safe_items = [item for item in deduplicated if not item.unsafe_content]
        ranked = sorted(safe_items, key=self._rank, reverse=True)
        answer_items = [item for item in ranked if item.metadata.get("answer")]

        if not answer_items:
            return (
                FinalDecision(
                    action=TerminalAction.ABSTAIN,
                    explanation="No acquired source safely supports a material answer.",
                    confidence=0.0,
                    risk=1.0,
                    risk_upper_bound=1.0,
                    risk_target=risk_target,
                    guarantee_status="no_supported_evidence",
                    reason_codes=["NO_SUPPORTED_EVIDENCE"],
                ),
                conflicts,
            )

        query_lower = query.lower()
        selected_items = [answer_items[0]]
        if " and where " in query_lower or ("how many" in query_lower and "where" in query_lower):
            unique_answers: list[EvidenceItem] = []
            normalized_answers: set[str] = set()
            for item in answer_items:
                answer = _normalize(str(item.metadata["answer"]))
                if answer and answer not in normalized_answers:
                    normalized_answers.add(answer)
                    unique_answers.append(item)
            selected_items = unique_answers[:2]
        elif conflicts:
            selected_items = sorted(
                answer_items,
                key=lambda item: (
                    item.source_updated_at.timestamp() if item.source_updated_at else 0.0,
                    float(item.metadata.get("reliability", 0.5)),
                ),
                reverse=True,
            )[:1]

        answers = [str(item.metadata["answer"]) for item in selected_items]
        answer = " in ".join(answers) if len(answers) == 2 else answers[0]
        citations = [item.evidence_id for item in selected_items]
        support_available = all(
            item.route.value != "PARAMETRIC" or bool(item.metadata.get("support_available"))
            for item in selected_items
        )
        if mode is VerificationMode.VERIFIED and not support_available:
            return (
                FinalDecision(
                    action=TerminalAction.ABSTAIN,
                    explanation="The direct proposal has no external support in verified mode.",
                    confidence=0.6,
                    risk=0.4,
                    risk_upper_bound=0.5,
                    risk_target=risk_target,
                    guarantee_status="verification_required",
                    citations=[],
                    reason_codes=["PARAMETRIC_UNVERIFIED"],
                ),
                conflicts,
            )

        confidence = min(
            0.98,
            sum(
                min(1.0, item.retrieval_score) * float(item.metadata.get("reliability", 0.85))
                for item in selected_items
            )
            / len(selected_items),
        )
        if mode is VerificationMode.BEST_EFFORT and not support_available:
            confidence = min(confidence, 0.78)
        risk = max(0.01, 1 - confidence)
        upper = self.risk_controller.conservative_upper(risk, effective_n=300)
        if shift_detected:
            upper = min(1.0, upper + 0.15)
        if upper > risk_target:
            return (
                FinalDecision(
                    action=TerminalAction.ABSTAIN,
                    explanation="The calibrated risk upper bound exceeds the requested target.",
                    confidence=confidence,
                    risk=risk,
                    risk_upper_bound=upper,
                    risk_target=risk_target,
                    guarantee_status="unavailable_under_shift"
                    if shift_detected
                    else "risk_above_target",
                    citations=citations,
                    reason_codes=["RISK_ABOVE_TARGET"],
                ),
                conflicts,
            )
        return (
            FinalDecision(
                action=TerminalAction.ANSWER,
                answer=answer,
                explanation=(
                    "Answer accepted from normalized evidence with exact provenance."
                    if support_available
                    else "Best-effort offline proposal; no external citation is available."
                ),
                confidence=confidence,
                risk=risk,
                risk_upper_bound=upper,
                risk_target=risk_target,
                guarantee_status="exchangeable_calibration_proxy",
                citations=citations if support_available else [],
                reason_codes=[
                    "SUPPORTED_EVIDENCE" if support_available else "BEST_EFFORT_UNVERIFIED",
                    *(["CONFLICT_RESOLVED_BY_FRESHNESS"] if conflicts else []),
                ],
            ),
            conflicts,
        )
