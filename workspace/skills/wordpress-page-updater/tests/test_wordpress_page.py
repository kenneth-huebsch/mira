from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from wordpress_page import (
    Config,
    ConfigurationError,
    WordPressError,
    WordPressPageClient,
    decode_json_response,
    normalize_base_url,
    read_content_file,
)


class FakeResponse:
    def __init__(self, body, *, status_code: int = 200, raw_text: str | None = None):
        self._body = body
        self.text = raw_text if raw_text is not None else ""
        self.status_code = status_code
        self.ok = 200 <= status_code < 300

    def json(self):
        if self.text:
            raise requests.JSONDecodeError("invalid JSON", self.text, 0)
        return self._body


def page(*, modified_gmt: str = "2026-07-23T12:00:00") -> dict:
    return {
        "id": 42,
        "link": "https://example.com/monthly/",
        "status": "publish",
        "modified_gmt": modified_gmt,
        "title": {"rendered": "Monthly page"},
        "content": {"raw": "<p>Current</p>", "rendered": "<p>Current</p>"},
    }


class ConfigTests(unittest.TestCase):
    def test_reads_required_environment(self):
        env = {
            "WORDPRESS_BASE_URL": "https://example.com/wordpress/",
            "WORDPRESS_USERNAME": "mira",
            "WORDPRESS_APP_PASSWORD": "not-a-real-secret",
        }
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_env()
        self.assertEqual(config.base_url, "https://example.com/wordpress")

    def test_rejects_non_https_url(self):
        with self.assertRaisesRegex(ConfigurationError, "must use HTTPS"):
            normalize_base_url("http://example.com")

    def test_rejects_credentials_in_url(self):
        with self.assertRaisesRegex(ConfigurationError, "no credentials"):
            normalize_base_url("https://user:pass@example.com")


class ResponseDecodeTests(unittest.TestCase):
    def test_strips_repeated_known_wpbakery_style_prefix(self):
        default_style = (
            '<style type="text/css" data-type="vc_shortcodes-default-css">'
            ".example{display:block;}</style>"
        )
        custom_style = (
            '<style type="text/css" data-type="vc_shortcodes-custom-css">'
            ".custom{color:inherit;}</style>"
        )
        response = FakeResponse(
            None,
            raw_text=default_style + custom_style + default_style + '[{"id":42}]',
        )
        self.assertEqual(decode_json_response(response), [{"id": 42}])

    def test_rejects_unknown_markup_prefix(self):
        response = FakeResponse(None, raw_text='<style id="unknown"></style>[]')
        with self.assertRaisesRegex(WordPressError, "non-JSON"):
            decode_json_response(response)

    def test_rejects_invalid_json_after_known_prefix(self):
        style = (
            '<style type="text/css" data-type="vc_shortcodes-default-css">'
            ".example{display:block;}</style>"
        )
        response = FakeResponse(None, raw_text=style + "not-json")
        with self.assertRaisesRegex(WordPressError, "after WPBakery"):
            decode_json_response(response)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.config = Config(
            base_url="https://example.com",
            username="mira",
            app_password="application-password-value",
        )
        self.session = Mock()
        self.client = WordPressPageClient(self.config, session=self.session)

    def test_get_uses_requested_page_and_edit_context(self):
        self.session.request.return_value = FakeResponse(page())
        result = self.client.get_page(42)
        self.assertEqual(result["id"], 42)
        self.session.request.assert_called_once_with(
            "GET",
            "https://example.com/wp-json/wp/v2/pages/42",
            params={"context": "edit"},
            json=None,
            auth=("mira", "application-password-value"),
            headers={"Accept": "application/json"},
            timeout=20.0,
        )

    def test_list_uses_only_pages_collection(self):
        self.session.request.return_value = FakeResponse([page()])
        result = self.client.list_pages(search="Monthly")
        self.assertEqual(len(result), 1)
        self.session.request.assert_called_once_with(
            "GET",
            "https://example.com/wp-json/wp/v2/pages",
            params={
                "context": "edit",
                "per_page": "100",
                "orderby": "title",
                "order": "asc",
                "search": "Monthly",
            },
            json=None,
            auth=("mira", "application-password-value"),
            headers={"Accept": "application/json"},
            timeout=20.0,
        )

    def test_rejects_invalid_page_id(self):
        with self.assertRaisesRegex(WordPressError, "positive integer"):
            self.client.get_page(0)
        self.session.request.assert_not_called()

    def test_update_sends_content_only_after_version_check(self):
        updated = page(modified_gmt="2026-07-23T12:05:00")
        self.session.request.side_effect = [FakeResponse(page()), FakeResponse(updated)]
        result = self.client.update_content(
            42, "<p>New</p>", expected_modified_gmt="2026-07-23T12:00:00"
        )
        self.assertEqual(result["modified_gmt"], "2026-07-23T12:05:00")
        self.assertEqual(self.session.request.call_count, 2)
        update_call = self.session.request.call_args_list[1]
        self.assertEqual(
            update_call.args,
            ("POST", "https://example.com/wp-json/wp/v2/pages/42"),
        )
        self.assertEqual(update_call.kwargs["json"], {"content": "<p>New</p>"})

    def test_update_refuses_stale_preview(self):
        self.session.request.return_value = FakeResponse(
            page(modified_gmt="2026-07-23T12:01:00")
        )
        with self.assertRaisesRegex(WordPressError, "changed after the preview"):
            self.client.update_content(
                42, "<p>New</p>", expected_modified_gmt="2026-07-23T12:00:00"
            )
        self.assertEqual(self.session.request.call_count, 1)

    def test_request_error_does_not_expose_exception_or_password(self):
        self.session.request.side_effect = requests.ConnectionError(
            "application-password-value"
        )
        with self.assertRaises(WordPressError) as raised:
            self.client.get_page(42)
        message = str(raised.exception)
        self.assertIn("ConnectionError", message)
        self.assertNotIn("application-password-value", message)

    def test_wordpress_error_is_bounded(self):
        self.session.request.return_value = FakeResponse(
            {"code": "rest_forbidden", "message": "x" * 1000}, status_code=403
        )
        with self.assertRaises(WordPressError) as raised:
            self.client.get_page(42)
        self.assertLess(len(str(raised.exception)), 600)


class ContentFileTests(unittest.TestCase):
    def test_reads_regular_utf8_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "content.html"
            path.write_text("<p>Monthly update</p>", encoding="utf-8")
            self.assertEqual(read_content_file(str(path)), "<p>Monthly update</p>")

    def test_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.html"
            link = Path(temp_dir) / "link.html"
            source.write_text("content", encoding="utf-8")
            link.symlink_to(source)
            with self.assertRaisesRegex(WordPressError, "non-symlink"):
                read_content_file(str(link))


if __name__ == "__main__":
    unittest.main()
