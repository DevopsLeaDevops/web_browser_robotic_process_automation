<#
.SYNOPSIS
一鍵安裝本機開發環境，並確認專案能運行（Windows）。macOS、Linux 請用 scripts/setup.sh。

.DESCRIPTION
依序完成：檢查系統、準備程式碼、安裝 uv、安裝 Python 與依賴、安裝 Chromium、
安裝提交前檢查，最後執行 rpa --version 與全部測試。重複執行是安全的，已完成的步驟會很快跳過。

已經有程式碼：在專案資料夾裡執行
  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

從零開始（還沒下載程式碼，預設下載到 %USERPROFILE%\code\web_browser_robotic_process_automation），在 PowerShell 執行：
  irm https://raw.githubusercontent.com/DevopsLeaDevops/web_browser_robotic_process_automation/main/scripts/setup.ps1 -OutFile $env:TEMP\rpa-setup.ps1
  powershell -ExecutionPolicy Bypass -File $env:TEMP\rpa-setup.ps1

不要用 irm ... | iex：檔案開頭的 BOM 會留在下載的字串裡，PowerShell 7 會因此解析失敗。

公司網路：先設定 $env:UV_INDEX_URL（套件鏡像）與 $env:PLAYWRIGHT_DOWNLOAD_HOST（瀏覽器鏡像）。
說明文件：docs/develop/quickstart.html

注意：要相容 Windows 內建的 PowerShell 5.1，不能用 &&、||、?:、?? 等 PowerShell 7 語法；
檔案必須存成「UTF-8 含 BOM」，否則 5.1 會用系統編碼讀取，中文變成亂碼（.editorconfig 已設定）。

.PARAMETER Dir
還沒有程式碼時，下載到哪裡。預設 %USERPROFILE%\code\web_browser_robotic_process_automation，
也可以用環境變數 RPA_DIR。在專案資料夾裡執行時不需要。

.PARAMETER SkipBrowser
不下載 Chromium；需要瀏覽器的測試會略過。

.PARAMETER SkipTests
只安裝，不跑測試。

.PARAMETER NoHooks
不安裝 Git 提交前檢查（pre-commit）。

.EXAMPLE
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -SkipBrowser

.EXAMPLE
powershell -ExecutionPolicy Bypass -File $env:TEMP\rpa-setup.ps1 -Dir D:\code\rpa
#>
[CmdletBinding()]
param(
    [string]$Dir = '',
    [switch]$SkipBrowser,
    [switch]$SkipTests,
    [switch]$NoHooks
)

# 萬一被 iex 或貼上執行，$PSCommandPath 是空的；這時發生錯誤不能用 exit，否則會關掉使用者的視窗。
$RpaSetupRunAsFile = -not [string]::IsNullOrEmpty($PSCommandPath)
$RpaSetupScriptRoot = $PSScriptRoot

$RpaSetupResult = @{ Ok = $false }
$RpaSetupArgs = @{
    Dir         = $Dir
    SkipBrowser = [bool]$SkipBrowser
    SkipTests   = [bool]$SkipTests
    NoHooks     = [bool]$NoHooks
    ScriptRoot  = $RpaSetupScriptRoot
    Result      = $RpaSetupResult
}

