# Queues and job scripts

Sources: <https://www.hpc.dtu.dk/?page_id=2759>, <https://www.hpc.dtu.dk/?page_id=3098>, <https://www.hpc.dtu.dk/?page_id=2129>. Docs can lag — verify with `bqueues`, `classstat`, `nodestat -g`.

## Three tiers

| Tier | Where | Use for | Lifetime |
|---|---|---|---|
| Local CPU | Mac | unit tests, 10-step run, shape/NaN checks | seconds |
| Interactive GPU | `a100sh`, `voltash`, `sxm2sh`, `p1i` (shared, in `tmux`) | import/CUDA check, one forward/backward, profiling | minutes |
| Batch GPU/CPU | `gpua100`, `gpul40s`, `gpuv100`, `gpua10`, `gpua40`, `hpc` | real runs, sweeps | GPU ≤24 h, CPU ≤72 h |

Interactive nodes are the debug queue; batch is never used to discover that a job crashes at import.

## API-bound jobs do not need a GPU

If the job only calls an external API (an LLM judge or student) and does any
model work on CPU, do **not** take a GPU. Use the `hpc` CPU queue instead:

```sh
#BSUB -q hpc
#BSUB -n 1
#BSUB -R "rusage[mem=8GB]"
#BSUB -W 24:00
```

- The 72 h ceiling is the real constraint. Chunk work per cell, write one output
  per cell, and make the runner skip completed cells on re-submit.
- Export API keys from the submit environment; never write them into the repo or
  the job script.
- Compute nodes have network egress. Prove it with a one-call smoke before a
  long run.
- Use `python -u` so `bpeek`/`hpc logs -f` show progress.

## GPU queues

| Queue | Hardware (per node) |
|---|---|
| `gpua100` | 2× A100 PCIe 40 GB / 80 GB |
| `gpul40s` | 2× L40S 48 GB |
| `gpuv100` | 2× V100 16/32 GB; some 4× V100-32 NVLink |
| `gpua10` | 2× A10 24 GB |
| `gpua40` | 2× A40 48 GB NVLink |
| `gpuamd` | 2× AMD MI25 |
| `p1` | Hopper (H100) pioneer queue; max 1 node/job; access via project shares |

Request: `#BSUB -gpu "num=1:mode=exclusive_process"`. Extras: `-R "select[gpu32gb]"`, `-R "select[sxm2]"`. Two GPUs: `-n 8` + `num=2`.

## Template essentials

```sh
#BSUB -q gpua100
#BSUB -J name
#BSUB -n 8
#BSUB -gpu "num=1:mode=exclusive_process"
#BSUB -R "rusage[mem=32GB]"
#BSUB -M 32GB
#BSUB -W 4:00
#BSUB -o {{RUN_DIR}}/logs/%J.out
#BSUB -e {{RUN_DIR}}/logs/%J.err
```

- Always set `-W`; the default is 15 minutes.
- Over-requesting memory/walltime delays scheduling; under-requesting gets the job killed.
- Use `-M` (per-process kill limit) *and* `-R rusage` (scheduling request).
- `python -u` for unbuffered logs so `bpeek` is useful.
- `p1` batch supports `-W`; the `p1i` interactive queue rejects it.
- `p1gpush` works, but it passes `TERM` via `-env`; if `TERM` is unset (e.g. bare `ssh -tt`), LSF rejects it. `hpc gpu p1` exports a fallback `TERM` and requests 2 shared H100s, matching the wrapper.

## Managing jobs

- `bstat`, `bstat -C` (efficiency), `bstat -M` (memory), `bpeek <id>`, `bkill <id>`.
- `showstart <id>` for an ETA; `classstat <queue>` for load; `nodestat -g <queue>` for GPUs.
- Arrays: `#BSUB -J "sweep[1-20]"`; dependencies: `bsub -w "done(<id>)"`.
- Checkpoint every N steps so a kill/requeue is cheap; LSF reruns are not a substitute for app-level checkpoints.
