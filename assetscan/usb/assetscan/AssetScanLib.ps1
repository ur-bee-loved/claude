$script:AssetScanVersion = '1.0.0'

# Internal field name -> column header in the asset_manager_v3 hardware sheet.
# The sheet's header really is " location", with a leading space.
$script:HardwareHeaders = [ordered]@{
    asset_id            = 'asset_id'
    serial_number       = 'serial_number'
    mac_addr_wifi       = 'mac_addr_wifi'
    mac_addr_eth        = 'mac_addr_eth'
    mac_addr_extra      = 'mac_addr_extra'
    type                = 'type'
    user_id             = 'user_id'
    department          = 'department'
    model               = 'model'
    manufacturer        = 'manufacturer'
    os                  = 'os'
    extra_hw_info       = 'extra_hw_info'
    key_type            = 'key_type'
    hostname            = 'hostname'
    acquired_in         = 'acquired_in'
    receipt_number      = 'receipt_number'
    location            = ' location'
    status              = 'status'
    approved_to_connect = 'approved_to_connect'
    last_log_change     = 'last_log_change'
}

$script:SoftwareColumns = @(
    'asset_id', 'hostname', 'serial_number', 'name', 'version', 'publisher',
    'install_date', 'architecture', 'scope', 'source', 'install_location', 'last_log_change'
)

# Fields typed by the operator; a blank value in a newer run keeps the last non-blank one.
$script:OperatorFields = @('asset_id', 'department', 'location')

$script:ChassisLabels = @{
    3 = 'Desktop'; 4 = 'Desktop'; 5 = 'Desktop'; 6 = 'Desktop'; 7 = 'Desktop'
    15 = 'Desktop'; 16 = 'Desktop'; 24 = 'Desktop'
    8 = 'Laptop'; 9 = 'Laptop'; 10 = 'Laptop'; 14 = 'Laptop'; 31 = 'Laptop'; 32 = 'Laptop'
    11 = 'Tablet'; 30 = 'Tablet'
    13 = 'All-in-One'
    34 = 'Mini PC'; 35 = 'Mini PC'; 36 = 'Mini PC'
    17 = 'Server'; 23 = 'Server'; 28 = 'Server'
}

$script:PcSystemTypeLabels = @{ 1 = 'Desktop'; 2 = 'Laptop'; 3 = 'Desktop'; 4 = 'Server'; 5 = 'Server'; 7 = 'Server'; 8 = 'Tablet' }

$script:BogusUuids = @('03000200-0400-0500-0006-000700080009')

$script:LogPath = $null
$script:Warnings = New-Object System.Collections.Generic.List[string]

function Get-Prop {
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    if ($Object -is [System.Collections.IDictionary]) {
        if ($Object.Contains($Name)) { return $Object[$Name] }
        return $null
    }
    $p = $Object.PSObject.Properties[$Name]
    if ($p) { return $p.Value }
    return $null
}

function ConvertTo-CleanText {
    param($Value)
    if ($null -eq $Value) { return '' }
    $s = [string]$Value
    $s = $s -replace '[\x00-\x1F]', ' '
    return ($s -replace '\s+', ' ').Trim()
}

function Test-Placeholder {
    param($Value)
    $v = ConvertTo-CleanText $Value
    if ($v -eq '') { return $true }
    $rx = '^(?i)(to be filled by o\.?e\.?m\.?|default string|system serial number|chassis serial number|' +
          'base board serial number|system product name|not specified|not applicable|not available|' +
          'none|n/?a|invalid|unknown|serial ?number|o\.?e\.?m\.?|0123456789|123456789|1234567890)$'
    if ($v -match $rx) { return $true }
    $compact = $v -replace '[\s\-\.:]', ''
    if ($compact -match '^(.)\1*$') { return $true }
    return $false
}

function Get-SafeToken {
    param([string]$Value)
    $t = ($Value -replace '[^A-Za-z0-9\-]', '').ToUpperInvariant()
    if ($t.Length -gt 48) { $t = $t.Substring(0, 48) }
    if ($t -eq '') { $t = 'UNKNOWN' }
    return $t
}

