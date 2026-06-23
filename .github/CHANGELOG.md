# Changelog

All notable changes to the Stage 8 sidecar telemetry validation work in this repository.

---

## [Unreleased] — Stage 8: Sidecar Telemetry Validation (2026-06-24)

### Summary

Added **Stage 8 — sidecar telemetry validation** across all seven OpenFrame validation services. The goal is to prove that spans produced by `TelemetryMiddleware` and `TracingProxy` survive a real **OTLP serialize → transmit → collect → file** round-trip through a dedicated OpenTelemetry Collector sidecar per service — not just an `InMemorySpanExporter` in unit tests.

---

## Architecture decisions

This section records **why** choices were made, not just what was built. Each decision includes the alternatives considered and the reason it was accepted or rejected.

### AD-1 — One sidecar per service, no shared gateway

**Decision:** Every app service gets its own `<service>-collector` container. There is no central OTel gateway tier.

**Rationale:** This is a validation framework, not a production observability deployment. Per-service sidecars mirror the production sidecar pattern (collector co-located with the process) and isolate failure domains — a misconfigured collector for `cache-redis` must not affect `research-pipeline` span capture.

**Rejected alternative:** A single shared collector on a bridge network receiving OTLP from all seven services. Rejected because it would not prove the `localhost:4318` sidecar wiring that OpenFrame services use in production, and would mix span files from different services into one assertion surface.

---

### AD-2 — `network_mode: "service:<app>"` for sidecar networking

**Decision:** Each collector container shares the app container's network namespace via Docker Compose `network_mode: "service:<app>"`.

**Rationale:** Inside the app, `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318` must resolve to the sidecar listener with zero extra network hops — exactly how a real sidecar deployment works. No service-specific hostnames, no port mapping gymnastics, no bridge-network DNS.

**Trade-off accepted:** The collector **cannot start until the app container exists** (`network_mode` requires the target service to be running). A few spans produced in the first seconds after app boot may be dropped by the SDK's bounded export queue before the collector is listening. This is documented as expected behaviour: **bounded loss, never blocking** — apps keep serving traffic regardless of collector availability.

---

### AD-3 — Shared collector config, isolated data volumes

**Decision:** One read-only config file (`.docker/collector-config.yaml`) bind-mounted into all seven sidecars. Each sidecar writes to its own named Docker volume (`<service>_otel_data`).

**Rationale:** All services need identical pipeline semantics (OTLP/HTTP → batch → file + debug). Per-service config duplication would drift. Span data must stay isolated so `test_observability.py` for `items-postgres` never reads spans from `swap-demo`.

**Rejected alternative:** Per-service `collector-config.yaml` files (initially created for `research-pipeline`). Consolidated to `.docker/collector-config.yaml` once the full rollout proved configs were identical.

---

### AD-4 — File exporter for test assertions, not Jaeger/Tempo

**Decision:** Collector pipeline ends in a `file` exporter writing JSON lines to `/var/otel/spans.jsonl`. Tests read and parse this file.

**Rationale:** Stage 8 proves the **mechanism** (OTLP round-trip + resource attribute survival), not a specific backend vendor. File output is deterministic, requires no extra infrastructure, and makes assertions inspectable with `docker cp`. Swapping to Jaeger or Grafana Tempo later is a one-line exporter config change.

**Also included:** `debug` exporter at `verbosity: basic` for human sanity checks via `docker compose logs <service>-collector`.

---

### AD-5 — `batch` processor with 1 s timeout

**Decision:** Collector uses `batch` with `timeout: 1s` and `send_batch_size: 512`.

**Rationale:** Tests poll `spans.jsonl` on a 0.5 s interval with a 30 s deadline. A 1 s batch flush keeps the file fresh enough for polling without busy-flushing every span individually. Larger batch sizes would increase test latency without improving correctness.

---

### AD-6 — Span-ID delta polling instead of traceparent injection

