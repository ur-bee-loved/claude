#!/usr/bin/env python3
"""portmap: serves the port visualizer and stores its data in one JSON file.

Standard library only. The browser loads the whole document with
GET /api/network and saves it with PUT /api/network. Each save must carry the
revision it was based on; a stale revision gets HTTP 409 so two open tabs
cannot silently overwrite each other.
"""

import argparse
import datetime as dt
import json
import mimetypes
import os
import re
import sys
import tempfile
import threading
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VERSION = "1.0.0"
PROG = "portmap"
APP_DIR = Path(__file__).resolve().parent
WEB_DIR = APP_DIR / "web"
DATA_FILE = APP_DIR / "data" / "network.json"
EXAMPLE_FILE = APP_DIR / "data" / "network.example.json"
SCHEMA_VERSION = 1
MAX_BODY = 8 * 1024 * 1024
KEEP_BACKUPS = 30
PATCH_RE = re.compile(r"^R\d+ PP\d+ T\d{2,}$")

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")


def die(msg, code=1):
    print(f"{PROG}: error: {msg}", file=sys.stderr)
    sys.exit(code)


def utc_stamp():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _is_int(v, lo, hi):
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def validate(doc):
    """Return a list of problems; an empty list means the document can be saved."""
    errors = []
    if not isinstance(doc, dict):
        return ["document must be a JSON object"]
    if doc.get("version") != SCHEMA_VERSION:
        errors.append(f"version must be {SCHEMA_VERSION}")

    states = doc.get("states")
    state_ids = set()
    if not isinstance(states, list) or not states:
        errors.append("states must be a non-empty list")
    else:
        for i, s in enumerate(states):
            if not isinstance(s, dict) or not all(isinstance(s.get(k), str) and s.get(k) for k in ("id", "label", "color")):
                errors.append(f"states[{i}] needs id, label and color")
            elif s["id"] in state_ids:
                errors.append(f"states[{i}]: duplicate id {s['id']!r}")
            else:
                state_ids.add(s["id"])

    devices = doc.get("devices")
    if not isinstance(devices, list):
        errors.append("devices must be a list")
        devices = []
    ids = set()
    for i, d in enumerate(devices):
        where = f"devices[{i}]"
        if not isinstance(d, dict):
            errors.append(f"{where} must be an object")
            continue
        if not isinstance(d.get("id"), str) or not d["id"]:
            errors.append(f"{where}.id must be a non-empty string")
        elif d["id"] in ids:
            errors.append(f"{where}: duplicate id {d['id']!r}")
        else:
            ids.add(d["id"])
        if not isinstance(d.get("name"), str):
            errors.append(f"{where}.name must be a string")
        if not _is_int(d.get("ports"), 1, 512):
            errors.append(f"{where}.ports must be an integer from 1 to 512")
            continue
        port_data = d.get("port_data", {})
        if not isinstance(port_data, dict):
            errors.append(f"{where}.port_data must be an object")
            continue
        for key, port in port_data.items():
            if not key.isdigit() or not 1 <= int(key) <= d["ports"]:
                errors.append(f"{where}.port_data: port {key!r} is outside 1..{d['ports']}")
            elif not isinstance(port, dict):
                errors.append(f"{where}.port_data[{key}] must be an object")
            elif state_ids and port.get("state", "available") not in state_ids:
                errors.append(f"{where}.port_data[{key}]: unknown state {port.get('state')!r}")

    sizes = {d["id"]: d["ports"] for d in devices
             if isinstance(d, dict) and isinstance(d.get("id"), str) and _is_int(d.get("ports"), 1, 512)}
    for d in devices:
        if not isinstance(d, dict) or not isinstance(d.get("port_data"), dict):
            continue
        for key, port in d["port_data"].items():
            link = port.get("link") if isinstance(port, dict) else None
            if link is None:
                continue
            if not isinstance(link, dict) or link.get("device") not in sizes \
                    or not _is_int(link.get("port"), 1, sizes[link["device"]]):
                errors.append(f"device {d.get('id')!r} port {key}: link points at a missing device or port")

    racks = doc.get("racks")
    if not isinstance(racks, list):
        errors.append("racks must be a list")
        racks = []
    rack_ids = set()
    for i, r in enumerate(racks):
        where = f"racks[{i}]"
        if not isinstance(r, dict) or not isinstance(r.get("id"), str) or not re.fullmatch(r"R\d+", r.get("id", "")):
            errors.append(f"{where}.id must look like R1")
            continue
        if r["id"] in rack_ids:
            errors.append(f"{where}: duplicate id {r['id']!r}")
        rack_ids.add(r["id"])
        if not _is_int(r.get("panels"), 1, 64) or not _is_int(r.get("ports_per_panel"), 1, 96):
            errors.append(f"{where}: panels must be 1..64 and ports_per_panel 1..96")
        if not isinstance(r.get("cells", {}), dict):
            errors.append(f"{where}.cells must be an object")

    endpoints = doc.get("endpoints", [])
    if not isinstance(endpoints, list):
        errors.append("endpoints must be a list")
    else:
        for i, e in enumerate(endpoints):
            if not isinstance(e, dict) or not PATCH_RE.match(str(e.get("patch", ""))):
                errors.append(f"endpoints[{i}].patch must look like 'R1 PP8 T05'")
    return errors


