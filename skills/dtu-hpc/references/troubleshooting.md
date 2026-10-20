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

## Logs are empty until the job ends

Use `python -u` (unbuffered). `bpeek` and `hpc logs -f` then show progress.

## A ~4B patient runs out of memory

Load one model at a time and free it between models; request `rusage[mem=32GB]`
for 4B-class weights, and avoid `device_map=auto` disk-offload warnings on small
GPUs. A 24 GB L40S/A10 handles 4B inference comfortably; 8 GB does not.
