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

## 2026-10-16 — Trackio ships as an on-demand skill (revisits the #14 deferral)

- Context: #14 deferred trackio ("dependency + doesn't fix capture"). Session request: useful, but must not sit in context every turn.
- Decision: `skills/trackio/SKILL.md` — loaded only when experiment tracking comes up; `AGENTS.md` untouched. The skill encodes the wiring pattern (`init`/`log`/`finish`, `config`/`group`), JSON-CLI metric reading for agents, dashboard handoff for humans, alerts, and Space sync gated on explicit approval (public by default); restates that §2 progress lines and §1.7 `experiments.jsonl` are unchanged.
- Alternatives: tracking guidance inside `AGENTS.md` (context cost every turn; rejected), pointing at upstream docs only (agent must re-research every time), no skill (status quo).
- Refs: #19.
- Tags: tracking, skills, ux, agents.
