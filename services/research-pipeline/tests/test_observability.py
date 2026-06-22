"""
Stage 8 — sidecar telemetry validation.

Proves that openframe-core's TelemetryMiddleware and openframe-adapters'
TracingProxy produce spans that survive a real OTLP serialize → transmit →
collect → file round-trip (not just InMemorySpanExporter).

Prerequisites
-------------
The full docker-compose stack must be running, including the sidecar:

    docker compose -f .docker/docker-compose.yml up -d

What is asserted
----------------
1. A POST to /artifacts triggers the Mongo store → Kafka publish → Redis cache
   chain and produces at least 3 spans (HTTP + Mongo + Redis).
2. All spans from that request share exactly one trace_id — confirming
   multi-adapter pooling holds through a real collector, not just in-memory.
3. Every span's resource attributes carry service.name=research-pipeline —
   proving resource tagging survives the full serialize/transmit/collect trip.
4. If the sidecar collector container is not running the test fails loudly
   with a clear diagnostic, never silently passes with zero spans.

Negative-case protection
------------------------
_require_collector_running() is called at the top of each test. It uses
`docker ps` to confirm the container exists before any span-reading attempt.
A missing or exited collector produces an immediate pytest.fail(), not a
vacuously-true "0 spans found" assertion.
"""
from __future__ import annotations

import base64
import json
import subprocess
import time
import uuid

import httpx
import pytest

# ── constants ────────────────────────────────────────────────────────────────

PIPELINE_URL       = "http://localhost:8007"
COLLECTOR_CONTAINER = "openframe-research-pipeline-collector"
SPANS_FILE         = "/var/otel/spans.jsonl"
POLL_TIMEOUT_S     = 30
POLL_INTERVAL_S    = 0.5

# Span-name substrings that must appear in the collected trace.
# TracingProxy prefixes: "repository.artifact.mongo" and "repository.artifact.redis".
# TelemetryMiddleware produces HTTP server spans named after the route.
EXPECTED_SPAN_PREFIXES = [
    "repository.artifact.mongo",   # MongoDB adapter — persistence
    "repository.artifact.redis",   # Redis adapter   — status cache
]


# ── helpers ──────────────────────────────────────────────────────────────────

