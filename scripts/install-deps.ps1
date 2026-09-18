<#
.SYNOPSIS
    Install the external tools Omniconv can use on Windows.

.DESCRIPTION
    Every tool is optional: Omniconv detects what is present and offers only
    those conversions. This script follows the same three rules as the Linux
    installer:

      1. A tool that is already installed is skipped. Omniconv also looks in
         the usual Program Files locations, so tools that are installed but
         not on PATH (LibreOffice, calibre, Ghostscript, Tesseract, 7-Zip)
         are still found.
      2. Each missing tool is requested from the first available package
         manager that carries it: winget (built into Windows 10/11), then
         scoop, then Chocolatey. One failed package never stops the rest.
      3. Python-side backends are installed with pip into the user site.

    Microsoft Edge is present on every Windows 10/11 installation and
    serves as the headless browser for HTML rendering, so no browser is
    installed.

.PARAMETER DryRun
    Show what would be installed without changing anything.

.PARAMETER Manager
    Force one package manager: winget, scoop or choco.

.PARAMETER CheckIds
    Do not install anything; instead ask each available package manager
    whether every identifier in the table exists, and report the ones that
    do not. Exit code 2 when any identifier is unknown.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\install-deps.ps1 -DryRun
    powershell -ExecutionPolicy Bypass -File scripts\install-deps.ps1

.NOTES
    The winget, scoop and Chocolatey package identifiers below follow each
    repository's naming but were not all verified on a live Windows system.
    A wrong identifier only affects that one tool.
#>
[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$CheckIds,
    [ValidateSet("", "winget", "scoop", "choco")]
    [string]$Manager = ""
)

$ErrorActionPreference = "Continue"

# probe (command names, comma separated) | extra paths to check (globs, ; separated) | winget id | scoop package | choco package
$Table = @'
ffmpeg||Gyan.FFmpeg|ffmpeg|ffmpeg
magick|%ProgramFiles%\ImageMagick*\magick.exe|ImageMagick.ImageMagick|imagemagick|imagemagick
gswin64c,gswin32c|%ProgramFiles%\gs\gs*\bin\gswin64c.exe|ArtifexSoftware.GhostScript|ghostscript|ghostscript
pdftoppm|%LOCALAPPDATA%\Microsoft\WinGet\Packages\*Poppler*\*\Library\bin\pdftoppm.exe|oschwartz10612.Poppler|poppler|poppler
pandoc|%LOCALAPPDATA%\Pandoc\pandoc.exe;%ProgramFiles%\Pandoc\pandoc.exe|JohnMacFarlane.Pandoc|pandoc|pandoc
soffice|%ProgramFiles%\LibreOffice\program\soffice.exe|TheDocumentFoundation.LibreOffice|extras/libreoffice|libreoffice-fresh
ebook-convert|%ProgramFiles%\Calibre2\ebook-convert.exe|calibre.calibre|extras/calibre|calibre
tesseract|%ProgramFiles%\Tesseract-OCR\tesseract.exe|UB-Mannheim.TesseractOCR|tesseract|tesseract
inkscape|%ProgramFiles%\Inkscape\bin\inkscape.exe|Inkscape.Inkscape|extras/inkscape|inkscape
7z|%ProgramFiles%\7-Zip\7z.exe|7zip.7zip|7zip|7zip
qpdf||QPDF.QPDF|qpdf|qpdf
dot|%ProgramFiles%\Graphviz*\bin\dot.exe|Graphviz.Graphviz|graphviz|graphviz
fontforge|%ProgramFiles(x86)%\FontForgeBuilds\bin\fontforge.exe|FontForge.FontForge|extras/fontforge|fontforge
typst||Typst.Typst|typst|-
pdflatex|%LOCALAPPDATA%\Programs\MiKTeX\miktex\bin\x64\pdflatex.exe;%ProgramFiles%\MiKTeX\miktex\bin\x64\pdflatex.exe|MiKTeX.MiKTeX|latex|miktex
wkhtmltopdf|%ProgramFiles%\wkhtmltopdf\bin\wkhtmltopdf.exe|wkhtmltopdf.wkhtmltox|extras/wkhtmltopdf|wkhtmltopdf
sox||ChrisBagwell.SoX|sox|sox.portable
fluidsynth||FluidSynth.FluidSynth|fluidsynth|-
potrace||-|potrace|potrace
cwebp||-|libwebp|-
optipng||-|optipng|optipng
gifsicle||-|gifsicle|gifsicle
pngquant||-|pngquant|pngquant
jpegoptim||-|jpegoptim|-
lame||-|lame|lame
flac||-|flac|flac
mpg123||-|mpg123|mpg123
cjxl||-|libjxl|-
exiftool||OliverBetz.ExifTool|exiftool|exiftool
python||Python.Python.3.12|python|python
'@

