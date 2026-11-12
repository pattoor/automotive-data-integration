# Project instructions

- Keep project files and Python dependencies inside this repository. Use the local `.venv/`; on G7, run the application and tests through Docker Compose instead of installing Python packages on the host.
- The only approved G7 workspace is `[private G7 project path]`, accessed as `[private G7 SSH target]`.
- Before remote writes, follow `[local-only G7 access instructions]` and verify the canonical working directory. Do not inspect or modify sibling homelab projects.
- Do not modify global OpenCode configuration/skills, SSH configuration, system packages, or files on `C:`. Do not use `sudo` on G7.
- Storage policy (narrow, explicit exception): Docker may keep images, containers, build cache, logs, and network metadata in its daemon-wide storage. Persistent project data and generated project files MUST live under `[private G7 project path]` — currently `./.data/postgres` for PostgreSQL, later `./.data/n8n` for n8n state. Do not use named persistent volumes for project data, do not change the Docker daemon configuration, and never run a global prune. `.data/` stays out of Git and out of the build context.
- Use this Git repository as the synchronization path between the local checkout and G7; do not copy project trees to other directories.
- Keep secrets out of Git and `.env` files untracked. Do not run destructive Git or filesystem commands, except removing a narrowly verified failed virtual environment created by this agent inside the approved project folder.
- Follow `docs/ROADMAP.md`; test each component and pause for the learner checkpoint before continuing.