function ConvertTo-Mac {
    param($Value)
    $hex = ([string]$Value -replace '[^0-9A-Fa-f]', '').ToUpperInvariant()
    if ($hex.Length -ne 12 -or $hex -match '^(0{12}|F{12})$') { return '' }
    return [regex]::Replace($hex, '(..)(?!$)', '$1:')
}

function Format-InstallDate {
    param($Value)
    $s = ConvertTo-CleanText $Value
    if ($s -match '^\d{8}$') {
        $dt = [datetime]::MinValue
        $ok = [datetime]::TryParseExact($s, 'yyyyMMdd', [Globalization.CultureInfo]::InvariantCulture,
            [Globalization.DateTimeStyles]::None, [ref]$dt)
        if ($ok) { return $dt.ToString('yyyy-MM-dd') }
    }
    return $s
}

function Get-DeviceType {
    param($ChassisTypes, $PCSystemType, [string]$Manufacturer, [string]$Model)
    if ("$Manufacturer $Model" -match '(?i)vmware|virtualbox|virtual machine|kvm|qemu|xen|hyper-v|parallels|bochs') {
        return 'Virtual Machine'
    }
    foreach ($c in @($ChassisTypes)) {
        if ($null -eq $c) { continue }
        $n = [int]$c
        if ($script:ChassisLabels.ContainsKey($n)) { return $script:ChassisLabels[$n] }
    }
    if ($null -ne $PCSystemType -and "$PCSystemType" -ne '') {
        $n = [int]$PCSystemType
        if ($script:PcSystemTypeLabels.ContainsKey($n)) { return $script:PcSystemTypeLabels[$n] }
    }
    return 'Unknown'
}

function Get-ModelName {
    param([string]$Manufacturer, [string]$Model, [string]$Version)
    $m = ConvertTo-CleanText $Model
    $v = ConvertTo-CleanText $Version
    if ($Manufacturer -match '(?i)^lenovo' -and -not (Test-Placeholder $v) -and $v -ne $m) {
        if ($m -eq '') { return $v }
        return "$v ($m)"
    }
    return $m
}

function Get-MachineIdentity {
    param([string]$BiosSerial, [string]$ProductSerial, [string]$EnclosureSerial, [string]$Uuid, [string]$Hostname)
    $serial = ''
    foreach ($c in @($BiosSerial, $ProductSerial, $EnclosureSerial)) {
        if (-not (Test-Placeholder $c)) { $serial = ConvertTo-CleanText $c; break }
    }
    $u = ConvertTo-CleanText $Uuid
    if ($serial -ne '') {
        $key = 'SN-' + (Get-SafeToken $serial)
    } elseif (-not (Test-Placeholder $u) -and $script:BogusUuids -notcontains $u) {
        $key = 'UU-' + (Get-SafeToken $u)
    } else {
        $key = 'HN-' + (Get-SafeToken $Hostname)
    }
    return [pscustomobject]@{ Serial = $serial; Key = $key }
}

# Adapters: objects with Name, Description, Mac, Medium (NdisPhysicalMedium), PnpId.
# Medium 9/1 = Wi-Fi, 14 = Ethernet (802.3), 0 = unspecified (classified by name).
function Select-AdapterMacs {
    param([object[]]$Adapters)
    $wifiRx = '(?i)wi-?fi|wireless|wlan|802\.11'
    $ethRx = '(?i)ethernet|gbe|gigabit|family controller|network connection|\blan\b'
    $seen = @{}
    $list = foreach ($a in @($Adapters)) {
        if ($null -eq $a) { continue }
        $mac = ConvertTo-Mac (Get-Prop $a 'Mac')
        if ($mac -eq '' -or $seen.ContainsKey($mac)) { continue }
        $seen[$mac] = $true
        $mediumRaw = Get-Prop $a 'Medium'
        $medium = 0
        if ($null -ne $mediumRaw -and "$mediumRaw" -ne '') { $medium = [int]$mediumRaw }
        $text = '{0} {1}' -f (Get-Prop $a 'Name'), (Get-Prop $a 'Description')
        $kind = 'extra'
        if ($medium -eq 9 -or $medium -eq 1 -or ($medium -eq 0 -and $text -match $wifiRx)) {
            $kind = 'wifi'
        } elseif ($medium -eq 14 -or ($medium -eq 0 -and $text -match $ethRx)) {
            $kind = 'eth'
        }
        [pscustomobject]@{
            Mac     = $mac
            Kind    = $kind
            Builtin = ([string](Get-Prop $a 'PnpId')) -like 'PCI\*'
            Name    = [string](Get-Prop $a 'Name')
        }
    }
    $sorted = @($list | Where-Object { $null -ne $_ } | Sort-Object -Property @{ Expression = 'Builtin'; Descending = $true }, @{ Expression = 'Name'; Descending = $false })
    $wifi = @($sorted | Where-Object { $_.Kind -eq 'wifi' } | Select-Object -First 1)
    $eth = @($sorted | Where-Object { $_.Kind -eq 'eth' } | Select-Object -First 1)
    $used = @($wifi + $eth | ForEach-Object { $_.Mac })
    $extra = @($sorted | Where-Object { $used -notcontains $_.Mac } | ForEach-Object { $_.Mac })
    return [pscustomobject]@{
        Wifi  = if ($wifi.Count) { $wifi[0].Mac } else { '' }
        Eth   = if ($eth.Count) { $eth[0].Mac } else { '' }
        Extra = $extra -join '; '
    }
}

