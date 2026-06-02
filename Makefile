.PHONY: venv install docker-up docker-down migrate test lint typecheck clean

VENV = .venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip

# Virtual environment
venv:
	python3.11 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

install:
	$(PIP) install -e ".[dev]"

# Docker
docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

docker-psql:
	docker compose exec postgis psql -U realitysync -d realitysync

# Database
migrate:
	$(PYTHON) database/run_migrations.py

db-reset:
	docker compose down -v
	docker compose up -d
	sleep 3
	$(MAKE) migrate

# Testing & linting
dev:
	@echo "Starting API on :8000 and Frontend on :3000..."
	@trap 'kill 0' EXIT; \
		uvicorn backend.engine.entrypoints.api:app --reload --host 0.0.0.0 --port 8000 & \
		cd frontend && npm run dev
test:
	$(PYTHON) -m pytest -v

test-cov:
	$(PYTHON) -m pytest --cov --cov-report=term-missing

lint:
	$(VENV)/bin/ruff check .

lint-fix:
	$(VENV)/bin/ruff check --fix .

typecheck:
	$(VENV)/bin/mypy backend/

# Cleanup
clean:
	rm -rf $(VENV)
	rm -rf __pycache__
	rm -rf **/__pycache__
	rm -rf .pytest_cache
	rm -rf *.egg-info
