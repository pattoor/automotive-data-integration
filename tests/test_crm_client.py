"""Paginated CRM client tests against a fully controlled HTTP boundary.

``httpx.MockTransport`` replaces only the network hop, so the real client code
builds URLs, follows ``next_page``, validates envelopes, and raises domain
errors while every response below mirrors the complete CRM envelope.
"""

from typing import Any

import httpx
import pytest

from automotive_data_integration.pipeline_api.crm_client import (
    CrmClient,
    CrmClientError,
)
from automotive_data_integration.pipeline_api.transform import transform_customers

BASE_URL = "http://crm-api:8000"


def envelope(
    items: list[dict[str, Any]],
    *,
    page: int,
    page_size: int,
    total: int,
    total_pages: int,
    next_page: int | None,
) -> dict[str, Any]:
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "next_page": next_page,
    }


def record(crm_id: str, **overrides: Any) -> dict[str, Any]:
    values = {
        "id": crm_id,
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.test",
        "phone": "+1-555-0101",
        "city": "London",
        "created_at": "2024-01-05T09:00:00Z",
    }
    values.update(overrides)
    return values


def serve(pages: dict[int, dict[str, Any]], requests: list[tuple[str, int, int]]):
    """Return a transport that answers page numbers and records each request."""

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        requests.append(
            (request.url.path, page, int(request.url.params["page_size"]))
        )
        return httpx.Response(200, json=pages[page])

    return httpx.MockTransport(handler)


def test_fetch_customers_follows_next_page_until_null_and_preserves_order():
    pages = {
        1: envelope(
            [record("CUST-1"), record("CUST-2"), record("CUST-3")],
            page=1,
            page_size=3,
            total=7,
            total_pages=3,
            next_page=2,
        ),
        2: envelope(
            [record("CUST-4"), record("CUST-5"), record("CUST-6")],
            page=2,
            page_size=3,
            total=7,
            total_pages=3,
            next_page=3,
        ),
        3: envelope(
            [record("CUST-7")],
            page=3,
            page_size=3,
            total=7,
            total_pages=3,
            next_page=None,
        ),
    }
    requests: list[tuple[str, int, int]] = []
    client = CrmClient(BASE_URL, transport=serve(pages, requests))

    customers = client.fetch_customers()

    assert [customer["id"] for customer in customers] == [
        "CUST-1",
        "CUST-2",
        "CUST-3",
        "CUST-4",
        "CUST-5",
        "CUST-6",
        "CUST-7",
    ]
    assert requests == [
        ("/customers", 1, 3),
        ("/customers", 2, 3),
        ("/customers", 3, 3),
    ]


def test_empty_collection_returns_no_rows():
    pages = {
        1: envelope(
            [], page=1, page_size=3, total=0, total_pages=0, next_page=None
        )
    }
    requests: list[tuple[str, int, int]] = []

    assert CrmClient(BASE_URL, transport=serve(pages, requests)).fetch_customers() == []
    assert requests == [("/customers", 1, 3)]


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("fetch_customers", "/customers"),
        ("fetch_vehicles", "/vehicles"),
        ("fetch_sales", "/sales"),
    ],
)
def test_each_fetch_uses_its_collection_path(method, path):
    pages = {
        1: envelope(
            [record("X-1")], page=1, page_size=3, total=1, total_pages=1, next_page=None
        )
    }
    requests: list[tuple[str, int, int]] = []

    getattr(CrmClient(BASE_URL, transport=serve(pages, requests)), method)()

    assert requests == [(path, 1, 3)]


def test_http_failure_raises_a_domain_error_with_the_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"detail": "upstream unavailable"})

    client = CrmClient(BASE_URL, transport=httpx.MockTransport(handler))

    with pytest.raises(CrmClientError) as raised:
        client.fetch_customers()

    assert "502" in str(raised.value)


def test_timeout_raises_a_domain_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = CrmClient(BASE_URL, transport=httpx.MockTransport(handler))

    with pytest.raises(CrmClientError):
        client.fetch_customers()


@pytest.mark.parametrize(
    ("content", "payload"),
    [
        pytest.param(b"not-json", None, id="not-json"),
        pytest.param(
            None,
            {
                "page": 1,
                "page_size": 3,
                "total": 0,
                "total_pages": 0,
                "next_page": None,
            },
            id="missing-items",
        ),
        pytest.param(
            None,
            {
                "items": "not-a-list",
                "page": 1,
                "page_size": 3,
                "total": 0,
                "total_pages": 0,
                "next_page": None,
            },
            id="wrong-item-type",
        ),
        pytest.param(
            None,
            {
                "items": [],
                "page": 1,
                "page_size": 3,
                "total": 0,
                "total_pages": 0,
            },
            id="missing-next-page",
        ),
    ],
)
def test_malformed_envelope_raises_a_domain_error(content, payload):
    def handler(request: httpx.Request) -> httpx.Response:
        if content is not None:
            return httpx.Response(200, content=content)
        return httpx.Response(200, json=payload)

    client = CrmClient(BASE_URL, transport=httpx.MockTransport(handler))

    with pytest.raises(CrmClientError) as raised:
        client.fetch_customers()

    assert "malformed" in str(raised.value)


def test_non_progressing_cursor_stops_instead_of_looping():
    pages = {
        1: envelope(
            [record("CUST-1")],
            page=1,
            page_size=3,
            total=7,
            total_pages=3,
            next_page=2,
        ),
        2: envelope(
            [record("CUST-2")],
            page=2,
            page_size=3,
            total=7,
            total_pages=3,
            next_page=2,
        ),
    }
    requests: list[tuple[str, int, int]] = []

    with pytest.raises(CrmClientError) as raised:
        CrmClient(BASE_URL, transport=serve(pages, requests)).fetch_customers()

    assert "cursor" in str(raised.value)
    assert requests == [("/customers", 1, 3), ("/customers", 2, 3)]


def test_envelope_page_must_match_the_requested_page():
    pages = {
        1: envelope(
            [record("CUST-1")],
            page=2,
            page_size=3,
            total=7,
            total_pages=3,
            next_page=3,
        )
    }

    with pytest.raises(CrmClientError):
        CrmClient(BASE_URL, transport=serve(pages, [])).fetch_customers()


@pytest.mark.parametrize("page_size", [0, -1, 101])
def test_page_size_must_be_bounded(page_size):
    with pytest.raises(ValueError):
        CrmClient(BASE_URL, page_size=page_size)


def test_collected_pages_count_duplicate_ids_across_page_boundaries():
    pages = {
        1: envelope(
            [record("CUST-1"), record("CUST-2"), record("CUST-3")],
            page=1,
            page_size=3,
            total=6,
            total_pages=2,
            next_page=2,
        ),
        2: envelope(
            [record("CUST-4"), record("CUST-5"), record("CUST-1", city="Paris")],
            page=2,
            page_size=3,
            total=6,
            total_pages=2,
            next_page=None,
        ),
    }
    requests: list[tuple[str, int, int]] = []

    raw_customers = CrmClient(BASE_URL, transport=serve(pages, requests)).fetch_customers()
    result = transform_customers(raw_customers)

    assert [customer.crm_id for customer in result.accepted] == [
        "CUST-1",
        "CUST-2",
        "CUST-3",
        "CUST-4",
        "CUST-5",
    ]
    assert result.accepted[0].city == "London"
    assert result.duplicate_count == 1
