"""Bounded pagination shared by the CRM collection endpoints."""

from math import ceil
from typing import Any

from pydantic import BaseModel, Field

DEFAULT_PAGE_SIZE = 3
MAX_PAGE_SIZE = 100


class PaginatedResponse(BaseModel):
    """Response envelope returned by every CRM collection endpoint."""

    items: list[dict[str, Any]] = Field(description="Records on the requested page.")
    page: int = Field(description="Requested one-based page number.")
    page_size: int = Field(description="Maximum records per page (1-100).")
    total: int = Field(description="Total records in the collection.")
    total_pages: int = Field(description="Number of pages at the requested page size.")
    next_page: int | None = Field(
        description="Next page number, or null when the requested page is the last one."
    )


def paginate(
    records: list[dict[str, Any]], page: int, page_size: int
) -> PaginatedResponse:
    """Slice one page of records and describe it with the standard envelope."""
    total = len(records)
    total_pages = ceil(total / page_size)
    start = (page - 1) * page_size

    return PaginatedResponse(
        items=records[start : start + page_size],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
        next_page=page + 1 if page < total_pages else None,
    )
