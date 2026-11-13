"""Synchronous client for the paginated synthetic CRM API.

The client owns the extraction boundary: it follows ``next_page`` until the
source reports the end of a collection, validates every response envelope, and
turns HTTP, transport, and malformed-response failures into one domain error.
It deliberately does not log or re-expose payloads, so a failing source cannot
leak record contents into logs or HTTP responses.

This demo collects each full collection before transforming it. That is a
deliberate memory trade-off: the synthetic collections are tiny, a whole
collection makes cross-page duplicate counting exact, and the alternative
(streaming page by page) would need cross-batch state to stay idempotent.
"""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, Field

DEFAULT_PAGE_SIZE = 3
MAX_PAGE_SIZE = 100
DEFAULT_TIMEOUT_SECONDS = 5.0


class CrmClientError(RuntimeError):
    """The CRM source could not be read safely.

    The message names the failing collection and failure kind only; it never
    includes request parameters, response bodies, or record contents.
    """


class PageEnvelope(BaseModel):
    """The response envelope every CRM collection endpoint returns."""

    items: list[dict[str, Any]]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)
    next_page: int | None


class CrmClient:
    """Read complete CRM collections over HTTP, one bounded page at a time."""

    def __init__(
        self,
        base_url: str,
        *,
        page_size: int = DEFAULT_PAGE_SIZE,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not 1 <= page_size <= MAX_PAGE_SIZE:
            raise ValueError(
                f"page_size must be between 1 and {MAX_PAGE_SIZE}, got {page_size}"
            )
        self._base_url = base_url.rstrip("/")
        self._page_size = page_size
        self._timeout = timeout
        self._transport = transport

    def fetch_customers(self) -> list[dict[str, Any]]:
        """Return every customer in source order."""
        return self._fetch_collection("/customers")

    def fetch_vehicles(self) -> list[dict[str, Any]]:
        """Return every vehicle in source order."""
        return self._fetch_collection("/vehicles")

    def fetch_sales(self) -> list[dict[str, Any]]:
        """Return every sale in source order."""
        return self._fetch_collection("/sales")

    def _fetch_collection(self, path: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page: int | None = 1
        with httpx.Client(
            base_url=self._base_url,
            timeout=self._timeout,
            transport=self._transport,
        ) as client:
            while page is not None:
                envelope = self._get_page(client, path, page)
                if envelope.page != page:
                    raise CrmClientError(
                        f"crm-api returned page {envelope.page} while page {page} "
                        f"was requested for {path}"
                    )
                records.extend(envelope.items)

                next_page = envelope.next_page
                if next_page is not None and next_page <= page:
                    raise CrmClientError(
                        f"crm-api returned a repeated or non-progressing page "
                        f"cursor {next_page} for {path}"
                    )
                page = next_page
        return records

    def _get_page(
        self, client: httpx.Client, path: str, page: int
    ) -> PageEnvelope:
        try:
            response = client.get(
                path, params={"page": page, "page_size": self._page_size}
            )
            response.raise_for_status()
        except httpx.TimeoutException as error:
            raise CrmClientError(f"crm-api request for {path} timed out") from error
        except httpx.HTTPStatusError as error:
            raise CrmClientError(
                f"crm-api request for {path} failed with HTTP "
                f"{error.response.status_code}"
            ) from error
        except httpx.HTTPError as error:
            raise CrmClientError(f"crm-api request for {path} failed") from error

        try:
            return PageEnvelope.model_validate(response.json())
        except ValueError as error:
            raise CrmClientError(
                f"crm-api returned a malformed page envelope for {path}"
            ) from error
