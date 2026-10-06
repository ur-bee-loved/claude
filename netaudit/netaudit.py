#!/usr/bin/env python3
"""netaudit: network monitoring (fping + mtr) and SQLite audit storage in one tool.

All datetimes are stored in UTC as YYYY-MM-DDTHH:MM:SSZ. They are displayed
either in UTC or in Brazil's format (dd/mm/aaaa HH:MM:SS, America/Sao_Paulo).
"""

import argparse
import csv
import datetime as dt
import math
import os
import re
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:
    ZoneInfo = None

VERSION = "1.1.0"
PROG = "netaudit"
TOOL_DIR = Path(__file__).resolve().parent
SQL_DIR = TOOL_DIR / "sql"
UTC = dt.timezone.utc
SCHEMA_VERSION = 2
UTC_FMT = "%Y-%m-%dT%H:%M:%SZ"
BR_FMT = "%d/%m/%Y %H:%M:%S"


def die(msg, code=1):
    print(f"{PROG}: error: {msg}", file=sys.stderr)
    sys.exit(code)


def brazil_tz():
    name = os.environ.get("NW_BR_ZONE", "America/Sao_Paulo")
    if ZoneInfo is not None:
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError:
            pass
    # Brazil has had no daylight saving time since 2019, so a fixed offset is
    # only wrong for older data.
    print(f"warning: time zone {name} not found, using fixed UTC-03:00", file=sys.stderr)
    return dt.timezone(dt.timedelta(hours=-3), "BRT")


BR = brazil_tz()


def now_utc():
    return dt.datetime.now(UTC).replace(microsecond=0)


def parse_datetime(value, assume=BR):
    """Parse ISO 8601 (with or without offset/Z), Brazilian dd/mm/aaaa or a Unix epoch into an aware UTC datetime."""
    s = value.strip()
    if re.fullmatch(r"\d{9,11}", s):
        return dt.datetime.fromtimestamp(int(s), UTC)
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    try:
        d = dt.datetime.fromisoformat(s)
    except ValueError:
        for fmt in (BR_FMT, "%d/%m/%Y %H:%M", "%d/%m/%Y"):
            try:
                d = dt.datetime.strptime(s, fmt).replace(tzinfo=assume)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"unrecognised datetime: {value!r}") from None
    if d.tzinfo is None:
        d = d.replace(tzinfo=assume)
    return d.astimezone(UTC).replace(microsecond=0)


def to_utc(value, assume=BR):
    return parse_datetime(value, assume).strftime(UTC_FMT)


def fmt_dt(value, tz):
    d = value if isinstance(value, dt.datetime) else parse_datetime(value)
    if tz == "utc":
        return d.astimezone(UTC).strftime(UTC_FMT)
    return d.astimezone(BR).strftime(BR_FMT)


def tz_label(tz):
    return "UTC" if tz == "utc" else f"{getattr(BR, 'key', BR)} (dd/mm/aaaa)"


def bound(value, tz, end=False):
    """--since/--until value to UTC. Naive input is read in the --tz zone; a bare date given to --until includes that whole day."""
    if value is None:
        return None
    zone = UTC if tz == "utc" else BR
    d = parse_datetime(value, assume=zone)
    if end and re.fullmatch(r"\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}", value.strip()):
        d += dt.timedelta(days=1)
    return d.strftime(UTC_FMT)


def hosts_of(path):
    hosts = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                hosts.append(line.split()[0])
    return hosts


# ---------------------------------------------------------------- database

def get_db_connection(path):
    try:
        conn = sqlite3.connect(path, timeout=20)
        conn.execute('PRAGMA foreign_keys = ON')
        return conn
    except sqlite3.Error as e:
        print(f"Erro na conexão: {e}", file=sys.stderr)
        return None


