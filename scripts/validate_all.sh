#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; exit 1; }

check() {
    local desc="$1"
    local url="$2"
    local method="${3:-GET}"
    local data="${4:-}"
    local expected="${5:-200}"

    if [ -n "$data" ]; then
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
            -X "$method" "$url" \
            -H "Content-Type: application/json" \
            -d "$data")
    else
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X "$method" "$url")
    fi

    if [ "$STATUS" = "$expected" ]; then
        pass "$desc ($STATUS)"
    else
        fail "$desc — expected $expected got $STATUS"
    fi
}

# Silently delete a resource before a test section so the script is idempotent
# and can be re-run against a persistent data volume without duplicate-key errors.
cleanup() {
    curl -s -o /dev/null -X DELETE "$1" || true
}

echo "=== openframe-local-validation ==="
echo ""

# ── items-postgres (port 8001) ──────────────────────────────────────────────
echo "--- items-postgres ---"
check "health"           "http://localhost:8001/health"
cleanup "http://localhost:8001/items/item-1"
cleanup "http://localhost:8001/items/bulk-1"
cleanup "http://localhost:8001/items/bulk-2"
check "create item"      "http://localhost:8001/items" \
    "POST" '{"id":"item-1","name":"Widget","description":"A test widget","status":"active"}' "201"
check "get item"         "http://localhost:8001/items/item-1"
check "list items"       "http://localhost:8001/items"
check "filter by status" "http://localhost:8001/items?status=active"
check "bulk import"      "http://localhost:8001/items/bulk" \
    "POST" '[{"id":"bulk-1","name":"Bulk A"},{"id":"bulk-2","name":"Bulk B"}]' "201"
check "delete item"      "http://localhost:8001/items/item-1" "DELETE" "" "204"
echo ""

# ── artifacts-mongo (port 8002) ─────────────────────────────────────────────
echo "--- artifacts-mongo ---"
check "health"           "http://localhost:8002/health"
cleanup "http://localhost:8002/artifacts/art-1"
check "create artifact"  "http://localhost:8002/artifacts" \
    "POST" '{"id":"art-1","title":"Attention Is All You Need","source":"arxiv","tags":["transformer","nlp"]}' "201"
check "get artifact"     "http://localhost:8002/artifacts/art-1"
check "list artifacts"   "http://localhost:8002/artifacts"
check "search"           "http://localhost:8002/artifacts/search?q=attention"
check "filter by tag"    "http://localhost:8002/artifacts?tags=transformer"
check "delete artifact"  "http://localhost:8002/artifacts/art-1" "DELETE" "" "204"
echo ""

# ── cache-redis (port 8003) ─────────────────────────────────────────────────
echo "--- cache-redis ---"
check "health"           "http://localhost:8003/health"
cleanup "http://localhost:8003/sessions/sess-1"
check "create session"   "http://localhost:8003/sessions" \
    "POST" '{"id":"sess-1","user_id":"user-123"}' "201"
check "get session"      "http://localhost:8003/sessions/sess-1"
check "extend TTL"       "http://localhost:8003/sessions/sess-1/extend" \
    "PUT" '{"seconds":7200}' "200"
check "redis stats"      "http://localhost:8003/sessions/stats"
check "delete session"   "http://localhost:8003/sessions/sess-1" "DELETE" "" "204"
echo ""

# ── events-kafka (port 8004) ─────────────────────────────────────────────────
echo "--- events-kafka ---"
check "health"           "http://localhost:8004/health"
check "publish event"    "http://localhost:8004/events" \
    "POST" '{"order_id":"ord-1","event_type":"created","payload":{"amount":99.99}}' "201"
check "publish batch"    "http://localhost:8004/events/batch" \
    "POST" '[{"order_id":"ord-2","event_type":"updated","payload":{}},{"order_id":"ord-3","event_type":"cancelled","payload":{}}]' "201"
check "topic metadata"   "http://localhost:8004/events/metadata"
check "received events"  "http://localhost:8004/events/received"
echo ""

