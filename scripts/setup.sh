#!/usr/bin/env bash
# 一鍵安裝本機開發環境，並確認專案能運行（macOS、Linux）。Windows 請用 scripts/setup.ps1。
#
# 已經有程式碼：在專案資料夾裡執行
#   ./scripts/setup.sh
#
# 從零開始（還沒下載程式碼，預設下載到 ~/code/web_browser_robotic_process_automation）：
#   curl -LsSf https://raw.githubusercontent.com/DevopsLeaDevops/web_browser_robotic_process_automation/main/scripts/setup.sh | bash
#
# 重複執行是安全的，已經完成的步驟很快就會跳過。選項見 --help。
# 說明文件：docs/develop/quickstart.html
#
# 注意：macOS 內建的是 bash 3.2，這個腳本不能用 bash 4 以後的語法
# （關聯陣列、${var,,}、mapfile 等）；set -u 下空的 "$@" 要寫成 ${1+"$@"}。
# 變數後面緊接中文時一定要寫成 ${var}：macOS 的 bash 會把中文的位元組當成變數名稱的一部分。

set -Eeuo pipefail

REPO_URL="https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation.git"
REPO_NAME="web_browser_robotic_process_automation"
UV_INSTALLER="https://astral.sh/uv/install.sh"
DOC_PAGE="docs/develop/quickstart.html"
TOTAL_STEPS=7

TARGET_DIR="${RPA_DIR:-$HOME/code/$REPO_NAME}"
DIR_GIVEN=0
SKIP_BROWSER=0
SKIP_TESTS=0
INSTALL_HOOKS=1

OS=""
STEP=0
STEP_NAME="開始"
REPO_DIR=""
START_DIR="$PWD"
UV=""
UV_INSTALLED_NOW=0
WARNINGS=0

# ---------------------------------------------------------------- 輸出

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_BOLD=$'\033[1m' C_DIM=$'\033[2m' C_RED=$'\033[31m' C_GREEN=$'\033[32m'
  C_YELLOW=$'\033[33m' C_BLUE=$'\033[34m' C_RESET=$'\033[0m'
else
  C_BOLD="" C_DIM="" C_RED="" C_GREEN="" C_YELLOW="" C_BLUE="" C_RESET=""
fi

step() {
  STEP=$((STEP + 1))
  STEP_NAME="$1"
  printf '\n%s[%d/%d] %s%s\n' "$C_BOLD$C_BLUE" "$STEP" "$TOTAL_STEPS" "$1" "$C_RESET"
}
ok() { printf '  %s✓%s %s\n' "$C_GREEN" "$C_RESET" "$*"; }
info() { printf '  %s·%s %s\n' "$C_DIM" "$C_RESET" "$*"; }
warn() {
  WARNINGS=$((WARNINGS + 1))
  printf '  %s! %s%s\n' "$C_YELLOW" "$*" "$C_RESET" >&2
}
run() {
  printf '  %s$ %s%s\n' "$C_DIM" "$*" "$C_RESET"
  "$@"
}

# 已知原因的失敗：說明怎麼處理，然後結束。
die() {
  trap - ERR
  printf '\n%s✗ %s%s\n' "$C_RED$C_BOLD" "$1" "$C_RESET" >&2
  shift
  local line
  for line in ${1+"$@"}; do printf '  %s\n' "$line" >&2; done
  printf '  修正後重新執行同一個命令即可，已完成的步驟會跳過。說明見 %s\n' "$DOC_PAGE" >&2
  exit 1
}

# 沒預料到的失敗：至少說清楚停在哪一步。
on_error() {
  local code=$?
  trap - ERR
  printf '\n%s✗ 第 %d 步「%s」失敗（結束碼 %d）。%s\n' \
    "$C_RED$C_BOLD" "$STEP" "$STEP_NAME" "$code" "$C_RESET" >&2
  printf '  往上看最後幾行的錯誤訊息；修正後重新執行同一個命令即可。說明見 %s\n' "$DOC_PAGE" >&2
  exit "$code"
}
trap on_error ERR

