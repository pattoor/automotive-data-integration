"""Batch transforms from CRM source records to validated integration records."""

import copy

import pytest

from automotive_data_integration.crm_api.fixtures import CUSTOMERS, SALES, VEHICLES
from automotive_data_integration.pipeline_api.transform import (
    transform_customers,
    transform_sales,
    transform_vehicles,
)


def raw_customer(crm_id="CUST-0001", **overrides):
    record = {
        "id": crm_id,
        "first_name": "Amara",
        "last_name": "Nakamura",
        "email": "amara.nakamura@example.test",
        "phone": "+1-555-0101",
        "city": "Springfield",
        "created_at": "2024-01-05T09:00:00Z",
    }
    record.update(overrides)
    return record


def raw_vehicle(crm_id="VEH-0001", **overrides):
    record = {
        "id": crm_id,
        "customer_id": "CUST-0001",
        "vin": "SYN00000000000001",
        "make": "Ficta",
        "model": "Vela",
        "year": 2021,
        "odometer_km": 41250,
    }
    record.update(overrides)
    return record


def raw_sale(crm_id="SALE-0001", **overrides):
    record = {
        "id": crm_id,
        "customer_id": "CUST-0001",
        "vehicle_id": "VEH-0001",
        "sale_date": "2024-02-10",
        "amount_usd": 21500.00,
        "status": "completed",
    }
    record.update(overrides)
    return record


def test_valid_customers_are_accepted_and_normalized():
    records = [
        raw_customer(" CUST-0001 ", email=" Amara.Nakamura@Example.TEST "),
        raw_customer("CUST-0002", first_name="Bruno", email="bruno@example.test"),
    ]

    result = transform_customers(records)

    assert [customer.crm_id for customer in result.accepted] == [
        "CUST-0001",
        "CUST-0002",
    ]
    assert result.accepted[0].email == "amara.nakamura@example.test"
    assert result.accepted[1].first_name == "Bruno"
    assert result.rejected == []
    assert result.duplicate_count == 0


def test_malformed_customer_is_rejected_with_its_raw_payload_and_reason():
    record = raw_customer(
        "CUST-9001",
        first_name="Malformed",
        email="not-an-email",
        phone=None,
        city=None,
    )
    expected_raw = copy.deepcopy(record)

    result = transform_customers([record])

    assert result.accepted == []
    assert len(result.rejected) == 1

    rejected = result.rejected[0]
    assert rejected.entity == "customer"
    assert rejected.source_id == "CUST-9001"
    assert rejected.raw == expected_raw
    assert "email" in rejected.reason
    assert result.duplicate_count == 0


def test_rejected_payload_is_a_snapshot_not_an_alias_of_the_source_record():
    record = raw_customer(
        "CUST-9001",
        email="not-an-email",
        source_meta={"batch_tags": ["original"]},
    )
    expected_raw = copy.deepcopy(record)

    result = transform_customers([record])
    record["email"] = "corrected@example.test"
    record["source_meta"]["batch_tags"].append("mutated")

    assert result.rejected[0].raw == expected_raw


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        pytest.param({"year": 1500}, "year", id="year-too-old"),
        pytest.param({"odometer_km": -5}, "odometer_km", id="negative-odometer"),
        pytest.param({"vin": "SYN-TOO-SHORT"}, "vin", id="malformed-vin"),
    ],
)
def test_invalid_vehicle_values_are_rejected(overrides, field):
    result = transform_vehicles([raw_vehicle(**overrides)])

    assert result.accepted == []
    assert len(result.rejected) == 1

    rejected = result.rejected[0]
    assert rejected.entity == "vehicle"
    assert rejected.source_id == "VEH-0001"
    assert field in rejected.reason
    assert result.duplicate_count == 0


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        pytest.param({"amount_usd": -1.0}, "amount_usd", id="negative-amount"),
        pytest.param({"sale_date": "2024-02-30"}, "sale_date", id="impossible-date"),
        pytest.param({"status": "   "}, "status", id="blank-status"),
    ],
)
def test_invalid_sale_values_are_rejected(overrides, field):
    result = transform_sales([raw_sale(**overrides)])

    assert result.accepted == []
    assert len(result.rejected) == 1

    rejected = result.rejected[0]
    assert rejected.entity == "sale"
    assert rejected.source_id == "SALE-0001"
    assert field in rejected.reason
    assert result.duplicate_count == 0


def test_duplicate_ids_keep_the_first_occurrence_and_count_separately():
    records = [
        raw_customer("CUST-0001", city="Springfield"),
        raw_customer("CUST-0002", city="Riverton"),
        raw_customer("CUST-0001", city="Lakeside"),
        raw_customer("CUST-0002", city="Fairview"),
        raw_customer("CUST-0001", city="Brookfield"),
    ]

    result = transform_customers(records)

    assert [customer.crm_id for customer in result.accepted] == [
        "CUST-0001",
        "CUST-0002",
    ]
    assert [customer.city for customer in result.accepted] == [
        "Springfield",
        "Riverton",
    ]
    assert result.rejected == []
    assert result.duplicate_count == 3


