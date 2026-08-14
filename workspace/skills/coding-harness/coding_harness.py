#!/usr/bin/env python3
"""Pinned, fail-closed adapter for the agent harness."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Iterator

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
PLAN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
DELIVERY_INTENTS = ("finalizable", "execution_only")
POLICY_FIELDS = {
    "schema_version", "allowed_target_roots", "inherited_environment_keys",
    "capability_environment", "capability_verification_hints",
    "sensitive_path_patterns", "default_timeout_seconds",
    "cancellation_grace_seconds", "allow_shell_verification", "default_branches",
    "guarded_commands", "model_tiers", "cheap_task_classes",
    "cheap_no_review_task_classes",
}
ADAPTER_POLICY_FIELDS = {"contract_version", "runtime_repos", "runs_dir", "denied_roots"}
RUNNER_POLICY_PATH = RUNTIME / ".coding-harness-runner-policy.json"


class AdapterError(RuntimeError):
    pass


class FinalizationError(AdapterError):
    def __init__(self, message: str, partial_state: dict[str, Any]):
        super().__init__(message)
        self.partial_state = partial_state


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
    tiers = value.get("model_tiers")
    if not isinstance(tiers, dict) or set(tiers) != {"cheap", "default", "reasoning"}:
        raise AdapterError("harness policy model_tiers must define cheap, default, and reasoning")
    for tier, mapping in tiers.items():
        if not isinstance(mapping, dict) or set(mapping) != {"implement", "review", "fix"}:
            raise AdapterError(f"harness policy model tier {tier!r} is invalid")
        if not all(isinstance(model, str) and MODEL_RE.fullmatch(model) for model in mapping.values()):
            raise AdapterError(f"harness policy model tier {tier!r} has an invalid model")
    cheap_classes = unique_strings("cheap_task_classes", nonempty=True)
    no_review_classes = unique_strings("cheap_no_review_task_classes")
    if not set(no_review_classes).issubset(cheap_classes):
        raise AdapterError("harness policy cheap no-review classes must be a subset")
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
    hints = value.get("capability_verification_hints")
    if not isinstance(hints, dict):
        raise AdapterError("harness policy capability_verification_hints must be an object")
    for capability, tokens in hints.items():
        if not isinstance(capability, str) or not CAPABILITY_RE.fullmatch(capability):
            raise AdapterError("harness policy capability verification hint name is invalid")
        if not isinstance(tokens, list) or not all(
            isinstance(token, str) and bool(token.strip()) for token in tokens
        ):
            raise AdapterError(
                f"harness policy capability verification hint {capability!r} tokens are invalid"
            )
        if len(tokens) != len(set(tokens)):
            raise AdapterError(
                f"harness policy capability verification hint {capability!r} tokens contain duplicates"
            )
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
    contract_result = command([sys.executable, str(runner), "contract"], cwd=HARNESS_DIR, check=False)
    if contract_result.returncode:
        raise AdapterError("pinned harness did not report its contract")
    contract = strict_json(contract_result.stdout, "pinned harness contract")
    expected = {
        "contract_version": lock["contract_version"],
        "schema_version": lock["contract_version"],
    }
    if contract != expected:
        raise AdapterError("pinned harness contract does not match lock")


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
        for key in (
            "CURSOR_API_KEY",
            "HOME",
            "LANG",
            "LC_ALL",
            "LOGNAME",
            "PATH",
            "SHELL",
            "TERM",
            "TMPDIR",
            "TZ",
            "USER",
        )
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


def finalization_git_environment() -> dict[str, str]:
    env = persistent_cli_environment()
    env.update({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
    })
    return env


def finalization_git_output(repo: Path, *args: str) -> str:
    result = command(
        ["git", "-C", str(repo), *args],
        check=False,
        env=finalization_git_environment(),
    )
    if result.returncode:
        raise AdapterError((result.stderr or result.stdout).strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def finalization_git_with_auth(
    args: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return command(
        ["git", "-c", "credential.helper=!gh auth git-credential", *args],
        check=check,
        env=finalization_git_environment(),
    )


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
    # Include all capability environment keys so the runner can forward them
    # to child processes that declare capabilities. The runner's policy.py
    # still validates that each phase explicitly declares which capabilities
    # it needs before those vars reach the child agent.
    for keys in policy.get("capability_environment", {}).values():
        allowed.update(keys)
    env = {key: value for key, value in os.environ.items() if key in allowed}
    env.update({
        "AGENT_RUN_HOME": str(RUNS_DIR),
        "GIT_TERMINAL_PROMPT": "0",
        "GCM_INTERACTIVE": "never",
        "SSH_ASKPASS_REQUIRE": "never",
        "XDG_CONFIG_HOME": "/home/node/.openclaw",
        "GH_CONFIG_DIR": "/home/node/.openclaw/gh",
    })
    # Cursor CLI accepts CURSOR_API_KEY, but the runner rejects API_KEY-shaped
    # names in inherited_environment_keys. Inject from the gateway env here so
    # children can auth with the key instead of browser SSO only.
    cursor_key = os.environ.get("CURSOR_API_KEY", "").strip()
    if cursor_key:
        env["CURSOR_API_KEY"] = cursor_key
    return env


def delegate(subcommand: str, extra: list[str], policy_path: Path = POLICY_PATH) -> tuple[dict[str, Any], int]:
    lock = materialize_harness()
    policy = load_policy(policy_path)
    runner_policy_path = materialize_runner_policy(policy)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    runner = HARNESS_DIR / "scripts" / "agent_run.py"
    argv = [sys.executable, str(runner), subcommand, *extra]
    if subcommand in {"run", "run-plan", "validate-plan", "resume", "cancel"} and "--policy" not in extra:
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
    policy: dict[str, Any] | None = None,
    include_model_flags: bool = True,
) -> list[str]:
    result: list[str] = []
    for attr, flag in (
        ("timeout", "--timeout"), ("review_threshold", "--review-threshold"),
        ("review_max_rounds", "--review-max-rounds"),
    ):
        value = getattr(args, attr, None)
        if value is not None:
            result += [flag, str(value)]
    if include_model_flags:
        for attr, flag in (
            ("implement_model", "--implement-model"),
            ("plan_model", "--plan-model"),
            ("review_model", "--review-model"),
            ("fix_model", "--fix-model"),
        ):
            value = getattr(args, attr, None)
            if value is not None:
                result += [flag, str(value)]
        if policy is not None and getattr(args, "plan_model", None) is None:
            result += ["--plan-model", policy["model_tiers"]["reasoning"]["implement"]]
    if getattr(args, "no_review", False):
        result.append("--no-review")
    if getattr(args, "dry_run", False):
        result.append("--dry-run")
    if default_timeout is not None and getattr(args, "timeout", None) is None:
        result += ["--timeout", str(default_timeout)]
    return result


def delivery_flags(args: argparse.Namespace) -> list[str]:
    intent = getattr(args, "delivery_intent", None)
    return ["--delivery-intent", intent] if intent is not None else []


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
    parser = JsonArgumentParser(description="Pinned coding harness adapter.")
    subs = parser.add_subparsers(dest="command", required=True, parser_class=JsonArgumentParser)
    subs.add_parser("refresh-harness")
    subs.add_parser("check-config")
    run = subs.add_parser("run")
    run.add_argument("--target", required=True)
    run.add_argument("--prompt", required=True)
    run.add_argument("--mode", choices=("autonomous", "plan"))
    run.add_argument("--verify")
    run.add_argument("--verification-json", help="Structured verification object JSON or @path.")
    run.add_argument("--routing-json", help="Symbolic routing object JSON or @path.")
    run.set_defaults(delivery_intent="execution_only")
    add_common(run)
    plan = subs.add_parser("run-plan")
    plan.add_argument("--target", required=True)
    plan.add_argument("--plan", required=True)
    plan.add_argument("--delivery-intent", choices=DELIVERY_INTENTS, required=True)
    continuation = plan.add_mutually_exclusive_group()
    continuation.add_argument("--strip-completed", metavar="PRIOR_PLAN_ID")
    continuation.add_argument("--recover-scope-from", metavar="PRIOR_PLAN_ID")
    add_common(plan)
    preflight = subs.add_parser("preflight-plan")
    preflight.add_argument("--target", required=True)
    preflight.add_argument("--plan", required=True)
    preflight.add_argument("--delivery-intent", choices=DELIVERY_INTENTS, required=True)
    approval_provenance = preflight.add_mutually_exclusive_group()
    approval_provenance.add_argument("--strip-completed", metavar="PRIOR_PLAN_ID")
    approval_provenance.add_argument("--recover-scope-from", metavar="PRIOR_PLAN_ID")
    preflight.add_argument("--timeout", type=positive_int)
    preflight.add_argument("--no-review", action="store_true")
    preflight.add_argument("--review-threshold", choices=("blocking", "high", "medium", "low"))
    preflight.add_argument("--review-max-rounds", type=positive_int)
    finalize = subs.add_parser("finalize-plan")
    finalize.add_argument("plan_id")
    finalize.add_argument("--message", required=True)
    finalize.add_argument("--approve-commit", action="store_true")
    finalize.add_argument("--approve-push", action="store_true")
    for name in ("status", "show"):
        child = subs.add_parser(name)
        child.add_argument("record_id")
    subs.add_parser("list")
    resume = subs.add_parser("resume")
    resume.add_argument("record_id")
    resume.add_argument("--restart-current-stage", action="store_true")
    resume.add_argument("--guidance")
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


def routing_object(value: str) -> dict[str, Any]:
    source = Path(value[1:]) if value.startswith("@") else None
    try:
        data = strict_json(
            source.read_text(encoding="utf-8") if source else value,
            "symbolic routing",
        )
    except OSError as exc:
        raise AdapterError(f"invalid symbolic routing: {exc}") from exc
    required = {"tier", "task_class", "reason", "risk_flags", "allowed_paths"}
    if not isinstance(data, dict) or set(data) != required:
        raise AdapterError(
            "symbolic routing must contain tier, task_class, reason, risk_flags, and allowed_paths"
        )
    return data


def automatic_routing(mode: str | None) -> dict[str, Any]:
    planning = mode == "plan"
    return {
        "tier": "reasoning" if planning else "default",
        "task_class": "planning" if planning else "ordinary",
        "reason": "automatic conservative routing default",
        "risk_flags": ["unclassified"],
        "allowed_paths": [],
    }


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


def cursor_agent_authenticated() -> bool:
    if not shutil.which("agent"):
        return False
    if os.environ.get("CURSOR_API_KEY", "").strip():
        return True
    result = command(["agent", "status"], check=False, env=persistent_cli_environment())
    output = f"{result.stdout}\n{result.stderr}".lower()
    return "logged in as" in output


def read_strict_json_file(path: Path, context: str) -> dict[str, Any]:
    """Read a regular record file without following a final-component symlink."""
    parent = path.parent.resolve(strict=True)
    if has_symlink_component(parent) or path.parent.resolve(strict=True) != parent:
        raise AdapterError(f"{context} parent is not canonical")
    directory_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise AdapterError(f"{context} must be a regular file")
            with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as stream:
                text = stream.read()
            after = os.fstat(fd)
            current = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino) or (
                before.st_dev, before.st_ino
            ) != (current.st_dev, current.st_ino):
                raise AdapterError(f"{context} changed while being read")
        finally:
            os.close(fd)
    except (OSError, UnicodeDecodeError) as exc:
        raise AdapterError(f"cannot read {context}: {exc}") from exc
    finally:
        os.close(directory_fd)
    value = strict_json(text, context)
    if not isinstance(value, dict):
        raise AdapterError(f"{context} must be a JSON object")
    return value


def canonical_json_sha256(value: Any) -> str:
    encoded = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    return hashlib.sha256(encoded).hexdigest()


def directory_identity(path: Path) -> tuple[int, int]:
    value = os.stat(path, follow_symlinks=False)
    if not stat.S_ISDIR(value.st_mode):
        raise AdapterError(f"record path is not a directory: {path}")
    return value.st_dev, value.st_ino


def open_directory_path(path: Path) -> int:
    """Open every absolute directory component without following symlinks."""
    if not path.is_absolute():
        raise AdapterError("record root must be absolute")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            child = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=fd,
            )
            os.close(fd)
            fd = child
        return fd
    except OSError as exc:
        os.close(fd)
        raise AdapterError(f"cannot safely open record directory {path}: {exc}") from exc


def open_record_directory(record_id: str) -> tuple[int, int, Path]:
    if not isinstance(record_id, str) or not record_id:
        raise AdapterError("record ID is invalid")
    parts = record_id.split("/")
    if len(parts) not in {1, 2} or any(not PLAN_ID_RE.fullmatch(part) for part in parts):
        raise AdapterError("record ID is invalid")
    runs_fd = open_directory_path(RUNS_DIR)
    current_fd = os.dup(runs_fd)
    try:
        for part in parts:
            child = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=current_fd,
            )
            os.close(current_fd)
            current_fd = child
        return runs_fd, current_fd, RUNS_DIR.joinpath(*parts)
    except OSError as exc:
        os.close(current_fd)
        os.close(runs_fd)
        raise AdapterError(f"cannot safely open record {record_id!r}: {exc}") from exc


def read_json_at(directory_fd: int, name: str, context: str) -> dict[str, Any]:
    if "/" in name or name in {"", ".", ".."}:
        raise AdapterError(f"{context} filename is invalid")
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise AdapterError(f"{context} must be a regular file")
            with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as stream:
                text = stream.read()
            after = os.fstat(fd)
            current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino) or (
                before.st_dev, before.st_ino
            ) != (current.st_dev, current.st_ino):
                raise AdapterError(f"{context} changed while being read")
        finally:
            os.close(fd)
    except (OSError, UnicodeDecodeError) as exc:
        raise AdapterError(f"cannot safely read {context}: {exc}") from exc
    value = strict_json(text, context)
    if not isinstance(value, dict):
        raise AdapterError(f"{context} must be a JSON object")
    return value


def verify_record_directory_identity(
    parent_fd: int,
    name: str,
    directory_fd: int,
    context: str,
) -> None:
    opened = os.fstat(directory_fd)
    current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if not stat.S_ISDIR(current.st_mode) or (
        opened.st_dev, opened.st_ino
    ) != (current.st_dev, current.st_ino):
        raise AdapterError(f"{context} directory identity changed")


def canonical_existing_path(path: Path, root: Path, context: str, *, directory: bool = False) -> Path:
    root = root.resolve(strict=True)
    absolute = path if path.is_absolute() else root / path
    if has_symlink_component(absolute):
        raise AdapterError(f"{context} contains a symlink component")
    try:
        canonical = absolute.resolve(strict=True)
    except OSError as exc:
        raise AdapterError(f"{context} does not exist: {absolute}") from exc
    if not within(canonical, root):
        raise AdapterError(f"{context} escapes {root}")
    if directory:
        if not canonical.is_dir() or canonical.is_symlink():
            raise AdapterError(f"{context} must be a regular directory")
    elif not canonical.is_file() or canonical.is_symlink():
        raise AdapterError(f"{context} must be a regular file")
    return canonical


def git_bytes(repo: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        env=finalization_git_environment(),
        capture_output=True,
        check=False,
    )
    if result.returncode:
        error = (result.stderr or result.stdout).decode(errors="replace").strip()
        raise AdapterError(error or f"git {' '.join(args)} failed")
    return result.stdout


def worktree_config_enabled(target: Path) -> bool:
    result = command(
        [
            "git", "-C", str(target), "config", "--local", "--type=bool",
            "--get", "extensions.worktreeConfig",
        ],
        check=False,
        env=finalization_git_environment(),
    )
    if result.returncode == 1:
        return False
    if result.returncode != 0 or result.stdout.strip() not in {"true", "false"}:
        raise AdapterError("extensions.worktreeConfig must be a valid local boolean")
    return result.stdout.strip() == "true"


def repository_config_bytes(target: Path) -> bytes:
    """Canonical local plus enabled worktree-scope configuration."""
    scopes = [("local", git_bytes(target, "config", "--local", "--null", "--list"))]
    if worktree_config_enabled(target):
        scopes.append(
            ("worktree", git_bytes(target, "config", "--worktree", "--null", "--list"))
        )
    chunks: list[bytes] = []
    for scope, raw in scopes:
        entries = sorted(item for item in raw.split(b"\0") if item)
        chunks.append(scope.encode() + b"\0" + b"\0".join(entries) + b"\0")
    return b"".join(chunks)


def runner_config_bytes(target: Path) -> bytes:
    """Match the pinned runner's persisted config checkpoint contract exactly."""
    return git_bytes(target, "config", "--local", "--list", "--show-origin")


