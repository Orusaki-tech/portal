# --- Builder ---
FROM python:3.13-slim AS builder

WORKDIR /app

COPY backend/requirements-core.txt .
RUN pip install --user --no-cache-dir -r requirements-core.txt

# --- Runtime ---
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

COPY backend/ backend/
COPY database/ database/

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

CMD ["sh", "-c", "python database/run_migrations.py && uvicorn backend.engine.entrypoints.api:app --host 0.0.0.0 --port 8000"]
