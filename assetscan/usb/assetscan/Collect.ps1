<#
.SYNOPSIS
    Collects hardware and installed software of this computer onto the USB drive.
.DESCRIPTION
    Each run is saved in <DataDir>\runs\<UTC time>_<HOST>_<machine key>\ (meta.json, details.json,
    hardware.csv, software.csv, run.log), then <DataDir>\hardware.csv and software.csv are rebuilt
    with the latest run of every machine collected so far.
#>
[CmdletBinding()]
param(
    [string]$DataDir,
    [switch]$NoPrompt,
    [string]$AssetId,
    [string]$Department,
    [string]$Location
)

$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'AssetScanLib.ps1')

if (-not $DataDir) { $DataDir = Join-Path (Split-Path $PSScriptRoot -Parent) 'assetscan-data' }
$DataDir = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($DataDir)

$started = Get-Date
$stamp = $started.ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$hostToken = Get-SafeToken $env:COMPUTERNAME
$runsDir = Join-Path $DataDir 'runs'
$partialDir = Join-Path $runsDir "${stamp}_${hostToken}.partial"

try {
    New-Item -ItemType Directory -Force -Path $partialDir -ErrorAction Stop | Out-Null
} catch {
    Write-Host "Cannot write to ${DataDir}: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'Is the USB drive write-protected or full?' -ForegroundColor Red
    exit 1
}
$script:LogPath = Join-Path $partialDir 'run.log'

$elevated = Test-IsElevated
Write-Log "assetscan $script:AssetScanVersion on $env:COMPUTERNAME, PowerShell $($PSVersionTable.PSVersion), elevated=$elevated"
Write-Log "Data folder: $DataDir"

# ---- identity (fast) first, so the operator can answer prompts while the rest runs
$cs = Invoke-Section 'Win32_ComputerSystem' { Get-CimSafe -Class Win32_ComputerSystem | Select-Object -First 1 }
$csp = Invoke-Section 'Win32_ComputerSystemProduct' { Get-CimSafe -Class Win32_ComputerSystemProduct | Select-Object -First 1 }
$bios = Invoke-Section 'Win32_BIOS' { Get-CimSafe -Class Win32_BIOS | Select-Object -First 1 }
$enc = Invoke-Section 'Win32_SystemEnclosure' { Get-CimSafe -Class Win32_SystemEnclosure | Select-Object -First 1 }
$board = Invoke-Section 'Win32_BaseBoard' { Get-CimSafe -Class Win32_BaseBoard | Select-Object -First 1 }

$hostname = ConvertTo-CleanText (Get-Prop $cs 'Name')
if ($hostname -eq '') { $hostname = $env:COMPUTERNAME }

