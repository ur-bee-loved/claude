from __future__ import annotations

import html
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import render
from .text import LANGS

MODE_LABELS = {"desconstruir": "Desconstruir", "adjetivo": "Adjetivo", "sinonimo": "Sinônimos", "formas": "Outras formas"}

PAGE = """<!doctype html>
<html lang="pt">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Léxico</title>
<style>
:root {{ --bg: #fbfaf7; --fg: #1d1d1b; --muted: #6b6a66; --line: #d9d6cf; --accent: #2f5d8a; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg: #161615; --fg: #e9e7e2; --muted: #9c9a94; --line: #3a3936; --accent: #8db4dc; }}
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--fg); font: 16px/1.5 system-ui, sans-serif; }}
main {{ max-width: 46rem; margin: 0 auto; padding: 1.5rem 1rem 3rem; }}
h1 {{ font-size: 1.25rem; margin: 0 0 1rem; }}
form {{ display: flex; flex-wrap: wrap; gap: .5rem; margin-bottom: 1.25rem; }}
input, select, button {{ font: inherit; color: inherit; background: transparent; border: 1px solid var(--line);
  border-radius: 6px; padding: .45rem .6rem; }}
input[name=w] {{ flex: 1 1 12rem; min-width: 0; }}
button {{ border-color: var(--accent); color: var(--accent); cursor: pointer; }}
pre {{ white-space: pre-wrap; word-break: break-word; border-top: 1px solid var(--line); padding-top: 1rem;
  font: 15px/1.6 ui-monospace, SFMono-Regular, Menlo, monospace; }}
.msg {{ color: var(--muted); }}
</style>
</head>
<body><main>
<h1>Léxico</h1>
<form method="get" action="/">
<input name="w" value="{word}" placeholder="palavra" autofocus autocomplete="off" autocapitalize="off">
<select name="m">{modes}</select>
<select name="l">{langs}</select>
<button type="submit">Consultar</button>
</form>
{result}
</main></body></html>
"""


def options(values, labels, selected) -> str:
    return "".join(
        f'<option value="{html.escape(v)}"{" selected" if v == selected else ""}>{html.escape(labels.get(v, v))}</option>'
        for v in values
    )


def make_handler(db):
    lock = threading.Lock()

    def answer(mode: str, word: str, lang: str | None) -> tuple[int, str]:
        with lock:
            try:
                return 200, render.run(db, mode, word, lang)
            except render.Ambiguous as exc:
                return 300, str(exc)
            except render.NotFound as exc:
                return 404, str(exc)

    class Handler(BaseHTTPRequestHandler):
        server_version = "lexico"

        def log_message(self, fmt, *args):
            pass

        def send(self, status: int, body: str, ctype: str):
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", f"{ctype}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            word = q.get("w", "").strip()[:80]
            mode = q.get("m", "desconstruir")
            mode = mode if mode in render.MODES else "desconstruir"
            lang = q.get("l") if q.get("l") in LANGS else None

            if url.path == "/txt":
                if not word:
                    return self.send(400, "use /txt?w=palavra&m=desconstruir&l=pt\n", "text/plain")
                status, text = answer(mode, word, lang)
                return self.send(200 if status == 300 else status, text + "\n", "text/plain")
            if url.path != "/":
                return self.send(404, "não encontrado\n", "text/plain")

            result = ""
            if word:
                status, text = answer(mode, word, lang)
                cls = "" if status == 200 else ' class="msg"'
                result = f"<pre{cls}>{html.escape(text)}</pre>"
            page = PAGE.format(
                word=html.escape(word),
                modes=options(render.MODES, MODE_LABELS, mode),
                langs=options(("",) + LANGS, {"": "língua: automática"}, lang or ""),
                result=result,
            )
            self.send(200, page, "text/html")

    return Handler


def serve(db, host: str, port: int):
    httpd = ThreadingHTTPServer((host, port), make_handler(db))
    print(f"lexico: http://{host}:{port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
