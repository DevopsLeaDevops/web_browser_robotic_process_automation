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
MIRROR="${RPA_PYPI_MIRROR:-}"
MIRROR_NAME=""
MIRROR_SIMPLE=""
MIRROR_FILES=""
LOCK_BACKUP=""
PYPI_FILES="https://files.pythonhosted.org/"

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
  --mirror <來源>           Python 套件從哪裡下載（也可設定 RPA_PYPI_MIRROR）：auto（預設，
                            測速後選內容正確而且最快的）、pypi、tuna、ustc、aliyun、tencent、
                            huawei，或公司鏡像的 simple 網址
  -h, --help                顯示說明

一般帳號執行即可；安裝系統套件與 systemd 服務時會呼叫 sudo。
首次安裝可設定 RPA_DATA_DIR（預設 ~/.local/share/rpa-server）、
RPA_PORT（8080）、RPA_WORKER_PORT（8081）、RPA_WORKER_HOST（0.0.0.0）、
RPA_TESTSITE_HOST（預設空白＝不啟動測試網站；0.0.0.0＝在 8765 對其他電腦開放）。
後續修改專案內 .rpa-server.env；重跑安裝會保留該設定與資料。
管理頁面只監聽 127.0.0.1；裝置使用有權杖驗證的 Worker／Client API。
內網可設定 HTTPS_PROXY、UV_PYTHON_INSTALL_MIRROR、UV_NATIVE_TLS；有設定 UV_INDEX_URL 或
UV_DEFAULT_INDEX、沒有指定 --mirror 時就用它當套件來源。用鏡像時版本與 sha256 照 uv.lock，
見 docs/develop/setup.html#linux-server。
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
      --mirror)
        [ $# -ge 2 ] && [ -n "$2" ] && [[ "$2" != --* ]] || die '--mirror 後面需要來源名稱或網址。'
        MIRROR="$2"; shift 2 ;;
      --mirror=*) MIRROR="${1#--mirror=}"; [ -n "$MIRROR" ] || die '--mirror 不能為空。'; shift ;;
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
  if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet rpa-server.service 2>/dev/null; then
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

# ---------------------------------------------------------------- 套件來源
# uv sync --locked 照 uv.lock 下載：鎖檔記著 PyPI 的索引與每個檔案的網址（files.pythonhosted.org）。
# 單設 UV_INDEX_URL 會讓 uv 判定鎖檔過期；所以用鏡像時把這次安裝用的 uv.lock 暫時換成鏡像的網址
# （版本、檔案與 sha256 都不變，uv 下載後照樣驗證雜湊），裝完就還原。

# 內建的來源：名稱、simple 索引、檔案網址的開頭（取代 https://files.pythonhosted.org/）
mirror_presets() {
  printf '%s\n' \
    'pypi https://pypi.org/simple https://files.pythonhosted.org/' \
    'tuna https://pypi.tuna.tsinghua.edu.cn/simple https://pypi.tuna.tsinghua.edu.cn/' \
    'ustc https://mirrors.ustc.edu.cn/pypi/simple https://mirrors.ustc.edu.cn/pypi/' \
    'aliyun https://mirrors.aliyun.com/pypi/simple https://mirrors.aliyun.com/pypi/' \
    'tencent https://mirrors.cloud.tencent.com/pypi/simple https://mirrors.cloud.tencent.com/pypi/' \
    'huawei https://repo.huaweicloud.com/repository/pypi/simple https://repo.huaweicloud.com/repository/pypi/'
}

# 來源名稱或 simple 網址 → 「名稱 索引 檔案開頭」一行
mirror_spec() {
  local value="$1" line url
  line="$(mirror_presets | awk -v name="$value" '$1 == name')"
  if [ -n "$line" ]; then printf '%s\n' "$line"; return; fi
  case "$value" in
    http://*|https://*) ;;
    *) die "不認得的套件來源：${value}（可用 auto、pypi、tuna、ustc、aliyun、tencent、huawei 或 simple 網址）" ;;
  esac
  case "$value" in
    *[[:space:]\#\&\|\\]*) die "套件來源網址不能有空白、#、&、| 或 \\：${value}" ;;
  esac
  url="${value%/}"
  # 一般的鏡像（bandersnatch、Nexus、Artifactory）把檔案放在 simple 上一層的 packages/
  if [ "${url%/simple}" != "$url" ]; then
    printf 'custom %s %s/\n' "$url" "${url%/simple}"
  else
    printf 'custom %s %s/\n' "$url" "$url"
  fi
}