usage() {
  cat <<EOF
用法：scripts/setup.sh [選項]

一鍵安裝本機開發環境（uv、Python、依賴、Chromium、提交前檢查），
並執行 rpa --version 與全部測試，確認專案能運行。

選項：
  --dir <路徑>      還沒有程式碼時，下載到哪裡（預設 ~/code/${REPO_NAME}，
                    也可以用環境變數 RPA_DIR）。在專案資料夾裡執行時不需要。
  --skip-browser    不下載 Chromium；需要瀏覽器的測試會略過。
  --skip-tests      只安裝，不跑測試。
  --no-hooks        不安裝 Git 提交前檢查（pre-commit）。
  -h, --help        顯示這段說明。

透過 curl 執行時，選項放在 bash -s -- 後面：
  curl -LsSf <腳本網址> | bash -s -- --skip-browser

公司網路：設定 UV_INDEX_URL（套件鏡像）與 PLAYWRIGHT_DOWNLOAD_HOST（瀏覽器鏡像）後再執行。
EOF
}

parse_args() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --dir)
        [ $# -ge 2 ] || die "--dir 後面需要一個路徑。"
        TARGET_DIR="$2"
        DIR_GIVEN=1
        shift 2
        ;;
      --dir=*)
        TARGET_DIR="${1#--dir=}"
        DIR_GIVEN=1
        shift
        ;;
      --skip-browser) SKIP_BROWSER=1; shift ;;
      --skip-tests) SKIP_TESTS=1; shift ;;
      --no-hooks) INSTALL_HOOKS=0; shift ;;
      -h | --help) usage; exit 0 ;;
      *) die "不認得的選項：$1" "用 --help 看可以用哪些選項。" ;;
    esac
  done
  case "$TARGET_DIR" in
    /*) ;;
    *) TARGET_DIR="$PWD/$TARGET_DIR" ;;
  esac
}

# ---------------------------------------------------------------- 小工具

# $1 >= $2？只比較前三段數字，例如 0.11.32 >= 0.11。
version_ge() {
  local have="$1." need="$2." h n _
  for _ in 1 2 3; do
    h="${have%%.*}" n="${need%%.*}"
    have="${have#*.}" need="${need#*.}"
    h="${h%%[!0-9]*}" n="${n%%[!0-9]*}"
    if [ "${h:-0}" -gt "${n:-0}" ]; then return 0; fi
    if [ "${h:-0}" -lt "${n:-0}" ]; then return 1; fi
  done
  return 0
}

is_repo_root() {
  [ -f "$1/pyproject.toml" ] && [ -f "$1/apps/cli/pyproject.toml" ] \
    && grep -q '^name = "rpa-cli"' "$1/apps/cli/pyproject.toml"
}

# 腳本本身在專案的 scripts/ 裡時，印出專案根目錄；透過 curl 執行時什麼都不印。
script_repo_root() {
  local src="${BASH_SOURCE[0]:-}" root
  case "$src" in
    "" | bash | -bash | /dev/stdin | /dev/fd/* | /proc/self/fd/*) return 0 ;;
  esac
  if [ -f "$src" ]; then
    root="$(cd "$(dirname "$src")/.." && pwd)"
    if is_repo_root "$root"; then printf '%s' "$root"; fi
  fi
}

# macOS 沒裝命令列開發者工具時，/usr/bin/git 只是個會跳出安裝視窗的空殼。
have_git() {
  if [ "$OS" = Darwin ] && [ "$(command -v git || true)" = /usr/bin/git ] \
    && ! xcode-select -p >/dev/null 2>&1; then
    return 1
  fi
  git --version >/dev/null 2>&1
}

linux_install_hint() {
  if command -v apt-get >/dev/null 2>&1; then printf 'sudo apt-get install -y %s' "$1"
  elif command -v dnf >/dev/null 2>&1; then printf 'sudo dnf install -y %s' "$1"
  elif command -v yum >/dev/null 2>&1; then printf 'sudo yum install -y %s' "$1"
  elif command -v pacman >/dev/null 2>&1; then printf 'sudo pacman -S --needed %s' "$1"
  elif command -v zypper >/dev/null 2>&1; then printf 'sudo zypper install -y %s' "$1"
  elif command -v apk >/dev/null 2>&1; then printf 'sudo apk add %s' "$1"
  else printf '用系統的套件管理員安裝 %s' "$1"
  fi
}

ensure_git() {
  if have_git; then return 0; fi
  if [ "$OS" = Darwin ]; then
    info "需要 Apple 的命令列開發者工具（含 Git），即將跳出安裝視窗。"
    xcode-select --install >/dev/null 2>&1 || true
    die "請在跳出的視窗按「安裝」，完成後重新執行同一個命令。" \
      "不需要安裝完整的 Xcode。沒有看到視窗的話，手動執行：xcode-select --install"
  fi
  die "找不到 Git。" "先安裝：$(linux_install_hint git)，再重新執行。"
}

find_uv() {
  UV=""
  if command -v uv >/dev/null 2>&1; then
    UV="$(command -v uv)"
    return 0
  fi
  # 剛裝好、但這個終端機的 PATH 還沒更新
  local d
  for d in "${XDG_BIN_HOME:-}" "$HOME/.local/bin" "${CARGO_HOME:-$HOME/.cargo}/bin"; do
    if [ -n "$d" ] && [ -x "$d/uv" ]; then
      PATH="$d:$PATH"
      export PATH
      UV="$d/uv"
      return 0
    fi
  done
}

uv_version() { "$UV" --version | awk '{ print $2 }'; }

fetch_uv_installer() {
  if command -v curl >/dev/null 2>&1; then
    curl -LsSf "$UV_INSTALLER"
  else
    wget -qO- "$UV_INSTALLER"
  fi
}

browser_launches() {
  uv run python -c "from playwright.sync_api import sync_playwright; \
p = sync_playwright().start(); p.chromium.launch().close(); p.stop()" >/dev/null 2>&1
}

# ---------------------------------------------------------------- 步驟

check_system() {
  step "檢查系統"
  OS="$(uname -s)"
  local arch
  arch="$(uname -m)"
  case "$OS" in
    Darwin)
      ok "macOS $(sw_vers -productVersion 2>/dev/null || true)（${arch}）"
      if [ "$arch" = x86_64 ] && [ "$(sysctl -n sysctl.proc_translated 2>/dev/null || true)" = 1 ]; then
        warn "終端機正透過 Rosetta 執行，會裝成 Intel 版的 Python。建議關掉終端機的 Rosetta 設定後重跑（見 docs/develop/macos.html#faq）。"
      fi
      ;;
    Linux)
      local distro=""
      if [ -r /etc/os-release ]; then
        # shellcheck source=/dev/null
        distro="$(. /etc/os-release && printf '%s' "${PRETTY_NAME:-}")"
      fi
      ok "Linux${distro:+ $distro}（${arch}）"
      ;;
    MINGW* | MSYS* | CYGWIN*)
      die "Windows 請改用 PowerShell 執行 scripts/setup.ps1。"
      ;;
    *)
      die "不支援的系統：$OS" "目前支援 macOS、Linux 與 Windows。"
      ;;
  esac
}

prepare_code() {
  step "準備程式碼"
  local here
  here="$(script_repo_root)"
  if [ -n "$here" ]; then
    REPO_DIR="$here"
    ok "使用腳本所在的專案：$REPO_DIR"
  elif is_repo_root "$PWD"; then
    REPO_DIR="$PWD"
    ok "使用目前資料夾的專案：$REPO_DIR"
  elif is_repo_root "$TARGET_DIR"; then
    REPO_DIR="$TARGET_DIR"
    ok "已經下載過：$REPO_DIR"
    info "沒有自動更新程式碼；需要最新版本時在專案資料夾執行 git pull。"
  else
    ensure_git
    if [ -e "$TARGET_DIR" ] && [ -n "$(ls -A "$TARGET_DIR" 2>/dev/null || true)" ]; then
      die "$TARGET_DIR 已經存在，而且不是空資料夾。" "用 --dir 指定別的位置，例如：--dir ~/code/rpa"
    fi
    mkdir -p "$(dirname "$TARGET_DIR")"
    if ! run git clone "$REPO_URL" "$TARGET_DIR"; then
      die "下載程式碼失敗。" "確認連得到 github.com；公司網路可能需要設定代理（HTTPS_PROXY）。"
    fi
    REPO_DIR="$TARGET_DIR"
    ok "已下載到：$REPO_DIR"
  fi
  if [ "$DIR_GIVEN" = 1 ] && [ "$REPO_DIR" != "$TARGET_DIR" ]; then
    info "已經在專案資料夾中，--dir 沒有作用。"
  fi
  cd "$REPO_DIR"

  if [ "$OS" = Darwin ]; then
    case "$REPO_DIR" in
      "$HOME/Desktop"/* | "$HOME/Documents"/* | "$HOME/Library/Mobile Documents"/*)
        warn "專案在可能有 iCloud 同步的資料夾，.venv 的大量小檔案會一直被同步。建議移到 ~/code 之類的位置。"
        ;;
    esac
  fi
}

ensure_uv() {
  step "準備 uv"
  local need ver
  need="$(sed -n 's/^required-version *= *">= *\([0-9][0-9.]*\)".*/\1/p' pyproject.toml | head -n 1)"
  need="${need:-0.11}"

  find_uv
  if [ -z "$UV" ]; then
    info "沒有找到 uv，用官方安裝腳本安裝。Python 由 uv 下載與管理，不會動到系統的 Python。"
    if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then
      die "需要 curl 或 wget 才能安裝 uv。" "先安裝：$(linux_install_hint curl)"
    fi
    printf '  %s$ （下載 %s）| sh%s\n' "$C_DIM" "$UV_INSTALLER" "$C_RESET"
    if ! fetch_uv_installer | sh; then
      die "安裝 uv 失敗。" \
        "連不到 astral.sh 時，可以改用 brew install uv 或 pipx install uv 安裝，再重新執行。"
    fi
    UV_INSTALLED_NOW=1
    find_uv
    if [ -z "$UV" ]; then
      die "uv 裝好了，但這個終端機找不到它。" "開一個新的終端機視窗，再執行一次。"
    fi
  fi

  ver="$(uv_version)"
  if ! version_ge "$ver" "$need"; then
    info "uv $ver 太舊，專案需要 $need 以上，嘗試升級。"
    if command -v brew >/dev/null 2>&1 && brew list --versions uv >/dev/null 2>&1; then
      run brew upgrade uv || true
    else
      run "$UV" self update || true
    fi
    ver="$(uv_version)"
    if ! version_ge "$ver" "$need"; then
      die "uv 仍然是 ${ver}，需要 $need 以上。" \
        "用安裝腳本裝的執行 uv self update，Homebrew 裝的執行 brew upgrade uv，其他方式請依原本的安裝方式升級。"
    fi
  fi
  ok "uv ${ver}（${UV}）"
}

