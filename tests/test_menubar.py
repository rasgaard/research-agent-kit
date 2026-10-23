"""Tests for the SwiftBar renderer (swiftbar/menubar.py), no network."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "hpc_menubar", REPO / "swiftbar" / "menubar.py")
assert SPEC and SPEC.loader
menubar = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(menubar)


def settings(**overrides: int) -> dict[str, int]:
    values = {key: int(value) for key, value in menubar.SETTINGS.items()}
    values.update(overrides)
    return values


class MenubarTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.state_dir = base / "state"
        self.config = base / "menubar.ini"
        self.old_state = os.environ.get("HPC_STATE_DIR")
        self.old_config = os.environ.get("HPC_MENUBAR_CONFIG")
        os.environ["HPC_STATE_DIR"] = str(self.state_dir)
        os.environ["HPC_MENUBAR_CONFIG"] = str(self.config)

        def restore() -> None:
            for key, value in (("HPC_STATE_DIR", self.old_state),
                               ("HPC_MENUBAR_CONFIG", self.old_config)):
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.addCleanup(restore)

    def test_settings_create_default_config(self) -> None:
        self.assertFalse(self.config.exists())
        values = menubar.load_settings()
        self.assertEqual(values["idle_seconds"], 300)
        self.assertIn("[menubar]", self.config.read_text())

    def test_merge_poll_tracks_running_then_finished(self) -> None:
        state = menubar.empty_state()
        now = 1_700_000_000.0
        record = {
            "job_id": "123", "key": "123", "stat": "RUN", "queue": "p1",
            "name": "train", "submit_time": "Oct 23 09:43:32 2026",
            "elapsed_seconds": 60,
        }
        menubar.merge_poll(
            state, {"host": "login9", "records": [record]}, settings(), now)
        self.assertEqual(state["jobs"]["123"]["stat"], "RUN")
        self.assertEqual(state["last_nonempty_at"], now)
        self.assertFalse(state["dormant"])

        menubar.merge_poll(
            state, {"host": "login9", "records": [dict(record, stat="DONE")]},
            settings(), now + 30)
        self.assertEqual(state["jobs"]["123"]["stat"], "DONE")
        self.assertEqual(state["jobs"]["123"]["finished_at"], now + 30)

    def test_disappeared_job_becomes_gone(self) -> None:
        state = menubar.empty_state()
        now = 1_700_000_000.0
        record = {"job_id": "1", "key": "1", "stat": "RUN", "queue": "p1",
                  "name": "a", "submit_time": "", "elapsed_seconds": 10}
        menubar.merge_poll(
            state, {"host": "h", "records": [record]}, settings(), now)
        menubar.merge_poll(state, {"host": "h", "records": []}, settings(), now + 60)
        self.assertEqual(state["jobs"]["1"]["stat"], "GONE")
        self.assertEqual(state["jobs"]["1"]["finished_at"], now + 60)

    def test_old_finished_jobs_are_pruned(self) -> None:
        state = menubar.empty_state()
        state["jobs"] = {"1": {"key": "1", "stat": "DONE", "finished_at": 1000.0}}
        menubar.prune(state["jobs"], settings(cache_hours=1, max_cached_jobs=20),
                      1000.0 + 2 * 3600)
        self.assertEqual(state["jobs"], {})

    def test_idle_poll_interval_and_dormant_wake(self) -> None:
        state = menubar.empty_state()
        now = 1_700_000_000.0
        values = settings(dormant_minutes=30)
        menubar.merge_poll(state, {"host": "h", "records": []}, values, now)
        self.assertFalse(state["dormant"])
        self.assertFalse(menubar.should_poll(state, values, now + 30))
        self.assertTrue(menubar.should_poll(state, values, now + 300))

        menubar.merge_poll(state, {"host": "h", "records": []}, values, now + 31 * 60)
        self.assertTrue(state["dormant"])
        self.assertFalse(menubar.should_poll(state, values, now + 32 * 60))

        self.state_dir.mkdir(parents=True, exist_ok=True)
        menubar.wake_path().touch()
        self.assertTrue(menubar.should_poll(state, values, now + 32 * 60))
        self.assertFalse(menubar.wake_path().exists())

    def test_title_counts_pending_alert_and_failure(self) -> None:
        values = settings(pending_alert_minutes=30, failure_minutes=60)
        submitted = menubar.parse_lsf_time("Oct 23 09:00:00 2026")
        assert submitted is not None
        now = submitted + 3600
        state = menubar.empty_state()
        state["jobs"] = {
            "1": {"key": "1", "stat": "RUN", "elapsed_seconds": 60,
                  "finished_at": None},
            "2": {"key": "2", "stat": "PEND", "submit_time": "Oct 23 09:00:00 2026",
                  "finished_at": None},
        }
        title = menubar.title_line(state, values, now)
        self.assertIn("1R 1P", title)
        self.assertIn("orange", title)
        state["jobs"]["3"] = {"key": "3", "stat": "KILL", "finished_at": now - 60}
        title = menubar.title_line(state, values, now)
        self.assertIn("!", title)
        self.assertIn("red", title)

    def test_render_sanitizes_names_and_offers_actions(self) -> None:
        now = 1_700_000_000.0
        state = menubar.empty_state()
        state["last_poll_at"] = now
        state["host"] = "login9"
        state["jobs"] = {
            "1": {"key": "1", "stat": "RUN", "queue": "p1", "name": "a|b",
                  "elapsed_seconds": 60, "finished_at": None},
        }
        output = menubar.render(state, settings(), now)
        self.assertIn("a/b", output)
        self.assertNotIn("a|b", output)
        self.assertIn("Running (1)", output)
        self.assertIn("--Details", output)
        self.assertIn("--Open logs", output)
        self.assertIn("Refresh now", output)
        self.assertIn("Updated", output)

    def test_error_render_offers_login(self) -> None:
        now = 1_700_000_000.0
        state = menubar.empty_state()
        state["last_poll_at"] = now
        state["last_error"] = {"kind": "auth", "message": "expired", "at": now}
        output = menubar.render(state, settings(), now)
        self.assertIn("HPC login", output)
        self.assertIn("Login", output)
        self.assertIn("param1=login", output)
        self.assertIn("stale", output)

    def test_action_helper_refresh_writes_wake(self) -> None:
        env = os.environ.copy()
        env["HPC_STATE_DIR"] = str(self.state_dir)
        subprocess.run(["/bin/sh", str(menubar.ACTION), "refresh"],
                       env=env, check=True)
        self.assertTrue(menubar.wake_path().exists())


if __name__ == "__main__":
    unittest.main()
