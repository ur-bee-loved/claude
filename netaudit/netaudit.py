#!/usr/bin/env python3
"""netaudit: network monitoring (fping + mtr) and SQLite audit storage in one tool.

All datetimes are stored in UTC as YYYY-MM-DDTHH:MM:SSZ. They are displayed
either in UTC or in Brazil's format (dd/mm/aaaa HH:MM:SS, America/Sao_Paulo).
"""

import argparse
import csv
import datetime as dt
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

UTC = dt.timezone.utc
SCHEMA_VERSION = 1
UTC_FMT = "%Y-%m-%dT%H:%M:%SZ"
BR_FMT = "%d/%m/%Y %H:%M:%S"


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
        for fmt in (BR_FMT, "%d/%m/%Y %H:%M"):
            try:
                d = dt.datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"unrecognised datetime: {value!r}")
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
        print(f"Erro na conexão: {e}")
        return None


def create_schema(conn):
    try:
        cursor = conn.cursor()
        cursor.executescript('''
            CREATE TABLE IF NOT EXISTS Audits (
                auditId   INTEGER PRIMARY KEY AUTOINCREMENT,
                auditDate TEXT NOT NULL,
                source    TEXT
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
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Erro ao criar schema: {e}")
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
    """Open the database, create the schema, and refuse to mix UTC rows with unsanitized ones."""
    conn = get_db_connection(path)
    if conn is None:
        sys.exit(1)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < SCHEMA_VERSION and unsanitized_count(conn):
        conn.close()
        sys.exit(f"{path} has datetimes not yet in UTC; run: {Path(sys.argv[0]).name} --db {path} migrate")
    if not create_schema(conn):
        sys.exit(1)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    return conn


def create_audit(conn, audit_date, source):
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO Audits (auditDate, source) VALUES (?, ?)",
            (audit_date.strftime(UTC_FMT), source),
        )
        conn.commit()
        audit_id = cursor.lastrowid
        print(f"Audit criado: auditId={audit_id} ({audit_date.strftime(UTC_FMT)})")
        return audit_id
    except sqlite3.Error as e:
        print(f"Erro ao criar audit: {e}")
        return None


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


# ---------------------------------------------------------------- import

def load_csv(conn, audit_id, csv_path):
    with open(csv_path, mode="r", newline="") as file:
        reader = csv.reader(file)
        next(reader, None)  # skip header
        raw_rows = [r for r in reader if r]
    rows = [(audit_id, *parse_row(r)) for r in raw_rows]
    conn.executemany(FPING_INSERT, rows)
    return len(rows)


def load_mtr(conn, audit_id, mtr_path):
    rows = [(audit_id, *r) for r in parse_mtr(Path(mtr_path).read_text())]
    conn.executemany(MTR_INSERT, rows)
    return len(rows)


def cmd_import(args):
    src = Path(args.source)
    if src.is_dir():
        fping_csv = src / "fping.csv"
        mtr_files = sorted(src.glob("mtr_*.csv"))
    else:
        fping_csv, mtr_files = src, []
    if not fping_csv.is_file():
        sys.exit(f"Uso da ferramenta: {Path(sys.argv[0]).name} import <arquivo.csv | run_dir>")

    conn = open_db(args.db)
    try:
        with conn:
            cur = conn.execute("INSERT INTO Audits (auditDate, source) VALUES (?, ?)",
                               (now_utc().strftime(UTC_FMT), str(src.resolve())))
            audit_id = cur.lastrowid
            n = load_csv(conn, audit_id, fping_csv)
            m = sum(load_mtr(conn, audit_id, f) for f in mtr_files)
    except (OSError, csv.Error, ValueError, sqlite3.Error) as e:
        print(f"Erro ao processar CSV: {e}")
        sys.exit(1)
    finally:
        conn.close()
    print(f"{n} linhas gravadas para auditId={audit_id}." + (f" ({m} linhas mtr)" if mtr_files else ""))
    print(f"Audit {audit_id} concluído com sucesso.")


# ---------------------------------------------------------------- migrate

def cmd_migrate(args):
    path = Path(args.db)
    if not path.is_file():
        sys.exit(f"no database: {path}")
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
        sys.exit(f"migration failed, database left unchanged: {e}")
    left = unsanitized_count(src)
    if left:
        src.close()
        sys.exit(f"{left} values still not in UTC format")
    if not create_schema(src):
        sys.exit(1)
    src.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    src.close()
    print("ok: all datetimes stored as UTC (YYYY-MM-DDTHH:MM:SSZ)")


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
            sys.exit(f"missing: {c} (sudo dnf install {c})")
    targets = Path(args.targets)
    mtr_targets = Path(args.mtr_targets)
    if not targets.is_file() or targets.stat().st_size == 0:
        sys.exit(f"no targets file: {targets}")
    has_mtr = mtr_targets.is_file() and mtr_targets.stat().st_size > 0

    if not os.environ.get("NW_INHIBITED") and shutil.which("systemd-inhibit"):
        env = dict(os.environ, NW_INHIBITED="1")
        os.execvpe("systemd-inhibit", [
            "systemd-inhibit", "--what=sleep:idle", "--who=netwatch", "--why=network monitoring",
            sys.executable, os.path.abspath(__file__), *sys.argv[1:]], env)

    start = now_utc()
    local = start if args.tz == "utc" else start.astimezone(BR)
    suffix = "Z" if args.tz == "utc" else local.strftime("%z")
    run_dir = Path(args.dir) / local.strftime("%Y-%m-%d") / f"netwatch-{local.strftime('%H%M')}{suffix}"
    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(targets, run_dir / "targets.txt")
    if has_mtr:
        shutil.copy(mtr_targets, run_dir / "mtr_targets.txt")
    meta = run_dir / "meta.txt"
    with open(meta, "w") as f:
        f.write(f"start: {start.strftime(UTC_FMT)} ({fmt_dt(start, 'br')} {getattr(BR, 'key', BR)})\n")
        f.write(f"host: {socket.gethostname()}\n")
        f.write(f"route: {default_route()}\n")
        f.write(f"fping: {tool_version('fping')}\n")
        f.write(f"mtr: {tool_version('mtr')}\n")
        f.write(f"fping period {args.fping_period} ms, report every {args.fping_report} s; "
                f"mtr every {args.mtr_every} s, {args.mtr_count} cycles\n")

    audit_id = None
    if not args.no_db:
        conn = open_db(args.db)
        audit_id = create_audit(conn, start, str(run_dir))
        conn.close()
        if audit_id is None:
            sys.exit(1)

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
            w.writerow(["ts", "host", "sent", "recv", "loss_pct", "min_ms", "avg_ms", "max_ms"])
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
    print(f"stopped; summary: {Path(sys.argv[0]).name} summary {run_dir}")


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
            sys.exit(f"no fping.csv in {d}")
        print(f"source: {d}")
        print_summary(fping_rows_from_csv(d / "fping.csv"), mtr_rows_from_dir(d), args.tz)
        return

    conn = open_db(args.db)
    audit = args.audit
    if audit is None:
        audit = conn.execute("SELECT max(auditId) FROM Audits").fetchone()[0]
    info = conn.execute("SELECT auditDate, source FROM Audits WHERE auditId = ?", (audit,)).fetchone()
    if info is None:
        sys.exit(f"no audit {audit} in {args.db}")
    fping_rows = conn.execute(
        "SELECT dateTime, host, sent, recv, loss_pct, min_ms, avg_ms, max_ms FROM RedeAudit "
        "WHERE auditId = ? ORDER BY dateTime, id", (audit,)).fetchall()
    mtr_rows = conn.execute(
        "SELECT dateTime, target, status, hop, ip, loss_pct, sent, last_ms, avg_ms, best_ms, worst_ms, stdev_ms "
        "FROM MtrAudit WHERE auditId = ? ORDER BY dateTime, id", (audit,)).fetchall()
    conn.close()
    print(f"audit {audit}: created {fmt_dt(info[0], args.tz)}, source {info[1]}")
    print_summary(fping_rows, mtr_rows, args.tz)


def cmd_audits(args):
    conn = open_db(args.db)
    rows = conn.execute(
        "SELECT a.auditId, a.auditDate, a.source, count(r.id), min(r.dateTime), max(r.dateTime) "
        "FROM Audits a LEFT JOIN RedeAudit r USING (auditId) GROUP BY a.auditId ORDER BY a.auditId").fetchall()
    conn.close()
    print(f"times in {tz_label(args.tz)}")
    print(f"{'id':>4} {'created':<20} {'rows':>7} {'first':<20} {'last':<20} source")
    for aid, created, source, n, first, last in rows:
        f = lambda v: fmt_dt(v, args.tz) if v else "-"
        print(f"{aid:>4} {f(created):<20} {n:>7} {f(first):<20} {f(last):<20} {source}")


# ---------------------------------------------------------------- cli

def main():
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    home = Path.home()
    env = os.environ.get
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", default=argparse.SUPPRESS,
                        help="SQLite database (env NW_DB, default ~/netaudit/DataAudit.db)")
    common.add_argument("--tz", choices=("utc", "br"), default=argparse.SUPPRESS,
                        help="display time zone: utc (ISO 8601 Z) or br (dd/mm/aaaa, America/Sao_Paulo); env NW_TZ, default br")
    p = argparse.ArgumentParser(prog="netaudit", description=__doc__.splitlines()[0], parents=[common])
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", parents=[common], help="monitor with fping and mtr, writing CSV files and the database")
    r.add_argument("--targets", default=env("NW_TARGETS", str(home / "netwatch" / "targets.txt")))
    r.add_argument("--mtr-targets", default=env("NW_MTR_TARGETS", str(home / "netwatch" / "mtr_targets.txt")))
    r.add_argument("--dir", default=env("NW_DIR", str(home / "netaudit")), help="where run directories are created")
    r.add_argument("--fping-period", type=int, default=int(env("NW_FPING_PERIOD", "1000")), help="ms between pings")
    r.add_argument("--fping-report", type=int, default=int(env("NW_FPING_REPORT", "60")), help="s between reports")
    r.add_argument("--mtr-every", type=int, default=int(env("NW_MTR_EVERY", "900")), help="s between mtr rounds")
    r.add_argument("--mtr-count", type=int, default=int(env("NW_MTR_COUNT", "60")), help="cycles per mtr round")
    r.add_argument("--no-db", action="store_true", help="only write CSV files")
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("summary", parents=[common], help="summarise a run directory or an audit in the database")
    s.add_argument("run_dir", nargs="?")
    s.add_argument("--audit", type=int, help="audit id (default: latest)")
    s.set_defaults(func=cmd_summary)

    i = sub.add_parser("import", parents=[common], help="load a fping CSV or a whole run directory into the database")
    i.add_argument("source")
    i.set_defaults(func=cmd_import)

    sub.add_parser("audits", parents=[common], help="list audits in the database").set_defaults(func=cmd_audits)
    sub.add_parser("migrate", parents=[common], help="convert every datetime in an existing database to UTC (backs it up first)").set_defaults(func=cmd_migrate)

    args = p.parse_args()
    if "db" not in args:
        args.db = env("NW_DB", str(home / "netaudit" / "DataAudit.db"))
    if "tz" not in args:
        args.tz = env("NW_TZ", "br")
    if args.cmd in ("run", "import") and not args.__dict__.get("no_db"):
        Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    args.func(args)


if __name__ == "__main__":
    main()