function Format-DiskSummary {
    param($Disk)
    $model = ConvertTo-CleanText (Get-Prop $Disk 'Model')
    $media = ConvertTo-CleanText (Get-Prop $Disk 'Media')
    $bus = ConvertTo-CleanText (Get-Prop $Disk 'Bus')
    $size = Get-Prop $Disk 'SizeBytes'
    $bits = @()
    if ($bus -eq 'NVMe' -and $media -eq 'SSD') { $bits += 'NVMe SSD' } elseif ($media) { $bits += $media }
    if ($size) { $bits += ('{0} GB' -f [math]::Round([double]$size / 1e9)) }
    if ($bits.Count) { return "$model ($($bits -join ', '))" }
    return $model
}

function Format-ExtraHwInfo {
    param($Cpus, $MemoryModules, $TotalMemory, $Disks, $Gpus, $Board, $Bios)
    $parts = New-Object System.Collections.Generic.List[string]

    $cpuText = @(foreach ($c in @($Cpus)) {
        if ($null -eq $c) { continue }
        $n = ConvertTo-CleanText (Get-Prop $c 'Name')
        $cores = Get-Prop $c 'NumberOfCores'
        $threads = Get-Prop $c 'NumberOfLogicalProcessors'
        if ($cores -and $threads) { "$n (${cores}C/${threads}T)" } else { $n }
    }) -join ' + '
    if ($cpuText) { $parts.Add("CPU: $cpuText") }

    [uint64]$bytes = 0
    $modCount = 0
    foreach ($m in @($MemoryModules)) {
        $cap = Get-Prop $m 'Capacity'
        if ($cap) { $bytes += [uint64]$cap; $modCount++ }
    }
    if ($bytes -eq 0 -and $TotalMemory) { $bytes = [uint64]$TotalMemory }
    if ($bytes -gt 0) {
        $ram = 'RAM: {0} GB' -f [math]::Round($bytes / 1GB)
        if ($modCount -eq 1) { $ram += ' (1 module)' } elseif ($modCount -gt 1) { $ram += " ($modCount modules)" }
        $parts.Add($ram)
    }

    $diskText = @(foreach ($d in @($Disks)) { if ($null -ne $d) { Format-DiskSummary $d } }) -join ' + '
    if ($diskText) { $parts.Add("Disk: $diskText") }

    $skipGpu = '(?i)microsoft basic display|microsoft remote display|remote desktop|mirage driver|dameware|citrix indirect|parsec virtual|virtual display'
    $gpuAll = @(foreach ($g in @($Gpus)) {
        $n = ConvertTo-CleanText (Get-Prop $g 'Name')
        if ($n -and $n -notmatch $skipGpu) { $n }
    })
    $gpuNames = @($gpuAll | Select-Object -Unique)
    if ($gpuNames.Count) { $parts.Add('GPU: ' + ($gpuNames -join ' + ')) }

    $boardText = ('{0} {1}' -f (ConvertTo-CleanText (Get-Prop $Board 'Manufacturer')), (ConvertTo-CleanText (Get-Prop $Board 'Product'))).Trim()
    if ($boardText) { $parts.Add("Board: $boardText") }

    $biosVer = ConvertTo-CleanText (Get-Prop $Bios 'SMBIOSBIOSVersion')
    $biosDate = Get-Prop $Bios 'ReleaseDate'
    if ($biosVer) {
        if ($biosDate -is [datetime]) { $biosVer += ' (' + $biosDate.ToString('yyyy-MM-dd') + ')' }
        $parts.Add("BIOS: $biosVer")
    }
    return ($parts -join ' | ')
}