sync_deps() {
  step "安裝 Python 與依賴"
  if [ -n "${UV_INDEX_URL:-}" ]; then info "已設定 UV_INDEX_URL，從套件鏡像下載。"; fi
  if ! run uv sync; then
    die "安裝依賴失敗。" \
      "連不到 PyPI 時，設定 UV_INDEX_URL 指向公司的套件鏡像（見 docs/develop/setup.html#faq）。"
  fi
  ok "$(uv run python --version)，虛擬環境在 $REPO_DIR/.venv"
}

install_browser() {
  step "安裝 Chromium"
  if [ "$SKIP_BROWSER" = 1 ]; then
    info "已用 --skip-browser 略過；需要瀏覽器的測試也會略過。"
    return 0
  fi
  if [ -n "${PLAYWRIGHT_DOWNLOAD_HOST:-}" ]; then
    info "已設定 PLAYWRIGHT_DOWNLOAD_HOST，從瀏覽器鏡像下載。"
  fi
  if ! run uv run playwright install chromium; then
    die "下載 Chromium 失敗。" \
      "公司網路請設定 PLAYWRIGHT_DOWNLOAD_HOST 指向內部鏡像；或先加 --skip-browser 跳過這一步。"
  fi
  if [ "$OS" = Linux ] && ! browser_launches; then
    info "Chromium 缺少系統函式庫，交給 Playwright 安裝（會用 sudo，可能需要輸入密碼）。"
    if ! run uv run playwright install-deps chromium; then
      die "安裝 Chromium 的系統函式庫失敗。" \
        "Playwright 只能在 Debian、Ubuntu 上自動安裝；其他發行版請依上面的錯誤訊息手動安裝缺少的函式庫。"
    fi
  fi
  if ! browser_launches; then
    die "Chromium 已下載，但無法啟動。" \
      "手動執行 uv run pytest -m browser 看完整錯誤；仍無法解決時可先加 --skip-browser。"
  fi
  ok "Chromium 可以啟動"
}

