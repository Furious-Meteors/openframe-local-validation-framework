"""
Stage 8 — sidecar telemetry validation for research-pipeline.

research-pipeline wires three adapters in one request:
  MongoDB (persistence) → Kafka (event) → Redis (status cache)

Key assertions:
  - Spans from one request all share one trace_id (multi-adapter pooling)
  - Every span's resource carries service.name=research-pipeline
  - At least 3 spans: HTTP server + MongoDB + Redis (Kafka may add more)

Negative-case protection: test_collector_is_running() fails loudly if the
sidecar is not running — a missing collector never produces a vacuous pass.

Prerequisites
-------------
    docker compose -f .docker/docker-compose.yml up -d
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
import time
import uuid

import httpx
import pytest

PIPELINE_URL        = "http://localhost:8007"
COLLECTOR_CONTAINER = "openframe-research-pipeline-collector"
SPANS_FILE          = "/var/otel/spans.jsonl"
EXPECTED_SERVICE    = "research-pipeline"
POLL_TIMEOUT_S      = 30
POLL_INTERVAL_S     = 0.5


# ── helpers ───────────────────────────────────────────────────────────────────

def _require_collector_running() -> None:
    """
    Fail fast and clearly if the collector sidecar is not up.
    A missing collector must never produce a vacuously-true 'zero spans' pass.
    """
    try:
        result = subprocess.run(
            ["docker", "ps",
             "--filter", f"name={COLLECTOR_CONTAINER}",
             "--filter", "status=running",
             "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10,
        )
    except FileNotFoundError:
        pytest.fail(
            "docker CLI not found. Stage 8 tests require the full docker-compose "
            "stack. Ensure Docker is installed and the daemon is running."
        )
    if COLLECTOR_CONTAINER not in result.stdout:
        pytest.fail(
            f"Collector container '{COLLECTOR_CONTAINER}' is not running.\n"
            "Start the full stack with:\n"
            "    docker compose -f .docker/docker-compose.yml up -d\n"
        )


def _normalize_trace_id(raw: str) -> str:
    """Normalize a trace ID to 32-char lowercase hex (handles both hex and base64)."""
    if len(raw) == 32 and all(c in "0123456789abcdefABCDEF" for c in raw):
        return raw.lower()
    try:
        return base64.b64decode(raw).hex()
    except Exception:
        return raw.lower()


def _read_all_spans() -> list[dict]:
    """
    Read every span the collector has flushed to SPANS_FILE so far.

    Uses docker cp — works without a shell in the collector container
    (otel-collector-contrib uses a minimal base image with no /bin/sh).
    Returns an empty list if the file does not exist yet.
    """
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        tmp_path = f.name
    try:
        result = subprocess.run(
            ["docker", "cp", f"{COLLECTOR_CONTAINER}:{SPANS_FILE}", tmp_path],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            if "no such container" in result.stderr.lower():
                pytest.fail(
                    f"Container '{COLLECTOR_CONTAINER}' disappeared mid-test: "
                    f"{result.stderr.strip()}"
                )
            # File doesn't exist yet — normal during cold-start, keep polling.
            return []
        with open(tmp_path) as f:
            content = f.read()
    finally:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass

    spans: list[dict] = []
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        for resource_span in payload.get("resourceSpans", []):
            resource_attrs: dict[str, str] = {}
            for attr in resource_span.get("resource", {}).get("attributes", []):
                val = attr.get("value", {})
                resource_attrs[attr["key"]] = (
                    val.get("stringValue") or val.get("intValue") or
                    val.get("boolValue") or ""
                )
            for scope_span in resource_span.get("scopeSpans", []):
                for span in scope_span.get("spans", []):
                    span["_resource_attrs"] = resource_attrs
                    spans.append(span)
    return spans


def _snapshot_span_ids() -> frozenset[str]:
    """Record current span IDs to detect new spans after a request."""
    return frozenset(s.get("spanId", "") for s in _read_all_spans())


def _poll_for_new_spans(before_ids: frozenset[str]) -> list[dict]:
    """Poll until spans appear that were not present before the request."""
    deadline = time.monotonic() + POLL_TIMEOUT_S
    while time.monotonic() < deadline:
        new = [s for s in _read_all_spans() if s.get("spanId", "") not in before_ids]
        if new:
            return new
        time.sleep(POLL_INTERVAL_S)
    return []


def _poll_for_trace_spans(before_ids: frozenset[str], min_spans: int = 2) -> list[dict]:
    """Poll until the delta contains a trace with at least min_spans spans."""
    from collections import Counter
    deadline = time.monotonic() + POLL_TIMEOUT_S
    while time.monotonic() < deadline:
        new = [s for s in _read_all_spans() if s.get("spanId", "") not in before_ids]
        if new:
            counts = Counter(_normalize_trace_id(s["traceId"]) for s in new)
            if any(n >= min_spans for n in counts.values()):
                return new
        time.sleep(POLL_INTERVAL_S)
    return []


def _post_artifact() -> httpx.Response:
    """POST a unique artifact to /artifacts — triggers Mongo + Kafka + Redis chain."""
    artifact_id = f"stage8-{uuid.uuid4().hex[:8]}"
    with httpx.Client(base_url=PIPELINE_URL, timeout=15.0) as client:
        return client.post(
            "/artifacts",
            json={
                "id":     artifact_id,
                "title":  "Stage 8 Sidecar Telemetry Test",
                "source": "test-suite",
                "tags":   ["stage8", "observability"],
            },
        )


# ── tests ─────────────────────────────────────────────────────────────────────

def test_collector_is_running():
    """
    Negative-case guard: explicitly fail if the sidecar is not up.
    A missing collector must never produce a vacuous 'zero spans' pass.
    """
    _require_collector_running()


def test_ingest_produces_spans_with_single_trace_id():
    """
    POST to /artifacts and confirm spans from that request all share one trace_id.

    Proves multi-adapter pooling (Mongo + Redis) holds through a real OTLP
    round-trip, not just InMemorySpanExporter.
    """
    _require_collector_running()
    # Allow in-flight batches from prior activity to flush before snapshotting.
    time.sleep(2.0)
    before_ids = _snapshot_span_ids()
    response = _post_artifact()
    assert response.status_code == 201, (
        f"Expected 201 from POST /artifacts, got {response.status_code}: {response.text}"
    )
    spans = _poll_for_trace_spans(before_ids, min_spans=2)
    assert spans, (
        f"No correlated trace (HTTP + adapter) appeared within {POLL_TIMEOUT_S}s. "
        "Check that TelemetryMiddleware and TracingProxy are active."
    )


def test_ingest_produces_http_and_adapter_spans():
    """
    Confirm ≥3 spans: HTTP server span + MongoDB adapter + Redis adapter.
    """
    _require_collector_running()
    before_ids = _snapshot_span_ids()
    response = _post_artifact()
    assert response.status_code == 201, (
        f"Expected 201, got {response.status_code}: {response.text}"
    )
    spans = _poll_for_trace_spans(before_ids, min_spans=3)
    assert spans, (
        f"No trace with ≥3 spans (HTTP + MongoDB + Redis) appeared within "
        f"{POLL_TIMEOUT_S}s."
    )


def test_resource_attributes_carry_service_name():
    """
    Every span's resource must tag service.name=research-pipeline.

    Proves that resource attributes survive the full serialize/transmit/collect
    round-trip.
    """
    _require_collector_running()
    before_ids = _snapshot_span_ids()
    response = _post_artifact()
    assert response.status_code == 201, (
        f"Expected 201, got {response.status_code}: {response.text}"
    )
    spans = _poll_for_new_spans(before_ids)
    assert spans, f"No new spans appeared within {POLL_TIMEOUT_S}s."
    for span in spans:
        service_name = span["_resource_attrs"].get("service.name", "")
        assert service_name == EXPECTED_SERVICE, (
            f"Span '{span.get('name')}' has service.name={service_name!r}, "
            f"expected {EXPECTED_SERVICE!r}. "
            "Check OTEL_SERVICE_NAME env var and setup_telemetry() in main.py."
        )


def test_collector_failure_does_not_crash_pipeline():
    """
    The pipeline health endpoint must return 200 — it must not depend on
    the collector being healthy in the request path.
    """
    _require_collector_running()
    with httpx.Client(base_url=PIPELINE_URL, timeout=10.0) as client:
        r = client.get("/health")
    assert r.status_code == 200, (
        f"/health returned {r.status_code}. The pipeline health endpoint must "
        "not depend on the collector being healthy."
    )
    body = r.json()
    assert body.get("status") == "ok", f"Unexpected health body: {body}"
