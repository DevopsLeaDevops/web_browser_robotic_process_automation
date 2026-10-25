#!/usr/bin/env bash
# RPA 伺服器分發包的安裝與升級（RHEL／CentOS 衍生版、無桌面）。
#
# 在解壓後的資料夾裡執行：bash install.sh [選項]。分發包已經帶著 Python 與照 uv.lock 裝好的套件，
# 伺服器不需要 git clone、uv，也不必連到 PyPI。由 tools/build_server.py 放進分發包；
# 系統辨識與 systemd 的寫法和 scripts/setup-linux.sh 相同（分發包必須能獨立執行，所以各寫一份）。
#
# 安裝後的資料夾（預設 ~/rpa-server，--prefix 可改）：
#   releases/<版本>-<提交>/   每個版本一個資料夾，並排存放
#   current                   指向使用中的版本（升級時一次換過去）
#   bin/rpa-server            啟動器：讀設定檔，以 current 的版本執行 rpa serve（systemd 也用它）
#   bin/rpa                   current 版本的 rpa 命令
#   rpa-server.env            設定（資料位置、埠號；升級保留）
#   rpa-server.service        systemd unit（--install-service 時安裝）
# 資料目錄由設定檔的 RPA_DATA_DIR 決定（預設 ~/.local/share/rpa-server，和 setup-linux.sh 相同），
# 安裝、升級都不會清除。
set -Eeuo pipefail

PREFIX="${RPA_SERVER_HOME:-$HOME/rpa-server}"
INSTALL_SERVICE=0
SKIP_SYSTEM_PACKAGES=0
IMPORT_ENV=""
KEEP=3
OS_RELEASE=/etc/os-release
UNIT_PATH=/etc/systemd/system/rpa-server.service
LEGACY_DIR="${RPA_DIR:-$HOME/code/web_browser_robotic_process_automation}"
BUNDLE=""
VERSION=""
COMMIT=""
ARCH=""
RELEASE=""
PACKAGE_MANAGER=""
PREVIOUS=""
IMPORTED=""
MISSING=()

die() { printf '\n錯誤：%s\n' "$*" >&2; exit 1; }
info() { printf '\n%s\n' "$*"; }
trap 'printf "\n安裝失敗（第 %s 行）；修正上述錯誤後可重新執行，已安裝的版本與資料不受影響。\n" "$LINENO" >&2' ERR

usage() {
  cat <<'EOF'
用法：bash install.sh [選項]

安裝或升級 RPA 伺服器（RHEL／CentOS／Fedora 及 ID_LIKE 包含這些名稱的公司 Linux）。
需要和分發包相同的架構（x86_64／aarch64）、glibc 2.28 以上；不需要 git clone、uv 或 PyPI。

  --prefix <路徑>           安裝位置（預設 ~/rpa-server，也可設定 RPA_SERVER_HOME）
  --install-service         安裝（或改用這一份）並啟動 systemd 的 rpa-server.service
  --skip-system-packages    系統套件已由管理員安裝，不呼叫 yum／dnf
  --import-env <檔案>       首次安裝時沿用這份設定（例如舊的 .rpa-server.env）
  --keep <數量>             保留最近幾個版本（預設 3，至少 2）
  -h, --help                顯示說明

一般帳號執行即可；安裝缺少的系統套件與 systemd 服務時會呼叫 sudo。
升級：解壓新版的分發包，再執行其中的 install.sh。設定、資料與服務沿用；服務正在執行時自動重新啟動。
首次安裝可設定 RPA_DATA_DIR（預設 ~/.local/share/rpa-server）、RPA_PORT（8080）、
RPA_WORKER_PORT（8081）、RPA_WORKER_HOST（0.0.0.0）、RPA_TESTSITE_HOST（空白＝不啟動測試網站）；
之後修改安裝位置的 rpa-server.env。之前用 scripts/setup-linux.sh 安裝過時，自動沿用那份設定與資料。
EOF
}

