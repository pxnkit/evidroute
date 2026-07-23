from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict, deque
from collections.abc import Iterable
from datetime import UTC, datetime

import numpy as np

from evidroute.datasets.corpus import CorpusDocument, CorpusStore, MemoryRecord
from evidroute.models import (
    Budget,
    EvidenceBundle,
    EvidenceItem,
    PrivacyClass,
    ProbeResult,
    RouteErrorCode,
    RouteEstimate,
    RouteHealth,
    RouteName,
)
from evidroute.routes.base import AcquisitionState, RouteAdapter
from evidroute.security import detect_prompt_injection, redact_pii

TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)?", re.IGNORECASE)
SYNONYMS = {
    "green": "emerald",
    "safe": "nominal",
    "work": "operations",
    "ongoing": "continue",
    "place": "location",
    "where": "location",
    "leader": "director",
    "leads": "director",
    "head": "director",
    "code": "identifier",
    "id": "identifier",
}


def tokenize(text: str, *, semantic: bool = False) -> list[str]:
    tokens = [token.lower() for token in TOKEN_PATTERN.findall(text)]
    if semantic:
        return [SYNONYMS.get(token, token) for token in tokens]
    return tokens


def _empty_bundle(
    route: RouteName,
    estimate: RouteEstimate,
    code: RouteErrorCode,
    message: str,
) -> EvidenceBundle:
    return EvidenceBundle(
        route=route,
        estimate=estimate,
        actual_latency_ms=estimate.latency_ms,
        actual_monetary_cost=estimate.monetary_cost,
        error_code=code,
        error_message=message,
    )


def _health(
    route: RouteName,
    snapshot_id: str,
    *,
    availability: float = 1.0,
    error_rate: float = 0.0,
    latency: int,
    support_rate: float,
    status: str = "healthy",
    index_version: str = "mini-v1",
) -> RouteHealth:
    return RouteHealth(
        route=route,
        snapshot_id=snapshot_id,
        availability=availability,
        error_rate=error_rate,
        latency_p50_ms=latency,
        support_rate=support_rate,
        index_version=index_version,
        status=status,
    )


def _document_evidence(
    route: RouteName,
    document: CorpusDocument,
    snapshot_id: str,
    score: float,
    score_type: str,
    estimate: RouteEstimate,
) -> EvidenceItem:
    injection_flags = detect_prompt_injection(document.text)
    safe_text, pii_flags = redact_pii(document.text)
    flags = [*injection_flags, *[f"PII_{flag}" for flag in pii_flags]]
    return EvidenceItem.from_text(
        evidence_id=f"{route.value.lower()}:{document.document_id}",
        route=route,
        snapshot_id=snapshot_id,
        source_uri=document.source_uri,
        title=document.title,
        text=safe_text,
        retrieval_score=float(score),
        score_type=score_type,
        latency_ms=estimate.latency_ms,
        monetary_cost=estimate.monetary_cost,
        privacy=document.privacy,
        source_updated_at=document.updated_at,
        unsafe_content=bool(injection_flags),
        injection_flags=flags,
        metadata={
            "document_id": document.document_id,
            "answer": document.answer,
            "reliability": document.reliability,
            "duplicate_group": document.duplicate_group,
            **document.metadata,
        },
    )


