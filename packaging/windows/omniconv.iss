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
// Register Omniconv in Explorer's "Open with" list for the common formats.
// This never changes the default program for a type; it only adds an entry.
const
  OpenWithTypes = '.png .jpg .jpeg .gif .bmp .tiff .tif .webp .heic .avif .svg .pdf .epub .docx .odt .md .txt .html .csv .json .mp3 .wav .flac .ogg .opus .m4a .mp4 .mkv .webm .mov .avi .zip .7z .ttf .otf .woff .woff2';

procedure RegisterOpenWith();
var
  Types, Ext: string;
  P: Integer;
  Base: string;
begin
  Base := 'Software\Classes\Applications\Omniconv.exe';
  RegWriteStringValue(HKEY_CURRENT_USER, Base, 'FriendlyAppName', 'Omniconv');
  RegWriteStringValue(HKEY_CURRENT_USER, Base + '\shell\open\command', '', '"' + ExpandConstant('{app}\Omniconv.exe') + '" "%1"');
  Types := OpenWithTypes + ' ';
  while Length(Types) > 0 do
  begin
    P := Pos(' ', Types);
    Ext := Copy(Types, 1, P - 1);
    Types := Copy(Types, P + 1, Length(Types));
    if Ext <> '' then
      RegWriteStringValue(HKEY_CURRENT_USER, Base + '\SupportedTypes', Ext, '');
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
    RegDeleteKeyIncludingSubkeys(HKEY_CURRENT_USER, 'Software\Classes\Applications\Omniconv.exe');
end;

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
