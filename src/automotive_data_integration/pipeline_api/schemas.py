"""Pydantic contracts for CRM source records.

Each model accepts one raw CRM record (the shapes served by ``crm-api``) and
normalizes it into the integration form: stable ``*_crm_id`` keys, trimmed
strings, a lowercased email, an uppercase VIN and status, and typed dates and
amounts. Unparseable input raises ``pydantic.ValidationError``; policy decisions
such as deduplication and quarantine live in ``transform``.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from email_validator import EmailNotValidError, validate_email
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

CrmId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
]
Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)
]
ContactText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
]
Status = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_upper=True, min_length=1, max_length=32),
]


def _uppercase_vin(value: Any) -> Any:
    """Trim and uppercase a VIN before the character pattern is checked."""
    return value.strip().upper() if isinstance(value, str) else value


Vin = Annotated[
    str,
    BeforeValidator(_uppercase_vin),
    StringConstraints(min_length=17, max_length=17, pattern=r"^[A-HJ-NPR-Z0-9]{17}$"),
]


def _normalize_email(value: Any) -> Any:
    """Validate and normalize an address, allowing the fixtures' ``.test`` domain.

    Pydantic's ``EmailStr`` calls email-validator with deliverability checks and
    rejects reserved domains such as ``.test``. The synthetic CRM depends on
    them, so the test-environment mode is used without DNS lookups.
    """
    if not isinstance(value, str):
        return value
    try:
        return validate_email(
            value.strip(), check_deliverability=False, test_environment=True
        ).normalized
    except EmailNotValidError as exc:
        raise ValueError(f"not a valid email address: {exc}") from exc


EmailAddress = Annotated[str, BeforeValidator(_normalize_email)]


class NormalizedRecord(BaseModel):
    """Shared strictness for accepted integration records."""

    model_config = ConfigDict(
        frozen=True,
        populate_by_name=True,
        extra="ignore",
        str_strip_whitespace=True,
    )


class Customer(NormalizedRecord):
    """A normalized customer from a raw ``id``-keyed CRM record."""

    crm_id: CrmId = Field(validation_alias="id")
    first_name: Name
    last_name: Name
    email: EmailAddress
    phone: ContactText | None = None
    city: ContactText | None = None
    created_at: datetime

    @field_validator("email", mode="after")
    @classmethod
    def _lowercase_email(cls, value: str) -> str:
        return value.lower()

    @field_validator("phone", "city", mode="before")
    @classmethod
    def _blank_optional_text_to_none(cls, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class Vehicle(NormalizedRecord):
    """A normalized vehicle, linked to its customer by CRM identifier."""

    crm_id: CrmId = Field(validation_alias="id")
    customer_crm_id: CrmId = Field(validation_alias="customer_id")
    vin: Vin
    make: Name
    model: Name
    year: int = Field(ge=1886, le=2100)
    odometer_km: int = Field(ge=0, le=2_000_000)


class Sale(NormalizedRecord):
    """A normalized sale, linked to its customer and vehicle by CRM identifier."""

    crm_id: CrmId = Field(validation_alias="id")
    customer_crm_id: CrmId = Field(validation_alias="customer_id")
    vehicle_crm_id: CrmId = Field(validation_alias="vehicle_id")
    sale_date: date
    amount_usd: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    status: Status
