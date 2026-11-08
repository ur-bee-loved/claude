import shutil
import sqlite3
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError

import pytest

from lexico import cli, query, web

FIX = Path(__file__).with_name("fixtures")


def test_cli_exit_codes(db_path, capsys):
    assert cli.main(["desconstruir", "sombrinha", "--db", str(db_path), "-l", "pt"]) == 0
    assert "Som-bri-nha" in capsys.readouterr().out
    assert cli.main(["zerlegen", "fluvial", "--db", str(db_path)]) == 2
    assert cli.main(["formas", "xyzzy", "--db", str(db_path)]) == 1
    assert cli.main(["formas", "anjo", "--db", "missing.db"]) == 1


def test_cli_adjective_phrase_uses_last_word(db_path, capsys):
    assert cli.main(["adjective", "aquele", "com", "qualidades", "de", "anjo", "--db", str(db_path)]) == 0
    assert capsys.readouterr().out.startswith("anjo -> Angelical")


@pytest.fixture()
def server(db):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), web.make_handler(db))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def fetch(url):
    with urllib.request.urlopen(url) as r:
        return r.status, r.read().decode("utf-8")


def test_web_page_and_text(server):
    status, body = fetch(server + "/?w=sombrinha&m=desconstruir&l=pt")
    assert status == 200 and "<pre>Som-bri-nha" in body
    _, body = fetch(server + "/txt?w=anjo&m=formas")
    assert body.startswith('Outras formas de "anjo"')


def test_web_escapes_input(server):
    _, body = fetch(server + "/?w=%3Cscript%3E&m=formas&l=pt")
    assert "<script>" not in body and "&lt;script&gt;" in body


def test_web_not_found(server):
    with pytest.raises(HTTPError) as exc:
        fetch(server + "/txt?w=xyzzy&l=pt")
    assert exc.value.code == 404


def test_cli_refuses_database_without_schema_version(tmp_path, capsys):
    old = tmp_path / "old.db"
    conn = sqlite3.connect(old)
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.commit()
    conn.close()
    assert cli.main(["formas", "anjo", "--db", str(old)]) == 1
    assert "rebuild" in capsys.readouterr().err


def test_cli_build_reads_fetch_date(tmp_path):
    data = tmp_path / "data"
    (data / "en").mkdir(parents=True)
    (data / "pt").mkdir()
    shutil.copy(FIX / "en.jsonl", data / "en" / "pt.jsonl")
    shutil.copy(FIX / "pt.jsonl", data / "pt" / "pt.jsonl")
    (data / "fetched_at").write_text("2020-01-02T03:04:05Z\n")
    out = tmp_path / "lexico.db"
    assert cli.main(["build", str(data), "--out", str(out)]) == 0
    conn = query.connect(out)
    assert query.meta(conn)["fetched_at"] == "2020-01-02T03:04:05Z"
    conn.close()
