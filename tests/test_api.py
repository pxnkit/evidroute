from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_and_security_headers(api_client: TestClient) -> None:
    response = api_client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["mode"] == "offline"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_route_inventory_and_source_health(api_client: TestClient) -> None:
    routes = api_client.get("/v1/routes")
    health = api_client.get("/v1/source-health?snapshot_id=t1")

    assert routes.status_code == 200
    assert len(routes.json()) == 7
    assert {row["name"] for row in routes.json()} == {
        "PARAMETRIC",
        "EPISODIC_MEMORY",
        "BM25",
        "DENSE",
        "STRUCTURED",
        "FROZEN_WEB",
        "LIVE_WEB",
    }
    assert len(health.json()) == 7


def test_query_trace_export_and_feedback_round_trip(api_client: TestClient) -> None:
    response = api_client.post(
        "/v1/query",
        json={
            "query": "According to the latest snapshot, where will Aurora launch?",
            "risk_target": 0.3,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    trace_id = payload["trace_id"]
    assert payload["decision"]["answer"] == "Zurich"

    trace = api_client.get(f"/v1/traces/{trace_id}")
    exported = api_client.get(f"/v1/traces/{trace_id}/export")
    feedback = api_client.post(
        "/v1/feedback",
        json={"trace_id": trace_id, "correct": True, "supported": True, "comment": "reviewed"},
    )

    assert trace.status_code == 200
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/json")
    assert feedback.status_code == 204


def test_query_supports_server_sent_event_stream(api_client: TestClient) -> None:
    response = api_client.post(
        "/v1/query?stream=true",
        json={
            "query": "What is the exact verification token for the Heliotrope gate?",
            "risk_target": 0.4,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: complete" in response.text
    assert "VIOLET-731" in response.text


def test_upload_is_local_only_and_content_type_restricted(api_client: TestClient) -> None:
    accepted = api_client.post(
        "/v1/corpora",
        files={"file": ("sample.jsonl", b'{"text":"safe"}\n', "application/x-ndjson")},
    )
    rejected = api_client.post(
        "/v1/corpora",
        files={"file": ("sample.exe", b"MZ", "application/octet-stream")},
    )

    assert accepted.status_code == 200
    assert accepted.json()["privacy"] == "local_only"
    assert accepted.json()["indexed"] is False
    assert rejected.status_code == 415


def test_recalibration_and_snapshot_activation(api_client: TestClient) -> None:
    calibration = api_client.post(
        "/v1/recalibrate",
        json={
            "scores": [0.99] * 30 + [0.1] * 5,
            "labeled_losses": [0] * 30 + [1] * 5,
            "risk_target": 0.2,
            "snapshot_id": "t1",
        },
    )
    activated = api_client.post("/v1/snapshots/activate?snapshot_id=t0")
    config = api_client.get("/v1/config")

    assert calibration.status_code == 200
    assert calibration.json()["upper_bound"] <= 0.2
    assert activated.json()["snapshot_id"] == "t0"
    assert config.json()["active_snapshot"] == "t0"


def test_api_rejects_invalid_snapshot_and_missing_trace(api_client: TestClient) -> None:
    invalid = api_client.post(
        "/v1/query",
        json={"query": "test", "snapshot_id": "future"},
    )
    missing = api_client.get("/v1/traces/not-found")

    assert invalid.status_code == 422
    assert missing.status_code == 404