function ConvertFrom-UninstallEntry {
    param([hashtable]$Values, [string]$Architecture, [string]$Scope)
    $name = ConvertTo-CleanText $Values['DisplayName']
    if ($name -eq '') { return }
    if ("$($Values['SystemComponent'])" -eq '1') { return }
    if ((ConvertTo-CleanText $Values['ParentKeyName']) -ne '') { return }
    if ((ConvertTo-CleanText $Values['ReleaseType']) -match '(?i)^(update|hotfix|security update|update rollup|service pack)$') { return }
    return [pscustomobject][ordered]@{
        name             = $name
        version          = ConvertTo-CleanText $Values['DisplayVersion']
        publisher        = ConvertTo-CleanText $Values['Publisher']
        install_date     = Format-InstallDate $Values['InstallDate']
        architecture     = $Architecture
        scope            = $Scope
        source           = 'registry'
        install_location = ConvertTo-CleanText $Values['InstallLocation']
    }
}

function Remove-DuplicateSoftware {
    param([object[]]$Items)
    $seen = @{}
    foreach ($i in @($Items)) {
        if ($null -eq $i) { continue }
        $k = ('{0}|{1}|{2}|{3}' -f $i.name, $i.version, $i.architecture, $i.scope).ToLowerInvariant()
        if ($seen.ContainsKey($k)) { continue }
        $seen[$k] = $true
        $i
    }
}

function New-SoftwareRecord {
    param($Hardware, $Item)
    $o = [ordered]@{}
    foreach ($c in $script:SoftwareColumns) { $o[$c] = '' }
    $o['asset_id'] = [string](Get-Prop $Hardware 'asset_id')
    $o['hostname'] = [string](Get-Prop $Hardware 'hostname')
    $o['serial_number'] = [string](Get-Prop $Hardware 'serial_number')
    foreach ($c in 'name', 'version', 'publisher', 'install_date', 'architecture', 'scope', 'source', 'install_location') {
        $o[$c] = [string](Get-Prop $Item $c)
    }
    $o['last_log_change'] = [string](Get-Prop $Hardware 'last_log_change')
    return [pscustomobject]$o
}

function ConvertTo-HardwareRecord {
    param($Hardware)
    $o = [ordered]@{}
    foreach ($k in $script:HardwareHeaders.Keys) {
        $o[$script:HardwareHeaders[$k]] = [string](Get-Prop $Hardware $k)
    }
    return [pscustomobject]$o
}

function New-EmptyHardware {
    $h = [ordered]@{}
    foreach ($k in $script:HardwareHeaders.Keys) { $h[$k] = '' }
    return $h
}

function Write-TextFileAtomic {
    param([string]$Path, [string[]]$Lines, [bool]$Bom = $true)
    $dir = Split-Path -Parent $Path
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    $tmp = "$Path.tmp"
    [IO.File]::WriteAllLines($tmp, $Lines, (New-Object System.Text.UTF8Encoding($Bom)))
    if (Test-Path -LiteralPath $Path) {
        try {
            [IO.File]::Replace($tmp, $Path, [NullString]::Value)
        } catch {
            Remove-Item -LiteralPath $Path -Force
            [IO.File]::Move($tmp, $Path)
        }
    } else {
        [IO.File]::Move($tmp, $Path)
    }
}