parse_args() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --prefix)
        [ $# -ge 2 ] && [ -n "$2" ] && [[ "$2" != --* ]] || die '--prefix 後面需要路徑。'
        PREFIX="$2"; shift 2 ;;
      --prefix=*) PREFIX="${1#--prefix=}"; [ -n "$PREFIX" ] || die '--prefix 不能為空。'; shift ;;
      --install-service) INSTALL_SERVICE=1; shift ;;
      --skip-system-packages) SKIP_SYSTEM_PACKAGES=1; shift ;;
      --import-env)
        [ $# -ge 2 ] && [ -n "$2" ] && [[ "$2" != --* ]] || die '--import-env 後面需要設定檔。'
        IMPORT_ENV="$2"; shift 2 ;;
      --import-env=*) IMPORT_ENV="${1#--import-env=}"; [ -n "$IMPORT_ENV" ] || die '--import-env 不能為空。'; shift ;;
      --keep)
        [ $# -ge 2 ] && [[ "$2" =~ ^[0-9]+$ ]] || die '--keep 後面需要數字。'
        KEEP="$2"; shift 2 ;;
      --keep=*) KEEP="${1#--keep=}"; [[ "$KEEP" =~ ^[0-9]+$ ]] || die '--keep 後面需要數字。'; shift ;;
      -h|--help) usage; exit 0 ;;
      *) die "不認得的選項：$1（見 --help）" ;;
    esac
  done
  [ "$KEEP" -ge 2 ] || die '--keep 至少是 2（使用中的版本與上一個版本）。'
  case "$PREFIX" in
    *$'\n'*|*$'\r'*) die '安裝位置不能包含換行字元。' ;;
    /*) ;;
    *) PREFIX="$PWD/$PREFIX" ;;
  esac
  PREFIX="${PREFIX%/}"
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

# 分發包的建置資訊（KEY=值，一行一項）；只逐行讀取，不當成腳本執行
read_bundle() {
  local here="${1:-}" key value
  if [ -z "$here" ]; then here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; fi
  [ -f "$here/BUILD_INFO" ] && [ -x "$here/bin/rpa" ] && [ -e "$here/python/bin/python3" ] ||
    die "${here} 不是完整的 RPA 伺服器分發包（缺 BUILD_INFO、bin/rpa 或 python/）。請重新下載並完整解壓。"
  BUNDLE="$here"
  while IFS='=' read -r key value; do
    case "$key" in
      version) VERSION="$value" ;;
      commit) COMMIT="$value" ;;
      arch) ARCH="$value" ;;
    esac
  done < "$BUNDLE/BUILD_INFO"
  [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "BUILD_INFO 的版本不對：${VERSION:-空白}"
  [[ "$COMMIT" =~ ^[0-9a-f]*$ ]] || die "BUILD_INFO 的提交不對：${COMMIT}"
  case "$ARCH" in x86_64|aarch64) ;; *) die "BUILD_INFO 的架構不對：${ARCH:-空白}" ;; esac
  RELEASE="$VERSION${COMMIT:+-$COMMIT}"
}

check_system() {
  [ "$(uname -s)" = Linux ] || die '這個分發包只適用於 Linux 伺服器。'
  local machine id="" id_like="" pretty="" glibc family
  machine="$(uname -m)"
  [ "$machine" = "$ARCH" ] ||
    die "這個分發包是 ${ARCH} 版，這台是 ${machine}。請下載 ${machine} 版的分發包。"
  [ -r "$OS_RELEASE" ] || die '找不到 /etc/os-release，無法辨識系統。'
  # 在子 Shell 讀：os-release 也有 VERSION 之類的變數，不能蓋掉分發包的版本。
  # 公司版本可能有自己的 ID，不能只比對 ID=centos 或 VERSION_ID。
  # shellcheck disable=SC1090
  # read 保留空欄位，並相容 macOS 測試環境的 Bash 3.2（沒有 mapfile）。
  {
    IFS= read -r id
    IFS= read -r id_like
    IFS= read -r pretty
  } < <(. "$OS_RELEASE" >/dev/null 2>&1; printf '%s\n%s\n%s\n' "${ID:-}" "${ID_LIKE:-}" "${PRETTY_NAME:-}")
  case " $id $id_like " in
    *' rhel '*|*' centos '*|*' fedora '*) ;;
    *) die "這個分發包適用於 RHEL／CentOS 系（目前：${pretty:-$id}）。" ;;
  esac
  glibc="$(getconf GNU_LIBC_VERSION 2>/dev/null || true)"
  family="${glibc%% *}"
  [ "$family" = glibc ] && version_ge "${glibc#* }" 2.28 ||
    die "需要 glibc 2.28 以上，目前為 ${glibc:-未知}。請使用較新的公司 Linux 映像；不要替換系統 glibc。"
  if command -v yum >/dev/null 2>&1; then PACKAGE_MANAGER=yum
  elif command -v dnf >/dev/null 2>&1; then PACKAGE_MANAGER=dnf
  fi
  info "系統：${pretty:-${id:-$id_like}}，${machine}，${glibc}；分發包：RPA 伺服器 ${VERSION}（${COMMIT:-未知提交}）"
}

as_root() {
  if [ "$(id -u)" = 0 ]; then "$@"
  elif command -v sudo >/dev/null 2>&1; then sudo "$@"
  else die '這一步需要管理員權限。請由管理員執行，或安裝系統套件後使用 --skip-system-packages。'
  fi
}

has_systemd() {
  command -v systemctl >/dev/null 2>&1 && systemctl show-environment >/dev/null 2>&1
}

check_service() {
  if [ "$INSTALL_SERVICE" = 1 ] && ! has_systemd; then
    die '目前沒有可用的 systemd（例如容器）。請省略 --install-service，使用前景啟動命令。'
  fi
}

has_libstdcxx() {
  local dir
  if command -v ldconfig >/dev/null 2>&1 && ldconfig -p 2>/dev/null | grep -q 'libstdc++\.so\.6 '; then
    return 0
  fi
  for dir in /usr/lib64 /lib64 /usr/lib /lib /usr/lib/x86_64-linux-gnu /usr/lib/aarch64-linux-gnu; do
    [ -e "$dir/libstdc++.so.6" ] && return 0
  done
  return 1
}

# 只裝缺少的：升級時通常什麼都不缺，不必 sudo
install_system_packages() {
  MISSING=()
  has_libstdcxx || MISSING+=(libstdc++)
  command -v git >/dev/null 2>&1 || MISSING+=(git)
  [ "${#MISSING[@]}" -gt 0 ] || return 0
  if [ "$SKIP_SYSTEM_PACKAGES" = 1 ]; then
    case " ${MISSING[*]} " in
      *' libstdc++ '*) die '缺少 libstdc++（部分套件需要）。請管理員 yum install libstdc++ 後再執行。' ;;
    esac
    info '找不到 git：其他功能照常，只有「領域資料夾的 git 同步」不能用；需要時請管理員 yum install git。'
    return 0
  fi
  [ -n "$PACKAGE_MANAGER" ] ||
    die "缺少 ${MISSING[*]}，而且找不到 yum 或 dnf。請管理員安裝後使用 --skip-system-packages。"
  info "使用 ${PACKAGE_MANAGER} 安裝缺少的系統套件：${MISSING[*]}"
  as_root "$PACKAGE_MANAGER" install -y "${MISSING[@]}"
}

# 版本資料夾能不能用：rpa 命令與伺服器的程式載入得了（也確認 Python 在這台系統上能執行）
verify_release() {
  local dir="$1"
  env -u PYTHONHOME -u PYTHONPATH "$dir/bin/rpa" --version >/dev/null 2>&1 &&
    env -u PYTHONHOME -u PYTHONPATH PYTHONNOUSERSITE=1 "$dir/python/bin/python3" -c \
      'import sqlite3, ssl; from rpa_server.app import create_app; from rpa_server.config import Settings' \
      >/dev/null 2>&1
}

same_dir() {
  [ -d "$1" ] && [ -d "$2" ] && [ "$(cd "$1" && pwd -P)" = "$(cd "$2" && pwd -P)" ]
}

install_release() {
  local target="$PREFIX/releases/$RELEASE" staging
  mkdir -p "$PREFIX/releases"
  if same_dir "$BUNDLE" "$target"; then
    verify_release "$target" || die "${target} 無法執行（Python 或套件載入失敗）。"
    return 0
  fi
  if [ -d "$target" ] && verify_release "$target"; then
    info "已經裝過 ${RELEASE}，沿用（設定與服務照樣更新）。"
    return 0
  fi
  info "安裝 ${RELEASE} 到 ${target}"
  staging="$PREFIX/releases/.${RELEASE}.tmp.$$"
  rm -rf "$staging"
  cp -a "$BUNDLE" "$staging"
  if ! verify_release "$staging"; then
    rm -rf "$staging"
    die "分發包裡的 Python 在這台系統上無法執行（架構、glibc 或檔案不完整）。執行 ${BUNDLE}/bin/rpa --version 查看原因。"
  fi
  # 之前沒裝完（例如中斷）留下的同名資料夾：不是使用中的版本才換掉
  if [ -e "$target" ]; then
    if same_dir "$target" "$PREFIX/current"; then
      rm -rf "$staging"
      die "使用中的 ${target} 無法執行，但它正被 current 使用。請先停止服務，刪除這個資料夾後再執行。"
    fi
    rm -rf "$target"
  fi
  mv "$staging" "$target"
}

# 第一次安裝時找之前用 setup-linux.sh（clone）安裝的設定：先看 systemd 服務啟動的是哪一份，
# 再看預設的 clone 位置。setup-linux.sh 的設定檔與這裡用同一組變數，可以直接沿用。
legacy_env() {
  local exec_line launcher repo candidate
  if [ -r "$UNIT_PATH" ]; then
    exec_line="$(sed -n 's/^ExecStart=\/bin\/bash "\(.*\)"$/\1/p' "$UNIT_PATH" | head -n 1)"
    if [ -n "$exec_line" ]; then
      launcher="${exec_line//\$\$/\$}"; launcher="${launcher//%%/%}"
      launcher="${launcher//\\\"/\"}"; launcher="${launcher//\\\\/\\}"
      case "$launcher" in
        */.venv-server/bin/rpa-server)
          repo="${launcher%/.venv-server/bin/rpa-server}"
          if [ -f "$repo/.rpa-server.env" ]; then printf '%s\n' "$repo/.rpa-server.env"; return 0; fi
          ;;
      esac
    fi
  fi
  candidate="$LEGACY_DIR/.rpa-server.env"
  if [ -f "$candidate" ]; then printf '%s\n' "$candidate"; return 0; fi
  return 1
}

