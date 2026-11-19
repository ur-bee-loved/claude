# assetscan

A USB-stick inventory collector for Windows. Each time it runs on a computer, it saves
that computer's hardware and installed programs onto the stick. It then rebuilds two
spreadsheets covering every machine collected so far:

- `hardware.csv` uses exactly the columns of the `asset_manager_v3 - hardware` sheet.
  Everything else collected about the machine goes to `extra_hw_info.csv` and
  `other_information.csv` in each run folder, one item per column.
- `software.csv` uses the columns of the `asset_manager_v3 - software` sheet,
  plus `other_information`, with one row per installed program per machine.
  That cell holds the program's details as `name: value | name: value`; add an
  `other_information` column at the end of the software sheet so pasted rows line up.
- `software_detail.csv` holds the same programs with hostname, serial number,
  install date and scope, so they can be matched to a machine even when
  `asset_id` is blank.
- `consent.csv` holds one row per run: the user's corporate e-mail and whether
  they accepted the consent window (or `skipped`, for an unattended run), linked
  to the device.

It runs on Windows PowerShell 5.1, which is built into Windows 10 and 11, so nothing
is installed on the computer being inventoried. It uses no admin rights and no
network.

## Putting it on the stick

Copy the **contents** of `usb/` to the root of the USB drive:

```
E:\
  autorun.inf          label, and an autorun attempt where the hardware still allows it (see Autorun)
  RUN.cmd              double-click on each computer: consent, then a results window
  QUICK.cmd            unattended: no consent, no results window; the console closes itself after 5 seconds
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

1. Plug the stick in and double-click `RUN.cmd`. On most machines Windows
   will not start it on its own (see [Autorun](#autorun)), so open the drive
   and double-click it.
2. Let the user accept the consent window.
3. After 10–60 seconds a results window (*Aquisição concluída*) lists what was
   collected and where it was saved. It closes only with **Finalizar aquisição**;
   the console window closes with it. Then unplug the stick.

If the user refuses consent, a *Coleta recusada* window says nothing was
collected, and also closes with **Finalizar aquisição**. If the run fails, the
console window stays open with the error until a key is pressed.

**Fastest / unattended:** `QUICK.cmd`. It collects the same data but shows
**no consent window and no results window** — it just runs, prints a short
summary, and closes itself 5 seconds later. This is the launcher `autorun.inf`
points at, so wherever autorun still fires (see [Autorun](#autorun)) the scan
starts on its own. Because it skips the notice, use it only on company-owned
machines where that is acceptable; the run is still recorded in `consent.csv`
with `method=skipped`.

Neither one asks anything else. `asset_id`, `department` and `location` keep
the values from the last time this machine was collected (blank the first
time); fill them in the sheet later, or pass them on the command line.

Repeat on every computer. To bring the data together, either take
`E:\assetscan-data\hardware.csv`, `software.csv` and `consent.csv` directly (they are always up
to date), or double-click `EXPORT.cmd` for a dated copy in
`assetscan-data\export\<date>\`.

Command-line options (from PowerShell in `E:\assetscan`):

```powershell
.\Collect.ps1 -AssetId PAT-0412 -Department TI -Location "Sala 3"
.\Collect.ps1 -NoResultDialog                            # results in the console only, no window to close (scripts, remote runs)
.\Collect.ps1 -SkipConsent                              # unattended: collect with no consent window, recorded as method=skipped
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
      extra_hw_info.csv     this run only: CPU, RAM, disk, GPU, board, BIOS in separate columns
      other_information.csv this run only: everything else collected, one item per column
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
| asset_id | previous run, or `-AssetId` | the BIOS asset tag is not used; if one is set it goes to `bios_asset_tag` in `other_information.csv` |
| serial_number | `Win32_BIOS.SerialNumber` → `Win32_ComputerSystemProduct.IdentifyingNumber` → `Win32_SystemEnclosure.SerialNumber` | placeholders discarded |
| mac_addr_wifi | `Get-NetAdapter -Physical`, `NdisPhysicalMedium` = 9 (802.11) | built-in (PCI) adapter preferred |
| mac_addr_eth | same, `NdisPhysicalMedium` = 14 (802.3) | built-in preferred over USB docks |
| mac_addr_extra | every other physical adapter (USB Ethernet, Bluetooth, 2nd NIC) | separated by `; ` |
| type | `Win32_SystemEnclosure.ChassisTypes` → `Win32_ComputerSystem.PCSystemType` | Desktop, Laptop, Tablet, All-in-One, Mini PC, Server, Virtual Machine, Unknown |
| user_id | `Win32_ComputerSystem.UserName` (console user), domain removed | falls back to the account running the script |
| department | previous run, or `-Department` | |
| model | `Win32_ComputerSystem.Model` | Lenovo: `ComputerSystemProduct.Version (Model)`, e.g. `ThinkPad T480 (20L5S0XX00)` |
| manufacturer | `Win32_ComputerSystem.Manufacturer` | |
| os | `Win32_OperatingSystem.Caption` + `DisplayVersion` + build.UBR + bitness | e.g. `Microsoft Windows 11 Pro 23H2 (build 22631.4460, 64-bit)` |
| extra_hw_info | CPU, RAM, disks, GPU, motherboard, BIOS | `\|`-separated summary; one column each in the run's `extra_hw_info.csv` |
| key_type | `SoftwareLicensingProduct.ProductKeyChannel` of Windows | `OEM:DM`, `Retail`, `Volume:MAK`, `Volume:GVLK`, … The key itself is **not** recorded |
| hostname | `Win32_ComputerSystem.Name` | |
| acquired_in, receipt_number, status, approved_to_connect | left blank | cannot be read from the machine |
| ` location` | previous run, or `-Location` | the header has a leading space, as in the sheet |
| last_log_change | local time of the collection | `yyyy-MM-dd HH:mm:ss` |

