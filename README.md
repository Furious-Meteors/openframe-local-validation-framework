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
  <a href="#running-tests">Tests</a>
</p>

---

`openframe-local-validation` proves that `openframe-adapters` and `openframe-core` work correctly against real backends. It is not a production service and not a tutorial — it is an engineering validation tool. Each service is the minimal possible FastAPI app that exercises one or more adapters end to end, with a full unit test suite that runs without any real backends.

---

## Quick start

```bash
# 1. Start all backends
docker compose up -d

# 2. Wait for all backends to be healthy
docker compose ps

# 3. Install and start each service in a separate terminal
cd services/items-postgres    && pip install -e ".[dev]" && uvicorn src.entrypoints.http.main:app --port 8001 --reload
cd services/artifacts-mongo   && pip install -e ".[dev]" && uvicorn src.entrypoints.http.main:app --port 8002 --reload
cd services/cache-redis       && pip install -e ".[dev]" && uvicorn src.entrypoints.http.main:app --port 8003 --reload
cd services/events-kafka      && pip install -e ".[dev]" && uvicorn src.entrypoints.http.main:app --port 8004 --reload
cd services/swap-demo         && pip install -e ".[dev]" && uvicorn entrypoints.http.main:app   --port 8005 --reload
cd services/items-cached      && pip install -e ".[dev]" && uvicorn src.entrypoints.http.main:app --port 8006 --reload
cd services/research-pipeline && pip install -e ".[dev]" && uvicorn src.entrypoints.http.main:app --port 8007 --reload

# 4. Run the full validation suite (covers ports 8001–8007, Stage 8 requires docker stack)
bash scripts/validate_all.sh
```

---

## Services

| Service | Port | Stage | Adapters | What it validates |
|---|---|---|---|---|
| `items-postgres` | 8001 | 1 | `openframe-adapters-db-postgres` | `PostgresRepository[T]` CRUD · asyncpg COPY bulk · filtered query |
| `artifacts-mongo` | 8002 | 1 | `openframe-adapters-db-mongo` | `MongoRepository[T]` CRUD · `$in` tag filter · regex search |
| `cache-redis` | 8003 | 1 | `openframe-adapters-db-redis` | `RedisRepository[T]` · `EXPIRE` TTL · `PIPELINE` stats |
| `events-kafka` | 8004 | 1 | `openframe-adapters-queue-kafka` | `KafkaProducer[T]` · `KafkaConsumer[T]` · keyed publish · background consumer |
| `swap-demo` | 8005 | 1 | Postgres **or** Mongo | Adapter swap via `PERSISTENCE_BACKEND` — same service, two backends |
| `items-cached` | 8006 | 2 | Postgres + Redis | Cache-aside pattern · `PluginRegistry` two-plugin wiring |
| `research-pipeline` | 8007 | 2 + 8 | Mongo + Redis + Kafka | Three-adapter orchestration · Redis-first status · background consumer · **sidecar telemetry** |

**Stage 1** — single adapter, `lru_cache` wiring or `PluginRegistry` with one plugin.  
**Stage 2** — multiple adapters simultaneously, `PluginRegistry` managing initialisation order, LIFO shutdown, and `health_all()`.  
**Stage 8** — sidecar telemetry validation: one OTel Collector per service (sidecar, not gateway), real OTLP round-trip, file-based span assertions.

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

Used by: `items-cached`, `research-pipeline`

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
- Initialisation in registration order (Postgres → Redis in `items-cached`; Mongo → Redis → Kafka in `research-pipeline`)
- Shutdown in reverse order (LIFO)
- Aggregated health via `health_all()`
- Capability-keyed lookup (`"persistence"`, `"cache"`, `"queue"`)

### Stage 8 — sidecar telemetry validation (`research-pipeline`)

Scope: proves that real spans produced by `TelemetryMiddleware` and `TracingProxy` survive a complete OTLP serialize → transmit → collect → file round-trip against a real collector process, not just `InMemorySpanExporter`.

**Mechanism — one sidecar per service, no shared gateway**

`research-pipeline-collector` uses `network_mode: "service:research-pipeline"` in docker-compose. This shares `research-pipeline`'s network namespace so that `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318` inside the app resolves directly to the sidecar's listener — no extra network hop, no shared gateway tier.

```
research-pipeline container
  ├── app process   → BatchSpanProcessor → OTLP/HTTP → localhost:4318
  └── (shared loopback)
research-pipeline-collector container (network_mode: "service:research-pipeline")
  └── OTLP receiver on 0.0.0.0:4318 → batch processor → file exporter → /var/otel/spans.jsonl
```

**Cold-start note:** `network_mode: "service:X"` requires `X` to be running first, so the collector starts *after* the app. A few spans produced during those initial seconds are dropped by the SDK's bounded queue. This is expected and acceptable — the design is "bounded loss, never blocking". The app keeps serving traffic regardless of collector availability.

