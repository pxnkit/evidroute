from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class UtilityWeights(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    supported_quality: float = 1.0
    action_success: float = 0.35
    cost: float = 0.15
    latency: float = 0.08
    clarification: float = 0.18
    contradiction: float = 0.45


class EngineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["offline"] = "offline"
    default_snapshot: str = "t1"
    max_query_chars: int = Field(default=4000, ge=1, le=20_000)
    evidence_limit: int = Field(default=4, ge=1, le=12)
    max_route_calls: int = Field(default=3, ge=1, le=8)
    default_risk_target: float = Field(default=0.25, gt=0.0, lt=1.0)
    confidence_level: float = Field(default=0.95, gt=0.5, lt=1.0)
    minimum_stratum_size: int = Field(default=20, ge=5)
    drift_threshold: float = Field(default=0.2, gt=0.0)
    utility: UtilityWeights = Field(default_factory=UtilityWeights)

    def digest(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @classmethod
    def from_json(cls, path: Path) -> EngineConfig:
        return cls.model_validate_json(path.read_text(encoding="utf-8"))


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def data_root() -> Path:
    return project_root() / "data" / "mini_route"
