from __future__ import annotations

import logging
import os

import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-36s %(levelname)-8s %(message)s",
)

logger = logging.getLogger("realitysync")


def main() -> None:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("RELOAD", "false").lower() == "true"

    logger.info("Starting RealitySync API on %s:%s (reload=%s)", host, port, reload)

    uvicorn.run(
        "backend.engine.entrypoints.api:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
