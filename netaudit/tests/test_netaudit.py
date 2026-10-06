import datetime as dt
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


def cli(*args):
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, check=False)


def legacy_run_dir(tmp_path):
    d = tmp_path / "netwatch-1425"
    d.mkdir()
    (d / "fping.csv").write_text(
        "ts,host,sent,recv,loss_pct,min_ms,avg_ms,max_ms\n"
        "2026-10-02T23:58:38-03:00,10.0.0.9,60,60,0,1,2,3\n"
        "2026-10-02T23:59:38-03:00,10.0.0.9,60,0,100,,,\n"
        "2026-10-03T00:00:38-03:00,10.0.0.9,60,0,100,,,\n"
        "2026-10-03T00:01:38-03:00,10.0.0.9,60,60,0,1,4,5\n")
    (d / "mtr_8.8.8.8.csv").write_text(MTR)
    return d


def test_import_and_summary(tmp_path):
    db = tmp_path / "a.db"
    d = legacy_run_dir(tmp_path)
    r = cli("--db", str(db), "import", str(d))
    assert r.returncode == 0, r.stdout + r.stderr
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT dateTime FROM RedeAudit ORDER BY id").fetchall()[1] == ("2026-10-03T02:59:38Z",)
        assert c.execute("SELECT count(*) FROM MtrAudit").fetchone() == (3,)
        assert c.execute("SELECT dataHoraBR FROM RedeAuditBR ORDER BY id").fetchone() == ("02/10/2026 23:58:38",)

    br = cli("--db", str(db), "summary").stdout
    assert "10.0.0.9                 02/10/2026 23:59:38 -> 03/10/2026 00:00:38  (2 min)" in br
    assert "   2 ???                    1  100.00     0.00     0.00" in br
    utc = cli("summary", "--db", str(db), "--tz", "utc").stdout
    assert "2026-10-03T02:59:38Z -> 2026-10-03T03:00:38Z  (2 min)" in utc
    assert cli("summary", str(d)).stdout.split("\n", 1)[1] == br.split("\n", 1)[1]


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
    db = tmp_path / "old.db"
    legacy_db(db)
    r = cli("--db", str(db), "audits")
    assert r.returncode != 0 and "migrate" in r.stderr

    r = cli("--db", str(db), "migrate")
    assert r.returncode == 0, r.stderr
    assert list(tmp_path.glob("old.db.bak-*"))
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT auditDate FROM Audits").fetchone() == ("2026-10-05T20:39:30Z",)
        assert c.execute("SELECT dateTime FROM RedeAudit").fetchone() == ("2026-10-02T17:25:38Z",)
        assert c.execute("PRAGMA user_version").fetchone() == (1,)

    assert cli("--db", str(db), "migrate").returncode == 0
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT dateTime FROM RedeAudit").fetchone() == ("2026-10-02T17:25:38Z",)
    assert "05/10/2026 17:39:30" in cli("--db", str(db), "audits").stdout