**What Stage 8 proves**

| Assertion | What it validates |
|---|---|
| All spans from one request share one `trace_id` | Multi-adapter pooling (Mongo + Redis) holds through a real collector, not just in-memory |
| Spans include HTTP server span + `repository.artifact.mongo.*` + `repository.artifact.redis.*` | Full pipeline is instrumented end-to-end via `TelemetryMiddleware` and `TracingProxy` |
| Every span's resource carries `service.name=research-pipeline` | Resource attributes survive the full serialize/transmit/collect round-trip |
| Test fails loudly if collector container is not running | Prevents vacuously-true "zero spans found" passes |

**Running Stage 8 tests**

```bash
# Start the full stack including the sidecar
docker compose -f .docker/docker-compose.yml up -d

# Run Stage 8 integration tests (requires live stack)
cd services/research-pipeline
pytest tests/test_observability.py -v
```

**Resilience check (manual)**

```bash
# Kill the collector mid-run — pipeline must keep serving traffic
docker stop openframe-research-pipeline-collector
curl http://localhost:8007/health   # must still return 200
```

Confirms that `BatchSpanProcessor`'s bounded queue drops spans on export failure rather than blocking the calling thread.

**Out of scope for Stage 8**

- A shared gateway collector across multiple services (explicitly rejected — sidecar-per-service is the chosen design).
- A real tracing backend (Jaeger, Tempo, Grafana). File-based assertion is sufficient to prove the mechanism; swapping the exporter target later is a config-only change.
- Adding sidecars to services other than `research-pipeline` in this pass.

### Adapter swap — `swap-demo`

`swap-demo` is the clearest proof of the hexagonal contract. `PERSISTENCE_BACKEND` selects the adapter at startup — no code changes anywhere else:

```bash
PERSISTENCE_BACKEND=postgres uvicorn entrypoints.http.main:app --port 8005
PERSISTENCE_BACKEND=mongo    uvicorn entrypoints.http.main:app --port 8005
```

Both backends return identical HTTP behaviour through the same routes, the same service, and the same port. Only `bootstrap/dependencies.py` and the two adapter files know which backend is active.

---

## What each service proves

### `items-postgres` — Stage 1 · Postgres only

- `PostgresSettings` reads `DATABASE_URL` from env; fails fast on missing config
- asyncpg pool creation, caching, and connection lifecycle against real Postgres
- `_row_to_entity()` / `_entity_to_row()` on real `asyncpg.Record` objects
- Full CRUD: `create()` → `get()` → `list()` → `update()` → `delete()`
- **Niche 1:** asyncpg `COPY` protocol for bulk insert — 10× faster than individual INSERTs (`bulk_import`)
- **Niche 2:** raw asyncpg parameterised filtered query (`find_by_status`)
- `TracingProxy` produces real OTel spans; `TelemetryMiddleware` instruments HTTP

### `artifacts-mongo` — Stage 1 · MongoDB only

- `MongoSettings` reads `MONGO_URL` and `MONGO_DATABASE` from env
- Motor lazy connection and `_id` ↔ domain `id` string conversion against real MongoDB
- `EmbeddingStatus` enum lifecycle — preview of Research Vault Phase 1
- **Niche 1:** MongoDB `$in` operator for tag filtering (`filter_by_tags`)
- **Niche 2:** case-insensitive regex search across title, abstract, and source (`search`)
- Uses `_get_collection()` for raw motor access inside the adapter subclass

### `cache-redis` — Stage 1 · Redis only

- `RedisSettings` reads `REDIS_URL` from env
- JSON serialisation/deserialisation round-trip with configurable TTL and key prefix
- `SET NX` create · `SET XX` update · `SCAN ITER` key pagination
- **Niche 1:** `EXPIRE` command for TTL extension (`extend_ttl`)
- **Niche 2:** Redis `PIPELINE` for atomic multi-command stats aggregation (`get_stats`)
- `RedisPlugin.capability = "cache"` — validated as the cache tier, not persistence

### `events-kafka` — Stage 1 · Kafka only

- `KafkaSettings` reads `KAFKA_BOOTSTRAP_SERVERS` from env
- `KafkaProducer.start()` connects to real Kafka KRaft broker (no ZooKeeper)
- JSON → bytes serialisation with broker delivery acknowledgement
- **Niche 1:** keyed publish for deterministic partition routing (`publish_keyed`)
- **Niche 2:** topic metadata via raw aiokafka producer introspection (`get_topic_metadata`)
- Background `asyncio.Task` consumer — observable via `GET /events/received`
- Graceful degraded startup when Kafka is not yet ready (`AdapterConnectionError` caught in lifespan)

### `swap-demo` — Stage 1 · Postgres **or** Mongo (swappable)

