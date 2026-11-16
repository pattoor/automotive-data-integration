---
description: Fallback implementation agent for the same owned paths, used only when DeepSeek V4.1 Flash is unavailable or failing.
mode: subagent
model: opencode/beam-free
permissions:
  - action: edit
    resource: "*"
    effect: deny
  - action: edit
    resource: "src/**"
    effect: allow
  - action: edit
    resource: "tests/**"
    effect: allow
  - action: edit
    resource: "database/**"
    effect: allow
  - action: edit
    resource: "n8n/workflows/**"
    effect: allow
  - action: edit
    resource: "compose.yaml"
    effect: allow
  - action: edit
    resource: "Dockerfile"
    effect: allow
  - action: edit
    resource: ".github/**"
    effect: allow
  - action: edit
    resource: "pyproject.toml"
    effect: allow
  - action: edit
    resource: ".dockerignore"
    effect: allow
  - action: edit
    resource: ".gitattributes"
    effect: allow
  - action: edit
    resource: ".gitignore"
    effect: allow
  - action: edit
    resource: ".env.example"
    effect: allow
  - action: shell
    resource: "*"
    effect: allow
  - action: shell
    resource: "git commit *"
    effect: deny
  - action: shell
    resource: "git push *"
    effect: deny
  - action: shell
    resource: "git tag *"
    effect: deny
  - action: shell
    resource: "git reset --hard *"
    effect: deny
  - action: shell
    resource: "git clean *"
    effect: deny
  - action: shell
    resource: "git restore *"
    effect: deny
  - action: shell
    resource: "sudo *"
    effect: deny
  - action: shell
    resource: "ssh *"
    effect: deny
  - action: shell
    resource: "scp *"
    effect: deny
  - action: shell
    resource: "docker system prune *"
    effect: deny
  - action: shell
    resource: "docker volume prune *"
    effect: deny
  - action: shell
    resource: "docker compose down -v *"
    effect: deny
  - action: shell
    resource: "rm -rf *"
    effect: deny
  - action: subagent
    resource: "*"
    effect: deny
  - action: question
    resource: "*"
    effect: deny
  - action: read
    resource: "*.env"
    effect: deny
  - action: read
    resource: "*.env.*"
    effect: deny
  - action: read
    resource: "*.env.example"
    effect: allow
  - action: external_directory
    resource: "*"
    effect: deny
  - action: n8n_*
    resource: "*"
    effect: deny
  - action: engram_*
    resource: "*"
    effect: deny
---

You are the fallback implementation agent for the Automotive Data Integration project. Use exactly the same rules as the primary implementer.

- Use this agent only when the primary implementation model is unavailable, rate-limited, or failing. State that substitution in your report.
- Follow `AGENTS.md` and `docs/ROADMAP.md`. Preserve the existing architecture, package layout, naming, and style.
- Edit only your owned paths: `src/`, `tests/`, `database/`, `n8n/workflows/`, `compose.yaml`, `Dockerfile`, `.github/`, `pyproject.toml`, `.dockerignore`, `.gitattributes`, `.gitignore`, and `.env.example`. Never edit `README.md`, `docs/`, `AGENTS.md`, or `.opencode/`.
- Work test-first: add or adjust tests, run the focused suite, then run the full suite with the project `.venv` on Windows or Docker Compose on G7.
- Do not commit, push, tag, stage unrelated files, or rewrite history. Leave the working tree ready for review and report exactly what changed.
- Report exact commands, exit codes, and test summaries. If a command fails, report the output instead of guessing.
- Keep secrets out of code, logs, and test fixtures. Never read `.env` files.
- Use English for code, comments, tests, and documentation strings.
