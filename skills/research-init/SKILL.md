---
name: research-init
description: Use when the user says start/init/bootstrap a new research project, or opens opencode in an empty directory and wants the research-assistant GitHub workflow. Scaffolds git+uv, copies in the AGENTS.md contract, and creates the private GitHub repo. Use ONLY for new-project bootstrapping, never for working in existing projects.
---

# Research-Init

Bootstrap a new research project so the issue → branch → PR research-assistant workflow works from the first commit. The canonical `AGENTS.md` lives at the kit root — always copy from there, never rewrite it from memory. Installed skills are symlinks, so resolve this file first; do not assume `../..` from the link path is the kit root.

## Procedure

1. **Confirm scope.** Run `gh auth status` early — if unauthenticated, warn now (the local scaffold can still proceed; `gh auth login` is needed before the remote step). Ask the user (question tool) for: project name, one-sentence research goal, Python version (default 3.12), and whether to create a private GitHub repo now. If the directory is not empty, stop and ask before touching anything.
2. **Scaffold.** `git init -b main`, then `uv init --name <name> --python <version> .`; delete the `main.py` hello-world stub it leaves behind. Seed the test harness: `uv add --dev pytest` plus `tests/test_smoke.py` with a placeholder to be replaced:

   ```python
   def test_smoke() -> None:
       """Placeholder — replace with the first real test."""
       assert True
   ```

   No other dependencies without asking.
3. **Copy the static kit files.** Resolve the skill through its symlink, then run the scaffold script:
   ```bash
   SKILL_DIR="$(dirname "$(realpath ~/.config/opencode/skills/research-init/SKILL.md)")"
   python3 "$SKILL_DIR/scripts/bootstrap.py" --target . --dry-run
   python3 "$SKILL_DIR/scripts/bootstrap.py" --target . --force
   ```
   This copies `AGENTS.md` verbatim, `.gitignore` (including `runs/`), the README skeleton, `.github/`, and the HPC `templates/` (`job.lsf`, `smoke.lsf`, `config.ini`, `ssh_config`), and creates an empty `experiments.jsonl`. `--force` is safe here on a fresh scaffold and replaces files `uv init` just created. Inspect the dry-run output first.
4. **Fill in the project files** (one pass — this is everything the first PR in step 6 ships besides the scaffold):
   1. `decisions.md` — title line plus the header paragraph deferring to the §1 entry format.
   2. `README.md` — edit the copied skeleton with the goal, commands (recording `uv run pytest`), and layout. Draft it from the scope answers; the human owns and refines it.
   3. `.gitignore` — add project-specific artefacts; the copied file already ignores `runs/`, `.venv/`, and caches.
   4. `experiments.jsonl` — starts empty; add rows only when you have measured results.
5. **Create the remote (only if confirmed in step 1).** Commit the scaffold, then `gh repo create <name> --private --description "<one-sentence goal>" --source=. --push`, and let merged branches clean themselves up: `gh repo edit --delete-branch-on-merge`. If the user declined a remote, stop after the local commit and hand over — the first PR happens once a remote exists.
6. **First issue → PR (when a remote exists).** Draft and file the first issue yourself (bootstrap + smoke test), branch `feat/1-<slug>`, commit, and open a PR that closes it — one reviewable slice proving the workflow end-to-end, not one issue per bootstrap step. The repo's test command (`uv run pytest`) must pass; quote its output in the PR.
7. **Hand over.** Summarize what was created and link the first issue; do not start implementing research code unprompted.

## Rules

- This repo is the source of truth for the template. If the user wants the template itself changed, that is a task in this repo (issue → branch → PR), not an edit to an installed copy.
- If `gh` is not authenticated, stop after the local scaffold and tell the user to run `gh auth login`.
