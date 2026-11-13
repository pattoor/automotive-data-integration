# Automotive Data Integration & Automation Pipeline — Architecture

This project demonstrates a small, auditable data integration system using synthetic dealership data. It is a **single repository with separate services**, so each boundary is visible without requiring separate machines or a distributed platform.

## Quick path

1. Docker Compose starts the mock CRM API, pipeline API, PostgreSQL, and n8n on one host.
2. n8n starts a run manually or on a schedule by calling the pipeline API.
3. The pipeline retrieves every page from the CRM API, normalizes and validates records, then writes accepted records and rejected-record details to PostgreSQL.
4. Unique CRM identifiers and PostgreSQL upserts make repeated runs idempotent.

## Services and responsibilities

| Service | Responsibility | Calls / stores |
|---|---|---|
| `crm-api` | Serve deterministic synthetic customers, vehicles, and sales as paginated REST resources. Include a small set of documented invalid/duplicate fixtures for demonstrations. | Called by `pipeline-api`; no database required. |
| `pipeline-api` | Expose health and pipeline-run endpoints; coordinate extraction, transformation, validation, persistence, and run summaries. | Calls `crm-api`; writes to PostgreSQL. |
| `postgres` | Persist accepted entities, pipeline run summaries, and rejected source records. | Private Compose network; project-relative bind mount `./.data/postgres`. |
| `n8n` | Provide manual and scheduled triggers using an HTTP Request node. | Calls `pipeline-api`; keeps n8n state in its own project-relative mount. |

The two FastAPI applications live in one Python package and can use one Docker image with different startup commands. They are separate processes and containers at runtime, but remain one codebase and one Compose deployment.

## Data flow

```text
n8n (manual or schedule)
        │ POST /pipeline/runs
        ▼
pipeline-api ── paginated GET requests ──► crm-api
     │                                        synthetic JSON
     ├── normalize and deduplicate batches
     ├── validate each record with Pydantic
     ├── store valid entities with PostgreSQL UPSERT
     └── store run summary and rejected payloads
```

Pandas is limited to batch-oriented normalization and duplicate analysis where it improves clarity. Pydantic remains the record-level validation boundary; Pandas is not used as an ORM or API schema layer.

## Persistence and idempotency

`database/schema.sql` is the initial schema, applied idempotently by direct SQL (`psycopg`, no ORM):

| Table | Responsibility | Key rules |
|---|---|---|
| `customers` | Normalized customers, one row per CRM identifier. | `crm_id` primary key; lowercase non-blank email; length/blank checks. |
| `vehicles` | Normalized vehicles linked to a customer. | `crm_id` primary key; `customer_crm_id` foreign key; 17-character VIN pattern; year `1886`–`2100`; odometer `0`–`2000000`. |
| `sales` | Normalized sales linked to a customer and a vehicle. | `crm_id` primary key; both parent foreign keys; `amount_usd NUMERIC(12,2) > 0`; non-blank status. |
| `pipeline_runs` | One row per execution. | Starts as `running`, then finalizes once to `succeeded` or `failed`; start/finish timestamps; fetched, accepted, rejected, and duplicate counts; optional error message. |
| `rejected_records` | Quarantined source rows. | Owning `run_id` (cascade delete); entity, source id, exact raw payload as `jsonb`, and reason. |

- Customers, vehicles, and sales each have a stable CRM identifier protected by a unique constraint.
- Writes use `INSERT ... ON CONFLICT ... DO UPDATE`, so a rerun updates matching entities instead of inserting duplicates; repeated identifiers inside one batch are applied in order and the last value wins.
- A `pipeline_runs` record captures status, timestamps, and fetched/accepted/rejected/duplicate counts plus an error message when a run fails.
- A `rejected_records` record captures the run, entity type, source identifier when available, raw synthetic payload as `jsonb`, and validation/processing reason.
- Foreign keys connect vehicles to their customer and sales to their customer and vehicle. Invalid or unresolvable records are rejected rather than silently creating broken references; the repository propagates the PostgreSQL violation instead of hiding it.
- The schema does not verify that a sale's vehicle belongs to the sale's customer; that cross-record rule belongs to orchestration, where both records are known.

Source duplicates within one run and duplicate database rows across repeated runs are distinct cases. Pandas counts repeated non-empty CRM IDs across the batch. Pydantic validates every row independently; invalid rows stay rejected, and among valid rows with a repeated ID the first valid row wins. Thus an invalid first occurrence cannot suppress a later valid record, and a malformed repeated row may contribute to both duplicate and rejection counts. PostgreSQL uniqueness and UPSERT handle duplicates across repeated executions.

### Schema application and migration policy

The schema has two application paths because a database directory may already exist:

1. Compose mounts `database/schema.sql` read-only at `/docker-entrypoint-initdb.d/001_schema.sql`; PostgreSQL applies it only while initializing an empty data directory.
2. `pipeline-api` calls `PostgresRepository.initialize_schema()` during startup whenever `DATABASE_URL` is set. This covers the current G7 data directory, which was initialized before the schema file existed, and any checkout that starts the API without Compose. Startup fails if the database rejects the schema, rather than serving with an unknown state.

