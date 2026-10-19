# Queues and job scripts

Sources: <https://www.hpc.dtu.dk/?page_id=2759>, <https://www.hpc.dtu.dk/?page_id=3098>, <https://www.hpc.dtu.dk/?page_id=2129>. Docs can lag — verify with `bqueues`, `classstat`, `nodestat -g`.

## Three tiers

| Tier | Where | Use for | Lifetime |
|---|---|---|---|
| Local CPU | Mac | unit tests, 10-step run, shape/NaN checks | seconds |
| Interactive GPU | `a100sh`, `voltash`, `sxm2sh` (shared, in `tmux`) | import/CUDA check, one forward/backward, profiling | minutes |
| Batch GPU/CPU | `gpua100`, `gpul40s`, `gpuv100`, `gpua10`, `gpua40`, `hpc` | real runs, sweeps | GPU ≤24 h, CPU ≤72 h |

Interactive nodes are the debug queue; batch is never used to discover that a job crashes at import.

## GPU queues

| Queue | Hardware (per node) |
|---|---|
| `gpua100` | 2× A100 PCIe 40 GB / 80 GB |
| `gpul40s` | 2× L40S 48 GB |
| `gpuv100` | 2× V100 16/32 GB; some 4× V100-32 NVLink |
| `gpua10` | 2× A10 24 GB |
| `gpua40` | 2× A40 48 GB NVLink |
| `gpuamd` | 2× AMD MI25 |

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

## Managing jobs

- `bstat`, `bstat -C` (efficiency), `bstat -M` (memory), `bpeek <id>`, `bkill <id>`.
- `showstart <id>` for an ETA; `classstat <queue>` for load; `nodestat -g <queue>` for GPUs.
- Arrays: `#BSUB -J "sweep[1-20]"`; dependencies: `bsub -w "done(<id>)"`.
- Checkpoint every N steps so a kill/requeue is cheap; LSF reruns are not a substitute for app-level checkpoints.
