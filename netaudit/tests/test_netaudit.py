import csv
import datetime as dt
import io
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import netaudit as na

TOOL = Path(__file__).resolve().parents[1] / "netaudit.py"
UTC = dt.timezone.utc


@pytest.mark.parametrize("value, expected", [
    ("2026-10-02T14:25:38-03:00", "2026-10-02T17:25:38Z"),
    ("2026-10-02T17:25:38Z", "2026-10-02T17:25:38Z"),
    ("2026-10-02T17:25:38+00:00", "2026-10-02T17:25:38Z"),
    ("2026-10-05T17:39:30", "2026-10-05T20:39:30Z"),
    ("2026-10-05T17:39:30.123456", "2026-10-05T20:39:30Z"),
    ("05/10/2026 21:30:00", "2026-10-06T00:30:00Z"),
    ("1791291225", "2026-10-06T12:53:45Z"),
])
def test_to_utc(value, expected):
    assert na.to_utc(value) == expected


def test_to_utc_is_idempotent():
    once = na.to_utc("2026-10-02T23:59:59-03:00")
    assert once == "2026-10-03T02:59:59Z"
    assert na.to_utc(once) == once


def test_to_utc_rejects_garbage():
    with pytest.raises(ValueError):
        na.to_utc("yesterday")


def test_fmt_dt():
    assert na.fmt_dt("2026-10-03T02:59:59Z", "br") == "02/10/2026 23:59:59"
    assert na.fmt_dt("2026-10-03T02:59:59Z", "utc") == "2026-10-03T02:59:59Z"


def test_fping_parser_blocks_and_cumulative_total():
    p = na.FpingParser()
    t1 = dt.datetime(2026, 10, 6, 12, 0, 0, tzinfo=UTC)
    t2 = t1 + dt.timedelta(seconds=1)
    lines = [
        ("1.1.1.1 : xmt/rcv/%loss = 5/5/0%, min/avg/max = 1/2/3", t1),
        ("[09:00:00]", t1),
        ("1.1.1.1 : xmt/rcv/%loss = 60/60/0%, min/avg/max = 0.9/2.8/16.4", t2),
        ("10.0.0.9 : xmt/rcv/%loss = 60/0/100%", t2),
        ("8.8.8.8 : xmt/rcv/%return = 60/61/101%, min/avg/max = 10/20/30", t2),
        ("1.1.1.1 : xmt/rcv/%loss = 600/600/0%, min/avg/max = 0.9/2.8/16.4", t2),
    ]
    rows = [r for r in (p.feed(line, t) for line, t in lines) if r]
    assert rows == [
        ("2026-10-06T12:00:00Z", "1.1.1.1", 60, 60, 0.0, 0.9, 2.8, 16.4),
        ("2026-10-06T12:00:00Z", "10.0.0.9", 60, 0, 100.0, None, None, None),
        ("2026-10-06T12:00:00Z", "8.8.8.8", 60, 61, 0.0, 10.0, 20.0, 30.0),
    ]


MTR = """Mtr_Version,Start_Time,Status,Host,Hop,Ip,Loss%,Snt, ,Last,Avg,Best,Wrst,StDev,
MTR.0.95,1791291225,OK,8.8.8.8,1,192.168.1.254,0.00,60,0,1.10,2.20,0.90,9.00,1.00
MTR.0.95,1791291225,OK,8.8.8.8,2,???,100.00,60,0,0.00,0.00,0.00,0.00,0.00
Mtr_Version,Start_Time,Status,Host,Hop,Ip,Loss%,Snt, ,Last,Avg,Best,Wrst,StDev,
MTR.0.95,1791292125,OK,8.8.8.8,1,192.168.1.254,5.00,60,0,1.00,3.20,0.90,20.00,2.00
"""


def test_parse_mtr():
    rows = na.parse_mtr(MTR)
    assert len(rows) == 3
    assert rows[0] == ("2026-10-06T12:53:45Z", "8.8.8.8", "OK", 1, "192.168.1.254", 0.0, 60, 1.1, 2.2, 0.9, 9.0, 1.0)
    assert rows[2][0] == "2026-10-06T13:08:45Z"
    assert rows[2][5] == 5.0


def cli(home, *args):
    return subprocess.run([sys.executable, str(TOOL), "--home", str(home), *args], capture_output=True, text=True, check=False)


def legacy_run_dir(tmp_path):
    d = tmp_path / "netwatch-1425"
    d.mkdir()
    (d / "fping.csv").write_text(
        "ts,host,sent,recv,loss_pct,min_ms,avg_ms,max_ms\n"
        "2026-10-02T23:58:38-03:00,10.0.0.9,60,60,0,1,2,3\n"
        "2026-10-02T23:59:38-03:00,10.0.0.9,60,0,100,,,\n"
        "2026-10-03T00:00:38-03:00,10.0.0.9,60,0,100,,,\n"
        "2026-10-03T00:01:38-03:00,10.0.0.9,60,60,0,1,4,5\n"
        "2026-10-02T23:58:38-03:00,10.0.0.1,60,57,5,1,2,900\n"
        "2026-10-02T23:59:38-03:00,10.0.0.1,60,59,2,1,3,3\n"
        "2026-10-03T00:00:38-03:00,10.0.0.1,60,60,0,1,3,3\n"
        "2026-10-03T00:01:38-03:00,10.0.0.1,60,60,0,1,3,3\n")
    (d / "mtr_8.8.8.8.csv").write_text(MTR)
    (d / "meta.txt").write_text("start: 2026-10-02T23:58:00-03:00\n")
    return d


