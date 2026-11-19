$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
. (Join-Path $root 'usb/assetscan/AssetScanLib.ps1')

$script:Failures = 0
$script:Count = 0
function Assert-Equal {
    param($Expected, $Actual, [string]$Name)
    $script:Count++
    if ("$Expected" -ceq "$Actual") {
        Write-Host "ok   $Name"
    } else {
        $script:Failures++
        Write-Host "FAIL $Name`n     expected: [$Expected]`n     actual:   [$Actual]" -ForegroundColor Red
    }
}

# ---- text helpers
Assert-Equal '' (ConvertTo-CleanText $null) 'clean null'
Assert-Equal 'a b' (ConvertTo-CleanText "  a`t`n b  ") 'clean whitespace'
foreach ($p in 'To be filled by O.E.M.', 'Default string', 'No Asset Tag', 'No Asset Information', 'Asset-1234567890', '0', '00000000', 'FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF', 'System Serial Number', '', ' ', 'N/A', 'None') {
    Assert-Equal $true (Test-Placeholder $p) "placeholder '$p'"
}
foreach ($p in 'PF1ABCDE', '5CG1234XYZ', 'C02XK0ABJGH5') {
    Assert-Equal $false (Test-Placeholder $p) "real serial '$p'"
}
Assert-Equal 'AA:BB:CC:DD:EE:FF' (ConvertTo-Mac 'aa-bb-cc-dd-ee-ff') 'mac dashes'
Assert-Equal 'AA:BB:CC:DD:EE:FF' (ConvertTo-Mac 'AABBCCDDEEFF') 'mac bare'
Assert-Equal '' (ConvertTo-Mac '00-00-00-00-00-00') 'mac zero'
Assert-Equal '' (ConvertTo-Mac '') 'mac empty'
Assert-Equal '2024-01-15' (Format-InstallDate '20240115') 'install date yyyymmdd'
Assert-Equal '15/01/2024' (Format-InstallDate '15/01/2024') 'install date other format kept'
Assert-Equal 'ABC-12' (Get-SafeToken 'a b/c-1\2') 'safe token'
Assert-Equal 'UNKNOWN' (Get-SafeToken '///') 'safe token empty'

# ---- device type
Assert-Equal 'Laptop' (Get-DeviceType -ChassisTypes @(10) -PCSystemType 2 -Manufacturer 'LENOVO' -Model 'x') 'chassis notebook'
Assert-Equal 'Desktop' (Get-DeviceType -ChassisTypes @([uint16]3) -PCSystemType 1) 'chassis desktop uint16'
Assert-Equal 'All-in-One' (Get-DeviceType -ChassisTypes @(13)) 'chassis aio'
Assert-Equal 'Laptop' (Get-DeviceType -ChassisTypes @(2) -PCSystemType 2) 'fallback pcsystemtype'
Assert-Equal 'Unknown' (Get-DeviceType -ChassisTypes $null -PCSystemType $null) 'unknown'
Assert-Equal 'Virtual Machine' (Get-DeviceType -ChassisTypes @(3) -Manufacturer 'Microsoft Corporation' -Model 'Virtual Machine') 'hyper-v vm'
Assert-Equal 'Virtual Machine' (Get-DeviceType -ChassisTypes @(1) -Manufacturer 'VMware, Inc.' -Model 'VMware7,1') 'vmware vm'

# ---- model
Assert-Equal 'ThinkPad T480 (20L5S0XX00)' (Get-ModelName -Manufacturer 'LENOVO' -Model '20L5S0XX00' -Version 'ThinkPad T480') 'lenovo model'
Assert-Equal 'Latitude 5420' (Get-ModelName -Manufacturer 'Dell Inc.' -Model 'Latitude 5420' -Version '') 'dell model'
Assert-Equal '20L5' (Get-ModelName -Manufacturer 'LENOVO' -Model '20L5' -Version 'None') 'lenovo placeholder version'