def create_schema(conn):
    try:
        cursor = conn.cursor()
        cursor.executescript('''
            CREATE TABLE IF NOT EXISTS Audits (
                auditId   INTEGER PRIMARY KEY AUTOINCREMENT,
                auditDate TEXT NOT NULL,
                source    TEXT,
                folder    TEXT
            );

            CREATE TABLE IF NOT EXISTS RedeAudit (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                auditId   INTEGER NOT NULL,
                dateTime  TEXT    NOT NULL,
                host      TEXT    NOT NULL,
                sent      INTEGER NOT NULL,
                recv      INTEGER NOT NULL,
                loss_pct  REAL,
                min_ms    REAL,
                avg_ms    REAL,
                max_ms    REAL,
                FOREIGN KEY (auditId) REFERENCES Audits(auditId) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_redeaudit_audit
                ON RedeAudit(auditId);

            CREATE INDEX IF NOT EXISTS idx_redeaudit_host_time
                ON RedeAudit(host, dateTime);

            CREATE TABLE IF NOT EXISTS MtrAudit (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                auditId   INTEGER NOT NULL,
                dateTime  TEXT    NOT NULL,
                target    TEXT    NOT NULL,
                status    TEXT,
                hop       INTEGER NOT NULL,
                ip        TEXT,
                loss_pct  REAL,
                sent      INTEGER,
                last_ms   REAL,
                avg_ms    REAL,
                best_ms   REAL,
                worst_ms  REAL,
                stdev_ms  REAL,
                FOREIGN KEY (auditId) REFERENCES Audits(auditId) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_mtraudit_audit
                ON MtrAudit(auditId);

            CREATE INDEX IF NOT EXISTS idx_mtraudit_target_time
                ON MtrAudit(target, dateTime);

            CREATE VIEW IF NOT EXISTS RedeAuditBR AS
                SELECT id, auditId, dateTime AS dateTimeUTC,
                       strftime('%d/%m/%Y %H:%M:%S', dateTime, '-3 hours') AS dataHoraBR,
                       host, sent, recv, loss_pct, min_ms, avg_ms, max_ms
                FROM RedeAudit;

            CREATE VIEW IF NOT EXISTS MtrAuditBR AS
                SELECT id, auditId, dateTime AS dateTimeUTC,
                       strftime('%d/%m/%Y %H:%M:%S', dateTime, '-3 hours') AS dataHoraBR,
                       target, status, hop, ip, loss_pct, sent, last_ms, avg_ms, best_ms, worst_ms, stdev_ms
                FROM MtrAudit;
        ''')
        if "folder" not in {r[1] for r in conn.execute("PRAGMA table_info(Audits)")}:
            conn.execute("ALTER TABLE Audits ADD COLUMN folder TEXT")
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Erro ao criar schema: {e}", file=sys.stderr)
        return False


def unsanitized_count(conn):
    n = 0
    for table, col in (("Audits", "auditDate"), ("RedeAudit", "dateTime"), ("MtrAudit", "dateTime")):
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        if exists:
            n += conn.execute(f"SELECT count(*) FROM {table} WHERE {col} NOT GLOB "
                              "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'").fetchone()[0]
    return n