# uv.lock 裡用來測速的檔案：一個 500 KB～4 MB 的純 Python wheel →「網址 sha256」
probe_file() {
  [ -f uv.lock ] || return 0
  awk -F'"' '/url = "https:\/\/files\.pythonhosted\.org\/.*-py3-none-any\.whl", hash = "sha256:/ {
    url = $2; hash = $4; sub(/^sha256:/, "", hash)
    size = $5; sub(/.*size = /, "", size); sub(/[^0-9].*/, "", size)
    if (size + 0 >= 500000 && size + 0 <= 4000000) { print url, hash; exit }
  }' uv.lock
}

# 從一個來源下載測速檔，雜湊相符才寫下「速度（位元組／秒） 名稱」；失敗不寫，結果一律成功
probe_mirror() {
  local name="$1" files="$2" url="$3" hash="$4" out="$5" speed got
  speed="$(curl -fsSL --connect-timeout 5 --max-time 20 -o "$out/$name.whl" -w '%{speed_download}' \
    "${files}${url#"$PYPI_FILES"}" 2>/dev/null)" || return 0
  speed="${speed%%.*}"
  case "$speed" in ''|*[!0-9]*) return 0 ;; esac
  got="$(sha256sum "$out/$name.whl" 2>/dev/null | awk '{print $1}')"
  [ "$got" = "$hash" ] || return 0
  printf '%s %s\n' "$speed" "$name" > "$out/$name.ok"
}

# 每個內建來源同時下載同一個檔案，選雜湊相符而且最快的；都不行時用 PyPI
auto_mirror() {
  local probe url hash out name simple files speed best=""
  probe="$(probe_file)"
  if [ -z "$probe" ] || ! command -v curl >/dev/null 2>&1 || ! command -v sha256sum >/dev/null 2>&1; then
    info '無法測速（找不到測速檔、curl 或 sha256sum），使用 PyPI。' >&2
    mirror_presets | awk '$1 == "pypi"'
    return
  fi
  url="${probe%% *}"
  hash="${probe##* }"
  out="$(mktemp -d)"
  info "測試套件來源的速度（同時下載 ${url##*/} 並核對 sha256，最多約 20 秒）：" >&2
  while read -r name simple files; do
    probe_mirror "$name" "$files" "$url" "$hash" "$out" &
  done < <(mirror_presets)
  wait
  while read -r name simple files; do
    if [ -f "$out/$name.ok" ]; then
      read -r speed _ < "$out/$name.ok"
      printf '  %-8s %8s KB/s\n' "$name" "$(( speed / 1024 ))" >&2
      if [ -z "$best" ] || [ "$speed" -gt "${best%% *}" ]; then best="$speed $name"; fi
    else
      printf '  %-8s 無法使用（連不上、逾時或內容不符）\n' "$name" >&2
    fi
  done < <(mirror_presets)
  rm -rf "$out"
  if [ -z "$best" ]; then
    info '沒有測速成功的來源，照舊使用 PyPI（公司網路可用 --mirror 指定核准的鏡像）。' >&2
    best="0 pypi"
  fi
  mirror_presets | awk -v name="${best#* }" '$1 == name'
}

# 決定套件來源：--mirror 或 RPA_PYPI_MIRROR；沒有時看 UV_DEFAULT_INDEX、UV_INDEX_URL；都沒有就 auto
choose_mirror() {
  local value="${MIRROR:-${UV_DEFAULT_INDEX:-${UV_INDEX_URL:-auto}}}" line
  if [ "$value" = auto ]; then line="$(auto_mirror)"; else line="$(mirror_spec "$value")"; fi
  read -r MIRROR_NAME MIRROR_SIMPLE MIRROR_FILES <<< "$line"
  info "套件來源：${MIRROR_NAME}（${MIRROR_SIMPLE}）。之後可用 --mirror ${MIRROR_NAME} 略過測速。"
}

