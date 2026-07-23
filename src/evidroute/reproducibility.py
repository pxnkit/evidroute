from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from evidroute.config import EngineConfig, project_root


def _git(command: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *command],
            cwd=project_root(),
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return "unavailable"
    return result.stdout.strip() or "clean"


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(config: EngineConfig, seed: int = 17) -> dict[str, object]:
    packages = {}
    for name in ("evidroute", "fastapi", "pydantic", "numpy", "scikit-learn", "scipy"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not-installed"
    data_dir = project_root() / "data" / "mini_route"
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "git_commit": _git(["rev-parse", "HEAD"]),
        "git_status": _git(["status", "--short"]),
        "python": sys.version,
        "platform": platform.platform(),
        "packages": packages,
        "seed": seed,
        "config": config.model_dump(mode="json"),
        "config_hash": config.digest(),
        "dataset_hashes": {
            path.name: file_hash(path) for path in sorted(data_dir.glob("*")) if path.is_file()
        },
        "source_versions": {
            "t0": "mini-route-t0-v1",
            "t1": "mini-route-t1-v1",
            "bm25": "bm25-mini-v1",
            "dense": "dense-hash-v1",
            "structured_t0": "schema-1.0",
            "structured_t1": "schema-2.0",
        },
    }


def write_manifest(path: Path, config: EngineConfig, seed: int = 17) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_manifest(config, seed), indent=2), encoding="utf-8")
