# research-agent-kit

Home of the reusable research-assistant setup: the `AGENTS.md` collaboration contract (issue → branch → PR via GitHub) plus the opencode skills that support it. This repo is the source of truth — installed copies are symlinks, never forks.

## Layout

```text
AGENTS.md                    # canonical template (copy verbatim, never per-project edits here)
skills/research-init/        # opencode skill: "start a new research project"
  SKILL.md                   # bootstrap procedure, references ../.. /AGENTS.md
  templates/github/          # .github/ issue/PR templates copied into new projects
skills/trackio/              # opencode skill: on-demand experiment tracking
decisions.md                 # append-only decision log for the kit itself
```

## Use in a new project

Say **"start a new research project"** with the skill installed, or manually: copy `AGENTS.md` into the project and follow the bootstrap checklist in `skills/research-init/SKILL.md`. The bootstrap also installs `.github/` issue/PR templates from `skills/research-init/templates/github/`; manual readers should copy those too.

## Install the skills

```bash
for s in "$(pwd)"/skills/*/; do ln -sfn "$s" ~/.config/opencode/skills/"$(basename "$s")"; done
```

Then quit and restart opencode (config-time files load at startup only).

## Evolving the template

Change `AGENTS.md` here via issue → branch → PR like any research change. Line 3 of `AGENTS.md` carries the contract version (`Contract vX.Y (date)`); bump minor for template changes and major for breaking ones, and note breaking changes in the PR description. Consumers copy at bootstrap time — the version marker is how they spot a stale copy.