**Decision:** Tests snapshot the set of `spanId` values before a request, fire the request, then poll for spans whose IDs were not in the snapshot.

**Rationale (initial approach abandoned):** The original design injected a W3C `traceparent` header on test HTTP requests so all new spans would share a known trace ID. This was abandoned because the **installed `openframe-core` version's `TelemetryMiddleware` does not extract incoming traceparent headers** in this environment — upstream support exists but is not wired in the dependency pin used here.

**Current approach:** Delta-by-`spanId` is robust against unknown prior state in the spans file and does not depend on middleware version.

---

### AD-7 — Correlated trace polling instead of strict single-trace assertions

**Decision:** Tests wait until the delta contains at least one `trace_id` with ≥2 spans (HTTP + adapter), or ≥3 for multi-adapter services — rather than asserting `len(unique_trace_ids) == 1`.

**Rationale:** Docker Compose healthchecks (`GET /health` every few seconds), prior `validate_all.sh` HTTP traffic, and batch flush timing all contribute **extra trace IDs** to the delta. A strict "exactly one trace" assertion produces false failures even when the request's own span chain is correct.

**Evolution:** `_poll_for_new_spans()` was replaced by `_poll_for_correlated_spans()` / `_poll_for_trace_spans(min_spans=N)` because the former returned on the **first** new span — almost always a lone healthcheck span — before adapter spans flushed.

---

### AD-8 — Read spans via `docker cp`, not `docker exec`

**Decision:** `test_observability.py` copies `/var/otel/spans.jsonl` out of the collector container with `docker cp` into a temp file, then parses JSON locally.

**Rationale:** `otel/opentelemetry-collector-contrib` uses a minimal base image with **no `/bin/sh`**. `docker exec … cat` and `docker exec … sh -c` both fail. `docker cp` works against any running container regardless of shell availability.

---

### AD-9 — Collectors run as `user: "0"` (root)

**Decision:** All seven collector services set `user: "0"` in docker-compose.

**Rationale:** Named Docker volumes are created root-owned. The default non-root collector user could not write to `/var/otel/spans.jsonl`, causing immediate collector crash loops. Running as root inside an isolated sidecar container is acceptable for a local validation stack.

**Rejected alternative:** Pre-create volume directories with correct ownership via an init container. Rejected as unnecessary complexity for a dev/validation stack.

---

### AD-10 — No `file_storage` collector extension

**Decision:** The shared collector config has no `extensions.file_storage` block.

**Rationale:** `file_storage` was initially added (in both the per-service and shared configs) to pre-create a queue directory on the named volume. Collectors crashed on startup with `file_storage: directory must exist` because `/var/otel/queue` was not present and the extension does not auto-create it. The `file` exporter writes directly to disk and **does not require** `file_storage` — the extension was removed entirely.

---

### AD-11 — Full Docker stack (Option A) vs host services (Option B)

**Decision:** README documents two workflows. Option A (`docker compose up -d --build` for all services + sidecars) is recommended. Option B (host-run uvicorn, Docker backends only) remains supported but **Stage 8 tests are skipped** when collector containers are absent.

**Rationale:** Stage 8 requires real sidecar containers. Host-mode developers still get HTTP validation from `validate_all.sh`; Stage 8 runs only when each `openframe-<service>-collector` is confirmed running via `docker ps`.

---

### AD-12 — Rollout scope: all seven services, not just `research-pipeline`

**Decision:** Stage 8 was initially scoped to `research-pipeline` only (maximum multi-adapter signal). Expanded to all seven services after explicit architectural confirmation that **every service gets its own sidecar, period**.

**Rationale for starting with `research-pipeline`:** Three adapters (Mongo + Redis + Kafka) in one request proves multi-adapter span pooling through a real collector — the highest-value single test target.

**Rationale for expanding:** Consistency across the validation matrix. Each Stage 1/2 service should prove its own OTLP round-trip independently. `items-cached` adds a Stage 2-specific assertion (Postgres + Redis under one trace). Single-adapter services prove resource attribute survival and HTTP + adapter correlation.

