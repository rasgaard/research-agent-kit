---
name: dtu-hpc
description: Use when the user wants to run code on DTU's LSF HPC cluster (login*.hpc.dtu.dk), submit or inspect bsub jobs, open an interactive GPU node, or move code/data/results between a local Mac and /work3. Covers one-auth-per-session SSH multiplexing, SHA-pinned code snapshots, GPU queues, and result pull.
---

# DTU HPC

Local-first workflow: edit and test on the Mac, ship an immutable `git archive` snapshot at a SHA, run under LSF, pull results back. The HPC side never needs GitHub credentials.

**Hard constraint:** outside DTU, auth requires SSH key **+ key passphrase + DTU password**. Unattended passwordless access is impossible without an always-on DTU relay. The goal is *one authentication per working session*, with jobs surviving disconnects.

## Preconditions

- `hpc doctor` is all `ok` (local git/ssh/rsync, live master socket, remote `bsub`/`bstat`/`rsync`).
- If the socket is dead, `hpc login` opens a visible Terminal; the human types the DTU password. Never store it, never use `sshpass`.
- Batch work runs under LSF and is unaffected by SSH drops. Interactive work belongs in `tmux`.

## Workflow

1. **Local smoke first.** Unit tests + a tiny CPU run. Do not spend a GPU slot on "does it import".
1b. **Pick the resource honestly.** GPU only for local model inference. A job
    that only calls an external API (judge/student) and does CPU work belongs on
    the `hpc` CPU queue, not `p1`/`gpua100`.
2. **Commit.** The CLI ships `HEAD`; a dirty tree is refused. WIP commits on a feature branch are fine.
2b. **Interactive check (optional).** `hpc stage` → `hpc shell` (CPU `linuxsh`) or `hpc gpu a100`; `cd .../interactive/current` and run the script. Shared nodes: short tests only.
3. **Dry run.** `hpc submit jobs/<job>.lsf --dry-run` to inspect the rendered script and paths.
4. **Submit.** `hpc submit jobs/<job>.lsf` → job id, run dir, ledger entry in `.git/hpc/jobs.jsonl`.
5. **Watch.** `hpc logs <id> -f` (follow) or `hpc status <id>` (`bstat`). `bpeek` shows output of running jobs.
6. **Pull.** `hpc pull <id>` → `runs/<run_id>/`. Commit small metrics; upload large artefacts to a private HF repo.

## Commands

```text
hpc login                  # ensure master socket (opens Terminal if re-auth needed)
hpc doctor                 # local + remote prerequisites
hpc stage                  # ship HEAD to /work3/.../interactive/current
hpc shell                  # linuxsh shared CPU node, in tmux
hpc gpu a100|v100|sxm2     # shared GPU node, in tmux (short tests only)
hpc gpu p1                 # p1gpush (2 shared H100s)
hpc submit jobs/job.lsf    # [--dry-run] [--name NAME] [--allow-dirty]
hpc status [id]            # bstat (falls back to bjobs)
hpc logs <id> [-f]         # tail the run log (bpeek fallback for unledgered jobs)
hpc pull <id> [--dest D]   # rsync the run dir
```

## Job scripts and queues

- Start from `templates/job.lsf` / `templates/smoke.lsf`. Placeholders `{{CODE_DIR}}`, `{{RUN_DIR}}`, `{{SHA}}`, `{{JOB_NAME}}` are rendered by the CLI.
- GPU queues: `gpua100`, `gpul40s`, `gpuv100`, `gpua10`, `gpua40`, plus `p1` (Hopper, project shares, max 1 node/job); request with `#BSUB -gpu "num=1:mode=exclusive_process"`.
- CPU queue `hpc` (72 h max). Default walltime is only 15 min — always set `-W`.
- Interactive dev nodes: `a100sh`, `voltash`, `sxm2sh`. Shared; use them for a one-step check, then submit batch.
- Check availability with `classstat <queue>`, `nodestat -g <queue>`, `showstart <id>`.
- Checkpoint long jobs; use arrays (`-J "sweep[1-20]"`) for sweeps.

## Guardrails

- Never run applications on the login node; only submit and inspect.
- Queues are shared: keep at most one smoke/pilot job in flight; check `hpc status` and the ledger before submitting, and `bkill` duplicates.
- Never put tokens, keys, or the DTU password in the repo or job scripts.
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
