"""Pure batch transforms from raw CRM records to validated integration records.

Each supplied record is processed independently: a rejected record never stops
the batch and is returned with its exact raw payload plus a human-readable
reason. Pandas counts repeated source identifiers, while Pydantic validates
every row. Among accepted rows sharing an identifier, the first valid record
wins; an invalid earlier duplicate cannot hide a later valid record.
"""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

import pandas as pd
from pydantic import BaseModel, ValidationError

from automotive_data_integration.pipeline_api.schemas import Customer, Sale, Vehicle

Record = TypeVar("Record", bound=BaseModel)


@dataclass(frozen=True)
class RejectedRecord:
    """A source record that could not be normalized into an integration record."""

    entity: str
    source_id: str | None
    raw: Any
    reason: str


@dataclass(frozen=True)
class TransformResult(Generic[Record]):
    """Accepted records, their aligned source payloads, quarantined rows, and duplicates.

    ``accepted_raw`` is index-aligned with ``accepted`` and holds a deep copy of
    the source row, so a later relationship check can quarantine the exact
    payload that produced an accepted record.
    """

    accepted: list[Record]
    accepted_raw: list[Any]
    rejected: list[RejectedRecord]
    duplicate_count: int


def transform_customers(records: list[dict[str, Any]]) -> TransformResult[Customer]:
    """Normalize a batch of raw customer records."""
    return _transform(records, entity="customer", model=Customer)


def transform_vehicles(records: list[dict[str, Any]]) -> TransformResult[Vehicle]:
    """Normalize a batch of raw vehicle records."""
    return _transform(records, entity="vehicle", model=Vehicle)


def transform_sales(records: list[dict[str, Any]]) -> TransformResult[Sale]:
    """Normalize a batch of raw sale records."""
    return _transform(records, entity="sale", model=Sale)


def _transform(
    records: list[dict[str, Any]], *, entity: str, model: type[Record]
) -> TransformResult[Record]:
    duplicate_count = _count_duplicate_identifiers(records)

    accepted: list[Record] = []
    accepted_raw: list[Any] = []
    rejected: list[RejectedRecord] = []
    accepted_ids: set[str] = set()
    for record in records:
        try:
            normalized = model.model_validate(record)
        except ValidationError as error:
            rejected.append(
                RejectedRecord(
                    entity=entity,
                    source_id=_source_id(record),
                    raw=deepcopy(record),
                    reason=_describe(error),
                )
            )
            continue

        if normalized.crm_id in accepted_ids:
            continue
        accepted_ids.add(normalized.crm_id)
        accepted.append(normalized)
        accepted_raw.append(deepcopy(record))

    return TransformResult(
        accepted=accepted,
        accepted_raw=accepted_raw,
        rejected=rejected,
        duplicate_count=duplicate_count,
    )


def _count_duplicate_identifiers(records: list[dict[str, Any]]) -> int:
    """Count repeated non-empty CRM ids without dropping rows before validation.

    Records without an identifier are left in place, so each one reaches
    validation and gets its own rejection reason instead of being collapsed
    into a single duplicate count. This also lets a valid later record survive
    when an earlier row with the same id is malformed.
    """
    if not records:
        return 0

    frame = pd.DataFrame(
        {"source_id": [_source_id(record) for record in records]}
    )
    identified = frame.dropna(subset=["source_id"])
    duplicate_count = identified.duplicated(
        subset=["source_id"], keep="first"
    ).sum()
    return int(duplicate_count)


def _source_id(record: Any) -> str | None:
    """Return the trimmed CRM identifier from a raw record, when present."""
    if not isinstance(record, dict):
        return None
    value = record.get("id")
    if value is None or (pd.api.types.is_scalar(value) and pd.isna(value)):
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def _describe(error: ValidationError) -> str:
    """Flatten Pydantic errors into one reason that names the failing fields."""
    parts = []
    for detail in error.errors():
        location = ".".join(str(part) for part in detail["loc"]) or "record"
        parts.append(f"{location}: {detail['msg']}")
    return "; ".join(parts)
