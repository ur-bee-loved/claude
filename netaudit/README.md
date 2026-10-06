# netaudit

One tool that replaces `netwatch.sh` (fping + mtr capture and summary) and
`DataBaseAuditv1.py` (CSV to SQLite loader). Python 3.10+, standard library
only; `fping` and `mtr` must be installed for `run`.

```sh
netaudit.py run                      # capture: CSV files + live rows in the database
netaudit.py audits                   # list audits in the database
netaudit.py summary                  # summary of the latest audit (or --audit N)
netaudit.py summary <run_dir>        # summary straight from a run directory's CSV files
netaudit.py import <fping.csv|run_dir>
netaudit.py migrate                  # convert an existing database's datetimes to UTC
```

Every command accepts `--db PATH` (default `~/netaudit/DataAudit.db`, env
`NW_DB`) and `--tz utc|br` (default `br`, env `NW_TZ`). The `NW_*`
environment variables of `netwatch.sh` still work for `run`.

## Datetimes

| where                     | format                                              |
|---------------------------|-----------------------------------------------------|
| database, CSV, raw log    | UTC, `2026-10-02T17:25:38Z`                         |
| output with `--tz utc`    | UTC, `2026-10-02T17:25:38Z`                         |
| output with `--tz br`     | America/Sao_Paulo, `02/10/2026 14:25:38`            |
| `RedeAuditBR`, `MtrAuditBR` views | column `dataHoraBR`, `dd/mm/aaaa HH:MM:SS` (fixed UTC-3) |

Input accepted by `import` and `migrate`: ISO 8601 with an offset or `Z`,
ISO 8601 without an offset (taken as America/Sao_Paulo), `dd/mm/aaaa
HH:MM[:SS]` (also São Paulo) and Unix epoch seconds (mtr's `Start_Time`).

A database whose datetimes are not all UTC is refused until `migrate` has
run. `migrate` writes a backup (`DataAudit.db.bak-<UTC stamp>`) first, works
in one transaction, can be run again safely, and marks the database with
`PRAGMA user_version = 1`.

## Database

`Audits` and `RedeAudit` keep the original columns. New:

- `MtrAudit`: one row per hop per mtr round (`target`, `hop`, `ip`,
  `loss_pct`, `sent`, `last_ms`, `avg_ms`, `best_ms`, `worst_ms`,
  `stdev_ms`, `status`).
- `RedeAuditBR`, `MtrAuditBR`: views with an added Brazilian-format column.

## Tests

```sh
python3 -m pytest netaudit/tests
```