install_hooks() {
  step "安裝提交前檢查"
  if [ "$INSTALL_HOOKS" = 0 ]; then
    info "已用 --no-hooks 略過。"
    return 0
  fi
  if ! have_git || ! git rev-parse --git-dir >/dev/null 2>&1; then
    warn "不是 Git 倉庫（可能是下載 ZIP 解壓縮的），略過。建議改用 git clone 下載。"
    return 0
  fi
  if run uv run pre-commit install; then
    ok "git commit 前會自動執行 ruff、pyright 與文檔檢查"
  else
    warn "安裝提交前檢查失敗（例如 Git 設定了 core.hooksPath）。不影響運行，之後可手動執行 uv run pre-commit install。"
  fi
}

verify() {
  step "確認能運行"
  local version
  version="$(uv run rpa --version)"
  ok "$version"
  if [ "$SKIP_TESTS" = 1 ]; then
    info "已用 --skip-tests 略過測試。"
    return 0
  fi
  if [ "$SKIP_BROWSER" = 1 ]; then
    if ! run uv run pytest -m "not browser"; then
      die "測試沒有通過。" "往上捲看 FAILED 的測試與錯誤訊息。"
    fi
  else
    # 跟 CI 一樣：缺瀏覽器時直接失敗，而不是略過
    if ! run env RPA_REQUIRE_BROWSER=1 uv run pytest; then
      die "測試沒有通過。" "往上捲看 FAILED 的測試與錯誤訊息。"
    fi
  fi
  ok "全部測試通過"
}

