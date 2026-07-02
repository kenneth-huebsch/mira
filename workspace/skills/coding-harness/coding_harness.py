#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HARNESS_REPO = "https://github.com/kenneth-huebsch/agent.git"
WORKSPACE = Path(os.environ.get("OPENCLAW_WORKSPACE", "/home/node/.openclaw/workspace"))
RUNTIME_REPOS = WORKSPACE / "runtime" / "repos"
HARNESS_DIR = RUNTIME_REPOS / "agent"
# The harness owns all execution (prompts, gates, handoffs, review loop, phased
# scheduling, run records). Mira only shells out to this runner.
RUNNER = HARNESS_DIR / "scripts" / "agent_run.py"
RUNS_DIR = WORKSPACE / "runtime" / "coding-harness-runs"
os.environ.setdefault("GH_CONFIG_DIR", "/home/node/.openclaw/gh")
MIRA_MARKERS = {
    "mira",
    "kenneth-huebsch/mira",
    "https://github.com/kenneth-huebsch/mira",
    "https://github.com/kenneth-huebsch/mira.git",
    "git@github.com:kenneth-huebsch/mira.git",
}


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=check)


def print_json(data: dict) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def require_command(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise RuntimeError(f"missing required command: {name}")
    return found


def ensure_gh_git_auth() -> None:
    run(["gh", "auth", "setup-git"])


def check_config(_: argparse.Namespace) -> None:
    status: dict[str, object] = {
        "runtime_repos": str(RUNTIME_REPOS),
        "harness_dir": str(HARNESS_DIR),
        "checks": {},
    }
    for command in ("git", "gh", "agent"):
        status["checks"][command] = require_command(command)

    gh_status = run(["gh", "auth", "status"], check=False)
    status["checks"]["gh_auth"] = gh_status.returncode == 0
    if gh_status.returncode != 0:
        status["gh_auth_error"] = (gh_status.stderr or gh_status.stdout).strip()

    agent_status = run(["agent", "status"], check=False)
    agent_status_text = (agent_status.stderr or agent_status.stdout).strip()
    cursor_auth_ok = agent_status.returncode == 0 and "not logged in" not in agent_status_text.lower()
    status["checks"]["cursor_agent_auth"] = cursor_auth_ok
    if not cursor_auth_ok:
        status["cursor_agent_auth_error"] = agent_status_text or "Cursor CLI is not authenticated"

    repo_view = run(["gh", "repo", "view", "kenneth-huebsch/agent", "--json", "name"], check=False)
    status["checks"]["harness_repo_access"] = repo_view.returncode == 0
    if repo_view.returncode != 0:
        status["harness_repo_error"] = (repo_view.stderr or repo_view.stdout).strip()

    status["runner"] = str(RUNNER)
    status["checks"]["harness_runner"] = RUNNER.exists()
    if not RUNNER.exists():
        status["harness_runner_error"] = f"{RUNNER} not found; run refresh-harness first"

    print_json(status)
    if not all(status["checks"].values()):
        sys.exit(1)
    ensure_gh_git_auth()


def refresh_harness(_: argparse.Namespace) -> None:
    RUNTIME_REPOS.mkdir(parents=True, exist_ok=True)
    ensure_gh_git_auth()
    if not HARNESS_DIR.exists():
        run(["gh", "repo", "clone", "kenneth-huebsch/agent", str(HARNESS_DIR)])
    else:
        run(["git", "fetch", "--prune", "origin"], cwd=HARNESS_DIR)
        run(["git", "switch", "main"], cwd=HARNESS_DIR)
        run(["git", "pull", "--ff-only"], cwd=HARNESS_DIR)

    commit = run(["git", "rev-parse", "--short", "HEAD"], cwd=HARNESS_DIR).stdout.strip()
    print_json({"harness_dir": str(HARNESS_DIR), "commit": commit})


def repo_name_from_target(target: str) -> str:
    clean = target.rstrip("/")
    if clean.endswith(".git"):
        clean = clean[:-4]
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", clean.split("/")[-1])


def is_mira_target(target: str) -> bool:
    lowered = target.strip().lower().rstrip("/")
    if lowered in MIRA_MARKERS:
        return True
    try:
        resolved = Path(target).expanduser().resolve()
    except OSError:
        return False
    return str(resolved).startswith("/home/kenny/mira") or resolved.name.lower() == "mira"


def resolve_target(target: str) -> Path:
    if is_mira_target(target):
        raise RuntimeError("Mira self-work is out of scope for coding-harness; use a future Mira self-work skill.")

    path = Path(target).expanduser()
    if path.exists():
        resolved = path.resolve()
        if not (resolved / ".git").exists():
            raise RuntimeError(f"target path is not a git repo: {resolved}")
        return resolved

    RUNTIME_REPOS.mkdir(parents=True, exist_ok=True)
    name = repo_name_from_target(target)
    if name == "mira":
        raise RuntimeError("Mira self-work is out of scope for coding-harness.")
    destination = RUNTIME_REPOS / name
    if destination.exists():
        run(["git", "fetch", "--prune", "origin"], cwd=destination)
        current_branch = run(["git", "branch", "--show-current"], cwd=destination).stdout.strip()
        if current_branch:
            run(["git", "pull", "--ff-only"], cwd=destination)
        return destination

    clone_target = target
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", target):
        clone_target = target
    elif target.startswith("https://github.com/") or target.startswith("git@github.com:"):
        clone_target = target
    else:
        raise RuntimeError("target must be an existing path, GitHub URL, or owner/repo slug")

    run(["gh", "repo", "clone", clone_target, str(destination)])
    return destination


def delegate(subcommand: str, extra_args: list[str]) -> None:
    """Shell out to the harness runner, streaming its JSON and propagating exit.

    The harness owns prompts, gates, handoffs, the review loop, phased
    scheduling, and run records. Mira only sets ``AGENT_RUN_HOME`` so records
    land under her ignored runtime and forwards already-resolved arguments.
    """
    if not RUNNER.exists():
        raise RuntimeError(f"harness runner not found at {RUNNER}; run refresh-harness first")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["AGENT_RUN_HOME"] = str(RUNS_DIR)
    command = [sys.executable or "python3", str(RUNNER), subcommand, *extra_args]
    # Flush our own buffered output (e.g. refresh-harness JSON) before the child
    # streams, so the combined output stays in call order under a pipe.
    sys.stdout.flush()
    sys.stderr.flush()
    completed = subprocess.run(command, env=env)
    if completed.returncode != 0:
        sys.exit(completed.returncode)


def add_review_flags(sub: argparse.ArgumentParser) -> None:
    """Forward-only review flags: no defaults so Mira never forks gate semantics."""
    sub.add_argument("--no-review", action="store_true", help="Forward --no-review to disable the harness review loop.")
    sub.add_argument(
        "--review-threshold",
        choices=("blocking", "high", "medium", "low"),
        default=None,
        help="Forward the harness review threshold (default lives in the harness).",
    )
    sub.add_argument(
        "--review-max-rounds",
        type=int,
        default=None,
        help="Forward the harness max fix rounds (default lives in the harness).",
    )


def forwarded_review_args(args: argparse.Namespace) -> list[str]:
    extra: list[str] = []
    if getattr(args, "no_review", False):
        extra.append("--no-review")
    if getattr(args, "review_threshold", None):
        extra += ["--review-threshold", args.review_threshold]
    if getattr(args, "review_max_rounds", None) is not None:
        extra += ["--review-max-rounds", str(args.review_max_rounds)]
    return extra


def run_harness(args: argparse.Namespace) -> None:
    refresh_harness(args)
    target = resolve_target(args.target)
    extra = ["--target", str(target), "--prompt", args.prompt]
    if args.mode:
        extra += ["--mode", args.mode]
    if args.verify:
        extra += ["--verify", args.verify]
    if args.timeout is not None:
        extra += ["--timeout", str(args.timeout)]
    if args.dry_run:
        extra.append("--dry-run")
    extra += forwarded_review_args(args)
    delegate("run", extra)


def run_plan(args: argparse.Namespace) -> None:
    refresh_harness(args)
    target = resolve_target(args.target)
    extra = ["--target", str(target), "--plan", args.plan]
    if args.timeout is not None:
        extra += ["--timeout", str(args.timeout)]
    if args.dry_run:
        extra.append("--dry-run")
    extra += forwarded_review_args(args)
    delegate("run-plan", extra)


def status_cmd(args: argparse.Namespace) -> None:
    delegate("status", [args.run_id])


def list_cmd(_: argparse.Namespace) -> None:
    delegate("list", [])


def show_cmd(args: argparse.Namespace) -> None:
    delegate("show", [args.run_id])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resolve/clone a non-Mira target and delegate execution to Kenny's agent harness runner."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check-config")
    check_parser.set_defaults(func=check_config)

    refresh_parser = subparsers.add_parser("refresh-harness")
    refresh_parser.set_defaults(func=refresh_harness)

    run_parser = subparsers.add_parser("run", help="Resolve/clone target, then delegate a single harness run.")
    run_parser.add_argument("--target", required=True, help="Container-visible path, GitHub URL, or owner/repo slug.")
    run_parser.add_argument("--prompt", required=True, help="Kenny's coding request.")
    run_parser.add_argument("--mode", choices=("autonomous", "plan"), default=None, help="Forward the child mode (harness default is autonomous).")
    run_parser.add_argument("--verify", default=None, help="Forward a verify shell command (part of the harness green gate).")
    run_parser.add_argument("--timeout", type=int, default=None, help="Forward the per-run wall-clock ceiling in seconds.")
    run_parser.add_argument("--dry-run", action="store_true", help="Forward --dry-run: build the run record without invoking agent.")
    add_review_flags(run_parser)
    run_parser.set_defaults(func=run_harness)

    plan_parser = subparsers.add_parser("run-plan", help="Resolve/clone target, then delegate an approved multi-phase plan.")
    plan_parser.add_argument("--target", required=True, help="Container-visible path, GitHub URL, or owner/repo slug.")
    plan_parser.add_argument("--plan", required=True, help="Path to an approved phase-spec JSON, e.g. runtime/coding-harness-plans/<name>.json.")
    plan_parser.add_argument("--timeout", type=int, default=None, help="Forward the per-phase wall-clock ceiling in seconds.")
    plan_parser.add_argument("--dry-run", action="store_true", help="Forward --dry-run: build records for all phases without invoking agent.")
    add_review_flags(plan_parser)
    plan_parser.set_defaults(func=run_plan)

    status_parser = subparsers.add_parser("status", help="Passthrough: print a run's status.json.")
    status_parser.add_argument("run_id")
    status_parser.set_defaults(func=status_cmd)

    list_parser = subparsers.add_parser("list", help="Passthrough: list run records under Mira's runtime.")
    list_parser.set_defaults(func=list_cmd)

    show_parser = subparsers.add_parser("show", help="Passthrough: show status, handoff, and git snapshot for a run-id.")
    show_parser.add_argument("run_id")
    show_parser.set_defaults(func=show_cmd)

    args = parser.parse_args()
    try:
        args.func(args)
    except subprocess.CalledProcessError as exc:
        print_json({
            "error": "command failed",
            "command": exc.cmd,
            "exit_code": exc.returncode,
            "stdout": exc.stdout,
            "stderr": exc.stderr,
        })
        sys.exit(exc.returncode)
    except Exception as exc:
        print_json({"error": str(exc)})
        sys.exit(1)


if __name__ == "__main__":
    main()
