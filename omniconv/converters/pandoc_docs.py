"""Markup and word-processing documents through pandoc."""

from __future__ import annotations

from pathlib import Path

from omniconv.core.engine import Job
from omniconv.core.procs import run
from omniconv.core.registry import converter
from omniconv.core.requirements import Tool
from omniconv.converters._common import tool_output

PANDOC = Tool("pandoc", package="pandoc")

# omniconv format -> (pandoc reader, pandoc writer); None where unsupported.
_MAP: dict[str, tuple[str | None, str | None]] = {
    "md": ("markdown", "markdown"),
    "html": ("html", "html5"),
    "docx": ("docx", "docx"),
    "odt": ("odt", "odt"),
    "epub": ("epub", "epub3"),
    "tex": ("latex", "latex"),
    "rst": ("rst", "rst"),
    "org": ("org", "org"),
    "textile": ("textile", "textile"),
    "mediawiki": ("mediawiki", "mediawiki"),
    "dokuwiki": ("dokuwiki", "dokuwiki"),
    "asciidoc": (None, "asciidoc"),
    "typst": ("typst", "typst"),
    "man": ("man", "man"),
    "docbook": ("docbook", "docbook5"),
    "opml": ("opml", "opml"),
    "ipynb": ("ipynb", "ipynb"),
    "jira": ("jira", "jira"),
    "muse": ("muse", "muse"),
    "t2t": ("t2t", None),
    "haddock": ("haddock", "haddock"),
    "pandoc-json": ("json", "json"),
    "rtf": ("rtf", "rtf"),
    "fb2": ("fb2", "fb2"),
    "txt": ("markdown_strict", "plain"),
    "pptx": (None, "pptx"),
    "pdf": (None, "pdf"),
    "csv": ("csv", None),
    "tsv": ("tsv", None),
    "bibtex": ("bibtex", "bibtex"),
    "biblatex": ("biblatex", "biblatex"),
    "csljson": ("csljson", "csljson"),
}

_PDF_ENGINES = ("pdflatex", "xelatex", "lualatex", "tectonic", "wkhtmltopdf", "weasyprint", "prince", "typst", "pagedjs-cli", "context", "pdfroff")


def _lists() -> tuple[set[str], set[str]]:
    exe = PANDOC.path()
    if not exe:
        return set(), set()
    readers = set(tool_output(exe, "--list-input-formats").split())
    writers = set(tool_output(exe, "--list-output-formats").split())
    return readers, writers


def _sources() -> set[str]:
    readers, _ = _lists()
    return {fmt for fmt, (r, _) in _MAP.items() if r and r.split("-")[0].split("+")[0] in readers}


def _pdf_engine() -> str | None:
    for eng in _PDF_ENGINES:
        if Tool(eng).available():
            return eng
    return None


def _targets() -> set[str]:
    _, writers = _lists()
    out = {fmt for fmt, (_, w) in _MAP.items() if w and w in writers}
    if "pdf" in out and _pdf_engine() is None:
        out.discard("pdf")
    return out


@converter(
    "pandoc",
    _sources,
    _targets,
    requires=(PANDOC,),
    cost=15,
    options=("title", "author", "page_size", "font_size"),
    description="Markup conversion with pandoc",
    predicate=lambda s, t: s != t and not (s in ("csv", "tsv") and t in ("csv", "tsv")),
)
def pandoc_convert(job: Job) -> list[Path]:
    exe = PANDOC.path()
    assert exe
    reader = _MAP[job.src_format.name][0]
    writer = _MAP[job.tgt_format.name][1]
    assert reader and writer
    cmd = [exe, "-f", reader, "-t", writer, "-o", str(job.target)]
    if job.tgt_format.name in ("html", "epub", "docx", "odt", "tex", "pdf", "man", "docbook", "fb2", "rtf", "pptx"):
        cmd.append("--standalone")
    if job.tgt_format.name in ("html", "epub", "pdf", "docx", "odt"):
        cmd += ["--metadata", f"title={job.opt('title') or job.source.stem}"]
    if job.opt("author"):
        cmd += ["--metadata", f"author={job.opt('author')}"]
    if job.tgt_format.name == "pdf":
        engine = _pdf_engine()
        if engine:
            cmd += [f"--pdf-engine={engine}"]
        cmd += ["-V", f"papersize={str(job.opt('page_size', 'A4')).lower()}", "-V", f"fontsize={int(job.opt('font_size', 11))}pt"]
    if job.tgt_format.name in ("html",):
        cmd += ["--embed-resources"] if "--embed-resources" in tool_output(exe, "--help") else ["--self-contained"]
    if job.src_format.name in ("html", "md") and job.tgt_format.name in ("docx", "odt", "epub", "pdf"):
        cmd += ["--resource-path", str(job.source.parent)]
    if job.tgt_format.name in ("md", "rst", "org", "textile", "asciidoc", "mediawiki", "dokuwiki", "txt"):
        cmd += ["--wrap=none"]
    cmd.append(str(job.source))
    run(cmd, cwd=job.source.parent)
    return [job.target]