# ── swap-demo (port 8005) ───────────────────────────────────────────────────
echo "--- swap-demo (PERSISTENCE_BACKEND=${PERSISTENCE_BACKEND:-postgres}) ---"
check "health"           "http://localhost:8005/health"
check "info"             "http://localhost:8005/info"
cleanup "http://localhost:8005/items/swap-1"
check "create"           "http://localhost:8005/items" \
    "POST" '{"id":"swap-1","name":"Swap Widget","description":"Adapter swap test"}' "201"
check "get"              "http://localhost:8005/items/swap-1"
check "list"             "http://localhost:8005/items"
check "delete"           "http://localhost:8005/items/swap-1" "DELETE" "" "204"
echo ""

# ── items-cached (port 8006) ─────────────────────────────────────────────────
echo "--- items-cached ---"
check "health"           "http://localhost:8006/health"
cleanup "http://localhost:8006/items/cached-1"
check "create item"      "http://localhost:8006/items" \
    "POST" '{"id":"cached-1","name":"Cached Widget","description":"Cache-aside test","status":"active"}' "201"
check "get item"         "http://localhost:8006/items/cached-1"
check "list items"       "http://localhost:8006/items"
check "delete item"      "http://localhost:8006/items/cached-1" "DELETE" "" "204"
echo ""

# ── research-pipeline (port 8007) ────────────────────────────────────────────
echo "--- research-pipeline ---"
check "health"           "http://localhost:8007/health"
check "pipeline info"    "http://localhost:8007/pipeline-info"
cleanup "http://localhost:8007/artifacts/rp-1"
check "ingest artifact"  "http://localhost:8007/artifacts" \
    "POST" '{"id":"rp-1","title":"Sidecar Telemetry Paper","source":"arxiv","tags":["otel","stage8"]}' "201"
check "get artifact"     "http://localhost:8007/artifacts/rp-1"
check "list artifacts"   "http://localhost:8007/artifacts"
check "get status"       "http://localhost:8007/artifacts/rp-1/status"
echo ""

# ── Stage 8 — sidecar telemetry (requires docker-compose stack) ──────────────
# One sidecar per service. Each test_observability.py is run only when its
# companion collector container is confirmed running.
echo "--- Stage 8: sidecar telemetry ---"

_REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
_STAGE8_ANY_RAN=false
_STAGE8_ALL_SKIPPED=true

_run_stage8() {
    local service="$1"
    local collector="openframe-${service}-collector"

    if ! command -v docker &>/dev/null; then
        echo -e "${RED}✗${NC} docker CLI not found — skipping Stage 8 for ${service}"
        return
    fi

    if docker ps --filter "name=${collector}" \
                 --filter "status=running" \
                 --format "{{.Names}}" 2>/dev/null \
        | grep -q "${collector}"; then
        _STAGE8_ALL_SKIPPED=false
        python -m pytest "${_REPO_ROOT}/services/${service}/tests/test_observability.py" \
            -v --tb=short \
            || fail "Stage 8 ${service} telemetry tests failed — see output above"
        pass "Stage 8 ${service}: sidecar telemetry"
        _STAGE8_ANY_RAN=true
    else
        echo -e "  ${RED}skip${NC} ${collector} not running (${service})"
    fi
}

_run_stage8 "items-postgres"
_run_stage8 "artifacts-mongo"
_run_stage8 "cache-redis"
_run_stage8 "events-kafka"
_run_stage8 "swap-demo"
_run_stage8 "items-cached"
_run_stage8 "research-pipeline"

if [ "$_STAGE8_ALL_SKIPPED" = "true" ]; then
    echo ""
    echo -e "  ${RED}Note:${NC} all Stage 8 tests skipped — no collector sidecars are running."
    echo "  To run them: docker compose -f .docker/docker-compose.yml up -d"
    echo "  Then re-run:  bash scripts/validate_all.sh"
fi
echo ""

echo "=== All checks passed ==="
