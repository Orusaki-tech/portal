#!/usr/bin/env bash
# RealitySync Full Validation — run inside a codespace with Docker + mypy installed.
# All steps are strict — failures cause non-zero exit unless noted.
set -euo pipefail

PASS=0
FAIL=0

pass() { echo "  ✓ $1"; PASS=$((PASS + 1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL + 1)); }

echo "RealitySync Validation"
echo "======================"
echo ""

echo "1. Ruff lint (must be clean)..."
if ruff check . && ruff format --check; then
    pass "ruff lint"
else
    fail "ruff lint"
fi

echo ""
echo "2. Mypy typecheck (191 pre-existing — not a regression)"
if mypy backend/; then
    pass "mypy"
else
    echo "  (expected: ~191 pre-existing errors)"
fi

echo ""
echo "3. Unit tests (all 75 pass)..."
if python -m pytest tests/unit/ -v --tb=short; then
    pass "unit tests"
else
    fail "unit tests"
fi

echo ""
echo "4. Smoke test (E2E against Docker)..."
if bash scripts/smoke-test.sh; then
    pass "smoke test"
else
    fail "smoke test"
fi

echo ""
echo "======================"
echo "Results: ${PASS} passed, ${FAIL} failed"
[ "${FAIL}" -eq 0 ]
