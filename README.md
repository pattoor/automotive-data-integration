# Automotive Data Integration

A small, auditable integration demo with synthetic dealership data: a mock CRM API, a pipeline API that extracts and validates from it, PostgreSQL for persistence, and n8n for manual and scheduled runs. Everything runs on one host with Docker Compose.

The repository is one Python codebase with **two FastAPI processes**. Stage 0 delivers the runnable foundation only: package skeleton, health endpoints, container image, Compose services, and tests. CRM data endpoints, persistence, and n8n arrive in later stages (see `docs/ROADMAP.md`).

## Layout

| Path | Purpose |
|---|---|
| `src/automotive_data_integration/crm_api/` | Synthetic CRM source service (`crm-api`) |
| `src/automotive_data_integration/pipeline_api/` | Consumer service (`pipeline-api`) |
| `src/automotive_data_integration/common/` | Health route and server bootstrap shared by both services |
| `tests/` | API tests using FastAPI `TestClient` |
| `compose.yaml` | Two APIs plus PostgreSQL (`postgres:16-alpine`) |
| `Dockerfile` | One image, one package, two startup commands |
| `.data/` | Local container data (PostgreSQL files; git-ignored) |
| `.backups/` | Host-side database dumps (git-ignored) |

## Requirements

- Docker Engine with Compose v2, or
- Python 3.11+ for local development (dependencies stay in `.venv/`)

## Run with Docker Compose

```bash
cp .env.example .env        # optional; defaults work without it
docker compose up --build
docker compose ps           # wait until all services are healthy
curl http://127.0.0.1:8000/health   # crm-api
curl http://127.0.0.1:8001/health   # pipeline-api
```

Health responses: `{"status":"ok","service":"crm-api"}` and `{"status":"ok","service":"pipeline-api"}`.

- Host ports bind to `127.0.0.1` only; PostgreSQL is not published.
- `pipeline-api` starts only after `pg_isready` reports PostgreSQL healthy.
- Database files live in `./.data/postgres` (bind-mounted to `/var/lib/postgresql/data`) and survive `docker compose down`. `docker compose down -v` does not remove a bind mount either. Remove that directory only after a deliberate backup, or when you intend a full reset.
- Containers reach each other by Compose service name, for example `http://crm-api:8000` or host `postgres`.

## Local development

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"   # Windows
# .venv/bin/python -m pip install -e ".[dev]"         # Linux/macOS

.venv/Scripts/python.exe -m pytest                    # full suite
.venv/Scripts/python.exe -m uvicorn automotive_data_integration.crm_api.main:app --reload --port 8000
.venv/Scripts/python.exe -m uvicorn automotive_data_integration.pipeline_api.main:app --reload --port 8001
```

The console scripts `crm-api` and `pipeline-api` start the same apps using `APP_HOST` (default `0.0.0.0`) and `APP_PORT` (default `8000`).

## Tests

```bash
.venv/Scripts/python.exe -m pytest tests/test_crm_api_health.py tests/test_pipeline_api_health.py  # focused
.venv/Scripts/python.exe -m pytest                                                                # full
docker compose run --rm crm-api pytest   # inside the image, no host packages needed
```

## Running on a G7 server

Machine-specific SSH aliases, usernames, and project paths are intentionally omitted from this public repository. Use your local access instructions to connect, then run these commands from the project checkout:

```bash
git pull --ff-only
docker compose up -d --build
docker compose ps
docker compose run --rm crm-api pytest
```

Do not install Python or system packages on the host; the image supplies dependencies and test tooling.

## Storage

Persistent project data stays inside the repository folder, not in Docker's shared daemon storage:

| Item | Host location | Container path |
|---|---|---|
| PostgreSQL data | `./.data/postgres` | `/var/lib/postgresql/data` |
| n8n state (later stage) | `./.data/n8n` | its n8n data directory |

- `.data/` is ignored by Git and by the Docker build context, so database files are never committed or baked into the image.
- `docker compose down` preserves these files; they are plain directories on the host.
- `docker compose down -v` removes named volumes only, so it does **not** delete a bind mount.
- PostgreSQL owns its data files as container UID 70 on G7; direct host reads or permission changes are not expected. Query or back up through the container instead of using host `chmod`/`chown`.
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
| `POSTGRES_DB` | `automotive` | PostgreSQL database name |
| `POSTGRES_USER` | `automotive` | PostgreSQL role |
| `POSTGRES_PASSWORD` | `automotive-local-dev` | Local demo only, not a real secret |
| `APP_HOST` / `APP_PORT` | `0.0.0.0` / `8000` | Set by Compose inside each container |
| `DATABASE_URL` | derived in Compose | Reserved for the persistence stage |

## Known limitations

- Single host only: no high availability, TLS, reverse proxy, or secret manager.
- The image includes test dependencies so the G7 host can run tests in containers; production images would split runtime and test stages.
- No CRM data endpoints, database schema, ETL logic, or n8n workflow yet.
