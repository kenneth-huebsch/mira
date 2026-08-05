#!/usr/bin/env python3
"""Stage and publish deterministic Addicks/Barker case updates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

SKILLS_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILLS_DIR / "wordpress-page-updater" / "scripts"))

from wordpress_page import (  # noqa: E402
    Config,
    ConfigurationError,
    WordPressError,
    WordPressPageClient,
    page_summary,
)


PAGE_ID = 3041
EXPECTED_URL = (
    "https://lawtx.com/areas-of-practice/"
    "addicks-barker-reservoirs-floodwater-release/"
)
UPDATES_COLUMN_ID = "updates-column"
SEPARATOR = '[vc_separator color="black" align="align_left" el_width="50"]'
TEXT_BOX_OPEN = '[vc_column_text css=""]'
TEXT_BOX_CLOSE = "[/vc_column_text]"
CONTACT_LINK = '<a href="/contact">contact us</a>'
MANIFEST_VERSION = 1
DEFAULT_RUNTIME_DIR = Path(
    "/home/node/.openclaw/workspace/runtime/addicks-barker-case-updates"
)
HEADER_RE = re.compile(
    r"\A<h2>(?P<date>[^<\n]+)</h2>\n"
    r"<strong>(?P<direction>UPSTREAM|DOWNSTREAM) - "
    r"(?P<title>[^<\n]+)</strong>\n\n"
    r"(?P<body>.+)\Z",
    re.DOTALL,
)
COLUMN_RE = re.compile(
    r'\[vc_column(?=[^\]]*\bel_id="updates-column")[^\]]*\]'
)
CONTACT_RE = re.compile(
    r'(?i)(?:<a\b[^>]*>)?contact us(?:</a>)?'
)


class CaseUpdateError(RuntimeError):
    """Raised when a case update cannot be staged or published safely."""


class SnippetHTMLValidator(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.errors: list[str] = []
        self.start_counts: dict[str, int] = {}
        self.end_counts: dict[str, int] = {}

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.start_counts[tag] = self.start_counts.get(tag, 0) + 1
        if tag not in {"h2", "strong", "a"}:
            self.errors.append(f"disallowed HTML tag: {tag}")
            return
        if tag == "a":
            if attrs != [("href", "/contact")]:
                self.errors.append("contact links must use only href=\"/contact\"")
        elif attrs:
            self.errors.append(f"attributes are not allowed on {tag}")

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.errors.append(f"self-closing HTML tag is not allowed: {tag}")

    def handle_comment(self, data: str) -> None:
        self.errors.append("HTML comments are not allowed")

    def handle_endtag(self, tag: str) -> None:
        self.end_counts[tag] = self.end_counts.get(tag, 0) + 1
        if tag not in {"h2", "strong", "a"}:
            self.errors.append(f"disallowed closing HTML tag: {tag}")


def normalize_url(value: str) -> str:
    parsed = urlsplit(value)
    path = parsed.path.rstrip("/") + "/"
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), path, "", "")
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_utf8_exact(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def normalize_contact_links(snippet: str) -> str:
    return CONTACT_RE.sub(CONTACT_LINK, snippet)


def parse_snippet(snippet: str) -> dict[str, str]:
    normalized_newlines = snippet.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalize_contact_links(normalized_newlines.strip())
    if "[vc_" in normalized or "[/vc_" in normalized:
        raise CaseUpdateError("the update snippet must not contain WPBakery shortcodes")

    match = HEADER_RE.fullmatch(normalized)
    if not match:
        raise CaseUpdateError(
            "snippet must start with an h2 date, a strong direction/title line, "
            "a blank line, and body content"
        )

    date_text = match.group("date")
    try:
        parsed_date = datetime.strptime(date_text, "%B %d, %Y")
    except ValueError as exc:
        raise CaseUpdateError(
            "snippet date must use the full Month D, YYYY format"
        ) from exc
    canonical_date = (
        f"{parsed_date.strftime('%B')} {parsed_date.day}, {parsed_date.year}"
    )
    if date_text != canonical_date:
        raise CaseUpdateError(f"snippet date must be exactly {canonical_date}")

    validator = SnippetHTMLValidator()
    validator.feed(normalized)
    validator.close()
    if validator.start_counts.get("h2", 0) != 1 or validator.end_counts.get(
        "h2", 0
    ) != 1:
        validator.errors.append("snippet must contain exactly one h2 date")
    if validator.start_counts.get(
        "strong", 0
    ) != 1 or validator.end_counts.get("strong", 0) != 1:
        validator.errors.append("snippet must contain exactly one strong title")
    if validator.start_counts.get("a", 0) != validator.end_counts.get("a", 0):
        validator.errors.append("contact link tags are unbalanced")
    if validator.errors:
        raise CaseUpdateError("; ".join(validator.errors))

    body = match.group("body")
    for contact_match in re.finditer(r"(?i)contact us", body):
        before = body[: contact_match.start()]
        if not before.endswith('<a href="/contact">'):
            raise CaseUpdateError("every 'contact us' phrase must use the contact link")

    title = match.group("title").strip()
    if not title:
        raise CaseUpdateError("snippet title must not be empty")
    return {
        "snippet": normalized,
        "date": canonical_date,
        "direction": match.group("direction"),
        "title": title,
    }


def validate_target_page(page: dict[str, Any]) -> str:
    if page.get("id") != PAGE_ID:
        raise CaseUpdateError(f"expected WordPress page ID {PAGE_ID}")
    link = str(page.get("link") or "")
    if normalize_url(link) != normalize_url(EXPECTED_URL):
        raise CaseUpdateError("the WordPress page URL does not match the fixed target")
    content = page.get("content")
    if not isinstance(content, dict) or not isinstance(content.get("raw"), str):
        raise CaseUpdateError("the WordPress page has no editable raw content")
    return content["raw"]


def insert_snippet(current_content: str, snippet: str) -> str:
    columns = list(COLUMN_RE.finditer(current_content))
    if len(columns) != 1:
        raise CaseUpdateError(
            f"expected exactly one {UPDATES_COLUMN_ID} column, found {len(columns)}"
        )

    column_start = columns[0].end()
    column_end = current_content.find("[/vc_column]", column_start)
    if column_end < 0:
        raise CaseUpdateError("the updates column has no closing shortcode")
    separator_index = current_content.find(SEPARATOR, column_start, column_end)
    if separator_index < 0:
        raise CaseUpdateError("the updates column has no expected top separator")

    parsed = parse_snippet(snippet)
    duplicate_header = (
        f"<h2>{parsed['date']}</h2>\n"
        f"<strong>{parsed['direction']} - {parsed['title']}</strong>"
    )
    column_content = current_content[column_start:column_end]
    if duplicate_header in column_content:
        raise CaseUpdateError("this date, direction, and title already exist")

    new_block = (
        SEPARATOR
        + TEXT_BOX_OPEN
        + "\n"
        + parsed["snippet"]
        + "\n"
        + TEXT_BOX_CLOSE
    )
    return (
        current_content[:separator_index]
        + new_block
        + current_content[separator_index:]
    )


def ensure_regular_file(path: Path, *, label: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise CaseUpdateError(f"{label} must be a regular, non-symlink file")


def runtime_dir() -> Path:
    value = os.environ.get("ADDICKS_BARKER_RUNTIME_DIR")
    return Path(value) if value else DEFAULT_RUNTIME_DIR


def atomic_write(path: Path, content: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    with temporary.open("xb") as handle:
        handle.write(content.encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def stage_update(
    client: WordPressPageClient, snippet_file: Path, output_dir: Path
) -> dict[str, Any]:
    ensure_regular_file(snippet_file, label="snippet file")
    parsed = parse_snippet(read_utf8_exact(snippet_file))
    page = client.get_page(PAGE_ID)
    current_content = validate_target_page(page)
    proposed_content = insert_snippet(current_content, parsed["snippet"])

    if output_dir.is_symlink():
        raise CaseUpdateError("runtime directory must not be a symlink")
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(output_dir, 0o700)

    staged_content_path = output_dir / "proposed-content.html"
    staged_snippet_path = output_dir / "snippet.html"
    manifest_path = output_dir / "manifest.json"
    atomic_write(staged_content_path, proposed_content)
    atomic_write(staged_snippet_path, parsed["snippet"] + "\n")

    manifest = {
        "version": MANIFEST_VERSION,
        "page_id": PAGE_ID,
        "page_url": EXPECTED_URL,
        "source_modified_gmt": str(page.get("modified_gmt") or ""),
        "source_content_sha256": sha256_text(current_content),
        "proposed_content_file": staged_content_path.name,
        "proposed_content_sha256": sha256_text(proposed_content),
        "snippet_file": staged_snippet_path.name,
        "snippet_sha256": sha256_text(parsed["snippet"] + "\n"),
        "date": parsed["date"],
        "direction": parsed["direction"],
        "title": parsed["title"],
        "staged_at": datetime.now(timezone.utc).isoformat(),
    }
    atomic_write(
        manifest_path,
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return {
        "ok": True,
        "manifest": str(manifest_path),
        "page": page_summary(page, include_content=False),
        "update": {
            "date": parsed["date"],
            "direction": parsed["direction"],
            "title": parsed["title"],
            "snippet": parsed["snippet"],
        },
        "insertion": {
            "column_id": UPDATES_COLUMN_ID,
            "sequence": ["separator", "text_box", "existing_separator"],
        },
    }


def load_manifest(manifest_path: Path, output_dir: Path) -> dict[str, Any]:
    ensure_regular_file(manifest_path, label="manifest")
    if manifest_path.resolve().parent != output_dir.resolve():
        raise CaseUpdateError("manifest must be inside the case-update runtime directory")
    try:
        manifest = json.loads(read_utf8_exact(manifest_path))
    except (OSError, ValueError) as exc:
        raise CaseUpdateError("manifest is not valid JSON") from exc
    if not isinstance(manifest, dict) or manifest.get("version") != MANIFEST_VERSION:
        raise CaseUpdateError("unsupported case-update manifest")
    if manifest.get("page_id") != PAGE_ID:
        raise CaseUpdateError("manifest targets the wrong page")
    if normalize_url(str(manifest.get("page_url") or "")) != normalize_url(
        EXPECTED_URL
    ):
        raise CaseUpdateError("manifest targets the wrong URL")
    return manifest


def manifest_file(
    manifest: dict[str, Any], output_dir: Path, key: str, hash_key: str
) -> tuple[Path, str]:
    filename = manifest.get(key)
    if not isinstance(filename, str) or Path(filename).name != filename:
        raise CaseUpdateError(f"invalid manifest file field: {key}")
    path = output_dir / filename
    ensure_regular_file(path, label=key)
    content = read_utf8_exact(path)
    if sha256_text(content) != manifest.get(hash_key):
        raise CaseUpdateError(f"staged file hash mismatch: {filename}")
    return path, content


def publish_update(
    client: WordPressPageClient, manifest_path: Path, output_dir: Path
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path, output_dir)
    _, proposed_content = manifest_file(
        manifest,
        output_dir,
        "proposed_content_file",
        "proposed_content_sha256",
    )
    manifest_file(manifest, output_dir, "snippet_file", "snippet_sha256")

    current_page = client.get_page(PAGE_ID)
    current_content = validate_target_page(current_page)
    if sha256_text(current_content) != manifest.get("source_content_sha256"):
        raise CaseUpdateError("the page content changed after staging")
    if str(current_page.get("modified_gmt") or "") != manifest.get(
        "source_modified_gmt"
    ):
        raise CaseUpdateError("the page modification time changed after staging")

    updated_page = client.update_content(
        PAGE_ID,
        proposed_content,
        expected_modified_gmt=str(manifest["source_modified_gmt"]),
    )
    return {
        "ok": True,
        "page": page_summary(updated_page, include_content=False),
        "published_update": {
            "date": manifest.get("date"),
            "direction": manifest.get("direction"),
            "title": manifest.get("title"),
        },
    }


def emit(value: dict[str, Any], *, pretty: bool) -> None:
    json.dump(
        value,
        sys.stdout,
        ensure_ascii=False,
        indent=2 if pretty else None,
        sort_keys=True,
    )
    sys.stdout.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stage or publish an Addicks/Barker PDF-derived case update."
    )
    parser.add_argument("--pretty", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    stage = commands.add_parser("stage")
    stage.add_argument("--snippet-file", required=True)
    publish = commands.add_parser("publish")
    publish.add_argument("--manifest", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        client = WordPressPageClient(Config.from_env())
        output_dir = runtime_dir()
        if args.command == "stage":
            result = stage_update(client, Path(args.snippet_file), output_dir)
        else:
            result = publish_update(client, Path(args.manifest), output_dir)
        emit(result, pretty=args.pretty)
        return 0
    except (
        CaseUpdateError,
        ConfigurationError,
        OSError,
        UnicodeError,
        WordPressError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
