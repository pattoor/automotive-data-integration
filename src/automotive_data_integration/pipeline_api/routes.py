"""Pipeline execution routes."""

from fastapi import APIRouter, Depends

from automotive_data_integration.pipeline_api.dependencies import (
    get_pipeline_service,
)
from automotive_data_integration.pipeline_api.schemas import PipelineRunSummary
from automotive_data_integration.pipeline_api.service import PipelineService

router = APIRouter(tags=["pipeline"])


@router.post(
    "/pipeline/runs",
    response_model=PipelineRunSummary,
    summary="Run the ETL pipeline once and return its summary",
)
def create_pipeline_run(
    service: PipelineService = Depends(get_pipeline_service),
) -> PipelineRunSummary:
    """Extract every CRM page, transform, load, and report the run."""
    return service.run()