- Selects `PostgresSwapRepository` or `MongoSwapRepository` at startup via `PERSISTENCE_BACKEND`
- Both adapters extend `PostgresRepository[SwapItem]` / `MongoRepository[SwapItem]` — not hand-rolled
- `save()` UPSERT implemented as a domain-specific custom method on each adapter subclass
- Identical `SwapItemService` and routes regardless of backend — zero code change on swap
- `/info` reports the active backend; `/items` CRUD behaves identically for both
- Architecture tests enforce the boundary: only `adapters/outbound/` and `bootstrap/` see `openframe.adapters`

### `items-cached` — Stage 2 · Postgres + Redis

- **The canonical Stage 2 service** — two adapters, one `PluginRegistry`
- `capability="persistence"` (Postgres) and `capability="cache"` (Redis) coexist without collision
- Cache-aside read pattern: Redis first → on miss, read Postgres and populate Redis
- Cache invalidation on write: `update_item()` and `delete_item()` delete the Redis key
- `create_item()` stamps `created_at` at the service layer before persisting — not delegated to DB default
- Graceful degradation: Redis failures never surface to the caller; Postgres remains the source of truth
- `health_all()` reports both plugins' health independently

### `research-pipeline` — Stage 2 · Mongo + Redis + Kafka · Stage 8 sidecar telemetry

- **The most complete Stage 2 service** — three adapters, three capabilities, one registry
- Registration and initialisation order: Mongo → Redis → Kafka (persistence must be ready before caching, caching before events)
- Shutdown order: Kafka → Redis → Mongo (LIFO — events stop first, connections close last)
- Three-step ingest flow: `store (Mongo)` → `publish event (Kafka)` → `cache status (Redis)`
- Redis-first status lookup: `get_status()` checks Redis sub-millisecond cache; falls back to MongoDB on miss
- Background `asyncio.Task` Kafka consumer updates embedding status in MongoDB and invalidates Redis cache
- `repository_class=` / `producer_class=` on each plugin registration ensures `get_repository()` / `get_producer()` returns the domain subclass — not the plain base class
- **Stage 8:** `research-pipeline-collector` sidecar shares the container's network namespace; `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318` resolves to the sidecar without any extra network hop; `tests/test_observability.py` asserts real spans via the collector's file exporter output

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
cd services/research-pipeline && pytest tests/ -v   # 59 tests  (unit, zero network)
```

**Total: 296 unit tests, zero network calls.**

**Stage 8 integration tests** (require the full docker-compose stack including sidecar):

```bash
# Start stack first
docker compose -f .docker/docker-compose.yml up -d

cd services/research-pipeline && pytest tests/test_observability.py -v   # 4 tests
```

Test coverage per service:

| Layer | What's tested |
|---|---|
| Domain | Entity defaults · field validation · no infrastructure imports |
| Service | Business logic · port delegation · graceful degradation paths |
| Adapter | Port conformance (`BaseRepository` / `BaseProducer`) · mapping methods · error translation (`AdapterQueryError`, `AdapterTimeoutError`) · niche feature behaviour |
| Routes | Status codes · request/response shapes · 404 / 422 handling · cache-hit vs miss transparency |
| Plugin wiring | `repository_class` / `producer_class` regression · capability taxonomy · multi-plugin coexistence |
| Architecture | AST-level import boundary checks — enforces hexagonal rules at the source level |

### Regression tests locked in from live validation

Three bugs discovered during live Docker validation of `items-cached` are locked in as explicit regression tests:

| Bug | Regression test |
|---|---|
| `PostgresPlugin` registered without `table=`/`id_column=` → `RuntimeError` at first request | `test_postgres_plugin_registered_with_table_name` |
| `created_at=None` passed to Postgres → `NotNullViolationError` | `test_create_item_sets_created_at_when_missing` |
| `UndefinedTableError` correctly translated to `AdapterQueryError` with cause chaining | `test_pg_undefined_table_raises_adapter_query_error` |

---

## Backends

```yaml
postgres:  image: postgres:16-alpine          port: 5432
mongo:     image: mongo:7                     port: 27017
redis:     image: redis:7-alpine              port: 6379
kafka:     image: confluentinc/cp-kafka:7.6.0  port: 9092  # KRaft mode, no ZooKeeper
```

All credentials default to `openframe / openframe`. The Postgres schema (`items`, `swap_items` tables) is initialised automatically via `scripts/init_postgres.sql` on first `docker compose up`.

> **Kafka note:** KRaft mode takes 30–60 s to elect a controller on first boot. All Kafka-dependent services handle `AdapterConnectionError` at startup and run in degraded mode until the broker is ready.

> **Degraded mode:** every service catches `(AdapterConnectionError, ValidationError)` in its FastAPI lifespan. If a backend is unreachable at startup the service logs a warning and continues serving traffic — this is intentional and tested behaviour, not a silent failure.

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
