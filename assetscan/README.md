# assetscan

A USB-stick inventory collector for Windows. Each time it runs on a computer, it saves
that computer's hardware and installed programs onto the stick. It then rebuilds two
spreadsheets covering every machine collected so far:

- `hardware.csv` uses exactly the columns of the `asset_manager_v3 - hardware` sheet.
- `software.csv` holds one row per installed program per machine.

It runs on Windows PowerShell 5.1, which is built into Windows 10 and 11, so nothing
is installed on the computer being inventoried. It uses no admin rights and no
network.

## Putting it on the stick

Copy the **contents** of `usb/` to the root of the USB drive:

```
E:\
  RUN.cmd              double-click on each computer
  EXPORT.cmd           double-click to make a dated export copy
  assetscan\           the scripts
  assetscan-data\      created on first run
```

## Using it

1. Plug the stick in and double-click `RUN.cmd`. Windows does not autorun
   programs from USB drives (it stopped doing so in Windows 7), so it must be
   started by hand.
2. It asks for `asset_id`, `department` and `location`:
   - Press Enter to keep the value shown in brackets. That value comes from the
     last time this machine was collected, or, for `asset_id`, from the BIOS
     asset tag if one is set.
   - Type `-` to clear the value.
3. It takes about 10–60 seconds, then prints a summary. Press a key to close.

Repeat on every computer. To bring the data together, either take
`E:\assetscan-data\hardware.csv` and `software.csv` directly (they are always up
to date), or double-click `EXPORT.cmd` for a dated copy in
`assetscan-data\export\<date>\`.

Command-line options (from PowerShell in `E:\assetscan`):

```powershell
.\Collect.ps1 -NoPrompt                                  # unattended, keeps previous asset_id/department/location
.\Collect.ps1 -AssetId PAT-0412 -Department TI -Location "Sala 3"
.\Export.ps1 -DataDir E:\assetscan-data, F:\assetscan-data -OutDir C:\inventario   # merge several sticks
.\Export.ps1 -Delimiter ';'                              # for Excel with a pt-BR/European list separator
.\Export.ps1 -History                                    # also hardware_history.csv, one row per run
```

## What is stored

```
assetscan-data\
  hardware.csv              latest state of every machine (sheet columns)
  software.csv              programs of every machine, from its latest run
  collections.log           one line per run
  runs\
    20261117T193300Z_PC-RH-04_SN-PF1ABCDE\      one folder per run: <UTC time>_<host>_<machine key>
      meta.json             the hardware row + run information (read by the merge)
      details.json          everything collected, in more detail than the sheet holds
      hardware.csv          this run only
      software.csv          this run only
      run.log               what was queried, how long it took, what failed
