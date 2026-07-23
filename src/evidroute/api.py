from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from typing import Annotated, Any
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

from evidroute.config import EngineConfig, project_root
from evidroute.engine import EvidRouteEngine
from evidroute.models import (
    FeedbackRequest,
    QueryRequest,
    RecalibrationRequest,
)
from evidroute.risk import SelectiveRiskController
from evidroute.routes.base import AcquisitionState
from evidroute.security import safe_local_path

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
RATE_LIMIT_REQUESTS = 60
RATE_LIMIT_WINDOW_SECONDS = 60

config = EngineConfig()
engine = EvidRouteEngine(config=config)
active_snapshot = {"snapshot_id": config.default_snapshot}
request_windows: dict[str, deque[float]] = defaultdict(deque)

app = FastAPI(
    title="EvidRoute API",
    version="0.1.0",
    description="Risk-constrained sequential evidence routing in reproducible offline mode.",
)
origins = os.getenv("EVIDROUTE_CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in origins if origin.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Request-ID"],
)


@app.middleware("http")
async def safety_headers_and_rate_limit(request: Request, call_next):  # type: ignore[no-untyped-def]
    request_id = request.headers.get("X-Request-ID", uuid4().hex)
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = request_windows[client]
    while window and window[0] < now - RATE_LIMIT_WINDOW_SECONDS:
        window.popleft()
    if len(window) >= RATE_LIMIT_REQUESTS:
        return JSONResponse(
            status_code=429,
            content={"detail": "rate limit exceeded", "request_id": request_id},
        )
    window.append(now)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "mode": "offline", "version": "0.1.0"}


@app.get("/v1/routes")
def routes() -> list[dict[str, object]]:
    state = AcquisitionState(
        query="route inventory",
        snapshot_id=active_snapshot["snapshot_id"],
    )
    return [
        {
            "name": adapter.name.value,
            "version": adapter.version,
            "capabilities": list(adapter.capabilities),
            "available": adapter.availability(state),
            "estimate": adapter.estimate(state).model_dump(mode="json"),
        }
        for adapter in engine.registry.all()
    ]


@app.get("/v1/source-health")
def source_health(
    snapshot_id: Annotated[str, Query(pattern=r"^t[01]$")] = "t1",
) -> list[dict[str, object]]:
    return engine.source_health(snapshot_id)


async def _event_stream(payload: dict[str, Any]) -> AsyncIterator[str]:
    for event in payload["events"]:
        yield f"event: {event['event_type']}\ndata: {json.dumps(event)}\n\n"
        await asyncio.sleep(0)
    final = {
        "trace_id": payload["trace_id"],
        "decision": payload["decision"],
        "evidence": payload["evidence"],
        "conflicts": payload["conflicts"],
        "candidates": payload["candidates"],
        "budget_remaining": payload["budget_remaining"],
    }
    yield f"event: complete\ndata: {json.dumps(final)}\n\n"


@app.post("/v1/query")
def query(request: QueryRequest, stream: bool = False) -> Response:
    if request.snapshot_id not in {"t0", "t1"}:
        raise HTTPException(status_code=422, detail="snapshot_id must be t0 or t1")
    response = engine.query(request)
    payload = response.model_dump(mode="json")
    if stream:
        return StreamingResponse(_event_stream(payload), media_type="text/event-stream")
    return JSONResponse(payload)


@app.post("/v1/route-preview")
def route_preview(request: QueryRequest) -> dict[str, object]:
    metadata = engine._case_metadata(request.query)
    state = AcquisitionState(
        query=request.query,
        snapshot_id=request.snapshot_id,
        memory_namespace=request.memory_namespace,
        budget=request.budget,
        metadata=metadata,
    )
    candidates = engine.policy.candidates(state, request.risk_target, request.budget)
    return {
        "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
        "feature_schema_version": "decision-features-v1",
        "probes_are_costed": True,
    }


@app.post("/v1/feedback", status_code=204)
def feedback(request: FeedbackRequest) -> Response:
    if engine.get_trace(request.trace_id) is None:
        raise HTTPException(status_code=404, detail="trace not found")
    engine.trace_store.add_feedback(
        request.trace_id, request.correct, request.supported, request.comment
    )
    return Response(status_code=204)


@app.get("/v1/traces/{trace_id}")
def trace(trace_id: str) -> dict[str, object]:
    stored = engine.get_trace(trace_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="trace not found")
    return stored.model_dump(mode="json")


@app.get("/v1/traces/{trace_id}/export")
def trace_export(trace_id: str) -> Response:
    stored = engine.get_trace(trace_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="trace not found")
    return Response(
        content=stored.canonical_json(),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="evidroute-{trace_id}.json"'},
    )


@app.post("/v1/corpora")
async def upload_corpus(file: Annotated[UploadFile, File()]) -> dict[str, object]:
    if file.content_type not in {"application/json", "application/x-ndjson", "text/plain"}:
        raise HTTPException(status_code=415, detail="only JSON, JSONL, and text are accepted")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="corpus exceeds 5 MiB offline demo limit")
    try:
        content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise HTTPException(status_code=422, detail="corpus must be UTF-8") from error
    digest = hashlib.sha256(content).hexdigest()
    corpus_root = project_root() / "artifacts" / "corpora"
    corpus_root.mkdir(parents=True, exist_ok=True)
    destination = safe_local_path(corpus_root, f"{digest}.upload")
    destination.write_bytes(content)
    return {
        "corpus_id": digest,
        "bytes": len(content),
        "privacy": "local_only",
        "indexed": False,
        "next_action": "run the explicit index build command after reviewing the content",
    }


@app.post("/v1/snapshots/activate")
def activate_snapshot(snapshot_id: Annotated[str, Query(pattern=r"^t[01]$")]) -> dict[str, str]:
    active_snapshot["snapshot_id"] = snapshot_id
    return {"snapshot_id": snapshot_id, "status": "active"}


@app.post("/v1/recalibrate")
def recalibrate(request: RecalibrationRequest) -> dict[str, object]:
    if len(request.scores) != len(request.labeled_losses):
        raise HTTPException(status_code=422, detail="scores and labeled_losses must align")
    calibration = SelectiveRiskController(config.confidence_level).fit(
        request.scores,
        request.labeled_losses,
        request.risk_target,
        request.snapshot_id,
    )
    return dict(calibration.as_dict())


@app.get("/v1/models")
def models() -> list[dict[str, object]]:
    return [
        {
            "id": "rule-voi-v1",
            "type": "transparent sequential policy",
            "default": True,
            "offline": True,
        },
        {
            "id": "potential-outcome-hgb-v1",
            "type": "CPU multi-route utility model",
            "default": False,
            "offline": True,
        },
    ]


@app.get("/v1/config")
def get_config() -> dict[str, object]:
    return {
        "engine": config.model_dump(mode="json"),
        "config_hash": config.digest(),
        "active_snapshot": active_snapshot["snapshot_id"],
        "privacy": {
            "live_web_enabled": False,
            "private_memory_external_allowed": False,
            "trace_store": "local_sqlite",
        },
    }
