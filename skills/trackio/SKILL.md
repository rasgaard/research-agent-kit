---
name: trackio
description: Instrument experiment scripts with trackio — Hugging Face's lightweight, local-first experiment tracking. Log metrics and configs, query runs as JSON, hand the human a dashboard, optionally sync to an HF Space. USE FOR: trackio, experiment tracking, log training metrics, metrics dashboard, compare runs or sweeps, wandb alternative, read run metrics programmatically. DO NOT USE FOR: progress lines for agent feedback (the AGENTS.md §2 rule — trackio never replaces them), experiment design or scope (issue thread), general HF Hub operations.
---

# Trackio

Local-first experiment tracking by Hugging Face ([docs](https://huggingface.co/docs/trackio/)): metrics go to a local SQLite DB, humans view a local dashboard, agents query JSON. wandb-compatible API (`import trackio as wandb`), free, Python ≥ 3.10. Patterns below verified against trackio 0.42.0.

**Never a replacement for AGENTS.md §2 progress lines.** The dashboard serves humans; the agent's live view of a run is still the periodic plain-text progress line (or `tail -1` of the detached log). trackio complements that — it does not fix agent-side capture.

## When to use

- Wiring tracking into an experiment script (loss curves, sweep comparison, configs).
- Reading back logged metrics programmatically (JSON CLI or Python API).
- Giving the human a dashboard while/after runs happen.

`uv add trackio` needs human approval first (AGENTS.md §2: dependencies). Keep tracking strictly non-fatal: a tracker failure must never kill the experiment (trackio is written defensively for the same reason).

## Minimal wiring

```python
import trackio

trackio.init(
    project="<experiment-name>",
    name=f"lr{lr}-bs{bs}",            # one run = one measured configuration
    group="<sweep-name>",              # groups related runs in the dashboard
    config={"lr": lr, "bs": bs, "seed": seed, "model": model_id},  # the run's reproducibility record
)
for step in range(steps):
    loss, val_loss = ...
    trackio.log({"loss": loss, "val_loss": val_loss}, step=step)
trackio.finish()
```

- Keep `project` stable across a sweep; vary `name`; set `group` for overlay comparison.
- `trackio.log()` is non-blocking (queued; background drain every 0.5 s) and never raises into training code.
- Pass explicit `step=`; otherwise trackio keeps its own counter.
- HF Trainer / TRL: `report_to="trackio"` logs automatically; still call `trackio.finish()`.
- Existing wandb call sites: `import trackio as wandb` is a drop-in.

## Reading metrics (agent-side)

Don't scrape the dashboard; query and relay results into the PR/issue thread (§1.5):

```bash
trackio list runs --project "my-project" --json
trackio get metric --project "my-project" --run "lr1e-3-bs64" --metric "val_loss" --json
trackio query project --project "my-project" --sql "SELECT ..."   # read-only SQL when list/get aren't enough
```

Python: `trackio.Api().runs(project)`, `.alerts(project)`. `experiments.jsonl` (§1.7) stays the canonical one-row-per-measured-config log; trackio is the live store behind it.

## Dashboard (hand off to the human)

```bash
trackio show --project "my-project"    # blocking server; prints a local URL
```

Run it detached (`... > outputs/trackio-show.log 2>&1 &`) during agent sessions, or hand the command to the human. Local data lives at `~/.cache/huggingface/trackio` (override with `TRACKIO_DIR`). trackio is pre-1.0 and the DB schema may change — `uv.lock` pins the exact version; don't rely on cross-version DB compatibility.

## Alerts

`trackio.alert(title=..., text=..., level=trackio.AlertLevel.WARN)` (levels: INFO/WARN/ERROR) flags divergence/completion events in the dashboard; readable via `trackio get alerts --project ... --json`. On long detached runs, alerts + §2 progress lines cover both ends: humans see alerts, the agent polls the progress line.

## HF Space sync — opt-in, ask the human first

`space_id="user/space"` in `init()`, or `trackio sync --project ... --space-id ...`, publishes runs to a free HF Space. **Spaces are public by default** — treat publishing as an external, approval-gated action: confirm with the human, and prefer private deployments where supported. Requires `hf auth login` with a write token; never put tokens in code or commits (§2).

## Checklist

- [ ] Dependency approved (AGENTS.md §2) before `uv add trackio`
- [ ] `config` carries seed + all hyperparameters of the measured configuration
- [ ] `name`/`group` scheme chosen so runs compare cleanly in the dashboard
- [ ] §2 progress lines still in place — trackio does not replace them
- [ ] Results summarized into `experiments.jsonl` (§1.7) and the PR/issue thread (§1.5)
- [ ] Space sync only with explicit approval