```

Runs are never overwritten, so the stick keeps a full history. The two
top-level CSVs are always rebuilt from `runs\`. If they are deleted, or a run
folder is removed by hand, `EXPORT.cmd` (or the next collection) rebuilds them.

A run is first written to a `...partial` folder and only renamed when complete.
If the stick is pulled out mid-run, the leftover `.partial` folder is ignored.

### Identifying a machine

Runs of the same computer are grouped by a *machine key*. The key uses the first
of these that is available:

1. **BIOS serial number** (`SN-...`).
2. **SMBIOS UUID** (`UU-...`).
3. **Hostname** (`HN-...`).

Placeholder serials that some motherboards ship with ("To be filled by O.E.M.",
"Default string", all zeros, and similar) are ignored. This means renaming a PC
does not create a duplicate row, but re-imaging a white-box PC that has no
serial and no usable UUID will.

When the latest run leaves `asset_id`, `department` or `location` blank, the
merge keeps the last non-blank value from an earlier run of the same machine.
Every other column always comes from the latest run.

## Where each column comes from

| Column | Source | Notes |
|---|---|---|
| asset_id | typed by operator; default: previous run, else `Win32_SystemEnclosure.SMBIOSAssetTag` | |
| serial_number | `Win32_BIOS.SerialNumber` → `Win32_ComputerSystemProduct.IdentifyingNumber` → `Win32_SystemEnclosure.SerialNumber` | placeholders discarded |
| mac_addr_wifi | `Get-NetAdapter -Physical`, `NdisPhysicalMedium` = 9 (802.11) | built-in (PCI) adapter preferred |
| mac_addr_eth | same, `NdisPhysicalMedium` = 14 (802.3) | built-in preferred over USB docks |
| mac_addr_extra | every other physical adapter (USB Ethernet, Bluetooth, 2nd NIC) | separated by `; ` |
| type | `Win32_SystemEnclosure.ChassisTypes` → `Win32_ComputerSystem.PCSystemType` | Desktop, Laptop, Tablet, All-in-One, Mini PC, Server, Virtual Machine, Unknown |
| user_id | `Win32_ComputerSystem.UserName` (console user), domain removed | falls back to the account running the script |
| department | typed by operator | |
| model | `Win32_ComputerSystem.Model` | Lenovo: `ComputerSystemProduct.Version (Model)`, e.g. `ThinkPad T480 (20L5S0XX00)` |
| manufacturer | `Win32_ComputerSystem.Manufacturer` | |
| os | `Win32_OperatingSystem.Caption` + `DisplayVersion` + build.UBR + bitness | e.g. `Microsoft Windows 11 Pro 23H2 (build 22631.4460, 64-bit)` |
| extra_hw_info | CPU, RAM, disks, GPU, motherboard, BIOS | `\|`-separated summary; full detail in `details.json` |
| key_type | `SoftwareLicensingProduct.ProductKeyChannel` of Windows | `OEM:DM`, `Retail`, `Volume:MAK`, `Volume:GVLK`, … The key itself is **not** recorded |
| hostname | `Win32_ComputerSystem.Name` | |
| acquired_in, receipt_number, status, approved_to_connect | left blank | cannot be read from the machine |
| ` location` | typed by operator | the header has a leading space, as in the sheet |
| last_log_change | local time of the collection | `yyyy-MM-dd HH:mm:ss` |

RAM is reported in binary GB (8 GiB → "8 GB"), as Windows shows it. Disks are
reported in decimal GB (a "256 GB" SSD → "256 GB"), as the manufacturer labels
it. USB disks, including the stick itself, are left out.

### Software

| Column | Source |
|---|---|
| asset_id, hostname, serial_number | same as the hardware row, for joining |
| name, version, publisher, install_date, install_location | `DisplayName`, `DisplayVersion`, `Publisher`, `InstallDate`, `InstallLocation` |
| architecture | `64-bit` / `32-bit` registry view (blank for per-user installs) |
| scope | `machine`, or `user:<name>` for per-user installs |
| source | `registry` or `store` |
| last_log_change | same as hardware |

Programs are read from the same registry keys that *Settings → Apps* and *Programs
and Features* use:

- `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall`, in both the 64-bit
  and 32-bit (`WOW6432Node`) views.
- `HKEY_USERS\<SID>\...\Uninstall` for each user profile that is loaded.

Entries are skipped when they are hidden (`SystemComponent=1`), when they are
updates of another product (`ParentKeyName`, `ReleaseType`), or when they have
no name. Microsoft Store apps of the current user are added with
`Get-AppxPackage`; framework and system packages are left out.

`Win32_Product` is deliberately **not** used. It is slow, lists only MSI
installs, and querying it makes Windows run a consistency check on every MSI
package, which can trigger repairs.

## Limitations

- **Per-user programs of users who are not logged on are missed.** Their
  registry hive is not loaded. Loading it would need admin rights and would
  modify the machine's state.
- **Store apps are only listed for the user running the script.**
  `-AllUsers` needs admin rights. The list includes Microsoft's in-box Store
  apps (Calculator, Photos and similar).
- **`key_type` is my reading of the column** as the Windows licence channel. If
  it means something else, the line `$hw['key_type'] = ...` in `Collect.ps1` is
  the one to change.
- **ExecutionPolicy.** `RUN.cmd` uses `-ExecutionPolicy Bypass`. That flag does
  not override a policy set by Group Policy (`MachinePolicy`/`UserPolicy`), and
  AppLocker or WDAC can block scripts altogether. On such machines, the script
  has to be signed or allowed by IT.
- **MAC classification relies on the driver.** Some drivers report
  `NdisPhysicalMedium` = 0 (unspecified). Those adapters are classified by name
  (Wi-Fi/Wireless/WLAN vs Ethernet/GbE/LAN) and may land in `mac_addr_extra`.
- **Placeholder detection is a list.** Placeholder serial numbers that are not
  on it are taken as real serials.

## Tests

`tests/Test-AssetScan.ps1` checks the logic that does not need Windows. That
covers placeholder and MAC handling, device type, model, machine key, software
filtering, the CSV layout and header, carrying fields forward, and merging
several runs.

The GitHub workflow `.github/workflows/assetscan.yml` runs these tests on a
Windows runner under both Windows PowerShell 5.1 and PowerShell 7. It then runs
the real collector there twice and checks the result, runs the export, and
starts `RUN.cmd`.

```powershell
./tests/Test-AssetScan.ps1
```
