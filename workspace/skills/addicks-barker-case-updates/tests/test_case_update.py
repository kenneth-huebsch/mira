from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from case_update import (  # noqa: E402
    CaseUpdateError,
    EXPECTED_URL,
    PAGE_ID,
    SEPARATOR,
    TEXT_BOX_CLOSE,
    TEXT_BOX_OPEN,
    insert_snippet,
    normalize_contact_links,
    parse_snippet,
    publish_update,
    sha256_text,
    stage_update,
    validate_target_page,
)


SNIPPET = """<h2>July 17, 2026</h2>
<strong>DOWNSTREAM - Case Update</strong>

We write to report a development in the case:

The Court held a status conference.

Please do not hesitate to <a href="/contact">contact us</a> with any questions."""

CURRENT_CONTENT = (
    '[vc_row][vc_column width="2/3" el_id="updates-column"]'
    '[vc_single_image image="1871"]'
    + SEPARATOR
    + TEXT_BOX_OPEN
    + "\n<h2>May 22, 2026</h2>\n"
    + "<strong>UPSTREAM - Case Update</strong>\n"
    + TEXT_BOX_CLOSE
    + '[/vc_column][vc_column width="1/3"]Sidebar[/vc_column][/vc_row]'
)


def page(
    *,
    content: str = CURRENT_CONTENT,
    modified_gmt: str = "2026-07-23T22:52:55",
    link: str = EXPECTED_URL,
) -> dict:
    return {
        "id": PAGE_ID,
        "link": link,
        "status": "publish",
        "modified_gmt": modified_gmt,
        "title": {"rendered": "Addicks/Barker"},
        "content": {"raw": content},
    }


class FakeClient:
    def __init__(self, current_page: dict | None = None):
        self.current_page = current_page or page()
        self.update_calls: list[tuple[int, str, str]] = []

    def get_page(self, page_id: int) -> dict:
        if page_id != PAGE_ID:
            raise AssertionError("wrong page requested")
        return self.current_page

    def update_content(
        self, page_id: int, content: str, *, expected_modified_gmt: str
    ) -> dict:
        self.update_calls.append((page_id, content, expected_modified_gmt))
        return page(content=content, modified_gmt="2026-07-23T23:00:00")


class SnippetTests(unittest.TestCase):
    def test_parses_required_shape(self):
        parsed = parse_snippet(SNIPPET)
        self.assertEqual(parsed["date"], "July 17, 2026")
        self.assertEqual(parsed["direction"], "DOWNSTREAM")
        self.assertEqual(parsed["title"], "Case Update")

    def test_normalizes_contact_link(self):
        normalized = normalize_contact_links(
            "Please contact us or <a href=\"https://example.com\">contact us</a>."
        )
        self.assertEqual(
            normalized,
            "Please <a href=\"/contact\">contact us</a> or "
            "<a href=\"/contact\">contact us</a>.",
        )

    def test_rejects_noncanonical_date(self):
        with self.assertRaisesRegex(CaseUpdateError, "exactly July 7, 2026"):
            parse_snippet(SNIPPET.replace("July 17, 2026", "July 07, 2026"))

    def test_rejects_disallowed_html(self):
        with self.assertRaisesRegex(CaseUpdateError, "disallowed HTML tag"):
            parse_snippet(SNIPPET + "\n<script>alert(1)</script>")

    def test_rejects_wpbakery_shortcode(self):
        with self.assertRaisesRegex(CaseUpdateError, "WPBakery"):
            parse_snippet(SNIPPET + "\n[vc_row]")


class InsertionTests(unittest.TestCase):
    def test_inserts_separator_and_text_box_before_existing_separator(self):
        proposed = insert_snippet(CURRENT_CONTENT, SNIPPET)
        expected = (
            SEPARATOR
            + TEXT_BOX_OPEN
            + "\n"
            + SNIPPET
            + "\n"
            + TEXT_BOX_CLOSE
            + SEPARATOR
        )
        self.assertIn(expected, proposed)
        self.assertEqual(proposed.count(SNIPPET), 1)
        self.assertTrue(proposed.endswith("Sidebar[/vc_column][/vc_row]"))

    def test_requires_exactly_one_anchor(self):
        with self.assertRaisesRegex(CaseUpdateError, "found 0"):
            insert_snippet(CURRENT_CONTENT.replace("updates-column", "other"), SNIPPET)
        with self.assertRaisesRegex(CaseUpdateError, "found 2"):
            insert_snippet(CURRENT_CONTENT + CURRENT_CONTENT, SNIPPET)

    def test_rejects_duplicate(self):
        existing = CURRENT_CONTENT.replace(
            "<h2>May 22, 2026</h2>\n<strong>UPSTREAM - Case Update</strong>",
            "<h2>July 17, 2026</h2>\n"
            "<strong>DOWNSTREAM - Case Update</strong>",
        )
        with self.assertRaisesRegex(CaseUpdateError, "already exist"):
            insert_snippet(existing, SNIPPET)

    def test_fixed_target_rejects_wrong_url(self):
        with self.assertRaisesRegex(CaseUpdateError, "URL"):
            validate_target_page(page(link="https://lawtx.com/other/"))


