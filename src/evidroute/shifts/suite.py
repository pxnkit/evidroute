from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from evidroute.risk import DriftReport, detect_source_shift


class CorruptionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_id: str
    seed: int
    source_version: str
    transformation: str
    severity: float = Field(ge=0.0, le=1.0)
    affected_ids: list[str]
    expected_invariants: list[str]


class ShiftSuite:
    @staticmethod
    def built_in() -> list[CorruptionManifest]:
        specifications = [
            ("omit-relevant-dense", "t1", "document_omission", 0.5, ["doc_dense"]),
            ("stale-elbe-workshop", "t1", "staleness", 0.7, ["elbe_workshop_t1"]),
            ("kepler-conflict", "t1", "contradiction_injection", 0.6, ["doc_contradict_b"]),
            ("dense-noise", "t1", "retriever_degradation", 0.45, ["dense-hash-v1"]),
            ("frozen-outage", "t1", "source_outage", 1.0, ["FROZEN_WEB"]),
            ("web-latency", "t1", "latency_spike", 0.8, ["FROZEN_WEB"]),
            ("memory-aging", "t1", "memory_aging", 0.75, ["mem_stale_city"]),
            ("schema-v2", "t1", "structured_schema_drift", 0.5, ["Nyx"]),
            ("duplicate-solstice", "t1", "duplicate_amplification", 0.6, ["solstice-copy"]),
            ("redwood-injection", "t1", "prompt_injection", 1.0, ["doc_injection"]),
        ]
        return [
            CorruptionManifest(
                manifest_id=manifest_id,
                seed=17,
                source_version=source_version,
                transformation=transformation,
                severity=severity,
                affected_ids=affected_ids,
                expected_invariants=[
                    "gold answers remain unchanged",
                    "unaffected sources retain integrity hashes",
                    "the original corpus remains immutable",
                ],
            )
            for manifest_id, source_version, transformation, severity, affected_ids in specifications
        ]

    @staticmethod
    def evaluate() -> DriftReport:
        reference_scores = [0.88, 0.83, 0.91, 0.79, 0.86, 0.9, 0.82, 0.87]
        shifted_scores = [0.42, 0.35, 0.51, 0.31, 0.48, 0.39, 0.44, 0.36]
        return detect_source_shift(
            reference_scores,
            shifted_scores,
            reference_error_rate=0.05,
            observed_error_rate=0.38,
            threshold=0.2,
        )

    @classmethod
    def write(cls, output_dir: Path) -> dict[str, object]:
        output_dir.mkdir(parents=True, exist_ok=True)
        manifests = cls.built_in()
        payload = [manifest.model_dump(mode="json") for manifest in manifests]
        manifest_path = output_dir / "corruption_manifests.json"
        manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        report = cls.evaluate()
        report_path = output_dir / "drift_report.json"
        report_path.write_text(json.dumps(report.as_dict(), indent=2), encoding="utf-8")
        return {
            "manifest_count": len(manifests),
            "drift": report.as_dict(),
            "manifest_hash": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        }
