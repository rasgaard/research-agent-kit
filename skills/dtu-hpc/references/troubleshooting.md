# Troubleshooting

Symptoms seen in real runs, with fixes. Prefer a fix over a blind retry.

## Python/HF hangs before any transfer (IPv6-first DNS)

**Symptom:** `huggingface_hub`/`requests` hangs at connect, often with no error
and no bytes transferred. `curl -4` works; `curl -6` does not.

**Cause:** the network advertises AAAA first but has no working IPv6 route, so
Python waits on the AAAA attempt before falling back.

**Fix:** force IPv4 for that job only, via a `sitecustomize.py` on `PYTHONPATH`
(never patch the system Python):

```python
# sitecustomize.py
import socket

_orig = socket.getaddrinfo


def _v4(host, port, family=0, type=0, proto=0, flags=0):
    return _orig(host, port, socket.AF_INET, type, proto, flags)


socket.getaddrinfo = _v4
```

```sh
# in the job script
export PYTHONPATH="$PWD/vendor:$PYTHONPATH"
python -c "import socket; print(socket.getaddrinfo('huggingface.co', 443)[0][0])"
# -> AddressFamily.AF_INET
```

## `no kernel image is available for execution on the device`

**Symptom:** model init or the first CUDA kernel fails with
`torch.AcceleratorError: CUDA error: no kernel image is available for execution
on the device`, often on `gpuv100`.

**Cause:** the installed torch wheel has no kernels for the GPU’s compute
capability. Current torch 2.14.1 wheels exclude `sm_70` (V100), so this is not
model-specific.

**Fix:** check `torch.cuda.get_device_capability()` and
`torch.cuda.get_arch_list()` on the node. Resubmit on a supported architecture
(`sm_80`+, preferably `sm_86`/`sm_89`/`sm_90`). Treat `gpuv100` as a last resort:
use it only with a pinned torch build that includes `sm_70`, and smoke-test the
exact checkpoint. Do not retry the same queue with the same environment.

## `Fp8Dequantize` fails, or a checkpoint reports `Ckpt contains: 3`

**Symptom:** loading an FP8 checkpoint fails during weight conversion, sometimes
with `no kernel image` on older GPUs. On `gpul40s` the same load can instead fail
with:

```text
ImportError: finegrained-fp8 kernel unavailable: 'kernels' is either not
installed or uses an incompatible version (0.17.0 <= version < 0.18.0)
```

**Cause:** FP8 dequantisation needs FP8-capable hardware (`sm_89`+; L40S or
H100). Pre-`sm_89` GPUs (`V100`, `A100`, `A10`, `A40`) cannot run it. On
`sm_89`+, fine-grained FP8 checkpoints additionally need the `kernels` extra.

**Fix:** use `gpul40s` or `p1` for FP8, and install the compatible `kernels`
version in the job venv (or load the model in bf16 if the checkpoint allows it).
Do not treat this as a generic “newer GPU” problem: the package extra is part of
the requirement.

## `hf upload --repo-type dataset` fails: the target is a bucket

Buckets are **not** dataset repos. `--repo-type dataset` errors or writes to the
wrong place. Use the bucket commands:

```sh
hf buckets create <user>/<bucket>
hf sync <local-dir> hf://buckets/<user>/<bucket>/
hf buckets cp hf://buckets/<user>/<bucket>/<file> .
```

`hf sync` handles buckets and directories; `hf buckets cp` handles single files.
A bucket id looks like `user/name`, which is why it is easy to mistake for a repo.

## Concurrent array tasks die importing `transformers`

**Symptom:** `FileNotFoundError` mid-walk inside `transformers` on a shared
filesystem, only when several array tasks start together.

**Cause:** the shared FS shows a momentarily stale view while `transformers`
walks its package directory.

**Fix:** retry the import with backoff before doing any work (the pattern in
`patientsim-smallLM/grid.py:warm_up_imports` populates `sys.modules`, so later
imports do not re-walk). Do not rerun the whole job for this.

## Long API-bound runs stop at the walltime

**Symptom:** a job that calls an external API is killed at 24 h/72 h with most
cells done.

**Fix:** write one output per cell and a manifest, and make the runner skip
completed cells. Re-submit the same command; do not rely on LSF requeue. Keep
per-cell work small enough that a kill loses at most one cell.

## HF download hangs on the login node

**Symptom:** an HF download started in a login-node shell produces no output and
no cache growth for minutes; the token is valid and the same repo downloads from
a compute node. This is not a universal login-node block, so treat it as “if it
hangs, do X”.

