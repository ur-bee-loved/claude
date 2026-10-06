# netaudit

One tool that replaces `netwatch.sh` (fping + mtr capture and summary),
`DataBaseAuditv1.py` (CSV to SQLite loader) and the five audit queries.
Python 3.10+, standard library only; `fping` and `mtr` must be installed
for `run`.

```sh
cp targets.example.txt targets.txt          # then edit it
cp mtr_targets.example.txt mtr_targets.txt  # optional

./netaudit.py run                 # monitor until Ctrl-C; creates a new audit and its folder
./netaudit.py audits              # list audits
./netaudit.py summary             # per-host and per-hop summary of the latest audit
./netaudit.py report              # list the SQL reports
./netaudit.py report availability -a latest
./netaudit.py import <fping.csv | netwatch folder>
./netaudit.py migrate             # convert an older database to UTC and the current schema
./netaudit.py -h                  # also --h, --help; every command has its own -h
```

## Layout

Everything lives in the *home* folder, which is the folder of `netaudit.py`
unless `--home DIR` or `NW_HOME` says otherwise:

```
netaudit/
  netaudit.py
  sql/*.sql                          reports (always next to the script)
  targets.txt, mtr_targets.txt       your hosts (git-ignored)
  DataAudit.db                       database (git-ignored)
  audits/                            git-ignored
    20261006T125713Z_audit3/         one folder per audit: <UTC start>_audit<id>
      meta.txt fping.csv fping_raw.log mtr_<target>.csv mtr_errors.log targets.txt
```

`Audits.folder` stores the folder path relative to the database. `import`
also creates a folder: `fping.csv` is rewritten with UTC timestamps, mtr
files are copied unchanged (their timestamps are Unix epoch), and the
source's `meta.txt` is kept as `source_meta.txt`.

## Command-line conventions

- `-h`, `--h`, `--help` on every command; `-V`, `--version`.
- Options can go before or after the command (`netaudit -t utc audits` and
  `netaudit audits -t utc` are the same).
- Errors go to stderr as `netaudit: error: ...`.
- Exit status: 0 success, 1 error, 2 usage error, 130 interrupted.
- `--format csv` on `report` and `audits` for spreadsheets; output into a
  pipe (`| head`) ends quietly.
- Environment: `NW_HOME NW_DB NW_TZ NW_TARGETS NW_MTR_TARGETS NW_BR_ZONE
  NW_FPING_PERIOD NW_FPING_REPORT NW_MTR_EVERY NW_MTR_COUNT`.

## Datetimes

| where                     | format                                              |
|---------------------------|-----------------------------------------------------|
| database, CSV, raw log, folder names | UTC, `2026-10-02T17:25:38Z` (`20261002T172538Z` in names) |
| output with `--tz utc`    | UTC, `2026-10-02T17:25:38Z`                         |
| output with `--tz br`     | America/Sao_Paulo, `02/10/2026 14:25:38`            |
| `RedeAuditBR`, `MtrAuditBR` views | column `dataHoraBR` (fixed UTC-3)           |

Accepted input (`import`, `migrate`, `--since`, `--until`): ISO 8601 with
or without an offset, `dd/mm/aaaa [HH:MM[:SS]]`, and Unix epoch seconds.
Input without an offset is read in the `--tz` zone (`import` and `migrate`
always use America/Sao_Paulo). `--until` is exclusive, except that a bare
date includes the whole day.

A database whose datetimes are not all UTC is refused until `migrate` has
run. `migrate` writes a backup (`DataAudit.db.bak-<UTC stamp>`) first, works
in one transaction and can be run again safely.

## Reports

`report <name>` runs `sql/<name>.sql` read-only, with the parameters
`:audit :host :since :until` (NULL when not given) and any
`--param NAME=VALUE`. Columns named `*_utc` are shown in the `--tz` zone.
`report path/to/file.sql` runs your own query the same way, and
`--show-sql` prints a report's query. Unset SQL parameters are NULL, so
the files should also run in the `sqlite3` shell (`latency` needs `sqrt`,
built into the shell since SQLite 3.35; not tested here).

| report | replaces | what changed and why |
|---|---|---|
| `audit_compare` | AuditCompare.sql | `pings` counted rows (one per host per minute); now `host_minutes` and `pings_sent`. Adds packet-weighted loss and latency, the period covered and fully-down minutes. |
| `availability` | availability.sql | The old `availability_pct` was the share of minutes with **zero** loss, so one lost ping marked a whole minute unavailable. Now there are three measures: `up_minutes_pct` (not at 100% loss), `clean_minutes_pct` (the old figure) and `delivery_pct` (packets received / sent). Also outage count and longest outage. |
| `packet_loss` | pcktLossAudit.sql | Adds packet-weighted `packet_loss_pct` and splits lossy minutes into partial loss and fully down. Hosts without loss are no longer hidden by `HAVING`. |
| `latency` | latencyAudit.sql | `AVG(avg_ms)` was a mean of minute means; `mean_ms` now weights each minute by packets received. `spread` (max − min) was ≈ 1000 ms for every host because one bad ping decides it; replaced with p50/p95/p99 of minute averages, their standard deviation, and a count of minutes over `:spike_ms`. |
| `host_timeline` | perHostAudit.sql | The host is a parameter (`--host`) instead of being written into the query. |
| `outages` | new | Each run of consecutive 100%-loss minutes, per host (the same as `summary`, in SQL). |
| `correlated_events` | new | Minutes where at least `:min_share`% of hosts had loss or a spike at the same time. When most hosts, including the LAN ones, are hit in the same minute, the cause is probably near the monitoring machine (its Wi-Fi, its load) rather than at the hosts. |
| `mtr_hops` | new | Per target and hop over all mtr rounds. |

Limits worth knowing: fping reports only min/avg/max per interval, so the
percentiles describe **minute averages**, not single pings, and `sd_ms` is
not RFC 3550 jitter. `loss_pct` from fping is rounded to whole percent;
the packet-weighted figures use `sent`/`recv` and are exact.

## Tests

```sh
python3 -m pytest netaudit/tests
```
