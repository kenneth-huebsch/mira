from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).parents[1]
TRACKED_ENTRYPOINT = REPO / "openclaw/entrypoint.sh"
LIVE_ENTRYPOINT = REPO / "openclaw-src/entrypoint.sh"


class EntrypointContractTests(unittest.TestCase):
    def test_shell_syntax_and_live_tracked_parity(self) -> None:
        subprocess.run(["sh", "-n", str(TRACKED_ENTRYPOINT)], check=True)
        if LIVE_ENTRYPOINT.exists():
            subprocess.run(["sh", "-n", str(LIVE_ENTRYPOINT)], check=True)
            self.assertEqual(LIVE_ENTRYPOINT.read_bytes(), TRACKED_ENTRYPOINT.read_bytes())

    def test_exact_aws_cli_pin_checksums_and_architectures(self) -> None:
        script = TRACKED_ENTRYPOINT.read_text(encoding="utf-8")
        self.assertIn('OPENCLAW_AWS_CLI_VERSION:-2.36.14', script)
        self.assertIn(
            "43b34875482244039716cc3725d1f60e7d47ef3cfb2a19e114759a46db24dc30",
            script,
        )
        self.assertIn(
            "61e2fb72b36dc0ad98912b3a7b7469c886b90ea703f1096428a152ab09babd8a",
            script,
        )
        self.assertIn('amd64)\n      aws_cli_arch="x86_64"', script)
        self.assertIn('arm64)\n      aws_cli_arch="aarch64"', script)
        self.assertIn(
            'aws_cli_url="https://awscli.amazonaws.com/${aws_cli_archive}"',
            script,
        )
        self.assertLess(script.index("sha256sum -c -"), script.index("unzip -q"))
        self.assertIn('if [ ! -x "$aws_cli_bin" ]; then', script)
        self.assertIn('trap \'rm -rf "$aws_cli_tmpdir"\' EXIT HUP INT TERM', script)
        self.assertIn('rm -rf "$aws_cli_tmpdir"', script)

    def test_persistent_installs_links_and_exact_cdk_package(self) -> None:
        script = TRACKED_ENTRYPOINT.read_text(encoding="utf-8")
        self.assertIn(
            'OPENCLAW_AWS_CLI_ROOT:-/home/node/.openclaw/tools/aws-cli',
            script,
        )
        self.assertIn(
            'OPENCLAW_AWS_CDK_ROOT:-/home/node/.openclaw/tools/aws-cdk',
            script,
        )
        self.assertIn('OPENCLAW_AWS_CDK_VERSION:-2.1134.0', script)
        self.assertIn('"aws-cdk@${aws_cdk_version}"', script)
        self.assertIn("--no-audit --no-fund", script)
        self.assertIn(
            'sh "$aws_cdk_install_dir" "aws-cdk@${aws_cdk_version}"',
            script,
        )
        self.assertIn('if [ ! -x "$aws_cdk_bin" ]; then', script)
        self.assertIn(
            'OPENCLAW_AWS_CLI_BIN_DIR:-/home/node/.openclaw/bin',
            script,
        )
        self.assertIn(
            'OPENCLAW_AWS_CDK_BIN_DIR:-/home/node/.openclaw/bin',
            script,
        )
        for command in ("aws", "cdk"):
            self.assertIn(f" /usr/local/bin/{command}", script)
        self.assertIn("chown -R node:node", script)
        self.assertIn("unzip ca-certificates", script)

    def test_playwright_cli_is_pinned_private_and_uses_baked_chromium(self) -> None:
        script = TRACKED_ENTRYPOINT.read_text(encoding="utf-8")
        compose = (REPO / "openclaw/docker-compose.yml").read_text(encoding="utf-8")
        runbook = (REPO / "RUNBOOK.md").read_text(encoding="utf-8")
        restore = (REPO / "RESTORE.md").read_text(encoding="utf-8")

        self.assertIn("OPENCLAW_PLAYWRIGHT_CLI_VERSION:-0.1.17", script)
        self.assertIn('"@playwright/cli@${playwright_cli_version}"', script)
        self.assertIn(
            'require("playwright-core").chromium.executablePath()', script
        )
        self.assertIn("PLAYWRIGHT_MCP_BROWSER=chromium", script)
        self.assertIn("PLAYWRIGHT_MCP_EXECUTABLE_PATH=", script)
        self.assertNotIn("/usr/local/bin/playwright-cli", script)
        self.assertIn(
            "PLAYWRIGHT_CLI_BIN: /home/node/.openclaw/tools/playwright-cli/playwright-cli",
            compose,
        )
        self.assertIn("OPENCLAW_INSTALL_BROWSER=1", runbook)
        self.assertIn("OPENCLAW_INSTALL_BROWSER=1", restore)

    def test_friend_safe_config_enables_isolated_browser_tool(self) -> None:
        config = json.loads(
            (REPO / "templates/openclaw.friend-safe.example.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(config["browser"]["enabled"])
        self.assertTrue(config["browser"]["headless"])
        self.assertTrue(config["browser"]["noSandbox"])
        self.assertFalse(config["browser"]["evaluateEnabled"])
        self.assertTrue(
            config["browser"]["ssrfPolicy"]["dangerouslyAllowPrivateNetwork"]
        )
        self.assertEqual(
            config["browser"]["ssrfPolicy"]["allowedHostnames"],
            ["localhost", "127.0.0.1"],
        )
        self.assertIn("browser", config["plugins"]["allow"])
        self.assertIn("browser", config["tools"]["allow"])

    def test_restore_replaces_source_local_entrypoint_from_blueprint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "openclaw-home"
            workspace = home / "workspace"
            source = root / "openclaw-source"
            source.mkdir()
            (source / "entrypoint.sh").write_text("# stale\n", encoding="utf-8")
            (source / "docker-compose.yml").write_text("stale: true\n", encoding="utf-8")
            env = {
                **os.environ,
                "TARGET_OPENCLAW_HOME": str(home),
                "TARGET_WORKSPACE": str(workspace),
                "OPENCLAW_SOURCE": str(source),
            }
            subprocess.run(
                ["bash", str(REPO / "scripts/restore-to-live.sh")],
                env=env,
                check=True,
                text=True,
                capture_output=True,
            )
            self.assertEqual(
                (source / "entrypoint.sh").read_bytes(),
                TRACKED_ENTRYPOINT.read_bytes(),
            )


if __name__ == "__main__":
    unittest.main()