@pytest.fixture
def imported(tmp_path):
    home = tmp_path / "home"
    d = legacy_run_dir(tmp_path)
    r = cli(home, "import", str(d))
    assert r.returncode == 0, r.stdout + r.stderr
    return home, d


def test_import_creates_audit_folder(imported):
    home, _ = imported
    with sqlite3.connect(home / "DataAudit.db") as c:
        assert c.execute("SELECT dateTime FROM RedeAudit ORDER BY id").fetchall()[1] == ("2026-10-03T02:59:38Z",)
        assert c.execute("SELECT count(*) FROM MtrAudit").fetchone() == (3,)
        assert c.execute("SELECT dataHoraBR FROM RedeAuditBR ORDER BY id").fetchone() == ("02/10/2026 23:58:38",)
        folder = c.execute("SELECT folder FROM Audits").fetchone()[0]
    assert re.fullmatch(r"audits/\d{8}T\d{6}Z_audit1", folder)
    f = home / folder
    assert sorted(p.name for p in f.iterdir()) == ["fping.csv", "meta.txt", "mtr_8.8.8.8.csv", "source_meta.txt"]
    assert "2026-10-03T02:59:38Z,10.0.0.9,60,0,100.0,,," in (f / "fping.csv").read_text()


def test_summary(imported):
    home, d = imported
    br = cli(home, "summary").stdout
    assert "10.0.0.9                 02/10/2026 23:59:38 -> 03/10/2026 00:00:38  (2 min)" in br
    assert "   2 ???                    1  100.00     0.00     0.00" in br
    utc = cli(home, "summary", "-a", "1", "--tz", "utc").stdout
    assert "2026-10-03T02:59:38Z -> 2026-10-03T03:00:38Z  (2 min)" in utc
    assert cli(home, "summary", str(d)).stdout.split("\n", 1)[1] == br.split("\n", 1)[1]


def report(home, *args, tz="utc"):
    r = cli(home, "report", *args, "-f", "csv", "-t", tz)
    assert r.returncode == 0, r.stderr
    rows = list(csv.reader(io.StringIO(r.stdout)))
    return [dict(zip(rows[0], row)) for row in rows[1:]]


def test_every_bundled_report_runs(imported):
    home, _ = imported
    listing = cli(home, "report").stdout
    for sql in sorted((TOOL.parent / "sql").glob("*.sql")):
        assert sql.stem in listing
        extra = ["--host", "10.0.0.9"] if sql.stem == "host_timeline" else []
        r = cli(home, "report", sql.stem, *extra)
        assert r.returncode == 0, (sql.stem, r.stderr)


def test_availability_and_loss(imported):
    home, _ = imported
    a = {r["host"]: r for r in report(home, "availability")}
    assert a["10.0.0.9"]["up_minutes_pct"] == "50.0"
    assert a["10.0.0.9"]["delivery_pct"] == "50.0"
    assert a["10.0.0.9"]["outages"] == "1" and a["10.0.0.9"]["longest_outage_min"] == "2"
    assert a["10.0.0.1"]["clean_minutes_pct"] == "50.0"
    loss = {r["host"]: r for r in report(home, "packet_loss")}
    assert loss["10.0.0.1"]["pings_lost"] == "4"
    assert loss["10.0.0.1"]["packet_loss_pct"] == "1.667"
    assert loss["10.0.0.9"]["down_minutes"] == "2" and loss["10.0.0.9"]["partial_loss_minutes"] == "0"


def test_outages_and_time_filters(imported):
    home, _ = imported
    o = report(home, "outages")
    assert o == [{"auditId": "1", "host": "10.0.0.9", "start_utc": "2026-10-03T02:59:38Z",
                  "end_utc": "2026-10-03T03:00:38Z", "minutes": "2", "still_down_at_end": ""}]
    assert len(report(home, "host_timeline", "--host", "10.0.0.9", "--until", "02/10/2026", tz="br")) == 2
    assert len(report(home, "host_timeline", "--host", "10.0.0.9", "--since", "03/10/2026", tz="br")) == 2
    assert len(report(home, "host_timeline", "--host", "10.0.0.9", "--until", "02/10/2026")) == 0
    assert len(report(home, "host_timeline", "--host", "10.0.0.9", "-s", "2026-10-03T03:01:00Z")) == 1