---

### AD-13 — Kafka dual listener: `PLAINTEXT` (host) + `INTERNAL` (Docker)

**Decision:** Kafka advertises `PLAINTEXT://localhost:9092` for host-side services and `INTERNAL://kafka:29092` for containerised services.

**Rationale:** Containerised `events-kafka`, `items-cached` (if needed), and `research-pipeline` connect to `kafka:29092` inside the Docker network. Host-side Option B services continue using `localhost:9092` unchanged. A single listener cannot satisfy both address families correctly in Docker Compose.

---

### AD-14 — `TracingProxy` on every outbound port, including producers

**Decision:** All repository and producer dependencies wrapped in `TracingProxy` at the composition root (`bootstrap/dependencies.py`).

**Rationale:** Stage 8 asserts ≥2 spans per request (HTTP middleware span + adapter span). Services that wired the repository but not the Kafka producer (`events-kafka`, `research-pipeline`) passed HTTP checks but failed Stage 8 — only the HTTP span appeared in the collector file.

**Convention:** Repository prefixes use `repository.*` or `cache.*`; producer prefixes use `queue.event`.

---

### AD-15 — Fail-loud collector guard in every test file

**Decision:** Every `test_observability.py` calls `_require_collector_running()` at the start of each test, failing with an explicit message if the sidecar container is not up.

**Rationale:** Without this guard, a missing collector produces **zero spans**, and naive assertions could vacuously pass or produce confusing timeouts. Stage 8 must never give false confidence.

---

### AD-16 — `validate_all.sh` Stage 8 loop with per-service collector detection

**Decision:** `_run_stage8()` iterates all seven services, running pytest only when that service's collector is confirmed running. Uses `|| fail` in the main shell (not a subshell) so test failures exit the script correctly.

**Rationale:** Replacing the original single-service Stage 8 block. The initial implementation ran pytest inside `( … )` subshell where `fail`/`exit` did not propagate to the parent script — Stage 8 failures were silently swallowed.

---

### AD-17 — Idempotent HTTP validation with `cleanup()` pre-deletes

**Decision:** `validate_all.sh` calls `cleanup()` (silent `DELETE`) before create operations so the script can be re-run against persistent Docker volumes without duplicate-key errors.

**Rationale:** Named volumes survive `docker compose down`. Without pre-delete, second runs fail on `201` expectations when resources already exist.

---

## Detailed bugs and issues

Each entry: **ID · severity · component · symptom → root cause → fix**.

---

### Infrastructure and Docker

#### BUG-01 · Blocker · OTel Collector · Startup crash: `file_storage: directory must exist`

- **Symptom:** All collector containers exited immediately on first boot. `docker compose ps` showed collectors in `Exited (1)` state.
- **Root cause:** Shared and per-service collector configs declared `extensions.file_storage` pointing at `/var/otel/queue`, which did not exist on the fresh named volume. The extension validates directory existence at startup and refuses to start.
- **Fix:** Removed `file_storage` extension entirely. The `file` exporter does not use it.
- **Lesson:** Do not declare collector extensions "for future use" unless the pipeline actually references them and paths are guaranteed to exist.

---

#### BUG-02 · Blocker · OTel Collector · Startup crash: `permission denied` on `/var/otel/spans.jsonl`

- **Symptom:** Collectors started after BUG-01 fix but immediately logged `open /var/otel/spans.jsonl: permission denied` and exited.
- **Root cause:** Named Docker volumes are root-owned. `otel-collector-contrib` runs as a non-root user (`10001`) by default and cannot create/write the spans file.
- **Fix:** Added `user: "0"` to all seven collector service definitions in docker-compose.
- **Note:** Apps are unaffected — only collector write access was broken.

---

#### BUG-03 · Blocker · Stage 8 tests · `docker exec` cannot read spans file

