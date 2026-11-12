"""Deterministic synthetic CRM fixtures.

Every record is fictional. Emails use the reserved ``.test`` domain, phone
numbers use the reserved ``555-01xx`` range, and VINs use a ``SYN`` prefix with
only ISO 3779-legal characters. No fixture is derived from a real customer,
vehicle, or sale.
"""

from typing import Any

CUSTOMERS: list[dict[str, Any]] = [
    {
        "id": "CUST-0001",
        "first_name": "Amara",
        "last_name": "Nakamura",
        "email": "amara.nakamura@example.test",
        "phone": "+1-555-0101",
        "city": "Springfield",
        "created_at": "2024-01-05T09:00:00Z",
    },
    {
        "id": "CUST-0002",
        "first_name": "Bruno",
        "last_name": "Almeida",
        "email": "bruno.almeida@example.test",
        "phone": "+1-555-0102",
        "city": "Riverton",
        "created_at": "2024-01-12T14:30:00Z",
    },
    {
        "id": "CUST-0003",
        "first_name": "Carla",
        "last_name": "Okafor",
        "email": "carla.okafor@example.test",
        "phone": "+1-555-0103",
        "city": "Fairview",
        "created_at": "2024-02-03T11:15:00Z",
    },
    {
        "id": "CUST-0004",
        "first_name": "Diego",
        "last_name": "Ferreyra",
        "email": "diego.ferreyra@example.test",
        "phone": "+1-555-0104",
        "city": "Lakeside",
        "created_at": "2024-02-20T16:45:00Z",
    },
    {
        "id": "CUST-0005",
        "first_name": "Elena",
        "last_name": "Petrova",
        "email": "elena.petrova@example.test",
        "phone": "+1-555-0105",
        "city": "Brookfield",
        "created_at": "2024-03-08T08:20:00Z",
    },
    # Deliberate source duplicate: an exact repeat of CUST-0001, as a CRM export
    # can contain. Stage 2 must detect it and the pipeline must count it instead
    # of inserting a second customer.
    {
        "id": "CUST-0001",
        "first_name": "Amara",
        "last_name": "Nakamura",
        "email": "amara.nakamura@example.test",
        "phone": "+1-555-0101",
        "city": "Springfield",
        "created_at": "2024-01-05T09:00:00Z",
    },
    # Deliberate malformed record: invalid email, missing phone/city, and an
    # impossible timestamp. Stage 2 validation must reject it and record why.
    {
        "id": "CUST-9001",
        "first_name": "Malformed",
        "last_name": "Fixture",
        "email": "not-an-email",
        "phone": None,
        "city": None,
        "created_at": "2024-13-45T99:99:99Z",
    },
]

VEHICLES: list[dict[str, Any]] = [
    {
        "id": "VEH-0001",
        "customer_id": "CUST-0001",
        "vin": "SYN00000000000001",
        "make": "Ficta",
        "model": "Vela",
        "year": 2021,
        "odometer_km": 41250,
    },
    {
        "id": "VEH-0002",
        "customer_id": "CUST-0002",
        "vin": "SYN00000000000002",
        "make": "Ficta",
        "model": "Vela",
        "year": 2022,
        "odometer_km": 18700,
    },
    {
        "id": "VEH-0003",
        "customer_id": "CUST-0003",
        "vin": "SYN00000000000003",
        "make": "Noma",
        "model": "Trek",
        "year": 2020,
        "odometer_km": 63800,
    },
    {
        "id": "VEH-0004",
        "customer_id": "CUST-0004",
        "vin": "SYN00000000000004",
        "make": "Noma",
        "model": "Trek",
        "year": 2023,
        "odometer_km": 5400,
    },
    {
        "id": "VEH-0005",
        "customer_id": "CUST-0005",
        "vin": "SYN00000000000005",
        "make": "Ficta",
        "model": "Aria",
        "year": 2019,
        "odometer_km": 92500,
    },
]

SALES: list[dict[str, Any]] = [
    {
        "id": "SALE-0001",
        "customer_id": "CUST-0001",
        "vehicle_id": "VEH-0001",
        "sale_date": "2024-02-10",
        "amount_usd": 21500.00,
        "status": "completed",
    },
    {
        "id": "SALE-0002",
        "customer_id": "CUST-0002",
        "vehicle_id": "VEH-0002",
        "sale_date": "2024-03-01",
        "amount_usd": 24800.00,
        "status": "completed",
    },
    {
        "id": "SALE-0003",
        "customer_id": "CUST-0003",
        "vehicle_id": "VEH-0003",
        "sale_date": "2024-04-15",
        "amount_usd": 17200.00,
        "status": "completed",
    },
    {
        "id": "SALE-0004",
        "customer_id": "CUST-0004",
        "vehicle_id": "VEH-0004",
        "sale_date": "2024-05-22",
        "amount_usd": 26900.00,
        "status": "completed",
    },
    {
        "id": "SALE-0005",
        "customer_id": "CUST-0005",
        "vehicle_id": "VEH-0005",
        "sale_date": "2024-06-30",
        "amount_usd": 13400.00,
        "status": "completed",
    },
]