$identity = Get-MachineIdentity -BiosSerial (Get-Prop $bios 'SerialNumber') `
    -ProductSerial (Get-Prop $csp 'IdentifyingNumber') `
    -EnclosureSerial (Get-Prop $enc 'SerialNumber') `
    -Uuid (Get-Prop $csp 'UUID') -Hostname $hostname
Write-Log "Machine key: $($identity.Key)"

$previous = $null
$prior = @(Read-RunMetas -DataDirs $DataDir | Where-Object { $_.machine_key -eq $identity.Key })
if ($prior.Count) {
    $previous = @(Merge-Runs $prior)[0].hardware
    Write-Log "Collected before: $($prior.Count) run(s) on this drive"
}

$assetTag = ConvertTo-CleanText (Get-Prop $enc 'SMBIOSAssetTag')
if (Test-Placeholder $assetTag) { $assetTag = '' }

function Read-Field {
    param([string]$Label, [string]$Default)
    $shown = ''
    if ($Default) { $shown = " [$Default]" }
    $answer = Read-Host "$Label$shown (Enter keeps, - clears)"
    if ($null -eq $answer) { return $Default }
    $answer = $answer.Trim()
    if ($answer -eq '') { return $Default }
    if ($answer -eq '-') { return '' }
    return $answer
}

$defaults = @{
    asset_id   = [string](Get-Prop $previous 'asset_id')
    department = [string](Get-Prop $previous 'department')
    location   = [string](Get-Prop $previous 'location')
}
if ($defaults.asset_id -eq '') { $defaults.asset_id = $assetTag }

$operator = @{}
$given = @{ asset_id = $AssetId; department = $Department; location = $Location }
$paramNames = @{ asset_id = 'AssetId'; department = 'Department'; location = 'Location' }
foreach ($f in 'asset_id', 'department', 'location') {
    if ($PSBoundParameters.ContainsKey($paramNames[$f])) {
        $operator[$f] = $given[$f]
    } elseif ($NoPrompt) {
        $operator[$f] = $defaults[$f]
    } else {
        $operator[$f] = Read-Field -Label $f -Default $defaults[$f]
    }
}

# ---- everything else
Write-Log 'Collecting hardware and software, this can take up to a minute...'
$os = Invoke-Section 'Win32_OperatingSystem' { Get-CimSafe -Class Win32_OperatingSystem | Select-Object -First 1 }
$cv = Invoke-Section 'Registry CurrentVersion' { Get-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' -ErrorAction Stop }
$cpus = @(Invoke-Section 'Win32_Processor' { Get-CimSafe -Class Win32_Processor })
$mem = @(Invoke-Section 'Win32_PhysicalMemory' { Get-CimSafe -Class Win32_PhysicalMemory })
$disks = @(Invoke-Section 'Disks' { Get-DiskInventory })
$gpus = @(Invoke-Section 'Win32_VideoController' { Get-CimSafe -Class Win32_VideoController })
$adapters = @(Invoke-Section 'Network adapters' { Get-AdapterInventory })
$volumes = @(Invoke-Section 'Win32_LogicalDisk' { Get-CimSafe -Class Win32_LogicalDisk -Filter 'DriveType = 3' })
$license = Invoke-Section 'Windows license' { Get-WindowsLicense }
$software = @(Invoke-Section 'Installed programs (registry)' { Get-InstalledSoftware })
$storeApps = @(Invoke-Section 'Store apps (current user)' { Get-StoreApps })

$osText = ConvertTo-CleanText (Get-Prop $os 'Caption')
$display = ConvertTo-CleanText (Get-Prop $cv 'DisplayVersion')
if ($display -eq '') { $display = ConvertTo-CleanText (Get-Prop $cv 'ReleaseId') }
$build = ConvertTo-CleanText (Get-Prop $os 'BuildNumber')
$ubr = Get-Prop $cv 'UBR'
if ($null -ne $ubr -and $build) { $build = "$build.$ubr" }
$arch = if ([Environment]::Is64BitOperatingSystem) { '64-bit' } else { '32-bit' }
if ($display) { $osText = "$osText $display" }
if ($build) { $osText = "$osText (build $build, $arch)" }

$userId = ConvertTo-CleanText (Get-Prop $cs 'UserName')
if ($userId -eq '') { $userId = $env:USERNAME }
$userId = $userId.Split('\')[-1]

$manufacturer = ConvertTo-CleanText (Get-Prop $cs 'Manufacturer')
$rawModel = ConvertTo-CleanText (Get-Prop $cs 'Model')
$macs = Select-AdapterMacs $adapters

$hw = New-EmptyHardware
$hw['asset_id'] = $operator['asset_id']
$hw['serial_number'] = $identity.Serial
$hw['mac_addr_wifi'] = $macs.Wifi
$hw['mac_addr_eth'] = $macs.Eth
$hw['mac_addr_extra'] = $macs.Extra
$hw['type'] = Get-DeviceType -ChassisTypes (Get-Prop $enc 'ChassisTypes') -PCSystemType (Get-Prop $cs 'PCSystemType') -Manufacturer $manufacturer -Model $rawModel
$hw['user_id'] = $userId
$hw['department'] = $operator['department']
$hw['model'] = Get-ModelName -Manufacturer $manufacturer -Model $rawModel -Version (Get-Prop $csp 'Version')
$hw['manufacturer'] = $manufacturer
$hw['os'] = $osText
$hw['extra_hw_info'] = Format-ExtraHwInfo -Cpus $cpus -MemoryModules $mem -TotalMemory (Get-Prop $cs 'TotalPhysicalMemory') -Disks $disks -Gpus $gpus -Board $board -Bios $bios
$hw['key_type'] = [string](Get-Prop $license 'Channel')
$hw['hostname'] = $hostname
$hw['location'] = $operator['location']
$hw['last_log_change'] = $started.ToString('yyyy-MM-dd HH:mm:ss')

$allSoftware = @(@($software) + @($storeApps) | Where-Object { $null -ne $_ } | Sort-Object -Property name, version)
$softwareRows = @(foreach ($s in $allSoftware) { New-SoftwareRecord -Hardware $hw -Item $s })

$details = [ordered]@{
    computer_system  = @(Select-Plain $cs 'Name', 'DNSHostName', 'Domain', 'PartOfDomain', 'Manufacturer', 'Model', 'SystemFamily', 'SystemSKUNumber', 'UserName', 'PCSystemType', 'TotalPhysicalMemory')
    product          = @(Select-Plain $csp 'Vendor', 'Name', 'Version', 'IdentifyingNumber', 'UUID')
    bios             = @(Select-Plain $bios 'Manufacturer', 'SMBIOSBIOSVersion', 'ReleaseDate', 'SerialNumber', 'SMBIOSMajorVersion', 'SMBIOSMinorVersion')
    enclosure        = @(Select-Plain $enc 'Manufacturer', 'ChassisTypes', 'SerialNumber', 'SMBIOSAssetTag')
    baseboard        = @(Select-Plain $board 'Manufacturer', 'Product', 'Version', 'SerialNumber')
    operating_system = @(Select-Plain $os 'Caption', 'Version', 'BuildNumber', 'OSArchitecture', 'OSLanguage', 'InstallDate', 'LastBootUpTime', 'RegisteredUser', 'Organization')
    windows_version  = @(Select-Plain $cv 'EditionID', 'DisplayVersion', 'ReleaseId', 'CurrentBuild', 'UBR')
    processors       = @(Select-Plain $cpus 'Name', 'Manufacturer', 'NumberOfCores', 'NumberOfLogicalProcessors', 'MaxClockSpeed', 'SocketDesignation')
    memory_modules   = @(Select-Plain $mem 'DeviceLocator', 'Capacity', 'Speed', 'Manufacturer', 'PartNumber', 'SerialNumber', 'SMBIOSMemoryType')
    disks            = $disks
    volumes          = @(Select-Plain $volumes 'DeviceID', 'VolumeName', 'FileSystem', 'Size', 'FreeSpace')
    video            = @(Select-Plain $gpus 'Name', 'DriverVersion', 'VideoProcessor', 'AdapterRAM', 'CurrentHorizontalResolution', 'CurrentVerticalResolution')
    network_adapters = $adapters
    license          = $license
}

$meta = [ordered]@{
    schema          = 1
    tool_version    = $script:AssetScanVersion
    machine_key     = $identity.Key
    collected_utc   = $started.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    collected_local = $started.ToString('yyyy-MM-dd HH:mm:ss zzz')
    collected_by    = "$env:USERDOMAIN\$env:USERNAME"
    elevated        = $elevated
    software_count  = $softwareRows.Count
    warnings        = @($script:Warnings)
    hardware        = $hw
}

$finalName = "${stamp}_${hostToken}_$($identity.Key)"
$finalDir = Join-Path $runsDir $finalName
if (Test-Path -LiteralPath $finalDir) {
    $finalName = "${stamp}-$([guid]::NewGuid().ToString('N').Substring(0, 6))_${hostToken}_$($identity.Key)"
    $finalDir = Join-Path $runsDir $finalName
}
try {
    Save-RunFiles -RunDir $partialDir -Meta $meta -Details $details -SoftwareRows $softwareRows
    Write-Log "Saved run files ($($softwareRows.Count) programs)"
    Rename-Item -LiteralPath $partialDir -NewName $finalName -ErrorAction Stop
    $script:LogPath = Join-Path $finalDir 'run.log'
} catch {
    Write-Log "Could not save this run: $($_.Exception.Message)" 'ERROR'
    exit 1
}

try {
    $r = Update-MasterFiles -DataDirs $DataDir -OutDir $DataDir
    Write-Log "Updated hardware.csv and software.csv: $($r.Machines) machine(s), $($r.Runs) run(s)"
} catch {
    Write-Log "Run saved, but the combined CSVs were not updated (open in Excel?): $($_.Exception.Message)" 'ERROR'
}

$summary = '{0}  {1,-15}  {2,-20}  {3,4} programs  {4} warning(s)  {5}' -f `
    $meta.collected_utc, $hostname, $identity.Key, $softwareRows.Count, $script:Warnings.Count, $finalName
try {
    [IO.File]::AppendAllText((Join-Path $DataDir 'collections.log'), $summary + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
} catch { }

Write-Host ''
Write-Host '==================== DONE ====================' -ForegroundColor Green
foreach ($k in 'asset_id', 'hostname', 'serial_number', 'type', 'manufacturer', 'model', 'os', 'user_id', 'mac_addr_wifi', 'mac_addr_eth', 'key_type') {
    Write-Host ('{0,-15} {1}' -f $k, $hw[$k])
}
Write-Host ('{0,-15} {1}' -f 'programs', $softwareRows.Count)
if ($script:Warnings.Count) {
    Write-Host ('{0} warning(s), see {1}' -f $script:Warnings.Count, (Join-Path $finalDir 'run.log')) -ForegroundColor Yellow
}
Write-Host "Saved in $finalDir"
exit 0
