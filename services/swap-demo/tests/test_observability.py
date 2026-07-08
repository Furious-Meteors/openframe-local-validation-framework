"""
Stage 8 — sidecar telemetry validation for swap-demo.

service.name must be 'swap-demo' regardless of the active backend (postgres/mongo).

Prerequisites
-------------
    docker compose -f .docker/docker-compose.yml up -d
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
import subprocess
import tempfile
import time
import uuid

import httpx
import pytest

SERVICE_URL         = "http://localhost:8005"
SWAP_SERVICE        = "swap-demo"
COLLECTOR_CONTAINER = "openframe-swap-demo-collector"
SPANS_FILE          = "/var/otel/spans.jsonl"
EXPECTED_SERVICE    = "swap-demo"
POLL_TIMEOUT_S      = 30
POLL_INTERVAL_S     = 0.5

COMPOSE_FILE = (
    pathlib.Path(__file__).resolve().parents[3] / ".docker" / "docker-compose.yml"
)
BACKEND_RESTART_TIMEOUT_S = 90
BACKEND_HEALTH_TIMEOUT_S  = 60


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


def _create_item() -> httpx.Response:
    item_id = f"stage8-{uuid.uuid4().hex[:8]}"
    with httpx.Client(base_url=SERVICE_URL, timeout=15.0) as client:
        return client.post(
            "/items",
            json={"id": item_id, "name": "Stage8 Swap Item",
                  "description": "Adapter-swap telemetry test"},
        )


def test_collector_is_running():
    _require_collector_running()


def test_request_produces_spans_with_single_trace_id():
    _require_collector_running()
    time.sleep(2.0)
    before_ids = _snapshot_span_ids()
    r = _create_item()
    assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
    spans = _poll_for_correlated_spans(before_ids)
    assert spans, (
        f"No correlated trace (HTTP + adapter) appeared within {POLL_TIMEOUT_S}s."
    )


def test_resource_attributes_carry_service_name():
    """service.name must be 'swap-demo' regardless of which backend is active."""
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


def test_at_least_http_and_adapter_span_present():
    _require_collector_running()
    before_ids = _snapshot_span_ids()
    r = _create_item()
    assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
    spans = _poll_for_correlated_spans(before_ids)
    assert spans, (
        f"No correlated trace (HTTP + adapter) appeared within {POLL_TIMEOUT_S}s."
    )


# ── backend-flip helpers ─────────────────────────────────────────────────────
#
# test_resource_attributes_carry_service_name() above only proves service.name
# for whichever backend happens to be active when the suite runs — it never
# flips PERSISTENCE_BACKEND and re-checks. test_service_name_consistent_across_
# both_backends() below closes that gap by actually restarting the swap-demo
# container under both backends in one test run.

def _restart_with_backend(backend: str) -> None:
    """Recreate the swap-demo container with PERSISTENCE_BACKEND=<backend>."""
    env = {**os.environ, "PERSISTENCE_BACKEND": backend}
    result = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d", "--no-deps", SWAP_SERVICE],
        capture_output=True, text=True, timeout=BACKEND_RESTART_TIMEOUT_S, env=env,
    )
    if result.returncode != 0:
        pytest.fail(
            f"Failed to restart {SWAP_SERVICE} with PERSISTENCE_BACKEND={backend}: "
            f"{result.stderr.strip()}"
        )
    _wait_for_health()

    # Recreating swap-demo gives it a new container ID. The collector's
    # network_mode: service:swap-demo is resolved to a container ID at the
    # collector's own creation time and does not follow the app across a
    # `--no-deps` recreate, so it must be force-recreated here too or it is
    # left attached to the now-dead network namespace and never sees spans.
    collector_result = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d",
         "--no-deps", "--force-recreate", f"{SWAP_SERVICE}-collector"],
        capture_output=True, text=True, timeout=BACKEND_RESTART_TIMEOUT_S, env=env,
    )
    if collector_result.returncode != 0:
        pytest.fail(
            f"Failed to recreate {SWAP_SERVICE}-collector after backend switch: "
            f"{collector_result.stderr.strip()}"
        )


def _wait_for_health(timeout_s: float = BACKEND_HEALTH_TIMEOUT_S) -> None:
    deadline = time.monotonic() + timeout_s
    last_error = "no attempt made"
    while time.monotonic() < deadline:
        try:
            with httpx.Client(base_url=SERVICE_URL, timeout=5.0) as client:
                r = client.get("/health")
            if r.status_code == 200:
                return
            last_error = f"status={r.status_code}"
        except httpx.HTTPError as exc:
            last_error = str(exc)
        time.sleep(1.0)
    pytest.fail(
        f"{SWAP_SERVICE} did not become healthy within {timeout_s}s "
        f"after a backend restart: {last_error}"
    )


def test_service_name_consistent_across_both_backends():
    """
    Prove service.name = 'swap-demo' for BOTH postgres and mongo backends by
    restarting the service with each PERSISTENCE_BACKEND value and asserting
    the span resource attribute is identical.

    Uses docker compose to recreate the swap-demo container under each
    backend, then reuses the same span-collection helpers as the rest of
    this file. Restores PERSISTENCE_BACKEND=postgres in a finally block so a
    failed assertion never leaves the stack on a non-default backend.
    """
    _require_collector_running()

    observed: dict[str, set[str]] = {}
    try:
        for backend in ("postgres", "mongo"):
            _restart_with_backend(backend)
            before_ids = _snapshot_span_ids()
            r = _create_item()
            assert r.status_code == 201, (
                f"Expected 201 with PERSISTENCE_BACKEND={backend}, "
                f"got {r.status_code}: {r.text}"
            )
            spans = _poll_for_new_spans(before_ids)
            assert spans, (
                f"No new spans appeared within {POLL_TIMEOUT_S}s "
                f"with PERSISTENCE_BACKEND={backend}."
            )
            observed[backend] = {
                span["_resource_attrs"].get("service.name", "") for span in spans
            }
    finally:
        _restart_with_backend("postgres")

    for backend, names in observed.items():
        assert names == {EXPECTED_SERVICE}, (
            f"PERSISTENCE_BACKEND={backend}: expected every span tagged "
            f"service.name={EXPECTED_SERVICE!r}, got {names}."
        )
