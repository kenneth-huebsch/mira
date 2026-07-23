from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class ContainerContractTests(unittest.TestCase):
    def test_toolchain_is_pinned_and_downloads_are_checksum_verified(self) -> None:
        lock = json.loads((ROOT / "openclaw/toolchain.lock.json").read_text())
        self.assertEqual(lock["schema_version"], 2)
        self.assertRegex(lock["base_image"]["digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertRegex(lock["base_image"]["source_revision"], r"^[0-9a-f]{40}$")
        for tool in ("cursor", "gogcli"):
            self.assertRegex(lock[tool]["linux_amd64_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(lock[tool]["linux_arm64_sha256"], r"^[0-9a-f]{64}$")
        dockerfile = (ROOT / "openclaw/Dockerfile.mira").read_text()
        self.assertIn("sha256sum -c -", dockerfile)
        self.assertIn('"gh=${GH_DEBIAN_PACKAGE}"', dockerfile)
        self.assertNotIn("openclaw:local", dockerfile)
        self.assertNotIn(lock["cursor"]["version"], dockerfile)
        self.assertNotIn("curl https://cursor.com/install", dockerfile)

    def test_build_script_verifies_base_and_feeds_every_locked_value(self) -> None:
        lock = json.loads((ROOT / "openclaw/toolchain.lock.json").read_text())
        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            source = temp / "source"
            shutil.copytree(ROOT / "openclaw", source)
            fake_bin = temp / "bin"
            fake_bin.mkdir()
            log = temp / "docker-args"
            (fake_bin / "git").write_text(
                f"#!/bin/sh\nprintf '%s\\n' '{lock['base_image']['source_revision']}'\n"
            )
            (fake_bin / "docker").write_text(
                "#!/bin/sh\n"
                "if [ \"$1 $2\" = \"image inspect\" ]; then\n"
                f"  printf '%s %s\\n' '{lock['base_image']['digest']}' "
                f"'[\"openclaw@{lock['base_image']['digest']}\"]'\n"
                "  exit 0\n"
                "fi\n"
                f"printf '%s\\n' \"$@\" > '{log}'\n"
            )
            (fake_bin / "git").chmod(0o755)
            (fake_bin / "docker").chmod(0o755)
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/build-mira-image.sh")],
                env={
                    **os.environ,
                    "PATH": f"{fake_bin}:{os.environ['PATH']}",
                    "OPENCLAW_SOURCE": str(source),
                },
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            args = log.read_text()
            self.assertIn(
                f"OPENCLAW_BASE_IMAGE=openclaw@{lock['base_image']['digest']}", args
            )
            self.assertIn(
                f"OPENCLAW_SOURCE_REVISION={lock['base_image']['source_revision']}", args
            )
            for value in lock["debian_packages"].values():
                self.assertIn(value, args)
            for tool in ("cursor", "gogcli"):
                for value in lock[tool].values():
                    self.assertIn(value, args)

    def test_entrypoint_only_validates_and_executes(self) -> None:
        entrypoint = (ROOT / "openclaw/entrypoint.sh").read_text()
        for forbidden in ("apt-get", "pip install", "curl -", "wget ", "chown "):
            self.assertNotIn(forbidden, entrypoint)
        self.assertIn('exec "$@"', entrypoint)
        self.assertIn("version mismatch", entrypoint)

    def test_compose_hardening_is_explicit(self) -> None:
        compose = (ROOT / "openclaw/docker-compose.yml").read_text()
        self.assertNotIn("build:", compose)
        self.assertNotIn("openclaw:local", compose)
        self.assertGreaterEqual(compose.count("- ALL"), 2)
        self.assertGreaterEqual(compose.count("no-new-privileges:true"), 2)
        self.assertGreaterEqual(compose.count('user: "1000:1000"'), 2)
        self.assertGreaterEqual(compose.count("read_only: true"), 2)
        self.assertNotIn("./entrypoint.sh:/entrypoint.sh", compose)
        self.assertIn("tmpfs:", compose)

    def test_startup_fails_closed_on_unsafe_rootless_mount_ownership(self) -> None:
        startup = (ROOT / "scripts/start-openclaw.sh").read_text()
        self.assertIn('[[ -L "$writable_root" ]]', startup)
        self.assertIn("stat -c '%u'", startup)
        self.assertIn('"$owner_uid" != "1000"', startup)


if __name__ == "__main__":
    unittest.main()
