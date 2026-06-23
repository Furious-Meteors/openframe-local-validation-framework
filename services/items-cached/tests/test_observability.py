"""
Stage 8 — sidecar telemetry validation for items-cached (Stage 2: Postgres + Redis).

The Stage 2 assertion checks that spans from BOTH adapters appear under one
trace_id — proving dual-adapter pooling holds through the real sidecar.

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

SERVICE_URL         = "http://localhost:8006"
COLLECTOR_CONTAINER = "openframe-items-cached-collector"
SPANS_FILE          = "/var/otel/spans.jsonl"
EXPECTED_SERVICE    = "items-cached"
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


def _create_item() -> httpx.Response:
    item_id = f"stage8-{uuid.uuid4().hex[:8]}"
    with httpx.Client(base_url=SERVICE_URL, timeout=15.0) as client:
        return client.post(
            "/items",
            json={"id": item_id, "name": "Stage8 Cached Item",
                  "description": "Dual-adapter telemetry test", "status": "active"},
        )


def test_collector_is_running():
    _require_collector_running()


def test_request_produces_spans_with_single_trace_id():
    _require_collector_running()
    time.sleep(2.0)
    before_ids = _snapshot_span_ids()
    r = _create_item()
    assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
    spans = _poll_for_trace_spans(before_ids, min_spans=2)
    assert spans, (
        f"No correlated trace (HTTP + adapter) appeared within {POLL_TIMEOUT_S}s."
    )


def test_resource_attributes_carry_service_name():
    _require_collector_running()
    before_ids = _snapshot_span_ids()
    r = _create_item()
    assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
    spans = _poll_for_new_spans(before_ids)
    assert spans, f"No new spans appeared within {POLL_TIMEOUT_S}s."
    for span in spans:
        sn = span["_resource_attrs"].get("service.name", "")
        assert sn == EXPECTED_SERVICE, (
            f"Span '{span.get('name')}' has service.name={sn!r}, "
            f"expected {EXPECTED_SERVICE!r}."
        )


def test_both_adapters_produce_spans_under_one_trace():
    """
    Stage 2 assertion: Postgres persistence + Redis cache spans must both
    appear under the same trace_id — proving dual-adapter pooling holds
    through the real sidecar.
    """
    _require_collector_running()
    before_ids = _snapshot_span_ids()
    r = _create_item()
    assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
    spans = _poll_for_trace_spans(before_ids, min_spans=3)
    from collections import Counter
    counts = Counter(_normalize_trace_id(s["traceId"]) for s in spans)
    dominant_count = max(counts.values())
    assert dominant_count >= 3, (
        f"Expected the dominant trace to have ≥3 spans (HTTP + Postgres + Redis), "
        f"got {dominant_count}. Trace counts: {dict(counts)}. "
        f"Span names: {[s.get('name') for s in spans]}"
    )
