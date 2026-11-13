# Automotive Data Integration

A staged, auditable data-automation portfolio project using synthetic dealership data. Its target architecture combines a mock CRM API, pipeline API, PostgreSQL, and n8n on one Docker Compose host; current implementation status is tracked by stage below and in `docs/ROADMAP.md`.

The repository is one Python codebase with **two FastAPI processes**. Stage 0 delivered the runnable foundation: package skeleton, health endpoints, container image, Compose services, and tests. Stage 1 adds deterministic synthetic CRM data with bounded pagination; Stage 2 adds Pydantic contracts and pure batch transforms that normalize and quarantine records; Stage 3 adds the PostgreSQL schema and repository that persist entities, run summaries, and rejected payloads; Stage 4 adds the paginated CRM client, the orchestration service, and `POST /pipeline/runs`; Stage 5 adds the pinned n8n service and a versioned workflow with a manual trigger and a daily schedule (see `docs/ROADMAP.md`).

## Layout

| Path | Purpose |
|---|---|
| `src/automotive_data_integration/crm_api/` | Synthetic CRM source service (`crm-api`) |
| `src/automotive_data_integration/pipeline_api/` | Consumer service (`pipeline-api`): contracts in `schemas.py`, batch transforms in `transform.py`, CRM extraction in `crm_client.py`, orchestration in `service.py`, persistence in `repository.py`, HTTP routes in `routes.py` |
| `src/automotive_data_integration/common/` | Health route and server bootstrap shared by both services |
| `database/schema.sql` | Versioned, idempotent PostgreSQL schema (initialization + startup) |
| `n8n/workflows/automotive-pipeline.json` | Versioned n8n workflow export: manual and daily schedule triggers calling the pipeline endpoint |
| `tests/` | API and transform tests with FastAPI `TestClient`; PostgreSQL integration tests skip without a database URL; n8n workflow contract test |
| `compose.yaml` | Two APIs plus PostgreSQL (`postgres:16-alpine`) and n8n (`n8nio/n8n:2.47.7`) |
| `Dockerfile` | One image, one package, two startup commands |
| `.data/` | Local container data (PostgreSQL files; git-ignored) |
| `n8n/data/` | n8n state: SQLite database, encryption key, local user settings (git-ignored) |
| `.backups/` | Host-side database dumps (git-ignored) |

## Requirements

- Docker Engine with Compose v2, or
- Python 3.11+ for local development (dependencies stay in `.venv/`)

## Run with Docker Compose

```bash
cp .env.example .env        # optional; defaults work without it
mkdir -p n8n/data           # n8n writes its SQLite database and key here
docker compose up --build
docker compose ps           # wait until the APIs and database are healthy
curl http://127.0.0.1:8000/health   # crm-api
curl http://127.0.0.1:8001/health   # pipeline-api
```

Health responses: `{"status":"ok","service":"crm-api"}` and `{"status":"ok","service":"pipeline-api"}`.

- Host ports bind to `127.0.0.1` only; PostgreSQL is not published.
- `pipeline-api` starts only after both `pg_isready` and the CRM health check succeed; `n8n` starts after `pipeline-api` is healthy.
- Database files live in `./.data/postgres` (bind-mounted to `/var/lib/postgresql/data`) and survive `docker compose down`. `docker compose down -v` does not remove a bind mount either. Remove that directory only after a deliberate backup, or when you intend a full reset.
- n8n state lives in `./n8n/data` (bind-mounted to `/home/node/.n8n`) and also survives `docker compose down`. The directory must be writable by the container's `node` user (UID/GID 1000), so create it as your normal project user before the first start. `n8n` has no Compose health check; open `http://127.0.0.1:5678` and check the editor loads.
- Containers reach each other by Compose service name, for example `http://crm-api:8000`, `http://pipeline-api:8000`, or host `postgres`.
- Schema setup is automatic: PostgreSQL applies `database/schema.sql` when it initializes an empty data directory, and `pipeline-api` applies the same idempotent file at startup, so an existing data directory gains missing tables without a reset.

## CRM API

