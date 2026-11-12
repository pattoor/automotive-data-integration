# Automotive Data Integration & Automation Pipeline — Roadmap

Build a working single-host demo in small, independently testable stages. Do not move to the next component until its tests pass and the learner has explained its purpose, operation, and alternatives.

## Delivery stages

| Stage | Deliverable | Verification gate | Learning checkpoint |
|---|---|---|---|
| 0. Repository foundation | Git remote/feature branch, Python package skeleton, dependency configuration, `.env.example`, `.gitignore`, Dockerfile, Compose services, PostgreSQL health check, initial README setup instructions. | Validate Compose configuration; build the image; confirm all required containers become healthy. | Explain what Compose solves and how services discover each other on one host. |
| 0b. Storage policy | PostgreSQL uses the project-relative bind mount `./.data/postgres` instead of a named volume; `.data/` is ignored by Git and build context; storage trade-off and container ownership documented. | Static config resolves source to `./.data/postgres`; on G7, Compose build/health succeeds, PostgreSQL answers inside the container, and the same bind-mounted data directory reopens after `docker compose down`/`up`. | Explain why project data is stored under the project folder, why Docker owns PostgreSQL files, and what the narrow global Docker-storage exception covers. |
| 1. Synthetic CRM API | Deterministic customer, vehicle, and sale fixtures; JSON REST endpoints with bounded pagination; health endpoint. | Unit/API tests for page boundaries, empty pages, response shape, and deterministic fixtures. | Explain why the mock is a separate service and how pagination protects API consumers. |
| 2. Data contracts and transforms | Pydantic entity schemas; normalization and batch duplicate detection; explicit handling of invalid records. | Unit tests for valid, malformed, duplicate, and normalized records. Run each test red before implementing its behavior. | Explain the boundary between normalization and validation, and why invalid records are quarantined. |
| 3. PostgreSQL persistence | SQL schema and repository operations for entities, run summaries, and rejected records; foreign keys, unique CRM IDs, and UPSERTs. | Integration tests against real PostgreSQL for insert/update behavior, FK handling, and repeated writes. | Explain database-enforced idempotency, constraints, and the ORM alternative. |
| 4. ETL orchestration and pipeline API | Paginated CRM client; run service; `POST /pipeline/runs`; response summary; persisted run status, counts, and rejected payloads. | Unit tests around transformation/orchestration and integration test for a complete run with invalid data. | Explain extract/transform/load responsibilities and failure/reporting behavior. |
| 5. n8n automation | Versioned workflow with manual and schedule triggers connected to the pipeline HTTP endpoint. | Import the workflow, run it manually, and verify an execution and database results; document schedule activation. | Explain why n8n calls an API rather than owning ETL logic, and compare a scheduler/cron alternative. |
| 6. End-to-end quality and documentation | GitHub Actions, full Compose smoke scenario, README, data dictionary, decisions, troubleshooting guide, and SQL examples. | Run unit/integration tests, Docker build, Compose validation, and the documented two-run idempotency scenario. | Explain the end-to-end design and identify which single-host production limitations matter. |

## Acceptance criteria

- [ ] A clean checkout can start the synthetic CRM, pipeline API, PostgreSQL, and n8n with Docker Compose.
- [ ] n8n can trigger a pipeline run manually and on a configured schedule.
- [ ] CRM pagination is fully consumed and valid customers, vehicles, and sales are persisted.
- [ ] Invalid synthetic records are rejected with their payload and reason recorded.
- [ ] Two executions do not increase entity row counts or create duplicate CRM IDs.
- [ ] Each run has a queryable status and counts; logs are useful without leaking secrets.
- [ ] Tests cover malformed input and idempotency; CI runs the automated checks.
- [ ] `.env.example` documents configuration while `.env` and real secrets remain untracked.
- [ ] Persistent project data lives under `.data/` in the project folder rather than in named volumes, and survives `docker compose down`.
- [ ] Documentation lets a student explain service boundaries, data flow, failure handling, and trade-offs in an interview.

## Working rules

1. Write a behavior-focused test first, run it to confirm the expected failure, implement the minimum, then rerun the test and the relevant suite.
2. Keep tests with the behavior they verify and prefer PostgreSQL integration tests for persistence guarantees.
3. After each stage, report exact verification results; never claim an unrun test passed.
4. Stop after each component for the learner's explanation and feedback before proceeding.
5. Keep the project synthetic-only and avoid frontend, commercial integrations, unnecessary infrastructure, and secrets in Git.

## Current progress

- [x] Connected the local and G7 checkouts to the `feat/automotive-data-integration` branch on GitHub.
- [x] Confirmed the approved G7 project directory and Docker Compose runtime; project dependencies will run in containers, not on the host.
- [x] Created local-only G7 access instructions (ignored by Git) and the local virtual environment.
- [x] Agreed on one repository with separate FastAPI service processes that can run together on one Compose host.
- [x] Decided the storage policy: project data (PostgreSQL now, n8n state later) uses project-relative bind mounts under `.data/`; Docker image/container/network metadata stays in Docker's shared daemon storage because Compose cannot relocate it per project. No daemon reconfiguration and no global prune; sibling projects are untouched.
- [x] Applied that policy to `compose.yaml` (`./.data/postgres`), `.gitignore`, `.dockerignore`, and the architecture/README documentation. Static check: `docker compose config --quiet` passes and resolves the PostgreSQL source to `.data/postgres`.
- [x] Runtime confirmation on G7: all three containers became healthy; PostgreSQL mount resolved inside the approved folder; container SQL and version checks passed after `docker compose down`/`up`.
- [x] Repository foundation and Docker Compose.
- [x] Stage 1 synthetic CRM API: deterministic customer, vehicle, and sale fixtures (including one deliberate duplicate and one malformed customer), `GET /customers`, `/vehicles`, and `/sales` with a bounded pagination envelope, and `/health` unchanged. Verified with `.venv/Scripts/python.exe -m pytest tests/test_crm_api_resources.py` (21 passed), full `.venv/Scripts/python.exe -m pytest` (23 passed), and `docker compose config --quiet` (OK).
- [ ] Data contracts and transforms.
- [ ] PostgreSQL persistence.
- [ ] ETL orchestration and pipeline API.
- [ ] n8n workflow.
- [ ] End-to-end tests, CI, and complete documentation.
