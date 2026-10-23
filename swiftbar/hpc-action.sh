#!/bin/sh
set -u

repo=$(cd -P "$(dirname "$0")/.." && pwd)
hpc="$repo/bin/hpc"
state="${HPC_STATE_DIR:-$HOME/.local/state/dtu-hpc}"
host=${2:-dtu}

case "${1:-}" in
  refresh)
    mkdir -p "$state" && touch "$state/menubar.wake"
    ;;
  login)
    ssh -O exit "$host" >/dev/null 2>&1 || true
    ssh -M -N -f "$host" || exit 1
    mkdir -p "$state" && touch "$state/menubar.wake"
    ;;
  status)
    if [ -n "${2:-}" ]; then
      exec "$hpc" status "$2" --detail
    fi
    exec "$hpc" status
    ;;
  logs)
    id=${2:-}
    case "$id" in
      ''|*[!0-9\[\]]*)
        echo "bad job id: $id" >&2
        exit 2
        ;;
    esac
    exec ssh -t "$host" "bash -lc \"exec bpeek -f '$id'\""
    ;;
  copy)
    printf '%s' "${2:-}" | pbcopy
    ;;
  *)
    echo "usage: $0 refresh|login <host>|status [job]|logs <job> <host>|copy <job>" >&2
    exit 2
    ;;
esac