class StagePublishTests(unittest.TestCase):
    def test_stage_writes_hashed_artifacts_without_updating(self):
        client = FakeClient()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snippet_path = root / "draft.html"
            output_dir = root / "runtime"
            snippet_path.write_text(SNIPPET, encoding="utf-8")

            result = stage_update(client, snippet_path, output_dir)
            manifest = json.loads(
                (output_dir / "manifest.json").read_text(encoding="utf-8")
            )
            proposed = (output_dir / "proposed-content.html").read_text(
                encoding="utf-8"
            )

            self.assertTrue(result["ok"])
            self.assertEqual(client.update_calls, [])
            self.assertEqual(
                manifest["proposed_content_sha256"], sha256_text(proposed)
            )
            self.assertEqual(manifest["page_id"], PAGE_ID)
            self.assertEqual(
                (output_dir / "manifest.json").stat().st_mode & 0o777, 0o600
            )

    def test_publish_verifies_manifest_and_updates_exact_artifact(self):
        client = FakeClient()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snippet_path = root / "draft.html"
            output_dir = root / "runtime"
            snippet_path.write_text(SNIPPET, encoding="utf-8")
            stage_update(client, snippet_path, output_dir)
            manifest_path = output_dir / "manifest.json"

            result = publish_update(client, manifest_path, output_dir)
            proposed = (output_dir / "proposed-content.html").read_text(
                encoding="utf-8"
            )

            self.assertTrue(result["ok"])
            self.assertEqual(
                client.update_calls,
                [(PAGE_ID, proposed, "2026-07-23T22:52:55")],
            )

    def test_publish_preserves_wordpress_crlf_bytes_during_hash_check(self):
        current_with_crlf = CURRENT_CONTENT.replace("][", "]\r\n[")
        client = FakeClient(page(content=current_with_crlf))
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snippet_path = root / "draft.html"
            output_dir = root / "runtime"
            snippet_path.write_text(SNIPPET, encoding="utf-8")
            stage_update(client, snippet_path, output_dir)
            manifest_path = output_dir / "manifest.json"
            proposed_bytes = (output_dir / "proposed-content.html").read_bytes()
            proposed = proposed_bytes.decode("utf-8")

            self.assertIn(b"\r\n", proposed_bytes)
            result = publish_update(client, manifest_path, output_dir)

            self.assertTrue(result["ok"])
            self.assertEqual(
                client.update_calls,
                [(PAGE_ID, proposed, "2026-07-23T22:52:55")],
            )

    def test_publish_rejects_changed_page(self):
        client = FakeClient()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snippet_path = root / "draft.html"
            output_dir = root / "runtime"
            snippet_path.write_text(SNIPPET, encoding="utf-8")
            stage_update(client, snippet_path, output_dir)
            client.current_page = page(content=CURRENT_CONTENT + "changed")

            with self.assertRaisesRegex(CaseUpdateError, "content changed"):
                publish_update(client, output_dir / "manifest.json", output_dir)
            self.assertEqual(client.update_calls, [])

    def test_publish_rejects_tampered_staged_file(self):
        client = FakeClient()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snippet_path = root / "draft.html"
            output_dir = root / "runtime"
            snippet_path.write_text(SNIPPET, encoding="utf-8")
            stage_update(client, snippet_path, output_dir)
            (output_dir / "proposed-content.html").write_text(
                "tampered", encoding="utf-8"
            )

            with self.assertRaisesRegex(CaseUpdateError, "hash mismatch"):
                publish_update(client, output_dir / "manifest.json", output_dir)
            self.assertEqual(client.update_calls, [])


if __name__ == "__main__":
    unittest.main()
