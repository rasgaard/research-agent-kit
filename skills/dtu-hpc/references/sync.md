# Sync

Rule: **git is the code source of truth; HF (or an explicit path) is the data source of truth; `/work3` is scratch.**

## Code: immutable snapshot per job

`hpc submit`:

1. Refuses a dirty tree (or warns with `--allow-dirty`) and resolves `HEAD`.
2. Streams `git archive --format=tar.gz <sha>` over SSH into
   `/work3/$USER/hpc/<repo>/jobs/<timestamp>-<sha8>/code`.
3. Renders `{{CODE_DIR}}`, `{{RUN_DIR}}`, `{{SHA}}`, `{{JOB_NAME}}` into the job script and submits it.

Consequences:

- No git clone, fetch, deploy key, or GitHub token on the HPC.
- Every run is reproducible from the SHA recorded in `.git/hpc/jobs.jsonl`.
- Only tracked files are shipped; uncommitted experiments cannot leak into a run.
- The remote code directory is read-only in spirit: never edit it; commit and resubmit.

## Data: pin revisions, never sync a tree

- Private HF repos for datasets/models; pin a revision (commit hash), not `main`.
- Set `HF_HOME=/work3/$USER/hf` so the cache lives on scratch, not the 30 GB home quota.
- Keep large data already on `/work3` where it is; record its path and checksum instead of re-downloading.
- A small `data.lock.json` in the repo is enough:

```json
{"dataset": "org/name", "revision": "<sha>", "path": "/work3/sXXXXXX/data/name"}
```

- Do not use Syncthing, rsync daemons, SSHFS, or DVC remotes for this: there is no always-on endpoint, and code drift is the failure mode we are avoiding.

## Results

- Small metrics → `experiments.jsonl` or Trackio; commit them via a PR.
- Large artefacts → upload from the HPC job to a private HF repo (write token scoped to that repo, stored only on the cluster with mode 600).
- Per-run manifest (recommended in the job script):

```json
{"sha": "...", "job_id": 12345, "queue": "gpua100", "data_revision": "...", "host": "..."}
```

- `hpc pull <id>` rsyncs `runs/<run_id>/` back for inspection; commit only what belongs in the repo.

## Storage facts (verify current quotas)

- Home: ~30 GB, backed up, quota enforced.
- `/work1` and `/work3/$USER`: BeeGFS scratch, fast, **not backed up**.
- Source: <https://www.hpc.dtu.dk/?page_id=59>.
