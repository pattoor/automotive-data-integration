# Project instructions

- Keep project files and Python dependencies inside this repository. Use the local `.venv/`; on G7, run the application and tests through Docker Compose instead of installing Python packages on the host.
- Access only the G7 project directory explicitly authorized by the user; verify its canonical path before remote writes and do not inspect or modify sibling homelab projects.
- Keep machine-specific SSH aliases, usernames, private paths, and access instructions in local ignored files; never commit them.
- Do not modify global OpenCode configuration/skills, SSH configuration, system packages, or files on `C:`. Do not use `sudo` on G7.
- Storage policy (narrow, explicit exception): Docker may keep images, containers, build cache, logs, and network metadata in its daemon-wide storage. Persistent project data and generated project files MUST live under the approved project directory — currently `./.data/postgres` for PostgreSQL and `./n8n/data` for n8n state. PostgreSQL files are owned by its container UID; access them through `docker compose exec`/`pg_dump`, not host `chmod`/`chown`. Store host-side backups in ignored `./.backups/`. Do not use named persistent volumes for project data, do not change the Docker daemon configuration, and never run a global prune. `.data/`, `./n8n/data/`, and `.backups/` stay out of Git, and `.data/`, `.backups/`, and `n8n/` stay out of the Docker build context.
- Use this Git repository as the synchronization path between the local checkout and G7; do not copy project trees to other directories.
- Keep secrets out of Git and `.env` files untracked. Do not run destructive Git or filesystem commands, except removing a narrowly verified failed virtual environment created by this agent inside the approved project folder.
- Follow `docs/ROADMAP.md`; test each component and pause for the learner checkpoint before continuing.

## Agent workflow

Project-scoped agents live in `.opencode/agents/`. They are subagents launched by the primary session; each one has its own model and permission set.

| Role | Agent | Model | Write scope |
| --- | --- | --- | --- |
| Architecture | `architect` | `opencode/longcat-2.5-free` | none (read-only) |
| Implementation | `implementer` | `opencode/deepseek-v4.1-flash-free` | code, tests, schema, Compose, CI, `.env.example` |
| Implementation fallback | `implementer-beam` | `opencode/beam-free` | same as `implementer` |
| Review | `reviewer` | `opencode/glm-5.3-flash-free` | none (read-only) |
| Documentation | `documenter` | `opencode/mimo-v2.6-flash-free` | `README.md` and `docs/**` except plans |
| Testing | `tester` | `opencode/hy4-flash-free` | none (read-only, runs commands) |

Rules:

- One writer at a time. The `implementer` owns code and infrastructure paths; the `documenter` owns `README.md` and `docs/**`. Do not launch both against overlapping work.
- No agent edits `AGENTS.md`, `.opencode/agents/`, or `docs/superpowers/plans/**`. Those are maintained by the primary session.
- Agents do not commit, push, tag, or rewrite history. The primary session verifies the work and commits at each milestone.
- If a free model is unavailable, rate-limited, or failing, switch to `implementer-beam` for implementation or retry with another free model; do not stop the task.
- Permission rules are guardrails, not a sandbox. Review agent output and the final diff before committing.