`crm-api` serves deterministic synthetic data. Every collection is read-only and paginated:

| Endpoint | Returns |
|---|---|
| `GET /customers` | Customers, including one deliberate duplicate row and one malformed row |
| `GET /vehicles` | Vehicles with clearly synthetic `SYN…` VINs |
| `GET /sales` | Sales referencing synthetic customers and vehicles |

Query parameters:

| Parameter | Default | Accepted values |
|---|---|---|
| `page` | `1` | Integer `>= 1` |
| `page_size` | `3` | Integer `1`–`100` |

All three endpoints return the same envelope:

```json
{
  "items": [
    {
      "id": "CUST-0001",
      "first_name": "Amara",
      "last_name": "Nakamura",
      "email": "amara.nakamura@example.test",
      "phone": "+1-555-0101",
      "city": "Springfield",
      "created_at": "2024-01-05T09:00:00Z"
    }
  ],
  "page": 1,
  "page_size": 3,
  "total": 7,
  "total_pages": 3,
  "next_page": 2
}
```

`next_page` is `null` on the last page. A page beyond `total_pages` returns `200` with an empty `items` list and the collection's real `total` and `total_pages`. Values outside the bounds above return `422`.

```bash
curl "http://127.0.0.1:8000/customers"
curl "http://127.0.0.1:8000/vehicles?page=2&page_size=2"
curl "http://127.0.0.1:8000/sales?page=1&page_size=3"
```

Fixtures live in `src/automotive_data_integration/crm_api/fixtures.py`. All data is fictional: `.test` emails, reserved `555-01xx` phone numbers, and `SYN`-prefixed VINs. `CUST-0001` appears twice on purpose, and `CUST-9001` is intentionally malformed, so later stages can prove source deduplication and validation rejection against real API responses.

## Data contracts and transforms

`pipeline_api` owns normalization and validation. `schemas.py` holds one frozen Pydantic model per CRM shape; `transform.py` turns a batch of raw API rows into accepted records, quarantined rows, and a duplicate count. The API fixtures stay raw: the transform normalizes copies, never the source dictionaries.

| Entity | Raw field | Normalized field | Rule |
|---|---|---|---|
| Customer | `id` | `crm_id` | Trimmed, required, 1–64 characters |
| Customer | `first_name`, `last_name` | same | Trimmed, required |
| Customer | `email` | `email` | Trimmed, validated, lowercased (reserved `.test` domain allowed) |
| Customer | `phone`, `city` | same | Trimmed; blank becomes `null` |
| Customer | `created_at` | `created_at` | ISO 8601 timestamp parsed to `datetime` |
| Vehicle | `id` | `crm_id` | Trimmed, required |
| Vehicle | `customer_id` | `customer_crm_id` | Trimmed, required |
| Vehicle | `vin` | `vin` | Trimmed, uppercased, exactly 17 characters from the ISO 3779 set (`I`, `O`, `Q` excluded) |
| Vehicle | `make`, `model` | same | Trimmed, required |
| Vehicle | `year` | `year` | Integer `1886`–`2100` |
| Vehicle | `odometer_km` | `odometer_km` | Integer `0`–`2,000,000` |
| Sale | `id` | `crm_id` | Trimmed, required |
| Sale | `customer_id` | `customer_crm_id` | Trimmed, required |
| Sale | `vehicle_id` | `vehicle_crm_id` | Trimmed, required |
| Sale | `sale_date` | `sale_date` | ISO date parsed to `date` |
| Sale | `amount_usd` | `amount_usd` | `Decimal` greater than zero, up to 12 digits and 2 decimals |
| Sale | `status` | `status` | Trimmed and uppercased |

Each record is validated independently, so a bad row never aborts the batch:

- An accepted row becomes a `Customer`, `Vehicle`, or `Sale` model.
- A rejected row becomes a `RejectedRecord` with the entity name, the source `id` when present, the **exact** raw payload, and a reason naming the failing fields (for example `email: ...`).
- Pandas counts every repeated, non-empty CRM identifier in the batch. Pydantic still validates every row independently, so a malformed row is preserved as a rejection. Among valid rows with the same identifier, the first valid occurrence is accepted and later valid repeats are omitted. Therefore, a malformed first row cannot hide a later valid row; a malformed repeated row can contribute to both `duplicate_count` and the rejected count. Rows without an `id` are never deduplicated and each one is rejected separately.
- An empty batch returns an empty result.

