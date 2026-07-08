<p align="center">
  <img src="docs/assets/images/banner.png" alt="openframe-local-validation" width="100%" />
</p>

<p align="center">
  <a href="https://github.com/amrit2356/openframe-local-validation-framework"><img src="https://img.shields.io/badge/phase-2-6DB33F?labelColor=1a1a1a" alt="Phase"/></a>
  <a href="https://github.com/amrit2356/openframe-local-validation-framework"><img src="https://img.shields.io/badge/python-3.11%2B-6DB33F?labelColor=1a1a1a" alt="Python versions"/></a>
  <a href="https://github.com/amrit2356/openframe-local-validation-framework/blob/production/LICENSE"><img src="https://img.shields.io/badge/license-MIT-6DB33F?labelColor=1a1a1a" alt="License"/></a>
  <a href="https://furious-meteors.github.io/openframe-core/"><img src="https://img.shields.io/badge/docs-openframe--core-6DB33F?labelColor=1a1a1a" alt="Docs"/></a>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> ·
  <a href="#services">Services</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#wiring-stages">Wiring Stages</a> ·
  <a href="#stage-8-details">Stage 8</a> ·
  <a href="#running-tests">Tests</a> ·
  <a href="#troubleshooting">Troubleshooting</a>
</p>

---

`openframe-local-validation` proves that `openframe-adapters` and `openframe-core` work correctly against real backends. It is not a production service and not a tutorial — it is an engineering validation tool. Each service is the minimal possible FastAPI app that exercises one or more adapters end to end, with a full unit test suite that runs without any real backends.

---

## Quick start

### Option A — Full Docker stack (recommended, includes Stage 8 sidecar telemetry)

```bash
# 0. Pre-pull the collector image once (avoids parallel-pull races when 7 sidecars start)
docker pull otel/opentelemetry-collector-contrib:latest

# 1. Build and start everything — 4 backends + 7 apps + 7 sidecar collectors (18 containers)
docker compose -f .docker/docker-compose.yml up -d --build

# 2. Wait for all services to be healthy (Kafka may take 30–60 s on first boot)
docker compose -f .docker/docker-compose.yml ps

# 3. Run the full validation suite — 35 HTTP checks + 29 Stage 8 telemetry tests
bash scripts/validate_all.sh
```

After changing service code (especially `bootstrap/dependencies.py`), rebuild affected containers:

```bash
docker compose -f .docker/docker-compose.yml up -d --build events-kafka research-pipeline swap-demo
```

