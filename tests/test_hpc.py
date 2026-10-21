"""Stubbed tests for bin/hpc — no network, no real SSH, no HPC."""
from __future__ import annotations

import json
import os
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
              *"bstat"*) printf 'JOBID USER QUEUE JOB_NAME NALLOC STAT\\n' ;;
              *"bjobs"*) [ -n "${HPC_TEST_BJOBS:-}" ] && cat "$HPC_TEST_BJOBS" ;;
              *"%T@"*) [ -n "${HPC_TEST_LOG_STATS:-}" ] && cat "$HPC_TEST_LOG_STATS" ;;
              *"-printf"*) [ -n "${HPC_TEST_LOG_NAMES:-}" ] && cat "$HPC_TEST_LOG_NAMES" ;;
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
        self.git("add", ".")
        self.git("commit", "-qm", "initial")

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.repo, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def write_job(self, content: str) -> None:
        (self.repo / "job.lsf").write_text(textwrap.dedent(content))
        self.git("add", "job.lsf")
        self.git("commit", "-qm", "job")

    def add_ledger(self, job_id: int = 123, submitted_at: str | None = None) -> None:
        path = self.repo / ".git" / "hpc" / "jobs.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "job_id": job_id,
            "run_id": f"20260101T000000Z-{job_id}",
            "run_dir": f"/work3/tester/hpc/proj/jobs/20260101T000000Z-{job_id}",
        }
        if submitted_at:
            entry["submitted_at"] = submitted_at
        path.write_text(json.dumps(entry) + "\n")

    def hpc(self, *args: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env.update({
            "HPC_CONFIG": str(self.config),
            "HPC_NO_OPEN": "1",
            "HPC_TEST_LOG": str(self.log),
            "HPC_TEST_STDIN": str(self.stdin_log),
            "HOME": str(self.home),
            "PATH": f"{self.stub_bin}{os.pathsep}{env['PATH']}",
        })
        env.update(extra_env or {})
        return subprocess.run([sys.executable, str(HPC), *args], cwd=self.repo,
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

    def test_status_no_id_lists_all_jobs(self) -> None:
        result = self.hpc("status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("bjobs -w", self.log.read_text())

    def test_status_id_uses_bstat(self) -> None:
        result = self.hpc("status", "123")
        self.assertEqual(result.returncode, 0, result.stderr)
        log = self.log.read_text()
        self.assertIn('bstat "$1"', log)
        self.assertIn("123", log)

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
        self.assertIn("hpc login", result.stdout)

    def test_init_without_alias_refuses_default(self) -> None:
        result = self.hpc("init", "--force")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no DTU SSH alias", result.stderr)
        self.assertIn("Host dtu", result.stderr)

    def test_init_accepts_explicit_ssh_host(self) -> None:
        result = self.hpc("init", "--force", "--ssh-host", "my-dtu")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("host = my-dtu", self.config.read_text())

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
        self.assertIn("OPENROUTER_API_KEY=sk-test-value", written)
        self.assertIn("chmod 600", self.log.read_text())
        self.assertNotIn("sk-test-value", result.stdout + result.stderr)
        self.assertNotIn("sk-test-value", self.log.read_text())

    def test_secret_quotes_values_with_spaces(self) -> None:
        value = Path(self.tmp.name) / "value.txt"
        value.write_text("sk test value\n")
        result = self.hpc("secret", "set", "K", "--file", str(value))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("K='sk test value'", self.stdin_log.read_text())
        self.assertNotIn("sk test value", self.log.read_text())

    def test_secret_dry_run_hides_value_and_skips_ssh(self) -> None:
        value = Path(self.tmp.name) / "value.txt"
        value.write_text("sk-test-value\n")
        result = self.hpc("secret", "set", "K", "--file", str(value), "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("sk-test-value", result.stdout + result.stderr)
        self.assertFalse(self.log.exists())

    def test_sync_env_uses_shared_venv(self) -> None:
        result = self.hpc("sync-env")
        self.assertEqual(result.returncode, 0, result.stderr)
        log = self.log.read_text()
        self.assertIn("uv sync --frozen", log)
        self.assertIn("/work3/tester/hpc/venvs/proj", log)

    def test_dry_run_renders_env_placeholders(self) -> None:
        (self.repo / "job.lsf").write_text(
            "#BSUB -q p1\ncd {{CODE_DIR}}\necho {{VENV}} {{HF_HOME}} {{SECRETS}}\n")
        self.git("add", "job.lsf")
        self.git("commit", "-qm", "placeholders")
        result = self.hpc("submit", "job.lsf", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("/work3/<user>/hpc/venvs/proj", result.stdout)
        self.assertIn("/work3/<user>/hf", result.stdout)
        self.assertIn("$HOME/.config/dtu-hpc/secrets.env", result.stdout)


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


class MergeEnvTest(unittest.TestCase):
    def test_preserves_comments_and_replaces_key(self) -> None:
        import runpy
        import types
        module = types.SimpleNamespace(**runpy.run_path(str(HPC), run_name="hpc_cli"))
        text = "# keep me\nA=1\nB=2\n"
        self.assertEqual(module.merge_env(text, "B", "3"), "# keep me\nA=1\nB=3\n")
        self.assertEqual(module.merge_env(text, "C", "4"), "# keep me\nA=1\nB=2\nC=4\n")


if __name__ == "__main__":
    unittest.main()
