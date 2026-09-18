; Inno Setup script for Omniconv. Compile with ISCC.exe after PyInstaller
; has produced dist\Omniconv\ (see build.ps1). Paths are relative to the
; repository root because build.ps1 runs ISCC from there.

#define AppName "Omniconv"
#define AppVersion "0.1.0"
#define AppExe "Omniconv.exe"

[Setup]
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
Name: "{userappdata}\Microsoft\Windows\SendTo\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: sendto

[Registry]
; Append the install directory to the user's PATH when the task is selected.
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Tasks: addtopath; Check: NeedsAddPath('{app}')

[Run]
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\install-deps.ps1"""; Description: "Install conversion tools now (ffmpeg, ImageMagick, Ghostscript, ...)"; Flags: postinstall nowait skipifsilent unchecked
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: postinstall nowait skipifsilent

[Code]
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Param) + ';', ';' + Uppercase(OrigPath) + ';') = 0;
end;