# Python packages. img2pdf, scour and ocrmypdf are command-line tools that
# happen to be distributed through pip, so they are installed here too.
$PyPkgs = "pillow pillow-heif pymupdf pypdf reportlab markdown openpyxl tomli-w PyYAML cairosvg fonttools brotli msgpack PySide6 img2pdf scour ocrmypdf"

function Expand-Vars([string]$s) {
    return [regex]::Replace($s, '%([^%]+)%', { param($m) [Environment]::GetEnvironmentVariable($m.Groups[1].Value) })
}

function Test-Tool([string]$probe, [string]$paths) {
    foreach ($name in $probe.Split(",")) {
        if (Get-Command $name.Trim() -ErrorAction SilentlyContinue) { return $true }
    }
    if ($paths) {
        foreach ($pattern in $paths.Split(";")) {
            $expanded = Expand-Vars $pattern
            if ($expanded -and (Get-Item -Path $expanded -ErrorAction SilentlyContinue)) { return $true }
        }
    }
    return $false
}

function Invoke-Step([string[]]$cmd) {
    if ($DryRun) { Write-Host "  [dry-run] $($cmd -join ' ')"; return $true }
    # Send the tool's own output to the host rather than the pipeline, so the
    # caller receives only the boolean and $LASTEXITCODE reflects the tool.
    & $cmd[0] $cmd[1..($cmd.Length - 1)] 2>&1 | Out-Host
    return ($LASTEXITCODE -eq 0)
}

# ---- package managers present --------------------------------------------
$managers = @()
foreach ($m in @("winget", "scoop", "choco")) {
    if (Get-Command $m -ErrorAction SilentlyContinue) { $managers += $m }
}
if ($Manager) { $managers = @($Manager) }
if ($managers.Count -eq 0) {
    Write-Host "No package manager found. winget ships with Windows 10 (1809+) and 11 as 'App Installer' from the Microsoft Store."
    Write-Host "Alternatively install scoop (https://scoop.sh) or Chocolatey (https://chocolatey.org)."
    exit 1
}
Write-Host "Package managers: $($managers -join ', ')"
if ($managers -contains "scoop" -and -not $DryRun) {
    scoop bucket add extras 2>$null | Out-Null
}

# ---- 0. optional: verify the identifiers against the catalogues ------------
function Test-PackageId([string]$m, [string]$id) {
    switch ($m) {
        "winget" {
            winget show --id $id -e --accept-source-agreements --disable-interactivity *> $null
            return ($LASTEXITCODE -eq 0)
        }
        "choco" {
            $out = choco search $id --exact --limit-output 2>$null
            return [bool]($out -match ("^" + [regex]::Escape($id) + "\|"))
        }
        "scoop" {
            $name = ($id -split "/")[-1]
            $out = scoop search $name 2>$null
            return [bool]($out -match ("(^|\s)" + [regex]::Escape($name) + "(\s|$)"))
        }
    }
    return $false
}