summary() {
  local open_docs="xdg-open docs/index.html"
  if [ "$OS" = Darwin ]; then open_docs="open docs/index.html"; fi

  printf '\n%s完成！本機環境已經可以運行。%s\n\n' "$C_GREEN$C_BOLD" "$C_RESET"
  printf '接下來在專案資料夾裡：\n'
  if [ "$START_DIR" != "$REPO_DIR" ]; then printf '  cd %q\n' "$REPO_DIR"; fi
  printf '  %-44s# %s\n' \
    "uv run rpa -h" "命令列工具" \
    "uv run pytest" "跑測試" \
    "$open_docs" "開啟文檔站" \
    "uv run python -m http.server -d docs 8000" "或用本機伺服器瀏覽文檔"
  if [ "$UV_INSTALLED_NOW" = 1 ]; then
    printf '\n%s! uv 是剛安裝的：開一個新的終端機視窗，才能直接使用 uv 命令。%s\n' "$C_YELLOW" "$C_RESET"
  fi
  if [ "$WARNINGS" -gt 0 ]; then
    printf '\n%s! 過程中有 %d 個提醒，見上方以 ! 開頭的行。%s\n' "$C_YELLOW" "$WARNINGS" "$C_RESET"
  fi
}

main() {
  parse_args "$@"
  printf '%s瀏覽器 RPA：本機環境一鍵安裝%s\n' "$C_BOLD" "$C_RESET"
  check_system
  prepare_code
  ensure_uv
  sync_deps
  install_browser
  install_hooks
  verify
  summary
}

# 整個腳本包在 main 裡，透過 curl | bash 執行時才會先讀完全部內容再開始跑。
main ${1+"$@"}
