# SQL Examples

Read-only queries for inspecting the pipeline database. Every statement in this file is a `SELECT`: nothing here inserts, updates, or removes data, and nothing changes the schema.

PostgreSQL is **not published on a host port**. Run the queries inside the existing container with `psql`, so no client and no credentials are needed on the host:

```bash
# From the repository root, with the stack running
docker compose exec -T postgres psql -U automotive -d automotive
```

For a single query, pass it with `-c`:

```bash
docker compose exec -T postgres psql -U automotive -d automotive \
  -c "SELECT count(*) FROM customers;"
```

For a multi-line block, pipe it through the container's `psql`:

```bash
docker compose exec -T postgres psql -U automotive -d automotive <<'SQL'
SELECT current_database(), current_user;
SELECT count(*) AS customers FROM customers;
SQL
```

Replace `-U automotive -d automotive` only if `.env` overrides `POSTGRES_USER` or `POSTGRES_DB`. The same connection values are documented in the README configuration table.

## Row counts and distinct CRM identifiers

Confirms how many entity rows exist and that the identifier column is unique. `distinct_crm_ids` is always equal to `row_count` because `crm_id` is the primary key; a smaller number would indicate a schema problem, not a data-loading quirk.

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

After at least one successful run with the default synthetic fixtures, the result is three rows of `5 | 5`. Repeated runs upsert instead of appending, so the counts do not grow.

## Recent pipeline runs

Shows the last ten runs, newest first, including every count and the stored error message.

```sql
SELECT id, status, started_at, finished_at,
       fetched_count, accepted_count, rejected_count, duplicate_count,
       error_message
FROM pipeline_runs
ORDER BY id DESC
LIMIT 10;
```

A healthy run against the default fixtures reports `fetched_count = 17`, `accepted_count = 15`, `rejected_count = 1`, and `duplicate_count = 1`. A `running` row with no `finished_at` can be a run still in flight, or a run whose failure could not be recorded because PostgreSQL was unavailable. The exact meanings are in the [data dictionary](DATA_DICTIONARY.md#count-and-status-semantics).

## Recent rejections with run context

Joins quarantined rows to their run so each rejection can be read next to the run that produced it.

```sql
SELECT r.id AS run_id, r.status, x.entity, x.source_id,
       x.reason, x.raw_payload, x.rejected_at
FROM rejected_records AS x
JOIN pipeline_runs AS r ON r.id = x.run_id
ORDER BY x.rejected_at DESC
LIMIT 20;
```

`raw_payload` prints as JSON. For the default fixtures it holds the exact `CUST-9001` row, including its invalid `email` and `created_at`, and `reason` names the failing fields.

## Latest run summary

Reports the newest run with the number of rejection rows actually stored for it, without hard-coding a run identifier.

```sql
SELECT r.id AS run_id, r.status, r.started_at, r.finished_at,
       r.fetched_count, r.accepted_count, r.rejected_count,
       r.duplicate_count, count(x.id) AS stored_rejections
FROM pipeline_runs AS r
LEFT JOIN rejected_records AS x ON x.run_id = r.id
WHERE r.id = (SELECT max(id) FROM pipeline_runs)
GROUP BY r.id;
```

- The query returns no rows when `pipeline_runs` is empty.
- For a `succeeded` run, `stored_rejections` normally equals `rejected_count`.
- For a `failed` run, `stored_rejections` can be lower, because rejection rows are written only after the batch loads; a failed run exits before that.
- The `run_id` value is also returned by `POST /pipeline/runs`, so a specific run can be inspected directly.

## Notes

- All queries are read-only and safe to repeat. Running them does not create, modify, or remove rows.
- Timestamps are `timestamptz`; `psql` renders them in the session time zone, which defaults to the container's `UTC`.
- For the flow that produces these rows, see [Pipeline runs](../README.md#pipeline-runs). For column definitions, see the [data dictionary](DATA_DICTIONARY.md). For operational failures, see [Troubleshooting](TROUBLESHOOTING.md).
