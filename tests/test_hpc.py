"""Stubbed tests for bin/hpc — no network, no real SSH, no HPC."""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HPC = REPO / "bin" / "hpc"


class HpcCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.repo = base / "proj"
        self.repo.mkdir()
        self.stub_bin = base / "bin"
        self.stub_bin.mkdir()
        self.home = base / "home"
        self.home.mkdir()
        self.log = base / "ssh.log"
        self.stdin_log = base / "stdin.log"
        (self.stub_bin / "ssh").write_text(textwrap.dedent("""\
            #!/bin/sh
            printf '%s\\n' "$*" >> "$HPC_TEST_LOG"
            if [ -n "${HPC_TEST_STDIN:-}" ]; then
              cat >> "$HPC_TEST_STDIN"
            else
              cat >/dev/null 2>&1 || true
            fi
            case "$*" in
              *"-O check"*)
                [ "${HPC_TEST_DEAD:-0}" = 1 ] && exit 1
                exit 0 ;;
              *"bsub"*) printf 'Job <123> is submitted to queue <gpua100>.\\n' ;;
              *"-json"*) [ -n "${HPC_TEST_BJOBS:-}" ] && cat "$HPC_TEST_BJOBS" ;;
              *"hpc-env.json"*) [ -n "${HPC_TEST_ENV_MANIFEST:-}" ] && cat "$HPC_TEST_ENV_MANIFEST" ;;
              *"uv --version"*) printf 'uv 0.8.0\\nPython 3.12.0\\n' ;;
              *"cat --"*"/projects/"*) [ -n "${HPC_TEST_PROJECT_SECRETS:-}" ] && cat "$HPC_TEST_PROJECT_SECRETS" ;;
              *"cat --"*) [ -n "${HPC_TEST_SECRETS:-}" ] && cat "$HPC_TEST_SECRETS" ;;
              *"bstat"*) printf 'JOBID USER QUEUE JOB_NAME NALLOC STAT\\n' ;;
              *"bjobs"*) [ -n "${HPC_TEST_BJOBS:-}" ] && cat "$HPC_TEST_BJOBS" ;;
              *"%T@"*) [ -n "${HPC_TEST_LOG_STATS:-}" ] && cat "$HPC_TEST_LOG_STATS" ;;
              *"-printf"*) [ -n "${HPC_TEST_LOG_NAMES:-}" ] && cat "$HPC_TEST_LOG_NAMES" ;;
              *"tail -F"*|*"tail -n"*) printf 'STUB-TAIL-OUTPUT\\n' ;;
              *"tmux"*) printf 'STUB-INTERACTIVE-OUTPUT\\n' ;;
              *"bpeek"*) printf 'STUB-BPEEK-OUTPUT\\n' ;;
              *"printf"*) printf 'tester\\n/home/tester\\n' ;;
            esac
            [ "${HPC_TEST_STALE:-0}" = 1 ] && exit 255
            exit 0
            """))
        (self.stub_bin / "ssh").chmod(0o755)
        (self.stub_bin / "rsync").write_text(
            '#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$HPC_TEST_LOG"\n')
        (self.stub_bin / "rsync").chmod(0o755)
        self.config = base / "config.ini"
        self.config.write_text("[hpc]\nhost = test\nremote_root = /work3/{user}/hpc/{repo}\n")
        self.env_manifest = base / "env-manifest.json"
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "test")
        (self.repo / "job.lsf").write_text(textwrap.dedent("""\
            #BSUB -q gpua100
            #BSUB -J {{JOB_NAME}}
            cd "{{CODE_DIR}}"
            echo "sha={{SHA}} run={{RUN_DIR}}"
            """))
        (self.repo / "train.py").write_text("print('hi')\n")
        (self.repo / "uv.lock").write_text("version = 1\n")
        self.git("add", ".")
        self.git("commit", "-qm", "initial")
        self.write_env_manifest()

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.repo, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def env_input_sha(self) -> str:
        material = ""
        for name in ("pyproject.toml", "uv.lock", ".python-version", "uv.toml"):
            path = self.repo / name
            if path.is_file():
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                material += f"{name}\0{digest}\n"
        return hashlib.sha256(material.encode()).hexdigest()

    def write_env_manifest(self, lock_sha: str | None = None,
                           venv: str = "/work3/tester/hpc/venvs/proj") -> None:
        lock_sha = lock_sha or hashlib.sha256(
            (self.repo / "uv.lock").read_bytes()).hexdigest()
        self.env_manifest.write_text(json.dumps({
            "input_sha256": self.env_input_sha(),
            "lock_sha256": lock_sha,
            "sha": "deadbeef",
            "venv": venv,
            "synced_at": "2026-10-22T00:00:00+00:00",
            "uv_version": "uv 0.8.0",
            "python_version": "Python 3.12.0",
        }))

    def write_job(self, content: str) -> None:
        (self.repo / "job.lsf").write_text(textwrap.dedent(content))
        self.git("add", "job.lsf")
        self.git("commit", "-qm", "job")

    def add_ledger(self, job_id: int = 123, submitted_at: str | None = None,
                   run_dir: str | None = None) -> None:
        path = self.repo / ".git" / "hpc" / "jobs.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "job_id": job_id,
            "run_id": f"20260101T000000Z-{job_id}",
            "run_dir": run_dir or f"/work3/tester/hpc/proj/jobs/20260101T000000Z-{job_id}",
        }
        if submitted_at:
            entry["submitted_at"] = submitted_at
        path.write_text(json.dumps(entry) + "\n")

    def hpc(self, *args: str, extra_env: dict[str, str] | None = None,
            cwd: Path | None = None) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env.update({
            "HPC_CONFIG": str(self.config),
            "HPC_NO_OPEN": "1",
            "HPC_TEST_LOG": str(self.log),
            "HPC_TEST_STDIN": str(self.stdin_log),
            "HPC_TEST_ENV_MANIFEST": str(self.env_manifest),
            "HOME": str(self.home),
            "PATH": f"{self.stub_bin}{os.pathsep}{env['PATH']}",
        })
        env.update(extra_env or {})
        return subprocess.run([sys.executable, str(HPC), *args], cwd=cwd or self.repo,
                              env=env, text=True, capture_output=True)

    def test_dirty_tree_is_refused(self) -> None:
        (self.repo / "train.py").write_text("print('changed')\n")
        result = self.hpc("submit", "job.lsf")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dirty", result.stderr)

    def test_submit_ships_snapshot_and_records_job(self) -> None:
        result = self.hpc("submit", "job.lsf")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("submitted job 123", result.stdout)
        ledger = self.repo / ".git" / "hpc" / "jobs.jsonl"
        entry = json.loads(ledger.read_text().strip())
        self.assertEqual(entry["job_id"], 123)
        self.assertEqual(entry["queue"], "gpua100")
        self.assertIn(entry["branch"], {"main", "master"})
        self.assertIn("/work3/tester/hpc/proj/jobs/", entry["run_dir"])
        self.assertEqual(entry["venv"], "/work3/tester/hpc/venvs/proj")
        self.assertEqual(entry["lock_sha256"],
                         hashlib.sha256((self.repo / "uv.lock").read_bytes()).hexdigest())
        self.assertEqual(entry["env_input_sha256"], self.env_input_sha())
        self.assertEqual(entry["env_synced_at"], "2026-10-22T00:00:00+00:00")
        self.assertEqual(entry["uv_version"], "uv 0.8.0")
        self.assertEqual(entry["python_version"], "Python 3.12.0")
        log = self.log.read_text()
        self.assertIn("tar -xzf", log)
        self.assertIn("bsub", log)

    def test_dry_run_needs_no_ssh_and_renders_placeholders(self) -> None:
        result = self.hpc("submit", "job.lsf", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("{{CODE_DIR}}", result.stdout)
        self.assertIn("/work3/<user>/hpc/proj/jobs/", result.stdout)
        self.assertIn("sha=", result.stdout)
        self.assertFalse((self.repo / ".git" / "hpc" / "jobs.jsonl").exists())
        self.assertFalse(self.log.exists())

    def test_stage_ships_head_and_points_current(self) -> None:
        result = self.hpc("stage")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("/work3/tester/hpc/proj/interactive/", result.stdout)
        log = self.log.read_text()
        self.assertIn("tar -xzf", log)
        self.assertIn("ln -sfn", log)

    def test_stage_refuses_dirty_tree(self) -> None:
        (self.repo / "train.py").write_text("print('changed')\n")
        result = self.hpc("stage")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dirty", result.stderr)

    def test_queue_override(self) -> None:
        result = self.hpc("submit", "job.lsf", "--queue", "p1", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("#BSUB -q p1", result.stdout)
        self.assertIn("overrides script queue gpua100", result.stderr)

    def test_queue_newline_injection_is_refused(self) -> None:
        result = self.hpc("submit", "job.lsf", "--queue", "p1\n#BSUB -q evil")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid queue", result.stderr)
        self.assertNotIn("#BSUB -q evil", result.stdout)
        self.assertFalse(self.log.exists())

    def test_invalid_job_names_are_refused(self) -> None:
        for name in ("bad name", "bad\nname", "bad;name", "bad$(id)"):
            with self.subTest(name=name):
                result = self.hpc("submit", "job.lsf", "--name", name)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("invalid job name", result.stderr)
                self.assertFalse(self.log.exists())

    def test_array_job_name_is_accepted(self) -> None:
        result = self.hpc("submit", "job.lsf", "--name", "sweep[1-3]%2",
                          "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("#BSUB -J sweep[1-3]%2", result.stdout)

    def test_uncapped_array_is_refused(self) -> None:
        self.write_job("""\
            #BSUB -q gpua100
            #BSUB -J "sweep[1-3]"
            echo "sha={{SHA}}"
            """)
        result = self.hpc("submit", "job.lsf")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("uncapped array", result.stderr)
        self.assertIn("--allow-uncapped", result.stderr)
        self.assertFalse(self.log.exists())

    def test_uncapped_array_dry_run_warns(self) -> None:
        self.write_job("""\
            #BSUB -q gpua100
            #BSUB -J "sweep[1-3]"
            echo "sha={{SHA}}"
            """)
        result = self.hpc("submit", "job.lsf", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("uncapped array", result.stderr)

    def test_capped_array_is_accepted(self) -> None:
        self.write_job("""\
            #BSUB -q gpua100
            #BSUB -J "sweep[1-3]%2"
            echo "sha={{SHA}}"
            """)
        result = self.hpc("submit", "job.lsf", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("uncapped array", result.stderr)

    def status_jobs(self, include_hosts: bool = False) -> Path:
        records = [
            {
                "JOBID": "123",
                "JOBINDEX": "4",
                "STAT": "RUN",
                "QUEUE": "p1",
                "JOB_NAME": "exp[4]",
                "SUBMIT_TIME": "Oct 22 09:13:41 2026",
                "START_TIME": "Oct 22 09:14:00 2026",
                "RUN_TIME": "00:10:00",
                "EXEC_HOST": "node1",
                "FROM_HOST": "login9",
            },
            {
                "JOBID": "123",
                "JOBINDEX": "5",
                "STAT": "PEND",
                "QUEUE": "p1",
                "JOB_NAME": "exp[5]",
                "SUBMIT_TIME": "Oct 22 09:13:41 2026",
                "START_TIME": "",
                "RUN_TIME": "00:00:00",
                "EXEC_HOST": "",
                "FROM_HOST": "login9",
            },
        ]
        if not include_hosts:
            for record in records:
                record.pop("EXEC_HOST", None)
                record.pop("FROM_HOST", None)
        path = Path(self.tmp.name) / "bjobs.json"
        path.write_text(json.dumps({"COMMAND": "bjobs", "JOBS": 2, "RECORDS": records}))
        return path

    def test_status_no_id_lists_all_jobs(self) -> None:
        bjobs = self.status_jobs()
        result = self.hpc("status", extra_env={"HPC_TEST_BJOBS": str(bjobs)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("bjobs", self.log.read_text())
        self.assertIn("-json", self.log.read_text())
        self.assertIn("JOBID", result.stdout)
        self.assertIn("START_TIME", result.stdout)
        self.assertIn("ELAPSED", result.stdout)
        self.assertIn("123[4]", result.stdout)
        self.assertIn("Oct 22 09:14:00 2026", result.stdout)
        self.assertIn("00:10:00", result.stdout)
        self.assertIn("123[5]", result.stdout)
        self.assertNotIn("USER", result.stdout)
        self.assertNotIn("FROM_HOST", result.stdout)
        self.assertNotIn("EXEC_HOST", result.stdout)

    def test_status_hosts_adds_debug_columns(self) -> None:
        bjobs = self.status_jobs(include_hosts=True)
        result = self.hpc("status", "--hosts", extra_env={"HPC_TEST_BJOBS": str(bjobs)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("EXEC_HOST", result.stdout)
        self.assertIn("FROM_HOST", result.stdout)
        self.assertIn("node1", result.stdout)
        self.assertIn("login9", result.stdout)

    def test_status_id_formats_job(self) -> None:
        bjobs = self.status_jobs()
        result = self.hpc("status", "123", extra_env={"HPC_TEST_BJOBS": str(bjobs)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('bjobs -o', self.log.read_text())
        self.assertIn("hpc 123", self.log.read_text())
        self.assertIn("123[4]", result.stdout)
        self.assertIn("ELAPSED", result.stdout)

    def test_status_detail_uses_bstat(self) -> None:
        result = self.hpc("status", "123", "--detail")
        self.assertEqual(result.returncode, 0, result.stderr)
        log = self.log.read_text()
        self.assertIn('bstat "$1"', log)
        self.assertIn("123", log)

    def test_status_json_error_record_fails(self) -> None:
        bjobs = Path(self.tmp.name) / "bjobs-error.json"
        bjobs.write_text(json.dumps({"RECORDS": [
            {"JOBID": "999", "ERROR": "Job <999> is not found"}]}))
        result = self.hpc("status", "999", extra_env={"HPC_TEST_BJOBS": str(bjobs)})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Job <999> is not found", result.stderr)
        self.assertNotIn("JOBID", result.stdout)

    def test_status_json_emits_machine_readable_records(self) -> None:
        bjobs = self.status_jobs()
        result = self.hpc("status", "--json",
                          extra_env={"HPC_TEST_BJOBS": str(bjobs)})
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["host"], "test")
        self.assertIn("generated_at", payload)
        self.assertEqual(payload["records"][0]["key"], "123[4]")
        self.assertEqual(payload["records"][0]["elapsed_seconds"], 600)
        self.assertEqual(payload["records"][1]["stat"], "PEND")

    def test_status_json_never_prompts_without_master(self) -> None:
        result = self.hpc("status", "--json", extra_env={"HPC_TEST_DEAD": "1"})
        self.assertEqual(result.returncode, 2, result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "auth")
        self.assertNotIn("bjobs", self.log.read_text())
        self.assertNotIn("Terminal", result.stderr)

    def test_status_json_rejects_detail(self) -> None:
        result = self.hpc("status", "123", "--json", "--detail")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--json cannot be combined with --detail", result.stderr)

    def test_submit_wakes_menubar(self) -> None:
        result = self.hpc("submit", "job.lsf")
        self.assertEqual(result.returncode, 0, result.stderr)
        wake = self.home / ".local" / "state" / "dtu-hpc" / "menubar.wake"
        self.assertTrue(wake.exists())

    def test_pull_skips_code_by_default(self) -> None:
        self.add_ledger()
        result = self.hpc("pull", "123")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--exclude=/code/", self.log.read_text())
        self.assertIn("excluded code/", result.stderr)

    def test_pull_include_code_keeps_snapshot(self) -> None:
        self.add_ledger()
        result = self.hpc("pull", "123", "--include-code")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("--exclude=/code/", self.log.read_text())
        self.assertNotIn("excluded code/", result.stderr)

    def test_pull_rejects_whitespace_in_run_dir(self) -> None:
        self.add_ledger(run_dir="/work3/tester/hpc/proj/jobs/bad dir")
        result = self.hpc("pull", "123")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("contains whitespace", result.stderr)
        self.assertFalse(self.log.exists())

    def test_logs_array_index_selects_one_element(self) -> None:
        self.add_ledger()
        names = Path(self.tmp.name) / "log-names"
        names.write_text(
            "123-load-1.out\n"
            "123-load-1.err\n"
            "123-load-2.out\n"
            "124-load-1.out\n")
        result = self.hpc("logs", "123", "--index", "1",
                          extra_env={"HPC_TEST_LOG_NAMES": str(names)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("123-load-1.out", result.stderr)
        self.assertIn("123-load-1.err", result.stderr)
        self.assertNotIn("123-load-2.out", result.stderr)

    def test_logs_prints_tail_output(self) -> None:
        self.add_ledger()
        names = Path(self.tmp.name) / "log-names"
        names.write_text("123.out\n123.err\n")
        result = self.hpc("logs", "123",
                          extra_env={"HPC_TEST_LOG_NAMES": str(names)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("STUB-TAIL-OUTPUT", result.stdout)

    def test_logs_follow_streams_tail_output(self) -> None:
        self.add_ledger()
        names = Path(self.tmp.name) / "log-names"
        names.write_text("123.out\n")
        result = self.hpc("logs", "123", "-f",
                          extra_env={"HPC_TEST_LOG_NAMES": str(names)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("STUB-TAIL-OUTPUT", result.stdout)

    def test_logs_without_ledger_uses_visible_bpeek(self) -> None:
        result = self.hpc("logs", "123")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("STUB-BPEEK-OUTPUT", result.stdout)

    def test_logs_outside_repo_uses_visible_bpeek(self) -> None:
        result = self.hpc("logs", "123", cwd=Path(self.tmp.name))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("STUB-BPEEK-OUTPUT", result.stdout)

    def test_logs_missing_is_actionable(self) -> None:
        self.add_ledger()
        result = self.hpc("logs", "123")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("may still be starting", result.stderr)
        self.assertIn("hpc status 123", result.stderr)

    def test_shell_attaches_terminal(self) -> None:
        result = self.hpc("shell")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("STUB-INTERACTIVE-OUTPUT", result.stdout)
        self.assertIn("-t test", self.log.read_text())

    def test_gpu_attaches_terminal(self) -> None:
        result = self.hpc("gpu", "a100")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("STUB-INTERACTIVE-OUTPUT", result.stdout)

    def test_watch_emits_terminal_failure_once(self) -> None:
        self.add_ledger()
        bjobs = Path(self.tmp.name) / "bjobs.txt"
        header = "JOBID USER STAT QUEUE FROM_HOST EXEC_HOST JOB_NAME SUBMIT_TIME\n"
        bjobs.write_text(header + "123 tester RUN p1 host exec job now\n")
        env = {"HPC_TEST_BJOBS": str(bjobs)}
        result = self.hpc("watch", "--once", extra_env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        events = self.repo / ".git" / "hpc" / "events.jsonl"
        self.assertFalse(events.exists())

        bjobs.write_text(header + "123 tester EXIT p1 host exec job now\n")
        result = self.hpc("watch", "--once", extra_env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = events.read_text().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["event"], "failed")

        result = self.hpc("watch", "--once", extra_env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(events.read_text().splitlines()), 1)

    def test_watch_emits_kill_failure_once(self) -> None:
        self.add_ledger()
        bjobs = Path(self.tmp.name) / "bjobs.txt"
        bjobs.write_text(
            "JOBID USER STAT QUEUE FROM_HOST EXEC_HOST JOB_NAME SUBMIT_TIME\n"
            "123 tester KILL p1 host exec job now\n")
        env = {"HPC_TEST_BJOBS": str(bjobs)}
        result = self.hpc("watch", "--once", extra_env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        events = self.repo / ".git" / "hpc" / "events.jsonl"
        event = json.loads(events.read_text().splitlines()[0])
        self.assertEqual(event["event"], "failed")
        self.assertEqual(event["status"], "KILL")
        result = self.hpc("watch", "--once", extra_env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(events.read_text().splitlines()), 1)

    def test_watch_mixed_array_failure_detail(self) -> None:
        self.add_ledger()
        bjobs = Path(self.tmp.name) / "bjobs.txt"
        bjobs.write_text(
            "JOBID USER STAT QUEUE FROM_HOST EXEC_HOST JOB_NAME SUBMIT_TIME\n"
            "123[1] tester RUN p1 host exec job now\n"
            "123[2] tester KILL p1 host exec job now\n")
        env = {"HPC_TEST_BJOBS": str(bjobs)}
        result = self.hpc("watch", "--once", extra_env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        events = self.repo / ".git" / "hpc" / "events.jsonl"
        event = json.loads(events.read_text().splitlines()[0])
        self.assertEqual(event["event"], "failed")
        self.assertEqual(event["status"], "KILL")
        self.assertIn("1/2 array elements failed", event["detail"])
        result = self.hpc("watch", "--once", extra_env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(events.read_text().splitlines()), 1)

        bjobs.write_text(
            "JOBID USER STAT QUEUE FROM_HOST EXEC_HOST JOB_NAME SUBMIT_TIME\n"
            "123[1] tester DONE p1 host exec job now\n"
            "123[2] tester KILL p1 host exec job now\n")
        result = self.hpc("watch", "--once", extra_env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(events.read_text().splitlines()), 1)

    def test_watch_emits_unknown_once(self) -> None:
        self.add_ledger()
        bjobs = Path(self.tmp.name) / "bjobs.txt"
        bjobs.write_text(
            "JOBID USER STAT QUEUE FROM_HOST EXEC_HOST JOB_NAME SUBMIT_TIME\n"
            "123 tester UNKWN p1 host exec job now\n")
        env = {"HPC_TEST_BJOBS": str(bjobs)}
        result = self.hpc("watch", "--once", extra_env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        events = self.repo / ".git" / "hpc" / "events.jsonl"
        event = json.loads(events.read_text().splitlines()[0])
        self.assertEqual(event["event"], "unknown")
        self.assertEqual(event["status"], "UNKWN")
        result = self.hpc("watch", "--once", extra_env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(events.read_text().splitlines()), 1)

        bjobs.write_text(
            "JOBID USER STAT QUEUE FROM_HOST EXEC_HOST JOB_NAME SUBMIT_TIME\n"
            "123 tester DONE p1 host exec job now\n")
        result = self.hpc("watch", "--once", extra_env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(events.read_text().splitlines()[1])["event"],
                         "completed")

    def test_watch_stall_emits_once(self) -> None:
        self.add_ledger()
        bjobs = Path(self.tmp.name) / "bjobs.txt"
        bjobs.write_text(
            "JOBID USER STAT QUEUE FROM_HOST EXEC_HOST JOB_NAME SUBMIT_TIME\n"
            "123 tester RUN p1 host exec job now\n")
        stats = Path(self.tmp.name) / "log-stats.txt"
        stats.write_text(f"{int(time.time()) - 3600} 42\n")
        env = {"HPC_TEST_BJOBS": str(bjobs), "HPC_TEST_LOG_STATS": str(stats)}
        result = self.hpc("watch", "--once", "--stall-minutes", "30", extra_env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        events = self.repo / ".git" / "hpc" / "events.jsonl"
        lines = events.read_text().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["event"], "stalled")

        result = self.hpc("watch", "--once", "--stall-minutes", "30", extra_env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(events.read_text().splitlines()), 1)

    def test_events_unread_and_peek(self) -> None:
        events = self.repo / ".git" / "hpc" / "events.jsonl"
        events.parent.mkdir(parents=True)
        entries = [
            {"timestamp": "2026-10-21T12:00:00+00:00", "job_id": 123,
             "event": "completed", "status": "DONE", "detail": "status DONE"},
            {"timestamp": "2026-10-21T12:01:00+00:00", "job_id": 124,
             "event": "failed", "status": "EXIT", "detail": "status EXIT"},
        ]
        events.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n")

        result = self.hpc("events", "--peek")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("job 123 completed", result.stdout)
        self.assertIn("job 124 failed", result.stdout)

        result = self.hpc("events", "--unread")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("job 123 completed", result.stdout)

        result = self.hpc("events")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no events", result.stderr)

    def test_array_status_helpers(self) -> None:
        import runpy
        import types
        module = types.SimpleNamespace(**runpy.run_path(str(HPC), run_name="hpc_cli"))
        text = (
            "JOBID USER STAT QUEUE FROM_HOST EXEC_HOST JOB_NAME SUBMIT_TIME\n"
            "123[1] tester RUN p1 host exec job now\n"
            "123[2] tester EXIT p1 host exec job now\n"
        )
        states = module.parse_bjobs(text)
        self.assertEqual(states[123], ["RUN", "EXIT"])
        self.assertEqual(module.summarize_states(states[123]), "EXIT")
        self.assertFalse(module.states_are_terminal(states[123]))
        self.assertTrue(module.states_are_terminal(["DONE", "EXIT"]))
        for state in ("KILL", "TERM", "ZOMBI"):
            self.assertEqual(module.summarize_states([state]), state)
            self.assertTrue(module.states_are_terminal([state]))
        self.assertEqual(module.summarize_states(["UNKWN"]), "UNKWN")
        self.assertFalse(module.states_are_terminal(["UNKWN"]))
        self.assertEqual(module.summarize_states(["RUN", "KILL"]), "KILL")
        self.assertFalse(module.states_are_terminal(["RUN", "KILL"]))

    def test_allow_dirty_warns_but_submits_head(self) -> None:
        (self.repo / "train.py").write_text("print('changed')\n")
        result = self.hpc("submit", "job.lsf", "--allow-dirty")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("dirty", result.stderr)

    def test_init_detects_existing_dtu_alias(self) -> None:
        ssh_dir = self.home / ".ssh"
        ssh_dir.mkdir()
        (ssh_dir / "config").write_text(
            "Host dtu\n  HostName login9.hpc.dtu.dk\n  User tester\n")
        result = self.hpc("init", "--force")
        self.assertEqual(result.returncode, 0, result.stderr)
        config = self.config.read_text()
        self.assertIn("host = dtu", config)
        self.assertIn("venv = /work3/{user}/hpc/venvs/{repo}", config)
        self.assertIn(
            "project_secrets = $HOME/.config/dtu-hpc/projects/{project}.env",
            config,
        )
        self.assertIn("hpc login", result.stdout)

    def test_init_detects_alias_in_included_config(self) -> None:
        ssh_dir = self.home / ".ssh"
        config_dir = ssh_dir / "config.d"
        config_dir.mkdir(parents=True)
        (ssh_dir / "config").write_text(
            "Include config.d/*\nHost elsewhere\n  HostName example.com\n")
        (config_dir / "dtu").write_text(
            "Host dtu\n  HostName login9.hpc.dtu.dk\n  User tester\n")
        result = self.hpc("init", "--force")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("host = dtu", self.config.read_text())

    def test_init_without_alias_refuses_default(self) -> None:
        result = self.hpc("init", "--force")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no DTU SSH alias", result.stderr)
        self.assertIn("Host dtu", result.stderr)

    def test_init_accepts_explicit_ssh_host(self) -> None:
        result = self.hpc("init", "--force", "--ssh-host", "my-dtu")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("host = my-dtu", self.config.read_text())

    def test_ensure_healthy_master_probes_remote(self) -> None:
        result = self.hpc("ensure", extra_env={"HPC_NO_OPEN": "1"})
        self.assertEqual(result.returncode, 0, result.stderr)
        log = self.log.read_text()
        self.assertIn("-O check", log)
        self.assertIn("true", log)

    def test_login_refuses_stale_master(self) -> None:
        result = self.hpc("login", extra_env={
            "HPC_NO_OPEN": "1", "HPC_TEST_STALE": "1"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stale", result.stderr)
        self.assertIn("hpc login", result.stderr)
        self.assertNotIn("authenticated", result.stdout)
        self.assertNotIn("is up", result.stderr)

    def test_ensure_missing_master(self) -> None:
        result = self.hpc("ensure", extra_env={
            "HPC_NO_OPEN": "1", "HPC_TEST_DEAD": "1"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no SSH master", result.stderr)

    def test_doctor_stale_socket_points_to_login(self) -> None:
        result = self.hpc("doctor", extra_env={"HPC_TEST_STALE": "1"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("socket stale", result.stdout)
        self.assertIn("hpc login", result.stdout)
        self.assertNotIn("remote user", result.stdout)
        self.assertNotIn("printf", self.log.read_text())

    def test_doctor_dead_socket_points_to_login(self) -> None:
        result = self.hpc("doctor", extra_env={"HPC_TEST_DEAD": "1"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("hpc login", result.stdout)
        self.assertNotIn("remote user", result.stdout)
        self.assertNotIn("printf", self.log.read_text())

    def test_dry_run_allows_dirty_tree(self) -> None:
        (self.repo / "train.py").write_text("print('changed')\n")
        result = self.hpc("submit", "job.lsf", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("HEAD", result.stderr)

    def test_secret_set_writes_env_file(self) -> None:
        value = Path(self.tmp.name) / "value.txt"
        value.write_text("sk-test-value\n")
        result = self.hpc("secret", "set", "OPENROUTER_API_KEY", "--file", str(value))
        self.assertEqual(result.returncode, 0, result.stderr)
        written = self.stdin_log.read_text()
        self.assertIn("OPENROUTER_API_KEY\n", written)
        self.assertIn("sk-test-value", written)
        log = self.log.read_text()
        self.assertIn("mktemp", log)
        self.assertIn("mv -f", log)
        self.assertIn("flock", log)
        self.assertIn("chmod 600", log)
        self.assertNotIn("sk-test-value", result.stdout + result.stderr)
        self.assertNotIn("sk-test-value", log)

    def test_secret_quotes_values_with_spaces(self) -> None:
        value = Path(self.tmp.name) / "value.txt"
        value.write_text("sk test value\n")
        result = self.hpc("secret", "set", "K", "--file", str(value))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("'sk test value'", self.stdin_log.read_text())
        self.assertNotIn("sk test value", self.log.read_text())

    def test_secret_dry_run_hides_value_and_skips_ssh(self) -> None:
        value = Path(self.tmp.name) / "value.txt"
        value.write_text("sk-test-value\n")
        result = self.hpc("secret", "set", "K", "--file", str(value), "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("sk-test-value", result.stdout + result.stderr)
        self.assertFalse(self.log.exists())

    def test_secret_set_project_writes_project_file(self) -> None:
        value = Path(self.tmp.name) / "value.txt"
        value.write_text("sk-project-value\n")
        result = self.hpc("secret", "set", "--project", "K", "--file", str(value))
        self.assertEqual(result.returncode, 0, result.stderr)
        log = self.log.read_text()
        self.assertIn("/projects/", log)
        self.assertNotIn(str(self.home / ".config/dtu-hpc/secrets.env"), log)
        self.assertNotIn("sk-project-value", log)
        self.assertIn("sk-project-value", self.stdin_log.read_text())

    def test_secret_project_dry_run_shows_project_path(self) -> None:
        value = Path(self.tmp.name) / "value.txt"
        value.write_text("sk-project-value\n")
        result = self.hpc("secret", "set", "K", "--project", "--file", str(value),
                          "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("project scope", result.stdout)
        self.assertIn("/projects/", result.stdout)
        self.assertNotIn("sk-project-value", result.stdout + result.stderr)
        self.assertFalse(self.log.exists())

    def test_secret_list_parses_only_valid_names(self) -> None:
        secrets = Path(self.tmp.name) / "remote-secrets"
        secrets.write_text("# comment\nA=1\nnoise without equals\nB=2\n")
        result = self.hpc("secret", "list", extra_env={"HPC_TEST_SECRETS": str(secrets)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip().splitlines(), ["A", "B"])

    def test_secret_list_all_labels_scopes(self) -> None:
        global_secrets = Path(self.tmp.name) / "global-secrets"
        project_secrets = Path(self.tmp.name) / "project-secrets"
        global_secrets.write_text("G=1\n")
        project_secrets.write_text("P=2\n")
        result = self.hpc("secret", "list", "--all", extra_env={
            "HPC_TEST_SECRETS": str(global_secrets),
            "HPC_TEST_PROJECT_SECRETS": str(project_secrets),
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("global:\nG", result.stdout)
        self.assertIn("project (", result.stdout)
        self.assertIn("P", result.stdout)

    def test_secret_list_project_only(self) -> None:
        project_secrets = Path(self.tmp.name) / "project-secrets"
        project_secrets.write_text("P=2\n")
        result = self.hpc("secret", "list", "--project", extra_env={
            "HPC_TEST_PROJECT_SECRETS": str(project_secrets),
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "P")

    def test_sync_env_skips_when_manifest_matches(self) -> None:
        result = self.hpc("sync-env")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("up to date", result.stdout)
        log = self.log.read_text()
        self.assertNotIn("uv sync", log)
        self.assertNotIn("tar -xzf", log)

    def test_sync_env_rebuilds_and_writes_manifest(self) -> None:
        missing = Path(self.tmp.name) / "missing-manifest.json"
        result = self.hpc("sync-env", extra_env={"HPC_TEST_ENV_MANIFEST": str(missing)})
        self.assertEqual(result.returncode, 0, result.stderr)
        log = self.log.read_text()
        self.assertIn("timeout 600 uv sync --locked", log)
        self.assertNotIn("--python", log)
        self.assertNotIn("module load python3/3.11.9", log)
        self.assertIn("/work3/tester/hpc/venvs/proj", log)
        self.assertIn("hpc-env.json", log)
        manifest = self.stdin_log.read_text(errors="replace")
        self.assertIn("lock_sha256", manifest)
        self.assertIn("uv_version", manifest)
        self.assertIn("python_version", manifest)

    def test_submit_refuses_stale_env(self) -> None:
        (self.repo / "uv.lock").write_text("version = 2\n")
        self.git("add", "uv.lock")
        self.git("commit", "-qm", "bump lock")
        result = self.hpc("submit", "job.lsf")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stale for the current env inputs", result.stderr)
        self.assertIn("hpc sync-env", result.stderr)
        self.assertNotIn("bsub", self.log.read_text())

    def test_submit_refuses_python_version_change(self) -> None:
        (self.repo / ".python-version").write_text("3.12\n")
        self.git("add", ".python-version")
        self.git("commit", "-qm", "bump python")
        result = self.hpc("submit", "job.lsf")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stale for the current env inputs", result.stderr)
        self.assertNotIn("bsub", self.log.read_text())

    def test_submit_refuses_missing_env_manifest(self) -> None:
        self.env_manifest.unlink()
        result = self.hpc("submit", "job.lsf")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no env manifest", result.stderr)
        self.assertIn("hpc sync-env", result.stderr)
        self.assertNotIn("bsub", self.log.read_text())

    def test_doctor_reports_stale_env(self) -> None:
        (self.repo / "uv.lock").write_text("version = 2\n")
        self.git("add", "uv.lock")
        self.git("commit", "-qm", "bump lock")
        result = self.hpc("doctor")
        self.assertEqual(result.returncode, 1)
        self.assertIn("stale", result.stdout)
        self.assertIn("hpc sync-env", result.stdout)

    def test_dry_run_renders_env_placeholders(self) -> None:
        (self.repo / "job.lsf").write_text(
            "#BSUB -q p1\ncd {{CODE_DIR}}\necho {{VENV}} {{HF_HOME}} {{SECRETS}} {{PROJECT_SECRETS}}\n")
        self.git("add", "job.lsf")
        self.git("commit", "-qm", "placeholders")
        result = self.hpc("submit", "job.lsf", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("/work3/<user>/hpc/venvs/proj", result.stdout)
        self.assertIn("/work3/<user>/hf", result.stdout)
        self.assertIn("$HOME/.config/dtu-hpc/secrets.env", result.stdout)
        self.assertIn("/projects/", result.stdout)


class SyncPolicyDocsTest(unittest.TestCase):
    def test_docs_agree_on_single_venv_and_bounded_sync(self) -> None:
        skill = (REPO / "skills" / "dtu-hpc" / "SKILL.md").read_text()
        sync = (REPO / "skills" / "dtu-hpc" / "references" / "sync.md").read_text()
        self.assertIn("one mutable venv", sync)
        self.assertIn("uv sync --locked", sync)
        self.assertIn("timeout 600", sync)
        self.assertIn("env_input_sha256", sync)
        self.assertIn("`uv`/Python versions", sync)
        self.assertNotIn("module load python3/3.11.9", sync)
        self.assertNotIn("uv sync --locked --python", sync)
        self.assertIn("bounded exception", skill)
        self.assertIn("uv sync --locked", skill)
        self.assertNotIn("pip packages) belong", skill)


class RenderValuesTest(unittest.TestCase):
    def test_remote_placeholders_use_remote_identity(self) -> None:
        import runpy
        import types
        module = types.SimpleNamespace(**runpy.run_path(str(HPC), run_name="hpc_cli"))
        values = module.render_values({}, Path("/tmp/proj"), "work", "run", "sha",
                                      "job", "tester", "/home/tester")
        self.assertEqual(values["VENV"], "/work3/tester/hpc/venvs/proj")
        self.assertEqual(values["HF_HOME"], "/work3/tester/hf")
        self.assertEqual(values["SECRETS"], "$HOME/.config/dtu-hpc/secrets.env")
        self.assertTrue(values["PROJECT_SECRETS"].startswith(
            "$HOME/.config/dtu-hpc/projects/"))
        self.assertTrue(values["PROJECT_SECRETS"].endswith(".env"))


class TemplateSourceOrderTest(unittest.TestCase):
    def test_job_template_sources_global_before_project(self) -> None:
        lines = [
            line.strip()
            for line in (REPO / "templates" / "job.lsf").read_text().splitlines()
            if line.strip().startswith("[ -f")
        ]
        self.assertEqual(lines, [
            '[ -f "{{SECRETS}}" ] && . "{{SECRETS}}"',
            '[ -f "{{PROJECT_SECRETS}}" ] && . "{{PROJECT_SECRETS}}"',
        ])


class SshConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        import runpy
        import types
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.module = types.SimpleNamespace(
            **runpy.run_path(str(HPC), run_name="hpc_cli")
        )

    def test_reads_relative_includes_and_nested_files(self) -> None:
        ssh = Path(self.tmp.name) / ".ssh"
        nested = ssh / "config.d" / "nested"
        nested.mkdir(parents=True)
        (ssh / "config").write_text("Include config.d/*\n")
        (ssh / "config.d" / "dtu").write_text(
            "Include nested/*\nHost ignored\n  HostName example.com\n")
        (nested / "actual").write_text(
            "Host dtu\n  HostName login9.hpc.dtu.dk\n")
        self.assertEqual(self.module.dtu_aliases(ssh / "config"), ["dtu"])

    def test_include_cycle_does_not_recurse_forever(self) -> None:
        ssh = Path(self.tmp.name) / ".ssh"
        ssh.mkdir()
        (ssh / "config").write_text("Include config\nHost dtu\n  HostName hpc.dtu.dk\n")
        self.assertEqual(self.module.dtu_aliases(ssh / "config"), ["dtu"])


class ProjectKeyTest(unittest.TestCase):
    def setUp(self) -> None:
        import runpy
        import types
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.module = types.SimpleNamespace(
            **runpy.run_path(str(HPC), run_name="hpc_cli")
        )

    def make_repo(self, name: str, origin: str | None = None) -> Path:
        root = Path(self.tmp.name) / name
        root.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        if origin:
            subprocess.run(["git", "remote", "add", "origin", origin],
                           cwd=root, check=True)
        return root

    def test_same_origin_is_stable_across_checkouts(self) -> None:
        first = self.make_repo("one", "https://github.com/org/repo.git")
        second = self.make_repo("two", "https://github.com/org/repo.git")
        self.assertEqual(self.module.project_key(first),
                         self.module.project_key(second))
        self.assertEqual(self.module.project_key(first),
                         self.module.project_key(first))

    def test_origin_credentials_do_not_change_key(self) -> None:
        plain = self.make_repo("one", "https://github.com/org/repo.git")
        with_credentials = self.make_repo(
            "two", "https://user:token@github.com/org/repo.git")
        self.assertEqual(self.module.project_key(plain),
                         self.module.project_key(with_credentials))

    def test_different_origins_and_fallbacks_collide_only_by_design(self) -> None:
        first = self.make_repo("first", "https://github.com/org/a.git")
        second = self.make_repo("second", "https://github.com/org/b.git")
        fallback_a = self.make_repo("fallback-a")
        fallback_b = self.make_repo("fallback-b")
        self.assertNotEqual(self.module.project_key(first),
                            self.module.project_key(second))
        self.assertNotEqual(self.module.project_key(fallback_a),
                            self.module.project_key(fallback_b))


class SecretWriteScriptTest(unittest.TestCase):
    def setUp(self) -> None:
        import runpy
        import types
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "secrets.env"
        fake_bin = Path(self.tmp.name) / "bin"
        fake_bin.mkdir()
        flock = fake_bin / "flock"
        flock.write_text("#!/bin/sh\nexit 0\n")
        flock.chmod(0o755)
        self.env = os.environ.copy()
        self.env["PATH"] = f"{fake_bin}{os.pathsep}{self.env['PATH']}"
        self.module = types.SimpleNamespace(
            **runpy.run_path(str(HPC), run_name="hpc_cli")
        )

    def run_script(self, name: str, value: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", "-c", self.module.SECRET_WRITE, "hpc", str(self.path)],
            input=f"{name}\n{shlex.quote(value)}\n",
            text=True,
            capture_output=True,
            env=self.env,
        )

    def test_creates_missing_file_with_mode_600(self) -> None:
        result = self.run_script("K", "sk-test")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.path.read_text(), "K=sk-test\n")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_preserves_other_lines_and_replaces_key(self) -> None:
        self.path.write_text("# keep\nA=1\nK=old\nNOISE\n")
        self.path.chmod(0o644)
        result = self.run_script("K", "sk test")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.path.read_text(), "# keep\nA=1\nK='sk test'\nNOISE\n"
        )
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_refuses_unreadable_existing_file(self) -> None:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root can read mode 000 files")
        self.path.write_text("A=1\n")
        self.path.chmod(0)
        result = self.run_script("K", "sk-test")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot read existing secrets file", result.stderr)
        self.path.chmod(0o600)
        self.assertEqual(self.path.read_text(), "A=1\n")
        self.assertEqual(list(self.path.parent.glob("secrets.env.tmp.*")), [])


if __name__ == "__main__":
    unittest.main()
