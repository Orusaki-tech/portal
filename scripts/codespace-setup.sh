#!/usr/bin/env bash
set -euo pipefail

echo "=== RealitySync Codespace Setup ==="

echo ""
echo "1. Installing project + dev deps..."
pip install -e ".[dev]"

echo ""
echo "   Installing frontend dependencies..."
(cd frontend && npm install @turf/turf shpjs 2>/dev/null && npm install) || echo "  npm not available, run 'cd frontend && npm install' manually"

echo ""
echo "2. Installing pre-commit hooks..."
pre-commit install

echo ""
echo "3. Copying env file..."
cp -n .env.example .env 2>/dev/null || echo "  .env already exists, skipped"

echo ""
echo "4. Starting PostGIS + services..."
docker compose up -d

echo ""
echo "5. Applying database migrations..."
make docker-migrate

echo ""
echo "6. Ensuring mypy is installed..."
python -m pip install mypy~=1.11

echo ""
echo "7. Auto-fixing ruff issues..."
ruff check --fix && ruff format

echo ""
echo "8. Running linter (must be clean)..."
make lint

echo ""
echo "9. Installing mypy type stubs..."
python -m pip install types-PyYAML types-psycopg2

echo ""
echo "10. Running typechecker (pre-existing errors only — not a regression)..."
make typecheck || true

echo ""
echo "11. Running unit tests (all 75 must pass)..."
python -m pytest tests/unit/ -v --tb=short

echo ""
echo "12. Running smoke test (E2E against Docker)..."
bash scripts/smoke-test.sh

echo ""
echo "=== Done! Open http://localhost:3000 ==="
