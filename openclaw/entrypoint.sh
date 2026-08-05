#!/bin/sh
set -eu

ensure_runtime_tools() {
  if ! command -v jq >/dev/null 2>&1 || ! command -v rg >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1 || ! command -v git >/dev/null 2>&1 || ! command -v bash >/dev/null 2>&1 || ! command -v unzip >/dev/null 2>&1 || ! python3 -m pip --version >/dev/null 2>&1 || ! python3 -c 'import requests' >/dev/null 2>&1; then
    apt-get update -qq >/dev/null
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends jq ripgrep curl git bash unzip ca-certificates python3-pip python3-requests >/dev/null
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

ensure_python_requests_runtime() {
  if su -m -s /bin/sh node -c 'python3 -c "import requests" >/dev/null 2>&1'; then
    return 0
  fi

  su -m -s /bin/sh node -c 'python3 -m pip install --user --break-system-packages --quiet requests'
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

ensure_github_cli_runtime() {
  if command -v gh >/dev/null 2>&1; then
    return 0
  fi

  apt-get update -qq >/dev/null
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends gh >/dev/null
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
    su -m -s /bin/bash node -c 'export HOME=/home/node; export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-/home/node/.openclaw}"; curl https://cursor.com/install -fsS | bash' >/dev/null
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

install_aws_cli() {
  aws_cli_version="${OPENCLAW_AWS_CLI_VERSION:-2.36.14}"
  aws_cli_root="${OPENCLAW_AWS_CLI_ROOT:-/home/node/.openclaw/tools/aws-cli}"
  aws_cli_bin_dir="${OPENCLAW_AWS_CLI_BIN_DIR:-/home/node/.openclaw/bin}"
  aws_cli_install_dir="${aws_cli_root}/${aws_cli_version}"
  aws_cli_bin="${aws_cli_install_dir}/v2/current/bin/aws"

  case "$(dpkg --print-architecture)" in
    amd64)
      aws_cli_arch="x86_64"
      aws_cli_checksum="${OPENCLAW_AWS_CLI_SHA256_X86_64:-43b34875482244039716cc3725d1f60e7d47ef3cfb2a19e114759a46db24dc30}"
      ;;
    arm64)
      aws_cli_arch="aarch64"
      aws_cli_checksum="${OPENCLAW_AWS_CLI_SHA256_AARCH64:-61e2fb72b36dc0ad98912b3a7b7469c886b90ea703f1096428a152ab09babd8a}"
      ;;
    *)
      echo "Unsupported architecture for AWS CLI: $(dpkg --print-architecture)" >&2
      exit 1
      ;;
  esac

  mkdir -p "$aws_cli_root" "$aws_cli_bin_dir"

  if [ ! -x "$aws_cli_bin" ]; then
    aws_cli_archive="awscli-exe-linux-${aws_cli_arch}-${aws_cli_version}.zip"
    aws_cli_url="https://awscli.amazonaws.com/${aws_cli_archive}"
    aws_cli_tmpdir="$(mktemp -d)"
    trap 'rm -rf "$aws_cli_tmpdir"' EXIT HUP INT TERM

    curl -fsSL "$aws_cli_url" -o "${aws_cli_tmpdir}/${aws_cli_archive}"
    printf '%s  %s\n' "$aws_cli_checksum" "${aws_cli_tmpdir}/${aws_cli_archive}" | sha256sum -c - >/dev/null
    unzip -q "${aws_cli_tmpdir}/${aws_cli_archive}" -d "$aws_cli_tmpdir"

    rm -rf "$aws_cli_install_dir"
    "${aws_cli_tmpdir}/aws/install" \
      --install-dir "$aws_cli_install_dir" \
      --bin-dir "${aws_cli_install_dir}/bin"

    rm -rf "$aws_cli_tmpdir"
    trap - EXIT HUP INT TERM
  fi

  ln -sfn "$aws_cli_bin" "${aws_cli_bin_dir}/aws"
  ln -sfn "$aws_cli_bin" /usr/local/bin/aws
  chown -R node:node "$aws_cli_root" "$aws_cli_bin_dir"
  export PATH="${aws_cli_bin_dir}:${PATH}"
}

install_aws_cdk() {
  aws_cdk_version="${OPENCLAW_AWS_CDK_VERSION:-2.1134.0}"
  aws_cdk_root="${OPENCLAW_AWS_CDK_ROOT:-/home/node/.openclaw/tools/aws-cdk}"
  aws_cdk_bin_dir="${OPENCLAW_AWS_CDK_BIN_DIR:-/home/node/.openclaw/bin}"
  aws_cdk_install_dir="${aws_cdk_root}/${aws_cdk_version}"
  aws_cdk_bin="${aws_cdk_install_dir}/bin/cdk"

  mkdir -p "$aws_cdk_root" "$aws_cdk_bin_dir"
  chown -R node:node "$aws_cdk_root" "$aws_cdk_bin_dir"

  if [ ! -x "$aws_cdk_bin" ]; then
    rm -rf "$aws_cdk_install_dir"
    mkdir -p "$aws_cdk_install_dir"
    chown -R node:node "$aws_cdk_install_dir"
    su -m -s /bin/sh node -c \
      'npm install --global --prefix "$1" --no-audit --no-fund "$2"' \
      sh "$aws_cdk_install_dir" "aws-cdk@${aws_cdk_version}"
  fi

  ln -sfn "$aws_cdk_bin" "${aws_cdk_bin_dir}/cdk"
  ln -sfn "$aws_cdk_bin" /usr/local/bin/cdk
  chown -R node:node "$aws_cdk_root" "$aws_cdk_bin_dir"
  export PATH="${aws_cdk_bin_dir}:${PATH}"
}

ensure_runtime_tools
prepare_gogcli_runtime
prepare_npm_runtime
ensure_python_requests_runtime
prepare_gh_runtime
ensure_github_cli_runtime
install_gogcli
install_aws_cli
install_aws_cdk
install_cursor_agent_runtime

exec env PATH="$PATH" GH_CONFIG_DIR="${GH_CONFIG_DIR:-}" su -m -s /bin/sh node -c 'exec "$@"' -- "$@"
