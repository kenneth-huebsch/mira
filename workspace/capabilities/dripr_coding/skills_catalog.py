#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
FIELD_RE = re.compile(r"^([A-Za-z0-9_-]+):\s*(.+)$")


def parse_frontmatter(text: str) -> dict[str, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        parsed = FIELD_RE.match(line.strip())
        if parsed:
            key, value = parsed.groups()
            fields[key] = value.strip().strip('"').strip("'")
    return fields


def list_dripr_repo_skills(repo_path: Path) -> dict[str, Any]:
    skills_root = repo_path / ".agent" / "skills"
    if not repo_path.exists():
        return {
            "status": "SETUP_REQUIRED",
            "reason": f"Dripr repo not found: {repo_path}",
            "skills": [],
        }
    if not skills_root.is_dir():
        return {
            "status": "SETUP_REQUIRED",
            "reason": f"Dripr skills directory not found: {skills_root}",
            "skills": [],
        }

    skills: list[dict[str, str]] = []
    for skill_dir in sorted(skills_root.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            continue
        frontmatter = parse_frontmatter(skill_file.read_text(encoding="utf-8", errors="replace"))
        skills.append(
            {
                "id": skill_dir.name,
                "name": frontmatter.get("name", skill_dir.name),
                "description": frontmatter.get("description", ""),
                "path": str(skill_file),
            }
        )

    return {
        "status": "OK",
        "repo_path": str(repo_path),
        "skill_count": len(skills),
        "skills": skills,
    }
