# Codespace Setup & Verification

## 1. Launch Codespace

Open the repo in GitHub, click **Code → Open with Codespaces → New codespace**.

## 2. Bootstrap Environment

```bash
# Install project with all dev deps
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Copy env file
cp .env.example .env
```

## 3. Start Services

```bash
# PostGIS + API + frontend
docker compose up -d
```

## 4. Run Migrations

```bash
make docker-migrate
```

## 5. Verify Lint & Types

```bash
make lint
make typecheck
```

Fix any issues found, then re-run until clean.

## 6. Run Tests

```bash
# Unit tests only (no PostGIS needed)
python -m pytest tests/unit/ -v

# All tests including integration
python -m pytest -v

# With coverage
python -m pytest --cov --cov-report=term-missing
```

## 7. Smoke Test

```bash
# Ensure API is running
curl http://localhost:8000/health

# Run full E2E smoke test
bash scripts/smoke-test.sh
```

## 8. Manual QA

- Open frontend at `http://localhost:3000`
- Register a user → upload a dataset → validate → review triage → export
- Verify map renders tiles at the review/correction stage

## 9. Cleanup & Commit

```bash
# Stage all new files
git add -A

# Review diff
git diff --cached --stat

# Commit
git commit -m "Production readiness: Sentry, ValidationRun, pre-commit, docs, smoke tests, bug fixes"
```

---

## Remaining Pre-Launch Checks

After the steps above, confirm:

- [ ] `ConsensusReached` and `HackathonScoreUpdated` handlers logged in bootstrap — no more empty `[]` handler lists
- [ ] `GET /api/credits/{user_id}` returns 403 when requesting another user's balance
- [ ] WKT parser in `export_worker.py` uses `shapely.wkt.loads` — robust to nested parens/spaces
- [ ] `ValidationRun` model includes `imagery_id`, `region`, `ambiguous_count`
- [ ] `requires-python` allows 3.14 — no version conflict

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `psycopg2` build fails | `apt-get install libpq-dev` |
| `gdal` / `fiona` install fails | `apt-get install gdal-bin libgdal-dev` |
| Port 8000 in use | Change `API_BASE` in .env or kill existing process |
| PostGIS won't start | Check docker logs: `docker compose logs postgis` |