def git_checkpoint(target: Path) -> dict[str, str]:
    object_dir = Path(finalization_git_output(target, "rev-parse", "--git-path", "objects"))
    if not object_dir.is_absolute():
        object_dir = (target / object_dir).resolve()
    with tempfile.TemporaryDirectory(prefix=".mira-finalize-") as raw:
        artifacts = Path(raw)
        index = artifacts / "snapshot.index"
        objects = artifacts / "objects"
        objects.mkdir()
        env = {
            **finalization_git_environment(),
            "GIT_INDEX_FILE": str(index),
            "GIT_OBJECT_DIRECTORY": str(objects),
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(object_dir),
        }
        has_head = command(
            ["git", "-C", str(target), "rev-parse", "--verify", "HEAD"],
            check=False,
            env=env,
        ).returncode == 0
        command(["git", "-C", str(target), "read-tree", "HEAD" if has_head else "--empty"], env=env)
        command(["git", "-C", str(target), "add", "-A", "--", "."], env=env)
        tree = command(["git", "-C", str(target), "write-tree"], env=env).stdout.strip()
    head = finalization_git_output(target, "rev-parse", "--verify", "HEAD")
    branch = finalization_git_output(target, "branch", "--show-current")
    git_dir = Path(finalization_git_output(target, "rev-parse", "--git-dir"))
    if not git_dir.is_absolute():
        git_dir = target / git_dir
    index_bytes = (git_dir.resolve() / "index").read_bytes() if (git_dir.resolve() / "index").exists() else b""
    config = runner_config_bytes(target)
    refs = git_bytes(target, "for-each-ref", "--format=%(refname)%00%(objectname)")
    digest = lambda value: hashlib.sha256(value).hexdigest()
    return {
        "tree_oid": tree,
        "head_oid": head,
        "branch": branch,
        "index_sha256": digest(index_bytes),
        "worktree_fingerprint": digest(f"{tree}\0{head}\0{branch}".encode()),
        "config_sha256": digest(config),
        "refs_sha256": digest(refs),
    }


