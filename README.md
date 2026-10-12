# research-agent-kit

Home of the reusable research-assistant setup: the `AGENTS.md` collaboration contract (issue → branch → PR via GitHub) plus the opencode skill that bootstraps it into new projects. This repo is the source of truth — installed copies are symlinks, never forks.

## Layout

```text
AGENTS.md                    # canonical template (copy verbatim, never per-project edits here)
skills/research-init/        # opencode skill: "start a new research project"
  SKILL.md                   # bootstrap procedure, references ../.. /AGENTS.md
```

## Use in a new project

Say **"start a new research project"** with the skill installed, or manually: copy `AGENTS.md` into the project and follow its `### Bootstrap` section.

## Install the skill

```bash
ln -s "$(pwd)/skills/research-init" ~/.config/opencode/skills/research-init
```

Then quit and restart opencode (config-time files load at startup only).

## Evolving the template

Change `AGENTS.md` here via issue → branch → PR like any research change. Consumers copy at bootstrap time, so note breaking changes in the PR description.
