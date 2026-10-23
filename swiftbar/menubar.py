"""SwiftBar renderer for DTU LSF jobs.

Stdlib only and Python 3.9 compatible. `hpc status --json` is the only data
source; this module adds caching, idle/dormant polling, and menu formatting.
"""
from __future__ import annotations

import configparser
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_DIR = Path(__file__).resolve().parent.parent
HPC = REPO_DIR / "bin" / "hpc"
ACTION = REPO_DIR / "swiftbar" / "hpc-action.sh"

RUNNING = {"RUN", "SSUSP", "USUSP"}
PENDING = {"PEND", "PSUSP"}
FAILED = {"EXIT", "KILL", "TERM", "ZOMBI"}
TERMINAL = {"DONE"} | FAILED
ACTIVE = RUNNING | PENDING

SETTINGS = {
    "active_seconds": "30",
    "idle_seconds": "300",
    "dormant_minutes": "30",
    "pending_alert_minutes": "30",
    "failure_minutes": "60",
    "cache_hours": "24",
    "max_cached_jobs": "20",
    "max_menu_jobs": "8",
}


def state_dir() -> Path:
    return Path(os.environ.get(
        "HPC_STATE_DIR", str(Path.home() / ".local" / "state" / "dtu-hpc")
    )).expanduser()


def state_path() -> Path:
    return state_dir() / "menubar.json"


def wake_path() -> Path:
    return state_dir() / "menubar.wake"


def config_path() -> Path:
    return Path(os.environ.get(
        "HPC_MENUBAR_CONFIG", str(Path.home() / ".config" / "dtu-hpc" / "menubar.ini")
    )).expanduser()


def load_settings() -> Dict[str, int]:
    values = {key: int(value) for key, value in SETTINGS.items()}
    path = config_path()
    if not path.exists():
        write_default_config(path)
    parser = configparser.ConfigParser()
    try:
        parser.read(path)
    except (OSError, configparser.Error):
        return values
    if parser.has_section("menubar"):
        for key in values:
            raw = parser.get("menubar", key, fallback=None)
            if raw is None:
                continue
            try:
                values[key] = int(raw)
            except ValueError:
                pass
    return values


def write_default_config(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return
        body = ["[menubar]"] + [f"{key} = {value}" for key, value in SETTINGS.items()]
        path.write_text("\n".join(body) + "\n")
    except OSError:
        pass


def configured_host() -> str:
    parser = configparser.ConfigParser()
    try:
        parser.read(Path.home() / ".config" / "dtu-hpc" / "config.ini")
        return parser.get("hpc", "host", fallback="dtu")
    except (OSError, configparser.Error):
        return "dtu"


def empty_state() -> Dict[str, Any]:
    return {
        "jobs": {},
        "last_poll_at": None,
        "last_nonempty_at": None,
        "dormant": False,
        "last_error": None,
        "host": configured_host(),
        "generated_at": None,
    }


def load_state() -> Dict[str, Any]:
    state = empty_state()
    try:
        data = json.loads(state_path().read_text())
    except (OSError, ValueError):
        return state
    if not isinstance(data, dict):
        return state
    jobs = data.get("jobs")
    if isinstance(jobs, dict):
        state["jobs"] = jobs
    for key in ("last_poll_at", "last_nonempty_at", "dormant", "last_error",
                "host", "generated_at"):
        if key in data:
            state[key] = data[key]
    return state


def save_state(state: Dict[str, Any]) -> None:
    path = state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".tmp")
        temp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        os.replace(temp, path)
    except OSError:
        pass


def has_active(state: Dict[str, Any]) -> bool:
    return any(job.get("stat") in ACTIVE for job in state.get("jobs", {}).values())


def should_poll(state: Dict[str, Any], settings: Dict[str, int], now: float) -> bool:
    if wake_path().exists():
        try:
            wake_path().unlink()
        except OSError:
            pass
        return True
    if state.get("dormant"):
        return False
    interval = settings["active_seconds"] if has_active(state) else settings["idle_seconds"]
    if state.get("last_error"):
        interval = settings["idle_seconds"]
    last = state.get("last_poll_at") or 0
    return now - last >= max(5, interval - 1)


