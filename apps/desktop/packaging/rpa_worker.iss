; RPA Worker 的安裝檔（M10.1 PR 3，ADR 0014）：Inno Setup 6.7。
;
; 不直接編譯：由 tools/build_desktop.py 在 Windows 上建好 App 後呼叫 ISCC，給下面這些定義：
;   AppVersion      版本（建置資訊，和套件版本相同，例如 0.2.0）
;   SourceDir       PyInstaller 的輸出（dist\desktop\rpa-worker）
;   OutputDir       安裝檔放在哪裡（dist\desktop）
;   IconFile        安裝檔的圖示（rpa_desktop.icon 畫的 .ico）
;   LangDir         繁中、簡中的翻譯檔（Inno Setup 原始碼 is-6_7_1 的檔案，建置時下載並核對 SHA-256）
;   WebView2Setup   Microsoft 的 WebView2 引導程式（建置時下載並核對 Microsoft 的數位簽章）
;   MessagesFile    安裝檔自己的訊息（[CustomMessages]）：建置時從 rpa_desktop 的訊息目錄
;                   installer.* 產生，所以和 App 一樣是繁中、英文人工維護、簡中由工具產生
;
; 行為：
; - 只裝給目前的使用者（不需要管理員）到 %LOCALAPPDATA%\Programs\RPA Worker；開始功能表捷徑。
; - 語言：預設繁中，安裝時可以選（ADR 0007：不跟隨作業系統語言）。
; - RPA Worker 正在執行時（具名 mutex RPAWorker.App，rpa_desktop.single_instance）：在資料夾寫
;   stop.request 請它取消執行中的任務、回報後結束，再換檔案（升級時配對、設定、自動啟動都保留）。
; - 沒有 WebView2 Runtime 時執行引導程式；失敗時說明，App 仍可只用通知區接任務。
; - 解除安裝：確認要解除安裝後停止 App、刪除「登入時執行」的項目；詢問是否也刪除配對、設定與日誌
;   （預設保留；靜默解除安裝不問、保留，加上 /REMOVEDATA=yes 才刪除）。只刪 App 自己的檔案：
;   資料夾可能是 RPA_WORKER_HOME 指定的任何地方，瀏覽器與 Firefox 範本的快取別的程式也在用。
; 名稱與路徑和 Python 那邊的常數一致，由 tests/ci/test_installer.py 檢查。

#ifndef AppVersion
  #error 請用 tools/build_desktop.py worker 建置（缺少 AppVersion 等定義）
#endif

#define AppName "RPA Worker"
#define AppExe "rpa-worker.exe"
#define ChildExe "rpa-child.exe"
#define AppMutexName "RPAWorker.App"
#define StopFile "stop.request"
#define ShowFile "show.request"
#define LockFile "instance.lock"
#define PairingFile "pairing.json"
#define SettingsFile "settings.json"
#define LogsDir "logs"
#define WorkDir "work"
#define RunKey "Software\Microsoft\Windows\CurrentVersion\Run"
#define RunValue "RPA Worker"
#define WebView2Client "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
#define Repository "https://github.com/DevopsLeaDevops/web_browser_robotic_process_automation"

