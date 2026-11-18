# assetscan

A USB-stick inventory collector for Windows. Each time it runs on a computer, it saves
that computer's hardware and installed programs onto the stick. It then rebuilds two
spreadsheets covering every machine collected so far:

- `hardware.csv` uses the columns of the `asset_manager_v3 - hardware` sheet,
  plus a last column, `other_information`.
- `software.csv` uses the columns of the `asset_manager_v3 - software` sheet,
  plus `other_information`, with one row per installed program per machine.

`other_information` holds everything collected that has no column of its own,
as `name: value | name: value`. Add an `other_information` column at the end of
both sheets so pasted rows line up.
- `software_detail.csv` holds the same programs with hostname, serial number,
  install date and scope, so they can be matched to a machine even when
  `asset_id` is blank.
- `consent.csv` holds one row per run with the user's corporate e-mail and
  whether they accepted the consent window, linked to the device.

It runs on Windows PowerShell 5.1, which is built into Windows 10 and 11, so nothing
is installed on the computer being inventoried. It uses no admin rights and no
network.

## Putting it on the stick

Copy the **contents** of `usb/` to the root of the USB drive:

```
E:\
  QUICK.cmd            double-click on each computer: consent window only, closes itself
  RUN.cmd              same, then asks for asset_id / department / location
  EXPORT.cmd           double-click to make a dated export copy
  assetscan\           the scripts
  assetscan-data\      created on first run
```

## Using it

