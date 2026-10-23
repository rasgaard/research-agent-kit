# research-agent-kit

Home of the reusable research-assistant setup: the `AGENTS.md` collaboration contract (issue → branch → PR via GitHub) plus the opencode skill that bootstraps it into new projects. This repo is the source of truth — installed copies are symlinks, never forks.

## Layout

```text
AGENTS.md                    # canonical template (copy verbatim, never per-project edits here)
skills/research-init/        # opencode skill: "start a new research project"
  SKILL.md                   # bootstrap procedure; resolves the kit root through symlinks
  scripts/bootstrap.py       # static scaffold copy; dry-run and layout test
  templates/README.md        # project README skeleton (goal, commands, layout, glossary)
  templates/github/          # .github/ issue/PR templates copied into new projects
skills/dtu-hpc/              # optional: DTU LSF workflow (local-first, SHA-pinned jobs)
  SKILL.md                   # commands, guardrails, re-auth protocol
  references/                # auth, sync, queues, monitoring — verified DTU docs
bin/hpc                      # stdlib CLI: init/login/ensure/doctor/sync-env/stage/shell/gpu/submit/status/logs/pull/secret/watch/events
examples/hf-smoke/           # uv + torch + transformers + datasets p1 job (verified)
templates/                   # LSF job + smoke templates, ssh_config, config.ini
tests/test_hpc.py            # stubbed CLI tests (no network)
tests/test_bootstrap.py      # scaffold dry-run/layout tests
decisions.md                 # append-only decision log for the kit itself
decisions-archive.md         # older entries preserved verbatim; indexed from decisions.md
```

## Tests

Stdlib only, no extra dependencies:

```bash
python3 -m unittest discover -s tests -q
```

## Use in a new project

Say **"start a new research project"** with the skill installed, or manually follow `skills/research-init/SKILL.md`. Its `scripts/bootstrap.py` copies `AGENTS.md`, the README skeleton, `.github/`, HPC templates, and `.gitignore`, and creates `experiments.jsonl`; use `--dry-run` to inspect the layout first.

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

- **Auth:** outside DTU requires key + key passphrase + DTU password, so fully unattended access is impossible. `ControlMaster`/`ControlPersist` gives **one auth per session**; jobs survive disconnects. The DTU password is never stored. `hpc init` writes the config; `hpc doctor` never prompts.
- **Queues:** local CPU smoke → interactive GPU (`hpc gpu a100|v100|sxm2|p1`, in `tmux`) → batch (`gpua100`, `gpul40s`, `gpuv100`, `p1`, …). The `p1i` interactive queue is reached with `p1gpush` (via `hpc gpu p1`); `p1i` is not an accepted `hpc gpu` argument.
- **Data:** private HF repos pinned by revision (or buckets via `hf sync` / `hf buckets cp`), cached in `/work3/$USER/hf`; large project data can live in `/dtu/p1/$USER` (P1 scratch) via `SCRATCH`; results via `hpc pull` + small metrics in git.
- **Quotas:** cluster free space is not your allotment; run `getquota_work3.sh` and `getquota_p1.sh` on the login node.

```bash
mkdir -p ~/.ssh/config.d
cp templates/ssh_config ~/.ssh/config.d/dtu     # edit User/HostName
# add `Include config.d/dtu` to ~/.ssh/config (hpc init resolves includes)
ssh-add --apple-use-keychain ~/.ssh/gbar
hpc init                        # detect the DTU alias; write ~/.config/dtu-hpc/config.ini
hpc login                       # one Terminal auth for this session
hpc sync-env                    # sync the shared venv when env inputs change; no-op otherwise
hpc doctor
hpc stage                       # HEAD → /work3/.../interactive/current
hpc shell                       # CPU shared node (linuxsh), or: hpc gpu a100|p1
hpc submit templates/smoke.lsf --dry-run
hpc submit templates/smoke.lsf
hpc watch --notify              # foreground; writes .git/hpc/events.jsonl
hpc events --unread            # agent/human event feed (use nohup for background)
hpc logs <job-id> -f
hpc pull <job-id>
```

Set a user-wide secret without putting it in argv or the repo (prompts, or pipe via stdin; written atomically, mode 600, on the cluster): `hpc secret set OPENROUTER_API_KEY`. Use `hpc secret set --project WANDB_API_KEY` for a key scoped to this repo's origin; project values override user-wide ones.

See `skills/dtu-hpc/` for the full procedure and guardrails.

### Desktop widget (optional, macOS 14+)

`widget/` is a native WidgetKit desktop widget showing running, pending, and failed jobs. It has no third-party runtime. The host app runs `hpc status --json` every 5 minutes and writes `~/.local/state/dtu-hpc/widget.json`; the sandboxed widget only reads that file and never runs SSH.

Build and install (Xcode 27, ad-hoc signing, no packages):

```bash
cd widget
xcodegen generate                      # only needed after editing project.yml
xcodebuild -project DTUHPCStatus.xcodeproj -scheme DTUHPC -configuration Release build
cp -R "$(xcodebuild -project DTUHPCStatus.xcodeproj -scheme DTUHPC -configuration Release -showBuildSettings | awk -F' = ' '/ TARGET_BUILD_DIR /{print $2}')/DTUHPC.app" /Applications/
open /Applications/DTUHPC.app          # then right-click the desktop → Edit Widgets → DTU HPC Jobs
```

- **Refresh:** every 10 minutes by default. Set `[widget] refresh_minutes = 5` (1–60) in `~/.config/dtu-hpc/config.ini`; restart the app to apply.
- **Auth boundary:** the widget and app never prompt for SSH. When the master is dead the snapshot says `login required`; click **Login to HPC** (opens Terminal running `hpc login`) to re-authenticate.
- **Stale:** a snapshot older than two refresh intervals is shown as stale; a failed poll is shown as an explicit error.
- **Tests:** `xcodebuild -project widget/DTUHPCStatus.xcodeproj -scheme DTUHPC test`.
- **Launch at login** uses `SMAppService`, which cannot pass `--background`, so the login launch also opens the window; close it and the app keeps polling. Install in `/Applications` so the login item resolves reliably.

## Experiment tracking

The trackio command above installs trackio's own official agent skill (logging, retrieval, storage schema, alerts) globally — loaded on demand, so it stays out of context until experiment tracking comes up. It also adds a `/logbook` command (`--no-command` skips it). For a per-project copy instead — travels with the repo, lands under `.agents/skills/trackio/` — rerun without `--global`. The kit deliberately does not duplicate upstream docs; the workflow rules that matter are already contract text (`AGENTS.md` §2 progress lines, §1.8 `experiments.jsonl`, dependency approval).

## Evolving the template

Change `AGENTS.md` here via issue → branch → PR like any research change. Line 3 of `AGENTS.md` carries the contract version (`Contract vX.Y (date)`); bump minor for template changes and major for breaking ones, and note breaking changes in the PR description. Consumers copy at bootstrap time — the version marker is how they spot a stale copy.
