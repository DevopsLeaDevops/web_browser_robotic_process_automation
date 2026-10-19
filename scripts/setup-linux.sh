#!/usr/bin/env bash
# RHEL／CentOS 衍生版的無桌面伺服器安裝；macOS／本機開發請用 setup.sh。
set -Eeuo pipefail

REPO_URL="https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation.git"
TARGET_DIR="${RPA_DIR:-$HOME/code/web_browser_robotic_process_automation}"
SKIP_SYSTEM_PACKAGES=0
INSTALL_SERVICE=0
REPO_DIR=""
UV=""
PACKAGE_MANAGER=""

die() { printf '\n錯誤：%s\n' "$*" >&2; exit 1; }
info() { printf '\n%s\n' "$*"; }
trap 'printf "\n安裝失敗（第 %s 行）；修正上述錯誤後可重新執行。\n" "$LINENO" >&2' ERR

usage() {
  cat <<'EOF'
用法：bash scripts/setup-linux.sh [選項]

安裝 RHEL／CentOS／Fedora 及 ID_LIKE 包含這些名稱的公司 Linux 伺服器。
優先使用 yum，其次 dnf；需要 x86_64／aarch64、glibc 2.28 以上。
只安裝伺服器依賴，不下載瀏覽器、不安裝桌面 App 或開發工具。

  --dir <路徑>             尚無程式碼時的 clone 位置（或設定 RPA_DIR）
  --skip-system-packages    系統套件已由管理員安裝，略過 yum／dnf
  --install-service         安裝並啟動 systemd 的 rpa-server.service
  -h, --help                顯示說明

一般帳號執行即可；安裝系統套件與 systemd 服務時會呼叫 sudo。
首次安裝可設定 RPA_DATA_DIR（預設 ~/.local/share/rpa-server）、
RPA_PORT（8080）、RPA_WORKER_PORT（8081）、RPA_WORKER_HOST（0.0.0.0）。
後續修改專案內 .rpa-server.env；重跑安裝會保留該設定與資料。
管理頁面只監聽 127.0.0.1；裝置使用有權杖驗證的 Worker／Client API。
內網可設定 HTTPS_PROXY、UV_PYTHON_INSTALL_MIRROR、UV_NATIVE_TLS；
套件鏡像與鎖檔的限制見 docs/develop/setup.html#linux-server。
EOF
}

parse_args() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --dir)
        [ $# -ge 2 ] && [ -n "$2" ] && [[ "$2" != --* ]] || die '--dir 後面需要路徑。'
        TARGET_DIR="$2"; shift 2 ;;
      --dir=*) TARGET_DIR="${1#--dir=}"; [ -n "$TARGET_DIR" ] || die '--dir 不能為空。'; shift ;;
      --skip-system-packages) SKIP_SYSTEM_PACKAGES=1; shift ;;
      --install-service) INSTALL_SERVICE=1; shift ;;
      -h|--help) usage; exit 0 ;;
      *) die "不認得的選項：$1（見 --help）" ;;
    esac
  done
}

version_ge() {
  local have="$1." need="$2." h n i
  for i in 1 2 3; do
    h="${have%%.*}"; n="${need%%.*}"
    have="${have#*.}"; need="${need#*.}"
    h="${h%%[!0-9]*}"; n="${n%%[!0-9]*}"
    [ "${h:-0}" -gt "${n:-0}" ] && return 0
    [ "${h:-0}" -lt "${n:-0}" ] && return 1
  done
  return 0
}

check_system() {
  [ "$(uname -s)" = Linux ] || die '此腳本只適用於 Linux 伺服器。'
  case "$(uname -m)" in
    x86_64|aarch64) ;;
    *) die '目前只支援 x86_64 與 aarch64。' ;;
  esac
  # 公司版本可能有自己的 ID，不能只比對 ID=centos 或 VERSION_ID。
  local ID="" ID_LIKE="" PRETTY_NAME="" family glibc release_file="${1:-/etc/os-release}"
  [ -r "$release_file" ] || die '找不到 /etc/os-release，無法辨識系統。'
  # shellcheck source=/dev/null
  . "$release_file"
  case " $ID $ID_LIKE " in
    *' rhel '*|*' centos '*|*' fedora '*) ;;
    *) die "此腳本適用於 RHEL／CentOS 系（目前：${PRETTY_NAME:-$ID}）。其他 Linux 請用 setup.sh。" ;;
  esac
  glibc="$(getconf GNU_LIBC_VERSION 2>/dev/null || true)"
  family="${glibc%% *}"
  [ "$family" = glibc ] && version_ge "${glibc#* }" 2.28 ||
    die "需要 glibc 2.28 以上，目前為 ${glibc:-未知}。請使用較新的公司 Linux 映像；不要替換系統 glibc。"
  if command -v yum >/dev/null 2>&1; then PACKAGE_MANAGER=yum
  elif command -v dnf >/dev/null 2>&1; then PACKAGE_MANAGER=dnf
  else die '找不到 yum 或 dnf。'
  fi
  info "系統：${PRETTY_NAME:-${ID:-$ID_LIKE}}，$(uname -m)，${glibc}；套件管理員：${PACKAGE_MANAGER}"
}