```python
from automotive_data_integration.pipeline_api.transform import transform_customers

result = transform_customers(raw_customers)
result.accepted        # list[Customer]
result.rejected        # list[RejectedRecord]
result.duplicate_count # int
```

The same pattern applies to `transform_vehicles` and `transform_sales`.

## PostgreSQL persistence

`database/schema.sql` is the initial schema and `pipeline_api/repository.py` is the only code that writes to it. Both use direct SQL through `psycopg` — no ORM and no migration framework yet.

| Table | Responsibility |
|---|---|
| `customers` | One row per normalized customer keyed by `crm_id`: names, normalized lowercase email, optional phone/city, source `created_at`, and a database-written `updated_at`. |
| `vehicles` | One row per normalized vehicle keyed by `crm_id`, with `customer_crm_id` referencing `customers`. |
| `sales` | One row per normalized sale keyed by `crm_id`, with `customer_crm_id` and `vehicle_crm_id` foreign keys, `sale_date`, `amount_usd`, and `status`. |
| `pipeline_runs` | One row per pipeline execution: `status`, `started_at`/`finished_at`, fetched/accepted/rejected/duplicate counts, and `error_message`. |
| `rejected_records` | Quarantined source rows: owning `run_id`, entity, source identifier when available, the exact raw payload as `jsonb`, and the rejection reason. |

Constraint highlights: CRM identifiers are primary keys, so they are unique; `vehicles.customer_crm_id`, `sales.customer_crm_id`, and `sales.vehicle_crm_id` are enforced foreign keys; amounts use `NUMERIC(12,2)` with `amount_usd > 0`; VIN, year, odometer, status, and run-count checks reject implausible values; a run cannot finish before it starts. Rejected payloads keep their original JSON shape, including nested objects and arrays.

```python
from automotive_data_integration.pipeline_api.repository import PostgresRepository

repository = PostgresRepository(dsn)
repository.initialize_schema()                      # idempotent; safe on every startup
repository.upsert_customers(customers)              # -> rows written
repository.upsert_vehicles(vehicles)                # after their customers
repository.upsert_sales(sales)                      # after their customer and vehicle
run_id = repository.create_pipeline_run()           # -> new run in `running` status
repository.finish_pipeline_run(
    run_id,
    status="succeeded",                             # final status: `succeeded` or `failed`
    fetched_count=7,
    accepted_count=5,
    rejected_count=1,
    duplicate_count=1,
    error_message=None,
)
repository.save_rejected_records(run_id, rejected)  # -> rows written
```

- Each method opens one connection and commits one logical operation. Errors are not swallowed: an unresolvable foreign key raises `psycopg.errors.ForeignKeyViolation`, a constraint breach raises its `psycopg` error, and an unreachable server raises `psycopg.OperationalError`. `finish_pipeline_run` raises `LookupError` when a run ID is missing or already finalized; both mean the run cannot be finalized again.
- Upserts are `INSERT ... ON CONFLICT (crm_id) DO UPDATE`, so repeating a batch updates those rows (and `updated_at`) instead of adding duplicates. Two rows with the same identifier in one batch are applied in order, and the last value wins.
- Write parents before children: a vehicle needs its customer row and a sale needs both its customer and vehicle rows.

### When the schema is applied

`database/schema.sql` contains only `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` statements: it creates missing objects and never alters, drops, or rewrites existing data. It has two entry points:

1. Compose mounts it read-only at `/docker-entrypoint-initdb.d/001_schema.sql`, so PostgreSQL applies it once while initializing an empty data directory.
2. `pipeline-api` calls `PostgresRepository.initialize_schema()` during startup when `DATABASE_URL` is set, which also covers a database directory that already exists — such as the current G7 `./.data/postgres` — where PostgreSQL skips init scripts entirely.