**Reproduced (2026-10-21):** on `login9`, `/usr/bin/python3` with
`HF_HUB_DISABLE_XET=1` hung inside `urllib3` `create_connection` during
`model_info`, with 0 bytes cached after 30 s. The same tiny download completed
in ~3 s after forcing `socket.getaddrinfo` to `AF_INET` (first section). A
project venv (`huggingface_hub 2.2.0`) succeeded on a later attempt, so this is
an environment/HTTP-stack issue, not proof that login-node egress is blocked.

**Rule:** bound every login-node cache attempt with `timeout 60`; this is a hard
cap, not a retry loop. Check xet and IPv4 in the same bounded attempt:

```sh
timeout 60s env HF_HOME=/work3/$USER/hf HF_HUB_DISABLE_XET=1 \
  python3 -c 'from huggingface_hub import snapshot_download; print(snapshot_download("hf-internal-testing/tiny-random-bert", max_workers=1))'
curl -4 -sI https://huggingface.co | head
```

If it times out, do not keep retrying on the login node. Note whether disabling
xet or forcing IPv4 changed anything; the `AF_INET` `sitecustomize` workaround
used by jobs is not automatically present in a plain login shell. If it recurs,
capture a stack before killing it:

```sh
timeout 60s env HF_DEBUG=1 HF_HUB_DISABLE_XET=1 python3 -u -c '
import faulthandler; faulthandler.dump_traceback_later(20, repeat=True)
from huggingface_hub import snapshot_download
snapshot_download("hf-internal-testing/tiny-random-bert", max_workers=1)'
```

**Fix:** first try forcing IPv4 as in the first section. For anything heavy, let
the first batch job populate `HF_HOME` with `HF_HUB_OFFLINE=0`, or submit a short
CPU/GPU job whose only purpose is caching. Wait for it to finish successfully,
then run offline jobs with `HF_HUB_OFFLINE=1`. See
`sync.md#data-pin-revisions-never-sync-a-tree`.

## API key works locally but is missing in the job

**Symptom:** `export OPENROUTER_API_KEY=...` works in a local shell, then the
job sees an empty variable or fails auth.

**Cause:** `hpc submit` opens a fresh SSH login shell. Local environment vars do
not cross; only the submitted script and its remote files travel.

**Fix:** store the key on the cluster and source it in the job:

```sh
hpc secret set OPENROUTER_API_KEY
# or, for a repo-scoped key:
# hpc secret set --project OPENROUTER_API_KEY
# job script:
[ -f "{{SECRETS}}" ] && . "{{SECRETS}}"
[ -f "{{PROJECT_SECRETS}}" ] && . "{{PROJECT_SECRETS}}"
```

Never pass the value on the command line or commit it. For a project-scoped
key, use `hpc secret set --project NAME` and source `{{PROJECT_SECRETS}}` after
`{{SECRETS}}`. If a secrets file exists but is not mode 600, `hpc doctor` flags
it; fix with `chmod 600` on the reported path.

## `hpc doctor` says the socket is stale

**Symptom:** `ssh -O check` returns success, but remote probes hang or fail with
`Permission denied`.

**Cause:** the ControlMaster process outlived its authenticated session.

**Fix:** run `hpc login` and complete the DTU password prompt in the Terminal.
Do not retry `hpc doctor`; it deliberately never prompts.

## `hpc sync-env` fails on `uv sync --locked`

**Symptom:** the venv is missing or `uv` reports the lock is out of date.

**Fix:** commit the updated environment inputs (including `uv.lock`), then
rerun `hpc sync-env` (it ships `HEAD` and writes the env manifest). If
`submit` says the venv is stale, run `hpc sync-env` before resubmitting. Do
not run an unlocked `uv sync` in the job; that makes runs non-reproducible and
races other jobs using the shared venv.

## `hpc sync-env` cannot find a compatible Python

**Symptom:** `uv` reports that the login-node interpreter is incompatible with
`requires-python`, e.g. `requires-python = ">=3.12"` but Python 3.11.9 was
found.

**Cause:** no uv-managed interpreter satisfies `.python-version` /
`requires-python`, and sync sets `UV_PYTHON_DOWNLOADS=never` so it does not
silently download one.

**Fix:** install a matching interpreter once on the login node (for example
`uv python install 3.12`), then rerun `hpc sync-env`. To pin it, add
`.python-version`; do not work around this by symlinking
`~/.local/bin/python3` or loading a login module, which makes the build depend
on the login-node default.

## Logs are empty until the job ends

Use `python -u` (unbuffered). `bpeek` and `hpc logs -f` then show progress.

## A ~4B patient runs out of memory

Load one model at a time and free it between models; request `rusage[mem=32GB]`
for 4B-class weights, and avoid `device_map=auto` disk-offload warnings on small
GPUs. A 24 GB L40S/A10 handles 4B inference comfortably; 8 GB does not.
