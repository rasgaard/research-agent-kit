# Queues and job scripts

Sources: <https://www.hpc.dtu.dk/?page_id=2759>, <https://www.hpc.dtu.dk/?page_id=3098>, <https://www.hpc.dtu.dk/?page_id=2129>. Docs can lag — verify with `bqueues`, `classstat`, `nodestat -g`.

## Three tiers

| Tier | Where | Use for | Lifetime |
|---|---|---|---|
| Local CPU | Mac | unit tests, 10-step run, shape/NaN checks | seconds |
| Interactive GPU | `a100sh`, `voltash`, `sxm2sh`, `p1i` (shared, in `tmux`) | import/CUDA check, one forward/backward, profiling | minutes |
| Batch GPU/CPU | `gpua100`, `gpul40s`, `gpuv100`, `gpua10`, `gpua40`, `hpc` | real runs, sweeps | GPU ≤24 h, CPU ≤72 h |

Interactive nodes are the debug queue; batch is never used to discover that a job crashes at import.

## Queue selection: `p1` by default

Use **one** GPU batch queue for a task, normally `p1`. Queue-depth snapshots are a weak signal:
`bstat` pending counts, `classstat` load, and `showstart` ETAs fluctuate and often do not
predict when your job starts. Killing a pending job to chase a shorter queue loses your
position and adds scheduler churn; the next snapshot can reverse the picture.

Switching is justified only by:

- **Explicit user instruction** — the user asked for another queue.
- **A hard resource mismatch** — `p1` cannot run the job (GPU model or memory, walltime,
  project access/quota), or the job requires a queue-specific feature.

When a switch is justified, state the reason once in the issue/PR, submit once to the
replacement queue, and stay there. Do not rotate through `gpua100`/`gpua40`/`gpua10` based on
free-GPU counts, and do not kill a running job to “improve” its queue position. If the
situation is ambiguous, wait or ask; a queue change is not a routine tuning knob.

## One job vs chunked vs array

**Default to one job with an internal loop.** One job holds a single allocation for its whole
`-W`; an array is N independent jobs, each with its own queue wait, and LSF does not guarantee
they are co-scheduled. Arrays are a throughput tool, not a way to reserve a node for the whole
sweep.

| Workload shape | Default | Why |
|---|---|---|
| Total fits one job within walltime; units share setup/model load | **One job, internal loop** | one queue entry, stable allocation, setup paid once |
| Total exceeds walltime; units are short or setup is expensive | **Roughly 2–8 chunk jobs**, each looping over its units | fewer queue entries, holds each allocation for a meaningful block |
| Many independent units, each substantial; parallel throughput is the point | **Array**, capped with `%K` | shorter per-element walltime can backfill; failures are isolated |
| Units must share one node/GPUs, run in order, or are tiny | **Do not array** | no co-scheduling, startup overhead, shared-memory contention |

Decide in this order:

1. Estimate total GPU/CPU-hours. Does it fit one job under the queue walltime with
   roughly 20–30% headroom? → **one job**.
2. If not, can you split it into a few chunks that each fit? → **chunk jobs**; checkpoint
   between units so a walltime kill loses one unit, not the whole chunk.
3. Only if the chunks are still too coarse or you need parallel throughput → **array**, with
   a concurrency cap.
4. If units are tiny, few, ordered, or need one node/multiple GPUs → **stay with one job**.

Rules:

- **Cap arrays.** `#BSUB -J "name[1-N]%K"`; choose `K` from the resources you can fairly use,
  not the size of the sweep. A large uncapped array crowds a shared queue and may hit
  per-user limits.
- **Chunk before arraying.** 100 short units → 4–8 chunk jobs, not 100 elements; 100 long
  units → array with a cap. On `p1`, an array of 1-GPU elements can occupy multiple project
  nodes, so cap it deliberately.
- **Do not pay setup N times.** If each element loads a large model or dataset, loop inside a
  chunk instead.
- **One node/multiple GPUs → one job.** Use `-n` and `num=2` in a single job; array elements
  may land on different nodes.
- **Checkpoint every unit** in either shape; an array element is not a checkpoint. Array tasks
  must write per-task files (`out/$LSB_JOBINDEX.jsonl` or
  `runs/$LSB_JOBID/$LSB_JOBINDEX/`), never append to one shared file concurrently.
- **State the choice** in the issue/PR: one job, chunked, or array; the concurrency cap; and
  why.

Rules of thumb, not hard limits: under about one GPU-day total, prefer one job; several
GPU-days, chunk first; array only when the chunks are still too coarse or parallel throughput
matters. A single long job may wait longer for a contiguous slot than short array elements,
which can backfill — choose based on total work and latency, not just queue position.

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
- Local exports do not cross `hpc submit` (fresh SSH login shell). Store keys with
  `hpc secret set NAME`, then source `{{SECRETS}}` in the job; never write them into
  the repo or the job script.
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
- Array tasks must not append to one shared `experiments.jsonl`/output file
  concurrently. Use `$LSB_JOBINDEX` in the filename (e.g.
  `out/$LSB_JOBINDEX.jsonl`) or a per-task directory (`runs/$LSB_JOBID/$LSB_JOBINDEX/`),
  then merge after the array finishes.
- Checkpoint every N steps so a kill/requeue is cheap; LSF reruns are not a substitute for app-level checkpoints.