as_root() {
  if [ "$(id -u)" = 0 ]; then "$@"
  elif command -v sudo >/dev/null 2>&1; then sudo "$@"
  else die '這一步需要管理員權限。請由管理員安裝系統套件後使用 --skip-system-packages。'
  fi
}

check_service() {
  if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet rpa-server.service; then
    die 'rpa-server.service 正在執行。請先 sudo systemctl stop rpa-server，再更新環境，完成後重新啟動。'
  fi
  if [ "$INSTALL_SERVICE" = 1 ]; then
    command -v systemctl >/dev/null 2>&1 && systemctl show-environment >/dev/null 2>&1 ||
      die '目前沒有可用的 systemd（例如容器）。請省略 --install-service，使用前景啟動命令。'
  fi
}

install_system_packages() {
  if [ "$SKIP_SYSTEM_PACKAGES" = 1 ]; then
    info '略過系統套件安裝（由管理員預先準備）。'
    return
  fi
  info "使用 ${PACKAGE_MANAGER} 安裝 Git、curl、CA 憑證與執行函式庫。"
  as_root "$PACKAGE_MANAGER" install -y git curl ca-certificates tar gzip libstdc++ libgcc
}

is_repo() { [ -f "$1/uv.lock" ] && [ -f "$1/apps/cli/pyproject.toml" ]; }

prepare_code() {
  local src="${BASH_SOURCE[0]:-}" here=""
  if [ -f "$src" ]; then here="$(cd "$(dirname "$src")/.." && pwd)"; fi
  if [ -n "$here" ] && is_repo "$here"; then REPO_DIR="$here"
  elif is_repo "$PWD"; then REPO_DIR="$PWD"
  elif is_repo "$TARGET_DIR"; then REPO_DIR="$(cd "$TARGET_DIR" && pwd)"
  else
    command -v git >/dev/null 2>&1 || die '請先 yum install git（或請管理員安裝）。'
    git clone "$REPO_URL" "$TARGET_DIR"
    if [ -n "${RPA_GIT_REF:-}" ]; then
      git -C "$TARGET_DIR" fetch origin "$RPA_GIT_REF"
      git -C "$TARGET_DIR" checkout --detach FETCH_HEAD
    fi
    REPO_DIR="$(cd "$TARGET_DIR" && pwd)"
  fi
  cd "$REPO_DIR"
  info "使用程式碼：${REPO_DIR}（既有工作區不自動 pull 或切換分支）。"
}

find_uv() {
  local candidate
  UV="$(command -v uv || true)"
  [ -z "$UV" ] || return 0
  for candidate in "${UV_INSTALL_DIR:-$HOME/.local/bin}/uv" "${XDG_BIN_HOME:-$HOME/.local/bin}/uv" "$HOME/.cargo/bin/uv"; do
    if [ -x "$candidate" ]; then UV="$candidate"; return; fi
  done
}

install_runtime() {
  local need version installer
  find_uv
  if [ -z "$UV" ]; then
    command -v curl >/dev/null 2>&1 || die '請先 yum install curl。'
    # 完整下載成功才執行；不讓失敗下載的半份腳本進入 sh。
    installer="$(mktemp)"
    if ! curl -LsSf https://astral.sh/uv/install.sh -o "$installer"; then
      rm -f "$installer"; die '下載 uv 失敗。可先用公司核准的方式安裝 uv，再重跑。'
    fi
    if ! env UV_NO_MODIFY_PATH=1 sh "$installer"; then
      rm -f "$installer"; die 'uv 安裝失敗。'
    fi
    rm -f "$installer"
    find_uv
  fi
  [ -n "$UV" ] || die '找不到 uv；請將 uv 的安裝目錄加入 PATH。'
  need="$(sed -n 's/^required-version *= *">= *\([0-9][0-9.]*\)".*/\1/p' pyproject.toml | head -n 1)"
  version="$("$UV" --version | awk '{print $2}')"
  version_ge "$version" "${need:-0.11}" || die "uv ${version} 太舊，請依原安裝方式升級至 ${need:-0.11} 以上。"
  info "使用 uv ${version} 安裝獨立的 .venv-server；保留開發用的 .venv。"
  UV_PROJECT_ENVIRONMENT="$REPO_DIR/.venv-server" "$UV" sync --locked --package rpa-cli --no-default-groups --managed-python
  "$REPO_DIR/.venv-server/bin/rpa" --version
  "$REPO_DIR/.venv-server/bin/python" -c 'import sqlite3; from rpa_server.app import create_app; from rpa_server.config import Settings'
}

