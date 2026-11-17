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
    foreach ($f in 'meta.json', 'details.json', 'hardware.csv', 'software.csv', 'software_detail.csv', 'consent.csv', 'run.log') {
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

$sw = @(Import-Csv -LiteralPath (Join-Path $DataDir 'software_detail.csv') -Encoding UTF8)
$sheet = @([IO.File]::ReadAllLines((Join-Path $DataDir 'software.csv')))
if ($sheet[0] -ne '" asset_id","title","publisher","version","department","usage","url","is_paid","licenses","internal_support_status","last_log_change"') { $failures += "software.csv header is $($sheet[0])" }
if ($sheet.Count - 1 -ne $sw.Count) { $failures += "software.csv has $($sheet.Count - 1) rows, software_detail.csv $($sw.Count)" }
$consents = @(Import-Csv -LiteralPath (Join-Path $DataDir 'consent.csv') -Encoding UTF8)
if ($consents.Count -ne $ExpectRuns) { $failures += "consent.csv has $($consents.Count) row(s), expected $ExpectRuns" }
foreach ($c in $consents) {
    if ($c.accepted -ne 'yes' -or -not $c.email -or $c.hostname -ne $env:COMPUTERNAME) { $failures += "bad consent row: $($c.hostname) $($c.accepted) $($c.email)" }
    if ($ExpectAssetId -and $c.asset_id -ne $ExpectAssetId) { $failures += "consent asset_id '$($c.asset_id)' is not '$ExpectAssetId'" }
}
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
