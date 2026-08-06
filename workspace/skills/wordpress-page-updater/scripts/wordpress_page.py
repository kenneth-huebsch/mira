#!/usr/bin/env python3
"""List, read, and update existing WordPress pages through the REST API."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests


class ConfigurationError(ValueError):
    """Raised when required runtime configuration is missing or unsafe."""


class WordPressError(RuntimeError):
    """Raised when WordPress rejects or cannot complete a request."""


WPBAKERY_STYLE_PREFIXES = (
    '<style type="text/css" data-type="vc_shortcodes-default-css">',
    '<style type="text/css" data-type="vc_shortcodes-custom-css">',
)


def decode_json_response(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError as original_error:
        text = response.text
        stripped_known_prefix = False
        while text.startswith(WPBAKERY_STYLE_PREFIXES):
            closing_index = text.find("</style>")
            if closing_index < 0:
                raise WordPressError(
                    "WordPress returned incomplete WPBakery markup"
                ) from original_error
            text = text[closing_index + len("</style>") :]
            stripped_known_prefix = True
        if not stripped_known_prefix:
            raise WordPressError("WordPress returned a non-JSON response") from original_error
        try:
            return json.loads(text)
        except ValueError as exc:
            raise WordPressError(
                "WordPress returned invalid JSON after WPBakery markup"
            ) from exc


@dataclass(frozen=True)
class Config:
    base_url: str
    username: str
    app_password: str

    @classmethod
    def from_env(cls) -> "Config":
        values = {
            "WORDPRESS_BASE_URL": os.environ.get("WORDPRESS_BASE_URL", "").strip(),
            "WORDPRESS_USERNAME": os.environ.get("WORDPRESS_USERNAME", "").strip(),
            "WORDPRESS_APP_PASSWORD": os.environ.get(
                "WORDPRESS_APP_PASSWORD", ""
            ).strip(),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise ConfigurationError(
                "missing required environment variable(s): " + ", ".join(missing)
            )

        base_url = normalize_base_url(values["WORDPRESS_BASE_URL"])
        return cls(
            base_url=base_url,
            username=values["WORDPRESS_USERNAME"],
            app_password=values["WORDPRESS_APP_PASSWORD"],
        )


def normalize_base_url(value: str) -> str:
    parsed = urlsplit(value.rstrip("/"))
    if parsed.scheme != "https":
        raise ConfigurationError("WORDPRESS_BASE_URL must use HTTPS")
    if not parsed.netloc or parsed.username or parsed.password:
        raise ConfigurationError(
            "WORDPRESS_BASE_URL must contain a hostname and no credentials"
        )
    if parsed.query or parsed.fragment:
        raise ConfigurationError(
            "WORDPRESS_BASE_URL must not contain a query string or fragment"
        )
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


class WordPressPageClient:
    def __init__(
        self,
        config: Config,
        *,
        session: requests.Session | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.config = config
        self.session = session or requests.Session()
        self.timeout = timeout

    @property
    def pages_url(self) -> str:
        return f"{self.config.base_url}/wp-json/wp/v2/pages"

    def page_url(self, page_id: int) -> str:
        if page_id <= 0:
            raise WordPressError("page ID must be a positive integer")
        return f"{self.pages_url}/{page_id}"

    def _request(
        self,
        method: str,
        *,
        page_id: int | None = None,
        params: dict[str, str] | None = None,
        payload: dict[str, str] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        url = self.pages_url if page_id is None else self.page_url(page_id)
        try:
            response = self.session.request(
                method,
                url,
                params=params,
                json=payload,
                auth=(self.config.username, self.config.app_password),
                headers={"Accept": "application/json"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise WordPressError(
                f"WordPress request failed ({type(exc).__name__})"
            ) from exc

        if not response.ok:
            code = "unknown_error"
            message = f"HTTP {response.status_code}"
            try:
                body = decode_json_response(response)
                if isinstance(body, dict):
                    code = str(body.get("code") or code)
                    message = str(body.get("message") or message)
            except (WordPressError, TypeError):
                pass
            raise WordPressError(
                f"WordPress rejected the request: {code}: {message[:500]}"
            )

        body = decode_json_response(response)
        if not isinstance(body, (dict, list)):
            raise WordPressError("WordPress returned an unexpected response shape")
        return body

    def list_pages(self, *, search: str | None = None) -> list[dict[str, Any]]:
        params = {
            "context": "edit",
            "per_page": "100",
            "orderby": "title",
            "order": "asc",
        }
        if search:
            params["search"] = search
        result = self._request("GET", params=params)
        if not isinstance(result, list):
            raise WordPressError("WordPress returned an unexpected page list")
        return result

    def get_page(self, page_id: int) -> dict[str, Any]:
        result = self._request(
            "GET", page_id=page_id, params={"context": "edit"}
        )
        if not isinstance(result, dict):
            raise WordPressError("WordPress returned an unexpected page")
        return result

    def update_content(
        self, page_id: int, content: str, *, expected_modified_gmt: str
    ) -> dict[str, Any]:
        current = self.get_page(page_id)
        actual_modified_gmt = str(current.get("modified_gmt") or "")
        if not expected_modified_gmt:
            raise WordPressError("an expected modified_gmt value is required")
        if actual_modified_gmt != expected_modified_gmt:
            raise WordPressError(
                "the page changed after the preview; fetch it again before updating"
            )
        result = self._request(
            "POST", page_id=page_id, payload={"content": content}
        )
        if not isinstance(result, dict):
            raise WordPressError("WordPress returned an unexpected updated page")
        return result


def page_summary(page: dict[str, Any], *, include_content: bool) -> dict[str, Any]:
    title = page.get("title")
    content = page.get("content")
    result: dict[str, Any] = {
        "id": page.get("id"),
        "link": page.get("link"),
        "status": page.get("status"),
        "modified_gmt": page.get("modified_gmt"),
        "title": title.get("rendered") if isinstance(title, dict) else title,
    }
    if include_content:
        if isinstance(content, dict):
            result["content"] = content.get("raw", content.get("rendered"))
        else:
            result["content"] = content
    return result


def read_content_file(path_value: str) -> str:
    path = Path(path_value)
    if not path.is_file() or path.is_symlink():
        raise WordPressError("content file must be a regular, non-symlink file")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise WordPressError("could not read the content file") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="List, read, or update existing WordPress pages."
    )
    parser.add_argument("--pretty", action="store_true", help="indent JSON output")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="verify credentials and page-list access")
    list_parser = subparsers.add_parser(
        "list", help="list or search editable WordPress pages"
    )
    list_parser.add_argument("--search")
    get = subparsers.add_parser("get", help="return one page and editable content")
    get.add_argument("--page-id", required=True, type=int)

    update = subparsers.add_parser(
        "update", help="replace content on one existing page"
    )
    update.add_argument("--page-id", required=True, type=int)
    update.add_argument("--content-file", required=True)
    update.add_argument("--expected-modified-gmt", required=True)
    return parser


def emit_json(value: dict[str, Any], *, pretty: bool) -> None:
    json.dump(
        value,
        sys.stdout,
        ensure_ascii=False,
        indent=2 if pretty else None,
        sort_keys=True,
    )
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        client = WordPressPageClient(Config.from_env())
        if args.command == "check":
            pages = client.list_pages()
            output = {"ok": True, "visible_page_count": len(pages)}
        elif args.command == "list":
            pages = client.list_pages(search=args.search)
            output = {
                "pages": [
                    page_summary(page, include_content=False) for page in pages
                ]
            }
        elif args.command == "get":
            output = page_summary(
                client.get_page(args.page_id), include_content=True
            )
        else:
            content = read_content_file(args.content_file)
            page = client.update_content(
                args.page_id,
                content,
                expected_modified_gmt=args.expected_modified_gmt,
            )
            output = {
                "ok": True,
                "page": page_summary(page, include_content=False),
            }
        emit_json(output, pretty=args.pretty)
        return 0
    except (ConfigurationError, WordPressError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
