"""Read-only CRM collection routes."""

from fastapi import APIRouter, Query

from automotive_data_integration.crm_api.fixtures import CUSTOMERS, SALES, VEHICLES
from automotive_data_integration.crm_api.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PaginatedResponse,
    paginate,
)

router = APIRouter(tags=["crm"])


@router.get(
    "/customers",
    response_model=PaginatedResponse,
    summary="List synthetic customers",
)
def list_customers(
    page: int = Query(1, ge=1, description="One-based page number."),
    page_size: int = Query(
        DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description="Records per page (1-100).",
    ),
) -> PaginatedResponse:
    return paginate(CUSTOMERS, page, page_size)


@router.get(
    "/vehicles",
    response_model=PaginatedResponse,
    summary="List synthetic vehicles",
)
def list_vehicles(
    page: int = Query(1, ge=1, description="One-based page number."),
    page_size: int = Query(
        DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description="Records per page (1-100).",
    ),
) -> PaginatedResponse:
    return paginate(VEHICLES, page, page_size)


@router.get(
    "/sales",
    response_model=PaginatedResponse,
    summary="List synthetic sales",
)
def list_sales(
    page: int = Query(1, ge=1, description="One-based page number."),
    page_size: int = Query(
        DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description="Records per page (1-100).",
    ),
) -> PaginatedResponse:
    return paginate(SALES, page, page_size)
