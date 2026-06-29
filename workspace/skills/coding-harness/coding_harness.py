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


def build_prompt(task: str, mode: str) -> str:
    mode_text = "Use autonomous mode." if mode == "autonomous" else "Use planning mode."
    return f"""You are running under Kenny's agent harness.

First read and follow:
- {HARNESS_DIR / "AGENTS.md"}
- relevant files under {HARNESS_DIR / "skills"}
- relevant files under {HARNESS_DIR / "rules"}

Project-local instructions in the target repo override the harness when they conflict.

{mode_text}

Kenny's request:
{task}
"""


def run_harness(args: argparse.Namespace) -> None:
    refresh_harness(args)
    target = resolve_target(args.target)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    prompt = build_prompt(args.prompt, args.mode)
    command = [
        "agent",
        "--print",
        "--trust",
        "--workspace",
        str(target),
        prompt,
    ]
    if args.mode == "plan":
        command.insert(1, "--mode=plan")

    completed = run(command, check=False)
    output = {
        "target": str(target),
        "harness": str(HARNESS_DIR),
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }
    print_json(output)
    if completed.returncode != 0:
        sys.exit(completed.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Route Mira coding work through Kenny's agent harness.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check-config")
    check_parser.set_defaults(func=check_config)

    refresh_parser = subparsers.add_parser("refresh-harness")
    refresh_parser.set_defaults(func=refresh_harness)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--target", required=True, help="Container-visible path, GitHub URL, or owner/repo slug.")
    run_parser.add_argument("--prompt", required=True, help="Kenny's coding request.")
    run_parser.add_argument("--mode", choices=("autonomous", "plan"), default="autonomous")
    run_parser.set_defaults(func=run_harness)

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
