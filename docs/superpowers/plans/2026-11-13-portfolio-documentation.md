# Portfolio Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Each task ends with a reviewable documentation deliverable.

**Goal:** Complete the portfolio's reference documentation with a data dictionary, safe read-only SQL examples, and practical troubleshooting guidance, while linking the existing architecture decisions rather than duplicating them.

**Architecture:** Derive the data dictionary from `database/schema.sql`, the Pydantic contracts, and the synthetic CRM fixtures. Keep operational troubleshooting in a focused guide, make SQL examples read-only, and add a short documentation index to the README. The decision alternatives already live in `docs/ARCHITECTURE.md#decisions-and-alternatives`; link to that source instead of creating a second decision log.

**Tech Stack:** Markdown, PostgreSQL SQL, existing Python/Pydantic contracts, Docker Compose v2.

## Global Constraints

- Document synthetic examples only; never add real customer data, credentials, SSH aliases, usernames, or private host paths.
- Keep the n8n schedule described as configured but intentionally inactive for this practice project.
- Use only read-only SQL examples (`SELECT`); do not publish destructive cleanup commands.
- Preserve project-relative storage policy: PostgreSQL in `./.data/postgres`, n8n in `./n8n/data`, host backups in ignored `./.backups/`.
- Do not recommend `docker compose down -v`, host edits to PostgreSQL files, `sudo` on G7, or any global Docker prune.
- Keep documentation in English to match the repository's current docs.

---

## File Map

- Create `docs/DATA_DICTIONARY.md` — source fields, normalized records, database tables, types, constraints, and relationships.
- Create `docs/SQL_EXAMPLES.md` — read-only verification and run-inspection queries.
- Create `docs/TROUBLESHOOTING.md` — common Compose, API, database-test, storage, and n8n access issues with safe checks.
- Modify `README.md` — add the documentation index and links from the quick path.
- Modify `docs/ARCHITECTURE.md` only if needed to point readers to the new references; its existing decisions-and-alternatives section remains the single decision source.
- Modify `docs/ROADMAP.md` after all deliverables are reviewed — record Stage 6 documentation status without claiming CI or runtime checks that have not passed.

### Task 1: Write the data dictionary

**Files:**
- Create: `docs/DATA_DICTIONARY.md`

**Interfaces:**
- Consumes: `database/schema.sql`, `src/automotive_data_integration/pipeline_api/schemas.py`, `src/automotive_data_integration/pipeline_api/transform.py`, and `src/automotive_data_integration/crm_api/fixtures.py`.
- Produces: a reader-facing reference covering the CRM input, normalized entities, and all five PostgreSQL tables.

- [x] **Step 1: Document the data path and source rules**

Start with the synthetic-only scope and show the complete CRM-to-normalized field mapping:

| Entity | CRM source fields | Normalized fields | Rule |
|---|---|---|---|
| Customer | `id` | `crm_id` | Trimmed, required, 1–64 characters. |
| Customer | `first_name`, `last_name` | Same names | Trimmed, required. |
| Customer | `email` | `email` | Trimmed, validated, lowercased; reserved `.test` domain is allowed. |
| Customer | `phone`, `city` | Same names | Trimmed; blank values become `null`. |
| Customer | `created_at` | `created_at` | ISO 8601 timestamp parsed to `datetime`. |
| Vehicle | `id` | `crm_id` | Trimmed and required. |
| Vehicle | `customer_id` | `customer_crm_id` | Trimmed and required. |
| Vehicle | `vin` | `vin` | Trimmed, uppercased, exactly 17 characters; ISO 3779 letters exclude `I`, `O`, and `Q`. |
| Vehicle | `make`, `model` | Same names | Trimmed and required. |
| Vehicle | `year` | `year` | Integer from 1886 through 2100. |
| Vehicle | `odometer_km` | `odometer_km` | Integer from 0 through 2,000,000. |
| Sale | `id` | `crm_id` | Trimmed and required. |
| Sale | `customer_id` | `customer_crm_id` | Trimmed and required. |
| Sale | `vehicle_id` | `vehicle_crm_id` | Trimmed and required. |
| Sale | `sale_date` | `sale_date` | ISO date parsed to `date`. |
| Sale | `amount_usd` | `amount_usd` | `Decimal` greater than zero, with at most 12 digits and 2 decimal places. |
| Sale | `status` | `status` | Trimmed and uppercased. |