function Write-CsvFile {
    param([string]$Path, [string[]]$Columns, [object[]]$Rows, [string]$Delimiter = ',')
    $rows = @($Rows | Where-Object { $null -ne $_ })
    if ($rows.Count) {
        $lines = @($rows | ConvertTo-Csv -NoTypeInformation -Delimiter $Delimiter)
    } else {
        $lines = @(($Columns | ForEach-Object { '"' + $_ + '"' }) -join $Delimiter)
    }
    Write-TextFileAtomic -Path $Path -Lines $lines -Bom $true
}

function Write-JsonFile {
    param([string]$Path, $Object, [int]$Depth = 6)
    $json = $Object | ConvertTo-Json -Depth $Depth
    [IO.File]::WriteAllText($Path, $json, (New-Object System.Text.UTF8Encoding($false)))
}

function Read-JsonFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try {
        return ([IO.File]::ReadAllText($Path) | ConvertFrom-Json)
    } catch {
        Write-Warning "Unreadable JSON, skipped: $Path"
        return $null
    }
}

function Save-RunFiles {
    param([string]$RunDir, $Meta, $Details, [object[]]$SoftwareRows)
    if (-not (Test-Path -LiteralPath $RunDir)) { New-Item -ItemType Directory -Force -Path $RunDir | Out-Null }
    Write-JsonFile -Path (Join-Path $RunDir 'meta.json') -Object $Meta
    if ($null -ne $Details) { Write-JsonFile -Path (Join-Path $RunDir 'details.json') -Object $Details -Depth 8 }
    $hwRecord = ConvertTo-HardwareRecord (Get-Prop $Meta 'hardware')
    Write-CsvFile -Path (Join-Path $RunDir 'hardware.csv') -Columns @($script:HardwareHeaders.Values) -Rows @($hwRecord)
    Write-CsvFile -Path (Join-Path $RunDir 'software.csv') -Columns $script:SoftwareColumns -Rows $SoftwareRows
}

function Read-RunMetas {
    param([string[]]$DataDirs)
    foreach ($dir in @($DataDirs)) {
        $runs = Join-Path $dir 'runs'
        if (-not (Test-Path -LiteralPath $runs)) { continue }
        foreach ($f in @(Get-ChildItem -LiteralPath $runs -Directory | Where-Object { $_.Name -notlike '*.partial' })) {
            $m = Read-JsonFile (Join-Path $f.FullName 'meta.json')
            if ($null -eq $m -or -not (Get-Prop $m 'machine_key')) { continue }
            $m | Add-Member -NotePropertyName run_dir -NotePropertyValue $f.FullName -Force
            $m
        }
    }
}

function Merge-Runs {
    param([object[]]$Metas)
    $groups = @(@($Metas) | Where-Object { $null -ne $_ } | Group-Object -Property { $_.machine_key })
    foreach ($g in $groups) {
        $runs = @($g.Group | Sort-Object -Property { $_.collected_utc })
        $latest = $runs[$runs.Count - 1]
        $hw = New-EmptyHardware
        foreach ($k in @($script:HardwareHeaders.Keys)) { $hw[$k] = [string](Get-Prop $latest.hardware $k) }
        foreach ($f in $script:OperatorFields) {
            if ($hw[$f] -ne '') { continue }
            for ($i = $runs.Count - 2; $i -ge 0; $i--) {
                $v = [string](Get-Prop $runs[$i].hardware $f)
                if ($v -ne '') { $hw[$f] = $v; break }
            }
        }
        [pscustomobject]@{
            machine_key   = $g.Name
            run_dir       = [string](Get-Prop $latest 'run_dir')
            collected_utc = [string]$latest.collected_utc
            run_count     = $runs.Count
            hardware      = $hw
        }
    }
}

