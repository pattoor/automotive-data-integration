-- Schema for the automotive data integration pipeline.
--
-- This file is the initial version of the schema. It is safe to run repeatedly:
-- every statement is CREATE ... IF NOT EXISTS, so it creates missing objects and
-- leaves existing tables and rows untouched. No statement drops or rewrites data.
--
-- Two entry points apply it:
--   1. PostgreSQL's image runs it once, at first initialization, because Compose
--      mounts it at /docker-entrypoint-initdb.d/001_schema.sql.
--   2. pipeline-api calls PostgresRepository.initialize_schema() at startup,
--      which covers databases created before this file existed (the existing G7
--      PGDATA directory) and any checkout that runs without Compose.
--
-- Because this file is already applied to a live database, later changes must
-- not be edited in place: add database/migrations/NNN_description.sql and apply
-- it explicitly. Editing this file does not alter an existing database.

CREATE TABLE IF NOT EXISTS customers (
    crm_id      text        PRIMARY KEY,
    first_name  text        NOT NULL,
    last_name   text        NOT NULL,
    email       text        NOT NULL,
    phone       text,
    city        text,
    created_at  timestamptz NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT customers_crm_id_length
        CHECK (char_length(crm_id) BETWEEN 1 AND 64),
    CONSTRAINT customers_first_name_not_blank
        CHECK (btrim(first_name) <> ''),
    CONSTRAINT customers_last_name_not_blank
        CHECK (btrim(last_name) <> ''),
    CONSTRAINT customers_email_normalized
        CHECK (email <> '' AND email = lower(email))
);

CREATE TABLE IF NOT EXISTS vehicles (
    crm_id           text        PRIMARY KEY,
    customer_crm_id  text        NOT NULL
        REFERENCES customers (crm_id) ON DELETE RESTRICT,
    vin              text        NOT NULL,
    make             text        NOT NULL,
    model            text        NOT NULL,
    year             integer     NOT NULL,
    odometer_km      integer     NOT NULL,
    updated_at       timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT vehicles_crm_id_length
        CHECK (char_length(crm_id) BETWEEN 1 AND 64),
    CONSTRAINT vehicles_vin_format
        CHECK (vin ~ '^[A-HJ-NPR-Z0-9]{17}$'),
    CONSTRAINT vehicles_make_not_blank
        CHECK (btrim(make) <> ''),
    CONSTRAINT vehicles_model_not_blank
        CHECK (btrim(model) <> ''),
    CONSTRAINT vehicles_year_range
        CHECK (year BETWEEN 1886 AND 2100),
    CONSTRAINT vehicles_odometer_range
        CHECK (odometer_km BETWEEN 0 AND 2000000)
);

CREATE INDEX IF NOT EXISTS vehicles_customer_crm_id_idx
    ON vehicles (customer_crm_id);

CREATE TABLE IF NOT EXISTS sales (
    crm_id           text        PRIMARY KEY,
    customer_crm_id  text        NOT NULL
        REFERENCES customers (crm_id) ON DELETE RESTRICT,
    vehicle_crm_id   text        NOT NULL
        REFERENCES vehicles (crm_id) ON DELETE RESTRICT,
    sale_date        date        NOT NULL,
    amount_usd       numeric(12, 2) NOT NULL,
    status           text        NOT NULL,
    updated_at       timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT sales_crm_id_length
        CHECK (char_length(crm_id) BETWEEN 1 AND 64),
    CONSTRAINT sales_amount_positive
        CHECK (amount_usd > 0),
    CONSTRAINT sales_status_not_blank
        CHECK (btrim(status) <> '' AND char_length(status) <= 32)
);

CREATE INDEX IF NOT EXISTS sales_customer_crm_id_idx
    ON sales (customer_crm_id);
CREATE INDEX IF NOT EXISTS sales_vehicle_crm_id_idx
    ON sales (vehicle_crm_id);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id               bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status           text        NOT NULL DEFAULT 'running',
    started_at       timestamptz NOT NULL DEFAULT now(),
    finished_at      timestamptz,
    fetched_count    integer     NOT NULL DEFAULT 0,
    accepted_count   integer     NOT NULL DEFAULT 0,
    rejected_count   integer     NOT NULL DEFAULT 0,
    duplicate_count  integer     NOT NULL DEFAULT 0,
    error_message    text,

    CONSTRAINT pipeline_runs_status_valid
        CHECK (status IN ('running', 'succeeded', 'failed')),
    CONSTRAINT pipeline_runs_counts_non_negative
        CHECK (
            fetched_count >= 0
            AND accepted_count >= 0
            AND rejected_count >= 0
            AND duplicate_count >= 0
        ),
    CONSTRAINT pipeline_runs_finished_after_started
        CHECK (finished_at IS NULL OR finished_at >= started_at)
);

CREATE TABLE IF NOT EXISTS rejected_records (
    id           bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id       bigint      NOT NULL
        REFERENCES pipeline_runs (id) ON DELETE CASCADE,
    entity       text        NOT NULL,
    source_id    text,
    raw_payload  jsonb       NOT NULL,
    reason       text        NOT NULL,
    rejected_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT rejected_records_entity_valid
        CHECK (entity IN ('customer', 'vehicle', 'sale')),
    CONSTRAINT rejected_records_reason_not_blank
        CHECK (btrim(reason) <> '')
);

CREATE INDEX IF NOT EXISTS rejected_records_run_id_idx
    ON rejected_records (run_id);
