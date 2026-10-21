# Monitoring jobs

Two layers, deliberately small and removable:

1. **`hpc watch`** polls the local ledger and LSF, writes events, and optionally
   sends macOS notifications.
2. **`hpc events`** is the agent-facing feed. The agent reads unread events and
   pulls logs or proposes the next action.

No job-side wrapper is required for the MVP. LSF supplies terminal states; the
watcher adds the event history, stall detection, and a place for the agent to
look without guessing.

## Start

```sh
hpc login                     # watcher cannot prompt for the DTU password

# foreground (keep the terminal open):
hpc watch --notify

# or background without tmux:
nohup hpc watch --notify >> .git/hpc/watch.log 2>&1 &
echo $! > .git/hpc/watch.pid

hpc events --unread           # agent or human reads what happened
```

`hpc watch` runs in the foreground at a 60 s interval. Use `--once` for a cron
job or a manual check. Stop a foreground watcher with Ctrl-C, or a background
one with `kill "$(cat .git/hpc/watch.pid)"`. If `tmux` is installed,
`tmux new -d -s hpc-watch 'hpc watch --notify'` also works.

Useful variants:

```sh
hpc watch --once --stall-minutes 45
hpc events --unread --json
hpc events --all             # history, does not change the unread offset
hpc events --peek            # show unread without marking them read
```

## What it watches

- Jobs in `.git/hpc/jobs.jsonl` for the current repo.
- `bjobs -w -a` statuses, including array element ids (`123[1]`).
- The newest `logs/<job_id>*` mtime for RUN jobs, used for stall detection.

Events are appended to `.git/hpc/events.jsonl`; watcher state is in
`.git/hpc/watch-state.json`. Both stay inside `.git/` and are never committed.

Event kinds: `state`, `completed`, `failed`, `stalled`, `resumed`, `unknown`,
`monitor_error`, `monitor_recovered`.

## Agent loop

At the start of a session and before deciding a job is still healthy:

```sh
hpc events --unread
```

For a `failed` or `stalled` event, inspect the log and run directory:

```sh
hpc logs <id> --index <n>    # arrays
hpc pull <id>                 # metrics/logs, excludes code/
```

The watcher never resubmits, kills, or merges. Those remain explicit decisions.

## Limits

- It only knows jobs submitted by `hpc` **in this repo**; other projects have
  their own ledgers.
- If SSH auth expires, the watcher records one `monitor_error` and then stays
  quiet until auth returns, when it records `monitor_recovered`. It cannot
  prompt for the DTU password in the background.
- Stall detection uses log mtime. Buffered output can look like a stall; raise
  `--stall-minutes` or set it to `0`.
- LSF may purge finished jobs from `bjobs -a`; run the watcher while jobs are
  pending/running, or rely on the ledger state already recorded.
- macOS notifications are best-effort; stdout in the tmux session is the
  durable log.

## Removal path

The feature touches no submission code. To scrap it, remove the `watch` and
`events` subparsers plus their helpers/tests and this reference, then delete
`.git/hpc/events.jsonl`, `.git/hpc/events.offset`, and
`.git/hpc/watch-state.json`.