function Update-MasterFiles {
    param([string[]]$DataDirs, [string]$OutDir, [string]$Delimiter = ',', [switch]$History)
    $metas = @(Read-RunMetas -DataDirs $DataDirs)
    $merged = @(Merge-Runs $metas | Sort-Object -Property @{ Expression = { $_.hardware['hostname'] } }, machine_key)
    if (-not (Test-Path -LiteralPath $OutDir)) { New-Item -ItemType Directory -Force -Path $OutDir | Out-Null }

    $hwRows = @(foreach ($m in $merged) { ConvertTo-HardwareRecord $m.hardware })
    Write-CsvFile -Path (Join-Path $OutDir 'hardware.csv') -Columns @($script:HardwareHeaders.Values) -Rows $hwRows -Delimiter $Delimiter

    $swRows = New-Object System.Collections.Generic.List[object]
    foreach ($m in $merged) {
        $p = Join-Path $m.run_dir 'software.csv'
        if (-not (Test-Path -LiteralPath $p)) { continue }
        foreach ($r in @(Import-Csv -LiteralPath $p -Encoding UTF8)) {
            $r.asset_id = $m.hardware['asset_id']
            $swRows.Add($r)
        }
    }
    Write-CsvFile -Path (Join-Path $OutDir 'software.csv') -Columns $script:SoftwareColumns -Rows $swRows.ToArray() -Delimiter $Delimiter

    if ($History) {
        $histRows = @($metas | Sort-Object -Property { $_.collected_utc } | ForEach-Object { ConvertTo-HardwareRecord $_.hardware })
        Write-CsvFile -Path (Join-Path $OutDir 'hardware_history.csv') -Columns @($script:HardwareHeaders.Values) -Rows $histRows -Delimiter $Delimiter
    }

    return [pscustomobject]@{
        Machines     = $merged.Count
        Runs         = $metas.Count
        SoftwareRows = $swRows.Count
        OutDir       = $OutDir
    }
}

function Write-Log {
    param([string]$Message, [string]$Level = 'INFO')
    $line = '{0} {1,-5} {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    if ($script:LogPath) {
        try {
            [IO.File]::AppendAllText($script:LogPath, $line + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
        } catch { }
    }
    switch ($Level) {
        'WARN' { Write-Host $line -ForegroundColor Yellow }
        'ERROR' { Write-Host $line -ForegroundColor Red }
        default { Write-Host $line }
    }
}

function Invoke-Section {
    param([string]$Name, [scriptblock]$Block)
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try {
        $r = & $Block
        Write-Log ('{0} ({1:N1}s)' -f $Name, $sw.Elapsed.TotalSeconds)
        return $r
    } catch {
        $msg = "${Name}: $($_.Exception.Message)"
        $script:Warnings.Add($msg)
        Write-Log $msg 'WARN'
        return $null
    }
}

function Select-Plain {
    param($Objects, [string[]]$Properties)
    foreach ($o in @($Objects)) {
        if ($null -eq $o) { continue }
        $h = [ordered]@{}
        foreach ($p in $Properties) {
            $v = Get-Prop $o $p
            if ($v -is [datetime]) { $v = $v.ToString('yyyy-MM-ddTHH:mm:ss') }
            $h[$p] = $v
        }
        [pscustomobject]$h
    }
}

# ---- Windows-only collectors below; everything above is plain logic and is unit-tested.

function Get-CimSafe {
    param([string]$Class, [string]$Namespace = 'root\cimv2', [string]$Filter)
    $p = @{ ClassName = $Class; Namespace = $Namespace; ErrorAction = 'Stop' }
    if ($Filter) { $p['Filter'] = $Filter }
    return @(Get-CimInstance @p)
}

function Get-AdapterInventory {
    $out = @()
    if (Get-Command Get-NetAdapter -ErrorAction SilentlyContinue) {
        foreach ($a in @(Get-NetAdapter -Physical -ErrorAction Stop)) {
            $out += [pscustomobject]@{
                Name        = [string](Get-Prop $a 'Name')
                Description = [string](Get-Prop $a 'InterfaceDescription')
                Mac         = [string](Get-Prop $a 'MacAddress')
                Medium      = Get-Prop $a 'NdisPhysicalMedium'
                PnpId       = [string](Get-Prop $a 'PnPDeviceID')
                Status      = [string](Get-Prop $a 'Status')
                LinkSpeed   = [string](Get-Prop $a 'LinkSpeed')
            }
        }
        return $out
    }
    foreach ($a in (Get-CimSafe -Class Win32_NetworkAdapter -Filter 'PhysicalAdapter = TRUE')) {
        $out += [pscustomobject]@{
            Name        = [string](Get-Prop $a 'NetConnectionID')
            Description = [string](Get-Prop $a 'Name')
            Mac         = [string](Get-Prop $a 'MACAddress')
            Medium      = 0
            PnpId       = [string](Get-Prop $a 'PNPDeviceID')
            Status      = [string](Get-Prop $a 'NetConnectionStatus')
            LinkSpeed   = [string](Get-Prop $a 'Speed')
        }
    }
    return $out
}

