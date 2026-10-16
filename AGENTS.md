# AGENTS.md — reusable research template

> Copy this file verbatim into other research repos — it contains no project-specific information. Anything specific to a repo (goals, stack, commands, file paths) lives in that repo's `README.md`; read it before starting work. This file is the collaboration contract between human and coding agent when working through GitHub (issues → branches → PRs). Keep it under ~150 lines: it loads every turn, so read-once material belongs in `skills/`, and stale rules get distilled, not appended.

## 1. How we work (GitHub interface)

1. **Issue = task.** Human files an issue describing *what* and *why*, with acceptance criteria. Agent may ask clarifying questions before starting. At project start and whenever scope shifts, the agent elicits deployment facts it cannot see (output channel, latency envelope, who judges, what infra exists) — constraints surface over time, so ask early and re-ask on redirection.
2. **Branch per task.** `git checkout -b <type>/<issue-nr>-<short-slug>` (e.g. `feat/3-log-seeds`). One issue → one branch → one PR. Branch from `main` always; never stack branches on unmerged PRs. If work seems to need an unmerged branch, split smaller or wait for review instead — stacked diffs confuse review, force retargeting, and cause avoidable conflicts. Keep PRs small so review is fast and stacks never need to form.
3. **PR = delivery.** Agent opens a PR that closes the issue (`Closes #<nr>`). Human reviews and merges. Agent never pushes directly to `main`. The human may grant standing delegation ("merge green routine PRs"); design, data, and threshold decisions always wait for explicit review. One coherent unit of work per PR — never one PR per micro-step; related work shares a branch and a reviewer decision. Review iterations land as commits on the open PR.
4. **Small steps, batched sensibly.** Prefer several small PRs over one large one — but batch the trivial: group units of work that share one verification command and one reviewer decision into a single issue → PR (e.g. the whole bootstrap scaffold ships as one first PR, not one issue per step). Split when scope, risk, or reviewability diverge: new experiments, new dependencies, irreversible or cost-bearing actions, and runs over ~1 h of compute each get their own issue. The agent proceeds autonomously within an approved plan; human approval gates are merges, experiment designs, cost-bearing choices, and scope changes. Review nits land as commits on the open PR — never as new issues.
5. **Document as you go.** Update `README.md` / docstrings when behaviour changes. Research decisions and negative results go in the PR description, not just in chat. Post intermediate results (tables, tallies, figures) as PR/issue comments when they land, with artefacts linked — review should happen in the thread, not require pulling the branch. Narrate process, not just outcomes: options considered, why this one, what was rejected. Format issues, PRs, and comments for skimmability: short headers, bullets, **bold** key terms, tables for comparisons.
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

**Human loop:** file an issue → review the PR against the contract (read the diff, run the reproduction command) → comment, request changes, or merge. Discuss wherever is fastest (often chat); the agent transcribes decisions, reasons, and results into the thread so the record — not chat history — is the shared memory. Approve plans with edges ("run X, stop at Y, report Z") so go-aheads cover defined ground. When both parties touch the tree, say who owns which copy. Terse issues are fine — one precise sentence plus acceptance criteria beats a long brief. New repos: the `research-init` skill owns the first-commit checklist; this file assumes it ran.

## 2. Behavioural rules

- **Evidence before claims.** Read the relevant files before answering. Verify by running code whenever a claim is executable (see README for the repo's commands). Report what you ran and what you observed.
- **Reproducibility first.** Use fixed seeds, log hyperparameters / versions, and keep randomness explicit. Never commit large artefacts (datasets, model binaries, run outputs) — log paths and summary metrics in the PR instead. Exception: small review figures (PNG, <~200 KB) may be committed to the feature branch so they are visible during review; share them per §4.
- **Long runs stream progress.** Experiment scripts log one short plain-text line every 15–60 s — `step 290/600  48%  9.6it/s  loss=0.60  elapsed=30s  eta=32s` (eta from observed rate), flushed — never `\r` redraw bars, which spam captured output. Runs that outlast the tool timeout go detached to a log file (`... > outputs/<run>.log 2>&1 &`); poll `tail -1` and relay the latest line — in chat, or in the issue/PR thread once the run is the task's long pole (§1.5).
- **Honest reporting.** State hypotheses, what you tried, and what failed. A negative result is a result. Flag uncertainty instead of guessing; distinguish observed vs. inferred.
- **Write for returning readers.** The human dips in and out: open updates with a one-paragraph recap, expand shorthand on first use, keep headers/bullets/tables skimmable. On jargon-heavy projects keep a short project glossary and link it from `README.md` so re-entry takes minutes.
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

Context: 1–3 sentences reminding the reader of the research goal and where
this PR sits in it. Details get lost across pauses; What/Why alone assume too
much shared memory.
What: 1–3 sentences on the change.
Why: link to research question / hypothesis.
How verified: commands run + key outputs (accuracy, test counts).
Figures: blob-page links to committed review figures, if any, each with a
reading guide (what each series is + sample sizes, legend definitions, and
explicit caveats on unvalidated points).
Notes: assumptions, limitations, follow-ups / new issues if scope grew.
Review focus: what needs human eyes here vs what is routine green (so review
effort lands where it matters, not on autopilot).
```

Author `gh` bodies via `--body-file`, never inline: the shell mangles inline
text (backticks eaten, output garbled). Write the body to a file first, then
`gh pr create --body-file` / `gh issue create --body-file` / `gh pr edit --body-file`.

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
- [ ] Branch cut from freshly pulled `main` (`git log` shows main tip as base)
- [ ] PR file list read back — only this issue's work, clean `git status`
- [ ] Merged branches deleted, locally and remote, on a regular pass

## 5. What the agent should NOT do

- Push to `main`, force-push, rebase other people's branches, or merge its own PRs.
- Stack branches on unmerged PRs (see §1.2).
- Skip verification ("should work" is not done).
- Expand scope beyond the issue without noting it and proposing a follow-up issue.
- Invent URLs, citations, or benchmark numbers. If a reference can't be verified, say so.
