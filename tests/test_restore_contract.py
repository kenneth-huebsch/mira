from __future__ import annotations

import os
import signal
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).parents[1]


class RestoreContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "blueprint"
        self.root.mkdir()
        for name in ("scripts", "workspace", "templates", "openclaw"):
            shutil.copytree(REPO / name, self.root / name)
        self.home = Path(self.temp.name) / "live"
        self.workspace = self.home / "workspace"
        self.source = Path(self.temp.name) / "openclaw-source"
        self.source.mkdir()
        self.env = {
            **os.environ,
            "TARGET_OPENCLAW_HOME": str(self.home),
            "TARGET_WORKSPACE": str(self.workspace),
            "OPENCLAW_SOURCE": str(self.source),
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def restore(self, *, check: bool = True, env: dict[str, str] | None = None):
        return subprocess.run(
            ["bash", str(self.root / "scripts/restore-to-live.sh")],
            env=env or self.env,
            text=True,
            capture_output=True,
            check=check,
        )

    def sync(self, *, check: bool = True, env: dict[str, str] | None = None):
        return subprocess.run(
            ["bash", str(self.root / "scripts/sync-from-live.sh")],
            env=env or self.env,
            text=True,
            capture_output=True,
            check=check,
        )

    def test_runtime_and_memory_survive_two_restores(self) -> None:
        runtime = self.workspace / "runtime"
        fixtures = (
            "coding-harness-runs/run-1/status.json",
            "coding-harness-runs/run-1/checkpoint.json",
            "coding-harness-runs/run-1/.lock",
            "coding-harness-plans/spec.json",
            "repos/project/.git/HEAD",
        )
        for rel in fixtures:
            path = runtime / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"keep:{rel}")
        memory = {
            "MEMORY.md": "private durable memory",
            "SESSION-STATE.md": "private session state",
            "DREAMS.md": "private dreams",
            "memory/2026-07-22.md": "private daily memory",
        }
        for rel, value in memory.items():
            path = self.workspace / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value)
        self.restore()
        self.restore()
        for rel in fixtures:
            self.assertEqual((runtime / rel).read_text(), f"keep:{rel}")
        for rel, value in memory.items():
            self.assertEqual((self.workspace / rel).read_text(), value)

    def test_injected_failure_rolls_back_managed_files(self) -> None:
        self.restore()
        managed = self.workspace / "AGENTS.md"
        before = managed.read_bytes()
        (self.root / "workspace/AGENTS.md").write_text("replacement\n")
        env = {**self.env, "MIRA_RESTORE_FAIL_AFTER": "2"}
        result = self.restore(check=False, env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(managed.read_bytes(), before)
        states = list((self.home / ".restore-rollback").glob("*/metadata.json"))
        self.assertTrue(any('"state": "rolled_back"' in path.read_text() for path in states))

    def test_manifest_traversal_and_destination_symlink_fail(self) -> None:
        malicious = self.root / "scripts/malicious-manifest.txt"
        malicious.write_text("../escape\n")
        env = {**self.env, "WORKSPACE_MANIFEST": str(malicious)}
        result = self.restore(check=False, env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.home / "escape").exists())

        unsafe = self.workspace / "skills"
        unsafe.parent.mkdir(parents=True, exist_ok=True)
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        unsafe.symlink_to(outside, target_is_directory=True)
        result = self.restore(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(outside.iterdir()), [])

    def test_duplicate_normalized_manifest_entries_fail_for_restore_and_sync(self) -> None:
        duplicate = self.root / "scripts/duplicate-manifest.txt"
        duplicate.write_text("AGENTS.md\nAGENTS.md\n")
        restore_env = {**self.env, "WORKSPACE_MANIFEST": str(duplicate)}
        result = self.restore(check=False, env=restore_env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate normalized", result.stderr)

        live_source = Path(self.temp.name) / "sync-source"
        shutil.copytree(self.root / "openclaw", live_source)
        live_home = Path(self.temp.name) / "sync-live"
        live_workspace = live_home / "workspace"
        shutil.copytree(self.root / "workspace", live_workspace)
        sync_env = {
            **os.environ,
            "LIVE_OPENCLAW_HOME": str(live_home),
            "LIVE_WORKSPACE": str(live_workspace),
            "OPENCLAW_SOURCE": str(live_source),
            "WORKSPACE_MANIFEST": str(duplicate),
        }
        result = self.sync(check=False, env=sync_env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate normalized", result.stderr)

    def test_source_and_destination_root_symlinks_fail_closed(self) -> None:
        actual_source = Path(self.temp.name) / "actual-source"
        actual_source.mkdir()
        symlink_source = Path(self.temp.name) / "source-link"
        symlink_source.symlink_to(actual_source, target_is_directory=True)
        result = self.restore(
            check=False,
            env={**self.env, "OPENCLAW_SOURCE": str(symlink_source)},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("canonical non-symlink directory", result.stderr)

        actual_workspace = Path(self.temp.name) / "actual-workspace"
        actual_workspace.mkdir()
        symlink_workspace = Path(self.temp.name) / "workspace-link"
        symlink_workspace.symlink_to(actual_workspace, target_is_directory=True)
        result = self.restore(
            check=False,
            env={**self.env, "TARGET_WORKSPACE": str(symlink_workspace)},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("canonical non-symlink directory", result.stderr)

    def test_sigkill_transaction_is_reconciled_before_next_restore(self) -> None:
        self.restore()
        managed = self.workspace / "AGENTS.md"
        original = managed.read_bytes()
        blueprint = self.root / "workspace/AGENTS.md"
        blueprint_original = blueprint.read_bytes()
        blueprint.write_text("crash replacement\n")
        killed = self.restore(
            check=False,
            env={**self.env, "MIRA_TRANSACTION_KILL_AFTER": "1"},
        )
        self.assertIn(killed.returncode, (-signal.SIGKILL, 128 + signal.SIGKILL))
        blueprint.write_bytes(blueprint_original)
        self.restore()
        self.assertEqual(managed.read_bytes(), original)
        metadata = list((self.home / ".restore-rollback").glob("*/metadata.json"))
        states = [path.read_text() for path in metadata]
        self.assertTrue(any('"state": "rolled_back"' in state for state in states))


if __name__ == "__main__":
    unittest.main()
