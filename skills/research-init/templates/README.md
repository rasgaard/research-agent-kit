# <project-name>

<One sentence: the research question this repo answers.>

## Commands

```bash
uv sync                # install dependencies
uv run pytest          # run the test suite
# TODO: main entry point, e.g. `uv run python -m <module>`
```

## Layout

```text
# TODO: the few files/dirs a returning reader (or a fresh agent) needs first
```

## Where things live

- `AGENTS.md` — the collaboration contract: workflow, conventions, PR shape.
- `decisions.md` — append-only decision log (entry format: AGENTS.md §1.8; grep by tag).
- `experiments.jsonl` — one JSON row per measured configuration (AGENTS.md §1.8); query with `jq`.
- `templates/` — DTU LSF job/smoke templates and SSH/config examples (see HPC below).

## HPC (optional)

Requires the `hpc` CLI from `research-agent-kit` on `PATH`. Once:

```bash
hpc init
hpc login
hpc sync-env
hpc doctor
hpc submit templates/smoke.lsf --dry-run
hpc submit templates/smoke.lsf
```

`hpc pull` writes to `runs/`, which is gitignored. See the kit's
`skills/dtu-hpc/` for auth, queues, secrets, and troubleshooting.

## Glossary

<TODO: the few terms a returning reader or a new agent would otherwise misread; delete this section if the project is jargon-free.>
