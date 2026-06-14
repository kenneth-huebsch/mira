#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from skills_catalog import list_dripr_repo_skills


WORKSPACE_ROOT = Path(os.environ.get("OPENCLAW_WORKSPACE_DIR", "/home/node/.openclaw/workspace"))
OPENCLAW_ROOT = WORKSPACE_ROOT.parent
DEFAULT_ENV_FILE = OPENCLAW_ROOT / "secrets" / "dripr-coding.env"
DEFAULT_REPOS_ROOT = WORKSPACE_ROOT / "runtime" / "repos"
DEFAULT_DRIPR_REPO = DEFAULT_REPOS_ROOT / "dripr"
DEFAULT_AGENT_REPO = DEFAULT_REPOS_ROOT / "agent"
DEFAULT_RUN_ROOT = WORKSPACE_ROOT / "runtime" / "capability-runs" / "dripr-coding"
DEFAULT_GIT_CREDENTIALS_FILE = OPENCLAW_ROOT / "secrets" / "dripr-git-credentials"
DEFAULT_DRIPR_URL = "https://github.com/kenneth-huebsch/dripr.git"
DEFAULT_AGENT_URL = "https://github.com/kenneth-huebsch/agent.git"
DEFAULT_GIT_USER_NAME = "mira-dripr-coding-agent"
DEFAULT_GIT_USER_EMAIL = "mira-dripr-coding-agent@users.noreply.github.com"
DEFAULT_TIMEOUT_SECONDS = 7200
MAX_OUTPUT_CHARS = 8000
TITLE_RE = re.compile(r"[^a-zA-Z0-9 ._:-]+")
URL_RE = re.compile(r"https://github\.com/[^\s)]+/pull/\d+")


class SetupError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dripr coding prompt-to-PR helper.")
    parser.add_argument("--env-file", default=os.environ.get("DRIPR_CODING_ENV", str(DEFAULT_ENV_FILE)))
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("check-config", help="Inspect tools, auth, and repo readiness without changing repos.")
    subparsers.add_parser("prepare-repos", help="Clone or refresh Dripr and agent harness repos.")
    subparsers.add_parser("list-skills", help="List Dripr repo skills from .agent/skills/*/SKILL.md frontmatter.")

    runner = subparsers.add_parser("run-prompt-pr", help="Run Dripr's prompt-to-PR wrapper.")
    prompt_source = runner.add_mutually_exclusive_group(required=True)
    prompt_source.add_argument("--prompt")
    prompt_source.add_argument("--prompt-file")
    runner.add_argument("--title")
    runner.add_argument("--kind", choices=["bug", "refactor", "feature", "test", "chore"], default="chore")
    runner.add_argument("--touches")
    runner.add_argument("--slug")
    runner.add_argument("--dry-run", action="store_true")
    runner.add_argument("--timeout-seconds", type=int)

    return parser.parse_args()


def parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    key, value = stripped.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not key:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        value = value[1:-1]
    return key, value


def load_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        parsed = parse_env_line(line)
        if parsed:
            key, value = parsed
            values[key] = value
    return values


def env_value(values: dict[str, str], key: str, default: str) -> str:
    return os.environ.get(key) or values.get(key) or default


def positive_int(value: int | str | None, default: int, max_value: int) -> int:
    try:
        parsed = int(value or default)
    except ValueError:
        return default
    return max(1, min(parsed, max_value))


def path_value(values: dict[str, str], key: str, default: Path) -> Path:
    return Path(env_value(values, key, str(default)))


def repos_root(values: dict[str, str]) -> Path:
    return path_value(values, "DRIPR_CODING_REPOS_ROOT", DEFAULT_REPOS_ROOT)


def dripr_repo(values: dict[str, str]) -> Path:
    return path_value(values, "DRIPR_REPO_PATH", repos_root(values) / "dripr")


def agent_repo(values: dict[str, str]) -> Path:
    return path_value(values, "AGENT_HARNESS_ROOT", repos_root(values) / "agent")


def dripr_url(values: dict[str, str]) -> str:
    return env_value(values, "DRIPR_REPO_URL", DEFAULT_DRIPR_URL)


def agent_url(values: dict[str, str]) -> str:
    return env_value(values, "AGENT_REPO_URL", DEFAULT_AGENT_URL)