Editing this file therefore does **not** change an existing database. Later schema changes need an explicit migration file (for example `database/migrations/002_add_column.sql`) applied deliberately, plus a matching change to this baseline for new installs.

## Pipeline runs

`POST /pipeline/runs` executes one full extraction, transformation, and load:

```bash
curl -X POST http://127.0.0.1:8001/pipeline/runs
```

```json
{
  "run_id": 1,
  "status": "succeeded",
  "fetched": 17,
  "accepted": 15,
  "rejected": 1,
  "duplicate": 1
}
```

The response is a concise `PipelineRunSummary`; the complete record lives in `pipeline_runs` and `rejected_records`.

### Flow

1. Create a `pipeline_runs` row in `running` status.
2. Extract every page of `/customers`, `/vehicles`, and `/sales` with the synchronous `httpx` client. It starts at page `1`, requests a bounded `CRM_PAGE_SIZE`, verifies page size/totals and exact next-page progression, checks the final row count, and caps a collection at 10,000 pages.
3. Run the Stage 2 transforms over the complete collections, so a repeated CRM identifier is detected even when the two rows land on different pages.
4. Validate relationships against this batch: a vehicle needs an accepted customer, and a sale needs an accepted customer and an accepted vehicle. Unresolved rows are quarantined with their exact raw payload and a reason naming the missing parent.
5. Upsert customers, then vehicles, then sales, so foreign keys are satisfied in parent-before-child order.
6. Save every rejected row for the run, then finalize the run as `succeeded` — even when individual rows were rejected.

### Counts

| Field | Meaning |
|---|---|
| `fetched` | Every source row read across all collections, including duplicates and invalid rows. |
| `accepted` | Every entity actually persisted by the upserts. |
| `rejected` | Every quarantined row: validation failures plus unresolved parent references. |
| `duplicate` | Every repeated non-empty source identifier across the full collected batch. |

With the synthetic fixtures one run reads 17 rows, persists 15 entities (5 customers, 5 vehicles, 5 sales), rejects the malformed `CUST-9001`, and counts the repeated `CUST-0001`. Two consecutive runs return the same counts without adding entity rows or duplicate CRM identifiers.

### Failure behavior

- CRM timeout, HTTP error, malformed envelope, or a cursor that does not advance: the run is finalized as `failed` with the counts reached so far, the endpoint returns `502`, and no source payload is logged or echoed.
- PostgreSQL failure while starting or writing a run: the run is finalized as `failed` when possible, the endpoint returns `503`, and the response message names only the failure type.
- Row-level problems never fail the run; they are quarantined and reported through `rejected` and `rejected_records`.
- If the database is unreachable, marking the run failed can also fail; the run row then remains `running`. That is an operational limitation of storing run state in the same database that failed.

### Memory trade-off

The client collects each entire collection before transforming it. That is a deliberate choice for this demo: the synthetic collections are small, collecting everything makes cross-page duplicate counting exact, and upserts keep the load idempotent. A production-sized source would stream pages and hold only a bounded batch, which needs additional cross-batch state for duplicates and parent resolution. The 10,000-page limit is a guardrail, not a high-volume processing strategy.

## n8n automation

`compose.yaml` pins the official `n8nio/n8n:2.47.7` image. n8n owns only scheduling and the HTTP call: normalization, validation, persistence, and run bookkeeping stay in `pipeline-api`.

| Setting | Value |
|---|---|
| Editor URL | `http://127.0.0.1:5678` (host port `N8N_UI_PORT`, bound to loopback only) |
| Instance timezone | `UTC` (`GENERIC_TIMEZONE`), matching the workflow timezone |
| Session cookie | `N8N_SECURE_COOKIE=false`, required because the loopback demo has no TLS |
| Telemetry / personalization / update checks | Disabled through `N8N_DIAGNOSTICS_ENABLED`, `N8N_PERSONALIZATION_ENABLED`, `N8N_VERSION_NOTIFICATIONS_ENABLED` |
| State | Bind mount `./n8n/data` → `/home/node/.n8n` |
| Workflow export | `./n8n/workflows` → `/workflows` (read-only) |
| Credentials | None: the endpoint is unauthenticated inside the Compose network |