def validate_checkpoint_shape(raw: Any, context: str) -> dict[str, str]:
    fields = {
        "tree_oid", "head_oid", "branch", "index_sha256", "worktree_fingerprint",
        "config_sha256", "refs_sha256",
    }
    if not isinstance(raw, dict) or set(raw) != fields:
        raise AdapterError(f"{context} has invalid checkpoint fields")
    if not all(isinstance(value, str) for value in raw.values()):
        raise AdapterError(f"{context} checkpoint values must be strings")
    for name in fields - {"branch"}:
        if not raw[name]:
            raise AdapterError(f"{context} {name} must not be empty")
    return raw


def preflight_delivery_context(
    target: Path,
    policy: dict[str, Any],
    delivery_intent: str,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "target": str(target),
        "delivery_intent": delivery_intent,
        "finalizable": delivery_intent == "finalizable",
    }
    if delivery_intent == "execution_only":
        context["target_ready"] = True
        context["note"] = "execution-only plans are not eligible for finalize-plan"
        return context
    checkpoint = git_checkpoint(target)
    if checkpoint["branch"] not in policy["default_branches"]:
        raise AdapterError(
            "finalizable preflight requires the target on a configured main/master branch"
        )
    head_tree = finalization_git_output(
        target, "rev-parse", f"{checkpoint['head_oid']}^{{tree}}"
    )
    if (
        checkpoint["tree_oid"] != head_tree
        or finalization_git_output(
            target, "status", "--porcelain", "--untracked-files=normal"
        )
    ):
        raise AdapterError("finalizable preflight requires a clean target")
    context.update({
        "target_ready": True,
        "branch": checkpoint["branch"],
        "head_oid": checkpoint["head_oid"],
        "tree_oid": checkpoint["tree_oid"],
        "note": "execution revalidates this target under the runner lock",
    })
    return context