def cursor_bin(values: dict[str, str]) -> str:
    return env_value(values, "CURSOR_BIN", "agent")


def run_root(values: dict[str, str]) -> Path:
    return path_value(values, "DRIPR_CODING_RUN_ROOT", DEFAULT_RUN_ROOT)


def git_credentials_file(values: dict[str, str]) -> Path:
    return path_value(values, "DRIPR_GIT_CREDENTIALS_FILE", DEFAULT_GIT_CREDENTIALS_FILE)


def git_user_name(values: dict[str, str]) -> str:
    return env_value(values, "DRIPR_CODING_GIT_USER_NAME", DEFAULT_GIT_USER_NAME)


def git_user_email(values: dict[str, str]) -> str:
    return env_value(values, "DRIPR_CODING_GIT_USER_EMAIL", DEFAULT_GIT_USER_EMAIL)


def git_command(values: dict[str, str], *args: str) -> list[str]:
    credentials_file = git_credentials_file(values)
    if credentials_file.exists():
        return ["git", "-c", f"credential.helper=store --file={credentials_file}", *args]
    return ["git", *args]


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def output_tail(text: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    lines = text.splitlines()
    tail = "\n".join(lines[-120:])
    if len(tail) <= max_chars:
        return tail
    return tail[-max_chars:]


def run_command(
    command: list[str],
    cwd: Path | None = None,
    timeout_seconds: int = 120,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout_seconds,
        check=False,
    )
    result = {
        "command": " ".join(command),
        "cwd": str(cwd) if cwd else None,
        "exit_code": completed.returncode,
        "output_tail": output_tail(completed.stdout),
    }
    if check and completed.returncode != 0:
        raise SetupError(f"command failed: {result['command']}\n{result['output_tail']}")
    return result


def require_git_checkout(path: Path, name: str) -> None:
    if not path.exists():
        raise SetupError(f"missing {name} repo: {path}")
    if not (path / ".git").exists():
        raise SetupError(f"{name} repo path is not a git checkout: {path}")


def git_value(path: Path, command: list[str]) -> str | None:
    try:
        result = run_command(command, path, 30, check=False)
    except Exception:
        return None
    if result["exit_code"] != 0:
        return None
    return str(result["output_tail"]).strip()


def repo_summary(path: Path, name: str) -> dict[str, Any]:
    exists = path.exists()
    is_git = (path / ".git").exists()
    summary: dict[str, Any] = {
        "name": name,
        "path": str(path),
        "exists": exists,
        "is_git_checkout": is_git,
    }
    if not is_git:
        return summary
    status = git_value(path, ["git", "status", "--short"]) or ""
    summary.update(
        {
            "branch": git_value(path, ["git", "branch", "--show-current"]),
            "commit": git_value(path, ["git", "rev-parse", "--short", "HEAD"]),
            "origin": git_value(path, ["git", "remote", "get-url", "origin"]),
            "dirty": bool(status),
            "dirty_summary": status.splitlines()[:20],
        }
    )
    return summary


def check_cursor_auth(values: dict[str, str]) -> dict[str, Any]:
    command = cursor_bin(values)
    if not command_exists(command):
        return {"command": command, "available": False, "authenticated": False}
    if os.environ.get("CURSOR_API_KEY") or values.get("CURSOR_API_KEY"):
        return {"command": command, "available": True, "authenticated": True, "auth_source": "CURSOR_API_KEY"}
    status = run_command([command, "status"], timeout_seconds=30, check=False)
    return {
        "command": command,
        "available": True,
        "authenticated": status["exit_code"] == 0,
        "status_exit_code": status["exit_code"],
    }


def check_gh_auth() -> dict[str, Any]:
    if not command_exists("gh"):
        return {"available": False, "authenticated": False}
    status = run_command(["gh", "auth", "status"], timeout_seconds=30, check=False)
    return {"available": True, "authenticated": status["exit_code"] == 0, "status_exit_code": status["exit_code"]}


def check_config(values: dict[str, str]) -> dict[str, Any]:
    dripr = dripr_repo(values)
    agent = agent_repo(values)
    runner = dripr / ".agent" / "scripts" / "run-prompt-pr.sh"
    integration_env = dripr / "env" / "integration.env"
    harness_agents = agent / "AGENTS.md"
    harness_skills = agent / "skills"

    issues: list[str] = []
    if not command_exists("git"):
        issues.append("git is not on PATH")
    cursor = check_cursor_auth(values)
    if not cursor["available"]:
        issues.append(f"Cursor CLI command is not on PATH: {cursor['command']}")
    elif not cursor["authenticated"]:
        issues.append("Cursor CLI is not authenticated")
    gh = check_gh_auth()
    if not gh["available"]:
        issues.append("gh is not on PATH")
    elif not gh["authenticated"]:
        issues.append("gh is not authenticated")
    if dripr.exists() and not runner.exists():
        issues.append(f"Dripr prompt runner is missing: {runner}")
    if dripr.exists() and not integration_env.exists():
        issues.append(f"Dripr integration env is missing: {integration_env}")
    if agent.exists() and (not harness_agents.exists() or not harness_skills.is_dir()):
        issues.append(f"Agent harness must contain AGENTS.md and skills/: {agent}")

    return {
        "status": "OK" if not issues else "NEEDS_ATTENTION",
        "issues": issues,
        "repos_root": str(repos_root(values)),
        "dripr_url": dripr_url(values),
        "agent_url": agent_url(values),
        "git_credentials_file_exists": git_credentials_file(values).exists(),
        "cursor": cursor,
        "github_cli": gh,
        "dripr": repo_summary(dripr, "dripr"),
        "agent": repo_summary(agent, "agent"),
        "runner_exists": runner.exists(),
        "integration_env_exists": integration_env.exists(),
        "agent_harness_shape_ok": harness_agents.exists() and harness_skills.is_dir(),
    }


def clone_if_missing(values: dict[str, str], path: Path, url: str, name: str) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    if path.exists():
        require_git_checkout(path, name)
        return operations
    path.parent.mkdir(parents=True, exist_ok=True)
    operations.append(run_command(git_command(values, "clone", url, str(path)), path.parent, 1800))
    return operations


def configure_git_for_runner(values: dict[str, str], path: Path) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    credentials_file = git_credentials_file(values)
    if credentials_file.exists():
        operations.append(run_command(["git", "config", "credential.helper", f"store --file={credentials_file}"], path, 30))
    operations.extend([
        run_command(["git", "config", "user.name", git_user_name(values)], path, 30),
        run_command(["git", "config", "user.email", git_user_email(values)], path, 30),
    ])
    return operations


def refresh_repo(values: dict[str, str], path: Path, name: str) -> list[dict[str, Any]]:
    require_git_checkout(path, name)
    operations: list[dict[str, Any]] = []
    operations.extend(configure_git_for_runner(values, path))
    operations.extend([
        run_command(["git", "reset", "--hard"], path, 300),
        run_command(["git", "clean", "-fd"], path, 300),
        run_command(["git", "switch", "main"], path, 300),
        run_command(git_command(values, "pull", "--ff-only"), path, 1800),
    ])
    return operations


def prepare_repos(values: dict[str, str]) -> dict[str, Any]:
    dripr = dripr_repo(values)
    agent = agent_repo(values)
    operations: list[dict[str, Any]] = []
    operations.extend(clone_if_missing(values, dripr, dripr_url(values), "dripr"))
    operations.extend(refresh_repo(values, dripr, "dripr"))
    operations.extend(clone_if_missing(values, agent, agent_url(values), "agent"))
    operations.extend(refresh_repo(values, agent, "agent"))
    return {
        "status": "OK",
        "operations": operations,
        "dripr": repo_summary(dripr, "dripr"),
        "agent": repo_summary(agent, "agent"),
    }


def clean_title(value: str) -> str:
    title = TITLE_RE.sub("", value).strip()
    return title[:120] or "Dripr coding task"


def title_from_prompt(prompt: str) -> str:
    for line in prompt.splitlines():
        stripped = line.strip()
        if stripped:
            return clean_title(stripped)
    return "Dripr coding task"


def slug_from_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:64].rstrip("-") or "dripr-coding-task"


