; Inno Setup script for Omniconv. Compile with ISCC.exe after PyInstaller
; has produced dist\Omniconv\ (see build.ps1). Inno Setup resolves relative
; paths from the script's directory, so SourceDir points at the repository
; root and every path below is written relative to it.

#define AppName "Omniconv"
#define AppVersion "0.1.0"
; The windowed build; omniconv.exe beside it is the console one.
#define AppExe "omniconvw.exe"

[Setup]
SourceDir=..\..
AppId={{F119E4A2-BF6C-4EC8-BADB-BDBBF6307941}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Omniconv contributors
AppPublisherURL=https://github.com/ur-bee-loved/claude
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=dist
OutputBaseFilename=Omniconv-Setup
SetupIconFile=omniconv\data\omniconv.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ChangesEnvironment=yes
; Per-user by default: the PATH entry, the Send-to shortcut and the
; "Open with" registration are all per-user, so an administrative install
; would write them into the administrator's profile rather than the
; profile of whoever ends up using the program. The dialog still offers an
; all-users install, and the registry writes below follow the chosen mode.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "addtopath"; Description: "Add the omniconv command to &PATH"; GroupDescription: "Command line:"
Name: "sendto"; Description: "Add Omniconv to the Explorer &Send to menu"; GroupDescription: "Explorer:"

[Files]
Source: "dist\Omniconv\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "scripts\install-deps.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Install conversion tools"; Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\install-deps.ps1"""; IconFilename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
; Send to is a per-user folder; Explorer offers no all-users equivalent.
Name: "{userappdata}\Microsoft\Windows\SendTo\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: sendto

[Registry]
; Append the install directory to the PATH when the task is selected: the
; user's own for a per-user install, the machine's for an all-users one.
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Tasks: addtopath; Check: not IsAdminInstallMode and NeedsAddPath('{app}')
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Tasks: addtopath; Check: IsAdminInstallMode and NeedsSystemPath('{app}')

[Run]
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\install-deps.ps1"""; Description: "Install conversion tools now (ffmpeg, ImageMagick, Ghostscript, ...)"; Flags: postinstall nowait skipifsilent unchecked
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: postinstall nowait skipifsilent

[Code]
// Register Omniconv in Explorer's "Open with" list for the common formats.
// This never changes the default program for a type; it only adds an entry.
const
  OpenWithTypes = '.png .jpg .jpeg .gif .bmp .tiff .tif .webp .heic .avif .svg .pdf .epub .docx .odt .md .txt .html .csv .json .mp3 .wav .flac .ogg .opus .m4a .mp4 .mkv .webm .mov .avi .zip .7z .ttf .otf .woff .woff2';

function ClassesRoot(): Integer;
begin
  // An all-users install registers for the machine, a per-user one for the
  // user; writing HKCU from an administrative install would only configure
  // the administrator's own profile.
  if IsAdminInstallMode then
    Result := HKEY_LOCAL_MACHINE
  else
    Result := HKEY_CURRENT_USER;
end;

procedure RegisterOpenWith();
var
  Types, Ext: string;
  P: Integer;
  Base: string;
  Root: Integer;
begin
  Root := ClassesRoot();
  Base := 'Software\Classes\Applications\omniconvw.exe';
  RegWriteStringValue(Root, Base, 'FriendlyAppName', 'Omniconv');
  RegWriteStringValue(Root, Base + '\shell\open\command', '', '"' + ExpandConstant('{app}\omniconvw.exe') + '" "%1"');
  Types := OpenWithTypes + ' ';
  while Length(Types) > 0 do
  begin
    P := Pos(' ', Types);
    Ext := Copy(Types, 1, P - 1);
    Types := Copy(Types, P + 1, Length(Types));
    if Ext <> '' then
      RegWriteStringValue(Root, Base + '\SupportedTypes', Ext, '');
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    RegisterOpenWith();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RegDeleteKeyIncludingSubkeys(ClassesRoot(), 'Software\Classes\Applications\omniconvw.exe');
end;

function PathMissing(Root: Integer; Subkey, Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(Root, Subkey, 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Param) + ';', ';' + Uppercase(OrigPath) + ';') = 0;
end;

function NeedsAddPath(Param: string): boolean;
begin
  Result := PathMissing(HKEY_CURRENT_USER, 'Environment', Param);
end;

function NeedsSystemPath(Param: string): boolean;
begin
  Result := PathMissing(HKEY_LOCAL_MACHINE, 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment', Param);
end;
