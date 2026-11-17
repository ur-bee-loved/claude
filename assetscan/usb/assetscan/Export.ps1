<#
.SYNOPSIS
    Builds hardware.csv, software.csv and software_detail.csv (latest run per machine) from one or more data folders.
.EXAMPLE
    .\Export.ps1
.EXAMPLE
    .\Export.ps1 -DataDir E:\assetscan-data, F:\assetscan-data -OutDir C:\inventory -Delimiter ';' -History
#>
[CmdletBinding()]
param(
    [string[]]$DataDir,
    [string]$OutDir,
    [string]$Delimiter = ',',
    [switch]$History
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'AssetScanLib.ps1')

if (-not $DataDir) { $DataDir = @(Join-Path (Split-Path $PSScriptRoot -Parent) 'assetscan-data') }
$DataDir = @($DataDir | ForEach-Object { $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($_) })
foreach ($d in $DataDir) {
    if (-not (Test-Path -LiteralPath (Join-Path $d 'runs'))) { Write-Warning "No runs folder in $d" }
}
if (-not $OutDir) { $OutDir = Join-Path $DataDir[0] ('export\' + (Get-Date -Format 'yyyyMMdd-HHmmss')) }
$OutDir = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutDir)

$r = Update-MasterFiles -DataDirs $DataDir -OutDir $OutDir -Delimiter $Delimiter -History:$History
Write-Host ('{0} machine(s) from {1} run(s), {2} software row(s)' -f $r.Machines, $r.Runs, $r.SoftwareRows)
Write-Host "Written to $($r.OutDir)"
