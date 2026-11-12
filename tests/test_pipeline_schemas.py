"""Contracts for CRM source records and their normalized integration form."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from automotive_data_integration.pipeline_api.schemas import Customer, Sale, Vehicle


def test_customer_contract_normalizes_source_record():
    record = {
        "id": "  CUST-0001  ",
        "first_name": "  Amara ",
        "last_name": "Nakamura ",
        "email": "  Amara.Nakamura@Example.TEST ",
        "phone": " +1-555-0101 ",
        "city": " Springfield ",
        "created_at": "2024-01-05T09:00:00Z",
    }

    customer = Customer.model_validate(record)

    assert customer.crm_id == "CUST-0001"
    assert customer.first_name == "Amara"
    assert customer.last_name == "Nakamura"
    assert customer.email == "amara.nakamura@example.test"
    assert customer.phone == "+1-555-0101"
    assert customer.city == "Springfield"
    assert customer.created_at == datetime(2024, 1, 5, 9, 0, tzinfo=UTC)


def test_vehicle_contract_normalizes_vin_and_keys():
    record = {
        "id": " VEH-0001 ",
        "customer_id": " CUST-0001 ",
        "vin": " syn00000000000001 ",
        "make": " Ficta ",
        "model": "Vela ",
        "year": 2021,
        "odometer_km": 41250,
    }

    vehicle = Vehicle.model_validate(record)

    assert vehicle.crm_id == "VEH-0001"
    assert vehicle.customer_crm_id == "CUST-0001"
    assert vehicle.vin == "SYN00000000000001"
    assert vehicle.make == "Ficta"
    assert vehicle.model == "Vela"
    assert vehicle.year == 2021
    assert vehicle.odometer_km == 41250


def test_sale_contract_normalizes_status_dates_and_money():
    record = {
        "id": "SALE-0001",
        "customer_id": "CUST-0001",
        "vehicle_id": "VEH-0001",
        "sale_date": "2024-02-10",
        "amount_usd": 21500.00,
        "status": " Completed ",
    }

    sale = Sale.model_validate(record)

    assert sale.crm_id == "SALE-0001"
    assert sale.customer_crm_id == "CUST-0001"
    assert sale.vehicle_crm_id == "VEH-0001"
    assert sale.sale_date == date(2024, 2, 10)
    assert sale.amount_usd == Decimal("21500.00")
    assert sale.status == "COMPLETED"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("email", "not-an-email", id="invalid-email"),
        pytest.param("created_at", "2024-13-45T99:99:99Z", id="invalid-timestamp"),
        pytest.param("first_name", None, id="missing-first-name"),
    ],
)
def test_customer_contract_rejects_malformed_source_values(field, value):
    valid = {
        "id": "CUST-0001",
        "first_name": "Amara",
        "last_name": "Nakamura",
        "email": "amara.nakamura@example.test",
        "phone": "+1-555-0101",
        "city": "Springfield",
        "created_at": "2024-01-05T09:00:00Z",
    }
    record = {**valid, field: value}

    with pytest.raises(ValidationError) as excinfo:
        Customer.model_validate(record)

    assert [error["loc"] for error in excinfo.value.errors()] == [(field,)]
