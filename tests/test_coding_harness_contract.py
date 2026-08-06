from __future__ import annotations

import hashlib
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
if sys.argv[1:2] == ["contract"]:
    print(json.dumps({"contract_version": 2, "schema_version": 2}))
elif sys.argv[1:2] == ["sleep"]:
    def stop(signum, frame):
        print(json.dumps({"signal": signum}))
        raise SystemExit(130)
    signal.signal(signal.SIGTERM, stop)
    time.sleep(30)
elif sys.argv[1:2] == ["validate-plan"]:
    plan_path = sys.argv[sys.argv.index("--plan") + 1]
    with open(plan_path, encoding="utf-8") as stream:
        normalized = json.load(stream)
    print(json.dumps({
        "schema_version": 2,
        "normalized_spec": normalized,
        "spec_sha256": "runner-owned-digest",
        "argv": sys.argv[1:],
    }))
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
        git("commit", "-qm", "fake harness", cwd=self.harness)
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
            "capability_environment": {
                "browser": ["PLAYWRIGHT_CLI_BIN"],
            },
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

    def make_finalization_fixture(self, plan_id: str = "plan-1") -> dict:
        target = self.workspace / "runtime/repos" / f"acme--delivery-{plan_id}"
        target.mkdir(parents=True)
        git("init", "-q", "-b", "main", cwd=target)
        git("config", "user.name", "Test", cwd=target)
        git("config", "user.email", "test@example.invalid", cwd=target)
        (target / "file.txt").write_text("baseline\n", encoding="utf-8")
        git("add", ".", cwd=target)
        git("commit", "-qm", "baseline", cwd=target)
        remote = self.root / f"delivery-{plan_id}.git"
        git("init", "--bare", "-q", str(remote))
        git("remote", "add", "origin", str(remote), cwd=target)
        git("push", "-qu", "origin", "main", cwd=target)
        initial = self.module.git_checkpoint(target)
        git("switch", "-qc", f"agent/{plan_id}", cwd=target)
        (target / "file.txt").write_text("delivered\n", encoding="utf-8")
        final = self.module.git_checkpoint(target)

        record_dir = self.workspace / "runtime/coding-harness-runs" / plan_id
        phase_dir = record_dir / "phase-1"
        phase_dir.mkdir(parents=True)
        identity = {
            "root": str(target.resolve()),
            "common_dir": str(Path(git("rev-parse", "--git-common-dir", cwd=target)).resolve()),
            "object_dir": str(Path(git("rev-parse", "--git-path", "objects", cwd=target)).resolve()),
        }
        # Resolve relative Git paths the same way as the adapter.
        for key, argv in (
            ("common_dir", ("rev-parse", "--git-common-dir")),
            ("object_dir", ("rev-parse", "--git-path", "objects")),
        ):
            value = Path(git(*argv, cwd=target))
            identity[key] = str((target / value).resolve() if not value.is_absolute() else value.resolve())
        result = {"run_id": f"{plan_id}/phase-1", "phase_id": "phase-1", "gate": "green"}
        spec = {
            "schema_version": 2,
            "phases": [{"id": "phase-1", "slug": "phase-1"}],
        }
        plan = {
            "schema_version": 2,
            "plan_id": plan_id,
            "target": str(target.resolve()),
            "source_spec": str(self.workspace / "runtime/coding-harness-plans/plan.json"),
            "spec_sha256": self.module.canonical_json_sha256(spec),
            "models": {"implement": None, "plan": None, "review": None, "fix": None},
            "state": "green",
            "gate": "green",
            "total_phases": 1,
            "scheduled": [result],
            "completed_phases": 1,
            "created_at": "2026-01-01T00:00:00Z",
        }
        (record_dir / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
        status = {
            "run_id": result["run_id"],
            "plan_id": plan_id,
            "phase_id": "phase-1",
            "target": str(target.resolve()),
            "spec_sha256": plan["spec_sha256"],
            "state": "green",
            "gate": "green",
        }
        (record_dir / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        (record_dir / "target.json").write_text(json.dumps({
            "schema_version": 2,
            **identity,
            "initial_baseline": initial,
        }), encoding="utf-8")
        (phase_dir / "checkpoint.json").write_text(json.dumps({
            "schema_version": 2,
            "stage": "green",
            "git": final,
        }), encoding="utf-8")

        def shown(record_id: str) -> dict:
            if record_id == plan_id:
                return {"kind": "plan", "record_dir": str(record_dir), "plan": plan}
            if record_id == result["run_id"]:
                return {
                    "kind": "run",
                    "record_dir": str(phase_dir),
                    "status": status,
                    "artifacts": ["checkpoint.json"],
                    "handoff": None,
                }
            raise AssertionError(f"unexpected show: {record_id}")

        return {
            "target": target,
            "remote": remote,
            "initial": initial,
            "final": final,
            "plan": plan,
            "spec": spec,
            "status": status,
            "record_dir": record_dir,
            "phase_dir": phase_dir,
            "shown": shown,
        }

    def finalize_fixture(self, fixture: dict, **kwargs):
        calls: list[list[str]] = []
        remote_value = kwargs.get("remote_oid", fixture["initial"]["head_oid"])
        with mock.patch.object(self.module, "show_record", side_effect=fixture["shown"]), \
             mock.patch.object(self.module, "validated_origin", return_value="https://github.com/acme/delivery.git"), \
             mock.patch.object(
                 self.module,
                 "remote_oid",
                 side_effect=remote_value if callable(remote_value) else None,
                 return_value=None if callable(remote_value) else remote_value,
             ), \
             mock.patch.object(
                 self.module,
                 "finalization_git_with_auth",
                 side_effect=lambda args, check=True: self.safe_temp_auth(fixture, calls, args, check),
             ):
            return self.module.finalize_plan(
                fixture["plan"]["plan_id"],
                kwargs.get("message", "Deliver approved plan"),
                kwargs.get("approve_commit", True),
                kwargs.get("approve_push", True),
            )

    def safe_temp_auth(self, fixture: dict, calls: list[list[str]], args: list[str], check: bool):
        calls.append(args)
        if "push" not in args:
            raise AssertionError(f"unexpected authenticated Git call: {args}")
        refspec = args[-1]
        return subprocess.run(
            [
                "git", "-C", str(fixture["target"]), "push", "--no-follow-tags",
                str(fixture["remote"]), refspec,
            ],
            text=True,
            capture_output=True,
            check=check,
        )

    def set_plan_shape(
        self,
        fixture: dict,
        *,
        spec_ids: list[str],
        scheduled_ids: list[str],
        skipped_ids: list[str] | None = None,
    ) -> None:
        skipped = skipped_ids or []
        spec = {
            "schema_version": 2,
            "phases": [{"id": phase_id, "slug": phase_id} for phase_id in spec_ids],
        }
        plan = fixture["plan"]
        plan["spec_sha256"] = self.module.canonical_json_sha256(spec)
        plan["total_phases"] = len(spec_ids)
        plan["scheduled"] = [
            {
                "run_id": f"{plan['plan_id']}/{phase_id}",
                "phase_id": phase_id,
                "gate": "green",
            }
            for phase_id in scheduled_ids
        ]
        plan["completed_phases"] = len(scheduled_ids)
        if skipped:
            plan["skipped_green_phases"] = skipped
            plan["continued_from_plan_id"] = "prior-plan"
        else:
            plan.pop("skipped_green_phases", None)
            plan.pop("continued_from_plan_id", None)
        fixture["spec"] = spec
        (fixture["record_dir"] / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
        (fixture["record_dir"] / "plan.json").write_text(json.dumps(plan), encoding="utf-8")

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
        with mock.patch.dict(
            os.environ,
            {
                **self.env,
                "OPENROUTER_API_KEY": "secret",
                "PLAYWRIGHT_CLI_BIN": "/runtime/playwright-cli",
                "LANG": "C",
            },
            clear=False,
        ):
            combined, code = self.module.delegate(
                "resume",
                ["record-1", "--restart-current-stage", "--implement-model", "model-x"],
            )
        self.assertEqual(code, 0)
        self.assertEqual(combined["harness_revision"], self.sha)
        result = combined["runner_result"]
        self.assertNotIn("OPENROUTER_API_KEY", result["env"])
        self.assertEqual(
            result["env"]["PLAYWRIGHT_CLI_BIN"], "/runtime/playwright-cli"
        )
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
            "--strip-completed", "prior-plan",
        ])
        combined, code = self.module.execute(plan_args)
        self.assertEqual(code, 0)
        argv = combined["runner_result"]["argv"]
        self.assertEqual(argv[argv.index("--timeout") + 1], "3000")
        self.assertEqual(Path(argv[argv.index("--plan") + 1]), plan.resolve())
        self.assertEqual(argv[argv.index("--strip-completed") + 1], "prior-plan")
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

    def test_preflight_delegates_normalization_policy_timeout_and_review_flags(self) -> None:
        plan = self.workspace / "runtime/coding-harness-plans/preflight.json"
        plan.parent.mkdir(parents=True)
        raw = {
            "schema_version": 2,
            "phases": [{"id": "phase-1", "prompt": "Do not commit or push"}],
        }
        plan.write_text(json.dumps(raw), encoding="utf-8")
        self.module.INVOCATION_CWD = self.workspace
        args = self.module.build_parser().parse_args([
            "preflight-plan",
            "--plan", "runtime/coding-harness-plans/preflight.json",
            "--no-review",
            "--review-threshold", "high",
            "--review-max-rounds", "4",
        ])
        combined, code = self.module.execute(args)
        self.assertEqual(code, 0)
        result = combined["runner_result"]
        self.assertEqual(result["normalized_spec"], raw)
        self.assertEqual(result["spec_sha256"], "runner-owned-digest")
        argv = result["argv"]
        self.assertEqual(Path(argv[argv.index("--plan") + 1]), plan.resolve())
        self.assertEqual(argv[argv.index("--timeout") + 1], "3000")
        self.assertIn("--no-review", argv)
        self.assertEqual(argv[argv.index("--review-threshold") + 1], "high")
        self.assertEqual(argv[argv.index("--review-max-rounds") + 1], "4")
        self.assertIn("--policy", argv)

    def test_preflight_enforces_plan_path_errors_before_delegation(self) -> None:
        plans = self.workspace / "runtime/coding-harness-plans"
        plans.mkdir(parents=True)
        outside = self.root / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        link = plans / "link.json"
        link.symlink_to(outside)
        for value, error in ((str(outside), "beneath"), (str(link), "symlink"), (str(plans), "regular")):
            with self.subTest(value=value), self.assertRaisesRegex(self.module.AdapterError, error):
                args = self.module.build_parser().parse_args(["preflight-plan", "--plan", value])
                self.module.execute(args)

    def test_finalize_plan_success_uses_authenticated_non_force_push(self) -> None:
        fixture = self.make_finalization_fixture()
        calls: list[list[str]] = []

        with mock.patch.object(self.module, "show_record", side_effect=fixture["shown"]), \
             mock.patch.object(self.module, "validated_origin", return_value="https://github.com/acme/delivery.git"), \
             mock.patch.object(self.module, "remote_oid", return_value=fixture["initial"]["head_oid"]), \
             mock.patch.object(
                 self.module,
                 "finalization_git_with_auth",
                 side_effect=lambda args, check=True: self.safe_temp_auth(fixture, calls, args, check),
             ):
            result = self.module.finalize_plan(
                "plan-1", "Deliver approved plan", True, True
            )
        self.assertTrue(result["partial_state"]["pushed"])
        self.assertEqual(git("branch", "--show-current", cwd=fixture["target"]), "main")
        self.assertEqual(git("status", "--porcelain", cwd=fixture["target"]), "")
        self.assertEqual(
            git("--git-dir", str(fixture["remote"]), "rev-parse", "refs/heads/main"),
            result["commit_oid"],
        )
        push = next(call for call in calls if "push" in call)
        self.assertEqual(push[-4:], [
            "push", "--no-follow-tags", "https://github.com/acme/delivery.git",
            "refs/heads/main:refs/heads/main",
        ])
        self.assertFalse(any("force" in arg for arg in push))

    def test_git_checkpoint_matches_runner_config_digest_contract(self) -> None:
        fixture = self.make_finalization_fixture("plan-runner-config-contract")
        config = subprocess.run(
            [
                "git", "-C", str(fixture["target"]),
                "config", "--local", "--list", "--show-origin",
            ],
            check=True,
            capture_output=True,
            env=self.module.finalization_git_environment(),
        ).stdout

        checkpoint = self.module.git_checkpoint(fixture["target"])

        self.assertEqual(
            checkpoint["config_sha256"],
            hashlib.sha256(config).hexdigest(),
        )

    def test_finalize_rejects_missing_message_and_approvals(self) -> None:
        fixture = self.make_finalization_fixture()
        cases = (
            ({"message": ""}, "message"),
            ({"approve_commit": False}, "approve-commit"),
            ({"approve_push": False}, "approve-push"),
        )
        for kwargs, error in cases:
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(self.module.FinalizationError, error):
                self.finalize_fixture(fixture, **kwargs)

    def test_finalize_rejects_red_dry_no_op_active_and_incomplete_plans(self) -> None:
        mutations = {
            "red": lambda plan: plan.update(state="red", gate="red"),
            "dry": lambda plan: plan.update(state="dry-run", gate="dry-run"),
            "no-op": lambda plan: plan.update(no_op=True),
            "active": lambda plan: plan.update(active_run_id=f"{plan['plan_id']}/phase-1"),
            "incomplete": lambda plan: plan.update(total_phases=2),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                fixture = self.make_finalization_fixture(f"plan-{label}")
                mutate(fixture["plan"])
                (fixture["record_dir"] / "plan.json").write_text(
                    json.dumps(fixture["plan"]), encoding="utf-8"
                )
                with self.assertRaises(self.module.FinalizationError):
                    self.finalize_fixture(fixture)

    def test_finalize_binds_plan_results_to_canonical_spec_order(self) -> None:
        cases = {
            "duplicate": (["one", "two"], ["one", "one"], []),
            "reordered": (["one", "two"], ["two", "one"], []),
            "substituted": (["one", "two"], ["one", "other"], []),
            "non-prefix skipped": (["one", "two"], ["one"], ["two"]),
        }
        for label, (spec_ids, scheduled_ids, skipped_ids) in cases.items():
            with self.subTest(label=label):
                fixture = self.make_finalization_fixture(f"plan-shape-{label.replace(' ', '-')}")
                self.set_plan_shape(
                    fixture,
                    spec_ids=spec_ids,
                    scheduled_ids=scheduled_ids,
                    skipped_ids=skipped_ids,
                )
                with self.assertRaisesRegex(
                    self.module.FinalizationError,
                    "canonical spec suffix|exact canonical spec prefix",
                ):
                    self.finalize_fixture(fixture)

    def test_skipped_provenance_compares_complete_normalized_phase_objects(self) -> None:
        base = {
            "id": "one",
            "slug": "one",
            "prompt": "original",
            "verification": [{"argv": ["python3", "-m", "unittest"]}],
            "capabilities": ["browser"],
        }
        mutations = {
            "prompt": {**base, "prompt": "changed"},
            "verification": {**base, "verification": [{"argv": ["python3", "-V"]}]},
            "capability": {**base, "capabilities": ["aws"]},
        }
        for label, current_phase in mutations.items():
            with self.subTest(label=label):
                prior_id = f"prior-{label}"
                prior_dir = self.workspace / "runtime/coding-harness-runs" / prior_id
                prior_dir.mkdir(parents=True)
                spec = {"schema_version": 2, "phases": [base]}
                plan = {
                    "plan_id": prior_id,
                    "target": "/safe/target",
                    "spec_sha256": self.module.canonical_json_sha256(spec),
                    "total_phases": 1,
                    "scheduled": [{
                        "run_id": f"{prior_id}/one",
                        "phase_id": "one",
                        "gate": "green",
                    }],
                }
                (prior_dir / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
                shown = {"kind": "plan", "record_dir": str(prior_dir), "plan": plan}
                with mock.patch.object(self.module, "show_record", return_value=shown), \
                     self.assertRaisesRegex(self.module.AdapterError, "phase definitions"):
                    self.module.validate_skipped_prefix(
                        {"continued_from_plan_id": prior_id},
                        [current_phase],
                        target=Path("/safe/target"),
                        seen={"current"},
                    )

    def test_finalize_rejects_tampered_or_symlinked_canonical_spec(self) -> None:
        tampered = self.make_finalization_fixture("plan-spec-digest")
        spec = dict(tampered["spec"])
        spec["phases"] = [{"id": "other", "slug": "other"}]
        (tampered["record_dir"] / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
        with self.assertRaisesRegex(self.module.FinalizationError, "digest"):
            self.finalize_fixture(tampered)

        linked = self.make_finalization_fixture("plan-spec-link")
        spec_path = linked["record_dir"] / "spec.json"
        outside = self.root / "outside-spec.json"
        outside.write_bytes(spec_path.read_bytes())
        spec_path.unlink()
        spec_path.symlink_to(outside)
        with self.assertRaisesRegex(self.module.FinalizationError, "safely read|symlink"):
            self.finalize_fixture(linked)

        ancestor = self.make_finalization_fixture("plan-record-ancestor-link")
        original = ancestor["record_dir"]
        relocated = self.root / "relocated-record"
        original.rename(relocated)
        original.symlink_to(relocated, target_is_directory=True)
        with self.assertRaisesRegex(self.module.FinalizationError, "safely open record"):
            self.finalize_fixture(ancestor)

    def test_finalize_rejects_baseline_branch_head_config_ref_and_tree_drift(self) -> None:
        cases = ("baseline-dirt", "branch", "head", "config", "ref", "tree")
        for case in cases:
            with self.subTest(case=case):
                fixture = self.make_finalization_fixture(f"plan-{case}")
                target = fixture["target"]
                if case == "baseline-dirt":
                    target_record_path = fixture["record_dir"] / "target.json"
                    target_record = json.loads(target_record_path.read_text())
                    target_record["initial_baseline"]["tree_oid"] = "0" * 40
                    target_record_path.write_text(json.dumps(target_record), encoding="utf-8")
                elif case == "branch":
                    git("branch", "-m", "agent/wrong", cwd=target)
                elif case == "head":
                    git("commit", "--allow-empty", "-qm", "drift", cwd=target)
                elif case == "config":
                    git("config", "test.drift", "yes", cwd=target)
                elif case == "ref":
                    git("branch", "unexpected", cwd=target)
                else:
                    (target / "file.txt").write_text("tree drift\n", encoding="utf-8")
                with self.assertRaises(self.module.FinalizationError):
                    self.finalize_fixture(fixture)

    def test_finalize_rejects_local_and_remote_default_branch_drift(self) -> None:
        local = self.make_finalization_fixture("plan-local-drift")
        drift = git("commit-tree", local["initial"]["tree_oid"], "-p", local["initial"]["head_oid"], "-m", "drift", cwd=local["target"])
        git("branch", "-f", "main", drift, cwd=local["target"])
        local["final"] = self.module.git_checkpoint(local["target"])
        checkpoint_path = local["phase_dir"] / "checkpoint.json"
        checkpoint = json.loads(checkpoint_path.read_text())
        checkpoint["git"] = local["final"]
        checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
        with self.assertRaisesRegex(self.module.FinalizationError, "local main drifted"):
            self.finalize_fixture(local)

        remote = self.make_finalization_fixture("plan-remote-drift")
        other = self.root / "other"
        git("clone", "-q", str(remote["remote"]), str(other))
        git("switch", "-q", "main", cwd=other)
        git("config", "user.name", "Test", cwd=other)
        git("config", "user.email", "test@example.invalid", cwd=other)
        (other / "remote.txt").write_text("drift\n", encoding="utf-8")
        git("add", ".", cwd=other)
        git("commit", "-qm", "remote drift", cwd=other)
        git("push", "-q", "origin", "main", cwd=other)
        with self.assertRaisesRegex(self.module.FinalizationError, "remote main drifted"):
            self.finalize_fixture(remote, remote_oid="b" * 40)

    def test_finalize_rejects_staged_tree_mismatch(self) -> None:
        fixture = self.make_finalization_fixture()
        original = self.module.finalization_git_output

        def mismatch(repo, *args):
            if args == ("write-tree",):
                return "0" * 40
            return original(repo, *args)

        with mock.patch.object(self.module, "show_record", side_effect=fixture["shown"]), \
             mock.patch.object(self.module, "finalization_git_output", side_effect=mismatch), \
             mock.patch.object(self.module, "validated_origin", return_value="https://github.com/acme/delivery.git"), \
             mock.patch.object(self.module, "remote_oid", return_value=fixture["initial"]["head_oid"]), \
             self.assertRaisesRegex(self.module.FinalizationError, "staged tree"):
            self.module.finalize_plan("plan-1", "Deliver", True, True)

    def test_finalize_reports_commit_hook_failure_and_changes_without_rollback(self) -> None:
        failed = self.make_finalization_fixture("plan-hook-fail")
        hooks = failed["target"] / ".git/hooks"
        hook = hooks / "pre-commit"
        hook.write_text("#!/bin/sh\necho 'pre-commit hook failure' >&2\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)
        with self.assertRaisesRegex(self.module.FinalizationError, "pre-commit") as caught:
            self.finalize_fixture(failed)
        self.assertTrue(caught.exception.partial_state["staged"])
        self.assertFalse(caught.exception.partial_state["commit_created"])
        self.assertEqual(git("branch", "--show-current", cwd=failed["target"]), "agent/plan-hook-fail")

        changed = self.make_finalization_fixture("plan-hook-change")
        hook = changed["target"] / ".git/hooks/pre-commit"
        hook.write_text(
            "#!/bin/sh\nprintf 'hook\\n' > hook.txt\ngit add hook.txt\n",
            encoding="utf-8",
        )
        hook.chmod(0o755)
        with self.assertRaisesRegex(self.module.FinalizationError, "hook changed") as caught:
            self.finalize_fixture(changed)
        self.assertTrue(caught.exception.partial_state["commit_created"])
        self.assertFalse(caught.exception.partial_state["local_default_fast_forwarded"])
        self.assertEqual(git("branch", "--show-current", cwd=changed["target"]), "agent/plan-hook-change")

    def test_finalize_rejects_hook_config_refs_branch_remote_and_checkout_mutations(self) -> None:
        hooks = {
            "config": "git config hook.changed yes\n",
            "extra-ref": "git branch hook-extra\n",
            "branch": "git symbolic-ref HEAD refs/heads/hook-branch\n",
            "remote": "git remote set-url origin https://github.com/evil/repo.git\n",
        }
        for label, body in hooks.items():
            with self.subTest(label=label):
                fixture = self.make_finalization_fixture(f"plan-hook-{label}")
                hook = fixture["target"] / ".git/hooks/pre-commit"
                hook.write_text(f"#!/bin/sh\n{body}", encoding="utf-8")
                hook.chmod(0o755)
                with self.assertRaises(self.module.FinalizationError):
                    self.finalize_fixture(fixture)

        checkout = self.make_finalization_fixture("plan-checkout-hook")
        hook = checkout["target"] / ".git/hooks/post-checkout"
        hook.write_text("#!/bin/sh\nprintf hook > checkout-hook.txt\n", encoding="utf-8")
        hook.chmod(0o755)
        with self.assertRaisesRegex(self.module.FinalizationError, "checkout/merge hook"):
            self.finalize_fixture(checkout)

        merge = self.make_finalization_fixture("plan-merge-hook")
        hook = merge["target"] / ".git/hooks/post-merge"
        hook.write_text("#!/bin/sh\ngit branch merge-hook-ref\n", encoding="utf-8")
        hook.chmod(0o755)
        with self.assertRaisesRegex(self.module.FinalizationError, "checkout/merge hook"):
            self.finalize_fixture(merge)

    def test_finalize_rejects_disabled_hooks_and_accepts_valid_in_repo_hooks_path(self) -> None:
        disabled = self.make_finalization_fixture("plan-hooks-disabled")
        git("config", "core.hooksPath", "/dev/null", cwd=disabled["target"])
        disabled["final"] = self.module.git_checkpoint(disabled["target"])
        checkpoint_path = disabled["phase_dir"] / "checkpoint.json"
        checkpoint = json.loads(checkpoint_path.read_text())
        checkpoint["git"] = disabled["final"]
        checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
        with self.assertRaisesRegex(self.module.FinalizationError, "hooksPath"):
            self.finalize_fixture(disabled)

        valid = self.make_finalization_fixture("plan-hooks-valid")
        hook_dir = valid["target"] / ".githooks"
        hook_dir.mkdir()
        git("config", "core.hooksPath", ".githooks", cwd=valid["target"])
        valid["final"] = self.module.git_checkpoint(valid["target"])
        checkpoint_path = valid["phase_dir"] / "checkpoint.json"
        checkpoint = json.loads(checkpoint_path.read_text())
        checkpoint["git"] = valid["final"]
        checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
        result = self.finalize_fixture(valid)
        self.assertTrue(result["partial_state"]["pushed"])

    def test_worktree_scope_config_is_hashed_and_hook_mutations_fail_closed(self) -> None:
        mutations = {
            "hooks-path": "git config --worktree core.hooksPath /dev/null\n",
            "url-rewrite": (
                "git config --worktree "
                "url.https://evil.example/.insteadOf https://github.com/\n"
            ),
        }
        for label, body in mutations.items():
            with self.subTest(label=label):
                fixture = self.make_finalization_fixture(f"plan-worktree-{label}")
                target = fixture["target"]
                git("config", "extensions.worktreeConfig", "true", cwd=target)
                git("config", "--worktree", "core.hooksPath", ".git/hooks", cwd=target)
                fixture["final"] = self.module.git_checkpoint(target)
                checkpoint_path = fixture["phase_dir"] / "checkpoint.json"
                checkpoint = json.loads(checkpoint_path.read_text())
                checkpoint["git"] = fixture["final"]
                checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
                hook = target / ".git/hooks/pre-commit"
                hook.write_text(f"#!/bin/sh\n{body}", encoding="utf-8")
                hook.chmod(0o755)
                with self.assertRaisesRegex(
                    self.module.FinalizationError,
                    "config|hooksPath|URL rewrite",
                ) as caught:
                    self.finalize_fixture(fixture)
                self.assertTrue(caught.exception.partial_state["commit_created"])
                self.assertFalse(caught.exception.partial_state["pushed"])

    def test_origin_validation_rejects_paths_and_divergent_pushurl(self) -> None:
        fixture = self.make_finalization_fixture("plan-origin")
        with self.assertRaisesRegex(self.module.AdapterError, "canonical GitHub"):
            self.module.validated_origin(fixture["target"])
        git(
            "remote", "set-url", "origin", "https://github.com/acme/repo.git",
            cwd=fixture["target"],
        )
        git(
            "remote", "set-url", "--add", "--push", "origin",
            "https://github.com/other/repo.git",
            cwd=fixture["target"],
        )
        with self.assertRaisesRegex(self.module.AdapterError, "pushurl"):
            self.module.validated_origin(fixture["target"])

    def test_finalization_git_environment_ignores_global_and_system_rewrites(self) -> None:
        fixture = self.make_finalization_fixture("plan-global-config")
        git(
            "remote", "set-url", "origin", "https://github.com/acme/repo.git",
            cwd=fixture["target"],
        )
        global_config = self.root / "global.gitconfig"
        global_config.write_text(
            "[url \"https://evil.example/\"]\n"
            "\tinsteadOf = https://github.com/\n"
            "[push]\n\tfollowTags = true\n",
            encoding="utf-8",
        )
        system_config = self.root / "system.gitconfig"
        system_config.write_text(
            "[url \"https://system-evil.example/\"]\n"
            "\tpushInsteadOf = https://github.com/\n",
            encoding="utf-8",
        )
        with mock.patch.dict(os.environ, {
            "GIT_CONFIG_GLOBAL": str(global_config),
            "GIT_CONFIG_SYSTEM": str(system_config),
        }, clear=False):
            env = self.module.finalization_git_environment()
            self.assertEqual(env["GIT_CONFIG_GLOBAL"], os.devnull)
            self.assertEqual(env["GIT_CONFIG_NOSYSTEM"], "1")
            self.assertNotIn("GIT_CONFIG_SYSTEM", env)
            self.assertEqual(
                self.module.validated_origin(fixture["target"]),
                "https://github.com/acme/repo.git",
            )
            self.module.validate_safe_push_config(fixture["target"])

    def test_local_url_rewrites_and_push_broadening_are_rejected(self) -> None:
        cases = (
            ("url.https://evil.example/.insteadOf", "https://github.com/"),
            ("url.https://evil.example/.pushInsteadOf", "https://github.com/"),
            ("push.followTags", "true"),
            ("remote.origin.push", "refs/tags/*:refs/tags/*"),
            ("remote.origin.tagOpt", "--tags"),
        )
        for index, (key, value) in enumerate(cases):
            with self.subTest(key=key):
                fixture = self.make_finalization_fixture(f"plan-push-config-{index}")
                git("config", "--local", key, value, cwd=fixture["target"])
                with self.assertRaises(self.module.AdapterError):
                    self.module.validate_safe_push_config(fixture["target"])

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