n8n's `/workflows` mount is a convenience for copying the file out of the container, not an auto-import. Importing is a deliberate one-time action in the editor:

1. Start the stack and open `http://127.0.0.1:5678`.
2. Complete n8n's first-run owner-account setup. That account is local to `./n8n/data`; no credentials belong in this repository.
3. **Workflows → ⋯ → Import from File**, and select `n8n/workflows/automotive-pipeline.json` (or `/workflows/automotive-pipeline.json` inside the container).
4. Open the imported workflow and click **Execute workflow** once. A green `Run Pipeline` node with the `run_id`/counts JSON proves the call reached `POST /pipeline/runs`.
5. Publish (activate) the workflow to enable the schedule. It stays inactive after import so nothing runs unexpectedly.

The imported workflow contains exactly three nodes and no data logic:

| Node | Type / version | Behavior |
|---|---|---|
| `Manual Trigger` | `n8n-nodes-base.manualTrigger` v1 | Runs the pipeline when you click Execute |
| `Schedule Trigger` | `n8n-nodes-base.scheduleTrigger` v1.3 | Daily at 09:00 in the workflow timezone (`UTC`) |
| `Run Pipeline` | `n8n-nodes-base.httpRequest` v4.5 | `POST http://pipeline-api:8000/pipeline/runs`, no authentication, 120-second timeout, no body |

Both triggers connect directly to `Run Pipeline`; the workflow has no transformation, branching, retry, or database node.

**Adjusting the schedule**: open `Schedule Trigger`, change the hour/minute (or switch to a cron expression) in the editor. To keep the file authoritative, update `n8n/workflows/automotive-pipeline.json` the same way — either edit `rule.interval` by hand (`field: "days"`, `triggerAtHour`, `triggerAtMinute`) or re-export the workflow after editing it in the UI. Changing the instance timezone (`GENERIC_TIMEZONE`) also shifts when "09:00" happens, so keep it `UTC` when the intent is a UTC schedule.

`tests/test_n8n_workflow.py` pins the import contract (one manual trigger, one schedule trigger, one HTTP node, the exact URL/method/timeout, no credentials, inactive on import), so a broken export fails the Python test suite without Docker.

## Local development

```powershell
# Keep venv bootstrap, pip cache, and temporary build files in this project.
New-Item -ItemType Directory -Force .venv\tmp | Out-Null
New-Item -ItemType Directory -Force .venv\pip-cache | Out-Null
$env:TEMP = Join-Path (Get-Location) ".venv\tmp"
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path (Get-Location) ".venv\pip-cache"
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Linux/macOS alternative:

```bash
mkdir -p .venv/tmp .venv/pip-cache
TMPDIR="$PWD/.venv/tmp" TEMP="$PWD/.venv/tmp" TMP="$PWD/.venv/tmp" PIP_CACHE_DIR="$PWD/.venv/pip-cache" python3 -m venv .venv
TMPDIR="$PWD/.venv/tmp" TEMP="$PWD/.venv/tmp" TMP="$PWD/.venv/tmp" PIP_CACHE_DIR="$PWD/.venv/pip-cache" .venv/bin/python -m pip install -e ".[dev]"

