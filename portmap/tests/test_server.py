import copy
import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
import server as srv

EXAMPLE = json.loads((APP / "data" / "network.example.json").read_text(encoding="utf-8"))


def test_example_is_valid():
    assert srv.validate(EXAMPLE) == []


@pytest.mark.parametrize("mutate, fragment", [
    (lambda d: d.update(version=2), "version"),
    (lambda d: d["devices"].append(copy.deepcopy(d["devices"][0])), "duplicate id"),
    (lambda d: d["devices"][0].update(ports=0), "ports"),
    (lambda d: d["devices"][1]["port_data"].update({"99": {}}), "outside"),
    (lambda d: d["devices"][1]["port_data"]["3"].update(state="nope"), "unknown state"),
    (lambda d: d["devices"][1]["port_data"]["1"].update(link={"device": "ghost", "port": 1}), "link"),
    (lambda d: d["devices"][1]["port_data"]["1"].update(link={"device": "router", "port": 99}), "link"),
    (lambda d: d["racks"][0].update(id="rack1"), "R1"),
    (lambda d: d["endpoints"][0].update(patch="PP1 T3"), "endpoints[0]"),
])
def test_validate_rejects(mutate, fragment):
    doc = copy.deepcopy(EXAMPLE)
    mutate(doc)
    assert any(fragment in e for e in srv.validate(doc))


def test_store_falls_back_to_example(tmp_path):
    store = srv.Store(tmp_path / "network.json", APP / "data" / "network.example.json")
    doc, source = store.load()
    assert source == "example"
    assert doc["site"] == EXAMPLE["site"]


def test_store_revisions_and_backups(tmp_path):
    store = srv.Store(tmp_path / "network.json", tmp_path / "missing.json")
    doc = copy.deepcopy(EXAMPLE)
    assert store.save(doc) == 1
    assert store.save(copy.deepcopy(doc)) == 2
    stale = copy.deepcopy(EXAMPLE)
    stale["revision"] = 1
    with pytest.raises(srv.ConflictError):
        store.save(stale)
    saved, source = store.load()
    assert (source, saved["revision"]) == ("data", 2)
    assert len(list((tmp_path / "backups").glob("network-*.json"))) == 1
    assert not list(tmp_path.glob(".network-*"))


@pytest.fixture
def live(tmp_path):
    store = srv.Store(tmp_path / "network.json", APP / "data" / "network.example.json")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.make_handler(store, srv.WEB_DIR, quiet=True))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", store
    httpd.shutdown()
    httpd.server_close()


def request(url, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, dict(res.headers), res.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def test_http_static_and_api(live):
    base, store = live
    status, headers, body = request(base + "/")
    assert status == 200 and b"<title>Portmap</title>" in body
    status, headers, _ = request(base + "/js/main.js")
    assert status == 200 and headers["Content-Type"].startswith("text/javascript")
    status, headers, body = request(base + "/api/network")
    assert status == 200 and headers["X-Portmap-Source"] == "example"

    doc = json.loads(body)
    doc["site"] = "Changed"
    status, _, body = request(base + "/api/network", "PUT", doc)
    assert status == 200 and json.loads(body)["revision"] == 1
    assert json.loads(store.path.read_text(encoding="utf-8"))["site"] == "Changed"

    status, _, body = request(base + "/api/network", "PUT", doc)
    assert status == 409

    doc["revision"] = 1
    doc["version"] = 7
    status, _, body = request(base + "/api/network", "PUT", doc)
    assert status == 400 and "version" in json.loads(body)["error"]


@pytest.mark.parametrize("path", ["/../server.py", "/%2e%2e/server.py", "/css/../../server.py", "/nope.js"])
def test_http_blocks_paths_outside_web(live, path):
    base, _ = live
    req = urllib.request.Request(base + path)
    req.full_url = base + path
    try:
        with urllib.request.urlopen(req) as res:
            status = res.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    assert status == 404


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as exc:
        srv.main(["--version"])
    assert exc.value.code == 0
    assert srv.VERSION in capsys.readouterr().out