- **Symptom:** Tests failed with `OCI runtime exec failed: exec failed: unable to start container process: exec: "sh": executable file not found in $PATH` (or equivalent).
- **Root cause:** `otel/opentelemetry-collector-contrib:latest` is a distroless/minimal image with no shell binary. All `docker exec … sh -c "cat …"` patterns fail.
- **Fix:** Replaced with `docker cp <container>:/var/otel/spans.jsonl <tmpfile>` in all seven `test_observability.py` files.
- **Architecture link:** AD-8.

---

#### BUG-04 · Blocker · Kafka · Containerised services cannot reach broker

- **Symptom:** `events-kafka` and `research-pipeline` containers logged Kafka connection errors; `AdapterConnectionError` at startup or failed publishes inside Docker network.
- **Root cause:** Kafka advertised only `PLAINTEXT://localhost:9092`. From inside another container, `localhost:9092` resolves to that container's own loopback, not the Kafka broker.
- **Fix:** Added `INTERNAL://0.0.0.0:29092` listener with `KAFKA_ADVERTISED_LISTENERS: …,INTERNAL://kafka:29092` and updated `KAFKA_LISTENER_SECURITY_PROTOCOL_MAP`. Container env vars point bootstrap servers at `kafka:29092`.
- **Architecture link:** AD-13.

---

#### BUG-05 · High · Postgres services · `DATABASE_URL` dialect prefix rejected

- **Symptom:** `items-postgres`, `items-cached`, and `swap-demo` (Postgres mode) returned 500 on first DB touch inside Docker.
- **Root cause:** Compose env used `postgresql+asyncpg://…` — SQLAlchemy-style dialect URL. `PostgresSettings` / asyncpg driver expects plain `postgresql://`.
- **Fix:** Changed compose `DATABASE_URL` values to `postgresql://openframe:openframe@postgres:5432/openframe`.

---

#### BUG-06 · High · Postgres · `swap_items` table missing on existing volume

- **Symptom:** `swap-demo` POST `/items` returned 500. Logs: `asyncpg.exceptions.UndefinedTableError: relation "swap_items" does not exist`.
- **Root cause:** Postgres named volume predated the `swap_items` DDL in `.docker/scripts/init_postgres.sql`. Init scripts run only on **first** volume creation — adding a table to the init script does not migrate existing volumes.
- **Fix:** Manual `CREATE TABLE IF NOT EXISTS swap_items (…)` on the running Postgres container during validation. Init script already correct for fresh installs.
- **Operational note:** Developers with old volumes must recreate the volume or apply the DDL manually.

---

#### BUG-07 · Medium · Docker Compose · Parallel collector image pull race

- **Symptom:** Intermittent `docker compose up` failures when seven sidecars simultaneously pulled `otel/opentelemetry-collector-contrib:latest`.
- **Root cause:** Parallel pull contention on the same image tag.
- **Fix:** Pre-pull the collector image once before `docker compose up -d`:
  ```bash
  docker pull otel/opentelemetry-collector-contrib:latest
  ```

---

#### BUG-08 · Low · App startup · OTLP export warnings before collector ready

- **Symptom:** App logs showed `Failed to export traces … Connection refused` and `retrying` messages during the first few seconds after `docker compose up`.
- **Root cause:** Expected cold-start race — app container starts before its sidecar (AD-2 trade-off). SDK retries then drops from bounded queue.
- **Fix:** None required. Documented as expected. Apps serve traffic normally; spans during the gap may be lost.

---

### Service application code

#### BUG-09 · Blocker · `swap-demo` · Zero telemetry spans exported

- **Symptom:** Stage 8 tests for `swap-demo` timed out with no new spans (or only healthcheck spans after other fixes). `test_resource_attributes_carry_service_name` could not find request spans.
- **Root cause:** `swap-demo/src/entrypoints/http/main.py` never called `setup_telemetry()` and did not register `TelemetryMiddleware` — the only service in the matrix missing telemetry wiring.
- **Fix:** Added `setup_telemetry()` in lifespan and `app.add_middleware(TelemetryMiddleware)` matching all other services.