write_config() {
  local env_file="$PREFIX/rpa-server.env" source_file=""
  if [ -e "$env_file" ]; then
    [ -z "$IMPORT_ENV" ] || info "已經有 ${env_file}，保留它；不匯入 ${IMPORT_ENV}。"
    return 0
  fi
  if [ -n "$IMPORT_ENV" ]; then
    [ -f "$IMPORT_ENV" ] && [ -r "$IMPORT_ENV" ] || die "讀不到要匯入的設定檔：${IMPORT_ENV}"
    source_file="$IMPORT_ENV"
  else
    source_file="$(legacy_env || true)"
  fi
  (
    umask 077
    if [ -n "$source_file" ]; then
      cat "$source_file" > "$env_file"
    else
      {
      printf '# RPA 伺服器設定（Bash 語法）；修改後重新啟動服務。\n'
      printf 'export RPA_DATA_DIR=%q\n' "${RPA_DATA_DIR:-$HOME/.local/share/rpa-server}"
      printf 'export RPA_PORT=%q\n' "${RPA_PORT:-8080}"
      printf 'export RPA_WORKER_PORT=%q\n' "${RPA_WORKER_PORT:-8081}"
      printf 'export RPA_WORKER_HOST=%q\n' "${RPA_WORKER_HOST:-0.0.0.0}"
      printf '# 測試網站（8765）：空白＝不啟動；0.0.0.0＝錄製端、Worker 也連得到（沒有保護，防火牆只開給它們）。\n'
      printf 'export RPA_TESTSITE_HOST=%q\n' "${RPA_TESTSITE_HOST:-}"
      } > "$env_file"
    fi
  )
  if [ -n "$source_file" ]; then
    IMPORTED="$source_file"
    info "沿用之前的設定：${source_file} → ${env_file}（資料目錄照舊，不搬動資料）。"
  fi
}

