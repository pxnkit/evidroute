from __future__ import annotations

import json
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from evidroute.security import safe_local_path


class JsonBenchmarkAdapter:
    name = "generic"

    def iter_examples(self, path: Path) -> Iterable[dict[str, Any]]:
        if not path.exists():
            raise FileNotFoundError(
                f"{self.name} data is not present. Run scripts/download_data.py and accept "
                "the dataset's license before preprocessing."
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload if isinstance(payload, list) else payload.get("data", [])
        for row in rows:
            yield self.normalize(row)

    def normalize(self, row: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class HotpotQAAdapter(JsonBenchmarkAdapter):
    name = "HotpotQA"

    def normalize(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row.get("_id") or row.get("id"),
            "question": row["question"],
            "answer": row["answer"],
            "supporting_facts": row.get("supporting_facts", []),
            "context": row.get("context", []),
        }


class MuSiQueAdapter(JsonBenchmarkAdapter):
    name = "MuSiQue"

    def normalize(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row.get("id"),
            "question": row["question"],
            "answer": row.get("answer"),
            "question_decomposition": row.get("question_decomposition", []),
            "paragraphs": row.get("paragraphs", []),
        }


class TwoWikiMultiHopQAAdapter(JsonBenchmarkAdapter):
    name = "2WikiMultiHopQA"

    def normalize(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row.get("_id") or row.get("id"),
            "question": row["question"],
            "answer": row.get("answer"),
            "evidences": row.get("evidences", []),
            "supporting_facts": row.get("supporting_facts", []),
        }


class TauKnowledgeLocalAdapter:
    """Metadata-only validation for a user-supplied private τ-Knowledge archive."""

    required_markers = {
        "README.md",
        "data/tau2/domains/knowledge/db.json",
    }
    required_prefixes = {"data/tau2/domains/knowledge/documents/"}

    def validate_archive(self, archive_path: Path) -> dict[str, Any]:
        if not archive_path.exists():
            raise FileNotFoundError(
                "τ-Knowledge is local-only. Set TAU_KNOWLEDGE_ARCHIVE to the supplied private ZIP."
            )
        if archive_path.suffix.lower() != ".zip":
            raise ValueError("τ-Knowledge input must be a ZIP archive")
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
        missing = sorted(self.required_markers - names)
        missing_prefixes = sorted(
            prefix
            for prefix in self.required_prefixes
            if not any(name.startswith(prefix) for name in names)
        )
        if missing or missing_prefixes:
            raise ValueError(
                "τ-Knowledge archive is missing required paths or prefixes: "
                f"{[*missing, *missing_prefixes]}"
            )
        return {
            "archive": str(archive_path),
            "member_count": len(names),
            "private": True,
            "redistributable": False,
            "validated_markers": sorted(self.required_markers),
            "validated_prefixes": sorted(self.required_prefixes),
        }

    def safe_extract_path(self, root: Path, member: str) -> Path:
        return safe_local_path(root, member)
