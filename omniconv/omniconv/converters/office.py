"""Office documents through LibreOffice in headless mode.

LibreOffice is slow to start (a few seconds per call) but it is the only
free tool that reads the full range of legacy office formats, so it is
registered with a high cost and used when nothing lighter applies.
Each invocation gets a private user profile directory so parallel
conversions do not fight over the profile lock.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from omniconv.core.engine import Job
from omniconv.core.errors import ConversionError
from omniconv.core.procs import run
from omniconv.core.registry import converter
from omniconv.core.requirements import Tool

SOFFICE = Tool("soffice", ("libreoffice", "loffice"), package="libreoffice")

WRITER_SOURCES = ("doc", "docx", "odt", "fodt", "rtf", "txt", "html", "wps", "wpd", "abw", "pages", "sxw", "uot", "dotx", "md")
WRITER_TARGETS = ("pdf", "docx", "doc", "odt", "fodt", "rtf", "txt", "html", "epub", "png", "jpeg", "xml", "md")
CALC_SOURCES = ("xls", "xlsx", "ods", "csv", "tsv", "numbers")
CALC_TARGETS = ("pdf", "xlsx", "xls", "ods", "csv", "html", "png", "jpeg")
IMPRESS_SOURCES = ("ppt", "pptx", "odp", "key")
IMPRESS_TARGETS = ("pdf", "pptx", "ppt", "odp", "png", "jpeg", "svg", "gif", "bmp", "tiff", "webp", "html", "odg")
DRAW_SOURCES = ("odg", "vsd", "pub", "wmf", "emf", "cgm", "dxf", "svg")
DRAW_TARGETS = ("pdf", "svg", "png", "jpeg", "odg", "emf", "wmf", "eps", "bmp", "gif", "tiff", "webp")

# Explicit export filters where the extension alone is ambiguous.
_FILTERS: dict[tuple[str, str], str] = {
    ("writer", "pdf"): "pdf:writer_pdf_Export",
    ("writer", "txt"): "txt:Text (encoded):UTF8",
    ("writer", "html"): "html:XHTML Writer File:UTF8",
    ("writer", "xml"): "xml:DocBook File",
    ("writer", "png"): "png:writer_png_Export",
    ("writer", "jpeg"): "jpg:writer_jpg_Export",
    ("writer", "epub"): "epub:EPUB",
    ("writer", "md"): "md:Markdown",
    ("calc", "pdf"): "pdf:calc_pdf_Export",
    ("calc", "csv"): "csv:Text - txt - csv (StarCalc):44,34,76,1,,0,false,true,false,false,false,-1",
    ("calc", "html"): "html:HTML (StarCalc)",
    ("calc", "png"): "png:calc_png_Export",
    ("calc", "jpeg"): "jpg:calc_jpg_Export",
    ("impress", "pdf"): "pdf:impress_pdf_Export",
    ("impress", "png"): "png:impress_png_Export",
    ("impress", "jpeg"): "jpg:impress_jpg_Export",
    ("impress", "svg"): "svg:impress_svg_Export",
    ("impress", "html"): "html:impress_html_Export",
    ("draw", "pdf"): "pdf:draw_pdf_Export",
    ("draw", "png"): "png:draw_png_Export",
    ("draw", "jpeg"): "jpg:draw_jpg_Export",
    ("draw", "svg"): "svg:draw_svg_Export",
    ("draw", "eps"): "eps:draw_eps_Export",
    ("draw", "emf"): "emf:draw_emf_Export",
    ("draw", "wmf"): "wmf:draw_wmf_Export",
}
_INFILTERS: dict[str, str] = {
    "csv": "Text - txt - csv (StarCalc):44,34,76,1",
    "tsv": "Text - txt - csv (StarCalc):9,34,76,1",
    "md": "Markdown",
}


def _app_for(src: str) -> str:
    if src in WRITER_SOURCES:
        return "writer"
    if src in CALC_SOURCES:
        return "calc"
    if src in IMPRESS_SOURCES:
        return "impress"
    if src in DRAW_SOURCES:
        return "draw"
    return "writer"


def _pairs() -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for sources, targets in ((WRITER_SOURCES, WRITER_TARGETS), (CALC_SOURCES, CALC_TARGETS), (IMPRESS_SOURCES, IMPRESS_TARGETS), (DRAW_SOURCES, DRAW_TARGETS)):
        for s in sources:
            for t in targets:
                if s != t:
                    pairs.add((s, t))
    # PDF import through Draw/Writer (editable but approximate).
    for t in ("docx", "odt", "doc", "rtf", "txt", "html", "svg", "png", "jpeg", "odg", "pptx", "odp"):
        pairs.add(("pdf", t))
    pairs.discard(("svg", "svg"))
    pairs.discard(("md", "md"))
    return pairs


_PAIRS = _pairs()
_ALL_SOURCES = tuple(sorted({s for s, _ in _PAIRS}))
_ALL_TARGETS = tuple(sorted({t for _, t in _PAIRS}))


def soffice_convert_file(source: Path, target: Path, spec: str, workdir: Path, infilter: str | None = None) -> Path:
    exe = SOFFICE.path()
    assert exe
    profile = Path(tempfile.mkdtemp(prefix="lo-profile-", dir=workdir))
    outdir = Path(tempfile.mkdtemp(prefix="lo-out-", dir=workdir))
    cmd = [exe, "--headless", "--norestore", "--nologo", f"-env:UserInstallation={profile.as_uri()}"]
    if infilter:
        cmd.append(f"--infilter={infilter}")
    cmd += ["--convert-to", spec, "--outdir", str(outdir), str(source)]
    proc = run(cmd, env={"HOME": str(profile)}, timeout=600)
    produced = [p for p in outdir.iterdir() if p.is_file()]
    if not produced:
        raise ConversionError("LibreOffice produced no output", stderr=proc.stderr.decode("utf-8", "replace") + proc.stdout.decode("utf-8", "replace"))
    produced.sort()
    shutil.move(str(produced[0]), target)
    return target


@converter(
    "libreoffice",
    _ALL_SOURCES,
    _ALL_TARGETS,
    requires=(SOFFICE,),
    cost=30,
    options=("password",),
    description="Office document conversion with LibreOffice",
    predicate=lambda s, t: (s, t) in _PAIRS,
)
def libreoffice_convert(job: Job) -> list[Path]:
    src, tgt = job.src_format.name, job.tgt_format.name
    app = _app_for(src)
    infilter = _INFILTERS.get(src)
    if src == "pdf":
        infilter = "writer_pdf_import" if tgt in ("docx", "odt", "doc", "rtf", "txt", "html") else "draw_pdf_import"
        app = "writer" if tgt in ("docx", "odt", "doc", "rtf", "txt", "html") else "draw"
    if src == "csv" and tgt == "csv":
        raise ConversionError("nothing to do")
    spec = _FILTERS.get((app, tgt), job.tgt_format.extension if tgt != "jpeg" else "jpg")
    soffice_convert_file(job.source, job.target, spec, job.workdir, infilter)
    return [job.target]
