"""Pure-Python text document conversions.

These need no external tool, so plain text, Markdown and HTML can always
be turned into each other and into PDF (via PyMuPDF's layout engine when
present, otherwise via reportlab).
"""

from __future__ import annotations

import html
import re
from pathlib import Path

from omniconv.core.engine import Job
from omniconv.core.errors import ConversionError
from omniconv.core.registry import converter
from omniconv.converters._common import PYMUPDF, load_pymupdf
from omniconv.core.requirements import AnyOf, Module

MARKDOWN = Module("markdown", "markdown")


def _read_text(job: Job) -> str:
    enc = job.opt("encoding") or "utf-8"
    data = job.source.read_bytes()
    try:
        return data.decode(enc)
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _html_document(title: str, body: str, font_size: int = 11) -> str:
    return (
        "<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title>"
        f"<style>body{{font-family:sans-serif;font-size:{font_size}pt;line-height:1.4;max-width:48em;margin:2em auto;padding:0 1em}}"
        "pre{white-space:pre-wrap;font-family:monospace}code{font-family:monospace}"
        "table{border-collapse:collapse}td,th{border:1px solid #999;padding:.2em .5em}</style>"
        f"</head><body>\n{body}\n</body></html>\n"
    )


def _text_to_html_body(text: str) -> str:
    paragraphs = re.split(r"\n\s*\n", text.strip())
    return "\n".join(f"<p>{html.escape(p).replace(chr(10), '<br/>')}</p>" for p in paragraphs if p.strip())


def _markdown_to_html_body(text: str) -> str:
    try:
        import markdown

        return markdown.markdown(text, extensions=["tables", "fenced_code", "toc", "sane_lists"])
    except ImportError:
        return _text_to_html_body(text)


def _html_to_text(source: str) -> str:
    from html.parser import HTMLParser

    class Extractor(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.parts: list[str] = []
            self.skip = 0

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style"):
                self.skip += 1
            elif tag in ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote"):
                self.parts.append("\n")
            if tag in ("h1", "h2", "h3"):
                self.parts.append("\n")

        def handle_endtag(self, tag):
            if tag in ("script", "style"):
                self.skip = max(0, self.skip - 1)
            elif tag in ("p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote", "table"):
                self.parts.append("\n")

        def handle_data(self, data):
            if not self.skip:
                self.parts.append(data)

    ex = Extractor()
    ex.feed(source)
    text = "".join(ex.parts)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


@converter("text-to-html", ("txt", "md"), ("html",), cost=5, options=("title", "font_size", "encoding"), description="Plain text or Markdown to HTML")
def text_to_html(job: Job) -> list[Path]:
    text = _read_text(job)
    body = _markdown_to_html_body(text) if job.src_format.name == "md" else _text_to_html_body(text)
    job.target.write_text(_html_document(str(job.opt("title") or job.source.stem), body, int(job.opt("font_size", 11))), encoding="utf-8")
    return [job.target]


@converter("html-to-text", ("html",), ("txt",), cost=6, options=("encoding",), description="Strip HTML tags to plain text")
def html_to_text(job: Job) -> list[Path]:
    job.target.write_text(_html_to_text(_read_text(job)), encoding="utf-8")
    return [job.target]


@converter("text-copy", ("txt", "md", "rst", "org", "tex", "textile", "asciidoc", "typst", "csv", "tsv", "json", "yaml", "toml", "xml", "ini", "srt", "vtt", "ass", "ssa", "lrc", "sub", "html", "svg", "ttx", "ics", "vcf", "jsonl", "docbook", "opml", "ttml", "mediawiki", "dokuwiki", "jira", "muse", "haddock", "man", "fodt"), ("txt",), cost=40, options=("encoding",), description="Treat any text-based file as plain text (re-encoded to UTF-8)", predicate=lambda s, t: s != "html")
def text_copy(job: Job) -> list[Path]:
    job.target.write_text(_read_text(job), encoding="utf-8")
    return [job.target]


@converter("text-to-markdown", ("txt",), ("md",), cost=5, options=("encoding",), description="Plain text to Markdown (paragraphs preserved)")
def text_to_markdown(job: Job) -> list[Path]:
    job.target.write_text(_read_text(job), encoding="utf-8")
    return [job.target]


@converter(
    "html-to-pdf",
    ("html", "txt", "md"),
    ("pdf",),
    requires=(AnyOf((PYMUPDF, Module("reportlab", "reportlab"))),),
    cost=13,
    options=("title", "font_size", "page_size", "encoding", "author"),
    description="Lay out text, Markdown or HTML into a PDF (MuPDF Story or reportlab)",
)
def html_to_pdf(job: Job) -> list[Path]:
    text = _read_text(job)
    title = str(job.opt("title") or job.source.stem)
    if job.src_format.name == "md":
        source_html = _html_document(title, _markdown_to_html_body(text), int(job.opt("font_size", 11)))
    elif job.src_format.name == "txt":
        source_html = _html_document(title, _text_to_html_body(text), int(job.opt("font_size", 11)))
    else:
        source_html = text
    page = str(job.opt("page_size", "A4")).lower()
    try:
        fitz = load_pymupdf()

        return [_story_pdf(job, source_html, page, title)]
    except ImportError:
        pass
    return [_reportlab_pdf(job, _html_to_text(source_html), page, title)]


def _story_pdf(job: Job, source_html: str, page: str, title: str) -> Path:
    fitz = load_pymupdf()

    sizes = {"a4": fitz.paper_rect("a4"), "a5": fitz.paper_rect("a5"), "letter": fitz.paper_rect("letter"), "legal": fitz.paper_rect("legal")}
    rect = sizes.get(page, fitz.paper_rect("a4"))
    margin = 50
    where = rect + (margin, margin, -margin, -margin)
    css = f"body{{font-family:sans-serif;font-size:{int(job.opt('font_size', 11))}pt}}"
    archive = fitz.Archive(str(job.source.parent))
    story = fitz.Story(html=source_html, user_css=css, archive=archive)
    # Lay out into memory, then save the final document once with metadata.
    # MuPDF's writer keeps its file open until the object is destroyed, which
    # on Windows blocks any later replace or delete of that file; writing to
    # a buffer avoids the file altogether.
    import io

    buffer = io.BytesIO()
    writer = fitz.DocumentWriter(buffer)
    more = True
    while more:
        dev = writer.begin_page(rect)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()
    del writer
    doc = fitz.open("pdf", buffer.getvalue())
    doc.set_metadata({"title": title, "author": str(job.opt("author") or "")})
    doc.save(str(job.target), garbage=2, deflate=True)
    doc.close()
    return job.target


def _reportlab_pdf(job: Job, text: str, page: str, title: str) -> Path:
    from reportlab.lib.pagesizes import A4, A5, LEGAL, LETTER
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    size = {"a4": A4, "a5": A5, "letter": LETTER, "legal": LEGAL}.get(page, A4)
    doc = SimpleDocTemplate(str(job.target), pagesize=size, title=title, author=str(job.opt("author") or ""))
    styles = getSampleStyleSheet()
    body = styles["BodyText"]
    body.fontSize = int(job.opt("font_size", 11))
    body.leading = body.fontSize * 1.35
    flow = []
    for para in re.split(r"\n\s*\n", text):
        if para.strip():
            flow.append(Paragraph(html.escape(para).replace("\n", "<br/>"), body))
            flow.append(Spacer(1, body.leading * 0.6))
    if not flow:
        raise ConversionError("nothing to lay out")
    doc.build(flow)
    return job.target