Every statement is `CREATE TABLE IF NOT EXISTS` or `CREATE INDEX IF NOT EXISTS`, so startup repeated on an existing database creates only what is missing and never alters, drops, or rewrites data. Because a baseline file that was already applied cannot evolve a live database, later changes require an explicit versioned migration file under `database/migrations/`, applied deliberately, plus a matching baseline update for new installs.

## Deployment model

### Local development and single-host demonstration

The same `compose.yaml` runs all four services on a single Debian/Linux machine (including the user's G7) or another computer with Docker Compose. Containers use Compose service names for internal communication. No cloud account or second machine is required. Exposed development ports should bind to localhost by default.

The authoring checkout uses a repository-local `.venv`. On G7, the Compose image supplies Python dependencies; do not install project packages or system packages on the host.

### Storage: where project data lives

Persistent project data is bind-mounted into the repository, not stored in named volumes:

- PostgreSQL data directory: `./.data/postgres` on the host, mounted at `/var/lib/postgresql/data`.
- The future n8n state directory must also be project-relative (for example `./.data/n8n`) rather than a named volume.
- `.data/` is ignored by Git and by the Docker build context, so database files are neither committed nor copied into the image.

This is a deliberate trade-off rather than a complete relocation of Docker state:

| Storage kind | Location | Why |
|---|---|---|
| Project data (database files, later n8n state) | Under the approved G7 project folder's `.data/` directory | Visible by path; PostgreSQL files are owned by container UID 70 and should be accessed through SQL/`pg_dump`, not host file permissions. Backups go under ignored `./.backups/`. |
| Docker image layers, container writable layers/logs, build cache, network metadata | Docker's shared daemon storage (normally `/var/lib/docker`, global) | Compose cannot relocate these per project. Changing `data-root` or otherwise reconfiguring the daemon is a host-wide change and is explicitly out of scope for this project. |

Consequences worth stating plainly: `docker compose down` does not touch bind-mounted data; `docker compose down -v` also does not, because it only removes named volumes. Stop the stack and create a project-local backup under `.backups/` before an intentional reset. PostgreSQL files are owned by the container UID (70 on G7), so the host user should not inspect or change their permissions directly; use `psql` and `pg_dump` through the service. Switching an existing installation from the former `postgres-data` named volume does not copy its contents; back it up with `pg_dump`, restore into the bind-mounted database, and verify before retiring the old volume. The initial G7 checkout had no previous Compose data to migrate. Docker's own storage still grows from images, build cache, and containers, and reclaiming it is a host maintenance decision made outside this project — never through a global prune or daemon reconfiguration triggered here.

### Production boundary

The mock CRM exists only for synthetic demo and test runs. A real deployment would configure the pipeline to call the employer's authorized CRM/API; the mock service would not be presented as a real source system. A single-host Compose deployment can suit a small, low-criticality installation, but it is a single point of failure and is not high availability.

Production hardening is deliberately outside the first implementation: TLS/reverse proxy, restricted n8n access, secret management, backups and restore drills, monitoring, resource limits, and a separate or managed PostgreSQL instance when operational needs justify it. Kubernetes, a message broker, Celery, and multiple repositories are not required for this portfolio scope.

## Decisions and alternatives

| Decision | Why | Alternative and trade-off |
|---|---|---|
| One monorepo, two FastAPI services | Makes the source/consumer boundary real while keeping development and review simple. | One FastAPI process is simpler to start, but couples the simulated source and its consumer and hides the integration boundary. Separate repositories add coordination and deployment work without benefit at this scale. |
| Docker Compose for all local services | Reproducible single-host setup and a realistic service network. | Running services directly on the host reduces container learning but makes setup less consistent. Kubernetes is excessive for a single-host portfolio demo. |
| Bind mounts under `./.data/` for persistent data | Project data stays inside the approved G7 project folder, so it is visible and can be backed up separately alongside the repository folder. | Named Docker volumes hide data in daemon-wide storage and tie it to volume lifecycle commands. Relocating Docker's whole storage would require a global daemon change that affects every other project on the host, so image/container/network metadata stays where Docker manages it. |
| PostgreSQL constraints and SQL UPSERT | Idempotency is enforced at the database boundary and remains visible to learners. | Application-only duplicate checks can race and are not a durable uniqueness guarantee. An ORM can be added later, but direct SQL keeps this small schema and upsert behavior explicit. |
| Idempotent baseline script plus explicit migrations | A fresh Compose database and the already-initialized G7 database reach the same state from one readable file, while applied databases are never mutated by editing it. | A full migration tool (Alembic, Flyway) automates version tracking and rollbacks, but adds configuration and a second execution path for a five-table schema. Editing the baseline in place would silently skip existing databases. |
| Pydantic per record; Pandas only for useful batches | Clear validation errors and focused use of the requested data-frame tool. | Using Pandas for every step adds overhead; using only Python collections is simpler for tiny data but misses a useful batch-processing example. |
| Synthetic fixtures, including documented bad records | Demonstrates validation and quarantine without personal or commercial data. | Live CRM credentials would make the demo unsafe, non-reproducible, and out of scope. |

## Out of scope

- Frontend, dashboard, real customer data, commercial integrations, AI features, distributed queues, and high-availability infrastructure.
- Publicly exposing development ports or claiming that a single Docker host is highly available.

## Learning checkpoints

At the end of each implementation component, pause for the learner to explain: **what problem it solves, how it works, and what alternatives exist**. Review the explanation and clear up misconceptions before moving to the next component.