# systemd 字串與 Shell 的跳脫規則不同；ExecStart 的 $、所有欄位的 % 都要單獨處理。
systemd_quote() {
  local value="$1"
  value="${value//\\/\\\\}"; value="${value//\"/\\\"}"; value="${value//%/%%}"
  printf '"%s"' "$value"
}

unit_text() {
  local launcher="$PREFIX/bin/rpa-server"
  printf '[Unit]\nDescription=RPA Server\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=simple\n'
  printf 'User=%s\n' "$(id -un)"
  printf 'Environment=%s\n' "$(systemd_quote "HOME=$HOME")"
  printf 'Environment=PYTHONUTF8=1\nUMask=0077\n'
  printf 'ExecStart=/bin/bash %s\n' "$(systemd_quote "${launcher//\$/\$\$}")"
  printf 'Restart=on-failure\nRestartSec=5\nTimeoutStopSec=30\n\n[Install]\nWantedBy=multi-user.target\n'
}

write_launchers() {
  local launcher="$PREFIX/bin/rpa-server"
  case "$HOME" in *$'\n'*|*$'\r'*) die '家目錄路徑不能包含換行字元。' ;; esac
  mkdir -p "$PREFIX/bin"
  {
    printf '#!/usr/bin/env bash\n# 由 install.sh 產生：以 current 指向的版本啟動 RPA 伺服器；設定在 rpa-server.env。\n'
    printf 'set -Eeuo pipefail\numask 077\n'
    printf 'source %q\n' "$PREFIX/rpa-server.env"
    printf 'mkdir -p "$RPA_DATA_DIR"\n'
    # 較早建立的設定沒有 RPA_TESTSITE_HOST：當成空白，照舊不啟動測試網站。
    printf 'testsite=(--no-testsite)\n'
    printf 'if [ -n "${RPA_TESTSITE_HOST:-}" ]; then testsite=(--testsite-host "$RPA_TESTSITE_HOST"); fi\n'
    # 在版本資料夾裡啟動：第一次啟動時從 scenarios/demo 匯入範例場景
    printf 'cd %q\n' "$PREFIX/current"
    printf 'exec %q serve --host 127.0.0.1 --port "$RPA_PORT" --data "$RPA_DATA_DIR" --worker-host "$RPA_WORKER_HOST" --worker-port "$RPA_WORKER_PORT" --no-local-worker "${testsite[@]}"\n' "$PREFIX/current/bin/rpa"
  } > "$launcher.tmp"
  chmod 755 "$launcher.tmp"
  mv -f "$launcher.tmp" "$launcher"
  {
    printf '#!/usr/bin/env bash\n# 由 install.sh 產生：current 版本的 rpa 命令。\n'
    printf 'exec %q "$@"\n' "$PREFIX/current/bin/rpa"
  } > "$PREFIX/bin/rpa.tmp"
  chmod 755 "$PREFIX/bin/rpa.tmp"
  mv -f "$PREFIX/bin/rpa.tmp" "$PREFIX/bin/rpa"
  unit_text > "$PREFIX/rpa-server.service"
}

