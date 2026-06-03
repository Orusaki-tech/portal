#!/usr/bin/env bash
# RealitySync Smoke Test — curl-based E2E sanity check
#
# Usage:
#   API_BASE=http://localhost:8000/api \
#     EMAIL=test@example.com \
#     PASSWORD=password123 \
#     bash scripts/smoke-test.sh
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000/api}"
EMAIL="${EMAIL:-smoke@realitysync.example}"
PASSWORD="${PASSWORD:-SmokeTest123!}"
COOKIE_JAR=$(mktemp)
PASS=0
FAIL=0

cleanup() { rm -f "$COOKIE_JAR"; }
trap cleanup EXIT

pass() { echo "  ✓ $1"; PASS=$((PASS + 1)); }
fail() { echo "  ✗ $1: $2"; FAIL=$((FAIL + 1)); }

echo "RealitySync Smoke Test"
echo "======================"
echo ""

# 1. Health check
echo "1. Health check"
HEALTH=$(curl -sf http://localhost:8000/health 2>&1 || true)
if echo "$HEALTH" | grep -q "ok"; then
    pass "health endpoint"
else
    fail "health endpoint" "$HEALTH"
fi

# 2. Register
echo "2. Register"
REG=$(curl -sf -X POST "${API_BASE}/register" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\",\"name\":\"Smoke Tester\"}" 2>&1 || true)
if echo "$REG" | grep -q "user_id"; then
    pass "register"
else
    fail "register" "$REG"
fi

# 3. Login
echo "3. Login"
LOGIN=$(curl -sf -X POST "${API_BASE}/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}" 2>&1 || true)
if echo "$LOGIN" | grep -q "token"; then
    TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
    pass "login"
else
    fail "login" "$LOGIN"
fi

AUTH="Authorization: Bearer ${TOKEN}"

# 4. Upload dataset (polygon set)
echo "4. Upload dataset"
UPLOAD=$(curl -sf -X POST "${API_BASE}/datasets" \
    -H "${AUTH}" \
    -H "Content-Type: application/json" \
    -d '{"name":"Smoke Dataset","polygons":[{"geometry":"POLYGON((-97.734 30.267,-97.733 30.267,-97.733 30.268,-97.734 30.268,-97.734 30.267))","properties":{}}]}' 2>&1 || true)
if echo "$UPLOAD" | grep -q "set_id"; then
    SET_ID=$(echo "$UPLOAD" | python3 -c "import sys,json; print(json.load(sys.stdin)['set_id'])")
    pass "upload dataset"
else
    fail "upload dataset" "$UPLOAD"
fi

# 5. Validate polygon
echo "5. Validate polygon"
VALIDATE=$(curl -sf -X POST "${API_BASE}/validate" \
    -H "${AUTH}" \
    -H "Content-Type: application/json" \
    -d "{\"polygon_set_id\":\"${SET_ID}\"}" 2>&1 || true)
if echo "$VALIDATE" | grep -q "run_id"; then
    pass "validate polygon"
else
    fail "validate polygon" "$VALIDATE"
fi

# 6. List triage
echo "6. List triage"
TRIAGE=$(curl -sf "${API_BASE}/triage" \
    -H "${AUTH}" 2>&1 || true)
if echo "$TRIAGE" | grep -qE "\[|\"polygons\""; then
    pass "list triage"
else
    fail "list triage" "$TRIAGE"
fi

# 7. Request export
echo "7. Request export"
EXPORT=$(curl -sf -X POST "${API_BASE}/exports" \
    -H "${AUTH}" \
    -H "Content-Type: application/json" \
    -d "{\"format\":\"geojson\",\"source_type\":\"dataset\",\"source_id\":\"${SET_ID}\"}" 2>&1 || true)
if echo "$EXPORT" | grep -q "export_id"; then
    pass "request export"
else
    fail "request export" "$EXPORT"
fi

echo ""
echo "======================"
echo "Results: ${PASS} passed, ${FAIL} failed"
[ "${FAIL}" -eq 0 ] || exit 1
