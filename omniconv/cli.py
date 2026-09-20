"""Command-line interface.

    omniconv convert photo.heic -t jpeg
    omniconv convert *.wav -t mp3 --bitrate 192k -o out/
    omniconv convert paper.docx -t png --dpi 200
    omniconv merge a.png b.jpg c.pdf -o bundle.pdf
    omniconv formats --from pdf
    omniconv route docx png
    omniconv doctor
    omniconv gui
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from omniconv import __version__
from omniconv.core import formats
from omniconv.core.engine import ENGINE, Result, detect_format
from omniconv.core.errors import OmniconvError
from omniconv.core.options import OPTION_SPECS
from omniconv.core.registry import REGISTRY
from omniconv.converters._common import load_pymupdf


def _load_backends() -> None:
    from omniconv.converters import load_all

    load_all()


# ------------------------------------------------------------------ helpers
def _add_option_flags(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("conversion options (each backend honours the ones it understands)")
    for spec in OPTION_SPECS.values():
        flag = "--" + spec.name.replace("_", "-")
        if spec.type is bool:
            group.add_argument(flag, dest=spec.name, action="store_true", default=None, help=spec.help)
        else:
            kwargs: dict[str, Any] = {"dest": spec.name, "help": spec.help, "default": None}
            if spec.choices:
                kwargs["choices"] = spec.choices
            group.add_argument(flag, **kwargs)


def _collect_options(args: argparse.Namespace) -> dict[str, Any]:
    opts: dict[str, Any] = {}
    for name in OPTION_SPECS:
        value = getattr(args, name, None)
        if value is not None:
            opts[name] = value
    for item in getattr(args, "opt", None) or []:
        key, _, value = item.partition("=")
        opts[key.strip().replace("-", "_")] = value
    return opts


def _expand_inputs(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            out.extend(sorted(c for c in path.iterdir() if c.is_file()))
        else:
            out.append(path)
    return out


def _print_result(res: Result, verbose: bool) -> None:
    if res.ok:
        outs = ", ".join(str(o) for o in res.outputs)
        route = f"  [{res.route_text}]" if verbose else ""
        print(f"ok    {res.source} -> {outs}{route}  ({res.seconds:.1f}s)")
    else:
        print(f"FAIL  {res.source}: {res.error}", file=sys.stderr)


# ----------------------------------------------------------------- commands
def cmd_convert(args: argparse.Namespace) -> int:
    _load_backends()
    inputs = _expand_inputs(args.inputs)
    if not inputs:
        print("no input files", file=sys.stderr)
        return 2
    opts = _collect_options(args)
    on_conflict = "overwrite" if args.overwrite else ("error" if args.no_rename else "rename")
    backend = args.backend
    if args.split:
        backend = backend or "pymupdf-split"
    if args.extract_images:
        backend = backend or "pymupdf-images"
    log = (lambda m: print("   " + m)) if args.verbose else None
    if args.output and len(inputs) == 1 and not Path(args.output).is_dir() and not str(args.output).endswith("/"):
        res = ENGINE.convert(inputs[0], args.to, output=args.output, options=opts, on_conflict=on_conflict, log=log, backend=backend)
        _print_result(res, args.verbose)
        return 0 if res.ok else 1
    if not args.to:
        print("a target format is required (-t/--to) when converting several files or into a directory", file=sys.stderr)
        return 2
    outdir = args.output if args.output else None
    results = ENGINE.convert_many(
        inputs, args.to, output_dir=outdir, options=opts, on_conflict=on_conflict, workers=args.jobs,
        progress=lambda r: _print_result(r, args.verbose), log=log, backend=backend,
    )
    failed = sum(1 for r in results if not r.ok)
    if len(results) > 1:
        print(f"{len(results) - failed}/{len(results)} converted")
    return 1 if failed else 0


def cmd_merge(args: argparse.Namespace) -> int:
    _load_backends()
    inputs = _expand_inputs(args.inputs)
    opts = _collect_options(args)
    on_conflict = "overwrite" if args.overwrite else "rename"
    log = (lambda m: print("   " + m)) if args.verbose else None
    res = ENGINE.merge(inputs, args.output, options=opts, on_conflict=on_conflict, log=log)
    _print_result(res, args.verbose)
    return 0 if res.ok else 1


def cmd_formats(args: argparse.Namespace) -> int:
    _load_backends()
    if args.source:
        src = formats.get(args.source)
        routes = REGISTRY.reachable(src.name)
        print(f"{src.name} ({src.description}) can be converted to {len(routes)} formats:")
        for name in sorted(routes, key=lambda n: (formats.FORMATS[n].category, n)):
            f = formats.FORMATS[name]
            via = " -> ".join(s.name for s in routes[name])
            print(f"  {f.category:9} {name:10} via {via}")
        return 0
    if args.target:
        tgt = formats.get(args.target)
        sources = []
        for f in formats.all_formats():
            route = REGISTRY.find_route(f.name, tgt.name)
            if route:
                sources.append((f, route))
        print(f"{tgt.name} ({tgt.description}) can be produced from {len(sources)} formats:")
        for f, route in sorted(sources, key=lambda x: (x[0].category, x[0].name)):
            print(f"  {f.category:9} {f.name:10} via {' -> '.join(s.name for s in route)}")
        return 0
    rows = []
    for f in formats.all_formats(args.category):
        n_out = len(REGISTRY.reachable(f.name))
        n_in = len([c for c in REGISTRY.available() if f.name in c.target_names()])
        if not args.all and n_out == 0 and n_in == 0:
            continue
        rows.append((f.category, f.name, ",".join(f.extensions), n_out, "yes" if n_in else "no", f.description))
    print(f"{'category':9} {'format':11} {'extensions':22} {'targets':>7} {'writable':8} description")
    for row in rows:
        print(f"{row[0]:9} {row[1]:11} {row[2][:22]:22} {row[3]:7d} {row[4]:8} {row[5]}")
    print(f"\n{len(rows)} formats listed (use --all to include formats no installed backend handles)")
    return 0


def cmd_route(args: argparse.Namespace) -> int:
    _load_backends()
    src, tgt = formats.get(args.source), formats.get(args.target)
    route = REGISTRY.find_route(src.name, tgt.name)
    if not route:
        print(ENGINE._no_route_message(src, tgt), file=sys.stderr)
        return 1
    print(f"{src.name} -> {tgt.name}: {len(route)} step(s)")
    for i, step in enumerate(route):
        print(f"  {i + 1}. {step.src} -> {step.tgt}  [{step.name}: {step.conv.description}]")
    alternatives = REGISTRY.direct(src.name, tgt.name)
    if len(alternatives) > 1:
        print("direct alternatives (use --backend NAME): " + ", ".join(c.name for c in alternatives))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    _load_backends()
    print(f"omniconv {__version__} on Python {sys.version.split()[0]}\n")
    print(f"{'converter':22} {'status':11} {'sources':>7} {'targets':>7}  requirements")
    for conv in sorted(REGISTRY.all(), key=lambda c: (not c.available(), c.name)):
        if conv.available():
            status = "available"
            ns, nt = len(conv.source_names()), len(conv.target_names())
            req = ", ".join(r.describe() for r in conv.requires) or "none (pure Python)"
        else:
            status = "MISSING"
            ns = nt = 0
            req = "; ".join(f"{r.describe()}" + (f" -> {r.hint()}" if r.hint() else "") for r in conv.missing())
        print(f"{conv.name:22} {status:11} {ns:7d} {nt:7d}  {req}")
    n_fmt = sum(1 for f in formats.all_formats() if REGISTRY.reachable(f.name))
    pairs = sum(len(REGISTRY.reachable(f.name)) for f in formats.all_formats())
    print(f"\n{len(REGISTRY.available())}/{len(REGISTRY.all())} converters available; {n_fmt} source formats; {pairs} source->target pairs reachable")
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    _load_backends()
    rc = 0
    for p in _expand_inputs(args.inputs):
        try:
            fmt = detect_format(p)
        except OmniconvError as exc:
            print(f"{p}: {exc}", file=sys.stderr)
            rc = 1
            continue
        size = p.stat().st_size
        print(f"{p}: {fmt.name} ({fmt.description}), {fmt.category}, {size} bytes, mime {fmt.mime}")
        details = _describe(p, fmt)
        for k, v in details.items():
            print(f"  {k}: {v}")
        n = len(REGISTRY.reachable(fmt.name))
        print(f"  convertible to {n} formats (omniconv formats --from {fmt.name})")
    return rc


def _describe(path: Path, fmt: formats.Format) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        if fmt.category in ("image",):
            from PIL import Image

            with Image.open(path) as im:
                out["size"] = f"{im.width}x{im.height}"
                out["mode"] = im.mode
                if getattr(im, "n_frames", 1) > 1:
                    out["frames"] = im.n_frames
        elif fmt.category in ("audio", "video"):
            from omniconv.converters.ffmpeg_media import probe

            data = probe(path)
            f = data.get("format", {})
            if f:
                out["container"] = f.get("format_long_name", f.get("format_name"))
                if "duration" in f:
                    out["duration"] = f"{float(f['duration']):.2f}s"
                if "bit_rate" in f:
                    out["bitrate"] = f"{int(f['bit_rate']) // 1000} kb/s"
            for s in data.get("streams", []):
                kind = s.get("codec_type")
                desc = s.get("codec_name", "?")
                if kind == "video":
                    desc += f" {s.get('width')}x{s.get('height')}"
                    if s.get("r_frame_rate"):
                        desc += f" @ {s['r_frame_rate']} fps"
                elif kind == "audio":
                    desc += f" {s.get('sample_rate')} Hz, {s.get('channels')} ch"
                out[f"{kind} stream"] = desc
        elif fmt.name == "pdf":
            fitz = load_pymupdf()

            doc = fitz.open(str(path))
            out["pages"] = doc.page_count
            out["encrypted"] = doc.needs_pass
            meta = doc.metadata or {}
            for k in ("title", "author", "producer"):
                if meta.get(k):
                    out[k] = meta[k]
            doc.close()
    except Exception:
        pass
    return out


def cmd_gui(args: argparse.Namespace) -> int:
    from omniconv.gui import launcher

    if args.toolkit:
        import os

        os.environ["OMNICONV_TOOLKIT"] = args.toolkit
    if getattr(args, "self_test", False):
        return launcher.self_test(args.inputs)
    return launcher.run(args.inputs)


# --------------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="omniconv", description="Convert files between image, audio, video, document, ebook, data, archive and font formats.")
    parser.add_argument("--version", action="version", version=f"omniconv {__version__}")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("convert", help="convert one or more files", description=cmd_convert.__doc__)
    p.add_argument("inputs", nargs="+", help="input files or directories")
    p.add_argument("-t", "--to", help="target format name or extension (e.g. jpeg, mp3, pdf)")
    p.add_argument("-o", "--output", help="output file (single input) or output directory")
    p.add_argument("-j", "--jobs", type=int, default=2, help="parallel conversions (default 2)")
    p.add_argument("--backend", help="force a specific converter (see 'omniconv route')")
    p.add_argument("--split", action="store_true", help="PDF: write one file per page")
    p.add_argument("--extract-images", action="store_true", help="PDF: extract embedded images instead of rendering pages")
    p.add_argument("--overwrite", action="store_true", help="overwrite existing outputs")
    p.add_argument("--no-rename", action="store_true", help="fail instead of renaming when the output exists")
    p.add_argument("--opt", action="append", metavar="KEY=VALUE", help="extra backend option")
    p.add_argument("-v", "--verbose", action="store_true", help="show the route and backend messages")
    _add_option_flags(p)
    p.set_defaults(func=cmd_convert)

    p = sub.add_parser("merge", help="combine several files into one (PDF, TIFF, GIF, archive, audio/video concat)")
    p.add_argument("inputs", nargs="+")
    p.add_argument("-o", "--output", required=True, help="output file; its extension selects the format")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    _add_option_flags(p)
    p.set_defaults(func=cmd_merge)

    p = sub.add_parser("formats", help="list formats and what they can be converted to")
    p.add_argument("--category", choices=formats.CATEGORIES)
    p.add_argument("--from", dest="source", help="show every target reachable from this format")
    p.add_argument("--to", dest="target", help="show every source that can produce this format")
    p.add_argument("--all", action="store_true", help="include formats with no installed backend")
    p.set_defaults(func=cmd_formats)

    p = sub.add_parser("route", help="explain how a conversion would be performed")
    p.add_argument("source")
    p.add_argument("target")
    p.set_defaults(func=cmd_route)

    p = sub.add_parser("doctor", help="show which backends are installed")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("info", help="identify files and show basic properties")
    p.add_argument("inputs", nargs="+")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("gui", help="open the graphical interface")
    p.add_argument("inputs", nargs="*")
    p.add_argument("--toolkit", choices=("gtk", "qt"), help="force a toolkit (default: GTK on Linux, Qt on Windows and macOS)")
    p.add_argument("--self-test", action="store_true", help="build the window, report what happened and exit (for diagnosing an installation)")
    p.set_defaults(func=cmd_gui)
    return parser


def main(argv: list[str] | None = None) -> int:
    from omniconv.core import platform

    platform.configure_console()
    argv = list(sys.argv[1:] if argv is None else argv)
    # Shortcut: "omniconv in.png out.webp" or "omniconv in.png -t webp".
    if argv and argv[0] not in ("convert", "merge", "formats", "route", "doctor", "info", "gui", "-h", "--help", "--version") and Path(argv[0]).exists():
        if len(argv) == 2 and not argv[1].startswith("-"):
            argv = ["convert", argv[0], "-o", argv[1]]
        else:
            argv = ["convert", *argv]
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        if not argv:
            from omniconv.gui import launcher

            if launcher.choose_toolkit():
                return cmd_gui(argparse.Namespace(inputs=[], toolkit=None))
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except OmniconvError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        # Output was piped into a program that stopped reading (e.g. head).
        try:
            sys.stdout.close()
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
