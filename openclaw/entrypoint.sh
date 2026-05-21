#!/bin/sh
set -eu

ensure_runtime_tools() {
  if ! command -v jq >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1; then
    apt-get update -qq >/dev/null
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends jq curl >/dev/null
  fi
}

prepare_gogcli_runtime() {
  xdg_config_home="${XDG_CONFIG_HOME:-/home/node/.openclaw}"
  gogcli_config_dir="${xdg_config_home}/gogcli"
  default_config_parent="/home/node/.config"
  default_gogcli_config_dir="${default_config_parent}/gogcli"
  export XDG_CONFIG_HOME="$xdg_config_home"

  mkdir -p "$gogcli_config_dir"
  mkdir -p "$default_config_parent"
  if [ -d "$default_gogcli_config_dir" ] && [ ! -e "$default_gogcli_config_dir/credentials.json" ] && [ ! -e "$default_gogcli_config_dir/keyring" ]; then
    rm -rf "$default_gogcli_config_dir"
  fi
  if [ ! -e "$default_gogcli_config_dir" ]; then
    ln -s "$gogcli_config_dir" "$default_gogcli_config_dir"
  fi
  chown -R node:node "$gogcli_config_dir" "$default_config_parent"
}

prepare_npm_runtime() {
  npm_cache_dir="${NPM_CONFIG_CACHE:-/home/node/.npm}"
  mkdir -p "$npm_cache_dir"
  chown -R node:node "$npm_cache_dir"
}

prepare_gh_runtime() {
  xdg_config_home="${XDG_CONFIG_HOME:-/home/node/.openclaw}"
  gh_config_dir="${GH_CONFIG_DIR:-${xdg_config_home}/gh}"
  default_config_parent="/home/node/.config"
  default_gh_config_dir="${default_config_parent}/gh"
  mkdir -p "$gh_config_dir"
  mkdir -p "$default_config_parent"
  if [ -d "$default_gh_config_dir" ] && [ ! -e "$default_gh_config_dir/hosts.yml" ]; then
    rm -rf "$default_gh_config_dir"
  fi
  if [ ! -e "$default_gh_config_dir" ]; then
    ln -s "$gh_config_dir" "$default_gh_config_dir"
  fi
  chown -R node:node "$gh_config_dir" "$default_config_parent"
  export GH_CONFIG_DIR="$gh_config_dir"
}

ensure_mysql_python_runtime() {
  if python3 - <<'PY' >/dev/null 2>&1
import pymysql
PY
  then
    return 0
  fi

  apt-get update -qq >/dev/null
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends python3-pymysql >/dev/null
}

ensure_aws_python_runtime() {
  if python3 - <<'PY' >/dev/null 2>&1
import boto3
PY
  then
    return 0
  fi

  apt-get update -qq >/dev/null
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends python3-boto3 >/dev/null
}

ensure_dripr_debug_python_runtime() {
  if python3 - <<'PY' >/dev/null 2>&1
import venv
PY
  then
    return 0
  fi

  apt-get update -qq >/dev/null
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends python3.11-venv python3-dev default-libmysqlclient-dev build-essential pkg-config >/dev/null
}

ensure_github_cli_runtime() {
  if command -v gh >/dev/null 2>&1; then
    return 0
  fi

  apt-get update -qq >/dev/null
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends gh >/dev/null
}

install_qmd_runtime() {
  if [ "${OPENCLAW_INSTALL_QMD:-1}" = "0" ]; then
    return 0
  fi

  xdg_config_home="${XDG_CONFIG_HOME:-/home/node/.openclaw}"
  qmd_runtime_root="${OPENCLAW_QMD_RUNTIME_ROOT:-${xdg_config_home}/runtime/qmd}"
  qmd_bin_dir="${OPENCLAW_QMD_BIN_DIR:-${xdg_config_home}/bin}"
  qmd_package="${OPENCLAW_QMD_PACKAGE:-@tobilu/qmd@2.1.0}"
  qmd_bin="${qmd_runtime_root}/node_modules/.bin/qmd"

  mkdir -p "$qmd_runtime_root" "$qmd_bin_dir"
  chown -R node:node "$qmd_runtime_root" "$qmd_bin_dir"

  if [ ! -x "$qmd_bin" ]; then
    npm install --no-save --prefix "$qmd_runtime_root" "$qmd_package" >/dev/null
  fi

  ln -sfn "$qmd_bin" "${qmd_bin_dir}/qmd"
  chown -R node:node "$qmd_runtime_root" "$qmd_bin_dir"
  export PATH="${qmd_bin_dir}:${PATH}"
}