def show_record(record_id: str) -> dict[str, Any]:
    wrapped, code = delegate("show", [record_id])
    if code:
        error = wrapped["runner_result"].get("error", "runner show failed")
        raise AdapterError(f"cannot validate record {record_id!r}: {error}")
    result = wrapped["runner_result"]
    if not isinstance(result, dict):
        raise AdapterError("runner show result must be an object")
    return result


def validate_green_phase(
    plan_id: str,
    result: dict[str, Any],
    *,
    target: Path,
    spec_sha256: str,
) -> dict[str, str]:
    run_id = result.get("run_id")
    if not isinstance(run_id, str) or not run_id.startswith(f"{plan_id}/"):
        raise AdapterError("plan phase run id is invalid")
    shown = show_record(run_id)
    if shown.get("kind") != "run":
        raise AdapterError(f"record {run_id!r} is not a phase run")
    status = shown.get("status")
    if not isinstance(status, dict) or (
        status.get("run_id") != run_id
        or status.get("plan_id") != plan_id
        or status.get("phase_id") != result.get("phase_id")
        or status.get("target") != str(target)
        or status.get("spec_sha256") != spec_sha256
        or status.get("state") != "green"
        or status.get("gate") != "green"
    ):
        raise AdapterError(f"phase record {run_id!r} does not match its green plan result")
    runs_fd, record_fd, record_dir = open_record_directory(run_id)
    try:
        if Path(shown.get("record_dir", "")) != record_dir:
            raise AdapterError("phase record path does not match its ID")
        checkpoint = read_json_at(record_fd, "checkpoint.json", "phase checkpoint")
    finally:
        os.close(record_fd)
        os.close(runs_fd)
    if set(checkpoint) - {"schema_version", "stage", "git", "review_round", "prior_findings_path"}:
        raise AdapterError("phase checkpoint has unknown fields")
    if checkpoint.get("schema_version") != 2 or checkpoint.get("stage") != "green":
        raise AdapterError(f"phase record {run_id!r} lacks a final green checkpoint")
    return validate_checkpoint_shape(checkpoint.get("git"), "phase checkpoint")


