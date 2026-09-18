"""Vector graphics: SVG, PostScript, EPS, WMF/EMF and bitmap tracing."""

from __future__ import annotations

import gzip
import shutil
from pathlib import Path

from omniconv.core.engine import Job
from omniconv.core.errors import ConversionError
from omniconv.core.procs import run
from omniconv.core.registry import converter
from omniconv.core.requirements import Module, Tool
from omniconv.converters._common import PYMUPDF, load_pymupdf, parse_colour

RSVG = Tool("rsvg-convert", package="librsvg2-bin")
INKSCAPE = Tool("inkscape", package="inkscape")
POTRACE = Tool("potrace", package="potrace")


@converter("svgz", ("svg", "svgz"), ("svg", "svgz"), cost=1, description="Compress or decompress SVG", predicate=lambda s, t: s != t)
def svgz_convert(job: Job) -> list[Path]:
    if job.tgt_format.name == "svgz":
        with open(job.source, "rb") as src, gzip.open(job.target, "wb") as dst:
            shutil.copyfileobj(src, dst)
    else:
        with gzip.open(job.source, "rb") as src, open(job.target, "wb") as dst:
            shutil.copyfileobj(src, dst)
    return [job.target]


@converter(
    "rsvg-convert",
    ("svg", "svgz"),
    ("png", "pdf", "ps", "eps", "svg"),
    requires=(RSVG,),
    cost=8,
    options=("width", "height", "dpi", "background"),
    description="Render SVG with librsvg",
    predicate=lambda s, t: not (s == "svg" and t == "svg"),
)
def rsvg_convert(job: Job) -> list[Path]:
    exe = RSVG.path()
    assert exe
    fmt = {"png": "png", "pdf": "pdf", "ps": "ps", "eps": "eps", "svg": "svg"}[job.tgt_format.name]
    cmd = [exe, "-f", fmt, "-o", str(job.target)]
    if job.opt("width"):
        cmd += ["-w", str(int(job.opt("width")))]
    if job.opt("height"):
        cmd += ["-h", str(int(job.opt("height")))]
    if job.opt("dpi"):
        cmd += ["-d", str(int(job.opt("dpi"))), "-p", str(int(job.opt("dpi")))]
    if job.opt("background"):
        cmd += ["-b", str(job.opt("background"))]
    if job.opt("width") is None and job.opt("height") is None:
        cmd += ["--keep-aspect-ratio"]
    cmd.append(str(job.source))
    run(cmd)
    return [job.target]


@converter(
    "cairosvg",
    ("svg", "svgz"),
    ("png", "pdf", "ps", "eps", "svg"),
    requires=(Module("cairosvg", "cairosvg"),),
    cost=11,
    options=("width", "height", "dpi", "background"),
    description="Render SVG with CairoSVG",
    predicate=lambda s, t: not (s == "svg" and t == "svg"),
)
def cairosvg_convert(job: Job) -> list[Path]:
    import cairosvg

    func = {"png": cairosvg.svg2png, "pdf": cairosvg.svg2pdf, "ps": cairosvg.svg2ps, "eps": cairosvg.svg2eps, "svg": cairosvg.svg2svg}[job.tgt_format.name]
    kwargs = {}
    if job.opt("width"):
        kwargs["output_width"] = int(job.opt("width"))
    if job.opt("height"):
        kwargs["output_height"] = int(job.opt("height"))
    if job.opt("dpi"):
        kwargs["dpi"] = int(job.opt("dpi"))
    if job.opt("background"):
        c = parse_colour(job.opt("background"))
        kwargs["background_color"] = "#%02x%02x%02x" % tuple(c[:3])
    func(url=str(job.source), write_to=str(job.target), **kwargs)
    return [job.target]


_INK_SOURCES = ("svg", "svgz", "pdf", "eps", "ps", "ai", "wmf", "emf", "dxf", "cgm", "png", "jpeg", "gif", "bmp", "tiff", "webp")
_INK_TARGETS = ("svg", "png", "pdf", "ps", "eps", "emf", "wmf", "dxf", "xaml", "svgz")


@converter(
    "inkscape",
    _INK_SOURCES,
    ("svg", "png", "pdf", "ps", "eps", "emf", "wmf", "dxf", "svgz"),
    requires=(INKSCAPE,),
    cost=20,
    options=("width", "height", "dpi", "background", "pages"),
    description="Vector conversion with Inkscape",
    predicate=lambda s, t: s != t,
)
def inkscape_convert(job: Job) -> list[Path]:
    exe = INKSCAPE.path()
    assert exe
    cmd = [exe, f"--export-type={job.tgt_format.extension}", f"--export-filename={job.target}"]
    if job.opt("width"):
        cmd.append(f"--export-width={int(job.opt('width'))}")
    if job.opt("height"):
        cmd.append(f"--export-height={int(job.opt('height'))}")
    if job.opt("dpi"):
        cmd.append(f"--export-dpi={int(job.opt('dpi'))}")
    if job.opt("background"):
        cmd.append(f"--export-background={job.opt('background')}")
    if job.src_format.name == "pdf":
        pages = job.opt("pages")
        cmd.append(f"--pdf-page={str(pages).split('-')[0].split(',')[0] if pages else 1}")
    if job.tgt_format.name == "svg":
        cmd.append("--export-plain-svg")
    cmd.append(str(job.source))
    run(cmd, env={"HOME": str(job.workdir)})
    return [job.target]


@converter(
    "potrace",
    ("pbm", "pgm", "ppm", "bmp"),
    ("svg", "pdf", "eps", "ps", "dxf", "xbm"),
    requires=(POTRACE,),
    cost=12,
    description="Trace a bitmap into vector outlines with potrace",
)
def potrace_convert(job: Job) -> list[Path]:
    exe = POTRACE.path()
    assert exe
    backend = {"svg": "svg", "pdf": "pdf", "eps": "eps", "ps": "postscript", "dxf": "dxf", "xbm": "xbm"}[job.tgt_format.name]
    run([exe, "-b", backend, "-o", str(job.target), str(job.source)])
    return [job.target]


@converter(
    "pymupdf-svg",
    ("svg",),
    ("png", "jpeg", "ppm", "pgm", "pam"),
    requires=(PYMUPDF,),
    cost=14,
    options=("dpi", "width", "height", "grayscale"),
    description="Rasterise SVG with MuPDF",
)
def mupdf_svg(job: Job) -> list[Path]:
    fitz = load_pymupdf()

    doc = fitz.open(str(job.source))
    page = doc[0]
    dpi = int(job.opt("dpi", 150) or 150)
    w, h = job.opt("width"), job.opt("height")
    if w or h:
        zx = int(w) / page.rect.width if w else None
        zy = int(h) / page.rect.height if h else None
        matrix = fitz.Matrix(zx or zy, zy or zx)
    else:
        matrix = fitz.Matrix(dpi / 72, dpi / 72)
    cs = fitz.csGRAY if job.opt("grayscale") or job.tgt_format.name == "pgm" else fitz.csRGB
    pix = page.get_pixmap(matrix=matrix, colorspace=cs, alpha=job.tgt_format.name in ("png", "pam"))
    if job.tgt_format.name == "jpeg":
        pix.save(str(job.target), output="jpg")
    else:
        pix.save(str(job.target))
    doc.close()
    return [job.target]