def run_status() -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    try:
        result = subprocess.run(
            [sys.executable, str(HPC), "status", "--json"],
            capture_output=True, text=True, timeout=25,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, {"kind": "offline", "message": str(exc)}
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        message = (result.stderr or result.stdout).strip()
        return None, {"kind": "cli", "message": message[:300] or "no output"}
    if not payload.get("ok"):
        return None, {
            "kind": payload.get("error") or "error",
            "message": payload.get("message") or "",
            "host": payload.get("host"),
        }
    return payload, None


def prune(jobs: Dict[str, Dict[str, Any]], settings: Dict[str, int],
          now: float) -> None:
    cutoff = now - max(1, settings["cache_hours"]) * 3600
    for key, job in list(jobs.items()):
        finished = job.get("finished_at")
        if finished is not None and finished < cutoff:
            jobs.pop(key, None)
    finished = [
        (key, job) for key, job in jobs.items()
        if job.get("finished_at") is not None
    ]
    finished.sort(key=lambda item: item[1].get("finished_at") or 0, reverse=True)
    for key, _job in finished[max(1, settings["max_cached_jobs"]):]:
        jobs.pop(key, None)


def merge_poll(state: Dict[str, Any], payload: Dict[str, Any],
               settings: Dict[str, int], now: float) -> None:
    jobs = state.setdefault("jobs", {})
    seen = set()
    for record in payload.get("records", []):
        key = str(record.get("key") or record.get("job_id") or "").strip()
        if not key:
            continue
        seen.add(key)
        previous = jobs.get(key, {})
        entry = dict(record)
        entry["last_seen"] = now
        if entry.get("stat") in TERMINAL:
            entry["finished_at"] = previous.get("finished_at") or now
        else:
            entry["finished_at"] = None
        jobs[key] = entry
    for key, entry in jobs.items():
        if key in seen:
            continue
        if entry.get("finished_at") is None:
            entry["stat"] = "GONE"
            entry["finished_at"] = now
    prune(jobs, settings, now)
    active = has_active(state)
    if active or state.get("last_nonempty_at") is None:
        state["last_nonempty_at"] = now
    dormant_at = state.get("last_nonempty_at") or now
    state["dormant"] = (not active and
                        now - dormant_at >= max(1, settings["dormant_minutes"]) * 60)
    state["last_poll_at"] = now
    state["last_error"] = None
    state["host"] = payload.get("host") or state.get("host") or configured_host()
    state["generated_at"] = payload.get("generated_at")


def record_error(state: Dict[str, Any], error: Dict[str, Any], now: float) -> None:
    state["last_error"] = {
        "kind": error.get("kind") or "error",
        "message": error.get("message") or "",
        "at": now,
    }
    state["last_poll_at"] = now
    if not has_active(state):
        state["dormant"] = True


def human_duration(seconds: Optional[float]) -> str:
    try:
        total = int(seconds or 0)
    except (TypeError, ValueError):
        return "?"
    if total < 0:
        return "?"
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d{hours}h"
    if hours:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes}m"


def parse_lsf_time(value: object) -> Optional[float]:
    text = str(value or "").strip()
    for fmt in ("%b %d %H:%M:%S %Y", "%a %b %d %H:%M:%S %Y"):
        try:
            return datetime.strptime(text, fmt).timestamp()
        except ValueError:
            continue
    return None


def clean(text: object, limit: int = 40) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).replace("|", "/").strip()
    if not value:
        return "-"
    if value.startswith("-"):
        value = "\u00b7" + value[1:]
    if len(value) > limit:
        value = value[: max(1, limit - 1)] + "\u2026"
    return value


def duration_for(job: Dict[str, Any], now: float) -> str:
    if job.get("stat") in PENDING:
        submitted = parse_lsf_time(job.get("submit_time"))
        return human_duration(now - submitted) if submitted else "?"
    return human_duration(job.get("elapsed_seconds"))


def job_color(job: Dict[str, Any], stale: bool) -> str:
    if stale:
        return "gray"
    stat = job.get("stat")
    if stat in FAILED:
        return "red"
    if stat in PENDING:
        return "orange"
    if stat == "GONE":
        return "gray"
    if stat in RUNNING:
        return "green"
    return "gray"


def recent_failures(state: Dict[str, Any], settings: Dict[str, int],
                    now: float) -> List[Dict[str, Any]]:
    window = max(0, settings["failure_minutes"]) * 60
    found = []
    for job in state.get("jobs", {}).values():
        finished = job.get("finished_at")
        if job.get("stat") in FAILED and finished is not None and now - finished <= window:
            found.append(job)
    return found


def long_pending(state: Dict[str, Any], settings: Dict[str, int],
                 now: float) -> bool:
    threshold = max(1, settings["pending_alert_minutes"]) * 60
    for job in state.get("jobs", {}).values():
        if job.get("stat") not in PENDING:
            continue
        submitted = parse_lsf_time(job.get("submit_time"))
        if submitted is not None and now - submitted >= threshold:
            return True
    return False


def title_line(state: Dict[str, Any], settings: Dict[str, int], now: float) -> str:
    jobs = list(state.get("jobs", {}).values())
    running = sum(1 for job in jobs if job.get("stat") in RUNNING)
    pending = sum(1 for job in jobs if job.get("stat") in PENDING)
    failures = recent_failures(state, settings, now)
    error = state.get("last_error")
    if error:
        kind = error.get("kind")
        if running or pending:
            label = f"HPC {running}R {pending}P ?"
        else:
            label = "HPC login" if kind == "auth" else "HPC offline"
        color = "orange" if kind == "auth" else "red"
        return f"{label} | sfimage=cpu color={color}"
    if running or pending:
        label = f"HPC {running}R {pending}P"
        color = "orange" if long_pending(state, settings, now) else "green"
        if failures:
            label += " !"
            color = "red"
        return f"{label} | sfimage=cpu color={color}"
    if failures:
        return "HPC ! | sfimage=cpu color=red"
    return "HPC idle | sfimage=cpu color=gray"


