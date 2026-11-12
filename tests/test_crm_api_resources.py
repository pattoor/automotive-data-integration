import pytest
from fastapi.testclient import TestClient

from automotive_data_integration.crm_api.main import app

client = TestClient(app)

ENVELOPE_FIELDS = {"items", "page", "page_size", "total", "total_pages", "next_page"}

# Total record counts the deterministic fixtures are specified to expose,
# including the documented duplicate and malformed source records.
RESOURCES = [
    pytest.param("/customers", 7, 3, id="customers"),
    pytest.param("/vehicles", 5, 2, id="vehicles"),
    pytest.param("/sales", 5, 2, id="sales"),
]


def get_page(path, **params):
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize(("path", "total", "total_pages"), RESOURCES)
def test_first_page_returns_default_page_size_with_complete_metadata(
    path, total, total_pages
):
    body = get_page(path)

    assert set(body) == ENVELOPE_FIELDS
    assert body["page"] == 1
    assert body["page_size"] == 3
    assert body["total"] == total
    assert body["total_pages"] == total_pages
    assert len(body["items"]) == 3
    assert body["next_page"] == 2


@pytest.mark.parametrize(
    ("path", "page", "remaining"),
    [
        pytest.param("/customers", 3, 1, id="customers"),
        pytest.param("/vehicles", 2, 2, id="vehicles"),
        pytest.param("/sales", 2, 2, id="sales"),
    ],
)
def test_last_page_returns_remaining_items_and_no_next_page(path, page, remaining):
    body = get_page(path, page=page)

    assert body["page"] == page
    assert len(body["items"]) == remaining
    assert body["next_page"] is None


@pytest.mark.parametrize(("path", "total", "total_pages"), RESOURCES)
def test_out_of_range_page_returns_empty_items_with_correct_metadata(
    path, total, total_pages
):
    requested_page = total_pages + 5

    body = get_page(path, page=requested_page)

    assert body["items"] == []
    assert body["page"] == requested_page
    assert body["page_size"] == 3
    assert body["total"] == total
    assert body["total_pages"] == total_pages
    assert body["next_page"] is None


def test_page_size_accepts_the_maximum_bound():
    body = get_page("/customers", page_size=100)

    assert body["page_size"] == 100
    assert len(body["items"]) == 7
    assert body["total_pages"] == 1
    assert body["next_page"] is None


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("/customers?page=0", id="page-zero"),
        pytest.param("/vehicles?page=-3", id="page-negative"),
        pytest.param("/sales?page_size=0", id="page-size-zero"),
        pytest.param("/customers?page_size=101", id="page-size-over-max"),
        pytest.param("/vehicles?page_size=-1", id="page-size-negative"),
    ],
)
def test_invalid_pagination_bounds_are_rejected_with_422(path):
    response = client.get(path)

    assert response.status_code == 422


def test_pages_preserve_fixture_order_across_boundaries():
    first_page = get_page("/customers")["items"]
    second_page = get_page("/customers", page=2)["items"]

    assert [item["id"] for item in first_page] == [
        "CUST-0001",
        "CUST-0002",
        "CUST-0003",
    ]
    # The deliberate duplicate of CUST-0001 is a separate source row, so it
    # keeps its own position instead of being silently removed by the API.
    assert [item["id"] for item in second_page] == [
        "CUST-0004",
        "CUST-0005",
        "CUST-0001",
    ]


@pytest.mark.parametrize("path", ["/customers", "/vehicles", "/sales"])
def test_repeated_requests_return_identical_payloads(path):
    assert get_page(path) == get_page(path)


def test_customers_include_the_documented_duplicate_source_record():
    items = get_page("/customers", page_size=100)["items"]
    records = [item for item in items if item["id"] == "CUST-0001"]

    assert len(records) == 2
    assert records[0] == records[1]


def test_customers_include_the_documented_malformed_record():
    items = get_page("/customers", page_size=100)["items"]
    records = [item for item in items if item["id"] == "CUST-9001"]

    assert len(records) == 1
    assert records[0]["email"] == "not-an-email"