def read_prompt(args: argparse.Namespace) -> tuple[str, Path | None]:
    if args.prompt_file:
        path = Path(args.prompt_file)
        if not path.exists():
            raise SetupError(f"prompt file not found: {path}")
        prompt = path.read_text()
        return prompt, path
    prompt = args.prompt or ""
    return prompt, None


def write_prompt_file(values: dict[str, str], prompt: str, title: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = slug_from_title(title)
    directory = run_root(values) / f"{timestamp}-{slug}"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "prompt.md"
    path.write_text(prompt.rstrip() + "\n")
    return path


def review_must_fix_items(review_path: Path) -> list[str]:
    if not review_path.exists():
        return []
    items: list[str] = []
    in_section = False
    for line in review_path.read_text().splitlines():
        stripped = line.strip()
        if stripped == "## MUST_FIX":
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section or not stripped or stripped == "None.":
            continue
        items.append(stripped.removeprefix("- ").strip())
    return items


def run_prompt_pr(values: dict[str, str], args: argparse.Namespace) -> dict[str, Any]:
    dripr = dripr_repo(values)
    agent = agent_repo(values)
    require_git_checkout(dripr, "dripr")
    require_git_checkout(agent, "agent")

    runner = dripr / ".agent" / "scripts" / "run-prompt-pr.sh"
    if not runner.exists():
        raise SetupError(f"Dripr prompt runner is missing: {runner}")
    if not (agent / "AGENTS.md").exists() or not (agent / "skills").is_dir():
        raise SetupError(f"agent harness must contain AGENTS.md and skills/: {agent}")

    configure_git_for_runner(values, dripr)

    prompt, existing_prompt_file = read_prompt(args)
    if not prompt.strip():
        raise SetupError("prompt is empty")
    title = clean_title(args.title) if args.title else title_from_prompt(prompt)
    prompt_file = existing_prompt_file or write_prompt_file(values, prompt, title)

    command = [
        "bash",
        str(runner),
        "--harness-root",
        str(agent),
        "--title",
        title,
        "--kind",
        args.kind,
        "--prompt-file",
        str(prompt_file),
    ]
    if args.touches:
        command.extend(["--touches", args.touches])
    if args.slug:
        command.extend(["--slug", args.slug])
    if args.dry_run:
        command.append("--dry-run")

    runner_env = os.environ.copy()
    runner_env["AGENT_HARNESS_ROOT"] = str(agent)
    for key in ["CURSOR_API_KEY", "CURSOR_BIN", "GH_TOKEN", "GITHUB_TOKEN", "GH_CONFIG_DIR"]:
        if key in values and key not in runner_env:
            runner_env[key] = values[key]

    timeout_seconds = positive_int(
        args.timeout_seconds or env_value(values, "DRIPR_CODING_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)),
        DEFAULT_TIMEOUT_SECONDS,
        24 * 60 * 60,
    )
    result = run_command(command, dripr, 120 if args.dry_run else timeout_seconds, check=False, env=runner_env)
    pr_urls = sorted(set(URL_RE.findall(str(result["output_tail"]))))
    runner_slug = args.slug or slug_from_title(title)
    review_path = dripr / ".agent" / "overnight" / f"review-{runner_slug}.md"
    status = "OK" if result["exit_code"] == 0 else "FAILED"
    return {
        "status": status,
        "dry_run": bool(args.dry_run),
        "title": title,
        "runner_slug": runner_slug,
        "kind": args.kind,
        "touches": args.touches,
        "prompt_file": str(prompt_file),
        "harness_root": str(agent),
        "command": result["command"],
        "exit_code": result["exit_code"],
        "pr_urls": pr_urls,
        "review_path": str(review_path) if review_path.exists() else None,
        "review_must_fix": review_must_fix_items(review_path),
        "output_tail": result["output_tail"],
    }


def print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def main() -> int:
    args = parse_args()
    values = load_env(Path(args.env_file))
    try:
        if args.command == "check-config":
            print_json(check_config(values))
            return 0
        if args.command == "prepare-repos":
            print_json(prepare_repos(values))
            return 0
        if args.command == "list-skills":
            print_json(list_dripr_repo_skills(dripr_repo(values)))
            return 0
        if args.command == "run-prompt-pr":
            result = run_prompt_pr(values, args)
            print_json(result)
            return 0 if result["status"] == "OK" else 1
    except subprocess.TimeoutExpired as error:
        print_json({"status": "FAILED", "error": f"command timed out after {error.timeout} seconds"})
        return 1
    except SetupError as error:
        print_json({"status": "FAILED", "error": str(error)})
        return 1
    except Exception as error:
        print_json({"status": "FAILED", "error": f"{type(error).__name__}: {error}"})
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