---

#### BUG-10 · High · `swap-demo` · `GET /items` returned 500

- **Symptom:** `validate_all.sh` failed at `swap-demo` list check with expected 200, got 500.
- **Root cause (two issues):**
  1. `SwapItemService.list()` called `self._repo.list()` without `limit`/`offset` — repository signature requires them.
  2. Repository `list()` returns `(items, total)` tuple; service returned the raw tuple instead of unpacking `items`.
- **Fix:** `list(self, limit=20, offset=0)` with `items, _total = await self._repo.list(limit, offset)`; routes pass `Query` params through.

---

#### BUG-11 · High · `events-kafka` · No adapter spans in collector output

- **Symptom:** Stage 8 failed — delta contained HTTP span only, no `queue.event.*` adapter span.
- **Root cause:** `get_event_service()` returned the raw `KafkaProducer` without `TracingProxy`. HTTP middleware span was exported; producer publish was not instrumented at the composition root.
- **Fix:** `TracingProxy(_producer, prefix="queue.event")` in `dependencies.py`.
- **Follow-up:** Container rebuild required (`docker compose up -d --build events-kafka`).

---

#### BUG-12 · High · `research-pipeline` · Kafka producer spans missing

- **Symptom:** Stage 8 `test_ingest_produces_http_and_adapter_spans` intermittently saw only 2 spans (HTTP + Mongo), not the expected ≥3.
- **Root cause:** Same as BUG-11 — `get_pipeline_service()` passed the raw Kafka producer as `publisher=` without `TracingProxy`. Mongo and Redis were wrapped; Kafka was not.
- **Fix:** `TracingProxy(..., prefix="queue.event")` on the producer in `dependencies.py`.
- **Follow-up:** Container rebuild required.

---

#### BUG-13 · Medium · `research-pipeline` · No DELETE endpoint for validation script

- **Symptom:** `validate_all.sh` research-pipeline section could not complete idempotent cleanup / delete check.
- **Root cause:** Service had POST/GET routes but no `DELETE /artifacts/{id}`.
- **Fix:** Added `delete_artifact()` to `ResearchPipelineService` and corresponding route in `routes.py`.

---

#### BUG-14 · Low · `swap-demo` Docker · Module import path in container

- **Symptom:** `swap-demo` container failed to start or crashed on import — uvicorn could not resolve application module.
- **Root cause:** `swap-demo` uses src-layout with `pythonpath=["src"]` in pyproject — packages import as `entrypoints.http.main`, not `src.entrypoints.http.main`. Dockerfile CMD and `PYTHONPATH` must match host dev setup.
- **Fix:** Dockerfile sets `ENV PYTHONPATH=/app/src` and `CMD ["uvicorn", "entrypoints.http.main:app", …]`.

---

### Test framework and assertion logic

#### BUG-15 · High · All services · Vacuous pass risk when collector absent

- **Symptom:** Without `_require_collector_running()`, tests polling an empty spans file could fail opaquely or (with weak assertions) appear to pass.
- **Root cause:** No explicit precondition check on collector container state.
- **Fix:** `_require_collector_running()` at the start of every test — `pytest.fail()` with actionable docker-compose instructions.
- **Architecture link:** AD-15.

---

#### BUG-16 · High · All services · Traceparent injection did not isolate test traces

- **Symptom:** Early test design injected `traceparent` on requests expecting all delta spans to share that trace ID. Assertions failed unpredictably.
- **Root cause:** Installed `openframe-core` version does not extract incoming W3C `traceparent` in `TelemetryMiddleware` despite upstream changelog notes — dependency pin lag.
- **Fix:** Abandoned traceparent approach entirely. Switched to span-ID delta polling (AD-6).

---

#### BUG-17 · High · All services · Strict `len(trace_ids) == 1` false failures

