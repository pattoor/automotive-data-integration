# Project instructions

- Keep project files and Python dependencies inside this repository. Use the local `.venv/`; on G7, run the application and tests through Docker Compose instead of installing Python packages on the host.
- Access only the G7 project directory explicitly authorized by the user; verify its canonical path before remote writes and do not inspect or modify sibling homelab projects.
- Keep machine-specific SSH aliases, usernames, private paths, and access instructions in local ignored files; never commit them.
- Do not modify global OpenCode configuration/skills, SSH configuration, system packages, or files on `C:`. Do not use `sudo` on G7.
- Storage policy (narrow, explicit exception): Docker may keep images, containers, build cache, logs, and network metadata in its daemon-wide storage. Persistent project data and generated project files MUST live under the approved project directory — currently `./.data/postgres` for PostgreSQL and `./n8n/data` for n8n state. PostgreSQL files are owned by its container UID; access them through `docker compose exec`/`pg_dump`, not host `chmod`/`chown`. Store host-side backups in ignored `./.backups/`. Do not use named persistent volumes for project data, do not change the Docker daemon configuration, and never run a global prune. `.data/`, `./n8n/data/`, and `.backups/` stay out of Git, and `.data/`, `.backups/`, and `n8n/` stay out of the Docker build context.
- Use this Git repository as the synchronization path between the local checkout and G7; do not copy project trees to other directories.
- Keep secrets out of Git and `.env` files untracked. Do not run destructive Git or filesystem commands, except removing a narrowly verified failed virtual environment created by this agent inside the approved project folder.
- Follow `docs/ROADMAP.md`; test each component and pause for the learner checkpoint before continuing.