def validate_plan_spec(
    record_fd: int,
    plan: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    spec = read_json_at(record_fd, "spec.json", "plan spec")
    if (
        set(spec) != {"schema_version", "delivery_intent", "phases"}
        or spec.get("schema_version") != 2
        or spec.get("delivery_intent") != "finalizable"
    ):
        raise AdapterError("canonical plan spec is malformed")
    if canonical_json_sha256(spec) != plan.get("spec_sha256"):
        raise AdapterError("canonical plan spec digest does not match the plan")
    phases = spec.get("phases")
    if not isinstance(phases, list) or not phases:
        raise AdapterError("canonical plan spec phases must be a non-empty array")
    ids: list[str] = []
    slugs: list[str] = []
    for phase in phases:
        if not isinstance(phase, dict):
            raise AdapterError("canonical plan spec phase must be an object")
        phase_id = phase.get("id")
        slug = phase.get("slug")
        if not isinstance(phase_id, str) or not phase_id or not isinstance(slug, str) or not slug:
            raise AdapterError("canonical plan spec phase identity is invalid")
        ids.append(phase_id)
        slugs.append(slug)
    if len(ids) != len(set(ids)) or len(slugs) != len(set(slugs)):
        raise AdapterError("canonical plan spec phase identities are not unique")
    skipped = plan.get("skipped_green_phases", [])
    scheduled = plan.get("scheduled")
    if not isinstance(skipped, list) or not all(isinstance(item, str) for item in skipped):
        raise AdapterError("plan skipped phase provenance is invalid")
    if skipped != ids[: len(skipped)]:
        raise AdapterError("skipped_green_phases must be the exact canonical spec prefix")
    if not isinstance(scheduled, list):
        raise AdapterError("plan scheduled results are invalid")
    scheduled_ids = [
        item.get("phase_id") if isinstance(item, dict) else None
        for item in scheduled
    ]
    if scheduled_ids != ids[len(skipped) :]:
        raise AdapterError("scheduled phase IDs must be the exact canonical spec suffix in order")
    expected_runs = [
        f"{plan.get('plan_id')}/{slug}" for slug in slugs[len(skipped) :]
    ]
    actual_runs = [
        item.get("run_id") if isinstance(item, dict) else None
        for item in scheduled
    ]
    if actual_runs != expected_runs:
        raise AdapterError("scheduled run IDs must match canonical phase order")
    if plan.get("total_phases") != len(ids):
        raise AdapterError("plan total_phases does not match canonical spec")
    return phases, ids, slugs


def validate_skipped_prefix(
    plan: dict[str, Any],
    phases: list[dict[str, Any]],
    *,
    target: Path,
    delivery_baseline: dict[str, str],
    runner_branch: str,
    seen: set[str],
) -> None:
    if not phases:
        return
    prior_id = plan.get("continued_from_plan_id")
    if not isinstance(prior_id, str) or prior_id in seen:
        raise AdapterError("skipped phase provenance is missing or cyclic")
    seen.add(prior_id)
    shown = show_record(prior_id)
    prior = shown.get("plan") if shown.get("kind") == "plan" else None
    if not isinstance(prior, dict) or prior.get("target") != str(target):
        raise AdapterError("prior plan target does not match finalization target")
    prior_runs_fd, prior_fd, prior_record_dir = open_record_directory(prior_id)
    try:
        if Path(shown.get("record_dir", "")) != prior_record_dir:
            raise AdapterError("prior plan record path does not match its ID")
        prior_phases, prior_ids, _ = validate_plan_spec(prior_fd, prior)
        prior_target = read_json_at(prior_fd, "target.json", "prior plan target")
    finally:
        os.close(prior_fd)
        os.close(prior_runs_fd)
    if (
        prior.get("delivery_intent") != "finalizable"
        or prior.get("finalizable") is not True
        or prior.get("delivery_baseline") != delivery_baseline
        or prior.get("runner_branch") != runner_branch
        or prior_target.get("delivery_intent") != "finalizable"
        or prior_target.get("finalizable") is not True
        or prior_target.get("delivery_baseline") != delivery_baseline
        or prior_target.get("runner_branch") != runner_branch
    ):
        raise AdapterError("prior plan finalizable delivery evidence is inconsistent")
    prior_skipped = prior.get("skipped_green_phases", [])
    if not isinstance(prior_skipped, list):
        raise AdapterError("prior plan skipped phase provenance is invalid")
    if phases != prior_phases[: len(phases)]:
        raise AdapterError("skipped phase definitions do not match prior canonical plan prefix")
    scheduled_by_phase = {}
    for item in prior.get("scheduled", []):
        if not isinstance(item, dict) or item.get("phase_id") in scheduled_by_phase:
            raise AdapterError("prior plan scheduled phase identities are invalid")
        scheduled_by_phase[item.get("phase_id")] = item
    inherited = phases[: len(prior_skipped)]
    if inherited:
        validate_skipped_prefix(
            prior,
            inherited,
            target=target,
            delivery_baseline=delivery_baseline,
            runner_branch=runner_branch,
            seen=seen,
        )
    for phase_id in [phase["id"] for phase in phases]:
        if phase_id in prior_skipped:
            continue
        result = scheduled_by_phase.get(phase_id)
        if not isinstance(result, dict) or result.get("gate") != "green":
            raise AdapterError(f"skipped phase {phase_id!r} lacks validated green provenance")
        validate_green_phase(
            prior_id,
            result,
            target=target,
            spec_sha256=str(prior.get("spec_sha256", "")),
        )


def validated_origin(target: Path) -> str:
    fetch_values = finalization_git_output(target, "remote", "get-url", "--all", "origin").splitlines()
    push_values = finalization_git_output(target, "remote", "get-url", "--push", "--all", "origin").splitlines()
    github_url = re.compile(
        r"^(?:git@github\.com:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?|"
        r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?)$",
        re.IGNORECASE,
    )
    if not fetch_values or not push_values or not all(
        github_url.fullmatch(value.strip()) for value in [*fetch_values, *push_values]
    ):
        raise AdapterError("target origin must be a canonical GitHub repository")
    fetch = {canonical_url(value) for value in fetch_values}
    push = {canonical_url(value) for value in push_values}
    if len(fetch) != 1 or push != fetch:
        raise AdapterError("remote.origin.pushurl diverges from the fetch origin")
    return next(iter(fetch))


def remote_oid(target: Path, branch: str, origin: str | None = None) -> str:
    destination = origin or validated_origin(target)
    result = finalization_git_with_auth(
        ["-C", str(target), "ls-remote", "--exit-code", destination, f"refs/heads/{branch}"],
        check=False,
    )
    if result.returncode:
        raise AdapterError(
            (result.stderr or result.stdout).strip()
            or f"cannot resolve remote {branch} baseline"
        )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise AdapterError(f"remote {branch} did not resolve to exactly one ref")
    parts = lines[0].split()
    if len(parts) != 2 or parts[1] != f"refs/heads/{branch}" or not REVISION_RE.fullmatch(parts[0]):
        raise AdapterError(f"remote {branch} response is malformed")
    return parts[0]


def git_refs(target: Path) -> dict[str, str]:
    refs: dict[str, str] = {}
    for line in finalization_git_output(
        target, "for-each-ref", "--format=%(refname) %(objectname)"
    ).splitlines():
        try:
            name, oid = line.split(" ", 1)
        except ValueError as exc:
            raise AdapterError("Git refs output is malformed") from exc
        if name in refs or not REVISION_RE.fullmatch(oid):
            raise AdapterError("Git refs output is invalid")
        refs[name] = oid
    return refs


def expected_refs(
    before: dict[str, str],
    updates: dict[str, str],
) -> dict[str, str]:
    result = dict(before)
    for name, oid in updates.items():
        if name not in result:
            raise AdapterError(f"expected ref is missing: {name}")
        result[name] = oid
    return result


def validated_hooks_path(target: Path) -> Path:
    configured = command(
        ["git", "-C", str(target), "config", "--get", "core.hooksPath"],
        check=False,
        env=finalization_git_environment(),
    )
    if configured.returncode not in {0, 1}:
        raise AdapterError("cannot inspect core.hooksPath")
    raw = configured.stdout.strip() if configured.returncode == 0 else ""
    candidate = Path(raw).expanduser() if raw else Path(finalization_git_output(target, "rev-parse", "--git-path", "hooks"))
    if not candidate.is_absolute():
        candidate = target / candidate
    if has_symlink_component(candidate):
        raise AdapterError("core.hooksPath contains a symlink component")
    try:
        canonical = candidate.resolve(strict=True)
    except OSError as exc:
        raise AdapterError("core.hooksPath must be an existing directory") from exc
    if not canonical.is_dir() or canonical.is_symlink() or not within(canonical, target.resolve()):
        raise AdapterError("core.hooksPath must be a canonical non-symlink directory beneath the target")
    return canonical


