<#
.SYNOPSIS
    Collects hardware and installed software of this computer onto the USB drive.
.DESCRIPTION
    Each run is saved in <DataDir>\runs\<UTC time>_<HOST>_<machine key>\ (meta.json, details.json,
    hardware.csv, software.csv, software_detail.csv, run.log), then <DataDir>\hardware.csv,
    software.csv and software_detail.csv are rebuilt with the latest run of every machine.
    -NoMerge skips that rebuild, for many computers writing to one network share at once.
    Nothing is read from the computer until the user accepts the consent window. -ConsentEmail
    records consent given some other way (on paper, by e-mail) and skips the window.
#>
[CmdletBinding()]
param(
    [string]$DataDir,
    [switch]$NoPrompt,
    [string]$AssetId,
    [string]$Department,
    [string]$Location,
    [switch]$NoMerge,
    [string]$ConsentEmail
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

function Complete-Run {
    param($Meta, [string]$FinalName, $Details, [object[]]$SoftwareRows)
    $finalDir = Join-Path $runsDir $FinalName
    if (Test-Path -LiteralPath $finalDir) {
        $FinalName = "${stamp}-$([guid]::NewGuid().ToString('N').Substring(0, 6))_" + $FinalName.Substring($stamp.Length + 1)
        $finalDir = Join-Path $runsDir $FinalName
    }
    try {
        Save-RunFiles -RunDir $partialDir -Meta $Meta -Details $Details -SoftwareRows $SoftwareRows
        Rename-Item -LiteralPath $partialDir -NewName $FinalName -ErrorAction Stop
        $script:LogPath = Join-Path $finalDir 'run.log'
    } catch {
        Write-Log "Could not save this run: $($_.Exception.Message)" 'ERROR'
        exit 1
    }
    if ($NoMerge) {
        Write-Log 'NoMerge: combined CSVs not rebuilt, run Export.ps1 later'
    } else {
        try {
            $r = Update-MasterFiles -DataDirs $DataDir -OutDir $DataDir
            Write-Log "Updated the combined CSVs: $($r.Machines) machine(s), $($r.Runs) run(s), $($r.Consents) consent record(s)"
        } catch {
            Write-Log "Run saved, but the combined CSVs were not updated (open in Excel?): $($_.Exception.Message)" 'ERROR'
        }
    }
    $line = '{0}  {1,-15}  {2,-20}  {3,4} programs  {4} warning(s)  consent={5}  {6}' -f `
        $Meta.collected_utc, $Meta.hardware['hostname'], $Meta.machine_key, $SoftwareRows.Count, $script:Warnings.Count, $Meta.consent['accepted'], $FinalName
    try {
        [IO.File]::AppendAllText((Join-Path $DataDir 'collections.log'), $line + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
    } catch { }
    return $finalDir
}

# ---- consent comes before anything is read from the computer
if ($PSBoundParameters.ContainsKey('ConsentEmail')) {
    if (-not (Test-CorporateEmail $ConsentEmail)) {
        Write-Log "Invalid -ConsentEmail '$ConsentEmail'" 'ERROR'
        exit 1
    }
    $answer = [pscustomobject]@{ Accepted = $true; Email = ConvertTo-CleanText $ConsentEmail }
    $consentMethod = 'parameter'
} else {
    try {
        $answer = Show-ConsentDialog
    } catch {
        Write-Log "The consent window could not be shown, nothing was collected: $($_.Exception.Message)" 'ERROR'
        exit 1
    }
    $consentMethod = 'dialog'
}
$consent = [ordered]@{
    accepted     = if ($answer.Accepted) { 'yes' } else { 'no' }
    email        = if ($answer.Accepted) { $answer.Email } else { '' }
    consent_date = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    method       = $consentMethod
    statement    = $script:ConsentStatement
}
Write-Log "Consent: accepted=$($consent.accepted) email=$($consent.email) method=$consentMethod"

if (-not $answer.Accepted) {
    $hw = New-EmptyHardware
    $hw['hostname'] = $env:COMPUTERNAME
    $hw['last_log_change'] = $started.ToString('yyyy-MM-dd HH:mm:ss')
    $meta = [ordered]@{
        schema          = 2
        tool_version    = $script:AssetScanVersion
        declined        = $true
        machine_key     = "HN-$hostToken"
        collected_utc   = $started.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        collected_local = $started.ToString('yyyy-MM-dd HH:mm:ss zzz')
        warnings        = @()
        consent         = $consent
        hardware        = $hw
    }
    $finalDir = Complete-Run -Meta $meta -FinalName "${stamp}_${hostToken}_DECLINED" -Details $null -SoftwareRows @()
    Write-Host ''
    Write-Host 'Coleta recusada: nenhuma informacao do sistema foi coletada.' -ForegroundColor Yellow
    Write-Host "Consent refusal recorded in $finalDir"
    exit 0
}

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
$prior = @(Read-RunMetas -DataDirs $DataDir -Key $identity.Key | Where-Object { $_.machine_key -eq $identity.Key })
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
$ipConfig = @(Invoke-Section 'IP configuration' { Get-CimSafe -Class Win32_NetworkAdapterConfiguration -Filter 'IPEnabled = TRUE' })
$monitors = @(Invoke-Section 'Monitors' { Get-CimSafe -Class WmiMonitorID -Namespace 'root\wmi' })
$batteries = @(Invoke-Section 'Win32_Battery' { Get-CimSafe -Class Win32_Battery })
$printers = @(Invoke-Section 'Win32_Printer' { Get-CimSafe -Class Win32_Printer })
$secureBoot = Invoke-Section 'Secure Boot' { Get-SecureBootState }
$tpm = ''
if ($elevated) { $tpm = Invoke-Section 'TPM' { Get-TpmSummary } }
$antivirus = @()
if ([string](Get-Prop $os 'ProductType') -eq '1') {
    $antivirus = @(Invoke-Section 'Antivirus (Security Center)' { Get-CimSafe -Class AntiVirusProduct -Namespace 'root\SecurityCenter2' })
}
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
if ($userId.EndsWith('$')) { $userId = '' }

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

$other = [ordered]@{}
$other['domain'] = Get-Prop $cs 'Domain'
$other['domain_joined'] = Format-YesNo (Get-Prop $cs 'PartOfDomain')
$dnsName = ConvertTo-CleanText (Get-Prop $cs 'DNSHostName')
if ($dnsName -and $dnsName -ne $hostname) { $other['dns_hostname'] = $dnsName }
$other['system_family'] = Get-Prop $cs 'SystemFamily'
$other['system_sku'] = Get-Prop $cs 'SystemSKUNumber'
$other['uuid'] = Get-Prop $csp 'UUID'
$encSerial = ConvertTo-CleanText (Get-Prop $enc 'SerialNumber')
if (-not (Test-Placeholder $encSerial) -and $encSerial -ne $identity.Serial) { $other['chassis_serial'] = $encSerial }
$boardSerial = ConvertTo-CleanText (Get-Prop $board 'SerialNumber')
if (-not (Test-Placeholder $boardSerial) -and $boardSerial -ne $identity.Serial) { $other['board_serial'] = $boardSerial }
if ($assetTag) { $other['bios_asset_tag'] = $assetTag }
$other['bios_vendor'] = Get-Prop $bios 'Manufacturer'
$other['secure_boot'] = $secureBoot
$other['tpm'] = $tpm
$other['os_edition'] = Get-Prop $cv 'EditionID'
$other['os_language'] = Get-Prop $os 'MUILanguages'
$other['os_install_date'] = Format-DateValue (Get-Prop $os 'InstallDate')
$other['last_boot'] = Format-DateValue (Get-Prop $os 'LastBootUpTime')
$other['registered_owner'] = Get-Prop $os 'RegisteredUser'
$other['organization'] = Get-Prop $os 'Organization'
$other['time_zone'] = [TimeZoneInfo]::Local.Id
$other['license_status'] = Get-Prop $license 'Status'
if ($null -ne $license) { $other['firmware_product_key'] = Format-YesNo (Get-Prop $license 'FirmwareKeyPresent') }
$other['memory_modules'] = @(foreach ($m in $mem) {
    if ($null -eq $m) { continue }
    $line = '{0} {1}' -f (ConvertTo-CleanText (Get-Prop $m 'DeviceLocator')), (Format-GB (Get-Prop $m 'Capacity'))
    $speed = Get-Prop $m 'Speed'
    if ($speed) { $line += " $speed MHz" }
    $line += ' ' + (ConvertTo-CleanText ('{0} {1}' -f (Get-Prop $m 'Manufacturer'), (Get-Prop $m 'PartNumber')))
    $memSerial = ConvertTo-CleanText (Get-Prop $m 'SerialNumber')
    if (-not (Test-Placeholder $memSerial)) { $line += " SN $memSerial" }
    $line
})
$other['disks'] = @(foreach ($d in $disks) {
    if ($null -eq $d) { continue }
    $line = '{0} {1}' -f $d.Model, $d.Bus
    if (-not (Test-Placeholder $d.Serial)) { $line += " SN $($d.Serial)" }
    $line
})
$other['volumes'] = @(foreach ($v in $volumes) {
    if ($null -eq $v) { continue }
    '{0} {1} {2}, {3} free' -f (Get-Prop $v 'DeviceID'), (Get-Prop $v 'FileSystem'), (Format-GB (Get-Prop $v 'Size')), (Format-GB (Get-Prop $v 'FreeSpace'))
})
$other['network_adapters'] = @(foreach ($a in $adapters) {
    if ($null -eq $a) { continue }
    '{0} ({1}) {2} {3} {4}' -f $a.Name, $a.Description, (ConvertTo-Mac $a.Mac), $a.Status, $a.LinkSpeed
})
$other['ip_config'] = @(foreach ($c in $ipConfig) {
    if ($null -eq $c) { continue }
    $line = '{0}: {1}' -f (ConvertTo-CleanText (Get-Prop $c 'Description')), (@(Get-Prop $c 'IPAddress') -join ', ')
    $gw = @(Get-Prop $c 'DefaultIPGateway') -join ', '
    if ($gw) { $line += " gw $gw" }
    $dnsServers = @(Get-Prop $c 'DNSServerSearchOrder') -join ', '
    if ($dnsServers) { $line += " dns $dnsServers" }
    $line += ' dhcp ' + (Format-YesNo (Get-Prop $c 'DHCPEnabled'))
    $line
})
$other['gpu_drivers'] = @(foreach ($g in $gpus) {
    if ($null -eq $g) { continue }
    $line = '{0} {1}' -f (ConvertTo-CleanText (Get-Prop $g 'Name')), (Get-Prop $g 'DriverVersion')
    $rx = Get-Prop $g 'CurrentHorizontalResolution'
    $ry = Get-Prop $g 'CurrentVerticalResolution'
    if ($rx -and $ry) { $line += " ${rx}x${ry}" }
    $line
})
$other['monitors'] = @(foreach ($m in $monitors) {
    if ($null -eq $m) { continue }
    $line = '{0} {1}' -f (ConvertFrom-WmiCharArray (Get-Prop $m 'ManufacturerName')), (ConvertFrom-WmiCharArray (Get-Prop $m 'UserFriendlyName'))
    $monSerial = ConvertFrom-WmiCharArray (Get-Prop $m 'SerialNumberID')
    if (-not (Test-Placeholder $monSerial)) { $line += " SN $monSerial" }
    $year = Get-Prop $m 'YearOfManufacture'
    if ($year) { $line += " ($year)" }
    $line
})
$other['battery'] = @(foreach ($b in $batteries) { if ($null -ne $b) { ConvertTo-CleanText (Get-Prop $b 'Name') } })
$other['antivirus'] = @(foreach ($av in $antivirus) { if ($null -ne $av) { ConvertTo-CleanText (Get-Prop $av 'displayName') } })
$other['printers'] = @(foreach ($pr in $printers) { if ($null -ne $pr) { ConvertTo-CleanText (Get-Prop $pr 'Name') } })
$other['scanned_by'] = "$env:USERDOMAIN\$env:USERNAME"
$other['scanned_as_admin'] = Format-YesNo $elevated
$hw['other_information'] = Format-OtherInfo $other

$allSoftware = @(@($software) + @($storeApps) | Where-Object { $null -ne $_ } | Sort-Object -Property name, version)
$softwareRows = @(foreach ($s in $allSoftware) { New-SoftwareRecord -Hardware $hw -Item $s })

$details = [ordered]@{
    computer_system  = @(Select-Plain $cs 'Name', 'DNSHostName', 'Domain', 'PartOfDomain', 'Manufacturer', 'Model', 'SystemFamily', 'SystemSKUNumber', 'UserName', 'PCSystemType', 'TotalPhysicalMemory')
    product          = @(Select-Plain $csp 'Vendor', 'Name', 'Version', 'IdentifyingNumber', 'UUID')
    bios             = @(Select-Plain $bios 'Manufacturer', 'SMBIOSBIOSVersion', 'ReleaseDate', 'SerialNumber', 'SMBIOSMajorVersion', 'SMBIOSMinorVersion')
    enclosure        = @(Select-Plain $enc 'Manufacturer', 'ChassisTypes', 'SerialNumber', 'SMBIOSAssetTag')
    baseboard        = @(Select-Plain $board 'Manufacturer', 'Product', 'Version', 'SerialNumber')
    operating_system = @(Select-Plain $os 'Caption', 'Version', 'BuildNumber', 'OSArchitecture', 'OSLanguage', 'MUILanguages', 'ProductType', 'InstallDate', 'LastBootUpTime', 'RegisteredUser', 'Organization')
    windows_version  = @(Select-Plain $cv 'EditionID', 'DisplayVersion', 'ReleaseId', 'CurrentBuild', 'UBR')
    processors       = @(Select-Plain $cpus 'Name', 'Manufacturer', 'NumberOfCores', 'NumberOfLogicalProcessors', 'MaxClockSpeed', 'SocketDesignation')
    memory_modules   = @(Select-Plain $mem 'DeviceLocator', 'Capacity', 'Speed', 'Manufacturer', 'PartNumber', 'SerialNumber', 'SMBIOSMemoryType')
    disks            = $disks
    volumes          = @(Select-Plain $volumes 'DeviceID', 'VolumeName', 'FileSystem', 'Size', 'FreeSpace')
    video            = @(Select-Plain $gpus 'Name', 'DriverVersion', 'VideoProcessor', 'AdapterRAM', 'CurrentHorizontalResolution', 'CurrentVerticalResolution')
    network_adapters = $adapters
    license          = $license
    ip_config        = @(Select-Plain $ipConfig 'Description', 'MACAddress', 'IPAddress', 'IPSubnet', 'DefaultIPGateway', 'DNSServerSearchOrder', 'DHCPEnabled', 'DNSDomain')
    monitors         = @($other['monitors'])
    batteries        = @(Select-Plain $batteries 'Name', 'DeviceID', 'EstimatedChargeRemaining', 'BatteryStatus')
    printers         = @(Select-Plain $printers 'Name', 'PortName', 'DriverName', 'Network', 'Default', 'Shared')
    antivirus        = @(Select-Plain $antivirus 'displayName', 'productState')
    secure_boot      = $secureBoot
    tpm              = $tpm
    other            = $other
}

$meta = [ordered]@{
    schema          = 2
    tool_version    = $script:AssetScanVersion
    machine_key     = $identity.Key
    collected_utc   = $started.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    collected_local = $started.ToString('yyyy-MM-dd HH:mm:ss zzz')
    collected_by    = "$env:USERDOMAIN\$env:USERNAME"
    elevated        = $elevated
    software_count  = $softwareRows.Count
    warnings        = @($script:Warnings)
    consent         = $consent
    hardware        = $hw
}

$finalDir = Complete-Run -Meta $meta -FinalName "${stamp}_${hostToken}_$($identity.Key)" -Details $details -SoftwareRows $softwareRows
Write-Log "Saved run files ($($softwareRows.Count) programs)"

Write-Host ''
Write-Host '==================== DONE ====================' -ForegroundColor Green
Write-Host ('{0,-15} {1}' -f 'email', $consent.email)
foreach ($k in 'asset_id', 'hostname', 'serial_number', 'type', 'manufacturer', 'model', 'os', 'user_id', 'mac_addr_wifi', 'mac_addr_eth', 'key_type') {
    Write-Host ('{0,-15} {1}' -f $k, $hw[$k])
}
Write-Host ('{0,-15} {1}' -f 'programs', $softwareRows.Count)
if ($script:Warnings.Count) {
    Write-Host ('{0} warning(s), see {1}' -f $script:Warnings.Count, (Join-Path $finalDir 'run.log')) -ForegroundColor Yellow
}
Write-Host "Saved in $finalDir"
exit 0
