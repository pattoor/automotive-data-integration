# Data Dictionary

This reference describes every field the pipeline touches: the synthetic CRM payloads, the normalized records produced by `pipeline-api`, and the five PostgreSQL tables defined in `database/schema.sql`.

**Synthetic scope only.** Every record is fictional. Emails use the reserved `.test` domain, phone numbers use the reserved `555-01xx` range, and VINs use a `SYN` prefix with ISO 3779-legal characters. No value in this document is derived from a real customer, vehicle, or sale, and the pipeline is not connected to a production CRM.

## Data path

```text
crm-api (raw JSON, paginated)
    │  GET /customers, /vehicles, /sales
    ▼
pipeline-api transform (Pydantic validation + normalization, per record)
    │  accepted → normalized record
    │  rejected → raw payload + reason
    ▼
PostgreSQL (customers, vehicles, sales, pipeline_runs, rejected_records)
```

- `crm-api` serves raw fixture rows. It never normalizes, validates, or deduplicates.
- `pipeline-api` normalizes a copy of each row. The source dictionaries are never mutated.
- A row that fails validation is quarantined with its **exact** raw payload and a reason naming the failing fields; it never aborts the batch.
- Persistence is parent-first (customers, then vehicles, then sales) so foreign keys are satisfied.

Cross-run state lives only in PostgreSQL, so repeating a run upserts the same rows instead of adding duplicates. See [run semantics](ARCHITECTURE.md#pipeline-run-semantics) and [persistence decisions](ARCHITECTURE.md#decisions-and-alternatives).

## CRM source fields to normalized fields

CRM identifiers are the integration keys. `id` is renamed to `crm_id`, and `customer_id`/`vehicle_id` become `customer_crm_id`/`vehicle_crm_id` so a foreign key is never mistaken for a local surrogate key.

| Entity | CRM source field | Normalized field | Rule |
|---|---|---|---|
| Customer | `id` | `crm_id` | Trimmed, required, 1–64 characters. |
| Customer | `first_name`, `last_name` | Same names | Trimmed, required, 1–160 characters. |
| Customer | `email` | `email` | Trimmed, validated with deliverability checks disabled and reserved-domain mode enabled (so `.test` is allowed), then lowercased. |
| Customer | `phone`, `city` | Same names | Trimmed, 1–64 characters; a blank value becomes `null`. |
| Customer | `created_at` | `created_at` | ISO 8601 timestamp parsed to a `datetime`; the fixtures are UTC. |
| Vehicle | `id` | `crm_id` | Trimmed, required, 1–64 characters. |
| Vehicle | `customer_id` | `customer_crm_id` | Trimmed, required, 1–64 characters. |
| Vehicle | `vin` | `vin` | Trimmed and uppercased, exactly 17 characters matching `^[A-HJ-NPR-Z0-9]{17}$` (ISO 3779 excludes `I`, `O`, `Q`). |
| Vehicle | `make`, `model` | Same names | Trimmed, required, 1–160 characters. |
| Vehicle | `year` | `year` | Integer from 1886 through 2100. |
| Vehicle | `odometer_km` | `odometer_km` | Integer from 0 through 2,000,000. |
| Sale | `id` | `crm_id` | Trimmed, required, 1–64 characters. |
| Sale | `customer_id` | `customer_crm_id` | Trimmed, required, 1–64 characters. |
| Sale | `vehicle_id` | `vehicle_crm_id` | Trimmed, required, 1–64 characters. |
| Sale | `sale_date` | `sale_date` | ISO date parsed to `date`. |
| Sale | `status` | `status` | Trimmed, uppercased, 1–32 characters. |
| Sale | `amount_usd` | `amount_usd` | `Decimal` greater than zero, at most 12 digits in total with at most 2 decimal places. |

Unknown CRM fields are ignored rather than rejected, so the source can grow a column without breaking the contracts. The normalized models are frozen: an accepted record is immutable for the rest of the run.

### Fixtures that exercise the rules

The synthetic source is small and deliberately imperfect:

| Fixture | Purpose | Expected effect |
|---|---|---|
| `CUST-0001` appears twice with identical values | Prove source deduplication | `duplicate_count` reports 1 and only one customer row is persisted. |
| `CUST-9001` has `email = "not-an-email"` and `created_at = "2024-13-45T99:99:99Z"` | Prove validation and quarantine | The row is rejected with its exact payload and a reason naming `email` and `created_at`; no customer row is created. |
| Five vehicles referencing `CUST-0001`…`CUST-0005` | Prove parent-first loading | Each vehicle is persisted only after its customer. |
| Five sales referencing both a customer and a vehicle | Prove relationship validation | Each sale is persisted only after its customer and vehicle. |

A default run therefore fetches 17 rows, persists 15 entities (5 customers, 5 vehicles, 5 sales), rejects 1 row, and counts 1 duplicate. The duplicate is counted, not persisted twice.

## Tables

All five tables are created by `database/schema.sql` with `CREATE TABLE IF NOT EXISTS`, so the file is the authoritative definition. Types below are the exact PostgreSQL types.

### `customers`

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `crm_id` | `text` | No | — | Primary key. CRM identifier. |
| `first_name` | `text` | No | — | Nonblank. |
| `last_name` | `text` | No | — | Nonblank. |
| `email` | `text` | No | — | Nonempty and already lowercased. |
| `phone` | `text` | Yes | — | Optional; `null` when the source was blank. |
| `city` | `text` | Yes | — | Optional; `null` when the source was blank. |
| `created_at` | `timestamptz` | No | — | Supplied by the CRM and stored as received after parsing. |
| `updated_at` | `timestamptz` | No | `now()` | Written by the database only; set on insert and refreshed on every upsert. It is **not** a CRM field. |

Constraints: `customers_crm_id_length` (`char_length(crm_id) BETWEEN 1 AND 64`), `customers_first_name_not_blank`, `customers_last_name_not_blank` (`btrim(...) <> ''`), and `customers_email_normalized` (`email <> '' AND email = lower(email)`).

### `vehicles`

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `crm_id` | `text` | No | — | Primary key. CRM identifier. |
| `customer_crm_id` | `text` | No | — | Foreign key to `customers (crm_id)`, `ON DELETE RESTRICT`. |
| `vin` | `text` | No | — | Must match `^[A-HJ-NPR-Z0-9]{17}$`. |
| `make` | `text` | No | — | Nonblank. |
| `model` | `text` | No | — | Nonblank. |
| `year` | `integer` | No | — | 1886–2100. |
| `odometer_km` | `integer` | No | — | 0–2,000,000. |
| `updated_at` | `timestamptz` | No | `now()` | Database-written; refreshed on every upsert. Not a CRM field. |

Constraints: `vehicles_crm_id_length`, `vehicles_vin_format`, `vehicles_make_not_blank`, `vehicles_model_not_blank`, `vehicles_year_range`, `vehicles_odometer_range`. Index `vehicles_customer_crm_id_idx` supports lookups by parent.

### `sales`

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `crm_id` | `text` | No | — | Primary key. CRM identifier. |
| `customer_crm_id` | `text` | No | — | Foreign key to `customers (crm_id)`, `ON DELETE RESTRICT`. |
| `vehicle_crm_id` | `text` | No | — | Foreign key to `vehicles (crm_id)`, `ON DELETE RESTRICT`. |
| `sale_date` | `date` | No | — | Calendar date from the CRM. |
| `amount_usd` | `numeric(12, 2)` | No | — | Greater than zero. |
| `status` | `text` | No | — | Nonblank, at most 32 characters; stored uppercased by the API. |
| `updated_at` | `timestamptz` | No | `now()` | Database-written; refreshed on every upsert. Not a CRM field. |

Constraints: `sales_crm_id_length`, `sales_amount_positive` (`amount_usd > 0`), and `sales_status_not_blank` (`btrim(status) <> '' AND char_length(status) <= 32`). Indexes `sales_customer_crm_id_idx` and `sales_vehicle_crm_id_idx` support parent lookups.

### `pipeline_runs`

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `bigint` | No | identity | `GENERATED ALWAYS AS IDENTITY` primary key; the application never supplies it. This value is the `run_id` returned by `POST /pipeline/runs`. |
| `status` | `text` | No | `'running'` | One of `running`, `succeeded`, `failed`. |
| `started_at` | `timestamptz` | No | `now()` | Written when the run row is created, before extraction. |
| `finished_at` | `timestamptz` | Yes | — | Set once when the run is finalized; `null` while running. |
| `fetched_count` | `integer` | No | `0` | Nonnegative. See [count semantics](#count-and-status-semantics). |
| `accepted_count` | `integer` | No | `0` | Nonnegative. |
| `rejected_count` | `integer` | No | `0` | Nonnegative. |
| `duplicate_count` | `integer` | No | `0` | Nonnegative. |
| `error_message` | `text` | Yes | — | Populated only for a failed run; names the failure class, never a payload or credential. |

Constraints: `pipeline_runs_status_valid`, `pipeline_runs_counts_non_negative`, and `pipeline_runs_finished_after_started` (`finished_at IS NULL OR finished_at >= started_at`).

A run is created in `running` status and finalized exactly once to `succeeded` or `failed`. The repository refuses to finalize a run that is missing or already final.

### `rejected_records`

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `bigint` | No | identity | `GENERATED ALWAYS AS IDENTITY` primary key. |
| `run_id` | `bigint` | No | — | Foreign key to `pipeline_runs (id)`, `ON DELETE CASCADE`. |
| `entity` | `text` | No | — | One of `customer`, `vehicle`, `sale`. |
| `source_id` | `text` | Yes | — | Trimmed source `id` when the row had one; `null` when it did not. |
| `raw_payload` | `jsonb` | No | — | Exact source row, preserving nested objects and arrays. |
| `reason` | `text` | No | — | Nonblank; from validation errors or unresolved-parent checks. |
| `rejected_at` | `timestamptz` | No | `now()` | Written when the rejection row is stored. |

Constraints: `rejected_records_entity_valid`, `rejected_records_reason_not_blank`. Index `rejected_records_run_id_idx` supports inspection by run.

Two reasons are recorded: a Pydantic validation failure (for example `email: Value error, not a valid email address: ...`) and an unresolved parent reference (`customer_crm_id: references unknown or rejected customer CUST-0001`, or the equivalent for `vehicle_crm_id`).

## Relationships

```text
customers ──1:N──► vehicles ──1:N──► sales
    │                                   ▲
    └──────────────1:N──────────────────┘

pipeline_runs ──1:N──► rejected_records   (cascade on run removal)
```

- A vehicle references an **accepted** customer, and a sale references an **accepted** customer and an **accepted** vehicle. References are checked against the batch before writing, so a broken link is quarantined rather than sent to PostgreSQL.
- Foreign keys use `ON DELETE RESTRICT` for entities: a parent row cannot be removed while children reference it.
- Rejected records cascade with their run, so run history can be removed as one unit without leaving orphans.
- The schema does **not** require that a sale's vehicle belongs to the sale's customer. The fixtures satisfy that rule, and enforcing it would be an additional cross-record policy beyond this stage.
- Entity tables store normalized values only; the exact accepted source payload is not retained. Rejected payloads are retained, because they are the audit trail.

## Count and status semantics

| Field | Definition |
|---|---|
| `fetched` | Every source row read across all three collections, including duplicates and invalid rows. |
| `accepted` | Every entity actually persisted by the upserts. Counted from the write row counts, so an upsert that updates an existing row still counts. |
| `rejected` | Every quarantined row: validation failures plus unresolved parent references. |
| `duplicate` | Every repeated non-empty source identifier across the full collected batch. |

Notes that follow from the implementation:

- Duplicate detection runs per collection, on the trimmed source `id`, and is case-sensitive. A row with a missing or blank `id` is never counted as a duplicate; it is rejected on its own.
- Duplicate counting inspects raw rows before validation, so a malformed repeated row can contribute to both `duplicate` and `rejected`. Among valid rows with the same identifier, the first valid occurrence is accepted.
- A run finalizes as `succeeded` even when individual rows were rejected. Only a CRM failure (HTTP `502`) or a database/configuration failure (HTTP `503`) finalizes it as `failed`.
- If PostgreSQL is unreachable while marking a failed run, the row can remain `running`. Run state lives in the same database that failed.

The full lifecycle, failure behavior, and the trade-offs behind it are in [Pipeline run semantics](ARCHITECTURE.md#pipeline-run-semantics) and [Decisions and alternatives](ARCHITECTURE.md#decisions-and-alternatives). To inspect these values, see [SQL examples](SQL_EXAMPLES.md); for operational problems, see [Troubleshooting](TROUBLESHOOTING.md).