sed_escape() { printf '%s' "$1" | sed -e 's/[\\&#]/\\&/g'; }

# 這次安裝用的 uv.lock 換成鏡像的網址；原檔先備份，結束時（含失敗、中斷）還原
use_mirror_lock() {
  LOCK_BACKUP="$(mktemp)"
  cp uv.lock "$LOCK_BACKUP"
  trap restore_lock EXIT
  sed -e "s#https://pypi\.org/simple#$(sed_escape "$MIRROR_SIMPLE")#g" \
    -e "s#https://files\.pythonhosted\.org/#$(sed_escape "$MIRROR_FILES")#g" "$LOCK_BACKUP" > uv.lock
}

restore_lock() {
  if [ -n "$LOCK_BACKUP" ] && [ -f "$LOCK_BACKUP" ]; then
    cat "$LOCK_BACKUP" > uv.lock
    rm -f "$LOCK_BACKUP"
  fi
  LOCK_BACKUP=""
}

# 照 uv.lock 安裝 .venv-server；用鏡像失敗時還原鎖檔、改用 PyPI 再試一次
sync_runtime() {
  local options=(--package rpa-cli --no-default-groups --managed-python)
  choose_mirror
  if [ "$MIRROR_NAME" != pypi ]; then
    use_mirror_lock
    if (
      unset UV_INDEX_URL UV_DEFAULT_INDEX UV_INDEX UV_EXTRA_INDEX_URL
      UV_PROJECT_ENVIRONMENT="$REPO_DIR/.venv-server" "$UV" sync --locked \
        --default-index "$MIRROR_SIMPLE" "${options[@]}"
    ); then
      restore_lock
      return 0
    fi
    restore_lock
    info "從 ${MIRROR_NAME} 安裝失敗，改用 PyPI 再試一次。"
  fi
  (
    unset UV_INDEX_URL UV_DEFAULT_INDEX UV_INDEX UV_EXTRA_INDEX_URL
    UV_PROJECT_ENVIRONMENT="$REPO_DIR/.venv-server" "$UV" sync --locked "${options[@]}"
  )
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
  sync_runtime
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
      printf '# 測試網站（8765）：空白＝不啟動；0.0.0.0＝錄製端、Worker 也連得到（沒有保護，防火牆只開給它們）。\n'
      printf 'export RPA_TESTSITE_HOST=%q\n' "${RPA_TESTSITE_HOST:-}"
      } > .rpa-server.env
    )
  fi
  {
    printf '#!/usr/bin/env bash\nset -Eeuo pipefail\numask 077\n'
    printf 'cd %q\nsource %q\n' "$REPO_DIR" "$REPO_DIR/.rpa-server.env"
    printf 'mkdir -p "$RPA_DATA_DIR"\n'
    # 較早建立的 .rpa-server.env 沒有 RPA_TESTSITE_HOST：當成空白，照舊不啟動測試網站。
    printf 'testsite=(--no-testsite)\n'
    printf 'if [ -n "${RPA_TESTSITE_HOST:-}" ]; then testsite=(--testsite-host "$RPA_TESTSITE_HOST"); fi\n'
    printf 'exec %q serve --host 127.0.0.1 --port "$RPA_PORT" --data "$RPA_DATA_DIR" --worker-host "$RPA_WORKER_HOST" --worker-port "$RPA_WORKER_PORT" --no-local-worker "${testsite[@]}"\n' "$REPO_DIR/.venv-server/bin/rpa"
  } > "$launcher"
  chmod 755 "$launcher"
  {
    printf '[Unit]\nDescription=RPA Server\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=simple\n'
    printf 'User=%s\n' "$(id -un)"
    # 舊版 systemd 不接受 WorkingDirectory 的外層引號；由啟動器的 cd 處理工作目錄。
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