function Get-DiskInventory {
    $mediaNames = @{ 3 = 'HDD'; 4 = 'SSD'; 5 = 'SCM' }
    $busNames = @{ 1 = 'SCSI'; 2 = 'ATAPI'; 3 = 'ATA'; 7 = 'USB'; 8 = 'RAID'; 10 = 'SAS'; 11 = 'SATA'; 12 = 'SD'; 13 = 'MMC'; 14 = 'Virtual'; 17 = 'NVMe'; 18 = 'SCM'; 19 = 'UFS' }
    $out = @()
    try {
        foreach ($d in (Get-CimSafe -Class MSFT_PhysicalDisk -Namespace 'root\Microsoft\Windows\Storage')) {
            $bus = [int](Get-Prop $d 'BusType')
            if ($bus -eq 7) { continue }
            $media = [int](Get-Prop $d 'MediaType')
            $out += [pscustomobject]@{
                Model     = ConvertTo-CleanText (Get-Prop $d 'FriendlyName')
                Serial    = ConvertTo-CleanText (Get-Prop $d 'SerialNumber')
                Media     = if ($mediaNames.ContainsKey($media)) { $mediaNames[$media] } else { '' }
                Bus       = if ($busNames.ContainsKey($bus)) { $busNames[$bus] } else { "$bus" }
                SizeBytes = Get-Prop $d 'Size'
            }
        }
        return $out
    } catch {
        Write-Log "MSFT_PhysicalDisk unavailable, using Win32_DiskDrive: $($_.Exception.Message)" 'WARN'
    }
    foreach ($d in (Get-CimSafe -Class Win32_DiskDrive)) {
        if ((Get-Prop $d 'InterfaceType') -eq 'USB' -or (Get-Prop $d 'MediaType') -match '(?i)removable|external') { continue }
        $out += [pscustomobject]@{
            Model     = ConvertTo-CleanText (Get-Prop $d 'Model')
            Serial    = ConvertTo-CleanText (Get-Prop $d 'SerialNumber')
            Media     = ''
            Bus       = [string](Get-Prop $d 'InterfaceType')
            SizeBytes = Get-Prop $d 'Size'
        }
    }
    return $out
}

function Get-WindowsLicense {
    $statusNames = @{ 0 = 'Unlicensed'; 1 = 'Licensed'; 2 = 'OOBGrace'; 3 = 'OOTGrace'; 4 = 'NonGenuineGrace'; 5 = 'Notification'; 6 = 'ExtendedGrace' }
    $filter = "ApplicationID = '55c92734-d682-4d71-983e-d6ec3f16059f' AND PartialProductKey IS NOT NULL"
    $products = @(Get-CimSafe -Class SoftwareLicensingProduct -Filter $filter)
    $lic = @($products | Sort-Object -Property { [int](Get-Prop $_ 'LicenseStatus') -ne 1 } | Select-Object -First 1)
    $firmwareKey = $false
    try {
        $svc = @(Get-CimSafe -Class SoftwareLicensingService) | Select-Object -First 1
        $firmwareKey = -not [string]::IsNullOrEmpty([string](Get-Prop $svc 'OA3xOriginalProductKey'))
    } catch { }
    if (-not $lic.Count) {
        return [pscustomobject]@{ Channel = ''; Status = ''; Description = ''; FirmwareKeyPresent = $firmwareKey }
    }
    $l = $lic[0]
    $desc = ConvertTo-CleanText (Get-Prop $l 'Description')
    $channel = ConvertTo-CleanText (Get-Prop $l 'ProductKeyChannel')
    if ($channel -eq '' -and $desc -match ',\s*([A-Za-z0-9_:]+)\s+channel') { $channel = $Matches[1] }
    $st = Get-Prop $l 'LicenseStatus'
    $stName = ''
    if ($null -ne $st -and $statusNames.ContainsKey([int]$st)) { $stName = $statusNames[[int]$st] }
    return [pscustomobject]@{
        Channel            = $channel
        Status             = $stName
        Description        = $desc
        FirmwareKeyPresent = $firmwareKey
    }
}

