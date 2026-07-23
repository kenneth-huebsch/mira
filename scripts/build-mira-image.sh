#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="${OPENCLAW_SOURCE:-$ROOT/openclaw-src}"
IMAGE="${MIRA_OPENCLAW_IMAGE:-openclaw-mira:local}"
LOCK="$SOURCE/toolchain.lock.json"

for file in Dockerfile.mira entrypoint.sh toolchain.lock.json; do
  [[ -f "$SOURCE/$file" && ! -L "$SOURCE/$file" ]] || {
    echo "missing or unsafe source file: $SOURCE/$file" >&2
    exit 1
  }
done

values="$(
  python3 - "$LOCK" <<'PY'
import json, re, sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
if data.get("schema_version") != 2:
    raise SystemExit("toolchain lock schema_version must be 2")
base = data.get("base_image")
if not isinstance(base, dict) or set(base) != {"source_tag", "digest", "source_revision"}:
    raise SystemExit("toolchain lock base_image fields are invalid")
patterns = {
    "source_tag": r"[A-Za-z0-9][A-Za-z0-9._/-]*:[A-Za-z0-9][A-Za-z0-9._-]*",
    "digest": r"sha256:[0-9a-f]{64}",
    "source_revision": r"[0-9a-f]{40}",
}
for name, pattern in patterns.items():
    if not isinstance(base.get(name), str) or not re.fullmatch(pattern, base[name]):
        raise SystemExit(f"toolchain lock base_image.{name} is invalid")
packages = data.get("debian_packages")
expected_packages = {"gh", "jq", "python3-pip", "python3-requests", "ripgrep"}
if not isinstance(packages, dict) or set(packages) != expected_packages:
    raise SystemExit("toolchain lock Debian package fields are invalid")
fields = [
    base["source_tag"], base["digest"], base["source_revision"],
    data.get("gh_version"),
    packages["gh"], packages["jq"], packages["python3-pip"],
    packages["python3-requests"], packages["ripgrep"],
    data.get("cursor", {}).get("version"),
    data.get("cursor", {}).get("linux_amd64_sha256"),
    data.get("cursor", {}).get("linux_arm64_sha256"),
    data.get("gogcli", {}).get("version"),
    data.get("gogcli", {}).get("linux_amd64_sha256"),
    data.get("gogcli", {}).get("linux_arm64_sha256"),
]
if not isinstance(fields[3], str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", fields[3]):
    raise SystemExit("toolchain lock gh_version is invalid")
for value in fields:
    if not isinstance(value, str) or not value or "\n" in value:
        raise SystemExit("toolchain lock contains an invalid build value")
for value in (fields[10], fields[11], fields[13], fields[14]):
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise SystemExit("toolchain lock contains an invalid artifact checksum")
print("\n".join(fields))
PY
)"
mapfile -t lock_values <<<"$values"
if [[ "${#lock_values[@]}" -ne 15 ]]; then
  echo "toolchain lock did not produce the expected build values" >&2
  exit 1
fi

base_tag="${lock_values[0]}"
base_digest="${lock_values[1]}"
source_revision="${lock_values[2]}"
actual_revision="$(git -C "$SOURCE" rev-parse HEAD)"
[[ "$actual_revision" == "$source_revision" ]] || {
  echo "OpenClaw source revision mismatch: expected $source_revision, got $actual_revision" >&2
  exit 1
}

image_data="$(docker image inspect "$base_tag" --format '{{.Id}} {{json .RepoDigests}}')"
image_id="${image_data%% *}"
repo_digests="${image_data#* }"
[[ "$image_id" == "$base_digest" && "$repo_digests" == *"@$base_digest"* ]] || {
  echo "OpenClaw base image mismatch: expected $base_digest for $base_tag" >&2
  exit 1
}
base_repository="${base_tag%:*}"
base_reference="$base_repository@$base_digest"

exec docker build --pull=false \
  --build-arg "OPENCLAW_BASE_IMAGE=$base_reference" \
  --build-arg "OPENCLAW_BASE_DIGEST=$base_digest" \
  --build-arg "OPENCLAW_SOURCE_REVISION=$source_revision" \
  --build-arg "GH_VERSION=${lock_values[3]}" \
  --build-arg "GH_DEBIAN_PACKAGE=${lock_values[4]}" \
  --build-arg "JQ_DEBIAN_PACKAGE=${lock_values[5]}" \
  --build-arg "PYTHON3_PIP_DEBIAN_PACKAGE=${lock_values[6]}" \
  --build-arg "PYTHON3_REQUESTS_DEBIAN_PACKAGE=${lock_values[7]}" \
  --build-arg "RIPGREP_DEBIAN_PACKAGE=${lock_values[8]}" \
  --build-arg "CURSOR_VERSION=${lock_values[9]}" \
  --build-arg "CURSOR_AMD64_SHA256=${lock_values[10]}" \
  --build-arg "CURSOR_ARM64_SHA256=${lock_values[11]}" \
  --build-arg "GOG_VERSION=${lock_values[12]}" \
  --build-arg "GOG_AMD64_SHA256=${lock_values[13]}" \
  --build-arg "GOG_ARM64_SHA256=${lock_values[14]}" \
  -f "$SOURCE/Dockerfile.mira" -t "$IMAGE" "$SOURCE"
