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
- Set `HF_HUB_OFFLINE=1` once weights are cached, so a run fails loudly instead of
  silently re-downloading a different revision. Record the revision in the manifest.
- Keep large data already on `/work3` where it is; record its path and checksum instead of re-downloading.
- A small `data.lock.json` in the repo is enough:

```json
{"dataset": "org/name", "revision": "<sha>", "path": "/work3/sXXXXXX/data/name"}
```

- Do not use Syncthing, rsync daemons, SSHFS, or DVC remotes for this: there is no always-on endpoint, and code drift is the failure mode we are avoiding.

### Buckets are not dataset repos

Some projects use an HF **bucket** as transport (e.g. `rasgaard/test`). A bucket
is an object store, not a dataset repo: `hf upload --repo-type dataset` fails or
writes to the wrong place. Use the bucket commands instead:

```sh
hf buckets create <user>/<bucket>
hf sync <local-dir> hf://buckets/<user>/<bucket>/
hf buckets cp hf://buckets/<user>/<bucket>/<file> .
```

A bucket id looks like `user/name`, which makes the confusion easy. See
`troubleshooting.md` for the IPv6/DNS hang that can make both commands look
"stuck" before any transfer starts.

## Python env: one shared uv venv on /work3

Compute nodes have PyPI/HF access (verified on `p1`), but re-downloading torch per job is waste. Keep the venv and caches on scratch and sync only from the committed lock:

```sh
module load python3/3.11.9
export PATH="$HOME/.local/bin:$PATH"       # uv lives in ~/.local/bin
export UV_PYTHON_DOWNLOADS=never
export UV_CACHE_DIR="/work3/$USER/.cache/uv"
export UV_PROJECT_ENVIRONMENT="/work3/$USER/hpc/venvs/<name>"
uv sync --frozen --python "$(command -v python3)"
uv run --frozen --no-sync python -u train.py
```

`examples/hf-smoke/` is the working reference; first sync was ~66 s, subsequent `uv sync` audited 72 packages in 183 ms.

## Results

- Small metrics → `experiments.jsonl` or Trackio; commit them via a PR.
- Large artefacts → upload from the HPC job to a private HF repo **or bucket** (write token scoped to that target, stored only on the cluster with mode 600).
- Per-run manifest (recommended in the job script):

```json
{"sha": "...", "job_id": 12345, "queue": "gpua100", "data_revision": "...", "host": "..."}
```

- `hpc pull <id>` rsyncs `runs/<run_id>/` back for inspection; commit only what belongs in the repo.

## Storage facts (verify current quotas)

- Home: `/zhome/$USER`, quota enforced and backed up. Configs only; large code/cache belongs elsewhere. Some users symlink `.cache`, `repos`, `.vscode-server` into `/work3`.
- `/work1` and `/work3/$USER`: BeeGFS scratch, fast, **not backed up**. Default for code snapshots, uv venv/cache, and HF cache.
- `/dtu/p1/$USER`: project NFS scratch, **not backed up**. Use it for large project data and p1 run outputs; it can be slower for venv installs. Quota is per user (check below). Override `remote_root` and `SCRATCH` per project.
- Verify with `df -h` / `readlink -f $HOME`; do not assume `$HOME` itself is a symlink.
- Source: <https://www.hpc.dtu.dk/?page_id=59>.

## Quotas

Cluster free space is **not** your quota. Check the per-user allotments on the login node:

```sh
getquota_work3.sh
getquota_p1.sh
```

Reports update roughly every 30 minutes. `getquota_work3.sh` breaks usage down by BeeGFS storage pool; check both `used` and `hard`, plus the file-count limit. `getquota_p1.sh` prints one line, e.g. `You are using 271.0G of 500G quota`.

## Growth and cleanup

Every `hpc submit` adds a full `code/` snapshot and a run directory; every `hpc stage` adds an interactive snapshot. There is no automatic deduplication or cleanup yet.

- Cost is the **tracked** repo size, not data: `.git`, venvs, `runs/`, and gitignored data are not shipped. The kit is ~69–293 KB per snapshot; 10k jobs is only ~1–3 GB.
- Large tracked files are the failure mode: a 100 MB tracked artefact costs 100 MB per submission. Keep data in HF/`/dtu/p1` and gitignore it.
- Logs, checkpoints, and run outputs usually dominate; `hpc pull` copies them locally but does not remove the remote copy.
- Before a large sweep: pull results, then remove old `jobs/<run_id>/` and `interactive/<timestamp>-<sha>/` directories manually. Keep the ledger and SHA; code is reproducible from git.
- A future `hpc clean` should dry-run by default, keep the newest N jobs, and optionally delete only `code/` while preserving logs. Not implemented yet.
