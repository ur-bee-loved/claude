from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import query, render
from .text import LANGS

ALIASES = {
    "desconstruir": ["deconstruct", "descomponer", "zerlegen", "decomposer", "décomposer"],
    "adjetivo": ["adjective", "adjektiv", "adjectif"],
    "sinonimo": ["sinônimo", "sinónimo", "synonym", "synonyme"],
    "formas": ["outras-formas", "other-forms", "otras-formas", "andere-formen", "autres-formes"],
}


def default_db() -> str:
    return os.environ.get("LEXICO_DB", "lexico.db")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="lexico", description="Morfologia lexical a partir do Wiktionary (kaikki.org).")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="build the database from kaikki.org JSONL (laptop)")
    b.add_argument("data_dir", nargs="?", type=Path, help="folder with en/ and pt/ subfolders from fetch.sh")
    b.add_argument("--out", type=Path, default=Path("lexico.db"))
    b.add_argument("--en", action="append", default=[], metavar="FILE", help="English-Wiktionary extract ('-' = stdin)")
    b.add_argument("--pt", action="append", default=[], metavar="FILE", help="Portuguese-Wiktionary extract")
    b.add_argument("--adjetivos", metavar="MD", help="adjetivos-eruditos.md from the lexico skill")
    b.add_argument("--radicais", metavar="MD", help="radicais.md from the lexico skill")
    b.add_argument("--all-forms", action="store_true", help="keep full conjugation/declension tables (much larger)")

    for mode, aliases in ALIASES.items():
        q = sub.add_parser(mode, aliases=aliases, help=f"modo {mode}")
        q.add_argument("word", nargs="+")
        q.add_argument("--lang", "-l", choices=LANGS)
        q.add_argument("--db", default=default_db())
        q.set_defaults(mode=mode)

    s = sub.add_parser("serve", help="web page (Pi)")
    s.add_argument("--db", default=default_db())
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8080)

    i = sub.add_parser("info", help="show database metadata")
    i.add_argument("--db", default=default_db())

    args = p.parse_args(argv)

    if args.cmd == "build":
        from . import build
        en, pt = list(args.en), list(args.pt)
        if args.data_dir:
            found_en, found_pt = build.discover(args.data_dir)
            en += found_en
            pt += found_pt
        if not en and not pt:
            p.error("no input: give a data folder or --en/--pt files")
        build.run(args.out, en, pt, args.adjetivos, args.radicais, args.all_forms)
        return 0

    try:
        db = query.connect(args.db)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    if args.cmd == "info":
        print(json.dumps(query.meta(db), indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "serve":
        from . import web
        web.serve(db, args.host, args.port)
        return 0

    word = args.word[-1] if args.mode == "adjetivo" else " ".join(args.word)
    try:
        print(render.run(db, args.mode, word, args.lang))
    except render.Ambiguous as exc:
        print(exc, file=sys.stderr)
        return 2
    except render.NotFound as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0
