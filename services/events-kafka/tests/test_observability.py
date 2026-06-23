"""
Stage 8 — sidecar telemetry validation for events-kafka.

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

SERVICE_URL         = "http://localhost:8004"
COLLECTOR_CONTAINER = "openframe-events-kafka-collector"
SPANS_FILE          = "/var/otel/spans.jsonl"
EXPECTED_SERVICE    = "events-kafka"
POLL_TIMEOUT_S      = 30
POLL_INTERVAL_S     = 0.5


def _require_collector_running() -> None:
    try:
        result = subprocess.run(
            ["docker", "ps",
             "--filter", f"name={COLLECTOR_CONTAINER}",
             "--filter", "status=running",
             "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=10,
        )
    except FileNotFoundError:
        pytest.fail("docker CLI not found. Ensure Docker is installed and running.")
    if COLLECTOR_CONTAINER not in result.stdout:
        pytest.fail(
            f"Collector '{COLLECTOR_CONTAINER}' is not running.\n"
            "Start the full stack: docker compose -f .docker/docker-compose.yml up -d"
        )


def _normalize_trace_id(raw: str) -> str:
    if len(raw) == 32 and all(c in "0123456789abcdefABCDEF" for c in raw):
        return raw.lower()
    try:
        return base64.b64decode(raw).hex()
    except Exception:
        return raw.lower()


def _read_all_spans() -> list[dict]:
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
        for rs in payload.get("resourceSpans", []):
            attrs = {a["key"]: (a.get("value") or {}).get("stringValue", "")
                     for a in rs.get("resource", {}).get("attributes", [])}
            for ss in rs.get("scopeSpans", []):
                for span in ss.get("spans", []):
                    span["_resource_attrs"] = attrs
                    spans.append(span)
    return spans


def _snapshot_span_ids() -> frozenset[str]:
    return frozenset(s.get("spanId", "") for s in _read_all_spans())


def _poll_for_new_spans(before_ids: frozenset[str]) -> list[dict]:
    deadline = time.monotonic() + POLL_TIMEOUT_S
    while time.monotonic() < deadline:
        new = [s for s in _read_all_spans() if s.get("spanId", "") not in before_ids]
        if new:
            return new
        time.sleep(POLL_INTERVAL_S)
    return []


def _poll_for_correlated_spans(before_ids: frozenset[str]) -> list[dict]:
    """Poll until the delta contains a trace with ≥2 spans (HTTP + adapter)."""
    from collections import Counter
    deadline = time.monotonic() + POLL_TIMEOUT_S
    while time.monotonic() < deadline:
        new = [s for s in _read_all_spans() if s.get("spanId", "") not in before_ids]
        if new:
            counts = Counter(_normalize_trace_id(s["traceId"]) for s in new)
            if any(n >= 2 for n in counts.values()):
                return new
        time.sleep(POLL_INTERVAL_S)
    return []


def _publish_event() -> httpx.Response:
    order_id = f"stage8-{uuid.uuid4().hex[:8]}"
    with httpx.Client(base_url=SERVICE_URL, timeout=15.0) as client:
        return client.post(
            "/events",
            json={"order_id": order_id, "event_type": "created",
                  "payload": {"amount": 1.0, "test": "stage8"}},
        )


def test_collector_is_running():
    _require_collector_running()


def test_request_produces_spans_with_single_trace_id():
    _require_collector_running()
    time.sleep(2.0)
    before_ids = _snapshot_span_ids()
    r = _publish_event()
    assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
    spans = _poll_for_correlated_spans(before_ids)
    assert spans, (
        f"No correlated trace (HTTP + adapter) appeared within {POLL_TIMEOUT_S}s."
    )


def test_resource_attributes_carry_service_name():
    _require_collector_running()
    before_ids = _snapshot_span_ids()
    r = _publish_event()
    assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
    spans = _poll_for_new_spans(before_ids)
    assert spans, f"No new spans appeared within {POLL_TIMEOUT_S}s."
    for span in spans:
        sn = span["_resource_attrs"].get("service.name", "")
        assert sn == EXPECTED_SERVICE, (
            f"Span '{span.get('name')}' has service.name={sn!r}, "
            f"expected {EXPECTED_SERVICE!r}."
        )


def test_at_least_http_and_adapter_span_present():
    _require_collector_running()
    before_ids = _snapshot_span_ids()
    r = _publish_event()
    assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
    spans = _poll_for_correlated_spans(before_ids)
    assert spans, (
        f"No correlated trace (HTTP + adapter) appeared within {POLL_TIMEOUT_S}s."
    )
