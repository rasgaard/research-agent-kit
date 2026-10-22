# Sync

Rule: **git is the code source of truth; HF (or an explicit path) is the data source of truth; `/work3` is scratch.**

## Code: immutable snapshot per job

`hpc submit`:

1. Refuses a dirty tree (or warns with `--allow-dirty`) and resolves `HEAD`.
2. Streams `git archive --format=tar.gz <sha>` over SSH into
   `/work3/$USER/hpc/<repo>/jobs/<timestamp>-<sha8>/code`.
3. Renders `{{CODE_DIR}}`, `{{RUN_DIR}}`, `{{SHA}}`, `{{JOB_NAME}}`, `{{VENV}}`, `{{HF_HOME}}`, `{{UV_CACHE}}`, `{{SECRETS}}`, `{{PROJECT_SECRETS}}` into the job script and submits it.

Consequences:

- No git clone, fetch, deploy key, or GitHub token on the HPC.
- Each run's ledger entry records the code SHA, env input/lock hashes, venv path, sync timestamp, and `uv`/Python versions. The venv is mutable: a later sync changes it, so the entry identifies the environment but does not freeze it. To rerun, use the recorded SHA/lock and build a separate env.
- Only tracked files are shipped; uncommitted experiments cannot leak into a run.
- The remote code directory is read-only in spirit: never edit it; commit and resubmit.

## Data: pin revisions, never sync a tree

- Private HF repos for datasets/models; pin a revision (commit hash), not `main`.
- Set `HF_HOME=/work3/$USER/hf` so the cache lives on scratch, not the 30 GB home quota.
- Set `HF_HUB_OFFLINE=1` once weights are cached, so a run fails loudly instead of
  silently re-downloading a different revision. Record the revision in the manifest.
- **Cache on compute, then run offline.** The first job may download with
  `HF_HUB_OFFLINE=0`; set `HF_HUB_OFFLINE=1` only after that job has populated
  `HF_HOME` with the pinned revision. Do not warm the cache from a login-node
  shell; if such a download hangs, see `troubleshooting.md#hf-download-hangs-on-the-login-node`.
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

Re-downloading torch per job is waste, so each project has **one mutable venv** (default `/work3/$USER/hpc/venvs/<repo>`), not one per job or per lock. `hpc sync-env` hashes the environment inputs from `HEAD` (`uv.lock`, `pyproject.toml`, `.python-version`, and `uv.toml` when present) and stores a manifest beside the venv (`<venv>.hpc-env.json`) with the input hash, lock hash, code SHA, sync timestamp, and `uv`/Python versions. It is a no-op when the venv exists and the manifest matches; otherwise it ships `HEAD` to `env/<timestamp>-<sha8>/` and runs `uv sync --locked`.

The login node is an explicit, bounded exception for this package sync: queue wait would block onboarding, and the sync is short and cached. It runs once per environment-input change, never for code-only commits, and is capped with `timeout 600`. Do not use it for HF datasets or model weights.

`hpc submit` refuses a missing, stale, or manifest-less venv and tells you to run `hpc sync-env`. The ledger records `venv`, `lock_sha256`, `env_input_sha256`, `env_synced_at`, and the `uv`/Python versions. A later sync changes the shared env for every job that uses it, so avoid syncing while jobs are queued or running; an old job cannot be made reproducible from its SHA alone.

`examples/hf-smoke/` is the working reference; first sync was ~66 s, subsequent `uv sync` audited 72 packages in 183 ms. The equivalent manual commands (for debugging only) are:

```sh
export PATH="$HOME/.local/bin:$PATH"       # uv lives in ~/.local/bin
export UV_PYTHON_DOWNLOADS=never
export UV_CACHE_DIR="/work3/$USER/.cache/uv"
export UV_PROJECT_ENVIRONMENT="/work3/$USER/hpc/venvs/<repo>"
uv sync --locked                             # interpreter from .python-version/requires-python
uv run --frozen --no-sync python -u train.py
```

The sync does not load or pin a login-node Python module. `uv` resolves the
interpreter from `.python-version` / `requires-python`; with downloads disabled
it uses an already-installed uv-managed interpreter. If none satisfies the
project, install one explicitly (e.g. `uv python install 3.12`) and rerun; the
error names the requirement instead of silently building against the login
node's default.

## Secrets: write remotely, source in the job

Local exports do **not** cross `hpc submit`: it starts a fresh SSH login shell. Store keys on the cluster instead:

```sh
hpc secret set OPENROUTER_API_KEY     # user-wide; prompts or pipe on stdin
hpc secret set --project WANDB_API_KEY  # scoped to this repo's origin
hpc secret list                        # user-wide names
hpc secret list --project              # project names
hpc secret list --all                  # both, grouped
```

User-wide secrets live in `~/.config/dtu-hpc/secrets.env`; project secrets live in
`~/.config/dtu-hpc/projects/<repo-key>.env`, where `<repo-key>` is the repo name
plus a short hash of the `origin` URL. Both are mode 600. Source them from the
job, normally near the top, in this order so project values win:

```sh
[ -f "{{SECRETS}}" ] && . "{{SECRETS}}"
[ -f "{{PROJECT_SECRETS}}" ] && . "{{PROJECT_SECRETS}}"
python -u train.py
```

Values never appear in argv, the repo, or the CLI log. `hpc secret set` takes a
remote lock, merges one key, writes a mode-600 temporary file, and atomically
replaces the file; it aborts if the existing file cannot be read and does not
print the value.

Project scoping is organizational: every job runs as your DTU Unix user and can
read any project file it knows the path to. Use separate Unix users or
containers if you need a real access boundary.

## Results

- Small metrics → `experiments.jsonl` or Trackio; commit them via a PR.
- Large artefacts → upload from the HPC job to a private HF repo **or bucket** (write token scoped to that target, stored on the cluster via `hpc secret set` or `hpc secret set --project`, mode 600).
- Per-run manifest (recommended in the job script):

```json
{"sha": "...", "job_id": 12345, "queue": "gpua100", "data_revision": "...", "host": "..."}
```

- `hpc pull <id>` rsyncs `runs/<run_id>/` back for inspection; `code/` is skipped by default so local test discovery does not pick up the snapshot. Use `--include-code` if you need the exact submitted tree; commit only what belongs in the repo.

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
