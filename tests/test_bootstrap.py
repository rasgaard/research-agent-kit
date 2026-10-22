"""Tests for the research-init static scaffold."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BOOTSTRAP = REPO / "skills" / "research-init" / "scripts" / "bootstrap.py"


class BootstrapTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target = Path(self.tmp.name) / "project"
        self.target.mkdir()

    def run_bootstrap(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(BOOTSTRAP), "--target", str(self.target), *args],
            text=True,
            capture_output=True,
        )

    def test_dry_run_prints_layout_without_writing(self) -> None:
        result = self.run_bootstrap("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("copy AGENTS.md", result.stdout)
        self.assertIn("copy templates/smoke.lsf", result.stdout)
        self.assertIn("create experiments.jsonl", result.stdout)
        self.assertFalse((self.target / "AGENTS.md").exists())
        self.assertFalse((self.target / "experiments.jsonl").exists())

    def test_dry_run_previews_replacements(self) -> None:
        (self.target / "README.md").write_text("custom\n")
        result = self.run_bootstrap("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("replace README.md", result.stdout)
        self.assertEqual((self.target / "README.md").read_text(), "custom\n")

    def test_scaffold_layout(self) -> None:
        result = self.run_bootstrap()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.target / "AGENTS.md").read_text(),
            (REPO / "AGENTS.md").read_text(),
        )
        self.assertTrue((self.target / "templates" / "job.lsf").is_file())
        self.assertTrue((self.target / "templates" / "smoke.lsf").is_file())
        self.assertTrue((self.target / "templates" / "config.ini").is_file())
        self.assertTrue((self.target / "templates" / "ssh_config").is_file())
        self.assertTrue((self.target / ".github" / "ISSUE_TEMPLATE" / "task.md").is_file())
        self.assertTrue((self.target / "README.md").is_file())
        self.assertEqual((self.target / "experiments.jsonl").read_text(), "")
        self.assertIn("runs/", (self.target / ".gitignore").read_text())

    def test_script_resolves_through_symlink(self) -> None:
        link = Path(self.tmp.name) / "bootstrap-link.py"
        link.symlink_to(BOOTSTRAP)
        result = subprocess.run(
            [sys.executable, str(link), "--target", str(self.target), "--dry-run"],
            text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("copy AGENTS.md", result.stdout)

    def test_existing_file_requires_force(self) -> None:
        readme = self.target / "README.md"
        readme.write_text("custom\n")
        result = self.run_bootstrap()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already exists", result.stderr)
        self.assertEqual(readme.read_text(), "custom\n")
        result = self.run_bootstrap("--force")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(readme.read_text(), "custom\n")


if __name__ == "__main__":
    unittest.main()