if ($CheckIds) {
    Write-Host ""
    Write-Host "Checking package identifiers against: $($managers -join ', ')"
    $bad = @()
    foreach ($line in $Table -split "`n") {
        $line = $line.Trim()
        if (-not $line) { continue }
        $f = $line.Split("|")
        $ids = @{ winget = $f[2]; scoop = $f[3]; choco = $f[4] }
        foreach ($m in $managers) {
            $id = $ids[$m]
            if (-not $id -or $id -eq "-") { continue }
            $found = Test-PackageId $m $id
            Write-Host ("  {0,-7} {1,-38} {2}" -f $m, $id, $(if ($found) { "ok" } else { "NOT FOUND" }))
            if (-not $found) { $bad += "$m`:$id" }
        }
    }
    Write-Host ""
    if ($bad.Count -gt 0) {
        Write-Host "Identifiers not found: $($bad -join ', ')"
        exit 2
    }
    Write-Host "All identifiers resolve."
    exit 0
}

# ---- 1. work out what is missing ------------------------------------------
Write-Host ""
Write-Host "Checking which backends are already present:"
$missing = @()
foreach ($line in $Table -split "`n") {
    $line = $line.Trim()
    if (-not $line) { continue }
    $f = $line.Split("|")
    $probe = $f[0]; $paths = $f[1]; $ids = @{ winget = $f[2]; scoop = $f[3]; choco = $f[4] }
    $short = $probe.Split(",")[0]
    if (Test-Tool $probe $paths) {
        Write-Host ("  present  {0}" -f $short)
    } else {
        $missing += ,@($probe, $ids)
        $avail = ($managers | Where-Object { $ids[$_] -ne "-" -and $ids[$_] } | ForEach-Object { "$_`:$($ids[$_])" }) -join ", "
        if ($avail) { Write-Host ("  missing  {0,-14} -> {1}" -f $short, $avail) }
        else { Write-Host ("  skipped  {0} (no package in {1})" -f $short, ($managers -join "/")) }
    }
}

# ---- 2. install each missing tool via the first manager that has it -------
Write-Host ""
Write-Host "Installing missing tools:"
$installed = 0; $failed = @()
foreach ($entry in $missing) {
    $probe = $entry[0]; $ids = $entry[1]; $short = $probe.Split(",")[0]
    $done = $false
    foreach ($m in $managers) {
        $id = $ids[$m]
        if (-not $id -or $id -eq "-") { continue }
        Write-Host "  $short via $m ($id)"
        $ok = switch ($m) {
            "winget" { Invoke-Step @("winget", "install", "--id", $id, "-e", "--silent", "--accept-package-agreements", "--accept-source-agreements") }
            "scoop"  { Invoke-Step @("scoop", "install", $id) }
            "choco"  { Invoke-Step @("choco", "install", $id, "-y", "--no-progress") }
        }
        if ($ok) { $done = $true; $installed++; break }
    }
    if (-not $done -and ($managers | Where-Object { $ids[$_] -and $ids[$_] -ne "-" })) { $failed += $short }
}
if ($missing.Count -eq 0) { Write-Host "  nothing to install" }

# ---- 3. Python backends ---------------------------------------------------
Write-Host ""
Write-Host "Python backends (user site-packages):"
$py = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } elseif (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { $null }
if ($py) {
    # No --user: pip falls back to a per-user install by itself when the
    # Python installation is not writable, and a plain install keeps the
    # omniconv command on PATH for per-user Python installations.
    $pipOk = Invoke-Step (@($py, "-m", "pip", "install", "--upgrade") + $PyPkgs.Split(" "))
    if (-not $pipOk) { Write-Host "  pip reported an error; re-run the command above by hand to see why." }
} else {
    Write-Host "  python not found yet; re-run this script after Python is installed (a new terminal is needed for PATH changes)."
}

# ---- 4. notes -------------------------------------------------------------
Write-Host ""
if ($failed.Count -gt 0) { Write-Host "Could not install: $($failed -join ', ')" }
Write-Host "Done. Open a new terminal so PATH changes take effect, then run:  omniconv doctor"
Write-Host "Microsoft Edge provides the headless browser backend; no separate Chromium install is needed."
