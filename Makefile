.PHONY: venv install docker-up docker-down migrate test lint typecheck pre-commit-install pre-commit-run clean

PYTHON ?= python3
PIP ?= pip3

# Virtual environment
venv:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -e ".[dev]"

install:
	pip3 install -e ".[dev]"

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

docker-migrate:
	docker compose exec api python database/run_migrations.py

db-reset:
	docker compose down -v
	docker compose up -d postgis --wait
	sleep 3
	$(MAKE) docker-migrate

# Testing & linting
dev:
	@echo "Starting API on :8000 and Frontend on :3000..."
	@trap 'kill 0' EXIT; \
		$(PYTHON) backend/engine/entrypoints/main.py & \
		cd frontend && npm run dev

run:
	$(PYTHON) backend/engine/entrypoints/main.py
test:
	$(PYTHON) -m pytest -v

test-cov:
	$(PYTHON) -m pytest --cov --cov-report=term-missing

lint:
	ruff check .

lint-fix:
	ruff check --fix .

typecheck:
	mypy backend/

pre-commit-install:
	$(VENV)/bin/pre-commit install

pre-commit-run:
	$(VENV)/bin/pre-commit run --all-files

# Cleanup
clean:
	rm -rf $(VENV)
	rm -rf __pycache__
	rm -rf **/__pycache__
	rm -rf .pytest_cache
	rm -rf *.egg-info
