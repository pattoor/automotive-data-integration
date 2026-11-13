# Troubleshooting

Symptom → safe check → action for the problems this stack actually produces. Start with the check column; every command is safe to run from the repository root.

**Safe by default:** use `docker compose down` to stop services; bind-mounted data under `./.data/postgres` and `./n8n/data` survives it. Do not reach for volume-removal flags, Docker-wide cleanup, or elevated privileges. PostgreSQL files are owned by the container and are read through `psql`/`pg_dump`, never edited on the host.

| Symptom | Safe checks | Action |
|---|---|---|
| Compose service is not healthy | `docker compose ps`; `docker compose logs --tail=50` | Fix the first service error and re-run Compose; do not prune Docker. |
| `pipeline-api` returns 502/503 | `docker compose logs --tail=50 pipeline-api`; inspect CRM/PostgreSQL health with `docker compose ps` | Restore the missing service/configuration; do not retry by changing entity data. |
| PostgreSQL tests skip locally | Check whether `DATABASE_URL` or `TEST_DATABASE_URL` is set | Run the integration test inside Compose, where PostgreSQL and CRM are available. |
| n8n editor port is occupied | Check the project's `N8N_UI_PORT` setting in ignored `.env` | Set it to a free port; keep Compose host binding at `127.0.0.1` and use the approved SSH tunnel. |
| n8n cannot write state | Check `ls -ld n8n/data` from the project root and `docker compose logs --tail=50 n8n` | Create `n8n/data` as the project user (UID/GID 1000 on G7); do not use `sudo` or change PostgreSQL permissions. |
| Schedule trigger does not run automatically | The tracked workflow is intentionally unpublished/inactive | This is expected for the practice project; use manual execution and do not publish the schedule. |

## Compose service is not healthy

`docker compose ps` shows each service's state and health. The first failing service is usually the cause of the ones behind it, because `pipeline-api` waits for healthy PostgreSQL and CRM, and `n8n` waits for a healthy `pipeline-api`.

```bash
docker compose ps
docker compose logs --tail=50 postgres
docker compose logs --tail=50 crm-api
docker compose logs --tail=50 pipeline-api
docker compose logs --tail=50 n8n
```

Typical causes are a port already in use, a missing `./n8n/data` directory, or a first build that never finished. Correct the reported problem, then bring the stack up again:

```bash
docker compose up -d --build
docker compose ps
```

`n8n` has no Compose health check, so `running` is its normal state; confirm the editor responds instead. If the stack needs to be stopped, use `docker compose down` — the bind-mounted data directories are plain host directories and are not affected.

## `pipeline-api` returns 502 or 503

The status code identifies the layer that failed:

| Code | Meaning | Evidence |
|---|---|---|
| `502` | CRM extraction failed: timeout, HTTP error, malformed envelope, or a page cursor that did not advance. | `docker compose logs --tail=50 pipeline-api`; run row finalized as `failed` with the counts reached so far. |
| `503` | Database or configuration failure while starting or writing a run. | The message names only the failure type; a run row may remain `running` if PostgreSQL was unreachable during finalization. |

```bash
curl -i -X POST http://127.0.0.1:8001/pipeline/runs
docker compose logs --tail=50 pipeline-api
docker compose ps
```

Confirm `crm-api` and `postgres` show `healthy`. The service addresses (`CRM_BASE_URL`, `DATABASE_URL`) are supplied by `compose.yaml`; a wrong value there is a configuration bug, not a data bug. Do not "fix" a failed run by editing fixture values, and do not hand-write entity rows while the service is running. Inspect what a run actually recorded with the queries in [SQL examples](SQL_EXAMPLES.md); repeated failures with the same error class point at the source or the connection, not at individual records.

Row-level problems never produce `502`/`503`: they are quarantined, counted in `rejected`, and stored in `rejected_records`.

## PostgreSQL tests skip locally

The PostgreSQL integration tests are gated on a database URL. They skip with a clear reason when neither `DATABASE_URL` nor `TEST_DATABASE_URL` is set, which keeps a host-only run green:

```bash
.venv/Scripts/python.exe -m pytest -rs
```

On this project the intended place to run them is inside Compose, where Compose supplies `DATABASE_URL` and the CRM is reachable by service name:

```bash
docker compose run --rm pipeline-api pytest tests/test_postgres_repository.py tests/test_pipeline_runs_integration.py
```

Running the suite through the `pipeline-api` service matters: that service receives `DATABASE_URL` and `CRM_BASE_URL` from `compose.yaml`, which is what turns the skipped tests into real ones.

The integration tests create rows under a unique per-test identifier prefix and remove only those rows; they never truncate or drop tables. Point them at the project's own database, not at a shared or production server.

## n8n editor port is occupied

The container always listens on `5678`; only the host side is configurable. An error from the `grep` below only means the ignored `.env` file does not exist, in which case the Compose defaults apply.

```bash
grep -n N8N_UI_PORT .env
docker compose ps n8n
```

If `.env` is absent or does not set the variable, Compose falls back to `5678`, which is the value most likely to be occupied. Set `N8N_UI_PORT` to a free port in the ignored project `.env` (for example `5679`), keep the Compose binding on `127.0.0.1`, and restart just that service:

```bash
docker compose up -d n8n
```

The Compose binding is `127.0.0.1:${N8N_UI_PORT:-5678}:5678`, so the editor is never published on a LAN interface. When the host is remote, forward the configured port over the approved SSH tunnel and open the local URL. Do not change the container port or bind the editor to `0.0.0.0`.

## n8n cannot write state

n8n runs as `node` (UID/GID 1000) and writes its SQLite database, encryption key, and user settings into `./n8n/data`.

```bash
ls -ld n8n/data
docker compose logs --tail=50 n8n
```

The directory must exist and be writable by UID/GID 1000. On G7 the project user already has that identity, so creating the directory as the project user is enough:

```bash
mkdir -p n8n/data
```

Then restart the service:

```bash
docker compose up -d n8n
```

PostgreSQL permissions are not part of this fix: those files belong to the container's own UID and are accessed with `psql`/`pg_dump` through the service, never through host ownership changes. If `./n8n/data` exists but belongs to a different user, stop the `n8n` service and have the directory ownership corrected by the account that owns the project checkout.

## Schedule trigger does not run automatically

This is expected. The tracked export `n8n/workflows/automotive-pipeline.json` imports inactive, and the daily 09:00 UTC schedule is optional configuration that stays intentionally inactive for this practice project.

```bash
docker compose ps n8n
docker compose logs --tail=50 n8n
```

Verify the workflow contract from a full checkout (the export is outside the API image build context, so this test skips inside the container):

```bash
.venv/Scripts/python.exe -m pytest tests/test_n8n_workflow.py
```

Run the pipeline from the n8n editor with **Execute workflow**, or call the endpoint directly:

```bash
curl -X POST http://127.0.0.1:8001/pipeline/runs
```

Then confirm the run in `pipeline_runs` with the [latest run summary](SQL_EXAMPLES.md#latest-run-summary). Leave the workflow unpublished; publishing only enables automatic scheduled executions and is not required for manual use.

## Related references

- [Data dictionary](DATA_DICTIONARY.md) — columns, constraints, and count definitions.
- [SQL examples](SQL_EXAMPLES.md) — read-only inspection queries.
- [Architecture](ARCHITECTURE.md) — service boundaries and trade-offs.
- [README](../README.md#storage) — storage layout, backups, and the ownership rules behind these checks.
