# Project instructions

- Keep project files and Python dependencies inside this repository. Use the local `.venv/` and the G7 project's `.venv/`; never install project packages globally.
- The only approved G7 workspace is `[private G7 project path]`, accessed as `[private G7 SSH target]`.
- Before remote writes, follow `[local-only G7 access instructions]` and verify the canonical working directory. Do not inspect or modify sibling homelab projects.
- Do not modify global OpenCode configuration/skills, SSH configuration, system packages, or files on `C:`. Do not use `sudo` on G7.
- Use this Git repository as the synchronization path between the local checkout and G7; do not copy project trees to other directories.
- Keep secrets out of Git and `.env` files untracked. Do not run destructive Git or filesystem commands.
- Follow `docs/ROADMAP.md`; test each component and pause for the learner checkpoint before continuing.