# 全部邏輯放在子範圍裡，不會把函式和變數留在使用者的工作階段。
# 不擷取這個區塊的輸出，外部命令（uv、pytest）才會直接寫到主控台，保留進度與顏色。
& {
    param(
        [string]$Dir,
        [bool]$SkipBrowser,
        [bool]$SkipTests,
        [bool]$NoHooks,
        [string]$ScriptRoot,
        [hashtable]$Result
    )

    Set-StrictMode -Version 2.0
    $ErrorActionPreference = 'Stop'

    $RepoUrl = 'https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation.git'
    $RepoName = 'web_browser_robotic_process_automation'
    $UvInstaller = 'https://astral.sh/uv/install.ps1'
    $DocPage = 'docs/develop/quickstart.html'
    $TotalSteps = 7

    $State = @{
        Step           = 0
        StepName       = '開始'
        RepoDir        = ''
        Uv             = ''
        UvInstalledNow = $false
        Warnings       = 0
        StartDir       = (Get-Location).Path
    }

    if ([string]::IsNullOrWhiteSpace($Dir)) {
        if ($env:RPA_DIR) { $Dir = $env:RPA_DIR } else { $Dir = Join-Path (Join-Path $HOME 'code') $RepoName }
        $DirGiven = $false
    }
    else {
        $DirGiven = $true
    }
    if ($Dir -match '^~(?=$|[\\/])') { $Dir = $HOME + $Dir.Substring(1) }
    # Path.Combine 遇到絕對路徑會直接採用它；相對路徑以目前資料夾為準
    $Dir = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine((Get-Location).Path, $Dir))

    # ------------------------------------------------------------ 輸出

    function Write-Step([string]$Name) {
        $State.Step++
        $State.StepName = $Name
        Write-Host ''
        Write-Host ('[{0}/{1}] {2}' -f $State.Step, $TotalSteps, $Name) -ForegroundColor Cyan
    }
    function Write-Ok([string]$Text) { Write-Host "  [OK] $Text" -ForegroundColor Green }
    function Write-Info([string]$Text) { Write-Host "  - $Text" -ForegroundColor DarkGray }
    function Write-Warn([string]$Text) {
        $State.Warnings++
        Write-Host "  [!] $Text" -ForegroundColor Yellow
    }

    # 已知原因的失敗：拋出帶有處理方式的錯誤，由最外層統一顯示。
    function Stop-Setup([string]$Message, [string[]]$Hints = @()) {
        $err = New-Object System.Exception $Message
        $err.Data['RpaHints'] = $Hints
        throw $err
    }

    # 執行外部命令；失敗時依 Message 與 Hints 停止。
    function Invoke-Native {
        param(
            [Parameter(Mandatory = $true)][string]$FilePath,
            [string[]]$ArgumentList = @(),
            [string]$Message = '',
            [string[]]$Hints = @(),
            [switch]$Quiet
        )
        if (-not $Quiet) {
            Write-Host ('  $ {0} {1}' -f $FilePath, ($ArgumentList -join ' ')) -ForegroundColor DarkGray
        }
        & $FilePath @ArgumentList
        if ($LASTEXITCODE -ne 0) {
            if ($Message) { Stop-Setup $Message $Hints }
            Stop-Setup ('命令失敗（結束碼 {0}）：{1} {2}' -f $LASTEXITCODE, $FilePath, ($ArgumentList -join ' '))
        }
    }

    # 執行外部命令並回傳是否成功，不顯示輸出。Windows PowerShell 5.1 在
    # $ErrorActionPreference = 'Stop' 時，原生命令寫到 stderr 會變成終止錯誤，所以這裡暫時放寬。
    function Test-Native([string]$FilePath, [string[]]$ArgumentList = @()) {
        $ErrorActionPreference = 'Continue'
        try {
            & $FilePath @ArgumentList *> $null
            return ($LASTEXITCODE -eq 0)
        }
        catch {
            return $false
        }
    }

    function Get-NativeOutput([string]$FilePath, [string[]]$ArgumentList = @()) {
        $ErrorActionPreference = 'Continue'
        $out = & $FilePath @ArgumentList 2> $null
        if ($LASTEXITCODE -ne 0) { return '' }
        return (($out | Out-String).Trim())
    }

    # ------------------------------------------------------------ 小工具

    function Test-RepoRoot([string]$Path) {
        if ([string]::IsNullOrEmpty($Path)) { return $false }
        $cli = Join-Path (Join-Path (Join-Path $Path 'apps') 'cli') 'pyproject.toml'
        if (-not (Test-Path -LiteralPath (Join-Path $Path 'pyproject.toml'))) { return $false }
        if (-not (Test-Path -LiteralPath $cli)) { return $false }
        return [bool](Select-String -LiteralPath $cli -Pattern '^name = "rpa-cli"' -Quiet)
    }

    function Update-SessionPath {
        $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
        $user = [Environment]::GetEnvironmentVariable('Path', 'User')
        $env:Path = (@($machine, $user, $env:Path) | Where-Object { $_ }) -join ';'
    }

    function Test-Git { return [bool](Get-Command git -ErrorAction SilentlyContinue) }

    function Install-Git {
        if (Test-Git) { return }
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            Stop-Setup '找不到 Git。' @(
                '從 https://git-scm.com/download/win 下載安裝，完成後開一個新的 PowerShell 視窗再執行一次。'
            )
        }
        Write-Info '沒有找到 Git，用 winget 安裝（可能會跳出系統權限確認）。'
        Invoke-Native winget @('install', '--id', 'Git.Git', '-e', '--source', 'winget',
            '--accept-package-agreements', '--accept-source-agreements') `
            -Message '用 winget 安裝 Git 失敗。' `
            -Hints @('從 https://git-scm.com/download/win 手動安裝，完成後開一個新的 PowerShell 視窗再執行一次。')
        Update-SessionPath
        if (-not (Test-Git)) {
            Stop-Setup 'Git 裝好了，但這個視窗找不到它。' @('開一個新的 PowerShell 視窗，再執行一次。')
        }
    }

    function Find-Uv {
        $State.Uv = ''
        $cmd = Get-Command uv -ErrorAction SilentlyContinue
        if ($cmd) { $State.Uv = $cmd.Source; return }
        # 剛裝好、但這個視窗的 PATH 還沒更新
        $candidates = @(
            (Join-Path (Join-Path $HOME '.local') 'bin'),
            (Join-Path (Join-Path $HOME '.cargo') 'bin')
        )
        if ($env:XDG_BIN_HOME) { $candidates = @($env:XDG_BIN_HOME) + $candidates }
        foreach ($d in $candidates) {
            foreach ($name in @('uv.exe', 'uv')) {
                $exe = Join-Path $d $name
                if (Test-Path -LiteralPath $exe -PathType Leaf) {
                    $env:Path = "$d;$env:Path"
                    $State.Uv = $exe
                    return
                }
            }
        }
    }

    function Get-UvVersion {
        $text = Get-NativeOutput $State.Uv @('--version')
        if ($text -match 'uv (\d+\.\d+(\.\d+)?)') { return $Matches[1] }
        return '0'
    }

    function Test-VersionAtLeast([string]$Have, [string]$Need) {
        $h = @(($Have -split '\.') + @('0', '0', '0'))[0..2] | ForEach-Object { [int]$_ }
        $n = @(($Need -split '\.') + @('0', '0', '0'))[0..2] | ForEach-Object { [int]$_ }
        for ($i = 0; $i -lt 3; $i++) {
            if ($h[$i] -gt $n[$i]) { return $true }
            if ($h[$i] -lt $n[$i]) { return $false }
        }
        return $true
    }

    function Test-BrowserLaunches {
        return (Test-Native uv @('run', 'python', '-c',
                'from playwright.sync_api import sync_playwright; p = sync_playwright().start(); p.chromium.launch().close(); p.stop()'))
    }

    # ------------------------------------------------------------ 步驟

    function Step-CheckSystem {
        Write-Step '檢查系統'
        $isWin = $true
        $isWinVar = Get-Variable -Name IsWindows -ErrorAction SilentlyContinue
        if ($isWinVar) { $isWin = [bool]$isWinVar.Value }
        if (-not $isWin) {
            Stop-Setup 'macOS、Linux 請改用 scripts/setup.sh。' @('在終端機執行：./scripts/setup.sh')
        }
        Write-Ok ('Windows {0}，PowerShell {1}（{2}）' -f [Environment]::OSVersion.Version,
            $PSVersionTable.PSVersion, $env:PROCESSOR_ARCHITECTURE)
        # 舊版 Windows 的 .NET 預設可能不啟用 TLS 1.2，下載 uv 與 GitHub 內容需要它
        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        }
        catch { }
    }

    function Step-PrepareCode {
        Write-Step '準備程式碼'
        $here = ''
        if ($ScriptRoot) {
            $parent = Split-Path -Parent $ScriptRoot
            if (Test-RepoRoot $parent) { $here = $parent }
        }
        $cwd = (Get-Location).Path
        if ($here) {
            $State.RepoDir = $here
            Write-Ok "使用腳本所在的專案：$here"
        }
        elseif (Test-RepoRoot $cwd) {
            $State.RepoDir = $cwd
            Write-Ok "使用目前資料夾的專案：$cwd"
        }
        elseif (Test-RepoRoot $Dir) {
            $State.RepoDir = $Dir
            Write-Ok "已經下載過：$Dir"
            Write-Info '沒有自動更新程式碼；需要最新版本時在專案資料夾執行 git pull。'
        }
        else {
            Install-Git
            if ((Test-Path -LiteralPath $Dir) -and (Get-ChildItem -LiteralPath $Dir -Force | Select-Object -First 1)) {
                Stop-Setup "$Dir 已經存在，而且不是空資料夾。" @('用 -Dir 指定別的位置，例如：-Dir D:\code\rpa')
            }
            $parentDir = Split-Path -Parent $Dir
            if (-not (Test-Path -LiteralPath $parentDir)) { New-Item -ItemType Directory -Path $parentDir | Out-Null }
            Invoke-Native git @('clone', $RepoUrl, $Dir) -Message '下載程式碼失敗。' `
                -Hints @('確認連得到 github.com；公司網路可能需要設定代理（HTTPS_PROXY）。')
            $State.RepoDir = $Dir
            Write-Ok "已下載到：$Dir"
        }
        if ($DirGiven -and ($State.RepoDir -ne $Dir)) {
            Write-Info '已經在專案資料夾中，-Dir 沒有作用。'
        }
        Set-Location -LiteralPath $State.RepoDir

        if ($env:OneDrive -and $State.RepoDir.StartsWith($env:OneDrive, [StringComparison]::OrdinalIgnoreCase)) {
            Write-Warn '專案在 OneDrive 同步的資料夾，.venv 的大量小檔案會一直被同步。建議移到 %USERPROFILE%\code 之類的位置。'
        }
    }

    function Step-EnsureUv {
        Write-Step '準備 uv'
        $need = '0.11'
        $line = Select-String -LiteralPath 'pyproject.toml' -Pattern '^required-version\s*=\s*">=\s*([0-9][0-9.]*)"' |
            Select-Object -First 1
        if ($line) { $need = $line.Matches[0].Groups[1].Value }

        Find-Uv
        if (-not $State.Uv) {
            Write-Info '沒有找到 uv，用官方安裝腳本安裝。Python 由 uv 下載與管理，不會動到系統的 Python。'
            # 在獨立的 PowerShell 程序執行官方安裝腳本，避免它影響目前的工作階段
            $shell = (Get-Process -Id $PID).Path
            Invoke-Native $shell @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', "irm $UvInstaller | iex") `
                -Message '安裝 uv 失敗。' `
                -Hints @('連不到 astral.sh 時，可以改用 winget install --id astral-sh.uv -e 或 pip install uv 安裝，再執行一次。')
            $State.UvInstalledNow = $true
            Update-SessionPath
            Find-Uv
            if (-not $State.Uv) {
                Stop-Setup 'uv 裝好了，但這個視窗找不到它。' @('開一個新的 PowerShell 視窗，再執行一次。')
            }
        }

        $ver = Get-UvVersion
        if (-not (Test-VersionAtLeast $ver $need)) {
            Write-Info "uv $ver 太舊，專案需要 $need 以上，嘗試升級。"
            if ($State.Uv -match 'WinGet') {
                $null = Test-Native winget @('upgrade', '--id', 'astral-sh.uv', '-e')
            }
            elseif ($State.Uv -match 'scoop') {
                $null = Test-Native scoop @('update', 'uv')
            }
            else {
                $null = Test-Native $State.Uv @('self', 'update')
            }
            $ver = Get-UvVersion
            if (-not (Test-VersionAtLeast $ver $need)) {
                Stop-Setup "uv 仍然是 ${ver}，需要 $need 以上。" @(
                    '用安裝腳本裝的執行 uv self update，winget 裝的執行 winget upgrade astral-sh.uv，其他方式請依原本的安裝方式升級。'
                )
            }
        }
        Write-Ok ('uv {0}（{1}）' -f $ver, $State.Uv)
    }

    function Step-SyncDeps {
        Write-Step '安裝 Python 與依賴'
        if ($env:UV_INDEX_URL) { Write-Info '已設定 UV_INDEX_URL，從套件鏡像下載。' }
        Invoke-Native uv @('sync') -Message '安裝依賴失敗。' `
            -Hints @('連不到 PyPI 時，設定 $env:UV_INDEX_URL 指向公司的套件鏡像（見 docs/develop/setup.html#faq）。')
        $py = Get-NativeOutput uv @('run', 'python', '--version')
        Write-Ok ('{0}，虛擬環境在 {1}' -f $py, (Join-Path $State.RepoDir '.venv'))
    }

    function Step-InstallBrowser {
        Write-Step '安裝 Chromium'
        if ($SkipBrowser) {
            Write-Info '已用 -SkipBrowser 略過；需要瀏覽器的測試也會略過。'
            return
        }
        if ($env:PLAYWRIGHT_DOWNLOAD_HOST) { Write-Info '已設定 PLAYWRIGHT_DOWNLOAD_HOST，從瀏覽器鏡像下載。' }
        Invoke-Native uv @('run', 'playwright', 'install', 'chromium') -Message '下載 Chromium 失敗。' `
            -Hints @('公司網路請設定 $env:PLAYWRIGHT_DOWNLOAD_HOST 指向內部鏡像；或先加 -SkipBrowser 跳過這一步。')
        if (-not (Test-BrowserLaunches)) {
            Stop-Setup 'Chromium 已下載，但無法啟動。' @(
                '手動執行 uv run pytest -m browser 看完整錯誤；仍無法解決時可先加 -SkipBrowser。'
            )
        }
        Write-Ok 'Chromium 可以啟動'
    }

    function Step-InstallHooks {
        Write-Step '安裝提交前檢查'
        if ($NoHooks) {
            Write-Info '已用 -NoHooks 略過。'
            return
        }
        if (-not (Test-Git) -or -not (Test-Native git @('rev-parse', '--git-dir'))) {
            Write-Warn '不是 Git 倉庫（可能是下載 ZIP 解壓縮的），略過。建議改用 git clone 下載。'
            return
        }
        try {
            Invoke-Native uv @('run', 'pre-commit', 'install')
            Write-Ok 'git commit 前會自動執行 ruff、pyright 與文檔檢查'
        }
        catch {
            Write-Warn '安裝提交前檢查失敗（例如 Git 設定了 core.hooksPath）。不影響運行，之後可手動執行 uv run pre-commit install。'
        }
    }

    function Step-Verify {
        Write-Step '確認能運行'
        Invoke-Native uv @('run', 'rpa', '--version') -Quiet -Message 'rpa 命令無法執行。'
        if ($SkipTests) {
            Write-Info '已用 -SkipTests 略過測試。'
            return
        }
        if ($SkipBrowser) {
            Invoke-Native uv @('run', 'pytest', '-m', 'not browser') -Message '測試沒有通過。' `
                -Hints @('往上捲看 FAILED 的測試與錯誤訊息。')
        }
        else {
            # 跟 CI 一樣：缺瀏覽器時直接失敗，而不是略過
            $prev = $env:RPA_REQUIRE_BROWSER
            $env:RPA_REQUIRE_BROWSER = '1'
            try {
                Invoke-Native uv @('run', 'pytest') -Message '測試沒有通過。' `
                    -Hints @('往上捲看 FAILED 的測試與錯誤訊息。')
            }
            finally {
                $env:RPA_REQUIRE_BROWSER = $prev
            }
        }
        Write-Ok '全部測試通過'
    }

    function Write-Summary {
        Write-Host ''
        Write-Host '完成！本機環境已經可以運行。' -ForegroundColor Green
        Write-Host ''
        Write-Host '接下來在專案資料夾裡：'
        if ($State.StartDir -ne $State.RepoDir) { Write-Host ('  cd "{0}"' -f $State.RepoDir) }
        $rows = @(
            @('uv run rpa -h', '命令列工具'),
            @('uv run pytest', '跑測試'),
            @('start docs\index.html', '開啟文檔站'),
            @('uv run python -m http.server -d docs 8000', '或用本機伺服器瀏覽文檔')
        )
        foreach ($row in $rows) { Write-Host ('  {0,-44}# {1}' -f $row[0], $row[1]) }
        if ($State.UvInstalledNow) {
            Write-Host ''
            Write-Host '[!] uv 是剛安裝的：開一個新的 PowerShell 視窗，才能直接使用 uv 命令。' -ForegroundColor Yellow
        }
        if ((Test-Path -LiteralPath 'uv.lock') -and (Test-Git) -and
            -not (Test-Native git @('ls-files', '--error-unmatch', 'uv.lock'))) {
            Write-Host ''
            Write-Host '- 產生了 uv.lock。M0 尚未提交鎖檔，請單獨開一個 PR 提交（見 docs/develop/setup.html#faq）。' -ForegroundColor DarkGray
        }
        if ($State.Warnings -gt 0) {
            Write-Host ''
            Write-Host ('[!] 過程中有 {0} 個提醒，見上方以 [!] 開頭的行。' -f $State.Warnings) -ForegroundColor Yellow
        }
    }

    # ------------------------------------------------------------ 主流程

    # Python 輸出中文時一律用 UTF-8，並讓 PowerShell 用 UTF-8 解讀；結束後還原，不影響使用者的視窗。
    $saved = @{ PYTHONUTF8 = $env:PYTHONUTF8; PYTHONIOENCODING = $env:PYTHONIOENCODING; Location = (Get-Location).Path }
    $savedEncoding = $null
    try { $savedEncoding = [Console]::OutputEncoding; [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch { }
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'

    try {
        Write-Host '瀏覽器 RPA：本機環境一鍵安裝' -ForegroundColor White
        Step-CheckSystem
        Step-PrepareCode
        Step-EnsureUv
        Step-SyncDeps
        Step-InstallBrowser
        Step-InstallHooks
        Step-Verify
        Write-Summary
        $Result.Ok = $true
    }
    catch {
        $ex = $_.Exception
        Write-Host ''
        if ($ex.Data.Contains('RpaHints')) {
            Write-Host ('[X] {0}' -f $ex.Message) -ForegroundColor Red
            foreach ($hint in $ex.Data['RpaHints']) { Write-Host "  $hint" }
        }
        else {
            Write-Host ('[X] 第 {0} 步「{1}」失敗：{2}' -f $State.Step, $State.StepName, $ex.Message) -ForegroundColor Red
            Write-Host '  往上看最後幾行的錯誤訊息。'
        }
        Write-Host "  修正後重新執行同一個命令即可，已完成的步驟會跳過。說明見 $DocPage"
    }
    finally {
        $env:PYTHONUTF8 = $saved.PYTHONUTF8
        $env:PYTHONIOENCODING = $saved.PYTHONIOENCODING
        if ($null -ne $savedEncoding) { try { [Console]::OutputEncoding = $savedEncoding } catch { } }
        # 讓使用者停在原本的資料夾；摘要裡已經印出 cd 命令
        Set-Location -LiteralPath $saved.Location
    }
} @RpaSetupArgs

if ($RpaSetupRunAsFile -and -not $RpaSetupResult.Ok) { exit 1 }