# ---- identity
$id = Get-MachineIdentity -BiosSerial 'Default string' -ProductSerial 'PF1 ABC' -EnclosureSerial 'X' -Uuid 'U' -Hostname 'PC1'
Assert-Equal 'PF1 ABC' $id.Serial 'identity serial fallback'
Assert-Equal 'SN-PF1ABC' $id.Key 'identity key serial'
$id = Get-MachineIdentity -BiosSerial '' -ProductSerial '' -EnclosureSerial '' -Uuid '4C4C4544-0042-3510-8052-B4C04F4E3732' -Hostname 'PC1'
Assert-Equal 'UU-4C4C4544-0042-3510-8052-B4C04F4E3732' $id.Key 'identity key uuid'
$id = Get-MachineIdentity -BiosSerial '' -ProductSerial '' -EnclosureSerial '' -Uuid '03000200-0400-0500-0006-000700080009' -Hostname 'pc-1'
Assert-Equal 'HN-PC-1' $id.Key 'identity bogus uuid -> hostname'

# ---- MACs
$adapters = @(
    [pscustomobject]@{ Name = 'Ethernet 2'; Description = 'USB GbE'; Mac = '11-11-11-11-11-11'; Medium = 14; PnpId = 'USB\VID_0BDA' },
    [pscustomobject]@{ Name = 'Ethernet'; Description = 'Intel(R) Ethernet Connection'; Mac = '22-22-22-22-22-22'; Medium = 14; PnpId = 'PCI\VEN_8086' },
    [pscustomobject]@{ Name = 'Wi-Fi'; Description = 'Intel(R) Wi-Fi 6 AX201'; Mac = '33-33-33-33-33-33'; Medium = 9; PnpId = 'PCI\VEN_8086' },
    [pscustomobject]@{ Name = 'Bluetooth'; Description = 'Bluetooth Device (PAN)'; Mac = '44-44-44-44-44-44'; Medium = 10; PnpId = 'BTH\MS_BTHPAN' },
    [pscustomobject]@{ Name = 'Dup'; Description = 'dup'; Mac = '22:22:22:22:22:22'; Medium = 14; PnpId = 'PCI\X' }
)
$m = Select-AdapterMacs $adapters
Assert-Equal '33:33:33:33:33:33' $m.Wifi 'mac wifi'
Assert-Equal '22:22:22:22:22:22' $m.Eth 'mac eth prefers built-in'
Assert-Equal '44:44:44:44:44:44; 11:11:11:11:11:11' $m.Extra 'mac extra, built-in first then by name'
$m = Select-AdapterMacs @([pscustomobject]@{ Name = 'Wireless Network Connection'; Description = 'Atheros'; Mac = 'AABBCCDDEEFF'; Medium = $null; PnpId = '' })
Assert-Equal 'AA:BB:CC:DD:EE:FF' $m.Wifi 'mac wifi by name when medium unknown'
$m = Select-AdapterMacs @()
Assert-Equal '' $m.Wifi 'no adapters'

