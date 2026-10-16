---
name: research-init
description: Use when the user says start/init/bootstrap a new research project, or opens opencode in an empty directory and wants the research-assistant GitHub workflow. Scaffolds git+uv, copies in the AGENTS.md contract, and creates the private GitHub repo. Use ONLY for new-project bootstrapping, never for working in existing projects.
---

# Research-Init

Bootstrap a new research project so the issue → branch → PR research-assistant workflow works from the first commit. The canonical `AGENTS.md` lives at this repo's root — always copy from there, never rewrite it from memory. (When installed, this file sits at `<repo>/skills/research-init/SKILL.md`, so the template is two levels up.)

## Procedure

1. **Confirm scope.** Run `gh auth status` early — if unauthenticated, warn now (the local scaffold can still proceed; `gh auth login` is needed before the remote step). Ask the user (question tool) for: project name, one-sentence research goal, Python version (default 3.12), and whether to create a private GitHub repo now. If the directory is not empty, stop and ask before touching anything.
2. **Scaffold.** `git init -b main`, then `uv init --name <name> --python <version> .`; delete the `main.py` hello-world stub it leaves behind. Seed the test harness: `uv add --dev pytest` plus `tests/test_smoke.py` with a placeholder to be replaced:

   ```python
   def test_smoke() -> None:
       """Placeholder — replace with the first real test."""
       assert True
   ```

   No other dependencies without asking.
3. **Copy the contract.** Copy `<repo>/AGENTS.md` to `./AGENTS.md` verbatim. Never edit it during bootstrap.
4. **Fill in the kit files** (one pass — this is everything the first PR in step 6 ships besides the scaffold):
   1. `decisions.md` — title line plus the header paragraph deferring to the §1 entry format.
   2. `.gitignore` — run artefacts (`outputs/`, `.venv/`, …); small review figures stay committable per §2.
   3. `README.md` — start from this skill's `templates/README.md` and fill in the goal, commands (recording `uv run pytest`), and layout. Draft it from the scope answers; the human owns and refines it.
   4. `.github/` — copy this skill's `templates/github/` verbatim — issue/PR templates for web-UI filings; agent `--body-file` posts don't read them.
5. **Create the remote (only if confirmed in step 1).** Commit the scaffold, then `gh repo create <name> --private --description "<one-sentence goal>" --source=. --push`, and let merged branches clean themselves up: `gh repo edit --delete-branch-on-merge`. If the user declined a remote, stop after the local commit and hand over — the first PR happens once a remote exists.
6. **First issue → PR (when a remote exists).** Draft and file the first issue yourself (bootstrap + smoke test), branch `feat/1-<slug>`, commit, and open a PR that closes it — one reviewable slice proving the workflow end-to-end, not one issue per bootstrap step. The repo's test command (`uv run pytest`) must pass; quote its output in the PR.
7. **Hand over.** Summarize what was created and link the first issue; do not start implementing research code unprompted.

## Rules

- This repo is the source of truth for the template. If the user wants the template itself changed, that is a task in this repo (issue → branch → PR), not an edit to an installed copy.
- If `gh` is not authenticated, stop after the local scaffold and tell the user to run `gh auth login`.
