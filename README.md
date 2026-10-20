# research-agent-kit

Home of the reusable research-assistant setup: the `AGENTS.md` collaboration contract (issue → branch → PR via GitHub) plus the opencode skill that bootstraps it into new projects. This repo is the source of truth — installed copies are symlinks, never forks.

## Layout

```text
AGENTS.md                    # canonical template (copy verbatim, never per-project edits here)
skills/research-init/        # opencode skill: "start a new research project"
  SKILL.md                   # bootstrap procedure, references ../.. /AGENTS.md
  templates/README.md        # project README skeleton (goal, commands, layout, glossary)
  templates/github/          # .github/ issue/PR templates copied into new projects
skills/dtu-hpc/              # optional: DTU LSF workflow (local-first, SHA-pinned jobs)
  SKILL.md                   # commands, guardrails, re-auth protocol
  references/                # auth, sync, queues — verified DTU docs
bin/hpc                      # stdlib CLI: login/shell/gpu/submit/status/logs/pull
examples/hf-smoke/           # uv + torch + transformers + datasets p1 job (verified)
templates/                   # LSF job + smoke templates, ssh_config, config.ini
tests/test_hpc.py            # stubbed CLI tests (no network)
decisions.md                 # append-only decision log for the kit itself
```

## Use in a new project

Say **"start a new research project"** with the skill installed, or manually: copy `AGENTS.md` into the project and follow the bootstrap checklist in `skills/research-init/SKILL.md`. The bootstrap also starts the project README from `templates/README.md` and installs `.github/` issue/PR templates from `skills/research-init/templates/github/`; manual readers should copy those too.

## Install the skills

```bash
mkdir -p ~/.config/opencode/skills ~/.local/bin
ln -s "$(pwd)/skills/research-init" ~/.config/opencode/skills/research-init
ln -s "$(pwd)/skills/dtu-hpc" ~/.config/opencode/skills/dtu-hpc
ln -s "$(pwd)/bin/hpc" ~/.local/bin/hpc
uvx trackio skills add --opencode --global
```

Then quit and restart opencode (config-time files load at startup only). `~/.local/bin` must be on `PATH`.

## DTU HPC (optional)

Local-first workflow for DTU's LSF cluster: edit/test on the Mac, ship an immutable `git archive` snapshot at a SHA, run under LSF, pull results. No GitHub credentials or git clone on the cluster.

- **Auth:** outside DTU requires key + key passphrase + DTU password, so fully unattended access is impossible. `ControlMaster`/`ControlPersist` gives **one auth per session**; jobs survive disconnects. The DTU password is never stored.
- **Queues:** local CPU smoke → interactive GPU (`a100sh`/`voltash`/`sxm2sh`/`p1i`, in `tmux`) → batch (`gpua100`, `gpul40s`, `gpuv100`, `p1`, …).
- **Data:** private HF repos pinned by revision (or buckets via `hf sync` / `hf buckets cp`), cached in `/work3/$USER/hf`; large project data can live in `/dtu/p1/$USER` (P1 scratch) via `SCRATCH`; results via `hpc pull` + small metrics in git.
- **Quotas:** cluster free space is not your allotment; run `getquota_work3.sh` and `getquota_p1.sh` on the login node.

```bash
cp templates/ssh_config ~/.ssh/config.d/dtu     # then edit User/HostName; include it from ~/.ssh/config
ssh-add --apple-use-keychain ~/.ssh/gbar
cp templates/config.ini ~/.config/dtu-hpc/config.ini   # optional; defaults work
hpc doctor
hpc login
hpc stage                       # HEAD → /work3/.../interactive/current
hpc shell                       # CPU shared node (linuxsh), or: hpc gpu a100|p1
hpc submit templates/smoke.lsf --dry-run
hpc submit templates/smoke.lsf
hpc logs <job-id> -f
hpc pull <job-id>
```

See `skills/dtu-hpc/` for the full procedure and guardrails.

## Experiment tracking

The trackio command above installs trackio's own official agent skill (logging, retrieval, storage schema, alerts) globally — loaded on demand, so it stays out of context until experiment tracking comes up. It also adds a `/logbook` command (`--no-command` skips it). For a per-project copy instead — travels with the repo, lands under `.agents/skills/trackio/` — rerun without `--global`. The kit deliberately does not duplicate upstream docs; the workflow rules that matter are already contract text (`AGENTS.md` §2 progress lines, §1.8 `experiments.jsonl`, dependency approval).

## Evolving the template

Change `AGENTS.md` here via issue → branch → PR like any research change. Line 3 of `AGENTS.md` carries the contract version (`Contract vX.Y (date)`); bump minor for template changes and major for breaking ones, and note breaking changes in the PR description. Consumers copy at bootstrap time — the version marker is how they spot a stale copy.