def validate_safe_push_config(target: Path) -> None:
    rewrites = command(
        [
            "git", "-C", str(target), "config", "--get-regexp",
            r"^url\..*\.(insteadOf|pushInsteadOf)$",
        ],
        check=False,
        env=finalization_git_environment(),
    )
    if rewrites.returncode == 0 and rewrites.stdout.strip():
        raise AdapterError("local URL rewrite configuration is forbidden for finalization")
    if rewrites.returncode not in {0, 1}:
        raise AdapterError("cannot inspect local URL rewrite configuration")
    for key in ("push.followTags", "remote.origin.push", "remote.origin.tagOpt"):
        result = command(
            ["git", "-C", str(target), "config", "--get-all", key],
            check=False,
            env=finalization_git_environment(),
        )
        if result.returncode == 0 and result.stdout.strip():
            raise AdapterError(f"unsafe local push configuration is set: {key}")
        if result.returncode not in {0, 1}:
            raise AdapterError(f"cannot inspect local push configuration: {key}")


def assert_repository_state(
    target: Path,
    *,
    branch: str,
    head: str,
    tree: str,
    config_sha256: str,
    protected_config_sha256: str,
    refs: dict[str, str],
    origin: str,
    context: str,
) -> None:
    current = git_checkpoint(target)
    if current["branch"] != branch or current["head_oid"] != head or current["tree_oid"] != tree:
        raise AdapterError(f"{context} changed branch, HEAD, or tree")
    if current["config_sha256"] != config_sha256:
        raise AdapterError(f"{context} changed repository config")
    if hashlib.sha256(repository_config_bytes(target)).hexdigest() != protected_config_sha256:
        raise AdapterError(f"{context} changed protected local/worktree config")
    if git_refs(target) != refs:
        raise AdapterError(f"{context} changed unexpected refs")
    if validated_origin(target) != origin:
        raise AdapterError(f"{context} changed target origin")
    validated_hooks_path(target)
    validate_safe_push_config(target)
    if finalization_git_output(target, "status", "--porcelain", "--untracked-files=normal"):
        raise AdapterError(f"{context} left the worktree dirty")


@contextmanager
def nonblocking_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AdapterError(f"lock is already held: {path}") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def finalization_state(target: Path | None, state: dict[str, Any]) -> dict[str, Any]:
    result = dict(state)
    if target is not None and target.is_dir():
        for key, args in (
            ("current_branch", ("branch", "--show-current")),
            ("current_head", ("rev-parse", "--verify", "HEAD")),
            ("worktree_status", ("status", "--porcelain", "--untracked-files=normal")),
        ):
            try:
                result[key] = finalization_git_output(target, *args)
            except AdapterError as exc:
                result[key] = f"unavailable: {exc}"
    return result


