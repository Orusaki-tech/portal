#!/usr/bin/env bash
set -euo pipefail

echo "=== RealitySync Codespace Setup ==="

echo ""
echo "1. Installing project + dev deps..."
pip install -e ".[dev]"

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
echo "6. Running linter..."
make lint || true

echo ""
echo "7. Running typechecker..."
make typecheck || true

echo ""
echo "8. Running unit tests..."
python -m pytest tests/unit/ -v || true

echo ""
echo "9. Running smoke test..."
bash scripts/smoke-test.sh || true

echo ""
echo "=== Done! Open http://localhost:3000 ==="
