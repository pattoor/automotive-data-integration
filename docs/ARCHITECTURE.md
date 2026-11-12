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
| `postgres` | Persist accepted entities, pipeline run summaries, and rejected source records. | Private Compose network; persistent volume. |
| `n8n` | Provide manual and scheduled triggers using an HTTP Request node. | Calls `pipeline-api`; keeps n8n state in its own persistent volume. |

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

- Customers, vehicles, and sales each have a stable CRM identifier protected by a unique constraint.
- Writes use `INSERT ... ON CONFLICT ... DO UPDATE`, so a rerun updates matching entities instead of inserting duplicates.
- A `pipeline_runs` record captures status, timestamps, and fetched/accepted/rejected counts.
- A `rejected_records` record captures the run, entity type, source identifier when available, raw synthetic payload, and validation/processing reason.
- Foreign keys connect sales to their customer and vehicle. Invalid or unresolvable records are rejected rather than silently creating broken references.

Source duplicates within one run and duplicate database rows across repeated runs are distinct cases. The pipeline will count and report source duplicates; database uniqueness and UPSERT handle repeated executions.

## Deployment model

### Local development and single-host demonstration

The same `compose.yaml` runs all four services on a single Debian/Linux machine (including the user's G7) or another computer with Docker Compose. Containers use Compose service names for internal communication. No cloud account or second machine is required. Exposed development ports should bind to localhost by default.

### Production boundary

The mock CRM exists only for synthetic demo and test runs. A real deployment would configure the pipeline to call the employer's authorized CRM/API; the mock service would not be presented as a real source system. A single-host Compose deployment can suit a small, low-criticality installation, but it is a single point of failure and is not high availability.

Production hardening is deliberately outside the first implementation: TLS/reverse proxy, restricted n8n access, secret management, backups and restore drills, monitoring, resource limits, and a separate or managed PostgreSQL instance when operational needs justify it. Kubernetes, a message broker, Celery, and multiple repositories are not required for this portfolio scope.

## Decisions and alternatives

| Decision | Why | Alternative and trade-off |
|---|---|---|
| One monorepo, two FastAPI services | Makes the source/consumer boundary real while keeping development and review simple. | One FastAPI process is simpler to start, but couples the simulated source and its consumer and hides the integration boundary. Separate repositories add coordination and deployment work without benefit at this scale. |
| Docker Compose for all local services | Reproducible single-host setup and a realistic service network. | Running services directly on the host reduces container learning but makes setup less consistent. Kubernetes is excessive for a single-host portfolio demo. |
| PostgreSQL constraints and SQL UPSERT | Idempotency is enforced at the database boundary and remains visible to learners. | Application-only duplicate checks can race and are not a durable uniqueness guarantee. An ORM can be added later, but direct SQL keeps this small schema and upsert behavior explicit. |
| Pydantic per record; Pandas only for useful batches | Clear validation errors and focused use of the requested data-frame tool. | Using Pandas for every step adds overhead; using only Python collections is simpler for tiny data but misses a useful batch-processing example. |
| Synthetic fixtures, including documented bad records | Demonstrates validation and quarantine without personal or commercial data. | Live CRM credentials would make the demo unsafe, non-reproducible, and out of scope. |

## Out of scope

- Frontend, dashboard, real customer data, commercial integrations, AI features, distributed queues, and high-availability infrastructure.
- Publicly exposing development ports or claiming that a single Docker host is highly available.

## Learning checkpoints

At the end of each implementation component, pause for the learner to explain: **what problem it solves, how it works, and what alternatives exist**. Review the explanation and clear up misconceptions before moving to the next component.