def open_db(path):
    """Open the database, create or upgrade the schema, and refuse to mix UTC rows with unsanitized ones."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = get_db_connection(path)
    if conn is None:
        sys.exit(1)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < 1 and unsanitized_count(conn):
        conn.close()
        die(f"{path} has datetimes not yet in UTC; run: {PROG} --db {path} migrate")
    if not create_schema(conn):
        sys.exit(1)
    return conn


def open_db_readonly(path):
    if not Path(path).is_file():
        die(f"no database: {path}")
    open_db(path).close()
    conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        conn.execute("SELECT sqrt(4)")
    except sqlite3.OperationalError:
        conn.create_function("sqrt", 1, lambda x: math.sqrt(x) if x is not None and x >= 0 else None, deterministic=True)
    return conn


def resolve_audit(conn, audit):
    if audit == "latest":
        audit = conn.execute("SELECT max(auditId) FROM Audits").fetchone()[0]
        if audit is None:
            die("the database has no audits yet")
    elif conn.execute("SELECT 1 FROM Audits WHERE auditId = ?", (audit,)).fetchone() is None:
        die(f"no audit {audit} in the database (see '{PROG} audits')")
    return audit


def create_audit(conn, audit_date, source, audits_dir, db_path):
    """Insert an Audits row and create its folder, named <UTC start>_audit<id>. Without a connection the folder ends in _nodb."""
    stamp = audit_date.strftime("%Y%m%dT%H%M%SZ")
    if conn is None:
        folder = audits_dir / f"{stamp}_nodb"
        folder.mkdir(parents=True, exist_ok=True)
        return None, folder
    cursor = conn.execute(
        "INSERT INTO Audits (auditDate, source) VALUES (?, ?)",
        (audit_date.strftime(UTC_FMT), source),
    )
    audit_id = cursor.lastrowid
    folder = audits_dir / f"{stamp}_audit{audit_id}"
    folder.mkdir(parents=True, exist_ok=False)
    try:
        stored = folder.resolve().relative_to(Path(db_path).resolve().parent)
    except ValueError:
        stored = folder.resolve()
    conn.execute("UPDATE Audits SET folder = ? WHERE auditId = ?", (str(stored), audit_id))
    return audit_id, folder


FPING_HEADER_ROW = ["ts", "host", "sent", "recv", "loss_pct", "min_ms", "avg_ms", "max_ms"]

FPING_INSERT = '''INSERT INTO RedeAudit
               (auditId, dateTime, host, sent, recv, loss_pct, min_ms, avg_ms, max_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'''

MTR_INSERT = '''INSERT INTO MtrAudit
               (auditId, dateTime, target, status, hop, ip, loss_pct, sent, last_ms, avg_ms, best_ms, worst_ms, stdev_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'''


# ---------------------------------------------------------------- parsers

def parse_row(row):
    """Parse one CSV row. Empty numeric fields -> None (NULL in DB)."""
    def to_int(v):
        v = v.strip()
        return int(v) if v else None

    def to_float(v):
        v = v.strip()
        return float(v) if v else None

    return (
        to_utc(row[0]),
        row[1].strip(),
        to_int(row[2]),
        to_int(row[3]),
        to_float(row[4]),
        to_float(row[5]),
        to_float(row[6]),
        to_float(row[7]),
    )


FPING_HEADER = re.compile(r"^\[\d{2}:\d{2}:\d{2}\]$")
FPING_STATS = re.compile(
    r"^(\S+) +: xmt/rcv/%(loss|return) = (\d+)/(\d+)/(\d+)%"
    r"(?:, min/avg/max = ([\d.]+)/([\d.]+)/([\d.]+))?")


class FpingParser:
    """Turns fping -l -Q output into per-interval rows.

    Every block opens with a [HH:MM:SS] line. A host seen twice without a new
    header is fping's cumulative total printed on SIGINT/SIGQUIT, not an
    interval, so it is discarded.
    """

    def __init__(self):
        self.ts = None
        self.seen = set()

    def feed(self, line, received_at):
        line = line.rstrip("\n")
        if FPING_HEADER.match(line):
            self.ts = received_at.strftime(UTC_FMT)
            self.seen = set()
            return None
        m = FPING_STATS.match(line)
        if not m or self.ts is None or m.group(1) in self.seen:
            return None
        host, kind, sent, recv, pct, mn, avg, mx = m.groups()
        self.seen.add(host)
        loss = float(pct) if kind == "loss" else 0.0
        f = lambda v: float(v) if v else None
        return (self.ts, host, int(sent), int(recv), loss, f(mn), f(avg), f(mx))


MTR_FIELDS = (("Host", str), ("Status", str), ("Hop", int), ("Ip", str), ("Loss%", float), ("Snt", int),
              ("Last", float), ("Avg", float), ("Best", float), ("Wrst", float), ("StDev", float))


def _mtr_field(rec, col, name, conv):
    i = col.get(name)
    v = rec[i].strip().rstrip("%") if i is not None and i < len(rec) else ""
    return conv(v) if v else None


def parse_mtr(text):
    """Parse mtr -C output (one or many runs, each with its own header) into MtrAudit tuples without auditId."""
    rows = []
    col = None
    for rec in csv.reader(text.splitlines()):
        if not rec:
            continue
        if rec[0] == "Mtr_Version":
            col = {name: i for i, name in enumerate(rec)}
            continue
        if col is None or "Hop" not in col:
            continue
        rows.append((
            to_utc(rec[col["Start_Time"]]),
            *(_mtr_field(rec, col, name, conv) for name, conv in MTR_FIELDS),
        ))
    return rows


def write_fping_csv(path, rows):
    with open(path, "w", newline="") as out:
        w = csv.writer(out)
        w.writerow(FPING_HEADER_ROW)
        for row in rows:
            w.writerow(["" if v is None else v for v in row])


# ---------------------------------------------------------------- import

def load_csv(csv_path):
    with open(csv_path, mode="r", newline="") as file:
        reader = csv.reader(file)
        next(reader, None)  # skip header
        raw_rows = [r for r in reader if r]
    return [parse_row(r) for r in raw_rows]


def cmd_import(args):
    src = Path(args.source)
    if src.is_dir():
        fping_csv = src / "fping.csv"
        mtr_files = sorted(src.glob("mtr_*.csv"))
    else:
        fping_csv, mtr_files = src, []
    if not fping_csv.is_file():
        die(f"no fping CSV at {fping_csv}", 2)

    try:
        rows = load_csv(fping_csv)
        mtr = {f: parse_mtr(f.read_text()) for f in mtr_files}
    except (OSError, csv.Error, ValueError, IndexError) as e:
        die(f"Erro ao processar CSV: {e}")

    conn = open_db(args.db)
    folder = None
    try:
        with conn:
            audit_id, folder = create_audit(conn, now_utc(), str(src.resolve()), args.audits_dir, args.db)
            conn.executemany(FPING_INSERT, [(audit_id, *r) for r in rows])
            for mtr_rows in mtr.values():
                conn.executemany(MTR_INSERT, [(audit_id, *r) for r in mtr_rows])
            write_fping_csv(folder / "fping.csv", rows)
            for f in mtr_files:
                shutil.copy(f, folder / f.name)
            for name in ("meta.txt", "targets.txt", "mtr_targets.txt"):
                if src.is_dir() and (src / name).is_file():
                    shutil.copy(src / name, folder / (f"source_{name}" if name == "meta.txt" else name))
            with open(folder / "meta.txt", "w") as f:
                t = now_utc()
                f.write(f"imported: {t.strftime(UTC_FMT)} ({fmt_dt(t, 'br')} {getattr(BR, 'key', BR)})\n")
                f.write(f"source: {src.resolve()}\n")
                f.write("fping.csv rewritten with UTC timestamps; mtr files copied unchanged (epoch timestamps)\n")
    except (OSError, sqlite3.Error) as e:
        if folder is not None:
            shutil.rmtree(folder, ignore_errors=True)
        die(f"Erro ao processar CSV: {e}")
    finally:
        conn.close()
    m = sum(len(v) for v in mtr.values())
    print(f"{len(rows)} linhas gravadas para auditId={audit_id}." + (f" ({m} linhas mtr)" if mtr_files else ""))
    print(f"Audit {audit_id} concluído com sucesso: {folder}")


# ---------------------------------------------------------------- migrate

def cmd_migrate(args):
    path = Path(args.db)
    if not path.is_file():
        die(f"no database: {path}")
    backup = path.with_name(f"{path.name}.bak-{now_utc().strftime('%Y%m%dT%H%M%SZ')}")
    src = sqlite3.connect(path)
    dst = sqlite3.connect(backup)
    src.backup(dst)
    dst.close()
    print(f"backup: {backup}")

    src.create_function("to_utc", 1, lambda v: to_utc(v) if v is not None else None, deterministic=True)
    try:
        with src:
            for table, col in (("Audits", "auditDate"), ("RedeAudit", "dateTime"), ("MtrAudit", "dateTime")):
                if src.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                    n = src.execute(f"UPDATE {table} SET {col} = to_utc({col})").rowcount
                    print(f"{table}.{col}: {n} rows converted to UTC")
    except (ValueError, sqlite3.Error) as e:
        src.close()
        die(f"migration failed, database left unchanged: {e}")
    left = unsanitized_count(src)
    if left:
        src.close()
        die(f"{left} values still not in UTC format")
    if not create_schema(src):
        sys.exit(1)
    src.close()
    print(f"ok: all datetimes stored as UTC (YYYY-MM-DDTHH:MM:SSZ), schema version {SCHEMA_VERSION}")


# ---------------------------------------------------------------- run

def tool_version(cmd):
    try:
        out = subprocess.run([cmd, "-v"], capture_output=True, text=True, timeout=5, check=False)
        return (out.stdout + out.stderr).splitlines()[0]
    except (OSError, IndexError, subprocess.TimeoutExpired):
        return "?"


def default_route():
    try:
        out = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True, timeout=5, check=False)
        return out.stdout.splitlines()[0] if out.stdout else ""
    except OSError:
        return ""


def cmd_run(args):
    for c in ("fping", "mtr"):
        if not shutil.which(c):
            die(f"missing: {c} (sudo dnf install {c})")
    targets = Path(args.targets)
    mtr_targets = Path(args.mtr_targets)
    if not targets.is_file() or not hosts_of(targets):
        die(f"no targets in {targets} (copy targets.example.txt to {targets} and edit it)")
    has_mtr = mtr_targets.is_file() and bool(hosts_of(mtr_targets))

    if not os.environ.get("NW_INHIBITED") and shutil.which("systemd-inhibit"):
        env = dict(os.environ, NW_INHIBITED="1")
        os.execvpe("systemd-inhibit", [
            "systemd-inhibit", "--what=sleep:idle", "--who=netwatch", "--why=network monitoring",
            sys.executable, os.path.abspath(__file__), *sys.argv[1:]], env)

    start = now_utc()
    conn = None if args.no_db else open_db(args.db)
    try:
        if conn is not None:
            with conn:
                audit_id, run_dir = create_audit(conn, start, f"run on {socket.gethostname()}", args.audits_dir, args.db)
            conn.close()
        else:
            audit_id, run_dir = create_audit(None, start, None, args.audits_dir, None)
    except (OSError, sqlite3.Error) as e:
        die(f"Erro ao criar audit: {e}")

    shutil.copy(targets, run_dir / "targets.txt")
    if has_mtr:
        shutil.copy(mtr_targets, run_dir / "mtr_targets.txt")
    meta = run_dir / "meta.txt"
    with open(meta, "w") as f:
        f.write(f"start: {start.strftime(UTC_FMT)} ({fmt_dt(start, 'br')} {getattr(BR, 'key', BR)})\n")
        f.write(f"auditId: {audit_id if audit_id is not None else '-'}\n")
        f.write(f"host: {socket.gethostname()}\n")
        f.write(f"route: {default_route()}\n")
        f.write(f"fping: {tool_version('fping')}\n")
        f.write(f"mtr: {tool_version('mtr')}\n")
        f.write(f"fping period {args.fping_period} ms, report every {args.fping_report} s; "
                f"mtr every {args.mtr_every} s, {args.mtr_count} cycles\n")

    stop = threading.Event()
    procs = []
    lock = threading.Lock()

    def track(p):
        with lock:
            procs.append(p)
        return p

    def fping_worker():
        db = None if audit_id is None else get_db_connection(args.db)
        parser = FpingParser()
        p = track(subprocess.Popen(
            ["fping", "-l", "-p", str(args.fping_period), "-Q", str(args.fping_report), *hosts_of(targets)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, bufsize=1))
        with open(run_dir / "fping_raw.log", "a") as raw, open(run_dir / "fping.csv", "w", newline="") as out:
            w = csv.writer(out)
            w.writerow(FPING_HEADER_ROW)
            out.flush()
            for line in p.stderr:
                t = now_utc()
                raw.write(f"{t.strftime(UTC_FMT)} {line}")
                raw.flush()
                if stop.is_set():
                    continue
                row = parser.feed(line, t)
                if row is None:
                    continue
                w.writerow(["" if v is None else v for v in row])
                out.flush()
                if db is not None:
                    with db:
                        db.execute(FPING_INSERT, (audit_id, *row))
        if db is not None:
            db.close()

    def mtr_worker():
        db = None if audit_id is None else get_db_connection(args.db)
        hosts = hosts_of(mtr_targets)
        while not stop.is_set():
            began = dt.datetime.now(UTC)
            running = []
            with open(run_dir / "mtr_errors.log", "a") as err:
                for t in hosts:
                    running.append((t, track(subprocess.Popen(
                        ["mtr", "-C", "-n", "-c", str(args.mtr_count), "-i", "1", t],
                        stdout=subprocess.PIPE, stderr=err, text=True))))
                for t, p in running:
                    text, _ = p.communicate()
                    if stop.is_set() or p.returncode != 0 or not text:
                        continue
                    safe = re.sub(r"[^A-Za-z0-9.]", "_", t)
                    with open(run_dir / f"mtr_{safe}.csv", "a") as f:
                        f.write(text)
                    if db is not None:
                        try:
                            rows = parse_mtr(text)
                            with db:
                                db.executemany(MTR_INSERT, [(audit_id, *r) for r in rows])
                        except (ValueError, sqlite3.Error) as e:
                            err.write(f"{now_utc().strftime(UTC_FMT)} db: {t}: {e}\n")
            with lock:
                procs[:] = [p for p in procs if p.poll() is None]
            elapsed = (dt.datetime.now(UTC) - began).total_seconds()
            stop.wait(max(args.mtr_every - elapsed, 0))
        if db is not None:
            db.close()

    def on_signal(signum, frame):
        stop.set()

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    threads = [threading.Thread(target=fping_worker, daemon=True)]
    if has_mtr:
        threads.append(threading.Thread(target=mtr_worker, daemon=True))
    for th in threads:
        th.start()
    print(f"logging to {run_dir}" + (f" (auditId={audit_id})" if audit_id else "") + " (Ctrl-C to stop)")

    while not stop.wait(1):
        if not threads[0].is_alive():
            print("fping exited; see fping_raw.log", file=sys.stderr)
            stop.set()
    with lock:
        for p in procs:
            if p.poll() is None:
                p.terminate()
    for th in threads:
        th.join(timeout=10)
    end = now_utc()
    with open(meta, "a") as f:
        f.write(f"stop: {end.strftime(UTC_FMT)} ({fmt_dt(end, 'br')} {getattr(BR, 'key', BR)})\n")
    print(f"stopped; summary: {PROG} summary " + (f"-a {audit_id}" if audit_id else str(run_dir)))


# ---------------------------------------------------------------- output

def print_table(headers, rows, tz, fmt="table", out=sys.stdout):
    """Columns named *_utc hold UTC datetimes and are shown in the --tz zone."""
    times = [h.endswith("_utc") for h in headers]
    rows = [[("" if v is None else fmt_dt(v, tz) if t and v else v) for v, t in zip(r, times)] for r in rows]
    if fmt == "csv":
        w = csv.writer(out)
        w.writerow([h[:-4] + ("_utc" if tz == "utc" else "_br") if t else h for h, t in zip(headers, times)])
        w.writerows(rows)
        return
    shown = [h[:-4] if t else h for h, t in zip(headers, times)]
    if any(times):
        print(f"times in {tz_label(tz)}", file=out)
    numeric = [bool(rows) and all(isinstance(r[i], (int, float)) or r[i] == "" for r in rows) for i in range(len(headers))]
    widths = [max([len(shown[i])] + [len(str(r[i])) for r in rows]) for i in range(len(headers))]
    line = lambda cells: "  ".join((str(c).rjust(w) if n else str(c).ljust(w)) for c, w, n in zip(cells, widths, numeric)).rstrip()
    print(line(shown), file=out)
    for r in rows:
        print(line(r), file=out)
    if not rows:
        print("(no rows)", file=out)


# ---------------------------------------------------------------- summary

def fping_rows_from_csv(path):
    with open(path, newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        return [parse_row(r) for r in reader if r]


def mtr_rows_from_dir(run_dir):
    rows = []
    for f in sorted(Path(run_dir).glob("mtr_*.csv")):
        rows.extend(parse_mtr(f.read_text()))
    return rows


def print_summary(fping_rows, mtr_rows, tz):
    print(f"times in {tz_label(tz)}")
    print()
    print("== fping, per host")
    stats = {}
    for ts, host, sent, recv, loss, mn, avg, mx in fping_rows:
        s = stats.setdefault(host, {"n": 0, "sent": 0, "recv": 0, "lm": 0, "dn": 0, "a": 0.0, "ac": 0, "mx": 0.0})
        s["n"] += 1
        s["sent"] += sent or 0
        s["recv"] += recv or 0
        if loss and loss > 0:
            s["lm"] += 1
        if loss == 100:
            s["dn"] += 1
        if avg is not None:
            s["a"] += avg
            s["ac"] += 1
        if mx is not None and mx > s["mx"]:
            s["mx"] = mx
    print(f"{'host':<24} {'minutes':>7} {'loss%':>7} {'min_loss':>9} {'min_down':>9} {'avg_ms':>8} {'max_ms':>8}")
    for host in sorted(stats):
        s = stats[host]
        loss = (s["sent"] - s["recv"]) * 100 / s["sent"] if s["sent"] else 0
        avg = s["a"] / s["ac"] if s["ac"] else 0
        print(f"{host:<24} {s['n']:>7d} {loss:>7.2f} {s['lm']:>9d} {s['dn']:>9d} {avg:>8.2f} {s['mx']:>8.2f}")

    print()
    print("== fping, outages (minutes at 100% loss)")
    open_ = {}
    for ts, host, sent, recv, loss, *_ in fping_rows:
        if loss == 100:
            o = open_.setdefault(host, [ts, ts, 0])
            o[1] = ts
            o[2] += 1
        elif host in open_:
            st, en, c = open_.pop(host)
            print(f"{host:<24} {fmt_dt(st, tz)} -> {fmt_dt(en, tz)}  ({c} min)")
    for host, (st, en, c) in open_.items():
        print(f"{host:<24} {fmt_dt(st, tz)} -> {fmt_dt(en, tz)}  ({c} min, still down at end)")

    by_target = {}
    for ts, target, status, hop, ip, loss, sent, last, avg, best, worst, sd in mtr_rows:
        h = by_target.setdefault(target, {}).setdefault(hop, {"ip": ip, "n": 0, "loss": 0.0, "avg": 0.0, "w": 0.0})
        h["ip"] = ip
        h["n"] += 1
        h["loss"] += loss or 0
        h["avg"] += avg or 0
        if worst is not None and worst > h["w"]:
            h["w"] = worst
    for target in sorted(by_target):
        print()
        print(f"== mtr {target}, per hop over all runs")
        print(f"{'hop':>4} {'ip':<18} {'runs':>5} {'loss%':>7} {'avg_ms':>8} {'worst_ms':>8}")
        for hop in sorted(by_target[target]):
            h = by_target[target][hop]
            print(f"{hop:>4d} {h['ip'] or '???':<18} {h['n']:>5d} {h['loss'] / h['n']:>7.2f} {h['avg'] / h['n']:>8.2f} {h['w']:>8.2f}")


def cmd_summary(args):
    if args.run_dir:
        d = Path(args.run_dir)
        if not (d / "fping.csv").is_file():
            die(f"no fping.csv in {d}", 2)
        print(f"source: {d}")
        print_summary(fping_rows_from_csv(d / "fping.csv"), mtr_rows_from_dir(d), args.tz)
        return

    conn = open_db_readonly(args.db)
    audit = resolve_audit(conn, args.audit or "latest")
    info = conn.execute("SELECT auditDate, source, folder FROM Audits WHERE auditId = ?", (audit,)).fetchone()
    fping_rows = conn.execute(
        "SELECT dateTime, host, sent, recv, loss_pct, min_ms, avg_ms, max_ms FROM RedeAudit "
        "WHERE auditId = ? ORDER BY dateTime, id", (audit,)).fetchall()
    mtr_rows = conn.execute(
        "SELECT dateTime, target, status, hop, ip, loss_pct, sent, last_ms, avg_ms, best_ms, worst_ms, stdev_ms "
        "FROM MtrAudit WHERE auditId = ? ORDER BY dateTime, id", (audit,)).fetchall()
    conn.close()
    print(f"audit {audit}: created {fmt_dt(info[0], args.tz)}, source {info[1]}" + (f", folder {info[2]}" if info[2] else ""))
    print_summary(fping_rows, mtr_rows, args.tz)


def cmd_audits(args):
    conn = open_db_readonly(args.db)
    cur = conn.execute(
        "SELECT a.auditId AS id, a.auditDate AS created_utc, count(r.id) AS rows, "
        "min(r.dateTime) AS first_utc, max(r.dateTime) AS last_utc, a.folder, a.source "
        "FROM Audits a LEFT JOIN RedeAudit r USING (auditId) GROUP BY a.auditId ORDER BY a.auditId")
    print_table([d[0] for d in cur.description], cur.fetchall(), args.tz, args.format)
    conn.close()


# ---------------------------------------------------------------- reports

def read_report(path):
    text = path.read_text()
    desc, requires = "", []
    for line in text.splitlines():
        if not line.startswith("--"):
            break
        body = line[2:].strip()
        if body.startswith("requires:"):
            requires = body[len("requires:"):].split()
        elif not desc:
            desc = body
    return text, desc, requires


def available_reports():
    return sorted(SQL_DIR.glob("*.sql")) if SQL_DIR.is_dir() else []


def cmd_report(args):
    if not args.name:
        print(f"reports in {SQL_DIR}:")
        for p in available_reports():
            print(f"  {p.stem:<20} {read_report(p)[1]}")
        print(f"\nrun one with: {PROG} report <name> [options]; see {PROG} report -h")
        return

    path = Path(args.name)
    if not (path.suffix == ".sql" and path.is_file()):
        path = SQL_DIR / f"{args.name}.sql"
    if not path.is_file():
        die(f"no report named {args.name!r}; run '{PROG} report' to list them", 2)
    text, _, requires = read_report(path)
    if args.show_sql:
        print(text, end="")
        return

    params = {"audit": None, "host": args.host, "spike_ms": None, "min_share": None}
    try:
        params["since"] = bound(args.since, args.tz)
        params["until"] = bound(args.until, args.tz, end=True)
    except ValueError as e:
        die(str(e), 2)
    for item in args.param or []:
        key, sep, value = item.partition("=")
        if not sep:
            die(f"--param expects NAME=VALUE, got {item!r}", 2)
        params[key] = float(value) if re.fullmatch(r"-?\d+(\.\d+)?", value) else value
    missing = [r for r in requires if params.get(r) is None]
    if missing:
        die(f"report {path.stem} needs --{missing[0]}", 2)

    conn = open_db_readonly(args.db)
    if args.audit:
        params["audit"] = resolve_audit(conn, args.audit)
    try:
        cur = conn.execute(text, params)
        rows = cur.fetchall()
    except sqlite3.Error as e:
        die(f"{path.name}: {e}")
    finally:
        conn.close()
    print_table([d[0] for d in cur.description], rows, args.tz, args.format)


# ---------------------------------------------------------------- cli

EPILOG = f"""\
examples:
  {PROG} run                                 start monitoring; Ctrl-C stops it
  {PROG} audits                              list audits
  {PROG} summary                             summary of the latest audit
  {PROG} report                              list the SQL reports
  {PROG} report availability -a latest       one report, one audit
  {PROG} report latency --since 05/10/2026 --format csv > latency.csv
  {PROG} import ~/netaudit/2026-10-02/netwatch-1425
  {PROG} migrate                             convert an older database to UTC

