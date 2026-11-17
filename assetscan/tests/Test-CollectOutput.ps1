param(
    [Parameter(Mandatory = $true)][string]$DataDir,
    [int]$ExpectRuns = 1,
    [string]$ExpectAssetId = ''
)
$ErrorActionPreference = 'Stop'
$failures = @()

$runs = @(Get-ChildItem -LiteralPath (Join-Path $DataDir 'runs') -Directory)
if ($runs.Count -ne $ExpectRuns) { $failures += "expected $ExpectRuns run folder(s), found $($runs.Count)" }
foreach ($r in $runs) {
    if ($r.Name -like '*.partial') { $failures += "unfinished run left behind: $($r.Name)" }
    foreach ($f in 'meta.json', 'details.json', 'hardware.csv', 'software.csv', 'run.log') {
        if (-not (Test-Path -LiteralPath (Join-Path $r.FullName $f))) { $failures += "$($r.Name) is missing $f" }
    }
}

$hwPath = Join-Path $DataDir 'hardware.csv'
$lines = @([IO.File]::ReadAllLines($hwPath))
if ($lines.Count -ne 2) { $failures += "hardware.csv should have 1 machine, has $($lines.Count - 1) row(s)" }
$hw = @(Import-Csv -LiteralPath $hwPath -Encoding UTF8)[0]
if ($hw.hostname -ne $env:COMPUTERNAME) { $failures += "hostname '$($hw.hostname)' is not '$env:COMPUTERNAME'" }
foreach ($c in 'os', 'manufacturer', 'model', 'type', 'user_id', 'last_log_change') {
    if (-not $hw.$c) { $failures += "hardware column $c is empty" }
}
if ($ExpectAssetId -and $hw.asset_id -ne $ExpectAssetId) { $failures += "asset_id '$($hw.asset_id)' is not '$ExpectAssetId'" }
if (-not ($hw.mac_addr_eth -or $hw.mac_addr_wifi -or $hw.mac_addr_extra)) { $failures += 'no MAC address found' }

$sw = @(Import-Csv -LiteralPath (Join-Path $DataDir 'software.csv') -Encoding UTF8)
if ($sw.Count -lt 5) { $failures += "only $($sw.Count) program(s) found" }

$hw.PSObject.Properties | ForEach-Object { '{0,-20} {1}' -f $_.Name, $_.Value } | Write-Host
Write-Host "programs: $($sw.Count)"
Write-Host ''
Get-Content -LiteralPath (Join-Path $runs[-1].FullName 'run.log') | Write-Host

if ($failures.Count) {
    $failures | ForEach-Object { Write-Host "FAIL $_" -ForegroundColor Red }
    exit 1
}
Write-Host 'Collected output looks right' -ForegroundColor Green
exit 0
