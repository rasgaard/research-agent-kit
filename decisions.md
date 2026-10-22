# Decisions

Append-only log. Entries follow the `AGENTS.md` §1.8 format (date-title heading, then Context / Decision / Alternatives / Refs / Tags). Never rewrite history — record reversals as new entries. Decisions made before this log exists (issues/PRs #1–#14) live in the merged PR history.

Older entries (2026-10-16 through 2026-10-20) moved verbatim to [`decisions-archive.md`](decisions-archive.md) on 2026-10-22 (#54) to keep this file under the ~100-line threshold. Compact index:

- 2026-10-16 — Long runs report plain progress lines, not bars — progress, ux, agents.
- 2026-10-16 — Contract version marker, starting at v1.0 — template, versioning.
- 2026-10-16 — No home-grown trackio skill — use trackio's official one — tracking, skills, maintenance.
- 2026-10-16 — Bootstrap revamp: no `experiment` label, pytest seeded, README skeleton — bootstrap, workflow, template.
- 2026-10-16 — Contract cleanup: de-duplicated rules, §1.4 bulleted, logs split into §1.8 — template, cleanup, versioning.
- 2026-10-19 — DTU HPC: local-first control plane, one auth per session — hpc, workflow, auth, sync.
- 2026-10-20 — HPC storage: BeeGFS default, project NFS override — hpc, storage, workflow.
- 2026-10-20 — HPC first-run: detect the SSH alias, store secrets remotely, sync one venv — hpc, ux, auth, secrets, venv.
- 2026-10-20 — Post-implementation issue status comment is part of delivery — workflow, github, communication, template.

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

## 2026-10-21 — HPC GPU selection: verify torch arch, V100 last resort

- Context: a `gpuv100` load check failed with `no kernel image` because torch 2.14.1 has no `sm_70` kernels; an L40S FP8 failure was initially attributed to arch but was a missing `kernels` 0.17.x extra.
- Decision: document compute capability per GPU queue and treat V100 as a last resort that requires a deliberately pinned `sm_70` torch build; smoke prints device capability and torch arch list; FP8 requires `sm_89`+ plus the compatible `kernels` extra (or bf16 loading).
- Alternatives: declare V100 universally unusable (too absolute; pinned builds may work; rejected); only document the error signatures (misses queue-selection cost; rejected); add an arch check to `hpc doctor` (no job/checkpoint context; declined).
- Refs: #35; PR #38.
- Tags: hpc, gpu, arch, fp8, troubleshooting.

## 2026-10-21 — HPC CLI: arrays are first-class, uncapped arrays refused

- Context: a 13-model sweep exposed four array frictions: `hpc logs` assumed a single log name, no-arg `hpc status` used `bstat` instead of `bjobs -w`, `hpc pull` copied `code/` and broke local test discovery, and `hpc submit` accepted uncapped arrays without warning.
- Decision: `hpc submit` refuses uncapped arrays by default (`--allow-uncapped` is the explicit exception), `hpc logs` discovers per-element files and supports `--index`, `hpc status` uses `bjobs -w` for all jobs and `bstat <id>` for one, and `hpc pull` skips `code/` unless `--include-code` is passed. Queue overrides still warn.
- Alternatives: warning-only array lint (too easy for agents to ignore; rejected); auto-inserting `%K` (silently changes semantics; rejected); keeping `code/` in pulls (duplicates tests and breaks `pytest`; rejected).
- Refs: #36; PR #39.
- Tags: hpc, cli, arrays, logs, pull, status.

## 2026-10-21 — HPC monitoring: local watcher plus event feed

- Context: jobs survive SSH disconnects, but nobody notices completion/failure; the human had to monitor and prompt the agent, and a crashed job could be mistaken for running.
- Decision: ship a two-layer MVP: `hpc watch` polls the ledger via `bjobs`, detects terminal states and stale RUN logs, and writes local events; `hpc events --unread` is the agent-facing feed. No job-side wrapper, auto-resubmit, `bkill`, or merge. Start under tmux; delete the commands and `.git/hpc/events*` to scrap it.
- Alternatives: a subagent as the primary monitor (session-bound, cannot survive a closed CLI or sleep; rejected); job-side status wrapper first (useful later, but not needed for terminal-state detection; deferred); LSF email only (does not wake the agent or provide logs; rejected).
- Refs: #41; PR #42.
- Tags: hpc, monitoring, watcher, events, agent, workflow.

## 2026-10-22 — Distill decision log into archive, keep recent entries

- Context: `decisions.md` had reached 123 lines, past the ~100-line pruning threshold in `AGENTS.md` §1.8.
- Decision: move the 2026-10-16 through 2026-10-20 entries verbatim to `decisions-archive.md` and leave a one-line index here; recent entries stay inline. History is preserved, nothing is rewritten.
- Alternatives: delete old entries (violates append-only; rejected); rewrite entries into summaries in place (rewrites history; rejected); keep appending (crosses the threshold again; rejected).
- Refs: #54.
- Tags: decisions, maintenance, docs.

## 2026-10-22 — Standardize typed commit prefixes

- Context: commit history mixed styles (`fix:`, `docs:`, `hpc:`, `decisions:`), and the contract only said to match repo style, so agents inferred conventions independently and could diverge across projects.
- Decision: §3 now requires `<type>: <imperative summary>` with the type matching the branch type (`feat`, `fix`, `docs`, `test`, `refactor`, `chore`), an optional scope (`fix(hpc): ...`), and a subject under ~72 characters; merge commits are exempt. Contract → v1.5.
- Alternatives: leave it implicit (drift recurs; rejected); mandatory Conventional Commits scopes (too rigid for small repos; rejected); free-form area prefixes like `hpc:` (ambiguous type; rejected).
- Refs: #58; PR #59.
- Tags: git, commits, workflow, template.

## 2026-10-22 — hpc status defaults to a compact job table

- Context: raw `bjobs -w` exposed redundant `USER`/`FROM_HOST`/`EXEC_HOST` columns while omitting the run start time, making the common status check noisy and less useful.
- Decision: `hpc status` now renders `JOBID STAT QUEUE JOB_NAME SUBMIT_TIME START_TIME ELAPSED` from `bjobs -json`, merging array indexes into the job ID; `--hosts` adds `EXEC_HOST`/`FROM_HOST`; `--detail` retains `bstat` for one job's pending reasons and array history.
- Alternatives: keep `bjobs -w` (no start time; noisy; rejected); parse fixed-width `bjobs` columns (fragile; rejected); use `bstat` for everything (no compact all-job view; rejected); include hosts by default (wide and rarely needed; rejected).
- Refs: #60.
- Tags: hpc, cli, status, ux.
