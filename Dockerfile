FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app

WORKDIR /app

COPY backend/requirements-core.txt .
RUN pip install --no-cache-dir -r requirements-core.txt

COPY backend/ backend/
COPY database/ database/

RUN chown -R app:app /app

USER app

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8080/health').raise_for_status()"

CMD ["sh", "-c", "python database/run_migrations.py && uvicorn backend.engine.entrypoints.api:app --host 0.0.0.0 --port 8080"]
