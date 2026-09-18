<#
.SYNOPSIS
    Build a stand-alone Windows distribution of Omniconv.

.DESCRIPTION
    Produces dist\Omniconv\ with Omniconv.exe (GUI) and omniconv.exe (CLI),
    and, when Inno Setup's ISCC.exe is installed, dist\Omniconv-Setup.exe.
    The external tools (ffmpeg, ImageMagick, ...) are not bundled; run
    scripts\install-deps.ps1 on the target machine or let the Setup wizard
    launch it.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
#>
[CmdletBinding()]
param([switch]$SkipInstaller)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $root

python -m pip install --upgrade pip
python -m pip install -e ".[all,qt]" pyinstaller
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

pyinstaller --noconfirm --clean packaging\windows\omniconv.spec
if ($LASTEXITCODE -ne 0) { throw "pyinstaller failed" }
Write-Host "Built dist\Omniconv\Omniconv.exe and dist\Omniconv\omniconv.exe"

if (-not $SkipInstaller) {
    $iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if (-not $iscc) {
        foreach ($candidate in @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe")) {
            if (Test-Path $candidate) { $iscc = Get-Item $candidate; break }
        }
    }
    if ($iscc) {
        & $iscc.Source packaging\windows\omniconv.iss
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
        Write-Host "Built dist\Omniconv-Setup.exe"
    } else {
        Write-Host "Inno Setup not found (winget install JRSoftware.InnoSetup); skipping the installer."
    }
}