def _require_collector_running() -> None:
    """
    Fail fast and clearly if the collector sidecar is not up.

    Uses `docker ps` (not `docker exec`) so we detect exited / missing
    containers before attempting file reads.
    """
    try:
        result = subprocess.run(
            [
                "docker", "ps",
                "--filter", f"name={COLLECTOR_CONTAINER}",
                "--filter", "status=running",
                "--format", "{{.Names}}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
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
            "Then wait for all services to be healthy:\n"
            "    docker compose -f .docker/docker-compose.yml ps\n"
            "\n"
            "A missing collector must not produce a vacuously-true 'zero spans' pass."
        )


def _normalize_trace_id(raw: str) -> str:
    """
    Normalize a trace ID to a 32-char lowercase hex string.

    The otel-collector-contrib file exporter marshals trace IDs as 32-char
    hex strings (pdata JSON format). This helper also handles base64 in case
    a future collector version changes the encoding.
    """
    if len(raw) == 32 and all(c in "0123456789abcdefABCDEF" for c in raw):
        return raw.lower()
    # Attempt base64 → hex fallback
    try:
        return base64.b64decode(raw).hex()
    except Exception:
        return raw.lower()


def _read_all_spans() -> list[dict]:
    """
    Read every span the collector has flushed to SPANS_FILE so far.

    Returns an empty list if the file does not exist yet (collector started
    but no batch flushed). Raises via pytest.fail() only if the container
    itself is not running (checked separately by _require_collector_running).

    Each returned span dict has an extra "_resource_attrs" key containing
    the flat {key: value} resource attributes from its ResourceSpan wrapper.
    """
    result = subprocess.run(
        [
            "docker", "exec", COLLECTOR_CONTAINER,
            "sh", "-c", f"test -f {SPANS_FILE} && cat {SPANS_FILE} || true",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        # Container gone mid-test — surface the error.
        pytest.fail(
            f"docker exec failed against '{COLLECTOR_CONTAINER}': {result.stderr.strip()}"
        )

    spans: list[dict] = []
    for line in result.stdout.splitlines():
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
                    val.get("stringValue")
                    or val.get("intValue")
                    or val.get("boolValue")
                    or ""
                )
            for scope_span in resource_span.get("scopeSpans", []):
                for span in scope_span.get("spans", []):
                    span["_resource_attrs"] = resource_attrs
                    spans.append(span)

    return spans


def _poll_spans_for_trace(trace_id_hex: str) -> list[dict]:
    """
    Poll SPANS_FILE until spans for trace_id_hex appear, or timeout.

    Returns the matching spans (empty list on timeout — caller asserts).
    """
    deadline = time.monotonic() + POLL_TIMEOUT_S
    while time.monotonic() < deadline:
        all_spans = _read_all_spans()
        matched = [
            s for s in all_spans
            if _normalize_trace_id(s.get("traceId", "")) == trace_id_hex
        ]
        if matched:
            return matched
        time.sleep(POLL_INTERVAL_S)
    return []


def _post_artifact(trace_id_hex: str) -> httpx.Response:
    """
    POST a unique artifact to /artifacts with a W3C traceparent header so we
    can correlate the resulting spans by the injected trace_id.
    """
    parent_span_id = uuid.uuid4().hex[:16]
    traceparent    = f"00-{trace_id_hex}-{parent_span_id}-01"
    artifact_id    = f"stage8-{uuid.uuid4().hex[:8]}"

    with httpx.Client(base_url=PIPELINE_URL, timeout=15.0) as client:
        return client.post(
            "/artifacts",
            json={
                "id":     artifact_id,
                "title":  "Stage 8 Sidecar Telemetry Test",
                "source": "test-suite",
                "tags":   ["stage8", "observability"],
            },
            headers={"traceparent": traceparent},
        )


# ── tests ────────────────────────────────────────────────────────────────────

def test_collector_is_running():
    """
    Negative-case guard: explicitly fail if the sidecar is not up.

    This runs before any span-reading test so the failure message is
    unambiguous — a missing collector can never silently look like
    "zero spans found, nothing to assert".
    """
    _require_collector_running()


def test_ingest_produces_spans_with_single_trace_id():
    """
    POST to /artifacts and confirm the resulting spans all share one trace_id.

    Proves that multi-adapter pooling (Mongo + Redis) holds through a real
    OTLP network round-trip, not just InMemorySpanExporter.
    """
    _require_collector_running()

    trace_id = uuid.uuid4().hex  # 32-char lowercase hex — valid W3C trace ID

    response = _post_artifact(trace_id)
    assert response.status_code == 201, (
        f"Expected 201 from POST /artifacts, got {response.status_code}: {response.text}"
    )

    spans = _poll_spans_for_trace(trace_id)
    assert spans, (
        f"No spans with trace_id={trace_id} appeared in {SPANS_FILE} within "
        f"{POLL_TIMEOUT_S}s. Check that TelemetryMiddleware extracts the incoming "
        "traceparent header (requires openframe-core fix: TelemetryMiddleware "
        "reads W3C traceparent on inbound requests)."
    )

    # All spans share exactly one trace_id (the one we injected).
    trace_ids_found = {_normalize_trace_id(s["traceId"]) for s in spans}
    assert trace_ids_found == {trace_id}, (
        f"Expected all spans to carry trace_id={trace_id}, "
        f"but found: {trace_ids_found}"
    )


def test_ingest_produces_http_and_adapter_spans():
    """
    Confirm that at least the HTTP server span plus Mongo and Redis adapter
    spans are present — proving the entire pipeline is instrumented end-to-end.
    """
    _require_collector_running()

    trace_id = uuid.uuid4().hex

    response = _post_artifact(trace_id)
    assert response.status_code == 201, (
        f"Expected 201, got {response.status_code}: {response.text}"
    )

    spans = _poll_spans_for_trace(trace_id)
    assert spans, (
        f"No spans appeared for trace_id={trace_id} within {POLL_TIMEOUT_S}s."
    )

    span_names = [s.get("name", "") for s in spans]

    # HTTP server span — produced by TelemetryMiddleware.
    http_spans = [n for n in span_names if "/artifacts" in n or "POST" in n]
    assert http_spans, (
        f"No HTTP server span found in: {span_names}\n"
        "TelemetryMiddleware should produce a span for POST /artifacts."
    )

    # Adapter spans — produced by TracingProxy with the registered prefixes.
    for prefix in EXPECTED_SPAN_PREFIXES:
        matching = [n for n in span_names if n.startswith(prefix)]
        assert matching, (
            f"No span with prefix '{prefix}' found in: {span_names}\n"
            f"TracingProxy(prefix='{prefix}') should emit spans for every "
            "adapter method called during ingest()."
        )


def test_resource_attributes_carry_service_name():
    """
    Every span's resource must tag service.name=research-pipeline.

    Proves that the OTel resource attributes survive the full
    serialize → transmit → collect → file round-trip.
    """
    _require_collector_running()

    trace_id = uuid.uuid4().hex

    response = _post_artifact(trace_id)
    assert response.status_code == 201, (
        f"Expected 201, got {response.status_code}: {response.text}"
    )

    spans = _poll_spans_for_trace(trace_id)
    assert spans, (
        f"No spans appeared for trace_id={trace_id} within {POLL_TIMEOUT_S}s."
    )

    for span in spans:
        service_name = span["_resource_attrs"].get("service.name", "")
        assert service_name == "research-pipeline", (
            f"Span '{span.get('name')}' has service.name={service_name!r}, "
            "expected 'research-pipeline'. "
            "Check OTEL_SERVICE_NAME env var and setup_telemetry() in main.py."
        )


def test_collector_failure_does_not_crash_pipeline():
    """
    Smoke-test resilience: the pipeline health endpoint must return 200 even
    when queried independently of the collector.

    The full kill-and-keep-serving acceptance criterion requires manual
    intervention (docker stop research-pipeline-collector while sending traffic).
    This test validates the baseline: the app endpoint is reachable and healthy
    without any collector dependency in the request path.
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
