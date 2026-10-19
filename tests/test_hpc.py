"""Stubbed tests for bin/hpc — no network, no real SSH, no HPC."""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
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
        self.log = base / "ssh.log"
        (self.stub_bin / "ssh").write_text(textwrap.dedent("""\
            #!/bin/sh
            printf '%s\\n' "$*" >> "$HPC_TEST_LOG"
            cat >/dev/null 2>&1 || true
            case "$*" in
              *"-O check"*) exit 0 ;;
              *"bsub"*) printf 'Job <123> is submitted to queue <gpua100>.\\n' ;;
              *"bstat"*) printf 'JOBID USER QUEUE JOB_NAME NALLOC STAT\\n' ;;
              *"printf"*) printf 'tester\\n/home/tester\\n' ;;
            esac
            exit 0
            """))
        (self.stub_bin / "ssh").chmod(0o755)
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

    def hpc(self, *args: str) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env.update({
            "HPC_CONFIG": str(self.config),
            "HPC_NO_OPEN": "1",
            "HPC_TEST_LOG": str(self.log),
            "PATH": f"{self.stub_bin}{os.pathsep}{env['PATH']}",
        })
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

    def test_queue_override(self) -> None:
        result = self.hpc("submit", "job.lsf", "--queue", "p1", "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("#BSUB -q p1", result.stdout)

    def test_allow_dirty_warns_but_submits_head(self) -> None:
        (self.repo / "train.py").write_text("print('changed')\n")
        result = self.hpc("submit", "job.lsf", "--allow-dirty")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("dirty", result.stderr)


if __name__ == "__main__":
    unittest.main()