files (in the home folder: --home, env NW_HOME, default the folder of this script):
  DataAudit.db                 database
  targets.txt                  fping hosts, one per line, '#' starts a comment
  mtr_targets.txt              mtr hosts (optional)
  audits/<UTC start>_audit<N>/ one folder per audit: meta.txt, fping.csv, fping_raw.log, mtr_*.csv
  {SQL_DIR}/*.sql   reports (always next to the script)

environment:
  NW_HOME NW_DB NW_TZ NW_TARGETS NW_MTR_TARGETS NW_BR_ZONE
  NW_FPING_PERIOD NW_FPING_REPORT NW_MTR_EVERY NW_MTR_COUNT

datetimes are stored in UTC; --tz br shows dd/mm/aaaa HH:MM:SS in America/Sao_Paulo,
--tz utc shows YYYY-MM-DDTHH:MM:SSZ. --since/--until read naive input in the --tz zone.

exit status: 0 success, 1 error, 2 usage error, 130 interrupted
"""


def audit_arg(value):
    if value == "latest":
        return value
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("expected an audit id or 'latest'") from None
    if n < 1:
        raise argparse.ArgumentTypeError("audit ids start at 1")
    return n


def add_help(parser):
    parser.add_argument("-h", "--h", "--help", action="help", help="show this help and exit")


def build_parser():
    env = os.environ.get
    fmt = argparse.RawDescriptionHelpFormatter

    common = argparse.ArgumentParser(add_help=False)
    g = common.add_argument_group("common options")
    g.add_argument("--home", metavar="DIR", default=argparse.SUPPRESS,
                   help="folder for the database, targets and audits (env NW_HOME, default: this script's folder)")
    g.add_argument("-d", "--db", metavar="FILE", default=argparse.SUPPRESS,
                   help="SQLite database (env NW_DB, default: HOME/DataAudit.db)")
    g.add_argument("-t", "--tz", choices=("utc", "br"), default=argparse.SUPPRESS,
                   help="time zone for output and for naive input (env NW_TZ, default: br)")

    p = argparse.ArgumentParser(prog=PROG, description=__doc__, epilog=EPILOG, formatter_class=fmt, parents=[common], add_help=False)
    add_help(p)
    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {VERSION}")
    sub = p.add_subparsers(dest="cmd", metavar="COMMAND", title="commands")
    sub.required = True
    add_parser = sub.add_parser

    def sub_parser(*a, **kw):
        sp = add_parser(*a, add_help=False, **kw)
        add_help(sp)
        return sp

    sub.add_parser = sub_parser

    r = sub.add_parser("run", parents=[common], formatter_class=fmt,
                       help="monitor with fping and mtr into a new audit",
                       description="Monitor with fping and mtr until Ctrl-C or SIGTERM. Creates a new audit in the database "
                                   "and its own folder under HOME/audits/.",
                       epilog=f"example:\n  {PROG} run --fping-report 30 --mtr-every 600")
    r.add_argument("--targets", metavar="FILE", default=env("NW_TARGETS"), help="fping hosts (default: HOME/targets.txt)")
    r.add_argument("--mtr-targets", metavar="FILE", default=env("NW_MTR_TARGETS"), help="mtr hosts (default: HOME/mtr_targets.txt)")
    r.add_argument("--fping-period", metavar="MS", type=int, default=int(env("NW_FPING_PERIOD", "1000")),
                   help="ms between pings to one host (default: %(default)s)")
    r.add_argument("--fping-report", metavar="S", type=int, default=int(env("NW_FPING_REPORT", "60")),
                   help="s between fping reports, one DB row per host each (default: %(default)s)")
    r.add_argument("--mtr-every", metavar="S", type=int, default=int(env("NW_MTR_EVERY", "900")),
                   help="s between the starts of mtr rounds (default: %(default)s)")
    r.add_argument("--mtr-count", metavar="N", type=int, default=int(env("NW_MTR_COUNT", "60")),
                   help="cycles per mtr round (default: %(default)s)")
    r.add_argument("--no-db", action="store_true", help="write only the audit folder, not the database")
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("summary", parents=[common], formatter_class=fmt,
                       help="per-host and per-hop summary of an audit",
                       description="Summarise one audit from the database, or any audit/run folder from its CSV files.",
                       epilog=f"examples:\n  {PROG} summary\n  {PROG} summary -a 2 -t utc\n  {PROG} summary audits/20261006T125713Z_audit3")
    s.add_argument("run_dir", nargs="?", metavar="FOLDER", help="audit or legacy netwatch folder (reads its CSV files)")
    s.add_argument("-a", "--audit", type=audit_arg, metavar="ID", help="audit id or 'latest' (default: latest)")
    s.set_defaults(func=cmd_summary)

    rp = sub.add_parser("report", parents=[common], formatter_class=fmt,
                        help="run an SQL report (no name: list them)",
                        description="Run one of the SQL reports in sql/, or any .sql file with the same parameters. "
                                    "Reports run read-only. Without a name, lists the reports.",
                        epilog="parameters available to the SQL: :audit :host :since :until, plus any --param NAME=VALUE\n"
                               "(latency/correlated_events read :spike_ms, default 500; correlated_events reads :min_share, default 50)\n\n"
                               f"examples:\n  {PROG} report\n  {PROG} report packet_loss -a latest\n"
                               f"  {PROG} report host_timeline --host 192.168.1.243 --since '05/10/2026 18:00'\n"
                               f"  {PROG} report correlated_events -p spike_ms=300 -p min_share=75\n"
                               f"  {PROG} report latency --show-sql")
    rp.add_argument("name", nargs="?", help="report name or path to a .sql file")
    rp.add_argument("-a", "--audit", type=audit_arg, metavar="ID", help="only this audit (id or 'latest'; default: all)")
    rp.add_argument("--host", help="only this host (mtr_hops: target)")
    rp.add_argument("-s", "--since", metavar="WHEN", help="from this datetime or date, inclusive")
    rp.add_argument("-u", "--until", metavar="WHEN", help="up to this datetime, exclusive; a bare date includes that day")
    rp.add_argument("-p", "--param", action="append", metavar="NAME=VALUE", help="extra SQL parameter (repeatable)")
    rp.add_argument("-f", "--format", choices=("table", "csv"), default="table", help="output format (default: table)")
    rp.add_argument("--show-sql", action="store_true", help="print the query instead of running it")
    rp.set_defaults(func=cmd_report)

    a = sub.add_parser("audits", parents=[common], formatter_class=fmt, help="list audits",
                       description="List every audit with its period, row count and folder.")
    a.add_argument("-f", "--format", choices=("table", "csv"), default="table", help="output format (default: table)")
    a.set_defaults(func=cmd_audits)

    i = sub.add_parser("import", parents=[common], formatter_class=fmt,
                       help="load a fping CSV or a netwatch folder as a new audit",
                       description="Load a fping CSV, or a whole netwatch/netaudit folder (fping.csv + mtr_*.csv), into a new "
                                   "audit. Timestamps are converted to UTC; naive ones are read as America/Sao_Paulo.",
                       epilog=f"examples:\n  {PROG} import fping.csv\n  {PROG} import ~/netaudit/2026-10-02/netwatch-1425")
    i.add_argument("source", metavar="CSV_OR_FOLDER")
    i.set_defaults(func=cmd_import)

    sub.add_parser("migrate", parents=[common], formatter_class=fmt,
                   help="convert an older database to UTC and the current schema",
                   description="Back up the database, convert every datetime to UTC (naive values are read as "
                               "America/Sao_Paulo) and upgrade the schema. Safe to run more than once.").set_defaults(func=cmd_migrate)
    return p


def main(argv=None):
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    args = build_parser().parse_args(argv)
    env = os.environ.get
    if "home" not in args:
        args.home = env("NW_HOME", str(TOOL_DIR))
    home = Path(args.home).expanduser()
    if "db" not in args:
        args.db = env("NW_DB", str(home / "DataAudit.db"))
    if "tz" not in args:
        args.tz = env("NW_TZ", "br")
    if args.tz not in ("utc", "br"):
        die(f"NW_TZ must be utc or br, not {args.tz!r}", 2)
    args.audits_dir = home / "audits"
    if args.cmd == "run":
        args.targets = args.targets or str(home / "targets.txt")
        args.mtr_targets = args.mtr_targets or str(home / "mtr_targets.txt")
    try:
        args.func(args)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
