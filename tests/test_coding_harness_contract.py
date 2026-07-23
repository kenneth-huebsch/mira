from __future__ import annotations

import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ADAPTER_SOURCE = Path(__file__).parents[1] / "workspace/skills/coding-harness/coding_harness.py"


def git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, text=True, capture_output=True).stdout.strip()


class AdapterContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.skill = self.workspace / "skills/coding-harness"
        self.harness = self.workspace / "runtime/repos/agent"
        self.skill.mkdir(parents=True)
        self.harness.mkdir(parents=True)
        git("init", "-q", cwd=self.harness)
        git("config", "user.name", "Test", cwd=self.harness)
        git("config", "user.email", "test@example.invalid", cwd=self.harness)
        git("remote", "add", "origin", "https://github.com/kenneth-huebsch/agent.git", cwd=self.harness)
        runner = self.harness / "scripts/agent_run.py"
        runner.parent.mkdir()
        runner.write_text(
            """#!/usr/bin/env python3
import json, os, signal, sys, time
if "--help" in sys.argv:
    print("Blocking version-2 phased agent harness runner.")
elif sys.argv[1:2] == ["sleep"]:
    def stop(signum, frame):
        print(json.dumps({"signal": signum}))
        raise SystemExit(130)
    signal.signal(signal.SIGTERM, stop)
    time.sleep(30)
else:
    payload = {"argv": sys.argv[1:], "env": dict(os.environ)}
    if sys.argv[1:2] == ["run-plan"]:
        plan_path = sys.argv[sys.argv.index("--plan") + 1]
        with open(plan_path, encoding="utf-8") as stream:
            payload["plan"] = json.load(stream)
    print(json.dumps(payload))
""",
            encoding="utf-8",
        )
        runner.chmod(0o755)
        git("add", ".", cwd=self.harness)
        git("commit", "-qm", "fake v2", cwd=self.harness)
        self.sha = git("rev-parse", "HEAD", cwd=self.harness)
        self.lock = self.skill / "harness.lock.json"
        self.lock.write_text(json.dumps({
            "repository": "https://github.com/kenneth-huebsch/agent.git",
            "revision": self.sha,
            "contract_version": 2,
        }))
        self.policy = self.skill / "policy.json"
        self.policy.write_text(json.dumps({
            "schema_version": 2,
            "adapter": {
                "contract_version": 2,
                "runtime_repos": str(self.workspace / "runtime/repos"),
                "runs_dir": str(self.workspace / "runtime/coding-harness-runs"),
                "denied_roots": [
                    str(self.workspace),
                    str(self.harness),
                    str(self.root / "denied"),
                ],
            },
            "allowed_target_roots": [str(self.workspace / "runtime/repos")],
            "inherited_environment_keys": ["HOME", "PATH", "LANG"],
            "capability_environment": {},
            "sensitive_path_patterns": [r"(^|/)\.env$"],
            "default_timeout_seconds": 3000,
            "cancellation_grace_seconds": 1,
            "allow_shell_verification": False,
            "default_branches": ["main", "master"],
            "guarded_commands": ["git push"],
        }))
        self.env = {
            "OPENCLAW_WORKSPACE": str(self.workspace),
            "MIRA_HARNESS_LOCK": str(self.lock),
            "MIRA_HARNESS_POLICY": str(self.policy),
        }
        self.module = self.load_module()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def load_module(self):
        with mock.patch.dict(os.environ, self.env, clear=False):
            spec = importlib.util.spec_from_file_location(f"adapter_{time.time_ns()}", ADAPTER_SOURCE)
            module = importlib.util.module_from_spec(spec)
            assert spec.loader
            spec.loader.exec_module(module)
            return module

    def make_repo(self, path: Path, origin: str = "https://github.com/acme/repo.git") -> Path:
        path.mkdir(parents=True)
        git("init", "-q", cwd=path)
        git("remote", "add", "origin", origin, cwd=path)
        return path

    def test_lock_rejects_unknown_symbolic_and_abbreviated_revisions(self) -> None:
        for revision in ("main", self.sha[:12], self.sha.upper()):
            self.lock.write_text(json.dumps({
                "repository": "https://github.com/kenneth-huebsch/agent.git",
                "revision": revision,
                "contract_version": 2,
            }))
            with self.assertRaises(self.module.AdapterError):
                self.module.load_lock()
        self.lock.write_text(json.dumps({
            "repository": "https://github.com/kenneth-huebsch/agent.git",
            "revision": self.sha,
            "contract_version": 2,
            "extra": True,
        }))
        with self.assertRaises(self.module.AdapterError):
            self.module.load_lock()

    def test_existing_pin_materializes_offline_and_is_detached_compatible(self) -> None:
        original = self.module.command
        def offline(argv, **kwargs):
            self.assertNotIn(argv[1] if len(argv) > 1 else "", {"clone", "fetch"})
            return original(argv, **kwargs)
        with mock.patch.object(self.module, "command", side_effect=offline):
            lock = self.module.materialize_harness()
        self.assertEqual(lock["revision"], self.sha)
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.harness), self.sha)
        symbolic = subprocess.run(
            ["git", "symbolic-ref", "-q", "HEAD"], cwd=self.harness, capture_output=True
        )
        self.assertNotEqual(symbolic.returncode, 0)

    def test_fresh_materialization_authenticates_clone_and_exact_sha_fetch(self) -> None:
        remote = self.root / "remote.git"
        git("clone", "--bare", str(self.harness), str(remote))
        shutil.rmtree(self.harness)
        calls: list[list[str]] = []

        def offline_auth(args, *, check=True):
            calls.append(args)
            if args[0] == "clone":
                result = subprocess.run(
                    ["git", "clone", "--no-checkout", str(remote), args[-1]],
                    text=True, capture_output=True, check=check,
                )
                git(
                    "-C", args[-1], "remote", "set-url", "origin",
                    "https://github.com/kenneth-huebsch/agent.git",
                )
                return result
            marker = args.index("fetch")
            local_args = [*args[:marker], "fetch", "--no-tags", str(remote), *args[marker + 3:]]
            return subprocess.run(["git", *local_args], text=True, capture_output=True, check=check)

        with mock.patch.object(self.module, "git_with_gh_auth", side_effect=offline_auth):
            lock = self.module.materialize_harness()
        self.assertEqual(lock["revision"], self.sha)
        self.assertEqual(calls[0][0:3], [
            "clone", "--no-checkout", "https://github.com/kenneth-huebsch/agent.git",
        ])
        fetch = next(call for call in calls if "fetch" in call)
        self.assertEqual(fetch[-1], self.sha)
        symbolic = subprocess.run(
            ["git", "symbolic-ref", "-q", "HEAD"], cwd=self.harness, capture_output=True
        )
        self.assertNotEqual(symbolic.returncode, 0)

    def test_harness_origin_mismatch_fails_closed(self) -> None:
        git("remote", "set-url", "origin", "https://github.com/evil/agent.git", cwd=self.harness)
        with self.assertRaisesRegex(self.module.AdapterError, "origin"):
            self.module.materialize_harness()

    def test_collision_free_targets_and_existing_origin_validation(self) -> None:
        first = self.make_repo(
            self.workspace / "runtime/repos/one--same",
            "https://github.com/one/same.git",
        )
        second = self.make_repo(
            self.workspace / "runtime/repos/two--same",
            "https://github.com/two/same.git",
        )
        policy = self.module.load_policy()
        self.assertEqual(self.module.resolve_target("one/same", policy), first.resolve())
        self.assertEqual(self.module.resolve_target("two/same", policy), second.resolve())
        self.make_repo(
            self.workspace / "runtime/repos/three--same",
            "https://github.com/not-three/same.git",
        )
        with self.assertRaisesRegex(self.module.AdapterError, "origin"):
            self.module.resolve_target("three/same", policy)

    def test_allowed_denied_and_symlink_boundaries(self) -> None:
        policy = self.module.load_policy()
        allowed = self.make_repo(self.workspace / "runtime/repos/acme--target")
        self.assertEqual(self.module.resolve_target(str(allowed), policy), allowed.resolve())
        outside = self.make_repo(self.root / "outside")
        with self.assertRaisesRegex(self.module.AdapterError, "outside policy"):
            self.module.resolve_target(str(outside), policy)
        link = self.workspace / "runtime/repos/link"
        link.symlink_to(allowed, target_is_directory=True)
        with self.assertRaisesRegex(self.module.AdapterError, "symlink"):
            self.module.resolve_target(str(link), policy)
        with self.assertRaisesRegex(self.module.AdapterError, "denied"):
            self.module.resolve_target(str(self.harness), policy)
        nested = self.make_repo(self.harness / "nested")
        with self.assertRaisesRegex(self.module.AdapterError, "denied"):
            self.module.resolve_target(str(nested), policy)

    def test_environment_scrub_single_json_and_forwarding(self) -> None:
        with mock.patch.dict(os.environ, {**self.env, "OPENROUTER_API_KEY": "secret", "LANG": "C"}, clear=False):
            combined, code = self.module.delegate(
                "resume",
                ["record-1", "--restart-current-stage", "--implement-model", "model-x"],
            )
        self.assertEqual(code, 0)
        self.assertEqual(combined["harness_revision"], self.sha)
        result = combined["runner_result"]
        self.assertNotIn("OPENROUTER_API_KEY", result["env"])
        self.assertEqual(result["env"]["XDG_CONFIG_HOME"], "/home/node/.openclaw")
        self.assertEqual(result["env"]["GH_CONFIG_DIR"], "/home/node/.openclaw/gh")
        self.assertIn("--restart-current-stage", result["argv"])
        self.assertIn("--policy", result["argv"])
        combined, _ = self.module.delegate("cancel", ["record-1", "--reason", "stop"])
        self.assertIn("--reason", combined["runner_result"]["argv"])
        encoded = json.dumps(combined)
        self.assertIsInstance(json.loads(encoded), dict)

    def test_run_and_run_plan_always_forward_policy_timeout(self) -> None:
        target = self.make_repo(self.workspace / "runtime/repos/acme--target")
        run_args = self.module.build_parser().parse_args([
            "run", "--target", str(target), "--prompt", "task", "--dry-run",
        ])
        combined, code = self.module.execute(run_args)
        self.assertEqual(code, 0)
        argv = combined["runner_result"]["argv"]
        self.assertEqual(argv[argv.index("--timeout") + 1], "3000")

        plan = self.workspace / "runtime/coding-harness-plans/documented.json"
        plan.parent.mkdir(parents=True)
        plan.write_text(json.dumps({
            "schema_version": 2,
            "phases": [{
                "id": "phase-1",
                "prompt": "task",
                "verification": {"commands": [{"argv": ["python3", "-m", "unittest"]}]},
            }],
        }))
        self.module.INVOCATION_CWD = self.workspace
        plan_args = self.module.build_parser().parse_args([
            "run-plan", "--target", str(target),
            "--plan", "runtime/coding-harness-plans/documented.json", "--dry-run",
        ])
        combined, code = self.module.execute(plan_args)
        self.assertEqual(code, 0)
        argv = combined["runner_result"]["argv"]
        self.assertEqual(argv[argv.index("--timeout") + 1], "3000")
        self.assertEqual(Path(argv[argv.index("--plan") + 1]), plan.resolve())
        parsed = json.loads(plan.read_text())
        self.assertEqual(parsed["schema_version"], 2)
        self.assertIn("commands", parsed["phases"][0]["verification"])
        self.assertEqual(combined["runner_result"]["plan"], parsed)

    def test_run_plan_rejects_outside_symlink_and_directory_paths(self) -> None:
        plans = self.workspace / "runtime/coding-harness-plans"
        plans.mkdir(parents=True)
        outside = self.root / "outside-plan.json"
        outside.write_text("{}")
        self.module.INVOCATION_CWD = self.workspace
        with self.assertRaisesRegex(self.module.AdapterError, "beneath"):
            self.module.resolve_plan_path(str(outside))
        link = plans / "link.json"
        link.symlink_to(outside)
        with self.assertRaisesRegex(self.module.AdapterError, "symlink"):
            self.module.resolve_plan_path(str(link))
        with self.assertRaisesRegex(self.module.AdapterError, "regular"):
            self.module.resolve_plan_path(str(plans))

    def test_private_clone_uses_gh_credential_helper_without_token(self) -> None:
        captured: list[tuple[list[str], dict[str, object]]] = []
        original = self.module.command

        def recording(argv, **kwargs):
            captured.append((argv, kwargs))
            return original(argv, **kwargs)

        with mock.patch.dict(os.environ, {"GH_TOKEN": "secret-token"}, clear=False), \
             mock.patch.object(self.module, "command", side_effect=recording):
            result = self.module.git_with_gh_auth(["--version"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("credential.helper=!gh auth git-credential", captured[0][0])
        self.assertFalse(any("TOKEN" in item or "secret" in item for item in captured[0][0]))
        self.assertNotIn("GH_TOKEN", captured[0][1]["env"])

    def test_check_config_executes_real_auth_status_checks_via_safe_commands(self) -> None:
        seen: list[tuple[str, ...]] = []

        def fake_success(argv):
            seen.append(tuple(argv))
            return True

        with mock.patch.object(self.module, "materialize_harness", return_value=self.module.load_lock()), \
             mock.patch.object(self.module.shutil, "which", return_value="/usr/bin/fake"), \
             mock.patch.object(self.module, "successful_check", side_effect=fake_success):
            combined, code = self.module.execute(self.module.build_parser().parse_args(["check-config"]))
        self.assertEqual(code, 0)
        checks = combined["runner_result"]["checks"]
        self.assertTrue(checks["gh_auth"])
        self.assertTrue(checks["private_harness_access"])
        self.assertTrue(checks["agent_auth"])
        self.assertIn(("gh", "auth", "status"), seen)
        self.assertIn(("agent", "status"), seen)

    def test_policy_strictly_rejects_types_duplicates_regex_and_capabilities(self) -> None:
        baseline = json.loads(self.policy.read_text())
        mutations = (
            ("boolean timeout", lambda p: p.update(default_timeout_seconds=True)),
            ("duplicate environment", lambda p: p["inherited_environment_keys"].append("HOME")),
            ("bad regex", lambda p: p.update(sensitive_path_patterns=["("])),
            ("bad capability", lambda p: p.update(capability_environment={"Bad Name": ["PATH"]})),
            ("duplicate command", lambda p: p.update(guarded_commands=["git push", "git push"])),
            ("relative root", lambda p: p.update(allowed_target_roots=["relative"])),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                candidate = json.loads(json.dumps(baseline))
                mutate(candidate)
                self.policy.write_text(json.dumps(candidate))
                with self.assertRaises(self.module.AdapterError):
                    self.module.load_policy()
        duplicate_field = json.dumps(baseline)[:-1] + ',"schema_version":2}'
        self.policy.write_text(duplicate_field)
        with self.assertRaisesRegex(self.module.AdapterError, "duplicate field"):
            self.module.load_policy()
        self.policy.write_text(json.dumps(baseline))

    def test_cli_contract_errors_are_one_combined_json_object(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ADAPTER_SOURCE), "unknown-command"],
            env={**os.environ, **self.env},
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(len([line for line in result.stdout.splitlines() if line]), 1)
        value = json.loads(result.stdout)
        self.assertEqual(value["harness_revision"], self.sha)
        self.assertIn("error", value["runner_result"])
        invalid_model = subprocess.run(
            [
                sys.executable, str(ADAPTER_SOURCE), "run", "--target", "x",
                "--prompt", "x", "--implement-model", "bad model",
            ],
            env={**os.environ, **self.env},
            text=True,
            capture_output=True,
        )
        self.assertEqual(invalid_model.returncode, 2)
        self.assertEqual(len([line for line in invalid_model.stdout.splitlines() if line]), 1)
        self.assertIsInstance(json.loads(invalid_model.stdout), dict)

        policy = json.loads(self.policy.read_text())
        policy["capability_environment"] = []
        self.policy.write_text(json.dumps(policy))
        malformed = subprocess.run(
            [sys.executable, str(ADAPTER_SOURCE), "check-config"],
            env={**os.environ, **self.env},
            text=True,
            capture_output=True,
        )
        self.assertEqual(malformed.returncode, 2)
        self.assertEqual(len([line for line in malformed.stdout.splitlines() if line]), 1)
        self.assertIsInstance(json.loads(malformed.stdout), dict)

    def test_foreground_signal_is_forwarded_to_runner_group(self) -> None:
        # Exercise delegate's process-group forwarding using the fake runner's
        # dedicated sleep command, which is equivalent to a blocking subcommand.
        with mock.patch.object(self.module, "materialize_harness", return_value=self.module.load_lock()):
            process = subprocess.Popen(
                [
                    sys.executable, "-c",
                    (
                        "import importlib.util,os;"
                        f"os.environ.update({self.env!r});"
                        f"s=importlib.util.spec_from_file_location('a',{str(ADAPTER_SOURCE)!r});"
                        "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
                        "r,c=m.delegate('sleep',[]);m.emit(r);raise SystemExit(c)"
                    ),
                ],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            time.sleep(0.4)
            process.send_signal(signal.SIGTERM)
            stdout, _ = process.communicate(timeout=5)
        value = json.loads(stdout)
        self.assertEqual(value["runner_result"]["signal"], signal.SIGTERM)
        self.assertEqual(len([line for line in stdout.splitlines() if line]), 1)


if __name__ == "__main__":
    unittest.main()
