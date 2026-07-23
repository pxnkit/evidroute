from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from evidroute.config import data_root
from evidroute.models import MiniRouteCase, PrivacyClass


class CorpusDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    title: str
    text: str
    answer: str | None = None
    keywords: list[str] = Field(default_factory=list)
    route_tags: list[str] = Field(default_factory=list)
    snapshot_ids: list[str] = Field(default_factory=lambda: ["t0", "t1"])
    source_uri: str
    updated_at: datetime
    reliability: float = Field(default=0.9, ge=0.0, le=1.0)
    privacy: PrivacyClass = PrivacyClass.PUBLIC
    duplicate_group: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: str
    namespace: str
    owner: str
    text: str
    answer: str
    keywords: list[str]
    created_at: datetime
    last_confirmed_at: datetime
    confidence: float = Field(ge=0.0, le=1.0)
    deleted: bool = False
    stale_after_days: int = Field(default=180, ge=1)
    privacy: PrivacyClass = PrivacyClass.PRIVATE


class StructuredEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edge_id: str
    subject: str
    relation: str
    object: str
    snapshot_ids: list[str] = Field(default_factory=lambda: ["t0", "t1"])
    answer: str | None = None
    source_document_id: str
    schema_version: str = "1.0"


class CorpusStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or data_root()
        self.documents = self._load_jsonl("documents.jsonl", CorpusDocument)
        self.cases = self._load_jsonl("cases.jsonl", MiniRouteCase)
        self.memories = self._load_jsonl("memories.jsonl", MemoryRecord)
        structured_payload = json.loads((self.root / "structured.json").read_text(encoding="utf-8"))
        self.structured_edges = [
            StructuredEdge.model_validate(item) for item in structured_payload["edges"]
        ]
        self.schema_versions: dict[str, str] = structured_payload["schema_versions"]

    def _load_jsonl(self, name: str, model: type[BaseModel]) -> list[Any]:
        rows: list[Any] = []
        for raw_line in (self.root / name).read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line:
                rows.append(model.model_validate_json(line))
        return rows

    def docs_for(self, snapshot_id: str, route_tag: str | None = None) -> list[CorpusDocument]:
        return [
            document
            for document in self.documents
            if snapshot_id in document.snapshot_ids
            and (route_tag is None or route_tag in document.route_tags)
        ]

    def cases_for(self, split: str | None = None) -> list[MiniRouteCase]:
        if split is None:
            return list(self.cases)
        return [case for case in self.cases if case.split == split]

    def edges_for(self, snapshot_id: str) -> list[StructuredEdge]:
        return [edge for edge in self.structured_edges if snapshot_id in edge.snapshot_ids]

    def documents_by_id(self) -> dict[str, CorpusDocument]:
        return {document.document_id: document for document in self.documents}

    def iter_public_assets(self) -> Iterable[Path]:
        yield from self.root.glob("*")
