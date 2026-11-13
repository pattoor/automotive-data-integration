"""Runtime wiring for the pipeline API.

Environment is read per request so tests and Compose can configure the service
without importing module-level state. A missing or invalid configuration is a
controlled 503, not a stack trace.
"""

import os

from automotive_data_integration.pipeline_api.crm_client import (
    DEFAULT_PAGE_SIZE,
    CrmClient,
)
from automotive_data_integration.pipeline_api.repository import PostgresRepository
from automotive_data_integration.pipeline_api.service import (
    PipelineError,
    PipelineService,
)


def get_pipeline_service() -> PipelineService:
    """Build one pipeline execution from the current environment."""
    dsn = os.environ.get("DATABASE_URL")
    base_url = os.environ.get("CRM_BASE_URL")
    if not dsn or not base_url:
        raise PipelineError(
            "DATABASE_URL and CRM_BASE_URL must be set to run the pipeline",
            status_code=503,
        )

    raw_page_size = os.environ.get("CRM_PAGE_SIZE", str(DEFAULT_PAGE_SIZE))
    try:
        page_size = int(raw_page_size)
    except ValueError:
        raise PipelineError(
            "CRM_PAGE_SIZE must be an integer", status_code=503
        ) from None

    try:
        client = CrmClient(base_url, page_size=page_size)
    except ValueError as error:
        raise PipelineError(str(error), status_code=503) from error

    return PipelineService(PostgresRepository(dsn), client)
