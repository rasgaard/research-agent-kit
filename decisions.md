# Decisions

Append-only log. Entries follow the `AGENTS.md` §1.8 format (date-title heading, then Context / Decision / Alternatives / Refs / Tags). Never rewrite history — record reversals as new entries. Decisions made before this log exists (issues/PRs #1–#14) live in the merged PR history.

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
- Decision: delete the drafted `skills/trackio/`; the official skill install (`uvx trackio skills add --opencode --global`) is part of kit skill setup in the README (per-project install documented as the alternative). The kit keeps no duplicate of upstream docs — the workflow rules that matter (§2 progress lines, §1.8 `experiments.jsonl`, dependency approval) already live in `AGENTS.md`.
- Alternatives: keep the draft for contract integration (mostly duplication; rejected), maintain a forked copy of the upstream docs (maintenance burden; rejected).
- Refs: #19, #20.
- Tags: tracking, skills, maintenance.

## 2026-10-16 — Bootstrap revamp: no `experiment` label, pytest seeded, README skeleton

- Context: the auto-created `experiment` label got applied indiscriminately (even documentation issues), bootstrapped repos had no runnable test command for the first PR's §3 requirement, and project READMEs had no shared structure for returning readers or fresh agents.
- Decision: drop the label everywhere it was bootstrapped (creation step, issue-template auto-label, §1 example; contract → v1.1). Bootstrap now seeds `uv add --dev pytest` + a placeholder `tests/test_smoke.py`, records `uv run pytest` in the README, starts the project README from `templates/README.md` (goal / commands / layout / where things live / glossary), sets the repo description from the goal, enables `--delete-branch-on-merge`, and linearizes the steps (files → commit → remote → first issue → PR) with an explicit no-remote path.
- Alternatives: better labeling instructions (the spam persisted; rejected); defer test setup to the first real PR (first review had nothing runnable; rejected); free-form READMEs (a shared front-page structure helps multi-agent repos; rejected).
- Refs: #21.
- Tags: bootstrap, workflow, template.

## 2026-10-16 — Contract cleanup: de-duplicated rules, §1.4 bulleted, logs split into §1.8

- Context: an independent audit of `AGENTS.md` flagged one dense paragraph (six rules), rules stated twice (review nits, docs, tests, §5 echoes of §1.2/§2), a misfiled checklist item, and a §1.7 heading covering mostly logging formats.
- Decision: §1.4 became bullets; review-nits merged into §1.3; checklist docs/tests items became section refs (`(see §1.5)`, `(see §3)`); §5 keeps only rules with no other home (force-push/rebase/merge-own, scope growth, invented citations); branch cleanup moved to §1.2; new §1.8 "Log decisions and results as you go" owns both log formats. Contract → v1.2; §1.7 refs updated to §1.8 across README/decisions/templates.
- Alternatives: relocating the format blocks into `skills/` (the audit's main cut — bigger change, deferred); keeping the checklist self-contained (refs follow the file's existing dedup pattern, e.g. §5's "(see §1.2)"); acting on the remaining audit findings ("green", approval-gate lists, `experiments.jsonl` bootstrap gap) — out of scope, candidates for follow-up issues.
- Refs: #23.
- Tags: template, cleanup, versioning.

## 2026-10-19 — DTU HPC: local-first control plane, one auth per session

- Context: managed work Mac (SSH/CLI only, no VPN/always-on relay) and a flaky connection made login-node work painful; DTU requires key + key passphrase + DTU password outside campus, so unattended passwordless access is impossible.
- Decision: add `bin/hpc` + `skills/dtu-hpc` to the kit. Code ships as an immutable `git archive` snapshot at a SHA (no HPC GitHub credentials); ControlMaster/ControlPersist gives one auth per session; batch jobs are LSF-owned and survive drops; interactive work lives in `tmux`; data via revision-pinned HF with a `/work3` cache.
- Alternatives: always-on DTU relay/Tailscale (needs hardware + policy approval; rejected for now); remote git clone + deploy keys (extra secret surface; rejected); rsync code trees/Syncthing (drift; rejected); storing the DTU password for autossh (security regression; rejected).
- Refs: #25.
- Tags: hpc, workflow, auth, sync.

## 2026-10-20 — HPC storage: BeeGFS default, project NFS override

- Context: `$HOME` is `/zhome` with selective symlinks (`.cache`, `repos`, `.vscode-server`) into `/work3`; `/dtu/p1/roraa` is a 60T project scratch already holding `patientsim-scratch` and `ppl-lies-scratch`.
- Decision: keep the kit's default on `/work3` (BeeGFS is faster for code snapshots and uv venvs, and the kit is small); reserve `/dtu/p1` for data-heavy projects. `remote_root` and the example job's `SCRATCH` are overridable per project.
- Alternatives: move everything to `/dtu/p1` (slower venv installs, no benefit for a small tooling repo; rejected); put venv/caches on `/dtu/p1` while code stays on `/work3` (extra split for no gain; rejected).
- Refs: #25.
- Tags: hpc, storage, workflow.

## 2026-10-20 — HPC first-run: detect the SSH alias, store secrets remotely, sync one venv

- Context: the first real `dtu-hpc` use hit avoidable friction: config defaulted to an alias the install never created, `doctor` could prompt while checking a stale master, local API-key exports did not cross `hpc submit`, and the shared venv path was undocumented.
- Decision: `hpc init` detects an existing DTU `Host`/`HostName` in `~/.ssh/config` (or accepts `--ssh-host`) and refuses to invent a broken `dtu` default; `hpc doctor` uses `BatchMode` and reports a dead/stale socket without prompting; `hpc secret set NAME` writes `~/.config/dtu-hpc/secrets.env` on the cluster via stdin with mode 600; `hpc sync-env` ships `HEAD` and runs `uv sync --frozen` into the configured shared venv; jobs render `{{VENV}}`, `{{HF_HOME}}`, `{{UV_CACHE}}`, and `{{SECRETS}}`.
- Alternatives: keep the `dtu` config default with a warning (still fails first-run; rejected); rely on local env forwarding (does not cross SSH; rejected); store secrets in argv or the repo (leaks; rejected); rebuild the venv per job (wasteful; rejected).
- Refs: #27.
- Tags: hpc, ux, auth, secrets, venv.

## 2026-10-20 — Post-implementation issue status comment is part of delivery

- Context: #27 was implemented and its PR opened, but the issue thread stayed silent until the human explicitly asked for a status update; §1.5 encouraged thread updates without making the post-PR comment a required step.
- Decision: §1.3 now requires an immediate short issue comment after opening the PR — PR link, what landed, verification, caveats — before reporting back in chat; the pre-review checklist includes it. Contract → v1.3.
- Alternatives: rely on the PR link/title alone (reviewers lose the issue-thread context and verification summary; rejected); leave it to §1.5's general "intermediate results" guidance (too easy to skip; rejected).
- Refs: #29.
- Tags: workflow, github, communication, template.

## 2026-10-20 — HPC queue selection: p1 by default, no queue-hopping

- Context: an agent killed pending jobs on `p1` and `gpua40` to chase a shorter “jobs ahead” snapshot on `gpua10`; queue-depth estimates are noisy, the shuffle loses position, and the user prefers one queue unless there is a real reason.
- Decision: the `dtu-hpc` skill defaults GPU batch work to `p1`. Switch only for explicit user instruction or a hard resource mismatch (GPU model/memory, walltime, access/quota), document the reason once, and make at most one deliberate switch. Do not kill pending/running jobs solely to chase a shorter queue.
- Alternatives: pick the queue with the shortest estimated wait each time (noisy and churn-heavy; rejected); always use the fastest hardware queue regardless of fit (wastes scarce resources; rejected); leave it implicit (the observed over-indexing recurs; rejected).
- Refs: #31.
- Tags: hpc, queues, workflow, guardrails.

## 2026-10-20 — HPC scheduling: one job by default, arrays only for throughput

- Context: the skill said “use arrays for sweeps” without a decision rule, biasing toward arrays; arrays create N queue entries with no co-scheduling guarantee, while one job holds a single allocation and amortizes setup/model loading.
- Decision: default to one job with an internal loop; chunk into roughly 2–8 jobs when the total exceeds one walltime; use an array only for many substantial independent units where parallel throughput matters, always capped with `%K`; never array tiny, ordered, or single-node/multi-GPU work.
- Alternatives: always array (queue churn and repeated setup; rejected); always one job (cannot exceed walltime and loses throughput; rejected); leave it implicit (the array bias recurs; rejected).
- Refs: #33; PR #34.
- Tags: hpc, scheduling, arrays, workflow, guardrails.

## 2026-10-21 — HF cache warming belongs on compute nodes; no hpc cache yet

- Context: a login-node `snapshot_download` hung silently for 10 minutes with no cache growth, while the same project downloaded weights from compute nodes. Bounded reproduction on 2026-10-21: system Python hung in `urllib3` `create_connection`; forcing IPv4 fixed it; a project venv succeeded, so this is not a blanket login-node block.
- Decision: document the conditional login-node HF hang, its bounded xet/IPv4 checks, and the required “cache on compute, then run offline” ordering. Make `timeout 60` the hard cap for any login-node cache attempt and capture a faulthandler stack if it recurs. Decline `hpc cache`/`hpc fetch` for now because cache path, revision, token, and job-dependency choices are project-specific; revisit if the friction recurs.
- Alternatives: add a generic cache command now (scope creep and ambiguous semantics; rejected); declare login-node downloads blocked (project venv succeeds; rejected); leave the trap undocumented (it silently wastes login-node time; rejected).
- Refs: #37; PR #40.
- Tags: hpc, huggingface, downloads, login-node, offline, workflow.
