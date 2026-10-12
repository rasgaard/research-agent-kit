# AGENTS.md — reusable research template

> Copy this file verbatim into other research repos — it contains no project-specific information. Anything specific to a repo (goals, stack, commands, file paths) lives in that repo's `README.md`; read it before starting work. This file is the collaboration contract between human and coding agent when working through GitHub (issues → branches → PRs).

## 1. How we work (GitHub interface)

1. **Issue = task.** Human files an issue describing *what* and *why*, with acceptance criteria. Agent may ask clarifying questions before starting.
2. **Branch per task.** `git checkout -b <type>/<issue-nr>-<short-slug>` (e.g. `feat/3-log-seeds`). One issue → one branch → one PR.
3. **PR = delivery.** Agent opens a PR that closes the issue (`Closes #<nr>`). Human reviews and merges. Agent never pushes directly to `main`.
4. **Small steps.** Prefer several small PRs over one large one. If a task grows, note it in the issue and split it.
5. **Document as you go.** Update `README.md` / docstrings when behaviour changes. Research decisions and negative results go in the PR description, not just in chat.
6. **Show who is speaking.** Posts made via CLI appear under the human's account, so the agent signs everything it authors (issues, PRs, comments) with the footer in §4. Unsigned = human.
7. **Start from the repo, not from chat.** A fresh agent has no history: read `README.md` and `decisions.md` before asking for background, and append significant decisions to `decisions.md` as you go. Entries use this exact format so logs stay consistent across projects:

    ## YYYY-MM-DD — One-line title

    - Context: why the decision came up.
    - Decision: what was decided.
    - Alternatives: what was considered and rejected, briefly.
    - Refs: #issue, #PR (or commit hash).
    - Tags: comma-separated keywords for selective retrieval (e.g. models, workflow, results).

    The log is append-only: record reversals as new entries, never rewrite history. Retrieve selectively: grep by tag/keyword and read only matching entries, never the whole file by default.

    Experiment results go in `experiments.jsonl` — one JSON object per line, one row per measured configuration:

    {"date": "YYYY-MM-DD", "issue": 7, "experiment": "<slug>", "model": "<id>", "params": {...}, "metrics": {"<name>": <value>}, "conclusion": "<one line>"}

    Required keys: date, issue, experiment, model, metrics. Query the log with `jq` before running an experiment that may already exist, and append a row for every new result. Audit for malformed rows (empty output = clean):

    jq -c 'select((.date and .issue and .experiment and .model and .metrics) | not)' experiments.jsonl

    Pruning: keep entries and rows short; if `decisions.md` passes ~100 lines, distill stale entries into topic summaries via a follow-up issue.

### Issues vs PRs

**Issues** are the task list and the discussion space. File tasks, bugs, research questions, and experiment proposals here — short body, clear acceptance criteria, labels where they help (`experiment`). Debate scope and approach on the issue *before* implementation. Work needing no code change (e.g. a quick experiment) is delivered as a results comment, then the issue is closed.

**PRs** are the delivery and review space. Each PR closes one issue, carries the §4 contract body, and receives line-level feedback, change requests, and the merge. A scope tweak small enough to stay in the same review (e.g. "also add the plot") goes on the PR as a comment; anything bigger becomes a new issue.

**Human loop:** file an issue → review the PR against the contract (read the diff, run the reproduction command) → comment, request changes, or merge. Terse issues are fine — one precise sentence plus acceptance criteria beats a long brief.

### Bootstrap (first commit of a new repo)

1. Copy in `AGENTS.md` — it is the whole kit. The `experiments.jsonl` schema above is queried with plain `jq`; no helper to install.
2. Create `decisions.md` containing only the title line and the header paragraph deferring to the §1 entry format.
3. Create the `experiment` label: `gh label create experiment --description "Research experiments and their results" --color 7057ff`.
4. Gitignore run artefacts (`outputs/`, `.venv/`, …); small review figures stay committable per §2.
5. Write the project-specific `README.md` (goal, commands, layout) — the only file the human must author by hand.
6. Verify the workflow end-to-end with a first tiny issue → PR.

## 2. Behavioural rules

- **Evidence before claims.** Read the relevant files before answering. Verify by running code whenever a claim is executable (see README for the repo's commands). Report what you ran and what you observed.
- **Reproducibility first.** Use fixed seeds, log hyperparameters / versions, and keep randomness explicit. Never commit large artefacts (datasets, model binaries, run outputs) — log paths and summary metrics in the PR instead. Exception: small review figures (PNG, <~200 KB) may be committed to the feature branch so they are visible during review; share them per §4.
- **Honest reporting.** State hypotheses, what you tried, and what failed. A negative result is a result. Flag uncertainty instead of guessing; distinguish observed vs. inferred.
- **Minimal diffs.** Edit existing files over creating new ones. Do not create docs, configs, or dependencies unprompted. Ask before adding a dependency.
- **No secrets.** Never commit tokens, keys, or personal data. Check `git status` / `git diff` before every commit.

## 3. Code conventions (Python / uv)

- Manage env and deps with `uv` only (`uv add`, `uv sync`, `uv run`). Dev deps (e.g. `pytest`) go in `[dependency-groups] dev`, not in main `dependencies`.
- Style: typed function signatures, short docstrings, `path:line` references when discussing code (e.g. `train.py:12`).
- Tests: every behaviour change needs a pytest in `tests/`. Run the repo's test command (see README) and paste/attach the result in the PR.
- Entry points: expose runnable work via `uv run <script>` or `uv run python -m <module>` so the human can reproduce with one command.

## 4. PR contract (what "done" looks like)

Every PR description must contain:

```markdown
Closes #<issue-nr>
Author: agent (or human — whoever wrote the PR)

What: 1–3 sentences on the change.
Why: link to research question / hypothesis.
How verified: commands run + key outputs (accuracy, test counts).
Figures: blob-page links to committed review figures, if any.
Notes: assumptions, limitations, follow-ups / new issues if scope grew.
```

Agent-authored issues, PRs, and comments end with this footer:

```markdown
<!-- posted-by: agent -->
---
🤖 Research-assistant agent (on behalf of @<human-username>)
```

The HTML comment keeps attribution machine-readable; the visible line keeps it human-readable. Human posts stay unsigned.

Checklist before requesting review:

- [ ] Test suite passes (see README for the command)
- [ ] Main reproduction command from the issue runs end-to-end
- [ ] Diff is minimal; no unrelated reformatting
- [ ] Docs/docstrings updated if behaviour changed
- [ ] Agent-authored content carries the 🤖 footer (PR body included)

## 5. What the agent should NOT do

- Push to `main`, force-push, rebase other people's branches, or merge its own PRs.
- Skip verification ("should work" is not done).
- Expand scope beyond the issue without noting it and proposing a follow-up issue.
- Invent URLs, citations, or benchmark numbers. If a reference can't be verified, say so.
