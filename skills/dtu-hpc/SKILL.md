---
name: dtu-hpc
description: Use when the user wants to run code on DTU's LSF HPC cluster (login*.hpc.dtu.dk), submit or inspect bsub jobs, open an interactive GPU node, or move code/data/results between a local Mac and /work3. Covers one-auth-per-session SSH multiplexing, SHA-pinned code snapshots, GPU queues, and result pull.
---

# DTU HPC

Local-first workflow: edit and test on the Mac, ship an immutable `git archive` snapshot at a SHA, run under LSF, pull results back. The HPC side never needs GitHub credentials.

**Hard constraint:** outside DTU, auth requires SSH key **+ key passphrase + DTU password**. Unattended passwordless access is impossible without an always-on DTU relay. The goal is *one authentication per working session*, with jobs surviving disconnects.

## First run

```text
hpc init                 # detect the DTU SSH alias; write config
hpc login                # one Terminal auth for this session
hpc sync-env             # once in a project with uv.lock; build the shared venv
hpc doctor               # local + remote checks
hpc stage                # optional interactive smoke
```

## Preconditions

- `hpc init` has written `~/.config/dtu-hpc/config.ini`; pass `--ssh-host <alias>` if `~/.ssh/config` is not detected.
- `hpc doctor` is all `ok` (local git/ssh/rsync, live master socket, remote `bsub`/`bstat`/`rsync`/`uv`, synced venv; a missing secrets file is a note, a wrong mode fails).
- If the socket is dead or stale, `hpc login` opens a visible Terminal; the human types the DTU password. Never store it, never use `sshpass`. `hpc doctor` never prompts.
- Batch work runs under LSF and is unaffected by SSH drops. Interactive work belongs in `tmux`.

## Workflow

1. **Local smoke first.** Unit tests + a tiny CPU run. Do not spend a GPU slot on "does it import".
1b. **Pick the resource honestly.** GPU only for local model inference. A job
    that only calls an external API (judge/student) and does CPU work belongs on
    the `hpc` CPU queue, not `p1`/`gpua100`.
2. **Commit.** The CLI ships `HEAD`; a dirty tree is refused. WIP commits on a feature branch are fine.
2b. **Interactive check (optional).** `hpc stage` → `hpc shell` (CPU `linuxsh`) or `hpc gpu a100`; `cd .../interactive/current` and run the script. Shared nodes: short tests only.
3. **Dry run.** `hpc submit jobs/<job>.lsf --dry-run` to inspect the rendered script and paths. Dry-run ships nothing and therefore allows a dirty tree; it still renders `HEAD`.
4. **Submit.** `hpc submit jobs/<job>.lsf` → job id, run dir, ledger entry in `.git/hpc/jobs.jsonl`.
5. **Watch.** `hpc logs <id> -f` (follow) or `hpc status <id>` (`bstat`). `bpeek` shows output of running jobs.
6. **Pull.** `hpc pull <id>` → `runs/<run_id>/`. Commit small metrics; upload large artefacts to a private HF repo.

## Commands

```text
hpc init [--ssh-host A]    # write config; detect a DTU alias in ~/.ssh/config
hpc login                  # ensure master socket (opens Terminal if re-auth needed)
hpc sync-env               # ship HEAD and uv sync into the configured shared venv
hpc secret set NAME        # set a job secret via stdin/prompt; mode 600 on the cluster
hpc secret list            # key names only
hpc doctor                 # local + remote prerequisites; never prompts
hpc stage                  # ship HEAD to /work3/.../interactive/current
hpc shell                  # linuxsh shared CPU node, in tmux
hpc gpu a100|v100|sxm2     # shared GPU node, in tmux (short tests only)
hpc gpu p1                 # p1gpush (2 shared H100s)
hpc submit jobs/job.lsf    # [--dry-run] [--name NAME] [--allow-dirty] [--allow-uncapped]
hpc status [id]            # bjobs -w (all) / bstat <id> (one)
hpc logs <id> [-f] [--index N]  # tail per-element logs for arrays
hpc pull <id> [--dest D] [--include-code]  # rsync; code/ is skipped by default
```

## Job scripts and queues

- **Stay on one queue.** Default GPU batch queue is `p1`. Do not rotate queues because a snapshot shows fewer “jobs ahead”: `bstat`/`classstat`/`showstart` estimates are noisy, and killing a pending job loses its position. Switch only for (a) explicit user instruction or (b) a hard resource mismatch (GPU model/memory, walltime, access/quota) that `p1` cannot satisfy. State the reason once in the issue/PR and make one deliberate switch — never a shuffle loop.
- Start from `templates/job.lsf` / `templates/smoke.lsf`. Placeholders `{{CODE_DIR}}`, `{{RUN_DIR}}`, `{{SHA}}`, `{{JOB_NAME}}`, `{{VENV}}`, `{{HF_HOME}}`, `{{UV_CACHE}}`, `{{SECRETS}}` are rendered by the CLI.
- GPU queues: `gpua100`, `gpul40s`, `gpuv100`, `gpua10`, `gpua40`, plus `p1` (Hopper, project shares, max 1 node/job); request with `#BSUB -gpu "num=1:mode=exclusive_process"`.
- CPU queue `hpc` (72 h max). Default walltime is only 15 min — always set `-W`.
- Interactive dev nodes: `a100sh`, `voltash`, `sxm2sh`. Shared; use them for a one-step check, then submit batch.
- Check availability with `classstat <queue>`, `nodestat -g <queue>`, `showstart <id>`.
- **Default to one job with an internal loop.** Chunk into roughly 2–8 jobs when the total exceeds one walltime, and use an array only for many substantial independent units where parallel throughput is the point. Arrays are N queue entries with no co-scheduling guarantee; cap them (`-J "name[1-N]%K"`), and never array work that needs one node or multiple GPUs together. The CLI refuses an uncapped array; add `%K` or pass `--allow-uncapped` for an intentional exception. See `references/queues.md#one-job-vs-chunked-vs-array`.
- Checkpoint every unit. Array tasks must write per-task files (`out/$LSB_JOBINDEX.jsonl` or `$LSB_JOBID/$LSB_JOBINDEX/`), never append to one shared file concurrently.

## Guardrails

- Never run applications on the login node; only submit and inspect.
- Queues are shared: keep at most one smoke/pilot job in flight; check `hpc status` and the ledger before submitting, and `bkill` duplicates. Never kill a pending/running job solely to chase a shorter queue.
- Never put tokens, keys, or the DTU password in the repo or job scripts. Local `export` does not cross `hpc submit`; use `hpc secret set NAME`, then source `{{SECRETS}}` in the job (see `references/sync.md`).
- Code is immutable per run: if you need a change, commit and submit a new job; do not edit `{{CODE_DIR}}`.
- Data lives in `/work3/$USER` (not backed up) or a private HF repo pinned by revision; home is 30 GB and backed up.
- Large artefacts go to a private HF repo **or bucket** (`hf sync` / `hf buckets cp`); `hf upload --repo-type dataset` does not work on a bucket.
- Pull metrics and logs with `hpc pull`; do not rsync gigabytes of checkpoints back.
- If auth needs a human, stop and say so; do not attempt to automate the DTU password.

## References

- `references/auth.md` — SSH key, ControlMaster, re-auth, tmux, security.
- `references/sync.md` — code snapshots, HF data pinning, buckets, run manifests, result flow.
- `references/queues.md` — queue parameters, template guidance, API-bound CPU jobs, smoke/batch tiers.
- `references/troubleshooting.md` — IPv6/DNS hangs, bucket-vs-repo errors, import races, walltime kills.
