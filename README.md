# research-agent-kit

Home of the reusable research-assistant setup: the `AGENTS.md` collaboration contract (issue → branch → PR via GitHub) plus the opencode skill that bootstraps it into new projects. This repo is the source of truth — installed copies are symlinks, never forks.

## Layout

```text
AGENTS.md                    # canonical template (copy verbatim, never per-project edits here)
skills/research-init/        # opencode skill: "start a new research project"
  SKILL.md                   # bootstrap procedure, references ../.. /AGENTS.md
  templates/README.md        # project README skeleton (goal, commands, layout, glossary)
  templates/github/          # .github/ issue/PR templates copied into new projects
decisions.md                 # append-only decision log for the kit itself
```

## Use in a new project

Say **"start a new research project"** with the skill installed, or manually: copy `AGENTS.md` into the project and follow the bootstrap checklist in `skills/research-init/SKILL.md`. The bootstrap also starts the project README from `templates/README.md` and installs `.github/` issue/PR templates from `skills/research-init/templates/github/`; manual readers should copy those too.

## Install the skills

```bash
ln -s "$(pwd)/skills/research-init" ~/.config/opencode/skills/research-init
uvx trackio skills add --opencode --global
```

Then quit and restart opencode (config-time files load at startup only).

## Experiment tracking

The trackio command above installs trackio's own official agent skill (logging, retrieval, storage schema, alerts) globally — loaded on demand, so it stays out of context until experiment tracking comes up. It also adds a `/logbook` command (`--no-command` skips it). For a per-project copy instead — travels with the repo, lands under `.agents/skills/trackio/` — rerun without `--global`. The kit deliberately does not duplicate upstream docs; the workflow rules that matter are already contract text (`AGENTS.md` §2 progress lines, §1.7 `experiments.jsonl`, dependency approval).

## Evolving the template

Change `AGENTS.md` here via issue → branch → PR like any research change. Line 3 of `AGENTS.md` carries the contract version (`Contract vX.Y (date)`); bump minor for template changes and major for breaking ones, and note breaking changes in the PR description. Consumers copy at bootstrap time — the version marker is how they spot a stale copy.
