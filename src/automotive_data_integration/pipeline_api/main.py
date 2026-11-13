import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from automotive_data_integration.common.health import health_router
from automotive_data_integration.common.server import serve
from automotive_data_integration.pipeline_api.repository import PostgresRepository

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create missing tables before serving requests.

    ``DATABASE_URL`` is optional so the API can still run without persistence
    (and so unit tests need no database). When it is set, schema errors and
    connection failures propagate: starting with a broken database is worse
    than failing the container start.
    """
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        PostgresRepository(dsn).initialize_schema()
        logger.info("database schema initialized")
    else:
        logger.warning("DATABASE_URL is not set; persistence is disabled")
    yield


app = FastAPI(title="pipeline-api", lifespan=lifespan)
app.include_router(health_router("pipeline-api"))


def main() -> None:
    serve(app)