class ParametricRoute(RouteAdapter):
    name = RouteName.PARAMETRIC

    def __init__(self) -> None:
        self._facts = {
            "what is two plus two": "4",
            "what is 2 plus 2": "4",
        }

    @property
    def capabilities(self) -> tuple[str, ...]:
        return ("direct_answer", "uncertainty")

    def availability(self, state: AcquisitionState) -> bool:
        return not state.metadata.get("all_routes_unavailable", False)

    def estimate(self, state: AcquisitionState) -> RouteEstimate:
        return RouteEstimate(
            monetary_cost=0.0,
            tokens=32,
            latency_ms=8,
            privacy_class=PrivacyClass.LOCAL_ONLY,
            failure_probability=0.01,
        )

    def probe(self, state: AcquisitionState) -> ProbeResult:
        normalized = " ".join(tokenize(state.query))
        confidence = 0.98 if normalized in self._facts else 0.12
        return ProbeResult(
            route=self.name,
            features={"known_pattern": normalized in self._facts, "confidence": confidence},
            cost=self.estimate(state),
        )

    def acquire(self, state: AcquisitionState, budget: Budget) -> EvidenceBundle:
        estimate = self.estimate(state)
        if not self.availability(state):
            return _empty_bundle(
                self.name, estimate, RouteErrorCode.UNAVAILABLE, "route unavailable"
            )
        if not budget.can_afford(estimate):
            return _empty_bundle(
                self.name, estimate, RouteErrorCode.BUDGET_EXCEEDED, "budget cannot fund route"
            )
        normalized = " ".join(tokenize(state.query))
        answer = self._facts.get(normalized)
        if answer is None:
            return _empty_bundle(
                self.name,
                estimate,
                RouteErrorCode.NO_RESULTS,
                "offline parametric model has no reliable answer",
            )
        proposal_text = f"Offline deterministic proposal: {answer}"
        item = EvidenceItem.from_text(
            evidence_id=f"parametric:{hashlib.sha256(normalized.encode()).hexdigest()[:12]}",
            route=self.name,
            snapshot_id=state.snapshot_id,
            source_uri="model://deterministic-mock-v1",
            title="Deterministic parametric proposal",
            text=proposal_text,
            retrieval_score=0.98,
            score_type="mock_confidence",
            latency_ms=estimate.latency_ms,
            monetary_cost=0.0,
            privacy=PrivacyClass.LOCAL_ONLY,
            metadata={"answer": answer, "support_available": False, "provider": "offline-mock"},
        )
        return EvidenceBundle(
            route=self.name,
            items=[item],
            estimate=estimate,
            actual_latency_ms=estimate.latency_ms,
            actual_monetary_cost=0.0,
            metadata={"support_available": False},
        )

    def health(self, snapshot_id: str) -> RouteHealth:
        return _health(self.name, snapshot_id, latency=8, support_rate=0.1)


class BM25Route(RouteAdapter):
    name = RouteName.BM25

    def __init__(self, store: CorpusStore) -> None:
        self.store = store

    @property
    def capabilities(self) -> tuple[str, ...]:
        return ("sparse_retrieval", "exact_match", "score_diagnostics")

    def availability(self, state: AcquisitionState) -> bool:
        return not state.metadata.get("all_routes_unavailable", False)

    def estimate(self, state: AcquisitionState) -> RouteEstimate:
        return RouteEstimate(
            monetary_cost=0.01,
            tokens=0,
            latency_ms=18,
            privacy_class=PrivacyClass.LOCAL_ONLY,
            failure_probability=0.01,
        )

    def _score(
        self, query: str, documents: list[CorpusDocument]
    ) -> list[tuple[CorpusDocument, float]]:
        query_tokens = tokenize(query)
        document_tokens = [
            tokenize(document.text + " " + " ".join(document.keywords)) for document in documents
        ]
        document_frequency: Counter[str] = Counter()
        for tokens in document_tokens:
            document_frequency.update(set(tokens))
        average_length = max(1.0, sum(map(len, document_tokens)) / max(1, len(document_tokens)))
        scores: list[tuple[CorpusDocument, float]] = []
        for document, tokens in zip(documents, document_tokens, strict=True):
            counts = Counter(tokens)
            score = 0.0
            for token in query_tokens:
                frequency = counts[token]
                if frequency == 0:
                    continue
                inverse_document_frequency = math.log(
                    1
                    + (len(documents) - document_frequency[token] + 0.5)
                    / (document_frequency[token] + 0.5)
                )
                denominator = frequency + 1.5 * (1 - 0.75 + 0.75 * len(tokens) / average_length)
                score += inverse_document_frequency * (frequency * 2.5) / denominator
            scores.append((document, score))
        return sorted(scores, key=lambda pair: (-pair[1], pair[0].document_id))

    def probe(self, state: AcquisitionState) -> ProbeResult:
        scored = self._score(state.query, self.store.docs_for(state.snapshot_id))
        positive = [score for _, score in scored if score > 0]
        margin = (
            positive[0] - positive[1] if len(positive) > 1 else (positive[0] if positive else 0.0)
        )
        return ProbeResult(
            route=self.name,
            features={
                "top_score": positive[0] if positive else 0.0,
                "margin": margin,
                "result_count": len(positive),
            },
            cost=RouteEstimate(
                monetary_cost=0.002,
                tokens=0,
                latency_ms=5,
                privacy_class=PrivacyClass.LOCAL_ONLY,
                failure_probability=0.0,
            ),
        )

    def acquire(self, state: AcquisitionState, budget: Budget) -> EvidenceBundle:
        estimate = self.estimate(state)
        if not self.availability(state):
            return _empty_bundle(
                self.name, estimate, RouteErrorCode.UNAVAILABLE, "BM25 unavailable"
            )
        if not budget.can_afford(estimate):
            return _empty_bundle(
                self.name, estimate, RouteErrorCode.BUDGET_EXCEEDED, "budget cannot fund BM25"
            )
        all_scored = self._score(state.query, self.store.docs_for(state.snapshot_id))
        top_score = all_scored[0][1] if all_scored else 0.0
        threshold = max(0.2, top_score * 0.18)
        scored = [pair for pair in all_scored if pair[1] >= threshold][:4]
        if not scored:
            return _empty_bundle(
                self.name, estimate, RouteErrorCode.NO_RESULTS, "BM25 returned no evidence"
            )
        return EvidenceBundle(
            route=self.name,
            items=[
                _document_evidence(self.name, document, state.snapshot_id, score, "bm25", estimate)
                for document, score in scored
            ],
            estimate=estimate,
            actual_latency_ms=estimate.latency_ms,
            actual_monetary_cost=estimate.monetary_cost,
            metadata={"index_version": "bm25-mini-v1"},
        )

    def health(self, snapshot_id: str) -> RouteHealth:
        return _health(
            self.name, snapshot_id, latency=18, support_rate=0.79, index_version="bm25-mini-v1"
        )