function Read-UninstallKey {
    param([Microsoft.Win32.RegistryKey]$Base, [string]$Path, [string]$Architecture, [string]$Scope)
    $key = $null
    try { $key = $Base.OpenSubKey($Path) } catch { return }
    if ($null -eq $key) { return }
    try {
        foreach ($name in $key.GetSubKeyNames()) {
            $sub = $null
            try {
                $sub = $key.OpenSubKey($name)
                if ($null -eq $sub) { continue }
                $vals = @{}
                foreach ($v in 'DisplayName', 'DisplayVersion', 'Publisher', 'InstallDate', 'InstallLocation', 'SystemComponent', 'ParentKeyName', 'ReleaseType') {
                    $vals[$v] = $sub.GetValue($v)
                }
                ConvertFrom-UninstallEntry -Values $vals -Architecture $Architecture -Scope $Scope
            } catch {
            } finally {
                if ($sub) { $sub.Close() }
            }
        }
    } finally {
        $key.Close()
    }
}

function Resolve-SidName {
    param([string]$Sid)
    try {
        $acct = ([System.Security.Principal.SecurityIdentifier]$Sid).Translate([System.Security.Principal.NTAccount]).Value
        return $acct.Split('\')[-1]
    } catch {
        return $Sid
    }
}

function Get-InstalledSoftware {
    $path = 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'
    $items = New-Object System.Collections.Generic.List[object]
    if ([Environment]::Is64BitOperatingSystem) {
        $views = @(
            @{ View = [Microsoft.Win32.RegistryView]::Registry64; Arch = '64-bit' },
            @{ View = [Microsoft.Win32.RegistryView]::Registry32; Arch = '32-bit' }
        )
    } else {
        $views = @(@{ View = [Microsoft.Win32.RegistryView]::Default; Arch = '32-bit' })
    }
    foreach ($v in $views) {
        $base = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::LocalMachine, $v.View)
        try {
            foreach ($e in @(Read-UninstallKey -Base $base -Path $path -Architecture $v.Arch -Scope 'machine')) { if ($e) { $items.Add($e) } }
        } finally { $base.Close() }
    }
    $users = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::Users, [Microsoft.Win32.RegistryView]::Default)
    try {
        foreach ($sid in $users.GetSubKeyNames()) {
            if ($sid -notmatch '^S-1-5-21-[\d-]+$') { continue }
            $scope = 'user:' + (Resolve-SidName $sid)
            foreach ($e in @(Read-UninstallKey -Base $users -Path "$sid\$path" -Architecture '' -Scope $scope)) { if ($e) { $items.Add($e) } }
        }
    } finally { $users.Close() }
    return @(Remove-DuplicateSoftware $items.ToArray())
}

function Get-StoreApps {
    if (-not (Get-Command Get-AppxPackage -ErrorAction SilentlyContinue)) { return @() }
    $out = @()
    foreach ($p in @(Get-AppxPackage -ErrorAction Stop)) {
        if ((Get-Prop $p 'IsFramework') -eq $true) { continue }
        if ((Get-Prop $p 'IsResourcePackage') -eq $true) { continue }
        if ([string](Get-Prop $p 'SignatureKind') -ne 'Store') { continue }
        $pub = [string](Get-Prop $p 'Publisher')
        if ($pub -match 'CN=([^,]+)') { $pub = $Matches[1] }
        $out += [pscustomobject][ordered]@{
            name             = [string](Get-Prop $p 'Name')
            version          = [string](Get-Prop $p 'Version')
            publisher        = $pub
            install_date     = ''
            architecture     = [string](Get-Prop $p 'Architecture')
            scope            = 'user:' + $env:USERNAME
            source           = 'store'
            install_location = ''
        }
    }
    return $out
}

function Test-IsElevated {
    try {
        $p = New-Object System.Security.Principal.WindowsPrincipal([System.Security.Principal.WindowsIdentity]::GetCurrent())
        return $p.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
    } catch {
        return $false
    }
}