# ---- extra hardware info
$extra = Format-ExtraHwInfo `
    -Cpus @([pscustomobject]@{ Name = 'Intel(R) Core(TM) i5-8250U CPU @ 1.60GHz'; NumberOfCores = 4; NumberOfLogicalProcessors = 8 }) `
    -MemoryModules @([pscustomobject]@{ Capacity = [uint64]4GB }, [pscustomobject]@{ Capacity = [uint64]4GB }) `
    -TotalMemory 0 `
    -Disks @([pscustomobject]@{ Model = 'SAMSUNG MZVLB256'; Media = 'SSD'; Bus = 'NVMe'; SizeBytes = [uint64]256060514304 }) `
    -Gpus @([pscustomobject]@{ Name = 'Intel(R) UHD Graphics 620' }, [pscustomobject]@{ Name = 'Microsoft Basic Display Adapter' }) `
    -Board ([pscustomobject]@{ Manufacturer = 'LENOVO'; Product = '20L5S0XX00' }) `
    -Bios ([pscustomobject]@{ SMBIOSBIOSVersion = 'N22ET80W (1.57 )'; ReleaseDate = [datetime]'2023-04-10' })
Assert-Equal ('CPU: Intel(R) Core(TM) i5-8250U CPU @ 1.60GHz (4C/8T) | RAM: 8 GB (2 modules) | ' +
    'Disk: SAMSUNG MZVLB256 (NVMe SSD, 256 GB) | GPU: Intel(R) UHD Graphics 620 | Board: LENOVO 20L5S0XX00 | ' +
    'BIOS: N22ET80W (1.57 ) (2023-04-10)') $extra 'extra hw info'
Assert-Equal 'RAM: 16 GB' (Format-ExtraHwInfo -TotalMemory ([uint64]17059545088)) 'extra hw info total memory fallback'
Assert-Equal '' (Format-ExtraHwInfo) 'extra hw info nothing'
$info = Get-ExtraHwInfo -Cpus @([pscustomobject]@{ Name = 'AMD Ryzen 5'; NumberOfCores = 6; NumberOfLogicalProcessors = 12 }) -TotalMemory ([uint64]17059545088)
Assert-Equal 'AMD Ryzen 5 (6C/12T)|16 GB||||' ('{0}|{1}|{2}|{3}|{4}|{5}' -f $info.cpu, $info.ram, $info.disk, $info.gpu, $info.board, $info.bios) 'extra hw info as separate values'
Assert-Equal 'CPU: AMD Ryzen 5 (6C/12T) | RAM: 16 GB' (Format-ExtraHwInfo -Info $info) 'extra hw info from separate values'

# ---- uninstall entries
$e = ConvertFrom-UninstallEntry -Values @{ DisplayName = 'Mozilla Firefox (x64 pt-BR)'; DisplayVersion = '133.0'; Publisher = 'Mozilla'; InstallDate = '20241101' } -Architecture '64-bit' -Scope 'machine'
Assert-Equal 'Mozilla Firefox (x64 pt-BR)|133.0|Mozilla|2024-11-01|64-bit|machine|registry' (($e.name, $e.version, $e.publisher, $e.install_date, $e.architecture, $e.scope, $e.source) -join '|') 'uninstall entry'
Assert-Equal $null (ConvertFrom-UninstallEntry -Values @{ DisplayName = 'X'; SystemComponent = 1 } -Architecture '' -Scope 'machine') 'skip system component'
Assert-Equal $null (ConvertFrom-UninstallEntry -Values @{ DisplayName = 'KB123'; ParentKeyName = 'Office' } -Architecture '' -Scope 'machine') 'skip child update'
Assert-Equal $null (ConvertFrom-UninstallEntry -Values @{ DisplayName = 'KB123'; ReleaseType = 'Security Update' } -Architecture '' -Scope 'machine') 'skip security update'
Assert-Equal $null (ConvertFrom-UninstallEntry -Values @{ DisplayName = '' } -Architecture '' -Scope 'machine') 'skip nameless'
$d = @(Remove-DuplicateSoftware @($e, $e, (ConvertFrom-UninstallEntry -Values @{ DisplayName = 'Mozilla Firefox (x64 pt-BR)'; DisplayVersion = '133.0' } -Architecture '32-bit' -Scope 'machine')))
Assert-Equal 2 $d.Count 'dedupe software'

# ---- other information
$oi = [ordered]@{ domain = 'EMPRESA'; empty = ''; none = $null; list = @('a', '', 'b|c'); joined = (Format-YesNo $true); date = (Format-DateValue ([datetime]'2024-03-05 14:07:00')) }
Assert-Equal 'domain: EMPRESA | list: a; b/c | joined: yes | date: 2024-03-05 14:07' (Format-OtherInfo $oi) 'other info format'
Assert-Equal '' (Format-OtherInfo ([ordered]@{ a = ''; b = @() })) 'other info empty'
Assert-Equal 'a: xxxxxx...' (Format-OtherInfo ([ordered]@{ a = ('x' * 50) }) -MaxLength 12) 'other info truncated'
Assert-Equal 'DEL' (ConvertFrom-WmiCharArray @(68, 69, 76, 0, 0)) 'wmi char array'
Assert-Equal '' (ConvertFrom-WmiCharArray $null) 'wmi char array null'
Assert-Equal 'no' (Format-YesNo $false) 'yes/no false'
Assert-Equal '' (Format-YesNo $null) 'yes/no null'
Assert-Equal '16 GB' (Format-GB ([uint64]17179869184)) 'format GB'

# ---- consent
Assert-Equal $true (Test-CorporateEmail 'maria.silva@empresa.com.br') 'email ok'
Assert-Equal $false (Test-CorporateEmail 'maria.silva') 'email without @'
Assert-Equal $false (Test-CorporateEmail 'maria @empresa.com') 'email with space'
Assert-Equal $true (Test-CorporateEmail 'Maria@Empresa.com.br' -Domain 'empresa.com.br') 'email domain match'
Assert-Equal $false (Test-CorporateEmail 'maria@gmail.com' -Domain 'empresa.com.br') 'email domain mismatch'
Assert-Equal 227 ([int][char]$script:ConsentStatement[($script:ConsentStatement.IndexOf('ser') + 3)]) 'statement has real accents (ser + a-tilde)'

# ---- run files, merge and master CSVs, end to end on a temporary data folder
$tmp = Join-Path ([IO.Path]::GetTempPath()) ('assetscan-test-' + [guid]::NewGuid().ToString('N'))
$data = Join-Path $tmp 'data'
function New-FakeRun {
    param([string]$Key, [string]$Utc, [string]$Hostname, [hashtable]$Fields, [string[]]$Programs, [string]$Email = 'user@example.com', [switch]$Declined)
    $hw = New-EmptyHardware
    $hw['hostname'] = $Hostname
    $hw['last_log_change'] = $Utc
    foreach ($k in $Fields.Keys) { $hw[$k] = $Fields[$k] }
    $consent = [ordered]@{ accepted = if ($Declined) { 'no' } else { 'yes' }; email = $Email; consent_date = $Utc; method = 'dialog'; statement = $script:ConsentStatement }
    $meta = [ordered]@{ schema = 2; declined = [bool]$Declined; machine_key = $Key; collected_utc = $Utc; warnings = @(); consent = $consent; hardware = $hw }
    if (-not $Declined) { $meta['extra_hw'] = [ordered]@{ cpu = 'CPU ' + $Key; ram = '8 GB'; disk = ''; gpu = ''; board = ''; bios = '' } }
    if (-not $Declined) { $meta['other_info'] = [ordered]@{ domain = 'EMPRESA'; monitors = @('DEL U2419H', '', 'LEN T24'); scanned_as_admin = 'no' } }
    $rows = @(foreach ($p in $Programs) { New-SoftwareRecord -Hardware $hw -Item ([pscustomobject]@{ name = $p; version = '1.0'; source = 'registry' }) })
    $dir = Join-Path $data ("runs/{0}_{1}_{2}" -f ($Utc -replace '[-:]', ''), $Hostname, $Key)
    Save-RunFiles -RunDir $dir -Meta $meta -Details ([ordered]@{ x = 1 }) -SoftwareRows $rows
}
try {
    New-FakeRun -Key 'SN-AAA' -Utc '2026-01-01T10:00:00Z' -Hostname 'PC-B' -Fields @{ asset_id = 'TAG-1'; location = 'Sala 2'; os = 'old' } -Programs 'Old App'
    New-FakeRun -Key 'SN-AAA' -Utc '2026-02-01T10:00:00Z' -Hostname 'PC-B' -Fields @{ department = 'TI'; os = 'new' } -Programs 'App A', 'App B'
    New-FakeRun -Key 'SN-BBB' -Utc '2026-01-15T10:00:00Z' -Hostname 'PC-A' -Fields @{ asset_id = 'TAG-2'; serial_number = 'BBB' } -Programs @()
    New-FakeRun -Key 'HN-PC-D' -Utc '2026-01-20T10:00:00Z' -Hostname 'PC-D' -Fields @{} -Programs @() -Email '' -Declined
    New-Item -ItemType Directory -Force -Path (Join-Path $data 'runs/20260301T000000Z_PC-C.partial') | Out-Null

    $metas = @(Read-RunMetas -DataDirs $data)
    Assert-Equal 4 $metas.Count 'read metas skips partial'
    Assert-Equal $false (Test-Path -LiteralPath (Join-Path $data 'runs/20260120T100000Z_PC-D_HN-PC-D/hardware.csv')) 'declined run has no hardware file'
    Assert-Equal $false (Test-Path -LiteralPath (Join-Path $data 'runs/20260120T100000Z_PC-D_HN-PC-D/extra_hw_info.csv')) 'declined run has no extra hw file'
    $xhw = @(Import-Csv -LiteralPath (Join-Path $data 'runs/20260101T100000Z_PC-B_SN-AAA/extra_hw_info.csv') -Encoding UTF8)
    Assert-Equal 'SN-AAA|TAG-1|PC-B|CPU SN-AAA|8 GB' ('{0}|{1}|{2}|{3}|{4}' -f $xhw[0].machine_key, $xhw[0].asset_id, $xhw[0].hostname, $xhw[0].cpu, $xhw[0].ram) 'run extra_hw_info.csv linked to the machine'
    $oiPath = Join-Path $data 'runs/20260101T100000Z_PC-B_SN-AAA/other_information.csv'
    Assert-Equal ('"' + ($script:OtherInfoColumns -join '","') + '"') ([IO.File]::ReadAllLines($oiPath)[0]) 'run other_information.csv header'
    $oi = @(Import-Csv -LiteralPath $oiPath -Encoding UTF8)[0]
    Assert-Equal 'SN-AAA|TAG-1|EMPRESA|DEL U2419H; LEN T24|no|' ('{0}|{1}|{2}|{3}|{4}|{5}' -f $oi.machine_key, $oi.asset_id, $oi.domain, $oi.monitors, $oi.scanned_as_admin, $oi.tpm) 'run other_information.csv one item per column'
    Assert-Equal $false (Test-Path -LiteralPath (Join-Path $data 'runs/20260120T100000Z_PC-D_HN-PC-D/other_information.csv')) 'declined run has no other information file'
    Assert-Equal $true (Test-Path -LiteralPath (Join-Path $data 'runs/20260120T100000Z_PC-D_HN-PC-D/consent.csv')) 'declined run has a consent file'

    $out = Join-Path $tmp 'out'
    $r = Update-MasterFiles -DataDirs $data -OutDir $out -History
    Assert-Equal 2 $r.Machines 'machines (declined run left out)'
    Assert-Equal 4 $r.Runs 'runs'
    Assert-Equal 4 $r.Consents 'consent records, one per run'
    Assert-Equal 2 $r.SoftwareRows 'software rows from latest runs only'

    $lines = [IO.File]::ReadAllLines((Join-Path $out 'hardware.csv'))
    $expectedHeader = '"asset_id","serial_number","mac_addr_wifi","mac_addr_eth","mac_addr_extra","type","user_id","department","model","manufacturer","os","extra_hw_info","key_type","hostname","acquired_in","receipt_number"," location","status","approved_to_connect","last_log_change"'
    Assert-Equal $expectedHeader $lines[0] 'hardware header matches the sheet'
    Assert-Equal 3 $lines.Count 'hardware rows'

    $hw = @(Import-Csv -LiteralPath (Join-Path $out 'hardware.csv') -Encoding UTF8)
    Assert-Equal 'PC-A' $hw[0].hostname 'sorted by hostname'
    Assert-Equal 'TAG-1' $hw[1].asset_id 'asset_id carried from older run'
    Assert-Equal 'Sala 2' (@($hw[1].PSObject.Properties | Where-Object { $_.Name.Trim() -eq 'location' })[0].Value) 'location carried from older run'
    Assert-Equal 'TI' $hw[1].department 'department from latest run'
    Assert-Equal 'new' $hw[1].os 'collected fields from latest run'

    $sw = @(Import-Csv -LiteralPath (Join-Path $out 'software_detail.csv') -Encoding UTF8)
    Assert-Equal ($script:SoftwareColumns -join ',') (($sw[0].PSObject.Properties | ForEach-Object { $_.Name }) -join ',') 'software detail header'
    Assert-Equal 'App A,App B' (($sw | ForEach-Object { $_.name }) -join ',') 'software of latest run'
    Assert-Equal 'TAG-1' $sw[0].asset_id 'software asset_id follows merged hardware'

    $sheet = [IO.File]::ReadAllLines((Join-Path $out 'software.csv'))
    Assert-Equal '" asset_id","title","publisher","version","department","usage","url","is_paid","licenses","internal_support_status","last_log_change","other_information"' $sheet[0] 'software header matches the sheet'
    Assert-Equal '"TAG-1","App A","","1.0","TI","","","","","","2026-02-01T10:00:00Z","hostname: PC-B | source: registry"' $sheet[1] 'software sheet row: asset_id and department from merged hardware'
    Assert-Equal 3 $sheet.Count 'software sheet rows'
    $runSheet = [IO.File]::ReadAllLines((Join-Path $data 'runs/20260201T100000Z_PC-B_SN-AAA/software.csv'))
    Assert-Equal '"","App A","","1.0","TI","","","","","","2026-02-01T10:00:00Z","hostname: PC-B | source: registry"' $runSheet[1] 'per-run software sheet uses that run only'

    Assert-Equal 2 @(Read-RunMetas -DataDirs $data -Key 'SN-AAA').Count 'read metas filtered by machine key'

    $hist = [IO.File]::ReadAllLines((Join-Path $out 'hardware_history.csv'))
    Assert-Equal 4 $hist.Count 'history has every collected run'

    $consents = @(Import-Csv -LiteralPath (Join-Path $out 'consent.csv') -Encoding UTF8)
    Assert-Equal ($script:ConsentColumns -join ',') (($consents[0].PSObject.Properties | ForEach-Object { $_.Name }) -join ',') 'consent header'
    Assert-Equal 'PC-B,PC-A,PC-D,PC-B' (($consents | ForEach-Object { $_.hostname }) -join ',') 'consent rows in time order'
    Assert-Equal 'TAG-1|yes|user@example.com' ('{0}|{1}|{2}' -f $consents[3].asset_id, $consents[3].accepted, $consents[3].email) 'consent linked to merged asset_id'
    Assert-Equal 'TAG-1' $consents[0].asset_id 'older consent also gets the current asset_id'
    Assert-Equal '|no|' ('{0}|{1}|{2}' -f $consents[2].asset_id, $consents[2].accepted, $consents[2].email) 'declined consent row'
    Assert-Equal $script:ConsentStatement $consents[0].statement 'statement survives the CSV round trip with accents'

    $bytes = [IO.File]::ReadAllBytes((Join-Path $out 'hardware.csv'))
    Assert-Equal '239,187,191' (($bytes[0..2]) -join ',') 'csv has UTF-8 BOM for Excel'

    $r = Update-MasterFiles -DataDirs $data -OutDir (Join-Path $tmp 'semi') -Delimiter ';'
    $first = [IO.File]::ReadAllLines((Join-Path $tmp 'semi/hardware.csv'))[0]
    Assert-Equal $true ($first.StartsWith('"asset_id";"serial_number"')) 'semicolon delimiter'

    $r = Update-MasterFiles -DataDirs (Join-Path $tmp 'empty') -OutDir (Join-Path $tmp 'empty-out')
    Assert-Equal 0 $r.Machines 'empty data folder'
    Assert-Equal $expectedHeader ([IO.File]::ReadAllLines((Join-Path $tmp 'empty-out/hardware.csv'))[0]) 'empty export still has header'

    Write-TextFileAtomic -Path (Join-Path $tmp 'atomic.txt') -Lines @('one')
    Write-TextFileAtomic -Path (Join-Path $tmp 'atomic.txt') -Lines @('two')
    Assert-Equal 'two' ([IO.File]::ReadAllLines((Join-Path $tmp 'atomic.txt'))[0]) 'atomic overwrite'
    Assert-Equal $false (Test-Path -LiteralPath (Join-Path $tmp 'atomic.txt.tmp')) 'no temp file left'
} finally {
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host ''
if ($script:Failures) {
    Write-Host "$script:Failures of $script:Count checks failed" -ForegroundColor Red
    exit 1
}
Write-Host "All $script:Count checks passed" -ForegroundColor Green
exit 0