Every run starts with a consent window (*Termo de ciência*). It shows the
statement and a field for the user's corporate e-mail. **Aceitar** stays
disabled until a valid e-mail is typed. **Recusar**, or closing the window,
stops the run before anything is read from the computer (see
[Consent](#consent)).

**Fastest:** plug the stick in, double-click `QUICK.cmd`, and let the user
accept the window. Unplug once the console window closes itself. It asks
nothing else; `asset_id`, `department` and `location` keep their previous
values, and you fill the rest in the sheet later.

**With questions:**

1. Plug the stick in and double-click `RUN.cmd`. Windows does not autorun
   programs from USB drives (see [Why there is no autorun](#why-there-is-no-autorun)),
   so it must be started by hand.
2. After the consent window, it asks for `asset_id`, `department` and `location`:
   - Press Enter to keep the value shown in brackets. That value comes from the
     last time this machine was collected.
   - Type `-` to clear the value.
3. It takes about 10–60 seconds, then prints a summary. Press a key to close.

Repeat on every computer. To bring the data together, either take
`E:\assetscan-data\hardware.csv`, `software.csv` and `consent.csv` directly (they are always up
to date), or double-click `EXPORT.cmd` for a dated copy in
`assetscan-data\export\<date>\`.

Command-line options (from PowerShell in `E:\assetscan`):

```powershell
.\Collect.ps1 -NoPrompt                                  # unattended, keeps previous asset_id/department/location
.\Collect.ps1 -AssetId PAT-0412 -Department TI -Location "Sala 3"
.\Collect.ps1 -ConsentEmail maria@empresa.com.br         # consent given another way (paper, e-mail): no window, method=parameter
.\Export.ps1 -DataDir E:\assetscan-data, F:\assetscan-data -OutDir C:\inventario   # merge several sticks
.\Export.ps1 -Delimiter ';'                              # for Excel with a pt-BR/European list separator
.\Export.ps1 -History                                    # also hardware_history.csv, one row per run
```

## What is stored

```
assetscan-data\
  hardware.csv              latest state of every machine (hardware sheet columns)
  software.csv              programs of every machine, from its latest run (software sheet columns)
  software_detail.csv       the same programs with hostname, serial, install date, scope
  consent.csv               every consent answer, oldest first, linked to the device
  collections.log           one line per run
  runs\
    20261117T193300Z_PC-RH-04_SN-PF1ABCDE\      one folder per run: <UTC time>_<host>_<machine key>
    20261117T201500Z_PC-RH-07_DECLINED\         a refused consent: meta.json, consent.csv, run.log only
      meta.json             the hardware row + run information (read by the merge)
      details.json          everything collected, in more detail than the sheet holds
      hardware.csv          this run only
      software.csv          this run only (software sheet columns)
      software_detail.csv   this run only (detail; read by the merge)
      consent.csv           this run's consent answer
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
| asset_id | typed by operator; default: previous run | the BIOS asset tag is not used; if one is set it goes to `other_information` |
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
| other_information | everything else, see below | not in the sheet yet |

`other_information` in `hardware.csv` (an entry is left out when it is empty):

| Entry | Source |
|---|---|
| domain, domain_joined, dns_hostname | `Win32_ComputerSystem` (dns_hostname only when it differs from hostname) |
| system_family, system_sku, uuid | `Win32_ComputerSystem`, `Win32_ComputerSystemProduct` |
| chassis_serial, board_serial | enclosure and motherboard serials, when real and different from serial_number |
| bios_asset_tag, bios_vendor | `Win32_SystemEnclosure`, `Win32_BIOS` |
| secure_boot | `HKLM\SYSTEM\CurrentControlSet\Control\SecureBoot\State` |
| tpm | `Win32_Tpm`, only when run as administrator (it needs admin rights) |
| os_edition, os_language, os_install_date, last_boot, registered_owner, organization, time_zone | registry and `Win32_OperatingSystem` |
| license_status, firmware_product_key | Windows activation state; whether an OEM key is stored in the firmware (the key itself is not recorded) |
| memory_modules | slot, size, speed, maker, part number, serial of each module |
| disks | model, bus, serial of each internal disk |
| volumes | each local volume with file system, size and free space |
| network_adapters | name, description, MAC, status, speed of each physical adapter |
| ip_config | IP addresses, gateway, DNS servers, DHCP of each connected adapter |
| gpu_drivers | video card, driver version, current resolution |
| monitors | maker, model, serial and year of each connected monitor (`WmiMonitorID`) |
| battery, antivirus, printers | `Win32_Battery`, Security Center (Windows 10/11 only), `Win32_Printer` |
| scanned_by, scanned_as_admin | the Windows account that ran the tool |

`details.json` in each run folder keeps the same data with one field per value,
for when the cell is not enough.

RAM is reported in binary GB (8 GiB → "8 GB"), as Windows shows it. Disks are
reported in decimal GB (a "256 GB" SSD → "256 GB"), as the manufacturer labels
it. USB disks, including the stick itself, are left out.

### Software

`software.csv` (sheet columns):

| Column | Source |
|---|---|
| ` asset_id` | the machine's `asset_id` after merging (the header has a leading space, as in the sheet) |
| title, publisher, version | `DisplayName`, `Publisher`, `DisplayVersion` |
| department | the machine's `department` after merging |
| usage, url, is_paid, licenses, internal_support_status | left blank, filled in elsewhere |
| last_log_change | same as hardware |
| other_information | hostname, serial_number, install_date, architecture, scope, source, install_location (not in the sheet yet) |

`software_detail.csv`:

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

## Consent

The window appears before anything is read from the computer. Until the user
answers, the only thing the run knows is the computer name, which Windows
gives every program.

| Answer | What happens |
|---|---|
| **Aceitar** (valid e-mail typed) | Collection runs. One `consent.csv` row is written: `accepted=yes`, the e-mail, the date and time. |
| **Recusar** or closing the window | Nothing is collected. One `consent.csv` row is written: `accepted=no`, hostname, date and time, with no e-mail. The run is left out of `hardware.csv` and `software.csv`. |

`consent.csv` columns:

| Column | Content |
|---|---|
| asset_id | the device's `asset_id` after merging, so every consent row of a device follows the current value |
| serial_number, hostname, user_id | from the hardware row of the same run; blank after a refusal, except hostname |
| email | typed in the window |
| accepted | `yes` / `no` |
| consent_date | local date and time of the answer, `yyyy-MM-dd HH:mm:ss` |
| method | `dialog` (the window) or `parameter` (`-ConsentEmail`) |
| statement | the exact text shown, so the record still says what was agreed to if the text changes later |

The table keeps **every** answer, not only the latest. A machine scanned three
times has three rows. Join it to `hardware.csv` on `asset_id`, or on
`serial_number` + `hostname` while `asset_id` is blank.

To accept only addresses of the company's domain, set
`$script:ConsentEmailDomain = 'yourdomain.com.br'` near the top of
`assetscan\AssetScanLib.ps1`. The statement and the window title are also set
there. They are written with `\u` escapes (`\u00e7` = ç, `\u00e3` = ã) because
Windows PowerShell 5.1 would otherwise misread the accents.

The window needs someone sitting at the desktop, so the collector cannot be
pushed to computers through Group Policy or run as SYSTEM. If it is started
without a desktop, it stops with an error and collects nothing.
`-ConsentEmail` is for consent collected another way; it is recorded as
`method=parameter`.

## Why there is no autorun

Since Windows 7, Windows ignores the `open=`/`shellexecute=` lines of
`autorun.inf` on USB flash drives. For drives that are not CD/DVD, only `label`
and `icon` are read. Microsoft backported this to XP and Vista in 2011
(KB971029) because worms such as Conficker spread that way. Windows 10 and 11
keep the same behaviour. Autorun still works for CD/DVD, but even there Windows
10/11 shows an AutoPlay prompt rather than starting the program by itself.
Some USB sticks present a read-only CD-ROM partition to get CD behaviour back.
They still end at the same prompt, and many company security policies block
them.

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
- **Consent is recorded, not verified.** The tool cannot check that the e-mail
  belongs to the person at the keyboard; it only checks the format (and the
  domain, if set).
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