- **Symptom:** Tests failed with multiple trace IDs in delta even when the request's own spans were correctly correlated.
- **Root cause:** Docker healthchecks, concurrent `validate_all.sh` HTTP calls, and prior test runs added unrelated traces to the delta between snapshot and assertion.
- **Fix:** Replaced with "at least one trace in delta has ≥N spans" (AD-7).

---

#### BUG-18 · High · `swap-demo` (and others) · Early-return poll captured healthcheck only

- **Symptom:**
  ```
  AssertionError: No trace_id has ≥2 correlated spans (HTTP + adapter).
  Trace counts: {'eed4dcd7382c59aa0bf37b90acbe3bf6': 1}.
  Span names: ['HTTP GET /health']
  ```
  Notably, `test_at_least_http_and_adapter_span_present` could pass in a later run while `test_request_produces_spans_with_single_trace_id` failed — same poll helper, different assertion timing.
- **Root cause:** `_poll_for_new_spans()` returned immediately on the **first** new span. Docker healthcheck (`GET /health`) consistently won the race, producing a single-span trace before the test request's adapter spans flushed to `spans.jsonl`.
- **Fix:** `_poll_for_correlated_spans()` — keep polling until `Counter(trace_id)` shows any trace with ≥2 spans. `_poll_for_trace_spans(min_spans=3)` for multi-adapter services. Propagated to all seven test files.

---

#### BUG-19 · Medium · `items-cached` · Dual-adapter test returned before Redis span arrived

- **Symptom:** `test_both_adapters_produce_spans_under_one_trace` failed with `dominant_count=2` (HTTP + Postgres only).
- **Root cause:** Same early-return poll race as BUG-18; Redis cache span flushed in a later batch.
- **Fix:** `_poll_for_trace_spans(before_ids, min_spans=3)` — wait for HTTP + Postgres + Redis on one trace.

---

#### BUG-20 · Medium · Trace ID format normalization

- **Symptom:** Intermittent trace correlation failures when comparing IDs across spans in the same export batch.
- **Root cause:** OTLP JSON export may encode `traceId` as base64 or 32-char hex depending on exporter version/encoding path.
- **Fix:** `_normalize_trace_id()` in every test file — accepts hex or base64, normalises to lowercase 32-char hex before counting.

---

### Scripts and tooling

#### BUG-21 · High · `validate_all.sh` · Stage 8 failures silently ignored

