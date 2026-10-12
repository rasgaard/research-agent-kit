---
name: research-init
description: Use when the user says start/init/bootstrap a new research project, or opens opencode in an empty directory and wants the research-assistant GitHub workflow. Scaffolds git+uv, copies in the AGENTS.md contract, and creates the private GitHub repo. Use ONLY for new-project bootstrapping, never for working in existing projects.
---

# Research-Init

Bootstrap a new research project so the issue → branch → PR research-assistant workflow works from the first commit. The canonical `AGENTS.md` lives at this repo's root — always copy from there, never rewrite it from memory. (When installed, this file sits at `<repo>/skills/research-init/SKILL.md`, so the template is two levels up.)

## Procedure

1. **Confirm scope.** Ask the user (question tool) for: project name, one-sentence research goal, and whether to create a private GitHub repo now. If the directory is not empty, stop and ask before touching anything.
2. **Scaffold.** `git init -b main`, then `uv init --name <name> --python 3.12 .` (adjust version only if the user says so). Do not add dependencies unprompted.
3. **Copy the contract.** Copy `<repo>/AGENTS.md` to `./AGENTS.md` verbatim. Never edit it during bootstrap.
4. **Follow the copied file.** From here on, execute the `### Bootstrap` section of the just-copied `AGENTS.md` (decisions.md stub, `experiment` label, gitignore rules, README with the user's goal, first tiny issue → PR). It is the checklist; this skill just gets you to it.
5. **Create the remote (only if confirmed in step 1).** Scaffold locally, commit, then `gh repo create <name> --private --source=. --push`.
6. **Hand over.** Summarize what was created and point the user at the first issue. Do not start implementing research code unprompted.

## Rules

- This repo is the source of truth for the template. If the user wants the template itself changed, that is a task in this repo (issue → branch → PR), not an edit to an installed copy.
- If `gh` is not authenticated, stop after the local scaffold and tell the user to run `gh auth login`.
