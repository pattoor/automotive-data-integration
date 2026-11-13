import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from automotive_data_integration.common.health import health_router
from automotive_data_integration.common.server import serve
from automotive_data_integration.pipeline_api.repository import PostgresRepository
from automotive_data_integration.pipeline_api.routes import router as pipeline_router
from automotive_data_integration.pipeline_api.service import PipelineError

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
app.include_router(pipeline_router)


@app.exception_handler(PipelineError)
async def pipeline_error_handler(
    request: Request, error: PipelineError
) -> JSONResponse:
    """Report a failed run with its status and a payload-free message."""
    return JSONResponse(
        status_code=error.status_code,
        content={
            "run_id": error.run_id,
            "status": "failed",
            "message": error.message,
        },
    )


def main() -> None:
    serve(app)