**Stack layout:** 4 infrastructure backends (Postgres, Mongo, Redis, Kafka) · 7 FastAPI app containers (ports 8001–8007) · 7 OTel Collector sidecars (one per app, no shared gateway). See [Stage 8 details](#stage-8-details) and [`.github/CHANGELOG.md`](.github/CHANGELOG.md) for architecture decisions and the full bug/fix history from live validation.

### Option B — Host services, Docker backends only

```bash
# 1. Start infrastructure backends only
docker compose -f .docker/docker-compose.yml up -d postgres mongo redis kafka

# 2. Install and start each service in a separate terminal
cd services/items-postgres    && pip install -e ".[dev]" && uvicorn src.entrypoints.http.main:app --port 8001 --reload
cd services/artifacts-mongo   && pip install -e ".[dev]" && uvicorn src.entrypoints.http.main:app --port 8002 --reload
cd services/cache-redis       && pip install -e ".[dev]" && uvicorn src.entrypoints.http.main:app --port 8003 --reload
cd services/events-kafka      && pip install -e ".[dev]" && uvicorn src.entrypoints.http.main:app --port 8004 --reload
cd services/swap-demo         && pip install -e ".[dev]" && uvicorn entrypoints.http.main:app   --port 8005 --reload
cd services/items-cached      && pip install -e ".[dev]" && uvicorn src.entrypoints.http.main:app --port 8006 --reload
cd services/research-pipeline && pip install -e ".[dev]" && uvicorn src.entrypoints.http.main:app --port 8007 --reload

# 3. Run HTTP validation (Stage 8 telemetry tests are skipped without sidecar containers)
bash scripts/validate_all.sh
```

---

## Services

| Service | Port | Stage | Adapters | What it validates |
|---|---|---|---|---|
| `items-postgres` | 8001 | 1 + 8 | `openframe-adapters-db-postgres` | `PostgresRepository[T]` CRUD · asyncpg COPY bulk · filtered query · sidecar OTLP |
| `artifacts-mongo` | 8002 | 1 + 8 | `openframe-adapters-db-mongo` | `MongoRepository[T]` CRUD · `$in` tag filter · regex search · sidecar OTLP |
| `cache-redis` | 8003 | 1 + 8 | `openframe-adapters-db-redis` | `RedisRepository[T]` · `EXPIRE` TTL · `PIPELINE` stats · sidecar OTLP |
| `events-kafka` | 8004 | 1 + 8 | `openframe-adapters-queue-kafka` | `KafkaProducer[T]` · `KafkaConsumer[T]` · keyed publish · sidecar OTLP |
| `swap-demo` | 8005 | 1 + 8 | Postgres **or** Mongo | Adapter swap via `PERSISTENCE_BACKEND` · sidecar OTLP |
| `items-cached` | 8006 | 2 + 8 | Postgres + Redis | Cache-aside · two-plugin `PluginRegistry` · dual-adapter trace pooling |
| `research-pipeline` | 8007 | 2 + 8 | Mongo + Redis + Kafka | Three-adapter orchestration via `ApplicationBootstrap` · triple-adapter trace pooling · sidecar OTLP |

**Stage 1** — single adapter, `lru_cache` wiring or `PluginRegistry` with one plugin.  
**Stage 2** — multiple adapters simultaneously. `items-cached` uses `PluginRegistry` directly; `research-pipeline` uses `ApplicationBootstrap` (see below) — the recommended composition root as of openframe-core 3.1.0, wrapping `PluginRegistry` with a structured `configure → start → stop` lifecycle and correct shutdown ordering.  
**Stage 8** — sidecar telemetry: every service has its own OTel Collector sidecar (not a shared gateway), real OTLP round-trip, file-based span assertions proving resource attributes survive end-to-end.

**`research-pipeline` and `ApplicationBootstrap`** — research-pipeline is the canonical proof of `ApplicationBootstrap`'s multi-adapter lifecycle, migrated ahead of `openframe-cli` scaffolding it as the default. `src/bootstrap/app.py` defines `ResearchPipelineApp(ApplicationBootstrap)`, registering Mongo → Redis → Kafka in `configure()`. This one service now demonstrates, in combination, everything Stage 8 validates:
  a. `ApplicationBootstrap`'s `configure → start → stop` lifecycle, including LIFO port shutdown and aggregated `health()`
  b. `shutdown_telemetry()` integration inside `ApplicationBootstrap.stop()` — spans emitted during port shutdown are flushed before the TracerProvider itself is torn down
  c. The sidecar collector receiving real spans over a real OTLP network round-trip (`test_ingest_produces_spans_with_single_trace_id`, `test_ingest_produces_http_and_adapter_spans`)
  d. Collector failure injection — the sidecar container is actually stopped mid-test to prove the bounded `BatchSpanProcessor` queue drops spans rather than blocking or crashing the pipeline (`test_bounded_queue_drop_not_crash_on_collector_failure`)

---

## Architecture

Every service follows the DDD-lite hexagonal structure from the OpenFrame architectural spec:

```
src/
├── domain/              ← Pydantic entity — zero infrastructure imports
├── application/
│   ├── ports/           ← Protocol (structural subtyping) — adapter-agnostic contract
│   └── services/        ← business logic — depends only on port, never on adapter
├── adapters/outbound/   ← openframe adapter subclass — only file that touches drivers
├── entrypoints/http/    ← FastAPI routes + lifespan
└── bootstrap/           ← dependencies.py (composition root — wires adapter → service)
```

### Hexagonal boundary

```
HTTP request
    │
    ▼
routes.py            ← speaks domain language (ItemService, SwapItemService, …)
    │
    ▼
*Service             ← depends on Port (Protocol) — never sees an adapter
    │
    ▼
TracingProxy         ← zero-code OTel spans on every repository/producer method
    │
    ▼
*Repository / *Producer   ← domain subclass — _row_to_entity(), _doc_to_entity(), _serialise()
    │
    ▼
PostgresRepository[T] / MongoRepository[T] / RedisRepository[T] / KafkaProducer[T]
    │
    ▼
asyncpg / motor / redis.asyncio / aiokafka
```

Three rules enforced by architecture tests in every service:

1. `domain/` and `application/` **never** import from `openframe.adapters`
2. `adapters/outbound/` is the **only** layer that imports driver-level code
3. `bootstrap/dependencies.py` is the **only** file that wires adapters to services

---

## Wiring stages

### Stage 1 — single adapter (`lru_cache` or single-plugin `PluginRegistry`)

Used by: `items-postgres`, `artifacts-mongo`, `cache-redis`, `events-kafka`, `swap-demo`

```python
# bootstrap/dependencies.py — items-postgres pattern
@lru_cache(maxsize=1)
def _get_repository() -> ItemPostgresRepository:
    return ItemPostgresRepository(PostgresSettings())

def get_item_service() -> ItemService:
    return ItemService(TracingProxy(_get_repository(), prefix="repository.item"))
```

### Stage 2 — multiple adapters (`PluginRegistry`)

Used by: `items-cached`

```python
# bootstrap/dependencies.py — items-cached pattern
async def initialise() -> None:
    global _registry
    _registry = PluginRegistry()
    _registry.register(PostgresPlugin(PostgresSettings(), table="items", id_column="id",
                                       repository_class=ItemPostgresRepository))
    _registry.register(RedisPlugin(RedisSettings()))
    await _registry.initialize_all()   # starts both in registration order

def get_item_service() -> ItemCachedService:
    persistence = TracingProxy(_registry.get("persistence").get_repository(), ...)
    cache       = TracingProxy(_registry.get("cache").get_repository(), ...)
    return ItemCachedService(persistence=persistence, cache=cache)
```

`PluginRegistry` guarantees:
- Initialisation in registration order
- Shutdown in reverse order (LIFO)
- Aggregated health via `health_all()`
- Capability-keyed lookup (`"persistence"`, `"cache"`, `"queue"`)

### Stage 2 — multiple adapters (`ApplicationBootstrap`)

Used by: `research-pipeline`

As of openframe-core 3.1.0, `ApplicationBootstrap` (in `openframe.core.runtime`) is the recommended composition root for multi-adapter services — it wraps `PluginRegistry` with a structured `configure → start → stop` lifecycle and handles shutdown ordering automatically: ports are shut down first (LIFO), then `shutdown_telemetry()` flushes the OTel SDK so spans emitted during port shutdown are not silently dropped.

```python
# bootstrap/app.py — research-pipeline pattern
class ResearchPipelineApp(ApplicationBootstrap):
    def configure(self) -> None:
        self.register(MongoPlugin(MongoSettings(), collection="artifacts",
                                   repository_class=ArtifactMongoRepository))
        self.register(RedisPlugin(RedisSettings()))
        self.register(KafkaPlugin(KafkaSettings(), producer_class=ArtifactEventProducer))

    async def stop(self) -> None:
        await self.stop_consumer()
        await super().stop()          # shuts down ports LIFO, flushes telemetry
        from openframe.core.telemetry import shutdown_telemetry
        shutdown_telemetry()          # after super().stop() — captures shutdown-time spans too

# bootstrap/dependencies.py — FastAPI Depends() layer, reads from the app instance
_app = ResearchPipelineApp()

def get_pipeline_service() -> ResearchPipelineService:
    persistence = TracingProxy(_app.get(Capability.PERSISTENCE).get_repository(), ...)
    cache       = TracingProxy(_app.get(Capability.CACHE).get_repository(), ...)
    return ResearchPipelineService(persistence=persistence, cache=cache, ...)
```

`ApplicationBootstrap` guarantees the same ordering/health/capability-lookup behaviour as `PluginRegistry` (which it wraps), plus:
- A single `start()`/`stop()` entry point instead of manually sequencing `initialize_all()`/`shutdown_all()`
- `Capability`-typed lookup (`Capability.PERSISTENCE` etc.) instead of raw strings
- Guaranteed `shutdown_telemetry()` on every `stop()`, so services can't forget to flush spans

### Stage 8 — sidecar telemetry validation (all services)

Scope: proves that real spans produced by `TelemetryMiddleware` and `TracingProxy` survive a complete **OTLP serialize → transmit → collect → file** round-trip against a real OpenTelemetry Collector process — not just `InMemorySpanExporter`. **Every service has its own dedicated sidecar — no shared gateway tier.**

See [Stage 8 details](#stage-8-details) for architecture decisions, test mechanics, and troubleshooting. Full bug IDs and decision log: [`.github/CHANGELOG.md`](.github/CHANGELOG.md).

**Mechanism — one sidecar per service, no shared gateway**

Each `<service>-collector` uses `network_mode: "service:<service>"` in docker-compose. This shares the app container's network namespace so that `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318` inside the app resolves directly to the sidecar's listener — no extra network hop.

```
<any-service> container
  ├── app process   → BatchSpanProcessor → OTLP/HTTP → localhost:4318
  └── (shared loopback)
<any-service>-collector container  (network_mode: "service:<any-service>")
  └── OTLP receiver on 0.0.0.0:4318 → batch (1s) → file + debug exporters
      └── /var/otel/spans.jsonl  (isolated named volume per service)
```

A single shared `.docker/collector-config.yaml` is bind-mounted read-only into every sidecar. Config is shared; **data volumes are isolated** per service.

**Cold-start note:** `network_mode: "service:X"` requires `X` to be running first, so the collector always starts *after* the app. A few spans produced during those initial seconds are dropped by the SDK's bounded queue. This is expected — **bounded loss, never blocking**. Apps keep serving traffic regardless of collector availability. You may see `Failed to export traces … Connection refused` in app logs for a few seconds after `docker compose up` — this is normal.

**What Stage 8 proves per service**

| Assertion | What it validates |
|---|---|
| At least one trace in the request delta has ≥2 correlated spans | `TelemetryMiddleware` (HTTP) and `TracingProxy` (adapter) both export into the same trace through the real collector |
| Every span's resource carries correct `service.name` | Resource attributes survive the full serialize/transmit/collect round-trip |
| `items-cached`: dominant trace has ≥3 spans | Postgres + Redis dual-adapter pooling holds through the sidecar, not just in-memory |
| `research-pipeline`: dominant trace has ≥3 spans | Mongo + Redis (+ Kafka when wrapped) multi-adapter pooling through the sidecar |
| Test fails loudly if collector container is not running | Prevents vacuously-true "zero spans found" passes |
| App `/health` returns 200 after collector is stopped | Export failure does not block the request path |

**Sidecar inventory**

| Service | Collector container | Shared config | Isolated volume |
|---|---|---|---|
| `items-postgres` | `openframe-items-postgres-collector` | `.docker/collector-config.yaml` | `items_postgres_otel_data` |
| `artifacts-mongo` | `openframe-artifacts-mongo-collector` | `.docker/collector-config.yaml` | `artifacts_mongo_otel_data` |
| `cache-redis` | `openframe-cache-redis-collector` | `.docker/collector-config.yaml` | `cache_redis_otel_data` |
| `events-kafka` | `openframe-events-kafka-collector` | `.docker/collector-config.yaml` | `events_kafka_otel_data` |
| `swap-demo` | `openframe-swap-demo-collector` | `.docker/collector-config.yaml` | `swap_demo_otel_data` |
| `items-cached` | `openframe-items-cached-collector` | `.docker/collector-config.yaml` | `items_cached_otel_data` |
| `research-pipeline` | `openframe-research-pipeline-collector` | `.docker/collector-config.yaml` | `research_pipeline_otel_data` |

**Resilience check (manual, any service)**

```bash
docker stop openframe-research-pipeline-collector
curl http://localhost:8007/health   # must still return 200
```

Confirms that `BatchSpanProcessor`'s bounded queue drops spans on export failure rather than blocking the calling thread.

**Out of scope for Stage 8**

- A shared gateway collector across multiple services (explicitly rejected — sidecar-per-service is the chosen design).
- A real tracing backend (Jaeger, Tempo, Grafana). File-based assertion is sufficient to prove the mechanism; swapping the exporter target is a one-line config change.
- CI wiring — Stage 8 requires a local Docker daemon and running collector containers.

---

## Stage 8 details

### Architecture decisions

| Decision | Choice | Rationale |
|---|---|---|
| Collector topology | **One sidecar per service** | Mirrors production sidecar pattern; isolates failure domains; proves `localhost:4318` wiring |
| Sidecar networking | `network_mode: "service:<app>"` | Zero-hop OTLP from app to collector on shared loopback |
| Collector config | **Single shared** `.docker/collector-config.yaml` | Identical pipeline for all services; avoids config drift |
| Span storage | **Isolated named volume** per sidecar | Tests never read another service's spans |
| Test input | **File exporter** (`spans.jsonl`) | Deterministic, no extra infra; Jaeger/Tempo out of scope |
| Span read path | **`docker cp`**, not `docker exec` | Collector image has no shell (`/bin/sh` missing) |
| Collector user | `user: "0"` (root) | Named volumes are root-owned; default collector user cannot write spans file |
| Kafka in Docker | Dual listener: `localhost:9092` + `kafka:29092` | Host Option B and container Option A both work |
| Test trace isolation | **Span-ID delta polling** | Snapshot `spanId` set before request; assert on new spans only |
| Trace correlation | **Correlated polling** (≥2 or ≥3 spans per trace) | Healthchecks and prior HTTP traffic add noise; strict single-trace assertions false-fail |
| Traceparent injection | **Not used** | Installed `openframe-core` pin does not extract incoming W3C headers in this environment |
| Producer telemetry | **`TracingProxy` on all producers** | Kafka producers must be wrapped at composition root or Stage 8 sees HTTP span only |
| Option B workflow | Stage 8 **skipped** when sidecars absent | Host-run uvicorn still gets HTTP validation from `validate_all.sh` |

### Collector pipeline

`.docker/collector-config.yaml`:

```
OTLP/HTTP :4318  →  batch (timeout: 1s, size: 512)  →  file (/var/otel/spans.jsonl, JSON)
                                                      →  debug (docker compose logs)
```

No `file_storage` extension — it caused startup crashes when `/var/otel/queue` did not exist and is not required by the file exporter.

### How `test_observability.py` works

Each service has 4–5 integration tests in `services/<service>/tests/test_observability.py` (29 tests total). All require the full Docker stack with that service's collector running.

1. **`test_collector_is_running`** — fails immediately if `openframe-<service>-collector` is not in `docker ps`. Prevents vacuous passes.
2. **Trigger a real request** — POST/GET to a domain endpoint (not `/health`), e.g. `POST /items`, `POST /artifacts`.
3. **Snapshot span IDs** — read all spans from the collector file; record existing `spanId` values.
4. **Poll for correlated spans** — re-read the file every 0.5 s (30 s timeout). Do **not** return on the first new span (that is almost always a Docker healthcheck). Wait until at least one trace in the delta has ≥2 spans (HTTP + adapter), or ≥3 for `items-cached` / `research-pipeline`.
5. **Read spans via `docker cp`** — copy `/var/otel/spans.jsonl` to a temp file locally; parse OTLP JSON export format.
6. **Assert `service.name`** — every span's resource must carry the expected `OTEL_SERVICE_NAME`.

```bash
# Run Stage 8 for one service
cd services/swap-demo && pytest tests/test_observability.py -v

# Inspect spans manually
docker cp openframe-swap-demo-collector:/var/otel/spans.jsonl /tmp/spans.jsonl
docker compose -f .docker/docker-compose.yml logs swap-demo-collector
```

### Telemetry wiring requirements

For Stage 8 to pass, every service must have:

| Layer | Requirement |
|---|---|
| `main.py` lifespan | `setup_telemetry()` called before handling requests |
| FastAPI app | `TelemetryMiddleware` registered |
| `bootstrap/dependencies.py` | Every repository **and producer** wrapped in `TracingProxy` |
| Docker env | `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318`, `OTEL_SERVICE_NAME=<service>` |
| Sidecar | Matching `<service>-collector` running with shared config mounted |

`swap-demo` was missing telemetry wiring entirely (fixed). `events-kafka` and `research-pipeline` had repositories wrapped but Kafka producers unwrapped (fixed — **rebuild containers** after pulling latest code).

### Service code fixes from Stage 8 validation

| Service | Issue | Fix |
|---|---|---|
| `swap-demo` | No `setup_telemetry()` / `TelemetryMiddleware` | Added to `main.py` |
| `swap-demo` | `GET /items` 500 — wrong `list()` signature / tuple unpack | Fixed service + routes |
| `events-kafka` | No adapter spans — producer not traced | `TracingProxy` on producer |
| `research-pipeline` | Kafka spans missing — producer not traced | `TracingProxy` on producer |
| `research-pipeline` | No DELETE endpoint for validation script | Added `DELETE /artifacts/{id}` |

---

## Troubleshooting

Common issues discovered during live Docker validation. Full write-up with bug IDs: [`.github/CHANGELOG.md`](.github/CHANGELOG.md).

### Collector containers exit immediately

| Symptom | Cause | Fix |
|---|---|---|
| `permission denied` on `spans.jsonl` | Default collector user cannot write to named volume | Collectors run as `user: "0"` in compose — pull latest compose file |
| `file_storage: directory must exist` | Old config with unused `file_storage` extension | Use current `.docker/collector-config.yaml` (no extensions block) |

```bash
docker compose -f .docker/docker-compose.yml logs items-postgres-collector
docker compose -f .docker/docker-compose.yml up -d --force-recreate items-postgres-collector
```

### Stage 8 test: only `HTTP GET /health` in span delta

**Symptom:** `AssertionError: No trace_id has ≥2 correlated spans … Span names: ['HTTP GET /health']`

**Cause:** Docker healthchecks produce a lone HTTP span before your test request's adapter spans flush. Old poll logic returned on the first new span.

**Fix:** Use current `test_observability.py` with `_poll_for_correlated_spans()` / `_poll_for_trace_spans(min_spans=N)`.

### Stage 8 test: collector not running

**Symptom:** `Failed: Collector 'openframe-<service>-collector' is not running.`

**Fix:**

```bash
docker compose -f .docker/docker-compose.yml up -d
docker compose -f .docker/docker-compose.yml ps | grep collector
```

Option B (host services) does not start sidecars — Stage 8 is skipped by design.

### HTTP 500 on Postgres services inside Docker

| Symptom | Cause | Fix |
|---|---|---|
| Connection errors | `DATABASE_URL` used `postgresql+asyncpg://` | Compose uses plain `postgresql://` |
| `relation "swap_items" does not exist` | Postgres volume predates init script | `CREATE TABLE` manually or `docker volume rm` and recreate |

```bash
docker exec openframe-postgres psql -U openframe -d openframe -c \
  "CREATE TABLE IF NOT EXISTS swap_items (id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());"
```

### Kafka services cannot connect inside Docker

**Symptom:** `AdapterConnectionError` from containerised `events-kafka` or `research-pipeline`.

**Cause:** Bootstrap pointed at `localhost:9092` — inside a container, that is not the Kafka broker.

**Fix:** Container env uses `KAFKA_BOOTSTRAP_SERVERS=kafka:29092` (INTERNAL listener). Wait 30–60 s after first Kafka boot for KRaft controller election.

### Stage 8: HTTP span only, no adapter span

**Cause:** Outbound port not wrapped in `TracingProxy` at the composition root (common on Kafka producers).

**Fix:** Wrap in `bootstrap/dependencies.py`, then rebuild:

```bash
docker compose -f .docker/docker-compose.yml up -d --build events-kafka research-pipeline
```

### `validate_all.sh` reports pass but pytest failed

**Cause:** Early Stage 8 block ran pytest inside a subshell where `exit 1` did not propagate.

**Fix:** Current script uses `_run_stage8()` with `pytest … \|\| fail` in the main shell.

### Parallel collector image pull failures

```bash
docker pull otel/opentelemetry-collector-contrib:latest
docker compose -f .docker/docker-compose.yml up -d
```

### Persistent data / idempotent re-runs

`validate_all.sh` calls `cleanup()` (silent DELETE) before creates so re-runs work against persistent volumes. If duplicate-key errors persist, delete stale resources manually or reset volumes:

```bash
docker compose -f .docker/docker-compose.yml down -v   # destroys all data volumes
```

### Adapter swap — `swap-demo`

`swap-demo` is the clearest proof of the hexagonal contract. `PERSISTENCE_BACKEND` selects the adapter at startup — no code changes anywhere else:

```bash
PERSISTENCE_BACKEND=postgres uvicorn entrypoints.http.main:app --port 8005
PERSISTENCE_BACKEND=mongo    uvicorn entrypoints.http.main:app --port 8005
```

Both backends return identical HTTP behaviour through the same routes, the same service, and the same port. Only `bootstrap/dependencies.py` and the two adapter files know which backend is active.

---

## What each service proves

### `items-postgres` — Stage 1 · Postgres only · Stage 8 sidecar

- `PostgresSettings` reads `DATABASE_URL` from env; fails fast on missing config
- asyncpg pool creation, caching, and connection lifecycle against real Postgres
- `_row_to_entity()` / `_entity_to_row()` on real `asyncpg.Record` objects
- Full CRUD: `create()` → `get()` → `list()` → `update()` → `delete()`
- **Niche 1:** asyncpg `COPY` protocol for bulk insert — 10× faster than individual INSERTs (`bulk_import`)
- **Niche 2:** raw asyncpg parameterised filtered query (`find_by_status`)
- `TracingProxy` produces real OTel spans; `TelemetryMiddleware` instruments HTTP
- **Stage 8:** `items-postgres-collector` sidecar; `tests/test_observability.py` asserts spans via real OTLP round-trip

### `artifacts-mongo` — Stage 1 · MongoDB only · Stage 8 sidecar

- `MongoSettings` reads `MONGO_URL` and `MONGO_DATABASE` from env
- Motor lazy connection and `_id` ↔ domain `id` string conversion against real MongoDB
- `EmbeddingStatus` enum lifecycle — preview of Research Vault Phase 1
- **Niche 1:** MongoDB `$in` operator for tag filtering (`filter_by_tags`)
- **Niche 2:** case-insensitive regex search across title, abstract, and source (`search`)
- Uses `_get_collection()` for raw motor access inside the adapter subclass
- **Stage 8:** `artifacts-mongo-collector` sidecar; correlated HTTP + Mongo adapter spans

### `cache-redis` — Stage 1 · Redis only · Stage 8 sidecar

- `RedisSettings` reads `REDIS_URL` from env
- JSON serialisation/deserialisation round-trip with configurable TTL and key prefix
- `SET NX` create · `SET XX` update · `SCAN ITER` key pagination
- **Niche 1:** `EXPIRE` command for TTL extension (`extend_ttl`)
- **Niche 2:** Redis `PIPELINE` for atomic multi-command stats aggregation (`get_stats`)
- `RedisPlugin.capability = "cache"` — validated as the cache tier, not persistence
- **Stage 8:** `cache-redis-collector` sidecar; correlated HTTP + Redis adapter spans

### `events-kafka` — Stage 1 · Kafka only · Stage 8 sidecar

- `KafkaSettings` reads `KAFKA_BOOTSTRAP_SERVERS` from env
- `KafkaProducer.start()` connects to real Kafka KRaft broker (no ZooKeeper)
- JSON → bytes serialisation with broker delivery acknowledgement
- **Niche 1:** keyed publish for deterministic partition routing (`publish_keyed`)
- **Niche 2:** topic metadata via raw aiokafka producer introspection (`get_topic_metadata`)
- Background `asyncio.Task` consumer — observable via `GET /events/received`
- Graceful degraded startup when Kafka is not yet ready (`AdapterConnectionError` caught in lifespan)
- **Stage 8:** `TracingProxy` on Kafka producer (`prefix="queue.event"`) required for adapter spans; containerised services use `kafka:29092` bootstrap

### `swap-demo` — Stage 1 · Postgres **or** Mongo (swappable) · Stage 8 sidecar

- Selects `PostgresSwapRepository` or `MongoSwapRepository` at startup via `PERSISTENCE_BACKEND`
- Both adapters extend `PostgresRepository[SwapItem]` / `MongoRepository[SwapItem]` — not hand-rolled
- `save()` UPSERT implemented as a domain-specific custom method on each adapter subclass
- Identical `SwapItemService` and routes regardless of backend — zero code change on swap
- `/info` reports the active backend; `/items` CRUD behaves identically for both
- Architecture tests enforce the boundary: only `adapters/outbound/` and `bootstrap/` see `openframe.adapters`
- **Stage 8:** `TelemetryMiddleware` and `setup_telemetry()` added (previously missing); `swap-demo-collector` sidecar; `test_observability.py` asserts `service.name=swap-demo` regardless of the active backend

### `items-cached` — Stage 2 · Postgres + Redis · Stage 8 sidecar

- **The canonical Stage 2 service** — two adapters, one `PluginRegistry`
- `capability="persistence"` (Postgres) and `capability="cache"` (Redis) coexist without collision
- Cache-aside read pattern: Redis first → on miss, read Postgres and populate Redis
- Cache invalidation on write: `update_item()` and `delete_item()` delete the Redis key
- `create_item()` stamps `created_at` at the service layer before persisting — not delegated to DB default
- Graceful degradation: Redis failures never surface to the caller; Postgres remains the source of truth
- `health_all()` reports both plugins' health independently
- **Stage 8:** `items-cached-collector` sidecar; `test_observability.py` asserts ≥3 spans (HTTP + Postgres + Redis) under one trace_id — proving two-adapter pooling through the real sidecar

### `research-pipeline` — Stage 2 · Mongo + Redis + Kafka · `ApplicationBootstrap` · Stage 8 sidecar telemetry

- **The most complete Stage 2 service** — three adapters, three capabilities, one `ApplicationBootstrap` subclass (`ResearchPipelineApp` in `src/bootstrap/app.py`)
- Registration and initialisation order: Mongo → Redis → Kafka (persistence must be ready before caching, caching before events)
- Shutdown order: Kafka → Redis → Mongo (LIFO, handled by `ApplicationBootstrap.stop()`), then `shutdown_telemetry()` flushes the OTel SDK last of all
- Three-step ingest flow: `store (Mongo)` → `publish event (Kafka)` → `cache status (Redis)`
- Redis-first status lookup: `get_status()` checks Redis sub-millisecond cache; falls back to MongoDB on miss
- Background `asyncio.Task` Kafka consumer, lifecycle owned by `ResearchPipelineApp.start_consumer()`/`stop_consumer()`, updates embedding status in MongoDB and invalidates Redis cache
- `repository_class=` / `producer_class=` on each plugin registration ensures `get_repository()` / `get_producer()` returns the domain subclass — not the plain base class
- **Stage 8:** sidecar on shared network namespace; `TracingProxy` on Mongo, Redis, **and Kafka producer**; tests assert ≥3 correlated spans and genuine collector-failure resilience — `test_bounded_queue_drop_not_crash_on_collector_failure` actually stops the sidecar container mid-test and confirms the pipeline keeps serving traffic

---

## Running tests

Each service has a full unit test suite. **Zero network calls** — all adapter interactions are mocked via `unittest.mock.AsyncMock`.

```bash
cd services/items-postgres    && pytest tests/ -v   # 57 tests
cd services/artifacts-mongo   && pytest tests/ -v   # 38 tests
cd services/cache-redis       && pytest tests/ -v   # 31 tests
cd services/events-kafka      && pytest tests/ -v   # 26 tests
cd services/swap-demo         && pytest tests/ -v   # 25 tests
cd services/items-cached      && pytest tests/ -v   # 60 tests
cd services/research-pipeline && pytest tests/ -v   # 67 tests  (unit, zero network)
```

**Total: 304 unit tests, zero network calls.**

**Stage 8 integration tests** (require the full docker-compose stack — all sidecars, 29 tests total):

```bash
# Pre-pull collector image (recommended)
docker pull otel/opentelemetry-collector-contrib:latest

# Start full stack
docker compose -f .docker/docker-compose.yml up -d --build

# Run Stage 8 per service:
cd services/items-postgres    && pytest tests/test_observability.py -v   # 4 tests
cd services/artifacts-mongo   && pytest tests/test_observability.py -v   # 4 tests
cd services/cache-redis       && pytest tests/test_observability.py -v   # 4 tests
cd services/events-kafka      && pytest tests/test_observability.py -v   # 4 tests
cd services/swap-demo         && pytest tests/test_observability.py -v   # 5 tests (includes backend-flip consistency check)
cd services/items-cached      && pytest tests/test_observability.py -v   # 5 tests (dual-adapter assertion)
cd services/research-pipeline && pytest tests/test_observability.py -v   # 5 tests (collector failure injection + triple-adapter)

# Or run all HTTP + Stage 8 checks:
bash scripts/validate_all.sh
```

Stage 8 tests are **integration tests** — they call real HTTP endpoints and read real collector output via `docker cp`. They are excluded from the 296 unit-test count above.

Test coverage per service:

| Layer | What's tested |
|---|---|
| Domain | Entity defaults · field validation · no infrastructure imports |
| Service | Business logic · port delegation · graceful degradation paths |
| Adapter | Port conformance (`BaseRepository` / `BaseProducer`) · mapping methods · error translation (`AdapterQueryError`, `AdapterTimeoutError`) · niche feature behaviour |
| Routes | Status codes · request/response shapes · 404 / 422 handling · cache-hit vs miss transparency |
| Plugin wiring | `repository_class` / `producer_class` regression · capability taxonomy · multi-plugin coexistence |
| Architecture | AST-level import boundary checks — enforces hexagonal rules at the source level |
| **Stage 8 observability** | Real OTLP round-trip · correlated trace polling · `service.name` resource attributes · collector-failure resilience |

### Regression tests locked in from live validation

Bugs discovered during live Docker validation are locked in as explicit regression tests or documented fixes:

**`items-cached` unit regressions**

| Bug | Regression test |
|---|---|
| `PostgresPlugin` registered without `table=`/`id_column=` → `RuntimeError` at first request | `test_postgres_plugin_registered_with_table_name` |
| `created_at=None` passed to Postgres → `NotNullViolationError` | `test_create_item_sets_created_at_when_missing` |
| `UndefinedTableError` correctly translated to `AdapterQueryError` with cause chaining | `test_pg_undefined_table_raises_adapter_query_error` |

**Stage 8 / Docker stack fixes (see [CHANGELOG](.github/CHANGELOG.md) for full bug IDs)**

| Bug | Where fixed |
|---|---|
| `swap-demo` missing telemetry — zero spans exported | `main.py`: `setup_telemetry()` + `TelemetryMiddleware` |
| `swap-demo` `GET /items` 500 — `list()` signature / tuple unpack | `swap_item_service.py`, `routes.py` |
| Kafka producer spans missing — producer not in `TracingProxy` | `events-kafka` and `research-pipeline` `dependencies.py` |
| Collector permission denied on spans file | `docker-compose.yml`: `user: "0"` on collectors |
| Collector crash on `file_storage` extension | Removed from `.docker/collector-config.yaml` |
| Stage 8 false failure on healthcheck-only span | `_poll_for_correlated_spans()` in all `test_observability.py` files |
| `validate_all.sh` swallowed Stage 8 pytest failures | `_run_stage8()` without subshell |

---

## Backends

```yaml
postgres:  image: postgres:16-alpine           port: 5432
mongo:     image: mongo:7                      port: 27017
redis:     image: redis:7-alpine               port: 6379
kafka:     image: confluentinc/cp-kafka:7.6.0   port: 9092  # KRaft mode, no ZooKeeper
           # Docker-internal bootstrap: kafka:29092 (INTERNAL listener)
```

All credentials default to `openframe / openframe`. The Postgres schema (`items`, `swap_items` tables) is defined in `scripts/init_postgres.sql` and applied on **first** volume creation only.

> **Postgres volume note:** If your `postgres_data` volume predates the `swap_items` table in the init script, run the manual `CREATE TABLE` in [Troubleshooting](#troubleshooting) or recreate the volume.

> **Kafka note:** KRaft mode takes 30–60 s to elect a controller on first boot. Containerised services connect via `kafka:29092`; host-side Option B services use `localhost:9092`. All Kafka-dependent services handle `AdapterConnectionError` at startup and run in degraded mode until the broker is ready.

> **Degraded mode:** every service catches `(AdapterConnectionError, ValidationError)` in its FastAPI lifespan. If a backend is unreachable at startup the service logs a warning and continues serving traffic — this is intentional and tested behaviour, not a silent failure.

> **Changelog:** Full Stage 8 architecture decision log (AD-1–AD-17) and bug report (BUG-01–BUG-21): [`.github/CHANGELOG.md`](.github/CHANGELOG.md).

---

## Ecosystem

| Package | Description |
|---|---|
| [`openframe-core`](https://github.com/Furious-Meteors/openframe-core) | Exceptions · ports · telemetry · middleware · `PluginRegistry` — foundation for the entire ecosystem |
| [`openframe-adapters`](https://github.com/Furious-Meteors/openframe-adapters) | DB + queue adapters — Postgres · MongoDB · Redis · Kafka |
| [`openframe-protocol`](https://github.com/Furious-Meteors/openframe-protocol) | WebSocket · SSE · gRPC · MCP · webhooks |
| [`openframe-infra`](https://github.com/Furious-Meteors/openframe-infra) | Storage · auth · secrets · observability · feature flags |
| [`openframe-ai`](https://github.com/Furious-Meteors/openframe-ai) | LangChain · LlamaIndex · CrewAI · model serving |

---

## License

MIT — see [LICENSE](LICENSE).