- **Symptom:** Stage 8 pytest failures did not cause `validate_all.sh` to exit non-zero; script printed "All checks passed" despite red pytest output.
- **Root cause:** Stage 8 block ran pytest inside a `( … )` subshell. `fail()`/`exit 1` inside a subshell terminates the subshell only, not the parent script (which had `set -e` on the parent scope only for that subshell's exit code if unhandled — the `if/then` structure swallowed it).
- **Fix:** Removed subshell; `_run_stage8()` calls `pytest … || fail "…"` directly in the main shell process.
- **Architecture link:** AD-16.

---

### Pre-existing issues surfaced during Stage 8 (not introduced by this work)

These were already tracked in README regression tests but blocked live Docker validation until encountered:

| Issue | Service | Symptom | Existing regression test |
|---|---|---|---|
| `PostgresPlugin` missing `table=` / `id_column=` | `items-cached` | `RuntimeError` at first request | `test_postgres_plugin_registered_with_table_name` |
| `created_at=None` on create | `items-cached` | `NotNullViolationError` | `test_create_item_sets_created_at_when_missing` |
| Missing table on fresh DB | `items-postgres` | `UndefinedTableError` | `test_pg_undefined_table_raises_adapter_query_error` |

---

## What was built

### Docker / infrastructure

- **`.docker/collector-config.yaml`** — shared OTel Collector config (see AD-3, AD-4, AD-5, AD-10)
- **`.docker/docker-compose.yml`** — full stack: 4 backends + 7 apps + 7 sidecars (see AD-1, AD-2, AD-9, AD-13)
- **`services/*/Dockerfile`** — one per service; `swap-demo` special-cased (BUG-14)

### Stage 8 integration tests

- **`services/*/tests/test_observability.py`** — 29 tests total:

  | Service | Tests | Extra assertions |
  |---|---|---|
  | `items-postgres` | 4 | HTTP + adapter spans under one trace |
  | `artifacts-mongo` | 4 | same |
  | `cache-redis` | 4 | same |
  | `events-kafka` | 4 | same |
  | `swap-demo` | 4 | `service.name=swap-demo` regardless of backend |
  | `items-cached` | 5 | ≥3 spans (HTTP + Postgres + Redis) on dominant trace |
  | `research-pipeline` | 5 | ≥3 spans (HTTP + Mongo + Redis); collector-failure resilience |

### Scripts and documentation

- **`scripts/validate_all.sh`** — HTTP checks for ports 8001–8007, idempotent `cleanup()`, `_run_stage8()` loop (AD-16, AD-17)
- **`README.md`** — Stage 8 section, sidecar inventory, Option A/B quick start, resilience check

---

## Sidecar inventory

| App service | Collector container | Span volume |
|---|---|---|
| `items-postgres` | `openframe-items-postgres-collector` | `items_postgres_otel_data` |
| `artifacts-mongo` | `openframe-artifacts-mongo-collector` | `artifacts_mongo_otel_data` |
| `cache-redis` | `openframe-cache-redis-collector` | `cache_redis_otel_data` |
| `events-kafka` | `openframe-events-kafka-collector` | `events_kafka_otel_data` |
| `swap-demo` | `openframe-swap-demo-collector` | `swap_demo_otel_data` |
| `items-cached` | `openframe-items-cached-collector` | `items_cached_otel_data` |
| `research-pipeline` | `openframe-research-pipeline-collector` | `research_pipeline_otel_data` |

---

## Verification status (last live run)

| Stage | Result |
|---|---|
| HTTP checks (ports 8001–8007) | All 35 checks passed with stack up |
| Docker stack | 18 containers (7 apps + 7 collectors + 4 backends) healthy after BUG-02 fix |
| Stage 8 per service | `items-postgres` 4/4 after BUG-18 fix; `swap-demo` failed BUG-18 (fixed); `events-kafka` / `research-pipeline` need rebuild after BUG-11/12 |

**To verify end-to-end:**

```bash
docker pull otel/opentelemetry-collector-contrib:latest
docker compose -f .docker/docker-compose.yml up -d --build
docker compose -f .docker/docker-compose.yml up -d --build events-kafka research-pipeline
bash scripts/validate_all.sh
```

**Resilience check:**

```bash
docker stop openframe-research-pipeline-collector
curl http://localhost:8007/health   # must still return 200
```

---

## Out of scope (explicitly rejected)

- Shared gateway collector across multiple services (AD-1)
- Production-grade sampling, tail-based sampling, or remote exporter targets (AD-4)
- CI pipeline wiring for Stage 8 (requires local Docker daemon)
- Upgrading `openframe-core` pin solely to enable traceparent injection (AD-6 — chose test-side workaround instead)

---

## Files touched

**New:** `.docker/collector-config.yaml`, `services/*/Dockerfile`, `services/*/tests/test_observability.py`, `.github/CHANGELOG.md`

**Modified:** `.docker/docker-compose.yml`, `README.md`, `scripts/validate_all.sh`, `services/events-kafka/src/bootstrap/dependencies.py`, `services/research-pipeline/src/bootstrap/dependencies.py`, `services/research-pipeline/src/application/services/pipeline_service.py`, `services/research-pipeline/src/entrypoints/http/routes.py`, `services/research-pipeline/tests/test_observability.py`, `services/swap-demo/src/entrypoints/http/main.py`, `services/swap-demo/src/application/services/swap_item_service.py`, `services/swap-demo/src/entrypoints/http/routes.py`