Document the intentional source fixtures `CUST-0001` duplicate and malformed `CUST-9001`, noting that the CRM API serves raw records and `pipeline-api` performs normalization and validation.

- [x] **Step 2: Add one field table per persisted entity**

Document these columns and constraints from `database/schema.sql`:

| Table | Columns to cover | Important rules |
|---|---|---|
| `customers` | `crm_id`, `first_name`, `last_name`, `email`, `phone`, `city`, `created_at`, `updated_at` | CRM ID primary key; nonblank names; lowercase nonblank email; optional phone/city; timestamps. |
| `vehicles` | `crm_id`, `customer_crm_id`, `vin`, `make`, `model`, `year`, `odometer_km`, `updated_at` | CRM ID primary key; customer foreign key; 17-character VIN pattern; year 1886–2100; odometer 0–2,000,000 km. |
| `sales` | `crm_id`, `customer_crm_id`, `vehicle_crm_id`, `sale_date`, `amount_usd`, `status`, `updated_at` | CRM ID primary key; customer/vehicle foreign keys; `NUMERIC(12,2)` amount greater than zero; nonblank status up to 32 characters. |
| `pipeline_runs` | `id`, `status`, `started_at`, `finished_at`, `fetched_count`, `accepted_count`, `rejected_count`, `duplicate_count`, `error_message` | Status is `running`, `succeeded`, or `failed`; counts are nonnegative; finish cannot precede start. |
| `rejected_records` | `id`, `run_id`, `entity`, `source_id`, `raw_payload`, `reason`, `rejected_at` | Run foreign key cascades on delete; entity is customer/vehicle/sale; raw payload is JSONB; reason is nonblank. |

- [x] **Step 3: Document relationship and count semantics**

State that a vehicle references an accepted customer and a sale references an accepted customer and vehicle; the pipeline does not enforce that the sale's vehicle belongs to the same customer. Define `fetched`, `accepted`, `rejected`, and `duplicate` exactly as in `docs/ARCHITECTURE.md` and link to the architecture section for full run semantics.

- [x] **Step 4: Review the dictionary against source files**

Compare every column name, SQL type, Pydantic field, and constraint against `database/schema.sql` and `pipeline_api/schemas.py`. Do not invent source columns or imply that `updated_at` comes from the CRM.

### Task 2: Add safe SQL examples

**Files:**
- Create: `docs/SQL_EXAMPLES.md`

**Interfaces:**
- Consumes: the schema in `database/schema.sql`.
- Produces: PostgreSQL queries that inspect current state without modifying data.

- [x] **Step 1: Add the table-count and distinct-ID query**

```sql
SELECT 'customers' AS entity,
       count(*) AS row_count,
       count(DISTINCT crm_id) AS distinct_crm_ids
FROM customers
UNION ALL
SELECT 'vehicles', count(*), count(DISTINCT crm_id) FROM vehicles
UNION ALL
SELECT 'sales', count(*), count(DISTINCT crm_id) FROM sales
ORDER BY entity;
```

- [x] **Step 2: Add recent run and rejected-record queries**

```sql
SELECT id, status, started_at, finished_at,
       fetched_count, accepted_count, rejected_count, duplicate_count,
       error_message
FROM pipeline_runs
ORDER BY id DESC
LIMIT 10;
```

```sql
SELECT r.id AS run_id, r.status, x.entity, x.source_id,
       x.reason, x.raw_payload, x.rejected_at
FROM rejected_records AS x
JOIN pipeline_runs AS r ON r.id = x.run_id
ORDER BY x.rejected_at DESC
LIMIT 20;
```

- [x] **Step 3: Add a latest-run summary query and usage instructions**

Add this query to report the latest run and its rejection count without assuming a fixed run ID:

```sql
SELECT r.id AS run_id, r.status, r.started_at, r.finished_at,
       r.fetched_count, r.accepted_count, r.rejected_count,
       r.duplicate_count, count(x.id) AS stored_rejections
FROM pipeline_runs AS r
LEFT JOIN rejected_records AS x ON x.run_id = r.id
WHERE r.id = (SELECT max(id) FROM pipeline_runs)
GROUP BY r.id;
```

State that the actual `run_id` is returned by `POST /pipeline/runs`. Every SQL example in the file must be a `SELECT`; connect through `docker compose exec -T postgres psql -U automotive -d automotive`, not by exposing PostgreSQL on a host port.

- [x] **Step 4: Review SQL names against the live schema**

Run each query against the G7 PostgreSQL container or a fresh Compose database. Confirm all column names and joins exist; leave the database unchanged.

### Task 3: Add troubleshooting and documentation navigation

**Files:**
- Create: `docs/TROUBLESHOOTING.md`
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md` only for links or stale wording.
- Modify: `docs/ROADMAP.md` after verification.

**Interfaces:**
- Consumes: existing README, architecture, Compose services, and local-only G7 access instructions.
- Produces: a short symptom → safe check → action guide, linked from README.

- [x] **Step 1: Add the troubleshooting table**

Cover these exact cases with safe commands and actions:

| Symptom | Safe checks | Action |
|---|---|---|
| Compose service is not healthy | `docker compose ps`; `docker compose logs --tail=50` | Fix the first service error and re-run Compose; do not prune Docker. |
| `pipeline-api` returns 502/503 | `docker compose logs --tail=50 pipeline-api`; inspect CRM/PostgreSQL health with `docker compose ps` | Restore the missing service/configuration; do not retry by changing entity data. |
| PostgreSQL tests skip locally | Check whether `DATABASE_URL` or `TEST_DATABASE_URL` is set | Run the integration test inside Compose, where PostgreSQL and CRM are available. |
| n8n editor port is occupied | Check the project's `N8N_UI_PORT` setting in ignored `.env` | Set it to a free port; keep Compose host binding at `127.0.0.1` and use the approved SSH tunnel. |
| n8n cannot write state | Check `ls -ld n8n/data` from the project root and `docker compose logs --tail=50 n8n` | Create `n8n/data` as the project user (UID/GID 1000 on G7); do not use `sudo` or change PostgreSQL permissions. |
| Schedule trigger does not run automatically | The tracked workflow is intentionally unpublished/inactive | This is expected for the practice project; use manual execution and do not publish the schedule. |

- [x] **Step 2: Add a README documentation index**

Link `docs/ARCHITECTURE.md#decisions-and-alternatives`, `docs/DATA_DICTIONARY.md`, `docs/SQL_EXAMPLES.md`, and `docs/TROUBLESHOOTING.md`. Add the new files to the README layout table and retain the concise n8n quick path in the existing README section.

- [x] **Step 3: Check the architecture document for duplicate/stale decisions**

Keep `docs/ARCHITECTURE.md#decisions-and-alternatives` as the single source for architecture choices; do not add a redundant `DECISIONS.md`. Confirm its n8n wording says the schedule is optional and intentionally inactive for the current practice setup.

- [x] **Step 4: Verify documentation links and safety**

Search all new docs for broken relative paths, secrets, host aliases, private paths, write queries, `down -v`, or global prune commands. Review the tables against the source files and then update the Stage 6 roadmap only for work actually completed.

- [x] **Step 5: Commit the documentation work unit**

Run `git add README.md docs/ARCHITECTURE.md docs/DATA_DICTIONARY.md docs/SQL_EXAMPLES.md docs/TROUBLESHOOTING.md docs/ROADMAP.md && git commit -m "docs: add data and operations references"` after the links and content are reviewed.

## Completion Gate

- Data dictionary matches all five PostgreSQL tables and existing Pydantic/CRM contracts.
- SQL examples are read-only and run against the current schema.
- Troubleshooting instructions avoid destructive cleanup and respect G7 storage/access boundaries.
- README links the docs and reuses the architecture decision matrix rather than duplicating it.
- The n8n schedule is explicitly optional and remains inactive for this practice project.
- Pause for the learner checkpoint after this component; do not continue to another roadmap stage without feedback.
