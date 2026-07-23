#!/bin/sh
set -eu

fail() {
  echo "Mira image validation failed: $*" >&2
  exit 1
}

[ "$(id -u)" = "1000" ] || fail "entrypoint must run as node (uid 1000)"
for path in /home/node/.openclaw /home/node/.openclaw/workspace; do
  [ -d "$path" ] || fail "missing writable mount: $path"
  [ -w "$path" ] || fail "mount is not writable by node: $path"
done
for command in git gh jq rg curl python3 agent gog; do
  command -v "$command" >/dev/null 2>&1 || fail "missing tool: $command"
done

[ "$(agent --version 2>/dev/null)" = "${CURSOR_AGENT_VERSION:?}" ] ||
  fail "Cursor Agent version mismatch"
gh --version | sed -n '1p' | grep -F "gh version ${GH_VERSION:?} " >/dev/null ||
  fail "GitHub CLI version mismatch"
gog --version 2>&1 | grep -F "${GOGCLI_VERSION:?}" >/dev/null ||
  fail "gogcli version mismatch"
python3 -c 'import requests' >/dev/null 2>&1 ||
  fail "python requests module unavailable"

exec "$@"