[Setup]
; AppId 決定升級與解除安裝的身分，永遠不要改
AppId={{2CBF2A08-B298-4FC0-A6DF-07036E04AA1E}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=DevopsLeaDevops
AppPublisherURL={#Repository}
AppSupportURL={#Repository}
AppUpdatesURL={#Repository}/releases
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\{#AppName}
DisableDirPage=auto
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=RPA-Worker-Setup-{#AppVersion}-windows-x64
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
; 執行中的 App 由下面的 [Code] 請它自己結束（取消任務並回報），不用 Restart Manager 強制關閉
CloseApplications=no
RestartApplications=no
ShowLanguageDialog=yes
LanguageDetectionMethod=none
; 繁中的翻譯檔是 6.1 版的，少數新訊息用英文：只是警告
MissingMessagesWarning=no
SetupLogging=yes

[Languages]
Name: "zht"; MessagesFile: "{#LangDir}\ChineseTraditional.isl"
Name: "zhs"; MessagesFile: "{#LangDir}\ChineseSimplified.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

#include MessagesFile

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; 升級時先刪掉舊版的程式庫，免得留下新版已經不用的模組
Type: filesandordirs; Name: "{app}\_internal"

[Files]
; 引導程式放第一個：SolidCompression 時取出它不必先解壓整個 App
Source: "{#WebView2Setup}"; Flags: dontcopy
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
const
  StopWaitMilliseconds = 150000;
  { mutex 在 App 結束前就釋放，程序還要一點時間才放開檔案（之後換檔案時 Inno Setup 也會重試） }
  ExitGraceMilliseconds = 1500;

var
  RemoveData: Boolean;

{ RPA Worker 的資料夾：和 App 一樣，環境變數 RPA_WORKER_HOME 優先（CI 用）。 }
function DataDir: String;
begin
  Result := GetEnv('RPA_WORKER_HOME');
  if Result = '' then
    Result := ExpandConstant('{localappdata}\rpa\worker');
end;

function WorkerRunning: Boolean;
begin
  Result := CheckForMutexes('{#AppMutexName}');
end;

procedure RequestStop;
begin
  ForceDirectories(DataDir);
  SaveStringToFile(AddBackslash(DataDir) + '{#StopFile}', 'setup', False);
  Log('已請 RPA Worker 結束：' + AddBackslash(DataDir) + '{#StopFile}');
end;

{ 安裝時：請執行中的 RPA Worker 結束，等它取消任務、回報（最多 150 秒），畫面上顯示進度。 }
function StopWorkerWithProgress: Boolean;
var
  Page: TOutputMarqueeProgressWizardPage;
  Waited: Integer;
begin
  Result := True;
  if not WorkerRunning then
    Exit;
  RequestStop;
  Page := CreateOutputMarqueeProgressPage(SetupMessage(msgWizardPreparing), CustomMessage('Stopping'));
  Page.Show;
  try
    Waited := 0;
    while WorkerRunning and (Waited < StopWaitMilliseconds) do
    begin
      Page.Animate;
      Sleep(100);
      Waited := Waited + 100;
    end;
  finally
    Page.Hide;
  end;
  Result := not WorkerRunning;
  if Result then
    Sleep(ExitGraceMilliseconds);
end;

{ 解除安裝時（沒有精靈頁面）：同樣請它結束並等待。 }
function StopWorkerQuietly: Boolean;
var
  Waited: Integer;
begin
  Result := True;
  if not WorkerRunning then
    Exit;
  RequestStop;
  Waited := 0;
  while WorkerRunning and (Waited < StopWaitMilliseconds) do
  begin
    Sleep(200);
    Waited := Waited + 200;
  end;
  Result := not WorkerRunning;
  if Result then
    Sleep(ExitGraceMilliseconds);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not StopWorkerWithProgress then
    Result := CustomMessage('StillRunning');
end;

function WebView2VersionAt(const Root: Integer; const Key: String): String;
begin
  if not RegQueryStringValue(Root, Key, 'pv', Result) then
    Result := '';
  if Result = '0.0.0.0' then
    Result := '';
end;

{ Microsoft 文件建議的偵測方式：EdgeUpdate 的 Clients 底下有版本（pv）。 }
function WebView2Installed: Boolean;
begin
  Result :=
    (WebView2VersionAt(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{#WebView2Client}') <> '') or
    (WebView2VersionAt(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{#WebView2Client}') <> '') or
    (WebView2VersionAt(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{#WebView2Client}') <> '');
end;

procedure InstallWebView2;
var
  ResultCode: Integer;
begin
  if WebView2Installed then
  begin
    Log('已有 WebView2 Runtime');
    Exit;
  end;
  WizardForm.StatusLabel.Caption := CustomMessage('WebView2Installing');
  ExtractTemporaryFile('{#ExtractFileName(WebView2Setup)}');
  ResultCode := 0;
  if not Exec(ExpandConstant('{tmp}\{#ExtractFileName(WebView2Setup)}'), '/silent /install', '',
    SW_HIDE, ewWaitUntilTerminated, ResultCode) or not WebView2Installed then
  begin
    Log(Format('WebView2 沒有安裝成功（%d）', [ResultCode]));
    { 靜默安裝（/SILENT、/VERYSILENT）不跳訊息擋住自動化；App 開啟時會再說明 }
    if not WizardSilent then
      SuppressibleMsgBox(FmtMessage(CustomMessage('WebView2Failed'), [IntToStr(ResultCode)]),
        mbInformation, MB_OK, IDOK);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    InstallWebView2;
end;

{ 是否也刪除配對、設定與日誌。預設保留：之後重新安裝不必再配對。
  命令列 /REMOVEDATA=yes 或 no 優先（自動化用）；靜默解除安裝不問，保留。 }
function AskRemoveData: Boolean;
var
  Answer: String;
begin
  Answer := ExpandConstant('{param:REMOVEDATA|}');
  if Answer <> '' then
    Result := SameText(Answer, 'yes')
  else if UninstallSilent then
    Result := False
  else
    Result := SuppressibleMsgBox(CustomMessage('RemoveData'), mbConfirmation,
      MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES;
  if Result then
    Log('也刪除配對、設定與日誌')
  else
    Log('保留配對、設定與日誌');
end;

{ 只刪 App 自己的檔案；資料夾空了才刪資料夾本身（RPA_WORKER_HOME 可能指到別的資料夾）。 }
procedure RemoveDataFolder;
var
  Dir: String;
begin
  Dir := AddBackslash(DataDir);
  DeleteFile(Dir + '{#PairingFile}');
  DeleteFile(Dir + '{#SettingsFile}');
  DeleteFile(Dir + '{#LockFile}');
  DeleteFile(Dir + '{#ShowFile}');
  DeleteFile(Dir + '{#StopFile}');
  DelTree(Dir + '{#LogsDir}', True, True, True);
  DelTree(Dir + '{#WorkDir}', True, True, True);
  if not RemoveDir(DataDir) then
    Log('資料夾裡還有別的檔案，保留資料夾：' + DataDir);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  { Inno Setup 問過「確定要解除安裝嗎」之後才到這一步：使用者取消時 App 照常執行 }
  if CurUninstallStep = usAppMutexCheck then
  begin
    RemoveData := AskRemoveData;
    if not StopWorkerQuietly then
    begin
      Log('RPA Worker 沒有在時間內結束，取消解除安裝');
      if not UninstallSilent then
        SuppressibleMsgBox(CustomMessage('StillRunning'), mbError, MB_OK, IDOK);
      Abort;
    end;
  end;
  if CurUninstallStep = usUninstall then
  begin
    { App 自己寫的「登入時執行」：程式刪掉後留著會指向不存在的檔案 }
    RegDeleteValue(HKCU, '{#RunKey}', '{#RunValue}');
    if RemoveData then
      Exec(ExpandConstant('{app}\{#ChildExe}'), '--forget-pairing', '', SW_HIDE,
        ewWaitUntilTerminated, ResultCode);
  end;
  if (CurUninstallStep = usPostUninstall) and RemoveData then
    RemoveDataFolder;
end;
