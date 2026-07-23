from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import evidroute.api as api_module
from evidroute.engine import EvidRouteEngine


@pytest.fixture
def engine(tmp_path: Path) -> EvidRouteEngine:
    return EvidRouteEngine(trace_db=tmp_path / "traces.sqlite3")


@pytest.fixture
def api_client(engine: EvidRouteEngine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(api_module, "engine", engine)
    api_module.request_windows.clear()
    api_module.active_snapshot["snapshot_id"] = "t1"
    with TestClient(api_module.app) as client:
        yield client
