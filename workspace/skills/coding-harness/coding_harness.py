#!/usr/bin/env python3
"""Pinned, fail-closed adapter for the version-2 agent harness."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent
LOCK_PATH = Path(os.environ.get("MIRA_HARNESS_LOCK", SKILL_DIR / "harness.lock.json"))
POLICY_PATH = Path(os.environ.get("MIRA_HARNESS_POLICY", SKILL_DIR / "policy.json"))
WORKSPACE = Path(os.environ.get("OPENCLAW_WORKSPACE", "/home/node/.openclaw/workspace")).resolve()
INVOCATION_CWD = Path.cwd().resolve()
RUNTIME = WORKSPACE / "runtime"
RUNTIME_REPOS = RUNTIME / "repos"
HARNESS_DIR = RUNTIME_REPOS / "agent"
RUNS_DIR = RUNTIME / "coding-harness-runs"
PLANS_DIR = RUNTIME / "coding-harness-plans"
INSTALL_LOCK = RUNTIME_REPOS / ".agent.install.lock"
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$")
ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
BRANCH_RE = re.compile(r"^(?![./])(?!.*(?:\.\.|//|@\{|\\))(?!.*[/.]$)[A-Za-z0-9._/-]+$")
POLICY_FIELDS = {
    "schema_version", "allowed_target_roots", "inherited_environment_keys",
    "capability_environment", "sensitive_path_patterns", "default_timeout_seconds",
    "cancellation_grace_seconds", "allow_shell_verification", "default_branches",
    "guarded_commands",
}
ADAPTER_POLICY_FIELDS = {"contract_version", "runtime_repos", "runs_dir", "denied_roots"}
RUNNER_POLICY_PATH = RUNTIME / ".coding-harness-runner-policy-v2.json"


class AdapterError(RuntimeError):
    pass


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise AdapterError(message)


def strict_json(text: str, context: str) -> Any:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, child in pairs:
            if key in result:
                raise AdapterError(f"{context} contains duplicate field {key!r}")
            result[key] = child
        return result

    try:
        return json.loads(text, object_pairs_hook=object_pairs)
    except json.JSONDecodeError as exc:
        raise AdapterError(f"invalid {context} JSON: {exc}") from exc


def command(
    argv: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, env=env, text=True, capture_output=True, check=check)


def emit(value: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def canonical_url(value: str) -> str:
    value = value.strip().rstrip("/")
    ssh = re.fullmatch(r"git@github\.com:([^/]+)/([^/]+?)(?:\.git)?", value, re.I)
    https = re.fullmatch(r"https://github\.com/([^/]+)/([^/]+?)(?:\.git)?", value, re.I)
    slug = re.fullmatch(r"([^/]+)/([^/]+)", value)
    match = ssh or https or slug
    if not match:
        raise AdapterError("repository must be a canonical GitHub URL or owner/repo slug")
    owner, repo = match.groups()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]+", repo):
        raise AdapterError("repository owner/name contains unsupported characters")
    return f"https://github.com/{owner.lower()}/{repo.lower()}.git"


def load_lock() -> dict[str, Any]:
    try:
        value = strict_json(LOCK_PATH.read_text(encoding="utf-8"), "harness lock")
    except OSError as exc:
        raise AdapterError(f"cannot load harness lock: {exc}") from exc
    if not isinstance(value, dict) or set(value) != {"repository", "revision", "contract_version"}:
        raise AdapterError("harness lock must contain only repository, revision, and contract_version")
    if type(value["contract_version"]) is not int or value["contract_version"] != 2:
        raise AdapterError("harness lock contract_version must be 2")
    revision = value["revision"]
    if not isinstance(revision, str) or not REVISION_RE.fullmatch(revision):
        raise AdapterError("harness revision must be a full lowercase 40-character SHA")
    if not isinstance(value["repository"], str):
        raise AdapterError("harness repository must be a string")
    value["repository"] = canonical_url(value["repository"])
    return value


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    try:
        value = strict_json(path.read_text(encoding="utf-8"), "harness policy")
    except OSError as exc:
        raise AdapterError(f"cannot load harness policy: {exc}") from exc
    if not isinstance(value, dict) or set(value) != POLICY_FIELDS | {"adapter"}:
        raise AdapterError("harness policy has unknown fields")
    if type(value.get("schema_version")) is not int or value["schema_version"] != 2:
        raise AdapterError("harness policy schema_version must be 2")
    if type(value.get("default_timeout_seconds")) is not int or value["default_timeout_seconds"] != 3000:
        raise AdapterError("harness policy default_timeout_seconds must be 3000")
    grace = value.get("cancellation_grace_seconds")
    if isinstance(grace, bool) or not isinstance(grace, int) or grace < 1:
        raise AdapterError("harness policy cancellation grace must be a positive integer")
    def unique_strings(name: str, *, nonempty: bool = False) -> list[str]:
        items = value.get(name)
        if not isinstance(items, list) or (nonempty and not items) or not all(
            isinstance(item, str) and bool(item.strip()) for item in items
        ):
            raise AdapterError(f"harness policy {name} must be an array of non-empty strings")
        if len(items) != len(set(items)):
            raise AdapterError(f"harness policy {name} contains duplicates")
        return items

    inherited = unique_strings("inherited_environment_keys")
    if not all(ENV_KEY_RE.fullmatch(item) for item in inherited):
        raise AdapterError("harness policy environment allowlist contains an invalid key")
    patterns = unique_strings("sensitive_path_patterns")
    for pattern in patterns:
        try:
            re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            raise AdapterError(f"harness policy sensitive path regex is invalid: {exc}") from exc
    if type(value.get("allow_shell_verification")) is not bool:
        raise AdapterError("harness policy allow_shell_verification must be a boolean")
    branches = unique_strings("default_branches", nonempty=True)
    if not all(BRANCH_RE.fullmatch(item) for item in branches):
        raise AdapterError("harness policy default_branches contains an invalid branch")
    guarded = unique_strings("guarded_commands", nonempty=True)
    for item in guarded:
        try:
            words = shlex.split(item)
        except ValueError as exc:
            raise AdapterError(f"harness policy guarded command is invalid: {exc}") from exc
        if not words or any("\x00" in word for word in words):
            raise AdapterError("harness policy guarded command is invalid")
    capabilities = value.get("capability_environment")
    if not isinstance(capabilities, dict):
        raise AdapterError("harness policy capability_environment must be an object")
    for capability, keys in capabilities.items():
        if not isinstance(capability, str) or not CAPABILITY_RE.fullmatch(capability):
            raise AdapterError("harness policy capability name is invalid")
        if not isinstance(keys, list) or not all(
            isinstance(key, str) and ENV_KEY_RE.fullmatch(key) for key in keys
        ):
            raise AdapterError(f"harness policy capability {capability!r} keys are invalid")
        if len(keys) != len(set(keys)):
            raise AdapterError(f"harness policy capability {capability!r} keys contain duplicates")
    adapter = value.get("adapter")
    if not isinstance(adapter, dict) or set(adapter) != ADAPTER_POLICY_FIELDS:
        raise AdapterError("harness adapter policy fields are invalid")
    if type(adapter.get("contract_version")) is not int or adapter["contract_version"] != 2:
        raise AdapterError("harness adapter contract_version must be 2")
    for name in ("runtime_repos", "runs_dir"):
        if not isinstance(adapter.get(name), str) or not adapter[name].strip() or not Path(adapter[name]).is_absolute():
            raise AdapterError(f"harness adapter {name} must be an absolute path")
        if Path(adapter[name]).resolve() != Path(adapter[name]):
            raise AdapterError(f"harness adapter {name} must be canonical")
    denied = adapter.get("denied_roots")
    if not isinstance(denied, list) or not denied or not all(
        isinstance(item, str) and item.strip() and Path(item).is_absolute() for item in denied
    ):
        raise AdapterError("harness adapter denied_roots must contain absolute paths")
    if len(denied) != len(set(denied)):
        raise AdapterError("harness adapter denied_roots contains duplicates")
    if any(Path(item).resolve() != Path(item) for item in denied):
        raise AdapterError("harness adapter denied_roots must be canonical")
    roots = unique_strings("allowed_target_roots", nonempty=True)
    if not all(Path(item).is_absolute() for item in roots):
        raise AdapterError("harness policy allowed_target_roots must contain absolute paths")
    if any(Path(item).resolve() != Path(item) for item in roots):
        raise AdapterError("harness policy allowed_target_roots must be canonical")
    if len({str(Path(item).resolve()) for item in roots}) != len(roots):
        raise AdapterError("harness policy allowed_target_roots contains duplicate canonical paths")
    if Path(adapter["runtime_repos"]).resolve() != RUNTIME_REPOS:
        raise AdapterError("harness adapter runtime_repos does not match this workspace")
    if Path(adapter["runs_dir"]).resolve() != RUNS_DIR:
        raise AdapterError("harness adapter runs_dir does not match this workspace")
    return value


def materialize_runner_policy(policy: dict[str, Any]) -> Path:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    runner_policy = {key: value for key, value in policy.items() if key in POLICY_FIELDS}
    temporary = RUNNER_POLICY_PATH.with_name(f"{RUNNER_POLICY_PATH.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(runner_policy, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, RUNNER_POLICY_PATH)
    return RUNNER_POLICY_PATH


def git_output(repo: Path, *args: str) -> str:
    result = command(["git", "-C", str(repo), *args], check=False)
    if result.returncode:
        raise AdapterError((result.stderr or result.stdout).strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def verify_harness(lock: dict[str, Any]) -> None:
    if HARNESS_DIR.is_symlink() or not HARNESS_DIR.is_dir():
        raise AdapterError("harness checkout is missing or is a symlink")
    if canonical_url(git_output(HARNESS_DIR, "remote", "get-url", "origin")) != lock["repository"]:
        raise AdapterError("harness checkout origin does not match lock")
    if git_output(HARNESS_DIR, "rev-parse", "HEAD") != lock["revision"]:
        raise AdapterError("harness checkout HEAD does not match lock")
    symbolic = command(["git", "-C", str(HARNESS_DIR), "symbolic-ref", "-q", "HEAD"], check=False)
    if symbolic.returncode == 0:
        raise AdapterError("harness checkout HEAD must be detached")
    if git_output(HARNESS_DIR, "status", "--porcelain", "--untracked-files=normal"):
        raise AdapterError("harness checkout is not clean")
    runner = HARNESS_DIR / "scripts" / "agent_run.py"
    if runner.is_symlink() or not runner.is_file():
        raise AdapterError("pinned harness runner is missing or is a symlink")
    help_result = command([sys.executable, str(runner), "--help"], cwd=HARNESS_DIR, check=False)
    if help_result.returncode or "version-2" not in help_result.stdout:
        raise AdapterError("pinned harness is not contract-version 2 compatible")


def materialize_harness() -> dict[str, Any]:
    lock = load_lock()
    if has_symlink_component(RUNTIME_REPOS):
        raise AdapterError("runtime repository path contains a symlink component")
    RUNTIME_REPOS.mkdir(parents=True, exist_ok=True)
    if RUNTIME_REPOS.is_symlink():
        raise AdapterError("runtime repository root must not be a symlink")
    with INSTALL_LOCK.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        if not HARNESS_DIR.exists():
            temp = Path(tempfile.mkdtemp(prefix=".agent-install-", dir=RUNTIME_REPOS))
            try:
                git_with_gh_auth(["clone", "--no-checkout", lock["repository"], str(temp)])
                git_with_gh_auth(["-C", str(temp), "fetch", "--no-tags", "origin", lock["revision"]])
                command(["git", "-C", str(temp), "checkout", "--detach", lock["revision"]])
                os.replace(temp, HARNESS_DIR)
            finally:
                if temp.exists():
                    shutil.rmtree(temp)
        else:
            if HARNESS_DIR.is_symlink():
                raise AdapterError("harness checkout must not be a symlink")
            if canonical_url(git_output(HARNESS_DIR, "remote", "get-url", "origin")) != lock["repository"]:
                raise AdapterError("harness checkout origin does not match lock")
            if git_output(HARNESS_DIR, "status", "--porcelain", "--untracked-files=normal"):
                raise AdapterError("refusing to replace a dirty harness checkout")
            if git_output(HARNESS_DIR, "rev-parse", "HEAD") != lock["revision"]:
                fetch = git_with_gh_auth(
                    ["-C", str(HARNESS_DIR), "fetch", "--no-tags", "origin", lock["revision"]],
                    check=False,
                )
                if fetch.returncode:
                    raise AdapterError((fetch.stderr or fetch.stdout).strip())
            command(["git", "-C", str(HARNESS_DIR), "checkout", "--detach", lock["revision"]])
        verify_harness(lock)
    return lock


def has_symlink_component(path: Path) -> bool:
    current = Path(path.anchor) if path.is_absolute() else Path.cwd()
    for part in path.parts[1:] if path.is_absolute() else path.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def git_with_gh_auth(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return command(
        ["git", "-c", "credential.helper=!gh auth git-credential", *args],
        check=check,
        env=persistent_cli_environment(),
    )


def persistent_cli_environment() -> dict[str, str]:
    inherited = {
        key: os.environ[key]
        for key in ("HOME", "LANG", "LC_ALL", "LOGNAME", "PATH", "SHELL", "TERM", "TMPDIR", "TZ", "USER")
        if key in os.environ
    }
    inherited.update({
        "GIT_TERMINAL_PROMPT": "0",
        "GCM_INTERACTIVE": "never",
        "SSH_ASKPASS_REQUIRE": "never",
        "XDG_CONFIG_HOME": "/home/node/.openclaw",
        "GH_CONFIG_DIR": "/home/node/.openclaw/gh",
    })
    return inherited


def allowed_roots(policy: dict[str, Any]) -> list[Path]:
    return [Path(item).expanduser().resolve() for item in policy["allowed_target_roots"]]


def validate_target_root(root: Path, policy: dict[str, Any]) -> Path:
    root = root.resolve()
    runtime_repos = Path(policy["adapter"]["runtime_repos"]).expanduser().resolve()
    denied = [Path(item).expanduser().resolve() for item in policy["adapter"]["denied_roots"]]
    for denied_root in denied:
        if within(root, denied_root) and not within(root, runtime_repos):
            raise AdapterError(f"target is a denied Mira/OpenClaw/harness root: {root}")
    if within(root, HARNESS_DIR.resolve()):
        raise AdapterError(f"target is a denied Mira/OpenClaw/harness root: {root}")
    if not any(within(root, allowed) for allowed in allowed_roots(policy)):
        raise AdapterError(f"target is outside policy allowed roots: {root}")
    if root == WORKSPACE or (within(root, WORKSPACE) and not within(root, RUNTIME_REPOS.resolve())):
        raise AdapterError(f"target is a denied workspace/config root: {root}")
    return root


def parse_remote(target: str) -> tuple[str, str, str]:
    url = canonical_url(target)
    match = re.fullmatch(r"https://github\.com/([^/]+)/([^/]+)\.git", url)
    assert match
    owner, repo = match.groups()
    return url, owner, repo


def resolve_target(target: str, policy: dict[str, Any]) -> Path:
    raw_path = Path(target).expanduser()
    if raw_path.exists() or target.startswith(("/", ".", "~")):
        if not raw_path.exists():
            raise AdapterError(f"target path does not exist: {raw_path}")
        absolute = raw_path.absolute()
        if has_symlink_component(absolute):
            raise AdapterError("target path contains a symlink component")
        root_text = command(
            ["git", "-C", str(absolute), "rev-parse", "--show-toplevel"], check=False
        )
        if root_text.returncode:
            raise AdapterError("target path is not a Git repository")
        root = Path(root_text.stdout.strip())
        if has_symlink_component(root):
            raise AdapterError("canonical Git root contains a symlink component")
        return validate_target_root(root, policy)

    url, owner, repo = parse_remote(target)
    destination = RUNTIME_REPOS / f"{owner}--{repo}"
    if destination.exists():
        if destination.is_symlink():
            raise AdapterError("target checkout must not be a symlink")
        actual = canonical_url(git_output(destination, "remote", "get-url", "origin"))
        if actual != url:
            raise AdapterError("existing target checkout origin does not match requested repository")
    else:
        git_with_gh_auth(["clone", url, str(destination)])
    root = Path(git_output(destination, "rev-parse", "--show-toplevel"))
    return validate_target_root(root, policy)


def sanitized_environment(policy: dict[str, Any]) -> dict[str, str]:
    allowed = set(policy["inherited_environment_keys"])
    env = {key: value for key, value in os.environ.items() if key in allowed}
    env.update({
        "AGENT_RUN_HOME": str(RUNS_DIR),
        "GIT_TERMINAL_PROMPT": "0",
        "GCM_INTERACTIVE": "never",
        "SSH_ASKPASS_REQUIRE": "never",
        "XDG_CONFIG_HOME": "/home/node/.openclaw",
        "GH_CONFIG_DIR": "/home/node/.openclaw/gh",
    })
    return env


def delegate(subcommand: str, extra: list[str], policy_path: Path = POLICY_PATH) -> tuple[dict[str, Any], int]:
    lock = materialize_harness()
    policy = load_policy(policy_path)
    runner_policy_path = materialize_runner_policy(policy)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    runner = HARNESS_DIR / "scripts" / "agent_run.py"
    argv = [sys.executable, str(runner), subcommand, *extra]
    if subcommand in {"run", "run-plan", "resume", "cancel"} and "--policy" not in extra:
        argv += ["--policy", str(runner_policy_path)]
    process = subprocess.Popen(
        argv,
        cwd=HARNESS_DIR,
        env=sanitized_environment(policy),
        text=True,
        stdout=subprocess.PIPE,
        stderr=None,
        start_new_session=True,
    )
    previous: dict[int, Any] = {}

    def forward(signum: int, _frame: Any) -> None:
        try:
            os.killpg(process.pid, signum)
        except ProcessLookupError:
            pass

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.signal(signum, forward)
    try:
        stdout, _ = process.communicate()
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=policy["cancellation_grace_seconds"])
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
    lines = [line for line in stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise AdapterError("harness runner violated exactly-one-JSON output contract")
    try:
        result = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise AdapterError("harness runner returned invalid JSON") from exc
    if not isinstance(result, dict):
        raise AdapterError("harness runner result must be a JSON object")
    return {"harness_revision": lock["revision"], "runner_result": result}, process.returncode


def forwarding_flags(
    args: argparse.Namespace,
    *,
    default_timeout: int | None = None,
) -> list[str]:
    result: list[str] = []
    for attr, flag in (
        ("timeout", "--timeout"), ("review_threshold", "--review-threshold"),
        ("review_max_rounds", "--review-max-rounds"), ("implement_model", "--implement-model"),
        ("plan_model", "--plan-model"), ("review_model", "--review-model"), ("fix_model", "--fix-model"),
    ):
        value = getattr(args, attr, None)
        if value is not None:
            result += [flag, str(value)]
    if getattr(args, "no_review", False):
        result.append("--no-review")
    if getattr(args, "dry_run", False):
        result.append("--dry-run")
    if default_timeout is not None and getattr(args, "timeout", None) is None:
        result += ["--timeout", str(default_timeout)]
    return result


def add_common(parser: argparse.ArgumentParser, *, execution: bool = True) -> None:
    if execution:
        parser.add_argument("--timeout", type=positive_int)
        parser.add_argument("--no-review", action="store_true")
        parser.add_argument("--review-threshold", choices=("blocking", "high", "medium", "low"))
        parser.add_argument("--review-max-rounds", type=positive_int)
        parser.add_argument("--dry-run", action="store_true")
    for name in ("implement", "plan", "review", "fix"):
        parser.add_argument(f"--{name}-model", type=model_value)


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer >= 1") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be an integer >= 1")
    return parsed


def model_value(value: str) -> str:
    if not MODEL_RE.fullmatch(value):
        raise argparse.ArgumentTypeError("invalid model slug")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description="Pinned version-2 coding harness adapter.")
    subs = parser.add_subparsers(dest="command", required=True, parser_class=JsonArgumentParser)
    subs.add_parser("refresh-harness")
    subs.add_parser("check-config")
    run = subs.add_parser("run")
    run.add_argument("--target", required=True)
    run.add_argument("--prompt", required=True)
    run.add_argument("--mode", choices=("autonomous", "plan"))
    run.add_argument("--verify")
    run.add_argument("--verification-json", help="V2 verification object JSON or @path.")
    add_common(run)
    plan = subs.add_parser("run-plan")
    plan.add_argument("--target", required=True)
    plan.add_argument("--plan", required=True)
    add_common(plan)
    for name in ("status", "show"):
        child = subs.add_parser(name)
        child.add_argument("record_id")
    subs.add_parser("list")
    resume = subs.add_parser("resume")
    resume.add_argument("record_id")
    resume.add_argument("--restart-current-stage", action="store_true")
    add_common(resume, execution=False)
    cancel = subs.add_parser("cancel")
    cancel.add_argument("record_id")
    cancel.add_argument("--reason", required=True)
    return parser


def verification_object(value: str) -> dict[str, Any]:
    source = Path(value[1:]) if value.startswith("@") else None
    try:
        data = json.loads(source.read_text(encoding="utf-8") if source else value)
    except (OSError, json.JSONDecodeError) as exc:
        raise AdapterError(f"invalid structured verification: {exc}") from exc
    if not isinstance(data, dict) or set(data) != {"commands"} or not isinstance(data["commands"], list):
        raise AdapterError("structured verification must be an object containing only commands")
    return data


def resolve_plan_path(value: str) -> Path:
    candidate = Path(value).expanduser()
    absolute = candidate if candidate.is_absolute() else INVOCATION_CWD / candidate
    if has_symlink_component(absolute):
        raise AdapterError("phase-spec path contains a symlink component")
    try:
        canonical = absolute.resolve(strict=True)
    except OSError as exc:
        raise AdapterError(f"phase-spec path does not exist: {absolute}") from exc
    plans = PLANS_DIR.resolve()
    if not within(canonical, plans):
        raise AdapterError(f"phase-spec must be beneath {plans}")
    if canonical.is_symlink() or not canonical.is_file():
        raise AdapterError("phase-spec must be a regular non-symlink file")
    return canonical


def successful_check(argv: list[str]) -> bool:
    result = command(argv, check=False, env=persistent_cli_environment())
    return result.returncode == 0


def execute(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if args.command == "refresh-harness":
        lock = materialize_harness()
        return {
            "harness_revision": lock["revision"],
            "runner_result": {"materialized": True, "harness_dir": str(HARNESS_DIR)},
        }, 0
    if args.command == "check-config":
        lock = materialize_harness()
        policy = load_policy()
        checks = {name: shutil.which(name) for name in ("git", "gh", "agent")}
        checks["gh_auth"] = bool(checks["gh"]) and successful_check(["gh", "auth", "status"])
        checks["private_harness_access"] = bool(checks["gh"]) and successful_check([
            "gh", "repo", "view", "kenneth-huebsch/agent", "--json", "nameWithOwner",
        ])
        checks["agent_auth"] = bool(checks["agent"]) and successful_check(["agent", "status"])
        checks["policy"] = policy["schema_version"] == lock["contract_version"]
        checks["harness"] = True
        return {"harness_revision": lock["revision"], "runner_result": {"checks": checks}}, (
            0 if all(checks.values()) else 1
        )
    if args.command in {"status", "show", "list"}:
        extra = [] if args.command == "list" else [args.record_id]
        return delegate(args.command, extra)
    if args.command == "resume":
        extra = [args.record_id]
        if args.restart_current_stage:
            extra.append("--restart-current-stage")
        extra += forwarding_flags(args)
        return delegate("resume", extra)
    if args.command == "cancel":
        return delegate("cancel", [args.record_id, "--reason", args.reason])

    policy = load_policy()
    target = resolve_target(args.target, policy)
    if args.command == "run-plan":
        plan = resolve_plan_path(args.plan)
        return delegate(
            "run-plan",
            [
                "--target", str(target), "--plan", str(plan),
                *forwarding_flags(args, default_timeout=policy["default_timeout_seconds"]),
            ],
        )
    if args.verification_json and args.verify:
        raise AdapterError("--verify and --verification-json are mutually exclusive")
    if args.verification_json:
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix="single-", suffix=".json", dir=PLANS_DIR)
        plan_path = Path(name)
        try:
            phase: dict[str, Any] = {
                "id": "run", "prompt": args.prompt,
                "verification": verification_object(args.verification_json),
            }
            if args.mode:
                phase["mode"] = args.mode
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({"schema_version": 2, "phases": [phase]}, stream)
            return delegate(
                "run-plan",
                [
                    "--target", str(target), "--plan", str(plan_path),
                    *forwarding_flags(args, default_timeout=policy["default_timeout_seconds"]),
                ],
            )
        finally:
            plan_path.unlink(missing_ok=True)
    extra = ["--target", str(target), "--prompt", args.prompt]
    if args.mode:
        extra += ["--mode", args.mode]
    if args.verify:
        extra += ["--verify", args.verify]
    return delegate(
        "run",
        [*extra, *forwarding_flags(args, default_timeout=policy["default_timeout_seconds"])],
    )


def main() -> None:
    try:
        result, code = execute(build_parser().parse_args())
    except subprocess.CalledProcessError as exc:
        error = {
            "error": (exc.stderr or exc.stdout or str(exc)).strip(),
            "error_type": "CommandError",
        }
        try:
            revision = load_lock()["revision"]
        except Exception:
            revision = None
        result, code = {"harness_revision": revision, "runner_result": error}, 2
    except (AdapterError, OSError) as exc:
        error = {"error": str(exc), "error_type": type(exc).__name__}
        try:
            revision = load_lock()["revision"]
        except Exception:
            revision = None
        result, code = {"harness_revision": revision, "runner_result": error}, 2
    except Exception as exc:
        error = {"error": str(exc), "error_type": type(exc).__name__}
        try:
            revision = load_lock()["revision"]
        except Exception:
            revision = None
        result, code = {"harness_revision": revision, "runner_result": error}, 1
    emit(result)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