### other_information.csv (run folder only)

Each run folder has `other_information.csv`: one row with everything collected
that has no column in the hardware sheet, one item per column. It starts with
the same link columns as `extra_hw_info.csv` (`machine_key`, `asset_id`,
`hostname`, `serial_number`, `last_log_change`); a value is blank when it could
not be read. Items holding several things (modules, disks, monitors, …) list
them separated by `; `. It is not merged into a top-level file.

| Column | Source |
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

### extra_hw_info.csv (run folder only)

Each run folder also has `extra_hw_info.csv`: the `extra_hw_info` cell split
into one column per item. It is not merged into a top-level file.

| Column | Value |
|---|---|
| machine_key | the machine's key, also the end of the run folder name |
| asset_id, hostname, serial_number | the same as this run's `hardware.csv`, to link it to the computer |
| last_log_change | when this run happened |
| cpu | each processor with cores/threads |
| ram | total RAM and module count |
| disk | each internal disk: model, type, size |
| gpu | each graphics adapter (remote/virtual displays left out) |
| board | motherboard maker and model |
| bios | BIOS version and date |

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
| `QUICK.cmd` / `-SkipConsent` | No window is shown and collection runs. One `consent.csv` row is written: `accepted=skipped`, `method=skipped`, no e-mail and a blank statement, so the record shows the machine was collected without the notice. |

`consent.csv` columns:

| Column | Content |
|---|---|
| asset_id | the device's `asset_id` after merging, so every consent row of a device follows the current value |
| serial_number, hostname, user_id | from the hardware row of the same run; blank after a refusal, except hostname |
| email | typed in the window |
| accepted | `yes` / `no` / `skipped` (no window was shown) |
| consent_date | local date and time of the answer, `yyyy-MM-dd HH:mm:ss` |
| method | `dialog` (the window), `parameter` (`-ConsentEmail`), or `skipped` (`QUICK.cmd` / `-SkipConsent`) |
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
`method=parameter`. `-SkipConsent` (used by `QUICK.cmd`) collects with no
notice at all and is recorded as `method=skipped`; it has no desktop
requirement, so it can run over a remote session or as a scheduled task.

## Autorun

The stick ships with an `autorun.inf` that tries to launch `QUICK.cmd`, but how
far it gets depends entirely on the drive and the Windows version — there is no
software-only way to make a plain USB flash drive run a program the moment it is
plugged in.

Since Windows 7, Windows ignores the `open=`/`shellexecute=` lines of
`autorun.inf` on USB flash drives, and the `shell\…` double-click verbs are
honoured only on CD/DVD media, not on removable drives. For a USB flash drive,
only `label` and `icon` are read. Microsoft backported this to XP and Vista in
2011 (KB971029) because worms such as Conficker spread that way, and Windows 10
and 11 keep the behaviour. So on a normal stick the `autorun.inf` only sets the
drive label; you still open the drive and double-click `RUN.cmd` or `QUICK.cmd`.

The same `autorun.inf` **does** fire where autorun still exists:

- CD/DVD media, and CD-ROM–emulating "secure" USB sticks (U3 and similar) that
  present a read-only optical partition — there Windows reaches an AutoPlay
  prompt whose entry (`action=`) runs the quick scan.
- Older Windows, and machines where an admin has re-enabled autorun by policy.

Everywhere else the file is read for the label and otherwise ignored, so it is
harmless to leave on the stick. Because the launcher it points at is
`QUICK.cmd`, any machine that *does* autorun collects with no prompts at all
(see [Consent](#consent)); keep that in mind before relying on it. An
`autorun.inf` that names a script can also trip antivirus or a USB-control
policy; if that is a problem, delete `autorun.inf` and start the scan by hand.

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