.venv/bin/python -m pytest
.venv/bin/python -m uvicorn automotive_data_integration.crm_api.main:app --reload --port 8000
.venv/bin/python -m uvicorn automotive_data_integration.pipeline_api.main:app --reload --port 8001
```

Use the matching `.venv` command for the current platform. On G7, run the application through Docker Compose instead of creating a host virtual environment.

The console scripts `crm-api` and `pipeline-api` start the same apps using `APP_HOST` (default `0.0.0.0`) and `APP_PORT` (default `8000`).

## Tests

```bash
.venv/Scripts/python.exe -m pytest tests/test_crm_api_health.py tests/test_crm_api_resources.py   # CRM API
.venv/Scripts/python.exe -m pytest tests/test_pipeline_schemas.py tests/test_pipeline_transforms.py   # contracts and transforms
.venv/Scripts/python.exe -m pytest tests/test_crm_client.py tests/test_pipeline_service.py tests/test_pipeline_api_runs.py   # extraction, orchestration, route
.venv/Scripts/python.exe -m pytest tests/test_n8n_workflow.py   # n8n workflow import contract (needs the checkout, not the API image)
.venv/Scripts/python.exe -m pytest                                    # full; database and end-to-end tests skip without URLs
docker compose run --rm crm-api pytest   # inside the image, no host packages needed
```

The PostgreSQL tests are integration tests against a real server. They skip with a clear reason unless `TEST_DATABASE_URL` or `DATABASE_URL` is set, so a laptop without a database still reports a green suite. They create rows under a unique per-test identifier prefix and delete only those rows; they never truncate or drop tables.

`tests/test_n8n_workflow.py` parses the versioned workflow export and fails if the triggers, HTTP call, or inactive-on-import contract changes. The export lives outside the API image build context, so that test skips inside `docker compose run --rm crm-api pytest` and runs locally or anywhere the full checkout is present.

```bash
# Against the Compose database (published port is not exposed, so run in a service):
docker compose run --rm -e TEST_DATABASE_URL=postgresql://automotive:automotive-local-dev@postgres:5432/automotive \
  pipeline-api pytest tests/test_postgres_repository.py tests/test_pipeline_runs_integration.py
```

Inside Compose the schema is created by PostgreSQL's initialization script or by `pipeline-api` startup, so the tests run against the same schema the application uses.

The end-to-end pipeline test needs a live CRM API and PostgreSQL. It skips unless `CRM_BASE_URL` and `DATABASE_URL` (or `TEST_DATABASE_URL`) are set, then runs two real pipeline executions through `TestClient`:

```bash
docker compose run --rm pipeline-api pytest tests/test_pipeline_runs_integration.py
```

That test keeps the fixture entities as the portfolio dataset and deletes only the pipeline runs it created; rejected records cascade with them.

## Running on a G7 server

Machine-specific SSH aliases, usernames, and project paths are intentionally omitted from this public repository. Use your local access instructions to connect, then run these commands from the project checkout:

```bash
git pull --ff-only
mkdir -p n8n/data           # once; owned by the project user (UID 1000), matching the container's node user
docker compose up -d --build
docker compose ps
docker compose run --rm crm-api pytest
curl -X POST http://127.0.0.1:8001/pipeline/runs
docker compose run --rm pipeline-api pytest tests/test_pipeline_runs_integration.py
```

Then import the workflow once through the editor at `http://127.0.0.1:5678` (see [n8n automation](#n8n-automation)), execute it manually to confirm a real run, and publish it when you want the daily 09:00 UTC schedule to take effect.

Do not install Python or system packages on the host; the image supplies dependencies and test tooling. If the editor is unreachable, an SSH tunnel to `127.0.0.1:5678` on the G7 host is the intended access path — the port is never published on a LAN interface.

## Storage

Persistent project data stays inside the repository folder, not in Docker's shared daemon storage:

| Item | Host location | Container path |
|---|---|---|
| PostgreSQL data | `./.data/postgres` | `/var/lib/postgresql/data` |
| n8n state | `./n8n/data` | `/home/node/.n8n` |
| n8n workflow export (tracked in Git) | `./n8n/workflows` | `/workflows` (read-only) |

- `.data/` is ignored by Git and by the Docker build context, so database files are never committed or baked into the image.
- `n8n/data/` is ignored by Git, and the whole `n8n/` directory is excluded from the Python image build context; only `n8n/workflows/` is tracked.
- `docker compose down` preserves these files; they are plain directories on the host.
- `docker compose down -v` removes named volumes only, so it does **not** delete a bind mount.
- PostgreSQL owns its data files as container UID 70 on G7; direct host reads or permission changes are not expected. Query or back up through the container instead of using host `chmod`/`chown`.
- n8n runs as `node` (UID/GID 1000), so `./n8n/data` must be owned by that UID. On G7 the project user is UID 1000, so creating the directory as that user is enough — no `chown` and no `sudo`.
- Stop the stack with `docker compose down` and make a deliberate backup before resetting data. Since the container owns `.data/postgres`, do not try to delete or change its permissions from the host; use a project-scoped reset procedure only when intentionally requested.