current_release() {
  local link
  link="$(readlink "$PREFIX/current" 2>/dev/null || true)"
  printf '%s\n' "${link#releases/}"
}

# 原子地把 current 換到這個版本（新連結先建好再改名蓋過去）
switch_current() {
  PREVIOUS="$(current_release)"
  [ "$PREVIOUS" != "$RELEASE" ] || PREVIOUS=""
  touch "$PREFIX/releases/$RELEASE"  # 修改時間＝最近一次安裝，舊版本依它刪除
  ln -sfn "releases/$RELEASE" "$PREFIX/.current.new"
  mv -Tf "$PREFIX/.current.new" "$PREFIX/current"
}

unit_is_ours() {
  [ -r "$UNIT_PATH" ] && cmp -s "$UNIT_PATH" "$PREFIX/rpa-server.service"
}

service_active() {
  has_systemd && systemctl is-active --quiet rpa-server.service 2>/dev/null
}

# 新版本啟動後，管理埠接得通才算成功（最多約 60 秒；第一次啟動要建資料庫、匯入範例）
wait_until_serving() {
  local port i
  port="$(bash -c 'source "$1" >/dev/null 2>&1; printf %s "${RPA_PORT:-8080}"' _ "$PREFIX/rpa-server.env")"
  for i in $(seq 1 60); do
    if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then return 0; fi
    service_active || [ "$i" -lt 5 ] || return 1
    sleep 1
  done
  return 1
}

