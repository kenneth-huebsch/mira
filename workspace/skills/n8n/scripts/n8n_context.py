#!/usr/bin/env python3
"""Refresh and inspect Mira's runtime checkout of Kenny's n8n repo."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


REPO_URL = "https://github.com/kenneth-huebsch/n8n"
DEFAULT_REPO_DIR = Path(
    os.getenv("N8N_CONTEXT_REPO_DIR", "/home/node/.openclaw/workspace/runtime/repos/n8n")
)
REQUIRED_FILES = [
    "AGENTS.md",
    "README.md",
    "compose.yaml",
    ".agents/skills/n8n-infrastructure/SKILL.md",
]


def run(command: List[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def git_available() -> bool:
    return shutil.which("git") is not None


def clone_repo(repo_dir: Path) -> None:
    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("gh"):
        run(["gh", "repo", "clone", "kenneth-huebsch/n8n", str(repo_dir)])
        return
    run(["git", "clone", REPO_URL, str(repo_dir)])


def refresh_repo(repo_dir: Path) -> Dict[str, Any]:
    if not git_available():
        raise RuntimeError("git is required to refresh the n8n context repo")

    if not repo_dir.exists():
        clone_repo(repo_dir)
        action = "cloned"
    elif not (repo_dir / ".git").is_dir():
        raise RuntimeError(f"existing path is not a git checkout: {repo_dir}")
    else:
        status = run(["git", "status", "--short"], cwd=repo_dir)
        if status:
            raise RuntimeError(
                "n8n context repo has local changes; inspect it before refreshing"
            )
        run(["git", "fetch", "--prune", "origin"], cwd=repo_dir)
        branch = run(["git", "branch", "--show-current"], cwd=repo_dir) or "main"
        run(["git", "pull", "--ff-only", "origin", branch], cwd=repo_dir)
        action = "updated"

    return repo_status(repo_dir, action=action)


def repo_status(repo_dir: Path, action: str = "checked") -> Dict[str, Any]:
    exists = repo_dir.exists()
    git_checkout = (repo_dir / ".git").is_dir()
    missing = [path for path in REQUIRED_FILES if not (repo_dir / path).is_file()]
    revision = None

    if git_checkout:
        try:
            revision = run(["git", "rev-parse", "--short", "HEAD"], cwd=repo_dir)
        except subprocess.CalledProcessError:
            revision = None

    return {
        "action": action,
        "repo_url": REPO_URL,
        "repo_dir": str(repo_dir),
        "exists": exists,
        "git_checkout": git_checkout,
        "revision": revision,
        "required_files": REQUIRED_FILES,
        "missing_required_files": missing,
        "ready": exists and git_checkout and not missing,
    }


def print_reading_list(repo_dir: Path) -> None:
    for rel_path in REQUIRED_FILES:
        print(repo_dir / rel_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage Mira's n8n context repo")
    parser.add_argument(
        "action",
        choices=["check-context", "refresh-repo", "reading-list"],
        help="Context operation to run",
    )
    parser.add_argument(
        "--repo-dir",
        default=str(DEFAULT_REPO_DIR),
        help="Runtime checkout directory for kenneth-huebsch/n8n",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    args = parser.parse_args()

    repo_dir = Path(args.repo_dir).expanduser()

    try:
        if args.action == "refresh-repo":
            result = refresh_repo(repo_dir)
        elif args.action == "check-context":
            result = repo_status(repo_dir)
        else:
            print_reading_list(repo_dir)
            return 0

        print(json.dumps(result, indent=2 if args.pretty else None))
        return 0 if result.get("ready") else 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
