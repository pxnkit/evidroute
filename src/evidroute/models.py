from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RouteName(StrEnum):
    PARAMETRIC = "PARAMETRIC"
    EPISODIC_MEMORY = "EPISODIC_MEMORY"
    BM25 = "BM25"
    DENSE = "DENSE"
    STRUCTURED = "STRUCTURED"
    FROZEN_WEB = "FROZEN_WEB"
    LIVE_WEB = "LIVE_WEB"


class TerminalAction(StrEnum):
    ANSWER = "ANSWER"
    ASK_USER = "ASK_USER"
    ABSTAIN = "ABSTAIN"


class VerificationMode(StrEnum):
    VERIFIED = "verified"
    BEST_EFFORT = "best_effort"


class PrivacyClass(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    LOCAL_ONLY = "local_only"


class RouteErrorCode(StrEnum):
    UNAVAILABLE = "UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    PRIVACY_DENIED = "PRIVACY_DENIED"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    INDEX_VERSION_MISMATCH = "INDEX_VERSION_MISMATCH"
    NO_RESULTS = "NO_RESULTS"
    POLICY_DENIED = "POLICY_DENIED"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Budget(StrictModel):
    monetary: float = Field(default=1.0, ge=0.0)
    latency_ms: int = Field(default=3000, ge=0, le=120_000)
    token_limit: int = Field(default=4096, ge=0)
    route_calls: int = Field(default=3, ge=0, le=12)
    clarification_turns: int = Field(default=1, ge=0, le=4)

    def can_afford(self, estimate: RouteEstimate) -> bool:
        return (
            estimate.monetary_cost <= self.monetary
            and estimate.latency_ms <= self.latency_ms
            and estimate.tokens <= self.token_limit
            and self.route_calls > 0
        )

    def spend(self, estimate: RouteEstimate) -> Budget:
        return Budget(
            monetary=max(0.0, self.monetary - estimate.monetary_cost),
            latency_ms=max(0, self.latency_ms - estimate.latency_ms),
            token_limit=max(0, self.token_limit - estimate.tokens),
            route_calls=max(0, self.route_calls - 1),
            clarification_turns=self.clarification_turns,
        )


class RouteEstimate(StrictModel):
    monetary_cost: float = Field(ge=0.0)
    tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    privacy_class: PrivacyClass
    failure_probability: float = Field(ge=0.0, le=1.0)


class ProbeResult(StrictModel):
    route: RouteName
    features: dict[str, float | int | str | bool]
    cost: RouteEstimate


class EvidenceItem(StrictModel):
    evidence_id: str
    route: RouteName
    route_version: str
    snapshot_id: str
    source_uri: str
    title: str
    text: str
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    retrieval_score: float
    score_type: str
    observed_at: datetime
    source_updated_at: datetime | None = None
    freshness: str = "unknown"
    privacy: PrivacyClass = PrivacyClass.PUBLIC
    integrity_hash: str
    relation_path: list[str] = Field(default_factory=list)
    parent_id: str | None = None
    unsafe_content: bool = False
    injection_flags: list[str] = Field(default_factory=list)
    acquisition_latency_ms: int = Field(ge=0)
    monetary_cost: float = Field(ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("integrity_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError("integrity_hash must be a lowercase SHA-256 digest")
        return value

    @classmethod
    def from_text(
        cls,
        *,
        evidence_id: str,
        route: RouteName,
        snapshot_id: str,
        source_uri: str,
        title: str,
        text: str,
        retrieval_score: float,
        score_type: str,
        latency_ms: int,
        monetary_cost: float,
        privacy: PrivacyClass = PrivacyClass.PUBLIC,
        source_updated_at: datetime | None = None,
        relation_path: list[str] | None = None,
        unsafe_content: bool = False,
        injection_flags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvidenceItem:
        return cls(
            evidence_id=evidence_id,
            route=route,
            route_version="1.0",
            snapshot_id=snapshot_id,
            source_uri=source_uri,
            title=title,
            text=text,
            char_start=0,
            char_end=len(text),
            retrieval_score=retrieval_score,
            score_type=score_type,
            observed_at=datetime.now(UTC),
            source_updated_at=source_updated_at,
            freshness="current" if snapshot_id == "t1" else "historical",
            privacy=privacy,
            integrity_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            relation_path=relation_path or [],
            unsafe_content=unsafe_content,
            injection_flags=injection_flags or [],
            acquisition_latency_ms=latency_ms,
            monetary_cost=monetary_cost,
            metadata=metadata or {},
        )


class EvidenceBundle(StrictModel):
    route: RouteName
    items: list[EvidenceItem] = Field(default_factory=list)
    estimate: RouteEstimate
    actual_latency_ms: int = Field(ge=0)
    actual_monetary_cost: float = Field(ge=0.0)
    error_code: RouteErrorCode | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RouteHealth(StrictModel):
    route: RouteName
    snapshot_id: str
    availability: float = Field(ge=0.0, le=1.0)
    error_rate: float = Field(ge=0.0, le=1.0)
    latency_p50_ms: int = Field(ge=0)
    support_rate: float = Field(ge=0.0, le=1.0)
    index_version: str
    status: str


class RouteCandidate(StrictModel):
    route: RouteName
    feasible: bool
    predicted_correct: float = Field(ge=0.0, le=1.0)
    predicted_supported: float = Field(ge=0.0, le=1.0)
    predicted_action_success: float = Field(ge=0.0, le=1.0)
    predicted_contradiction: float = Field(ge=0.0, le=1.0)
    predicted_risk: float = Field(ge=0.0, le=1.0)
    risk_upper_bound: float = Field(ge=0.0, le=1.0)
    expected_cost: float = Field(ge=0.0)
    expected_latency_ms: int = Field(ge=0)
    expected_information_gain: float
    utility: float
    source_health: float = Field(ge=0.0, le=1.0)
    selected: bool = False
    reason_codes: list[str] = Field(default_factory=list)


class QueryRequest(StrictModel):
    query: str = Field(min_length=1, max_length=4000)
    mode: VerificationMode = VerificationMode.VERIFIED
    risk_target: float = Field(default=0.25, gt=0.0, lt=1.0)
    budget: Budget = Field(default_factory=Budget)
    snapshot_id: str = "t1"
    policy: str = "evidroute"
    memory_namespace: str = "demo"
    user_reply: str | None = None

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must not be blank")
        return stripped


class FinalDecision(StrictModel):
    action: TerminalAction
    answer: str | None = None
    clarification_question: str | None = None
    explanation: str
    confidence: float = Field(ge=0.0, le=1.0)
    risk: float = Field(ge=0.0, le=1.0)
    risk_upper_bound: float = Field(ge=0.0, le=1.0)
    risk_target: float = Field(gt=0.0, lt=1.0)
    guarantee_status: str
    citations: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)


class TraceEvent(StrictModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_type: str
    route: RouteName | None = None
    message: str
    measurements: dict[str, Any] = Field(default_factory=dict)


class QueryTrace(StrictModel):
    trace_id: str = Field(default_factory=lambda: uuid4().hex)
    request_id: str = Field(default_factory=lambda: uuid4().hex)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    query: str
    mode: VerificationMode
    snapshot_id: str
    policy: str
    candidates: list[RouteCandidate]
    events: list[TraceEvent]
    evidence: list[EvidenceItem]
    conflicts: list[dict[str, Any]]
    budget_initial: Budget
    budget_final: Budget
    final_decision: FinalDecision
    config_hash: str
    source_versions: dict[str, str]
    model_versions: dict[str, str]
    timing_ms: dict[str, int]

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, indent=2)


class QueryResponse(StrictModel):
    trace_id: str
    decision: FinalDecision
    candidates: list[RouteCandidate]
    evidence: list[EvidenceItem]
    conflicts: list[dict[str, Any]]
    events: list[TraceEvent]
    budget_remaining: Budget


class CounterfactualOutcome(StrictModel):
    case_id: str
    split: str
    route: RouteName
    feasible: bool
    answer: str | None
    exact_match: float
    token_f1: float
    correct: bool
    evidence_recall: float
    citation_precision: float
    citation_recall: float
    citation_completeness: float
    supported: bool
    contradiction: bool
    policy_compliant: bool
    action_success: bool
    monetary_cost: float
    latency_ms: int
    route_calls: int
    error_code: RouteErrorCode | None
    utility: float
    source_version: str
    seed: int
    config_hash: str


class MiniRouteCase(StrictModel):
    case_id: str
    split: str
    task_family: str
    question: str
    gold_answer: str | None
    gold_action: TerminalAction
    gold_support_ids: list[str] = Field(default_factory=list)
    expected_routes: list[RouteName] = Field(default_factory=list)
    snapshot_id: str = "t1"
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeedbackRequest(StrictModel):
    trace_id: str
    correct: bool | None = None
    supported: bool | None = None
    comment: str = Field(default="", max_length=2000)


class RecalibrationRequest(StrictModel):
    labeled_losses: list[int] = Field(min_length=5, max_length=10_000)
    scores: list[float] = Field(min_length=5, max_length=10_000)
    risk_target: float = Field(gt=0.0, lt=1.0)
    snapshot_id: str

    @field_validator("labeled_losses")
    @classmethod
    def validate_binary(cls, values: list[int]) -> list[int]:
        if any(value not in (0, 1) for value in values):
            raise ValueError("labeled_losses must be binary")
        return values
