# Decisions

Append-only log. Entries follow the `AGENTS.md` §1.7 format (date-title heading, then Context / Decision / Alternatives / Refs / Tags). Never rewrite history — record reversals as new entries. Decisions made before this log exists (issues/PRs #1–#14) live in the merged PR history.

## 2026-10-16 — Long runs report plain progress lines, not bars

- Context: no contract guidance for long experiment runs; agent-captured output is non-TTY, so tqdm-style bars degrade into redraw spam.
- Decision: scripts log one plain line every 15–60 s (`step/total, %, rate, metric, elapsed, eta`), flushed; runs past the tool timeout detach to a log and are polled/relayed. No tqdm, no dashboards.
- Alternatives: tqdm default (~58 KB/min captured), tqdm `disable=None` (silent when captured), trackio-style dashboards (dependency + doesn't fix capture; deferred).
- Refs: #13, #14.
- Tags: progress, ux, agents.

## 2026-10-16 — Contract version marker, starting at v1.0

- Context: consumers copy `AGENTS.md` once at bootstrap; nothing identifies which revision a repo holds.
- Decision: line 3 of `AGENTS.md` reads `Contract vX.Y (date)`; minor bumps for template changes, major for breaking; README documents the policy.
- Alternatives: no marker (drift invisible), external changelog (consumers still can't tell what they copied).
- Refs: #15.
- Tags: template, versioning.

## 2026-10-16 — No home-grown trackio skill — use trackio's official one

- Context: #19 proposed an on-demand trackio skill, drafted in #20. A subagent evaluation found that trackio ships its own official agent skill (`trackio skills add`), and that an agent following those official docs independently converged on the same patterns the draft encoded.
- Decision: delete the drafted `skills/trackio/`; the official skill install (`uvx trackio skills add --opencode --global`) is part of kit skill setup in the README (per-project install documented as the alternative). The kit keeps no duplicate of upstream docs — the workflow rules that matter (§2 progress lines, §1.7 `experiments.jsonl`, dependency approval) already live in `AGENTS.md`.
- Alternatives: keep the draft for contract integration (mostly duplication; rejected), maintain a forked copy of the upstream docs (maintenance burden; rejected).
- Refs: #19, #20.
- Tags: tracking, skills, maintenance.

## 2026-10-16 — Bootstrap revamp: no `experiment` label, pytest seeded, README skeleton

- Context: the auto-created `experiment` label got applied indiscriminately (even documentation issues), bootstrapped repos had no runnable test command for the first PR's §3 requirement, and project READMEs had no shared structure for returning readers or fresh agents.
- Decision: drop the label everywhere it was bootstrapped (creation step, issue-template auto-label, §1 example; contract → v1.1). Bootstrap now seeds `uv add --dev pytest` + a placeholder `tests/test_smoke.py`, records `uv run pytest` in the README, starts the project README from `templates/README.md` (goal / commands / layout / where things live / glossary), sets the repo description from the goal, enables `--delete-branch-on-merge`, and linearizes the steps (files → commit → remote → first issue → PR) with an explicit no-remote path.
- Alternatives: better labeling instructions (the spam persisted; rejected); defer test setup to the first real PR (first review had nothing runnable; rejected); free-form READMEs (a shared front-page structure helps multi-agent repos; rejected).
- Refs: #21.
- Tags: bootstrap, workflow, template.