class Store:
    """The data file plus its backups. A lock keeps the revision check and the
    write together, since ThreadingHTTPServer runs requests in parallel."""

    def __init__(self, path, example):
        self.path = Path(path)
        self.example = Path(example)
        self.lock = threading.Lock()

    def load(self):
        """Return (document, source) where source is 'data' or 'example'."""
        for path, source in ((self.path, "data"), (self.example, "example")):
            if path.exists():
                with path.open(encoding="utf-8") as fh:
                    doc = json.load(fh)
                doc.setdefault("revision", 0)
                return doc, source
        return empty_doc(), "example"

    def save(self, doc):
        """Write doc if its revision matches the stored one. Returns the new revision."""
        with self.lock:
            current, source = self.load()
            expected = current.get("revision", 0) if source == "data" else doc.get("revision", 0)
            if doc.get("revision", 0) != expected:
                raise ConflictError(f"revision {doc.get('revision')} is stale; the file is at {expected}")
            doc["revision"] = expected + 1
            doc["saved_utc"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                self._backup()
            fd, tmp = tempfile.mkstemp(prefix=".network-", suffix=".json", dir=self.path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(doc, fh, ensure_ascii=False, indent=2)
                    fh.write("\n")
                os.replace(tmp, self.path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise
            return doc["revision"]

    def _backup(self):
        folder = self.path.parent / "backups"
        folder.mkdir(exist_ok=True)
        target = folder / f"{self.path.stem}-{utc_stamp()}.json"
        n = 1
        while target.exists():
            n += 1
            target = folder / f"{self.path.stem}-{utc_stamp()}-{n}.json"
        target.write_bytes(self.path.read_bytes())
        old = sorted(folder.glob(f"{self.path.stem}-*.json"))
        for p in old[:-KEEP_BACKUPS]:
            p.unlink()


class ConflictError(Exception):
    pass


def empty_doc():
    return {
        "version": SCHEMA_VERSION,
        "revision": 0,
        "site": "New site",
        "states": [{"id": "available", "label": "Disponível", "color": "#8a96ab", "pattern": "dashed"}],
        "devices": [],
        "racks": [],
        "endpoints": [],
    }


def make_handler(store, web_dir, quiet=False):
    web_root = Path(web_dir).resolve()

    class Handler(BaseHTTPRequestHandler):
        server_version = f"{PROG}/{VERSION}"

        def log_message(self, fmt, *args):
            if not quiet:
                sys.stderr.write(f"{self.address_string()} - {fmt % args}\n")

        def send_json(self, status, payload, headers=None):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/api/network":
                try:
                    doc, source = store.load()
                except (OSError, json.JSONDecodeError) as exc:
                    return self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"cannot read data file: {exc}"})
                return self.send_json(HTTPStatus.OK, doc, {"X-Portmap-Source": source})
            self.serve_static(path)

        def do_PUT(self):
            if self.path.split("?", 1)[0] != "/api/network":
                return self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                return self.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE if length else HTTPStatus.BAD_REQUEST,
                                      {"error": f"body must be 1 byte to {MAX_BODY} bytes"})
            try:
                doc = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                return self.send_json(HTTPStatus.BAD_REQUEST, {"error": f"invalid JSON: {exc}"})
            problems = validate(doc)
            if problems:
                return self.send_json(HTTPStatus.BAD_REQUEST, {"error": "; ".join(problems[:5]), "problems": problems})
            try:
                revision = store.save(doc)
            except ConflictError as exc:
                return self.send_json(HTTPStatus.CONFLICT, {"error": str(exc)})
            except OSError as exc:
                return self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"cannot write data file: {exc}"})
            self.send_json(HTTPStatus.OK, {"revision": revision})

        def serve_static(self, path):
            path = urllib.parse.unquote(path)
            rel = "index.html" if path in ("", "/") else path.lstrip("/")
            target = (web_root / rel).resolve()
            if not target.is_relative_to(web_root) or not target.is_file():
                return self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            body = target.read_bytes()
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype == "application/json":
                ctype += "; charset=utf-8"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def build_parser():
    p = argparse.ArgumentParser(prog=PROG, description="Serve the switch-port visualizer and save its data.")
    p.add_argument("--h", action="help", help=argparse.SUPPRESS)
    p.add_argument("-V", "--version", action="version", version=f"{PROG} {VERSION}")
    p.add_argument("--host", default=os.environ.get("PORTMAP_HOST", "127.0.0.1"),
                   help="address to listen on (default 127.0.0.1; use 0.0.0.0 to share on the LAN)")
    p.add_argument("-p", "--port", type=int, default=int(os.environ.get("PORTMAP_PORT", "8765")), help="default 8765")
    p.add_argument("-d", "--data", type=Path, default=Path(os.environ.get("PORTMAP_DATA", DATA_FILE)),
                   help="data file (default data/network.json)")
    p.add_argument("--open", action="store_true", help="open the page in the default browser")
    p.add_argument("-q", "--quiet", action="store_true", help="do not log requests")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    store = Store(args.data, EXAMPLE_FILE)
    try:
        server = ThreadingHTTPServer((args.host, args.port), make_handler(store, WEB_DIR, args.quiet))
    except OSError as exc:
        die(f"cannot listen on {args.host}:{args.port}: {exc.strerror or exc}")
    host = "localhost" if args.host in ("127.0.0.1", "0.0.0.0", "::") else args.host
    url = f"http://{host}:{server.server_address[1]}/"
    source = "data" if store.path.exists() else "example (no data file yet)"
    print(f"{PROG} {VERSION}: {url}  data: {store.path} [{source}]  Ctrl-C to stop", file=sys.stderr)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(file=sys.stderr)
        return 130
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