install_agent_browser_runtime() {
  if [ "${OPENCLAW_INSTALL_AGENT_BROWSER:-1}" = "0" ]; then
    return 0
  fi

  xdg_config_home="${XDG_CONFIG_HOME:-/home/node/.openclaw}"
  agent_browser_runtime_root="${OPENCLAW_AGENT_BROWSER_RUNTIME_ROOT:-${xdg_config_home}/runtime/agent-browser}"
  agent_browser_bin_dir="${OPENCLAW_AGENT_BROWSER_BIN_DIR:-${xdg_config_home}/bin}"
  agent_browser_home="${OPENCLAW_AGENT_BROWSER_HOME:-${xdg_config_home}/agent-browser}"
  agent_browser_package="${OPENCLAW_AGENT_BROWSER_PACKAGE:-agent-browser@latest}"
  agent_browser_apt_packages="libnspr4 libnss3 libatk1.0-0 libatk-bridge2.0-0 libdbus-1-3 libcups2 libxkbcommon0 libasound2 libgbm1 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libatspi2.0-0"
  agent_browser_bin="${agent_browser_runtime_root}/node_modules/.bin/agent-browser"

  mkdir -p "$agent_browser_runtime_root" "$agent_browser_bin_dir" "$agent_browser_home"
  chown -R node:node "$agent_browser_runtime_root" "$agent_browser_bin_dir" "$agent_browser_home"

  if ! dpkg-query -W -f='${Status}' libnspr4 2>/dev/null | awk '/installed/ { found=1 } END { exit found ? 0 : 1 }'; then
    apt-get update -qq >/dev/null
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends $agent_browser_apt_packages >/dev/null
  fi

  if [ ! -x "$agent_browser_bin" ]; then
    npm install --no-save --prefix "$agent_browser_runtime_root" "$agent_browser_package" >/dev/null
  fi

  ln -sfn "$agent_browser_bin" "${agent_browser_bin_dir}/agent-browser"
  rm -rf /home/node/.agent-browser
  ln -sfn "$agent_browser_home" /home/node/.agent-browser
  export AGENT_BROWSER_HOME="$agent_browser_home"

  HOME=/home/node XDG_CONFIG_HOME="$xdg_config_home" AGENT_BROWSER_HOME="$agent_browser_home" "$agent_browser_bin" install >/dev/null

  chown -R node:node "$agent_browser_runtime_root" "$agent_browser_bin_dir" "$agent_browser_home"
  export PATH="${agent_browser_bin_dir}:${PATH}"
}

install_cursor_agent_runtime() {
  if [ "${OPENCLAW_INSTALL_CURSOR_AGENT:-1}" = "0" ]; then
    return 0
  fi

  cursor_agent_bin_dir="${OPENCLAW_CURSOR_AGENT_BIN_DIR:-/home/node/.local/bin}"
  cursor_agent_bin="${cursor_agent_bin_dir}/agent"
  mkdir -p "$cursor_agent_bin_dir"
  chown -R node:node "$cursor_agent_bin_dir" /home/node/.local

  if [ ! -x "$cursor_agent_bin" ]; then
    su -m -s /bin/sh node -c 'export HOME=/home/node; export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-/home/node/.openclaw}"; curl https://cursor.com/install -fsS | sh' >/dev/null
  fi

  ln -sfn "$cursor_agent_bin" /usr/local/bin/agent
  chown -R node:node /home/node/.local
  export PATH="${cursor_agent_bin_dir}:${PATH}"
}

install_gogcli() {
  gogcli_version="${OPENCLAW_GOGCLI_VERSION:-0.12.0}"
  gogcli_version="${gogcli_version#v}"
  gogcli_tag="v${gogcli_version}"
  gogcli_root="${OPENCLAW_GOGCLI_ROOT:-/home/node/.openclaw/tools/gogcli}"
  gogcli_bin_dir="${OPENCLAW_GOGCLI_BIN_DIR:-/home/node/.openclaw/bin}"
  gogcli_install_dir="${gogcli_root}/${gogcli_version}"
  gogcli_bin="${gogcli_install_dir}/gog"

  case "$(dpkg --print-architecture)" in
    amd64)
      gogcli_arch="amd64"
      ;;
    arm64)
      gogcli_arch="arm64"
      ;;
    *)
      echo "Unsupported architecture for gogcli: $(dpkg --print-architecture)" >&2
      exit 1
      ;;
  esac

  mkdir -p "$gogcli_root" "$gogcli_bin_dir"

  if [ ! -x "$gogcli_bin" ]; then
    asset="gogcli_${gogcli_version}_linux_${gogcli_arch}.tar.gz"
    base_url="https://github.com/steipete/gogcli/releases/download/${gogcli_tag}"
    tmpdir="$(mktemp -d)"
    trap 'rm -rf "$tmpdir"' EXIT HUP INT TERM

    curl -fsSL "${base_url}/checksums.txt" -o "${tmpdir}/checksums.txt"
    curl -fsSL "${base_url}/${asset}" -o "${tmpdir}/${asset}"

    expected_checksum="$(awk -v asset="$asset" '$2 == asset { print $1 }' "${tmpdir}/checksums.txt")"
    actual_checksum="$(sha256sum "${tmpdir}/${asset}" | awk '{ print $1 }')"

    if [ -z "$expected_checksum" ] || [ "$expected_checksum" != "$actual_checksum" ]; then
      echo "gogcli checksum verification failed for ${asset}" >&2
      exit 1
    fi

    rm -rf "$gogcli_install_dir" "${gogcli_install_dir}.tmp"
    mkdir -p "${gogcli_install_dir}.tmp"
    tar -xzf "${tmpdir}/${asset}" -C "${gogcli_install_dir}.tmp" gog
    chmod 755 "${gogcli_install_dir}.tmp/gog"
    mv "${gogcli_install_dir}.tmp" "$gogcli_install_dir"
    rm -rf "$tmpdir"
    trap - EXIT HUP INT TERM
  fi

  ln -sf "$gogcli_bin" "${gogcli_bin_dir}/gog"
  ln -sf "$gogcli_bin" /usr/local/bin/gog
  chown -R node:node "$gogcli_root" "$gogcli_bin_dir"
  export PATH="${gogcli_bin_dir}:${PATH}"
}

ensure_runtime_tools
prepare_gogcli_runtime
prepare_npm_runtime
prepare_gh_runtime
ensure_mysql_python_runtime
ensure_aws_python_runtime
ensure_dripr_debug_python_runtime
ensure_github_cli_runtime
install_gogcli
install_qmd_runtime
install_agent_browser_runtime
install_cursor_agent_runtime

exec env PATH="$PATH" AGENT_BROWSER_HOME="${AGENT_BROWSER_HOME:-}" GH_CONFIG_DIR="${GH_CONFIG_DIR:-}" su -m -s /bin/sh node -c 'exec "$@"' -- "$@"