def finalize_plan(plan_id: str, message: str, approve_commit: bool, approve_push: bool) -> dict[str, Any]:
    state: dict[str, Any] = {
        "staged": False,
        "commit_created": False,
        "local_default_fast_forwarded": False,
        "pushed": False,
    }
    target: Path | None = None
    try:
        if not PLAN_ID_RE.fullmatch(plan_id):
            raise AdapterError("plan ID is invalid")
        if not message.strip():
            raise AdapterError("explicit commit message must not be empty")
        if not approve_commit:
            raise AdapterError("--approve-commit is required")
        if not approve_push:
            raise AdapterError("--approve-push is required")
        policy = load_policy()
        shown = show_record(plan_id)
        if shown.get("kind") != "plan":
            raise AdapterError("finalization requires a plan record")
        plan = shown.get("plan")
        if not isinstance(plan, dict):
            raise AdapterError("runner show omitted the plan")
        if (
            plan.get("plan_id") != plan_id
            or plan.get("state") != "green"
            or plan.get("gate") != "green"
        ):
            raise AdapterError("plan is not terminal green")
        if plan.get("delivery_intent") != "finalizable" or plan.get("finalizable") is not True:
            raise AdapterError("plan is explicitly non-finalizable or lacks finalizable evidence")
        runner_branch = plan.get("runner_branch")
        if not isinstance(runner_branch, str) or not runner_branch:
            raise AdapterError("finalizable plan runner_branch evidence is invalid")
        delivery_baseline = validate_checkpoint_shape(
            plan.get("delivery_baseline"),
            "plan delivery baseline",
        )
        if plan.get("active_run_id") is not None:
            raise AdapterError("plan still has an active run")
        if plan.get("no_op") is True:
            raise AdapterError("no-op plans cannot be finalized")
        scheduled = plan.get("scheduled")
        if not isinstance(scheduled, list) or not scheduled:
            raise AdapterError("plan has no executable green phases")
        skipped = plan.get("skipped_green_phases", [])
        if not isinstance(skipped, list):
            raise AdapterError("plan skipped phase provenance is invalid")
        if len(skipped) + len(scheduled) != plan.get("total_phases"):
            raise AdapterError("plan does not account for every phase")
        if any(not isinstance(item, dict) or item.get("gate") != "green" for item in scheduled):
            raise AdapterError("not every scheduled phase is green")
        runs_fd, record_fd, record_dir = open_record_directory(plan_id)
        record_stat = os.fstat(record_fd)
        expected_record_dir = RUNS_DIR / plan_id
        try:
            if Path(shown.get("record_dir", "")) != expected_record_dir or record_dir != expected_record_dir:
                raise AdapterError("plan record path does not match its ID")
            if read_json_at(record_fd, "plan.json", "plan summary") != plan:
                raise AdapterError("runner show plan differs from canonical plan record")
            phase_objects, phase_ids, _ = validate_plan_spec(record_fd, plan)
            if len(skipped) + len(scheduled) != len(phase_ids):
                raise AdapterError("plan does not account for every canonical phase")
            target_record = read_json_at(record_fd, "target.json", "plan target")
        finally:
            os.close(record_fd)
            os.close(runs_fd)
        allowed_target_fields = {
            "schema_version", "root", "common_dir", "object_dir", "initial_baseline",
            "delivery_intent", "finalizable", "delivery_baseline", "runner_branch",
        }
        if set(target_record) != allowed_target_fields or target_record.get("schema_version") != 2:
            raise AdapterError("plan target record is malformed")
        if (
            target_record.get("delivery_intent") != "finalizable"
            or target_record.get("finalizable") is not True
            or target_record.get("delivery_baseline") != delivery_baseline
            or target_record.get("runner_branch") != runner_branch
        ):
            raise AdapterError("plan target finalizable delivery evidence is inconsistent")
        target = resolve_target(str(plan.get("target", "")), policy)
        if target_record.get("root") != str(target):
            raise AdapterError("plan target does not match its canonical target record")
        git_root = Path(finalization_git_output(target, "rev-parse", "--show-toplevel")).resolve()
        common_dir = Path(finalization_git_output(target, "rev-parse", "--git-common-dir"))
        object_dir = Path(finalization_git_output(target, "rev-parse", "--git-path", "objects"))
        common_dir = (target / common_dir).resolve() if not common_dir.is_absolute() else common_dir.resolve()
        object_dir = (target / object_dir).resolve() if not object_dir.is_absolute() else object_dir.resolve()
        if {
            "root": str(git_root), "common_dir": str(common_dir), "object_dir": str(object_dir)
        } != {key: target_record[key] for key in ("root", "common_dir", "object_dir")}:
            raise AdapterError("canonical target identity drifted from plan evidence")
        validate_checkpoint_shape(target_record.get("initial_baseline"), "initial baseline")
        default_branch = delivery_baseline["branch"]
        if default_branch not in policy["default_branches"]:
            raise AdapterError("target did not start on a configured main/master branch")
        if delivery_baseline["tree_oid"] != finalization_git_output(
            target, "rev-parse", f"{delivery_baseline['head_oid']}^{{tree}}"
        ):
            raise AdapterError("target was not clean at its delivery baseline")
        if plan.get("target") != str(target):
            raise AdapterError("plan target does not match policy-approved repository")
        with ExitStack() as stack:
            stack.enter_context(nonblocking_lock(RUNS_DIR / ".locks" / f"{plan_id}.lock"))
            stack.enter_context(nonblocking_lock(common_dir / "agent-harness.lock"))
            locked_runs_fd, locked_record_fd, locked_record_dir = open_record_directory(plan_id)
            stack.callback(os.close, locked_record_fd)
            stack.callback(os.close, locked_runs_fd)
            locked_stat = os.fstat(locked_record_fd)
            if (
                locked_record_dir != expected_record_dir
                or (locked_stat.st_dev, locked_stat.st_ino)
                != (record_stat.st_dev, record_stat.st_ino)
            ):
                raise AdapterError("canonical plan record directory changed while acquiring locks")
            verify_record_directory_identity(
                locked_runs_fd, plan_id, locked_record_fd, "plan record"
            )
            locked = show_record(plan_id)
            if locked.get("plan") != plan:
                raise AdapterError("plan record changed while finalization was acquiring locks")
            if read_json_at(locked_record_fd, "plan.json", "locked plan summary") != plan:
                raise AdapterError("canonical plan record changed while locks were held")
            locked_phases, _, _ = validate_plan_spec(locked_record_fd, plan)
            if locked_phases != phase_objects:
                raise AdapterError("canonical plan spec changed while locks were held")
            if read_json_at(locked_record_fd, "target.json", "locked plan target") != target_record:
                raise AdapterError("canonical target record changed while locks were held")
            if skipped:
                validate_skipped_prefix(
                    plan,
                    phase_objects[: len(skipped)],
                    target=target,
                    delivery_baseline=delivery_baseline,
                    runner_branch=runner_branch,
                    seen={plan_id},
                )
            final_checkpoint: dict[str, str] | None = None
            for result in scheduled:
                final_checkpoint = validate_green_phase(
                    plan_id,
                    result,
                    target=target,
                    spec_sha256=str(plan.get("spec_sha256", "")),
                )
            assert final_checkpoint is not None
            current = git_checkpoint(target)
            expected_branch = runner_branch
            if current["branch"] != expected_branch:
                raise AdapterError(f"target is not on expected runner branch {expected_branch}")
            if current != final_checkpoint:
                raise AdapterError("target branch/HEAD/config/refs/tree drifted from final green checkpoint")
            protected_config_sha256 = hashlib.sha256(repository_config_bytes(target)).hexdigest()
            if current["head_oid"] != delivery_baseline["head_oid"]:
                raise AdapterError("target HEAD drifted from the recorded main baseline")
            origin = validated_origin(target)
            validated_hooks_path(target)
            validate_safe_push_config(target)
            local_default = finalization_git_output(target, "rev-parse", f"refs/heads/{default_branch}")
            if local_default != delivery_baseline["head_oid"]:
                raise AdapterError(f"local {default_branch} drifted from the recorded baseline")
            baseline_remote = remote_oid(target, default_branch, origin)
            if baseline_remote != delivery_baseline["head_oid"]:
                raise AdapterError(f"remote {default_branch} drifted from the recorded baseline")
            if final_checkpoint["tree_oid"] == finalization_git_output(
                target,
                "rev-parse",
                f"{delivery_baseline['head_oid']}^{{tree}}",
            ):
                raise AdapterError("plan produced no actual changes")
            refs_before_commit = git_refs(target)
            task_ref = f"refs/heads/{expected_branch}"
            default_ref = f"refs/heads/{default_branch}"
            command(
                ["git", "-C", str(target), "add", "-A", "--", "."],
                env=finalization_git_environment(),
            )
            state["staged"] = True
            staged_tree = finalization_git_output(target, "write-tree")
            if staged_tree != final_checkpoint["tree_oid"]:
                raise AdapterError("staged tree does not match the final green checkpoint")
            commit = command(
                ["git", "-C", str(target), "commit", "-m", message],
                check=False,
                env=finalization_git_environment(),
            )
            if commit.returncode:
                raise AdapterError(
                    (commit.stderr or commit.stdout).strip() or "git commit failed"
                )
            state["commit_created"] = True
            commit_oid = finalization_git_output(target, "rev-parse", "HEAD")
            state["commit_oid"] = commit_oid
            refs_after_commit = expected_refs(refs_before_commit, {task_ref: commit_oid})
            assert_repository_state(
                target,
                branch=expected_branch,
                head=commit_oid,
                tree=final_checkpoint["tree_oid"],
                config_sha256=final_checkpoint["config_sha256"],
                protected_config_sha256=protected_config_sha256,
                refs=refs_after_commit,
                origin=origin,
                context="commit hook",
            )
            if finalization_git_output(
                target, "rev-parse", f"refs/heads/{default_branch}"
            ) != delivery_baseline["head_oid"]:
                raise AdapterError(f"local {default_branch} drifted before fast-forward")
            if validated_origin(target) != origin:
                raise AdapterError("target origin changed before local fast-forward")
            if remote_oid(target, default_branch, origin) != baseline_remote:
                raise AdapterError(f"remote {default_branch} drifted before local fast-forward")
            command(
                ["git", "-C", str(target), "switch", default_branch],
                env=finalization_git_environment(),
            )
            command(
                ["git", "-C", str(target), "merge", "--ff-only", commit_oid],
                env=finalization_git_environment(),
            )
            state["local_default_fast_forwarded"] = True
            refs_after_fast_forward = expected_refs(
                refs_after_commit,
                {task_ref: commit_oid, default_ref: commit_oid},
            )
            assert_repository_state(
                target,
                branch=default_branch,
                head=commit_oid,
                tree=final_checkpoint["tree_oid"],
                config_sha256=final_checkpoint["config_sha256"],
                protected_config_sha256=protected_config_sha256,
                refs=refs_after_fast_forward,
                origin=origin,
                context="checkout/merge hook",
            )
            push_origin = validated_origin(target)
            if push_origin != origin:
                raise AdapterError("push destination changed after final checks")
            if remote_oid(target, default_branch, push_origin) != baseline_remote:
                raise AdapterError(f"remote {default_branch} drifted immediately before push")
            push = finalization_git_with_auth(
                [
                    "-C", str(target), "push", "--no-follow-tags", push_origin,
                    f"refs/heads/{default_branch}:refs/heads/{default_branch}",
                ],
                check=False,
            )
            if push.returncode:
                raise AdapterError(
                    (push.stderr or push.stdout).strip() or f"git push {default_branch} failed"
                )
            state["pushed"] = True
            return {
                "plan_id": plan_id,
                "target": str(target),
                "default_branch": default_branch,
                "commit_oid": commit_oid,
                "final_tree": final_checkpoint["tree_oid"],
                "partial_state": finalization_state(target, state),
            }
    except (AdapterError, OSError, subprocess.CalledProcessError) as exc:
        raise FinalizationError(str(exc), finalization_state(target, state)) from exc


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
        checks["agent_auth"] = cursor_agent_authenticated()
        checks["policy"] = policy["schema_version"] == lock["contract_version"]
        checks["harness"] = True
        return {"harness_revision": lock["revision"], "runner_result": {"checks": checks}}, (
            0 if all(checks.values()) else 1
        )
    if args.command == "preflight-plan":
        policy = load_policy()
        plan = resolve_plan_path(args.plan)
        for record_id in (args.strip_completed, args.recover_scope_from):
            if record_id is not None and not PLAN_ID_RE.fullmatch(record_id):
                raise AdapterError("approval provenance plan ID is invalid")
        wrapped, code = delegate(
            "validate-plan",
            [
                "--plan", str(plan),
                *delivery_flags(args),
                *forwarding_flags(
                    args,
                    default_timeout=policy["default_timeout_seconds"],
                    policy=policy,
                    include_model_flags=False,
                ),
            ],
        )
        if code:
            return wrapped, code
        normalized = wrapped["runner_result"].get("normalized_spec")
        if not isinstance(normalized, dict) or normalized.get("delivery_intent") != args.delivery_intent:
            raise AdapterError("runner preflight omitted the approved delivery intent")
        target = resolve_target(args.target, policy)
        wrapped["runner_result"]["approval_context"] = preflight_delivery_context(
            target,
            policy,
            args.delivery_intent,
        )
        provenance = None
        if args.strip_completed is not None:
            provenance = {
                "mode": "strip_completed",
                "prior_plan_id": args.strip_completed,
            }
        elif args.recover_scope_from is not None:
            provenance = {
                "mode": "recover_scope",
                "prior_plan_id": args.recover_scope_from,
            }
        wrapped["runner_result"]["approval_context"]["provenance"] = provenance
        return wrapped, code
    if args.command == "finalize-plan":
        lock = load_lock()
        return {
            "harness_revision": lock["revision"],
            "runner_result": finalize_plan(
                args.plan_id,
                args.message,
                args.approve_commit,
                args.approve_push,
            ),
        }, 0
    if args.command in {"status", "show", "list"}:
        extra = [] if args.command == "list" else [args.record_id]
        return delegate(args.command, extra)
    if args.command == "resume":
        policy = load_policy()
        extra = [args.record_id]
        if args.restart_current_stage:
            extra.append("--restart-current-stage")
        if args.guidance:
            extra += ["--guidance", args.guidance]
        extra += forwarding_flags(args, policy=policy)
        return delegate("resume", extra)
    if args.command == "cancel":
        return delegate("cancel", [args.record_id, "--reason", args.reason])

    policy = load_policy()
    target = resolve_target(args.target, policy)
    if args.command == "run-plan":
        plan = resolve_plan_path(args.plan)
        continuation: list[str] = []
        if args.strip_completed is not None:
            continuation = ["--strip-completed", args.strip_completed]
        elif args.recover_scope_from is not None:
            continuation = ["--recover-scope-from", args.recover_scope_from]
        return delegate(
            "run-plan",
            [
                "--target", str(target), "--plan", str(plan),
                *delivery_flags(args),
                *continuation,
                *forwarding_flags(args, default_timeout=policy["default_timeout_seconds"], policy=policy),
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
            phase["routing"] = (
                routing_object(args.routing_json)
                if args.routing_json
                else automatic_routing(args.mode)
            )
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({"schema_version": 2, "phases": [phase]}, stream)
            return delegate(
                "run-plan",
                [
                    "--target", str(target), "--plan", str(plan_path),
                    *delivery_flags(args),
                    *forwarding_flags(args, default_timeout=policy["default_timeout_seconds"], policy=policy),
                ],
            )
        finally:
            plan_path.unlink(missing_ok=True)
    extra = ["--target", str(target), "--prompt", args.prompt]
    if args.routing_json:
        raise AdapterError("--routing-json requires --verification-json")
    if args.mode:
        extra += ["--mode", args.mode]
    if args.verify:
        extra += ["--verify", args.verify]
    return delegate(
        "run",
        [
            *extra,
            *delivery_flags(args),
            *forwarding_flags(args, default_timeout=policy["default_timeout_seconds"], policy=policy),
        ],
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
        if isinstance(exc, FinalizationError):
            error["partial_state"] = exc.partial_state
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