class DenseRoute(RouteAdapter):
    name = RouteName.DENSE
    dimensions = 96

    def __init__(self, store: CorpusStore) -> None:
        self.store = store

    @property
    def capabilities(self) -> tuple[str, ...]:
        return ("semantic_retrieval", "cosine_similarity", "neighborhood_diagnostics")

    def availability(self, state: AcquisitionState) -> bool:
        return not state.metadata.get("all_routes_unavailable", False)

    def estimate(self, state: AcquisitionState) -> RouteEstimate:
        return RouteEstimate(
            monetary_cost=0.035,
            tokens=0,
            latency_ms=35,
            privacy_class=PrivacyClass.LOCAL_ONLY,
            failure_probability=0.02,
        )

    def _embed(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dimensions, dtype=np.float64)
        semantic_tokens = tokenize(text, semantic=True)
        features = semantic_tokens + [
            f"{left}_{right}"
            for left, right in zip(semantic_tokens, semantic_tokens[1:], strict=False)
        ]
        for feature in features:
            digest = hashlib.sha256(feature.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = np.linalg.norm(vector)
        return vector / norm if norm else vector

    def _score(
        self, query: str, documents: Iterable[CorpusDocument]
    ) -> list[tuple[CorpusDocument, float]]:
        query_vector = self._embed(query)
        rows = [
            (
                document,
                float(
                    np.dot(
                        query_vector, self._embed(document.text + " " + " ".join(document.keywords))
                    )
                ),
            )
            for document in documents
        ]
        return sorted(rows, key=lambda pair: (-pair[1], pair[0].document_id))

    def probe(self, state: AcquisitionState) -> ProbeResult:
        scored = self._score(state.query, self.store.docs_for(state.snapshot_id))
        positive = [score for _, score in scored if score > 0]
        margin = (
            positive[0] - positive[1] if len(positive) > 1 else (positive[0] if positive else 0.0)
        )
        entropy = 0.0
        if positive:
            values = np.exp(np.asarray(positive[:5]) - max(positive[:5]))
            probabilities = values / values.sum()
            entropy = float(-np.sum(probabilities * np.log(probabilities + 1e-12)))
        return ProbeResult(
            route=self.name,
            features={
                "top_score": positive[0] if positive else 0.0,
                "margin": margin,
                "entropy": entropy,
                "result_count": len(positive),
            },
            cost=RouteEstimate(
                monetary_cost=0.004,
                tokens=0,
                latency_ms=9,
                privacy_class=PrivacyClass.LOCAL_ONLY,
                failure_probability=0.0,
            ),
        )

    def acquire(self, state: AcquisitionState, budget: Budget) -> EvidenceBundle:
        estimate = self.estimate(state)
        if not self.availability(state):
            return _empty_bundle(
                self.name, estimate, RouteErrorCode.UNAVAILABLE, "dense route unavailable"
            )
        if not budget.can_afford(estimate):
            return _empty_bundle(
                self.name,
                estimate,
                RouteErrorCode.BUDGET_EXCEEDED,
                "budget cannot fund dense route",
            )
        scored = [
            pair
            for pair in self._score(state.query, self.store.docs_for(state.snapshot_id))
            if pair[1] > 0.08
        ][:4]
        if state.metadata.get("shift") == "dense_noise":
            scored = list(reversed(scored))
        if not scored:
            return _empty_bundle(
                self.name, estimate, RouteErrorCode.NO_RESULTS, "dense route returned no evidence"
            )
        return EvidenceBundle(
            route=self.name,
            items=[
                _document_evidence(
                    self.name,
                    document,
                    state.snapshot_id,
                    min(0.97, 0.72 + max(0.0, score) * 0.25),
                    "cosine",
                    estimate,
                )
                for document, score in scored
            ],
            estimate=estimate,
            actual_latency_ms=estimate.latency_ms,
            actual_monetary_cost=estimate.monetary_cost,
            metadata={"index_version": "dense-hash-v1", "dimensions": self.dimensions},
        )

    def health(self, snapshot_id: str) -> RouteHealth:
        return _health(
            self.name, snapshot_id, latency=35, support_rate=0.76, index_version="dense-hash-v1"
        )


class StructuredRoute(RouteAdapter):
    name = RouteName.STRUCTURED

    def __init__(self, store: CorpusStore) -> None:
        self.store = store

    @property
    def capabilities(self) -> tuple[str, ...]:
        return ("graph_traversal", "multi_hop", "schema_provenance")

    def availability(self, state: AcquisitionState) -> bool:
        return not state.metadata.get("all_routes_unavailable", False)

    def estimate(self, state: AcquisitionState) -> RouteEstimate:
        return RouteEstimate(
            monetary_cost=0.055,
            tokens=0,
            latency_ms=42,
            privacy_class=PrivacyClass.LOCAL_ONLY,
            failure_probability=0.015,
        )

    def _paths(self, query: str, snapshot_id: str) -> list[tuple[list[str], str, str]]:
        query_tokens = set(tokenize(query, semantic=True))
        edges = self.store.edges_for(snapshot_id)
        adjacency: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        entities: set[str] = set()
        for edge in edges:
            adjacency[edge.subject].append((edge.relation, edge.object, edge.source_document_id))
            entities.update((edge.subject, edge.object))
        starts = [
            entity
            for entity in entities
            if query_tokens.intersection(tokenize(entity, semantic=True))
        ]
        matches: list[tuple[list[str], str, str]] = []
        for start in starts:
            queue: deque[tuple[str, list[str], list[str]]] = deque([(start, [start], [])])
            seen = {start}
            while queue:
                node, path, sources = queue.popleft()
                if len(path) > 1:
                    overlap = query_tokens.intersection(tokenize(" ".join(path), semantic=True))
                    if overlap:
                        matches.append((path, node, sources[-1]))
                if len(path) >= 3:
                    continue
                for relation, target, source_id in adjacency.get(node, []):
                    if target not in seen:
                        seen.add(target)
                        queue.append((target, [*path, relation, target], [*sources, source_id]))
        return sorted(matches, key=lambda row: (-len(row[0]), row[1]))

    def probe(self, state: AcquisitionState) -> ProbeResult:
        paths = self._paths(state.query, state.snapshot_id)
        return ProbeResult(
            route=self.name,
            features={
                "entity_coverage": min(1.0, len(paths) / 2),
                "path_count": len(paths),
                "schema_version": self.store.schema_versions[state.snapshot_id],
            },
            cost=RouteEstimate(
                monetary_cost=0.003,
                tokens=0,
                latency_ms=6,
                privacy_class=PrivacyClass.LOCAL_ONLY,
                failure_probability=0.0,
            ),
        )

    def acquire(self, state: AcquisitionState, budget: Budget) -> EvidenceBundle:
        estimate = self.estimate(state)
        if not self.availability(state):
            return _empty_bundle(
                self.name, estimate, RouteErrorCode.UNAVAILABLE, "structured route unavailable"
            )
        if not budget.can_afford(estimate):
            return _empty_bundle(
                self.name,
                estimate,
                RouteErrorCode.BUDGET_EXCEEDED,
                "budget cannot fund graph route",
            )
        paths = self._paths(state.query, state.snapshot_id)
        if not paths:
            return _empty_bundle(
                self.name, estimate, RouteErrorCode.NO_RESULTS, "no matching structured path"
            )
        documents = self.store.documents_by_id()
        items: list[EvidenceItem] = []
        seen_documents: set[str] = set()
        fallback_source_id = paths[0][2]
        for path, answer, _source_id in paths:
            for candidate_source in [
                edge.source_document_id
                for edge in self.store.edges_for(state.snapshot_id)
                if edge.subject in path and edge.object in path
            ]:
                if candidate_source in seen_documents or candidate_source not in documents:
                    continue
                seen_documents.add(candidate_source)
                document = documents[candidate_source]
                item = _document_evidence(
                    self.name,
                    document,
                    state.snapshot_id,
                    min(1.0, 0.55 + 0.15 * len(path)),
                    "graph_path",
                    estimate,
                )
                item.relation_path = path
                item.metadata["answer"] = answer
                item.metadata["schema_version"] = self.store.schema_versions[state.snapshot_id]
                items.append(item)
            if len(items) >= 4:
                break
        if not items and fallback_source_id in documents:
            items.append(
                _document_evidence(
                    self.name,
                    documents[fallback_source_id],
                    state.snapshot_id,
                    0.8,
                    "graph_path",
                    estimate,
                )
            )
        return EvidenceBundle(
            route=self.name,
            items=items,
            estimate=estimate,
            actual_latency_ms=estimate.latency_ms,
            actual_monetary_cost=estimate.monetary_cost,
            metadata={
                "schema_version": self.store.schema_versions[state.snapshot_id],
                "executable_query": "bounded_bfs(max_hops=2)",
            },
        )

    def health(self, snapshot_id: str) -> RouteHealth:
        schema_version = self.store.schema_versions[snapshot_id]
        return _health(
            self.name,
            snapshot_id,
            latency=42,
            support_rate=0.83,
            index_version=f"structured-schema-{schema_version}",
        )


class MemoryRoute(RouteAdapter):
    name = RouteName.EPISODIC_MEMORY

    def __init__(self, store: CorpusStore) -> None:
        self.store = store

    @property
    def capabilities(self) -> tuple[str, ...]:
        return ("namespace_memory", "freshness", "deletion")

    def availability(self, state: AcquisitionState) -> bool:
        return not state.metadata.get("all_routes_unavailable", False)

    def estimate(self, state: AcquisitionState) -> RouteEstimate:
        return RouteEstimate(
            monetary_cost=0.005,
            tokens=0,
            latency_ms=12,
            privacy_class=PrivacyClass.PRIVATE,
            failure_probability=0.01,
        )

    @staticmethod
    def _age_days(memory: MemoryRecord) -> int:
        return max(0, (datetime.now(UTC) - memory.last_confirmed_at).days)

    def _matches(self, state: AcquisitionState) -> list[tuple[MemoryRecord, float]]:
        query_tokens = set(tokenize(state.query, semantic=True))
        rows = []
        for memory in self.store.memories:
            if memory.deleted or memory.namespace != state.memory_namespace:
                continue
            overlap = len(
                query_tokens.intersection(
                    tokenize(memory.text + " " + " ".join(memory.keywords), semantic=True)
                )
            )
            if overlap:
                freshness = max(
                    0.1, 1 - self._age_days(memory) / max(1, memory.stale_after_days * 2)
                )
                rows.append((memory, overlap * memory.confidence * freshness))
        return sorted(rows, key=lambda pair: (-pair[1], pair[0].memory_id))

    def probe(self, state: AcquisitionState) -> ProbeResult:
        matches = self._matches(state)
        return ProbeResult(
            route=self.name,
            features={
                "memory_present": bool(matches),
                "match_count": len(matches),
                "freshest_age_days": self._age_days(matches[0][0]) if matches else -1,
                "content_accessed": False,
            },
            cost=RouteEstimate(
                monetary_cost=0.0,
                tokens=0,
                latency_ms=2,
                privacy_class=PrivacyClass.PRIVATE,
                failure_probability=0.0,
            ),
        )

    def acquire(self, state: AcquisitionState, budget: Budget) -> EvidenceBundle:
        estimate = self.estimate(state)
        if state.metadata.get("privacy_denied"):
            return _empty_bundle(
                self.name,
                estimate,
                RouteErrorCode.PRIVACY_DENIED,
                "policy prevents private memory from being sent to an external route",
            )
        if not self.availability(state):
            return _empty_bundle(
                self.name, estimate, RouteErrorCode.UNAVAILABLE, "memory unavailable"
            )
        if not budget.can_afford(estimate):
            return _empty_bundle(
                self.name, estimate, RouteErrorCode.BUDGET_EXCEEDED, "budget cannot fund memory"
            )
        matches = self._matches(state)[:3]
        if not matches:
            return _empty_bundle(
                self.name, estimate, RouteErrorCode.NO_RESULTS, "no matching memory"
            )
        items: list[EvidenceItem] = []
        for memory, score in matches:
            age_days = self._age_days(memory)
            item = EvidenceItem.from_text(
                evidence_id=f"memory:{memory.memory_id}",
                route=self.name,
                snapshot_id=state.snapshot_id,
                source_uri=f"memory://{memory.namespace}/{memory.memory_id}",
                title=f"Episodic memory {memory.memory_id}",
                text=memory.text,
                retrieval_score=float(score),
                score_type="memory_overlap_freshness",
                latency_ms=estimate.latency_ms,
                monetary_cost=estimate.monetary_cost,
                privacy=memory.privacy,
                metadata={
                    "answer": memory.answer,
                    "owner": memory.owner,
                    "age_days": age_days,
                    "stale": age_days > memory.stale_after_days,
                    "last_confirmed_at": memory.last_confirmed_at.isoformat(),
                },
            )
            items.append(item)
        return EvidenceBundle(
            route=self.name,
            items=items,
            estimate=estimate,
            actual_latency_ms=estimate.latency_ms,
            actual_monetary_cost=estimate.monetary_cost,
            metadata={"namespace": state.memory_namespace},
        )

    def health(self, snapshot_id: str) -> RouteHealth:
        return _health(
            self.name, snapshot_id, latency=12, support_rate=0.72, index_version="memory-v1"
        )


class FrozenWebRoute(RouteAdapter):
    name = RouteName.FROZEN_WEB

    def __init__(self, store: CorpusStore) -> None:
        self.store = store
        self.bm25 = BM25Route(store)

    @property
    def capabilities(self) -> tuple[str, ...]:
        return ("frozen_snapshot", "temporal_retrieval", "provenance")

    def availability(self, state: AcquisitionState) -> bool:
        return not (
            state.metadata.get("all_routes_unavailable", False)
            or state.metadata.get("force_timeout") == self.name.value
        )

    def estimate(self, state: AcquisitionState) -> RouteEstimate:
        return RouteEstimate(
            monetary_cost=0.08,
            tokens=0,
            latency_ms=65,
            privacy_class=PrivacyClass.PUBLIC,
            failure_probability=0.03,
        )

    def _score(self, state: AcquisitionState) -> list[tuple[CorpusDocument, float]]:
        documents = self.store.docs_for(state.snapshot_id, "frozen_web")
        return self.bm25._score(state.query, documents)

    def probe(self, state: AcquisitionState) -> ProbeResult:
        scored = self._score(state)
        positive = [score for _, score in scored if score > 0]
        return ProbeResult(
            route=self.name,
            features={
                "top_score": positive[0] if positive else 0.0,
                "result_count": len(positive),
                "snapshot_id": state.snapshot_id,
                "freshness_available": True,
            },
            cost=RouteEstimate(
                monetary_cost=0.003,
                tokens=0,
                latency_ms=8,
                privacy_class=PrivacyClass.PUBLIC,
                failure_probability=0.0,
            ),
        )

    def acquire(self, state: AcquisitionState, budget: Budget) -> EvidenceBundle:
        estimate = self.estimate(state)
        if state.metadata.get("force_timeout") == self.name.value:
            return _empty_bundle(
                self.name, estimate, RouteErrorCode.TIMEOUT, "simulated frozen-web timeout"
            )
        if not self.availability(state):
            return _empty_bundle(
                self.name, estimate, RouteErrorCode.UNAVAILABLE, "frozen-web unavailable"
            )
        if not budget.can_afford(estimate):
            return _empty_bundle(
                self.name, estimate, RouteErrorCode.BUDGET_EXCEEDED, "budget cannot fund frozen web"
            )
        all_scored = self._score(state)
        top_score = all_scored[0][1] if all_scored else 0.0
        threshold = max(0.15, top_score * 0.18)
        scored = [pair for pair in all_scored if pair[1] >= threshold][:4]
        if not scored:
            return _empty_bundle(
                self.name, estimate, RouteErrorCode.NO_RESULTS, "frozen-web returned no evidence"
            )
        return EvidenceBundle(
            route=self.name,
            items=[
                _document_evidence(
                    self.name, document, state.snapshot_id, score, "snapshot_bm25", estimate
                )
                for document, score in scored
            ],
            estimate=estimate,
            actual_latency_ms=estimate.latency_ms,
            actual_monetary_cost=estimate.monetary_cost,
            metadata={"snapshot_id": state.snapshot_id, "snapshot_format": "normalized-jsonl"},
        )

    def health(self, snapshot_id: str) -> RouteHealth:
        return _health(
            self.name,
            snapshot_id,
            latency=65,
            support_rate=0.82 if snapshot_id == "t1" else 0.7,
            index_version=f"frozen-web-{snapshot_id}",
        )


class LiveWebRoute(RouteAdapter):
    name = RouteName.LIVE_WEB

    @property
    def capabilities(self) -> tuple[str, ...]:
        return ("optional_live_search", "ssrf_guarded")

    def availability(self, state: AcquisitionState) -> bool:
        return False

    def estimate(self, state: AcquisitionState) -> RouteEstimate:
        return RouteEstimate(
            monetary_cost=0.25,
            tokens=500,
            latency_ms=1200,
            privacy_class=PrivacyClass.PUBLIC,
            failure_probability=0.15,
        )

    def probe(self, state: AcquisitionState) -> ProbeResult:
        return ProbeResult(
            route=self.name,
            features={"enabled": False, "reason": "OFFLINE_REPRODUCIBLE_MODE"},
            cost=RouteEstimate(
                monetary_cost=0.0,
                tokens=0,
                latency_ms=0,
                privacy_class=PrivacyClass.PUBLIC,
                failure_probability=1.0,
            ),
        )

    def acquire(self, state: AcquisitionState, budget: Budget) -> EvidenceBundle:
        return _empty_bundle(
            self.name,
            self.estimate(state),
            RouteErrorCode.UNAVAILABLE,
            "live web is disabled in the reproducible offline configuration",
        )

    def health(self, snapshot_id: str) -> RouteHealth:
        return _health(
            self.name,
            snapshot_id,
            availability=0.0,
            error_rate=1.0,
            latency=1200,
            support_rate=0.0,
            status="disabled",
            index_version="live-web-disabled",
        )