# systemd 字串與 Shell 的跳脫規則不同；ExecStart 的 $、所有欄位的 % 都要單獨處理。
systemd_quote() {
  local value="$1"
  value="${value//\\/\\\\}"; value="${value//\"/\\\"}"; value="${value//%/%%}"
  printf '"%s"' "$value"
}

write_launchers() {
  local launcher="$REPO_DIR/.venv-server/bin/rpa-server" unit="$REPO_DIR/.venv-server/rpa-server.service"
  case "$REPO_DIR$HOME" in
    *$'\n'*|*$'\r'*) die '專案與家目錄路徑不能包含換行字元。' ;;
  esac
  # 設定只在首次建立；升級保留資料位置、埠號與使用者自行加入的環境變數。
  if [ ! -e .rpa-server.env ]; then
    (
      umask 077
      {
      printf '# Linux 伺服器設定（Bash 語法）；修改後重新啟動服務。\n'
      printf 'export RPA_DATA_DIR=%q\n' "${RPA_DATA_DIR:-$HOME/.local/share/rpa-server}"
      printf 'export RPA_PORT=%q\n' "${RPA_PORT:-8080}"
      printf 'export RPA_WORKER_PORT=%q\n' "${RPA_WORKER_PORT:-8081}"
      printf 'export RPA_WORKER_HOST=%q\n' "${RPA_WORKER_HOST:-0.0.0.0}"
      } > .rpa-server.env
    )
  fi
  {
    printf '#!/usr/bin/env bash\nset -Eeuo pipefail\numask 077\n'
    printf 'cd %q\nsource %q\n' "$REPO_DIR" "$REPO_DIR/.rpa-server.env"
    printf 'mkdir -p "$RPA_DATA_DIR"\n'
    printf 'exec %q serve --host 127.0.0.1 --port "$RPA_PORT" --data "$RPA_DATA_DIR" --worker-host "$RPA_WORKER_HOST" --worker-port "$RPA_WORKER_PORT" --no-local-worker --no-testsite\n' "$REPO_DIR/.venv-server/bin/rpa"
  } > "$launcher"
  chmod 755 "$launcher"
  {
    printf '[Unit]\nDescription=RPA Server\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=simple\n'
    printf 'User=%s\n' "$(id -un)"
    printf 'WorkingDirectory=%s\n' "$(systemd_quote "$REPO_DIR")"
    printf 'Environment=%s\n' "$(systemd_quote "HOME=$HOME")"
    printf 'Environment=PYTHONUTF8=1\nUMask=0077\n'
    printf 'ExecStart=/bin/bash %s\n' "$(systemd_quote "${launcher//\$/\$\$}")"
    printf 'Restart=on-failure\nRestartSec=5\nTimeoutStopSec=30\n\n[Install]\nWantedBy=multi-user.target\n'
  } > "$unit"
  if [ "$INSTALL_SERVICE" = 1 ]; then
    as_root install -m 644 "$unit" /etc/systemd/system/rpa-server.service
    as_root systemctl daemon-reload
    as_root systemctl enable --now rpa-server.service
    as_root systemctl is-active --quiet rpa-server.service
  fi
  info '安裝完成。設定檔：.rpa-server.env；資料目錄沿用設定檔，不會清除。'
  printf '前景啟動：%q\n' "$launcher"
  if [ "$INSTALL_SERVICE" = 1 ]; then
    printf '背景服務：sudo systemctl status rpa-server\n日誌：sudo journalctl -u rpa-server -f\n'
  else
    printf '需要背景服務時：bash scripts/setup-linux.sh --install-service\n'
  fi
  printf '首次配對：用 SSH 轉發管理埠，在「裝置」頁建立邀請；錄製端／Worker 連線到伺服器的裝置埠。\n'
  printf '詳細說明：docs/develop/setup.html#linux-server\n'
}

main() {
  parse_args "$@"
  check_system
  check_service
  install_system_packages
  prepare_code
  install_runtime
  write_launchers
}

# 可由測試載入函式；直接執行與 curl | bash 都進入主流程。
if [ -z "${BASH_SOURCE[0]:-}" ] || [ "${BASH_SOURCE[0]}" = "$0" ]; then main "$@"; fi
