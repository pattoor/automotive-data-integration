# Engineering workflow

This document explains how the project was built and verified: a human defined the work and approved each milestone, agents drafted changes under explicit path ownership, and the primary session reviewed, tested, and committed the result.

## Human-led, agent-assisted

The human owned the requirements, the acceptance criteria in `docs/ROADMAP.md`, the architecture decisions recorded in [Decisions and alternatives](ARCHITECTURE.md#decisions-and-alternatives), and milestone approval. The primary session ran the stages, reviewed agent output, and performed commits and pushes; agents never committed or pushed. Work moved stage by stage, with a pause after each component for the learner to explain what it solves, how it works, and what alternatives exist.

Agents produced drafts — code, tests, schema, Compose configuration, CI, and documentation — under explicit path ownership. The primary session reviewed the final diff before each commit. Permission rules are guardrails, not a sandbox: agent output was verified, never trusted on its own. Nothing was documented as passing unless the command had actually been run.

## Role boundaries

Project-scoped agents are defined in [`AGENTS.md`](../AGENTS.md) (Agent workflow), each with its own model and write scope. Six roles take part:

- **Architecture** and **review** are read-only: they analyze and critique, they never edit.
- **Implementation** owns code, tests, schema, Compose, CI, and `.env.example`; a **fallback implementation** role with the same write scope covers rate-limited or unavailable models.
- **Documentation** owns `README.md` and `docs/**` except process plans.
- **Testing** runs commands and reports results; it is read-only.

No agent edits `AGENTS.md`, `.opencode/agents/`, or `docs/superpowers/plans/**`, and no agent commits, pushes, tags, or rewrites history — the primary session does that after verification. Model identifiers and permission details live in `AGENTS.md` and `.opencode/agents/`, not here.

## One writer at a time

Only one role writes at a time. Code and infrastructure paths belong to the implementation role; `README.md` and `docs/**` belong to the documentation role. The two are never launched against overlapping work, and the read-only roles (architecture, review, testing) cannot edit at all. `docs/superpowers/plans/**` is process history maintained by the primary session and stays untouched by agents.

## Verification gates

Each stage in `docs/ROADMAP.md` had to pass its gate before the next one started:

1. Focused tests for the behavior under change, run before the full suite.
2. The full test suite, so new work did not break earlier stages.
3. A Compose-backed smoke test that starts the whole stack and exercises a live HTTP pipeline run.
4. The GitHub Actions workflow (`.github/workflows/ci.yml`), which repeats unit tests, dependency checks, Compose validation, the full in-container suite, and the smoke test on push and pull request.
5. A review pass over the final diff before each milestone commit.

`docs/ROADMAP.md` records the exact commands and observed evidence for every stage; a result was never claimed for a command that was not run.

## Why publish this

The repository is meant to be honest and reproducible: attribution is explicit about what the human decided and what an agent drafted, and every stage's evidence can be re-run from a clean checkout.

The value of the work is the data engineering — service boundaries, contracts, idempotent persistence, and verification — not the tooling used to produce it. Agents did not replace engineering judgment; they executed under it, and the human remains responsible for every architectural decision and every commit.