restart_failed() {
  local back=""
  [ -z "$PREVIOUS" ] || back="；要退回上一版：ln -sfn releases/${PREVIOUS} ${PREFIX}/current 後 sudo systemctl restart rpa-server"
  die "rpa-server 重新啟動後沒有回應。查看 sudo journalctl -u rpa-server -n 100${back}"
}

handle_service() {
  if [ "$INSTALL_SERVICE" = 1 ]; then
    as_root install -m 644 "$PREFIX/rpa-server.service" "$UNIT_PATH"
    as_root systemctl daemon-reload
    as_root systemctl enable rpa-server.service
    as_root systemctl restart rpa-server.service
    wait_until_serving || restart_failed
    SERVICE_STATE="已啟動（開機自動啟動）"
    return 0
  fi
  if [ ! -e "$UNIT_PATH" ]; then
    SERVICE_STATE="未安裝"
    return 0
  fi
  if ! unit_is_ours; then
    SERVICE_STATE="仍是另一份安裝（例如 setup-linux.sh 的 clone）"
    info "現有的 rpa-server 服務啟動的不是這一份。要改用分發包：bash ${BUNDLE}/install.sh --install-service（設定與資料已沿用）。"
    return 0
  fi
  if service_active; then
    info '重新啟動 rpa-server，改用新的版本。'
    as_root systemctl restart rpa-server.service
    wait_until_serving || restart_failed
    SERVICE_STATE="已重新啟動"
  else
    SERVICE_STATE="已安裝，目前停止（sudo systemctl start rpa-server）"
  fi
}

# 保留最近的幾個版本；使用中與上一個版本一定保留
prune_releases() {
  local dir name kept=1
  if [ -n "$PREVIOUS" ] && [ -d "$PREFIX/releases/$PREVIOUS" ]; then kept=2; fi
  while IFS= read -r dir; do
    name="${dir##*/}"
    if [ "$name" = "$RELEASE" ] || [ "$name" = "$PREVIOUS" ]; then continue; fi
    if [ "$kept" -lt "$KEEP" ]; then kept=$((kept + 1)); continue; fi
    info "刪除舊版本：${name}"
    rm -rf "$dir"
  done < <(ls -1dt "$PREFIX/releases"/*/ 2>/dev/null | sed 's#/$##')
}

summary() {
  local data
  data="$(bash -c 'source "$1" >/dev/null 2>&1; printf %s "${RPA_DATA_DIR:-}"' _ "$PREFIX/rpa-server.env")"
  info "安裝完成：RPA 伺服器 ${VERSION}（${COMMIT:-未知提交}），位置 ${PREFIX}（current → releases/${RELEASE}）"
  printf '設定檔：%s；資料目錄：%s（安裝、升級都不會清除）\n' "$PREFIX/rpa-server.env" "${data:-未知}"
  printf '前景啟動：%q\n' "$PREFIX/bin/rpa-server"
  printf '背景服務：%s\n' "$SERVICE_STATE"
  if [ "$SERVICE_STATE" = 未安裝 ]; then
    printf '需要背景服務時：bash %q --install-service\n' "$BUNDLE/install.sh"
  else
    printf '服務狀態：sudo systemctl status rpa-server；日誌：sudo journalctl -u rpa-server -f\n'
  fi
  printf '升級：解壓新版的分發包，執行其中的 install.sh（--prefix 相同時設定、資料與服務沿用）。\n'
  printf '首次配對：用 SSH 轉發管理埠，在「裝置」頁建立邀請；錄製端／Worker 連線到伺服器的裝置埠。\n'
}

SERVICE_STATE=""

main() {
  parse_args "$@"
  read_bundle
  check_system
  check_service
  install_system_packages
  install_release
  write_config
  write_launchers
  switch_current
  handle_service
  prune_releases
  summary
}

# 可由測試載入函式；直接執行時進入主流程。
if [ "${BASH_SOURCE[0]}" = "$0" ]; then main "$@"; fi
