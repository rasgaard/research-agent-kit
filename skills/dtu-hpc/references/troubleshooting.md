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

## API key works locally but is missing in the job

**Symptom:** `export OPENROUTER_API_KEY=...` works in a local shell, then the
job sees an empty variable or fails auth.

**Cause:** `hpc submit` opens a fresh SSH login shell. Local environment vars do
not cross; only the submitted script and its remote files travel.

**Fix:** store the key on the cluster and source it in the job:

```sh
hpc secret set OPENROUTER_API_KEY
# job script:
[ -f "{{SECRETS}}" ] && . "{{SECRETS}}"
```

Never pass the value on the command line or commit it. If the file exists but is
not mode 600, `hpc doctor` flags it; fix with `chmod 600 ~/.config/dtu-hpc/secrets.env`
on the cluster.

## `hpc doctor` says the socket is stale

**Symptom:** `ssh -O check` returns success, but remote probes hang or fail with
`Permission denied`.

**Cause:** the ControlMaster process outlived its authenticated session.

**Fix:** run `hpc login` and complete the DTU password prompt in the Terminal.
Do not retry `hpc doctor`; it deliberately never prompts.

## `hpc sync-env` fails on `uv sync --frozen`

**Symptom:** the venv is missing or `uv` reports the lock is out of date.

**Fix:** commit the updated `uv.lock`, then rerun `hpc sync-env` (it ships
`HEAD`). Do not run an unfrozen `uv sync` in the job; that makes runs
non-reproducible and races other jobs using the shared venv.

## Logs are empty until the job ends

Use `python -u` (unbuffered). `bpeek` and `hpc logs -f` then show progress.

## A ~4B patient runs out of memory

Load one model at a time and free it between models; request `rusage[mem=32GB]`
for 4B-class weights, and avoid `device_map=auto` disk-offload warnings on small
GPUs. A 24 GB L40S/A10 handles 4B inference comfortably; 8 GB does not.