def action(name: str, *params: str, terminal: bool = False,
           refresh: bool = False) -> str:
    parts = [f"bash={ACTION}", f"param1={name}"]
    for index, value in enumerate(params, start=2):
        parts.append(f"param{index}={value}")
    if terminal:
        parts.append("terminal=true")
    if refresh:
        parts.append("refresh=true")
    return " ".join(parts)


def job_line(job: Dict[str, Any], now: float, stale: bool) -> str:
    key = clean(job.get("key") or job.get("job_id"), 18)
    name = clean(job.get("name"), 22)
    queue = clean(job.get("queue"), 10)
    stat = job.get("stat") or "?"
    duration = duration_for(job, now)
    if stat in RUNNING and stat == "RUN":
        label = f"{key}  {name}  {queue}  {duration}"
    else:
        label = f"{key}  {name}  {queue}  {stat}  {duration}"
    return f"{label} | color={job_color(job, stale)}"


def job_submenu(job: Dict[str, Any], host: str) -> List[str]:
    key = clean(job.get("key") or job.get("job_id"), 24)
    return [
        f"--Details | {action('status', key, terminal=True)}",
        f"--Open logs | {action('logs', key, host, terminal=True)}",
        f"--Copy job id | {action('copy', key)}",
    ]


def error_lines(error: Dict[str, Any], host: str) -> List[str]:
    kind = error.get("kind")
    message = clean(error.get("message"), 80)
    if kind == "auth":
        return [
            "SSH session expired | color=orange",
            f"Login | {action('login', host, terminal=True, refresh=True)}",
        ]
    if kind == "offline":
        return ["HPC unreachable | color=red", f"{message} | color=gray size=10"]
    if kind == "timeout":
        return ["HPC did not answer | color=red"]
    return [f"HPC error: {message} | color=red size=10"]


def render(state: Dict[str, Any], settings: Dict[str, int], now: float) -> str:
    host = state.get("host") or configured_host()
    jobs = list(state.get("jobs", {}).values())
    error = state.get("last_error")
    stale = bool(error)
    running = [job for job in jobs if job.get("stat") in RUNNING]
    pending = [job for job in jobs if job.get("stat") in PENDING]
    other = [job for job in jobs
             if job.get("stat") not in ACTIVE and job.get("stat") not in TERMINAL]
    finished = [job for job in jobs if job.get("stat") in TERMINAL]
    finished.sort(key=lambda job: job.get("finished_at") or 0, reverse=True)

    lines = [title_line(state, settings, now), "---"]
    if error:
        lines.extend(error_lines(error, host))
        if state.get("dormant"):
            lines.append("Polling paused until login or refresh | color=gray")
    elif state.get("dormant"):
        lines.append("No jobs; polling paused | color=gray")
    elif not jobs:
        lines.append("No jobs in the last 24h | color=gray")

    limit = max(1, settings["max_menu_jobs"])
    if running:
        lines.append(f"Running ({len(running)}) | color=green size=11")
        for job in running[:limit]:
            lines.append(job_line(job, now, stale))
            lines.extend(job_submenu(job, host))
        if len(running) > limit:
            lines.append(f"{len(running) - limit} more running | color=gray")
    if pending:
        lines.append(f"Pending ({len(pending)}) | color=orange size=11")
        for job in pending[:limit]:
            lines.append(job_line(job, now, stale))
            lines.extend(job_submenu(job, host))
        if len(pending) > limit:
            lines.append(f"{len(pending) - limit} more pending | color=gray")
    if other:
        lines.append(f"Other ({len(other)}) | color=gray size=11")
        for job in other[:limit]:
            lines.append(job_line(job, now, stale))
            lines.extend(job_submenu(job, host))
    if finished:
        lines.append(f"Recently finished ({len(finished)}) | color=gray size=11")
        for job in finished[:limit]:
            lines.append(job_line(job, now, stale))
            lines.extend(job_submenu(job, host))
        if len(finished) > limit:
            lines.append(f"{len(finished) - limit} older | color=gray")

    lines.append("---")
    stamp = "never"
    if state.get("last_poll_at"):
        stamp = datetime.fromtimestamp(state["last_poll_at"]).strftime("%H:%M:%S")
    suffix = " (stale)" if stale else ""
    lines.append(f"Updated {stamp}{suffix} | color=gray size=10")
    lines.append(f"Refresh now | {action('refresh', refresh=True)}")
    lines.append(f"Open status in Terminal | {action('status', terminal=True)}")
    return "\n".join(lines)


def main() -> int:
    settings = load_settings()
    state = load_state()
    now = time.time()
    if should_poll(state, settings, now):
        payload, error = run_status()
        if error is not None:
            record_error(state, error, now)
        elif payload is not None:
            merge_poll(state, payload, settings, now)
        save_state(state)
    print(render(state, settings, now))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
