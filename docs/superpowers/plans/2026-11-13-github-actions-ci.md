# GitHub Actions CI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Each task ends with a runnable verification gate.

**Goal:** Add a secret-free GitHub Actions workflow that runs local checks and the full Compose-backed test suite on pushes and pull requests.

**Architecture:** A GitHub-hosted Ubuntu runner performs a fast local Python test pass, checks dependencies and Compose configuration, prepares the n8n bind-mount directory with the container's UID, then builds and starts the complete Compose stack. The in-container pytest run covers PostgreSQL integration and the live HTTP smoke test. A final `docker compose down` stops only this project without deleting bind-mounted data or pruning Docker globally.

**Tech Stack:** GitHub Actions, Ubuntu 24.04, Python 3.13, Docker Compose v2, pytest, existing project dependencies.

## Global Constraints

- Do not add secrets, commercial integrations, or external service credentials; CI uses only synthetic fixtures.
- Grant only `contents: read`; the workflow does not need repository write permissions.
- Run CI on GitHub-hosted runners, never on G7. The only `sudo` command in this plan is a targeted ownership fix on the disposable hosted runner, not on G7.
- Keep all test data in the checkout's project-relative `.data/postgres` and `n8n/data` mounts.
- Never use `docker compose down -v`, `docker system prune`, or another global cleanup command.
- Do not publish or activate the n8n workflow; CI only starts the n8n service.

---

## File Map

- Create `.github/workflows/ci.yml` — push and pull-request verification.
- Modify `docs/ROADMAP.md` after the workflow has completed successfully on GitHub — record CI coverage and exact checks.

### Task 1: Add the CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `pyproject.toml` development dependencies, `compose.yaml`, `Dockerfile`, the pytest suite, and `tests/test_compose_smoke.py` from the Compose Smoke plan.
- Produces: one `CI` workflow with a read-only token and no repository secrets.

- [x] **Step 1: Create the workflow with these triggers, permissions, and job settings**

```yaml
name: CI

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-24.04
    timeout-minutes: 30
    steps:
      - name: Check out repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Install project and test dependencies
        run: |
          python -m venv .venv
          .venv/bin/python -m pip install -e ".[dev]"

      - name: Run local unit and contract tests
        run: .venv/bin/python -m pytest

      - name: Check Python dependencies
        run: .venv/bin/python -m pip check

      - name: Validate Compose configuration
        run: docker compose config --quiet

      - name: Prepare project-local n8n state directory
        run: |
          mkdir -p n8n/data
          sudo chown 1000:1000 n8n/data

      - name: Build and start the complete Compose stack
        run: docker compose up -d --build --wait --wait-timeout 300

      - name: Run the complete test suite against Compose services
        run: docker compose exec -T pipeline-api pytest

      - name: Run the explicitly marked live HTTP smoke test
        run: docker compose exec -T -e COMPOSE_SMOKE_TEST=1 pipeline-api pytest tests/test_compose_smoke.py

      - name: Stop this Compose project
        if: always()
        run: docker compose down
```

- [x] **Step 2: Review workflow safety and scope**

Confirm the workflow has no `secrets.*` references, no write permissions, no n8n publish/import operation, and no destructive Docker cleanup. Confirm the n8n state directory remains project-relative and owned by UID 1000 before the container starts.

- [x] **Step 3: Run the same checks locally**

Run:

```bash
.venv/Scripts/python.exe -m pytest
.venv/Scripts/python.exe -m pip check
docker compose config --quiet
```

Expected: pytest succeeds (database-dependent tests may skip on the host), `pip check` reports no broken requirements, and Compose exits successfully.

- [x] **Step 4: Commit the CI workflow**

Run `git add .github/workflows/ci.yml docs/superpowers/plans/2026-11-13-github-actions-ci.md && git commit -m "ci: add Compose-backed GitHub Actions workflow"` after the local checks pass. The workflow file must be committed before GitHub can run it.

- [ ] **Step 5: Record CI evidence**

Run `git push` from the feature branch and inspect the `CI` workflow run for that commit. Require the hosted job to finish successfully; if it fails, fix the underlying workflow/test issue and rerun. Only after success, update `docs/ROADMAP.md` with the workflow path, trigger scope, and the exact hosted checks. Do not include a fabricated run URL or success result.

- [ ] **Step 6: Commit the CI work unit**

Run `git add docs/ROADMAP.md && git commit -m "docs: record successful Stage 6 CI run"` after the hosted run passes.

## Completion Gate

- Push and pull-request events start the CI job.
- The local test, dependency, Compose-config, image-build, and in-container pytest steps pass.
- The in-container suite includes real PostgreSQL/CRM integration and live HTTP smoke coverage.
- The teardown uses only `docker compose down`; no named-volume deletion, global prune, external secrets, or schedule activation occurs.
- Pause for the learner checkpoint after this component before starting the documentation plan.