def test_missing_ids_are_rejected_individually_instead_of_deduplicated():
    records = [
        raw_customer(None),
        {key: value for key, value in raw_customer().items() if key != "id"},
    ]

    result = transform_customers(records)

    assert result.accepted == []
    assert [rejected.source_id for rejected in result.rejected] == [None, None]
    assert all("id" in rejected.reason for rejected in result.rejected)
    assert result.duplicate_count == 0


def test_nan_like_ids_are_rejected_individually_and_not_counted_as_duplicates():
    records = [raw_customer(float("nan")), raw_customer(float("nan"))]

    result = transform_customers(records)

    assert result.accepted == []
    assert [rejected.source_id for rejected in result.rejected] == [None, None]
    assert result.duplicate_count == 0


@pytest.mark.parametrize(
    "transform",
    [
        pytest.param(transform_customers, id="customers"),
        pytest.param(transform_vehicles, id="vehicles"),
        pytest.param(transform_sales, id="sales"),
    ],
)
def test_empty_batch_returns_an_empty_result(transform):
    result = transform([])

    assert result.accepted == []
    assert result.rejected == []
    assert result.duplicate_count == 0


def test_mixed_batch_keeps_valid_rows_and_rejects_only_the_bad_one():
    records = [
        raw_customer("CUST-0001"),
        raw_customer("CUST-0002", email="not-an-email"),
        raw_customer("CUST-0003", first_name="Carla"),
    ]

    result = transform_customers(records)

    assert [customer.crm_id for customer in result.accepted] == [
        "CUST-0001",
        "CUST-0003",
    ]
    assert [rejected.source_id for rejected in result.rejected] == ["CUST-0002"]
    assert result.duplicate_count == 0


def test_invalid_first_duplicate_does_not_hide_a_later_valid_record():
    records = [
        raw_customer("CUST-0001", email="not-an-email"),
        raw_customer("CUST-0001", email="recovered@example.test"),
        raw_customer("CUST-0002"),
    ]

    result = transform_customers(records)

    assert [customer.crm_id for customer in result.accepted] == [
        "CUST-0001",
        "CUST-0002",
    ]
    assert result.accepted[0].email == "recovered@example.test"
    assert [rejected.source_id for rejected in result.rejected] == ["CUST-0001"]
    assert "email" in result.rejected[0].reason
    assert result.rejected[0].raw["email"] == "not-an-email"
    assert result.duplicate_count == 1


def test_invalid_repeat_after_a_valid_record_is_still_quarantined():
    records = [
        raw_customer("CUST-0001"),
        raw_customer("CUST-0001", email="not-an-email"),
    ]

    result = transform_customers(records)

    assert [customer.crm_id for customer in result.accepted] == ["CUST-0001"]
    assert [rejected.source_id for rejected in result.rejected] == ["CUST-0001"]
    assert result.rejected[0].raw["email"] == "not-an-email"
    assert result.duplicate_count == 1


def test_transform_does_not_mutate_the_source_records():
    records = [raw_customer(" CUST-0001 "), raw_vehicle(), raw_sale()]
    before = copy.deepcopy(records)

    transform_customers([records[0]])
    transform_vehicles([records[1]])
    transform_sales([records[2]])

    assert records == before


def test_accepted_records_keep_aligned_raw_payload_snapshots():
    records = [
        raw_customer("CUST-0001", city="Springfield"),
        raw_customer("CUST-0001", email="not-an-email"),
        raw_customer("CUST-0002", city="Riverton"),
    ]
    expected_raw = copy.deepcopy([records[0], records[2]])

    result = transform_customers(records)
    records[0]["city"] = "Mutated"
    records[2]["city"] = "Mutated"

    assert [customer.crm_id for customer in result.accepted] == [
        "CUST-0001",
        "CUST-0002",
    ]
    assert result.accepted_raw == expected_raw


def test_crm_customer_fixtures_yield_the_documented_batch_counts():
    result = transform_customers(CUSTOMERS)

    assert [customer.crm_id for customer in result.accepted] == [
        "CUST-0001",
        "CUST-0002",
        "CUST-0003",
        "CUST-0004",
        "CUST-0005",
    ]
    assert [rejected.source_id for rejected in result.rejected] == ["CUST-9001"]
    assert result.duplicate_count == 1


def test_crm_vehicle_and_sale_fixtures_are_fully_accepted():
    vehicles = transform_vehicles(VEHICLES)
    sales = transform_sales(SALES)

    assert len(vehicles.accepted) == 5
    assert vehicles.rejected == []
    assert vehicles.duplicate_count == 0
    assert len(sales.accepted) == 5
    assert sales.rejected == []
    assert sales.duplicate_count == 0
