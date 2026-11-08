import threading
import urllib.request
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError

import pytest

from lexico import cli, web


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