Back up to a user-writable folder inside the project:

```bash
mkdir -p .backups
docker compose exec -T postgres pg_dump -U automotive -d automotive > .backups/postgres.sql
```

Restore the default demo database from that dump with:

```bash
cat .backups/postgres.sql | docker compose exec -T postgres psql -U automotive -d automotive
```

`.backups/` is excluded from Git and the Docker build context. Adjust the role/database arguments if `.env` overrides the defaults.

### Migrating an existing named volume

The G7 project directory was empty before this setup and Compose had not been run there, so the initial G7 deployment has no previous database volume to migrate. For any later installation that already has data in the old `postgres-data` named volume, changing `compose.yaml` does **not** copy that data to `./.data/postgres`. Back up the old database with `pg_dump` to a file under `.backups/`, stop the old stack without `-v`, start the bind-mounted stack, restore and verify the data, and retain the old volume until verification succeeds. Never use a global Docker prune for this migration.

Docker image layers, container writable layers/logs, build cache, and network metadata still live in Docker's daemon-wide storage (normally `/var/lib/docker`). Compose cannot move those per project, and reconfiguring the daemon is out of scope here.

## Configuration

| Variable | Default | Used by |
|---|---|---|
| `CRM_API_PORT` | `8000` | Published host port for `crm-api` |
| `PIPELINE_API_PORT` | `8001` | Published host port for `pipeline-api` |
| `N8N_UI_PORT` | `5678` | Published host port for the n8n editor (loopback only; the container still listens on `5678`) |
| `POSTGRES_DB` | `automotive` | PostgreSQL database name |
| `POSTGRES_USER` | `automotive` | PostgreSQL role |
| `POSTGRES_PASSWORD` | `automotive-local-dev` | Local demo only, not a real secret |
| `APP_HOST` / `APP_PORT` | `0.0.0.0` / `8000` | Set by Compose inside each container |
| `DATABASE_URL` | derived in Compose | `pipeline-api`: connection string; when set, the schema is initialized at startup |
| `CRM_BASE_URL` | `http://crm-api:8000` in Compose | `pipeline-api`: CRM source base URL; required to run `POST /pipeline/runs` |
| `CRM_PAGE_SIZE` | `3` | `pipeline-api`: extraction page size, bounded to `1`–`100` |
| `TEST_DATABASE_URL` | unset | Only the PostgreSQL integration tests; falls back to `DATABASE_URL` |

`DATABASE_URL` comes from Compose for the pipeline service and is not needed for local unit tests. Keep real credentials out of tracked files; `.env` stays untracked.

## Known limitations

- Single host only: no high availability, TLS, reverse proxy, or secret manager.
- The image includes test dependencies so the G7 host can run tests in containers; production images would split runtime and test stages.
- CRM endpoints serve synthetic in-memory fixtures only. n8n owns only the manual trigger, the daily schedule, and the HTTP call; the ETL logic stays in `pipeline-api`.
- n8n runs on SQLite in `./n8n/data` with no credentials, no TLS, and a loopback-only editor port. That suits a single-user demo, not a shared or internet-facing installation.
- The client collects whole collections in memory before transforming them. That is intentional for this small synthetic dataset; a large source would need bounded streaming plus cross-batch duplicate and relationship state.
- Duplicate detection compares trimmed CRM identifiers case-sensitively within one supplied batch; cross-run duplicates are handled by the PostgreSQL uniqueness constraint and UPSERT.
- Relationship validation checks that parents exist and were accepted in the same run. It does not check that a sale's vehicle belongs to the sale's customer; the fixtures satisfy that rule, and enforcing it would be an additional cross-record policy beyond this stage.
- Schema changes are manual: there is no migration runner yet, so an existing database only changes when an explicit migration file is applied.
