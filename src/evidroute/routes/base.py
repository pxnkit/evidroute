from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import Field

from evidroute.models import (
    Budget,
    EvidenceBundle,
    ProbeResult,
    RouteEstimate,
    RouteHealth,
    RouteName,
    StrictModel,
)


class AcquisitionState(StrictModel):
    query: str
    snapshot_id: str
    memory_namespace: str = "demo"
    budget: Budget = Field(default_factory=Budget)
    acquired_routes: list[RouteName] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RouteAdapter(ABC):
    name: RouteName
    version = "1.0"

    @property
    @abstractmethod
    def capabilities(self) -> tuple[str, ...]:
        raise NotImplementedError

    @abstractmethod
    def availability(self, state: AcquisitionState) -> bool:
        raise NotImplementedError

    @abstractmethod
    def estimate(self, state: AcquisitionState) -> RouteEstimate:
        raise NotImplementedError

    @abstractmethod
    def probe(self, state: AcquisitionState) -> ProbeResult:
        raise NotImplementedError

    @abstractmethod
    def acquire(self, state: AcquisitionState, budget: Budget) -> EvidenceBundle:
        raise NotImplementedError

    @abstractmethod
    def health(self, snapshot_id: str) -> RouteHealth:
        raise NotImplementedError

    def close(self) -> None:
        return None