def test_correlated_events(imported):
    home, _ = imported
    ev = report(home, "correlated_events")
    assert [(e["time_utc"], e["affected"], e["with_loss"]) for e in ev] == [("2026-10-03T02:59:38Z", "2", "2")]
    assert report(home, "correlated_events", "-p", "min_share=100") == ev
    assert report(home, "correlated_events", "--host", "10.0.0.1") == []


def test_br_output_and_errors(imported):
    home, _ = imported
    out = cli(home, "report", "outages").stdout
    assert "times in America/Sao_Paulo" in out and "02/10/2026 23:59:38" in out
    r = cli(home, "report", "host_timeline")
    assert r.returncode == 2 and "--host" in r.stderr
    assert cli(home, "report", "nope").returncode == 2
    r = cli(home, "report", "latency", "-a", "9")
    assert r.returncode == 1 and "no audit 9" in r.stderr
    custom = home / "mine.sql"
    custom.write_text("SELECT count(*) AS n FROM RedeAudit WHERE :host IS NULL OR host = :host")
    assert report(home, str(custom), "--host", "10.0.0.1") == [{"n": "4"}]
    r = cli(home, "report", str(custom), "--show-sql")
    assert r.stdout == custom.read_text()


def test_reports_are_read_only(imported):
    home, _ = imported
    evil = home / "evil.sql"
    evil.write_text("DELETE FROM RedeAudit")
    r = cli(home, "report", str(evil))
    assert r.returncode == 1 and "readonly" in r.stderr
    with sqlite3.connect(home / "DataAudit.db") as c:
        assert c.execute("SELECT count(*) FROM RedeAudit").fetchone() == (8,)


@pytest.mark.parametrize("flag", ["-h", "--h", "--help"])
def test_help(tmp_path, flag):
    for cmd in ([], ["report"], ["run"], ["summary"]):
        r = cli(tmp_path, *cmd, flag)
        assert r.returncode == 0 and r.stdout.startswith("usage: netaudit")


def test_version_and_usage_errors(tmp_path):
    r = cli(tmp_path, "-V")
    assert r.returncode == 0 and r.stdout.startswith("netaudit ")
    assert cli(tmp_path).returncode == 2
    assert cli(tmp_path, "nosuch").returncode == 2
    assert cli(tmp_path, "summary", "-a", "x").returncode == 2


def test_run_without_targets_fails_cleanly(tmp_path):
    r = cli(tmp_path, "run")
    assert r.returncode == 1
    assert "targets" in r.stderr or "missing" in r.stderr
    assert not (tmp_path / "audits").exists()


def legacy_db(path):
    c = sqlite3.connect(path)
    c.executescript("""
        CREATE TABLE Audits (auditId INTEGER PRIMARY KEY AUTOINCREMENT, auditDate TEXT NOT NULL, source TEXT);
        CREATE TABLE RedeAudit (id INTEGER PRIMARY KEY AUTOINCREMENT, auditId INTEGER NOT NULL, dateTime TEXT NOT NULL,
            host TEXT NOT NULL, sent INTEGER NOT NULL, recv INTEGER NOT NULL, loss_pct REAL, min_ms REAL, avg_ms REAL, max_ms REAL);
        INSERT INTO Audits VALUES (1, '2026-10-05T17:39:30', 'fping.csv');
        INSERT INTO RedeAudit VALUES (1, 1, '2026-10-02T14:25:38-03:00', 'h', 60, 60, 0, 1, 2, 3);
    """)
    c.commit()
    c.close()


def test_unsanitized_db_is_refused_until_migrated(tmp_path):
    db = tmp_path / "DataAudit.db"
    legacy_db(db)
    r = cli(tmp_path, "audits")
    assert r.returncode == 1 and "migrate" in r.stderr

    r = cli(tmp_path, "migrate")
    assert r.returncode == 0, r.stderr
    assert list(tmp_path.glob("DataAudit.db.bak-*"))
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT auditDate FROM Audits").fetchone() == ("2026-10-05T20:39:30Z",)
        assert c.execute("SELECT dateTime FROM RedeAudit").fetchone() == ("2026-10-02T17:25:38Z",)
        assert c.execute("PRAGMA user_version").fetchone() == (2,)
        assert "folder" in {r[1] for r in c.execute("PRAGMA table_info(Audits)")}

    assert cli(tmp_path, "migrate").returncode == 0
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT dateTime FROM RedeAudit").fetchone() == ("2026-10-02T17:25:38Z",)
    assert "05/10/2026 17:39:30" in cli(tmp_path, "audits").stdout


def test_version1_db_is_upgraded_in_place(tmp_path):
    db = tmp_path / "DataAudit.db"
    legacy_db(db)
    with sqlite3.connect(db) as c:
        c.execute("UPDATE Audits SET auditDate = '2026-10-05T20:39:30Z'")
        c.execute("UPDATE RedeAudit SET dateTime = '2026-10-02T17:25:38Z'")
        c.execute("PRAGMA user_version = 1")
    assert cli(tmp_path, "audits").returncode == 0
    with sqlite3.connect(db) as c:
        assert c.execute("PRAGMA user_version").fetchone() == (2,)
