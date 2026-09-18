"""PDF and page-oriented document conversion.

Several backends overlap here; the costs order them so that the fastest,
most faithful one wins when several are installed:

* PyMuPDF (``fitz``) renders PDF/XPS/EPUB/CBZ/FB2/SVG pages to images,
  extracts text/HTML/SVG, rebuilds PDFs (page selection, rotation,
  compression, encryption) and converts images and reflowable ebooks to PDF.
* pypdf handles pure-Python PDF manipulation and text extraction.
* poppler's ``pdftoppm``, ``pdftotext``, ``pdftohtml``, ``pdftocairo``.
* Ghostscript handles PostScript, PDF/A, downsampling presets.
* img2pdf embeds images losslessly into PDF.
* qpdf rewrites PDF structure (linearise, decrypt, encrypt).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from omniconv.core.engine import Job
from omniconv.core.errors import ConversionError
from omniconv.core.options import parse_pages
from omniconv.core.procs import run
from omniconv.core.registry import converter
from omniconv.converters._common import PYMUPDF, load_pymupdf
from omniconv.core.requirements import Module, Tool

PYPDF = Module("pypdf", "pypdf")
GS = Tool("gs", package="ghostscript")

MUPDF_SOURCES = ("pdf", "xps", "epub", "mobi", "fb2", "cbz", "svg", "txt")
RASTER_TARGETS = ("png", "jpeg", "ppm", "pgm", "pbm", "pnm", "pam", "psd")


def _mupdf_open(job: Job):
    fitz = load_pymupdf()

    try:
        doc = fitz.open(str(job.source))
    except Exception as exc:
        raise ConversionError(f"cannot open {job.source.name}: {exc}") from exc
    if doc.needs_pass:
        pw = job.opt("password")
        if not pw or not doc.authenticate(str(pw)):
            raise ConversionError("document is encrypted; supply --password")
    return doc


def _selected_pages(job: Job, count: int) -> list[int]:
    frame = job.opt("frame")
    if frame is not None:
        return [min(int(frame), count - 1)]
    return parse_pages(job.opt("pages"), count)


# ------------------------------------------------------------------ PyMuPDF
@converter(
    "pymupdf-render",
    MUPDF_SOURCES,
    RASTER_TARGETS,
    requires=(PYMUPDF,),
    cost=10,
    options=("dpi", "pages", "frame", "grayscale", "background", "password", "quality", "width", "height"),
    description="Rasterise document pages with MuPDF",
)
def mupdf_render(job: Job) -> list[Path]:
    fitz = load_pymupdf()

    doc = _mupdf_open(job)
    pages = _selected_pages(job, doc.page_count)
    dpi = int(job.opt("dpi", 150) or 150)
    tgt = job.tgt_format.name
    outputs: list[Path] = []
    colorspace = fitz.csGRAY if job.opt("grayscale") or tgt in ("pgm", "pbm") else fitz.csRGB
    alpha = tgt in ("png", "pam", "psd") and not job.opt("background")
    for i, idx in enumerate(pages):
        page = doc[idx]
        zoom = dpi / 72.0
        w, h = job.opt("width"), job.opt("height")
        if w or h:
            rect = page.rect
            zx = (int(w) / rect.width) if w else None
            zy = (int(h) / rect.height) if h else None
            zoom_x = zx or zy
            zoom_y = zy or zx
            matrix = fitz.Matrix(zoom_x, zoom_y)
        else:
            matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, colorspace=colorspace, alpha=alpha)
        out = job.target if len(pages) == 1 else job.numbered(i, len(pages))
        if tgt == "jpeg":
            pix.save(str(out), output="jpg", jpg_quality=int(job.opt("quality", 90) or 90))
        else:
            pix.save(str(out))
        outputs.append(out)
    doc.close()
    return outputs


@converter(
    "pymupdf-extract",
    MUPDF_SOURCES,
    ("txt", "html", "svg", "json"),
    requires=(PYMUPDF,),
    cost=10,
    options=("pages", "password"),
    description="Extract text, HTML, SVG or JSON structure from document pages",
    predicate=lambda s, t: not (s == "svg" and t == "svg") and not (s == "txt" and t == "txt"),
)
def mupdf_extract(job: Job) -> list[Path]:
    doc = _mupdf_open(job)
    pages = _selected_pages(job, doc.page_count)
    tgt = job.tgt_format.name
    if tgt == "svg":
        outputs = []
        for i, idx in enumerate(pages):
            out = job.target if len(pages) == 1 else job.numbered(i, len(pages))
            out.write_text(doc[idx].get_svg_image(), encoding="utf-8")
            outputs.append(out)
        doc.close()
        return outputs
    if tgt == "json":
        import json

        data = [doc[idx].get_text("dict") for idx in pages]
        job.target.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        doc.close()
        return [job.target]
    chunks = []
    for idx in pages:
        if tgt == "html":
            chunks.append(doc[idx].get_text("xhtml"))
        else:
            chunks.append(doc[idx].get_text("text"))
    doc.close()
    if tgt == "html":
        body = "\n<hr/>\n".join(chunks)
        title = job.opt("title") or job.source.stem
        job.target.write_text(f"<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\"><title>{title}</title></head><body>\n{body}\n</body></html>\n", encoding="utf-8")
    else:
        job.target.write_text("\f".join(chunks), encoding="utf-8")
    return [job.target]


@converter(
    "pymupdf-topdf",
    ("xps", "epub", "mobi", "fb2", "cbz", "svg", "png", "jpeg", "bmp", "gif", "tiff", "pnm", "pgm", "pbm", "ppm", "pam", "jp2", "psd", "txt"),
    ("pdf",),
    requires=(PYMUPDF,),
    cost=11,
    options=("pages", "password", "title", "author"),
    description="Convert images, SVG and reflowable ebooks to PDF with MuPDF",
)
def mupdf_to_pdf(job: Job) -> list[Path]:
    fitz = load_pymupdf()

    doc = _mupdf_open(job)
    pages = _selected_pages(job, doc.page_count)
    pdf_bytes = doc.convert_to_pdf(from_page=0, to_page=doc.page_count - 1)
    doc.close()
    pdf = fitz.open("pdf", pdf_bytes)
    if len(pages) != pdf.page_count:
        pdf.select(pages)
    meta = pdf.metadata or {}
    if job.opt("title"):
        meta["title"] = str(job.opt("title"))
    if job.opt("author"):
        meta["author"] = str(job.opt("author"))
    pdf.set_metadata(meta)
    pdf.save(str(job.target), garbage=3, deflate=True)
    pdf.close()
    return [job.target]


@converter(
    "pymupdf-rewrite",
    ("pdf",),
    ("pdf",),
    requires=(PYMUPDF,),
    cost=10,
    same_format=True,
    options=("pages", "rotate", "password", "compress", "title", "author", "grayscale"),
    description="Rewrite a PDF: select pages, rotate, compress, set metadata, encrypt",
)
def mupdf_rewrite(job: Job) -> list[Path]:
    fitz = load_pymupdf()

    doc = _mupdf_open(job)
    pages = _selected_pages(job, doc.page_count)
    if len(pages) != doc.page_count or pages != list(range(doc.page_count)):
        doc.select(pages)
    rotate = job.opt("rotate")
    if rotate:
        for page in doc:
            page.set_rotation((page.rotation + int(rotate)) % 360)
    meta = doc.metadata or {}
    if job.opt("title"):
        meta["title"] = str(job.opt("title"))
    if job.opt("author"):
        meta["author"] = str(job.opt("author"))
    doc.set_metadata(meta)
    level = job.opt("compress")
    kwargs = dict(garbage=4, deflate=True, deflate_images=True, deflate_fonts=True, clean=True)
    if level is not None and int(level) >= 2:
        # Recompress images aggressively for a smaller file.
        try:
            doc.rewrite_images(dpi_threshold=150, dpi_target=int(96 if int(level) >= 3 else 120), quality=int(60 if int(level) >= 3 else 75))
        except Exception:
            pass
    pw = job.opt("password")
    if pw and not doc.is_encrypted:
        kwargs.update(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw=str(pw), user_pw=str(pw))
    doc.save(str(job.target), **kwargs)
    doc.close()
    return [job.target]


@converter(
    "pymupdf-merge",
    ("pdf", "xps", "epub", "cbz", "fb2", "svg", "png", "jpeg", "bmp", "gif", "tiff", "pnm", "ppm", "pgm", "pbm", "jp2"),
    ("pdf",),
    requires=(PYMUPDF,),
    cost=10,
    many_to_one=True,
    options=("title", "author"),
    description="Merge PDFs, images and ebooks into a single PDF",
)
def mupdf_merge(job: Job) -> list[Path]:
    fitz = load_pymupdf()

    out = fitz.open()
    for src in job.sources:
        d = fitz.open(str(src))
        if d.needs_pass and job.opt("password"):
            d.authenticate(str(job.opt("password")))
        if not d.is_pdf:
            d = fitz.open("pdf", d.convert_to_pdf())
        out.insert_pdf(d)
        d.close()
    meta = {"title": str(job.opt("title") or ""), "author": str(job.opt("author") or "")}
    out.set_metadata({k: v for k, v in meta.items() if v})
    out.save(str(job.target), garbage=3, deflate=True)
    out.close()
    return [job.target]


@converter(
    "pymupdf-split",
    ("pdf",),
    ("pdf",),
    requires=(PYMUPDF,),
    cost=50,
    same_format=True,
    options=("password",),
    description="Split a PDF into one file per page (use with --split)",
)
def mupdf_split(job: Job) -> list[Path]:
    fitz = load_pymupdf()

    doc = _mupdf_open(job)
    outputs = []
    for i in range(doc.page_count):
        single = fitz.open()
        single.insert_pdf(doc, from_page=i, to_page=i)
        out = job.numbered(i, doc.page_count)
        single.save(str(out))
        single.close()
        outputs.append(out)
    doc.close()
    return outputs


@converter(
    "pymupdf-images",
    ("pdf", "xps", "epub", "cbz"),
    ("png", "jpeg"),
    requires=(PYMUPDF,),
    cost=60,
    options=("pages", "password"),
    description="Extract embedded images from a document (use with --extract-images)",
)
def mupdf_images(job: Job) -> list[Path]:
    fitz = load_pymupdf()

    doc = _mupdf_open(job)
    outputs = []
    n = 0
    for idx in _selected_pages(job, doc.page_count):
        for info in doc[idx].get_images(full=True):
            pix = fitz.Pixmap(doc, info[0])
            if pix.n - pix.alpha > 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            out = job.target.with_name(f"{job.target.stem}-p{idx + 1}-{n + 1:03d}{job.target.suffix}")
            if job.tgt_format.name == "jpeg":
                if pix.alpha:
                    pix = fitz.Pixmap(pix, 0)
                pix.save(str(out), output="jpg")
            else:
                pix.save(str(out))
            outputs.append(out)
            n += 1
    doc.close()
    if not outputs:
        raise ConversionError("no embedded images found")
    return outputs


# -------------------------------------------------------------------- pypdf
@converter(
    "pypdf-rewrite",
    ("pdf",),
    ("pdf",),
    requires=(PYPDF,),
    cost=14,
    same_format=True,
    options=("pages", "rotate", "password", "title", "author", "compress"),
    description="Rewrite a PDF with pypdf (pages, rotation, encryption)",
)
def pypdf_rewrite(job: Job) -> list[Path]:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(job.source))
    if reader.is_encrypted:
        pw = job.opt("password")
        if not pw or not reader.decrypt(str(pw)):
            raise ConversionError("document is encrypted; supply --password")
    writer = PdfWriter()
    for idx in _selected_pages(job, len(reader.pages)):
        page = reader.pages[idx]
        if job.opt("rotate"):
            page.rotate(int(job.opt("rotate")))
        writer.add_page(page)
    meta = {}
    if job.opt("title"):
        meta["/Title"] = str(job.opt("title"))
    if job.opt("author"):
        meta["/Author"] = str(job.opt("author"))
    if meta:
        writer.add_metadata(meta)
    if job.opt("compress") is not None:
        for page in writer.pages:
            page.compress_content_streams()
    pw = job.opt("password")
    if pw and not reader.is_encrypted:
        writer.encrypt(str(pw))
    with open(job.target, "wb") as fh:
        writer.write(fh)
    return [job.target]


@converter("pypdf-text", ("pdf",), ("txt",), requires=(PYPDF,), cost=16, options=("pages", "password"), description="Extract text with pypdf")
def pypdf_text(job: Job) -> list[Path]:
    from pypdf import PdfReader

    reader = PdfReader(str(job.source))
    if reader.is_encrypted and job.opt("password"):
        reader.decrypt(str(job.opt("password")))
    chunks = [reader.pages[i].extract_text() or "" for i in _selected_pages(job, len(reader.pages))]
    job.target.write_text("\f".join(chunks), encoding="utf-8")
    return [job.target]


@converter("pypdf-merge", ("pdf",), ("pdf",), requires=(PYPDF,), cost=14, many_to_one=True, description="Merge PDFs with pypdf")
def pypdf_merge(job: Job) -> list[Path]:
    from pypdf import PdfWriter

    writer = PdfWriter()
    for src in job.sources:
        writer.append(str(src))
    with open(job.target, "wb") as fh:
        writer.write(fh)
    return [job.target]


# ------------------------------------------------------------------ poppler
def _first_last(job: Job, count_hint: int = 9999) -> list[str]:
    pages = job.opt("pages")
    frame = job.opt("frame")
    if frame is not None:
        return ["-f", str(int(frame) + 1), "-l", str(int(frame) + 1)]
    if pages and "," not in str(pages):
        lo, _, hi = str(pages).partition("-")
        args = ["-f", lo or "1"]
        if hi:
            args += ["-l", hi]
        elif not _:
            args += ["-l", lo]
        return args
    return []


@converter(
    "pdftoppm",
    ("pdf",),
    ("png", "jpeg", "tiff", "ppm", "pgm", "pbm"),
    requires=(Tool("pdftoppm", package="poppler-utils"),),
    cost=12,
    options=("dpi", "pages", "frame", "grayscale", "password", "width", "height"),
    description="Rasterise PDF pages with poppler",
)
def pdftoppm_convert(job: Job) -> list[Path]:
    exe = Tool("pdftoppm").path()
    assert exe
    tgt = job.tgt_format.name
    flag = {"png": "-png", "jpeg": "-jpeg", "tiff": "-tiff", "ppm": None, "pgm": "-gray", "pbm": "-mono"}[tgt]
    cmd = [exe, "-r", str(int(job.opt("dpi", 150) or 150))]
    if flag:
        cmd.append(flag)
    if job.opt("grayscale") and tgt not in ("pgm", "pbm"):
        cmd.append("-gray")
    if job.opt("width"):
        cmd += ["-scale-to-x", str(int(job.opt("width"))), "-scale-to-y", "-1"]
    if job.opt("height"):
        cmd += ["-scale-to-y", str(int(job.opt("height"))), "-scale-to-x", "-1"]
    if job.opt("password"):
        cmd += ["-upw", str(job.opt("password"))]
    cmd += _first_last(job)
    prefix = job.workdir / "page"
    cmd += [str(job.source), str(prefix)]
    run(cmd)
    ext = {"png": "png", "jpeg": "jpg", "tiff": "tif", "ppm": "ppm", "pgm": "pgm", "pbm": "pbm"}[tgt]
    produced = sorted(job.workdir.glob(f"page-*.{ext}"))
    if not produced:
        raise ConversionError("pdftoppm produced no pages")
    if len(produced) == 1:
        shutil.move(str(produced[0]), job.target)
        return [job.target]
    outputs = []
    for i, p in enumerate(produced):
        out = job.numbered(i, len(produced))
        shutil.move(str(p), out)
        outputs.append(out)
    return outputs


@converter("pdftotext", ("pdf",), ("txt",), requires=(Tool("pdftotext", package="poppler-utils"),), cost=12, options=("pages", "password"), description="Text extraction with poppler")
def pdftotext_convert(job: Job) -> list[Path]:
    exe = Tool("pdftotext").path()
    assert exe
    cmd = [exe, "-layout", "-enc", "UTF-8", *_first_last(job)]
    if job.opt("password"):
        cmd += ["-upw", str(job.opt("password"))]
    cmd += [str(job.source), str(job.target)]
    run(cmd)
    return [job.target]


@converter("pdftohtml", ("pdf",), ("html", "xml"), requires=(Tool("pdftohtml", package="poppler-utils"),), cost=13, options=("pages", "password"), description="HTML/XML export with poppler")
def pdftohtml_convert(job: Job) -> list[Path]:
    exe = Tool("pdftohtml").path()
    assert exe
    cmd = [exe, "-enc", "UTF-8", "-noframes", "-s", "-i", *_first_last(job)]
    if job.tgt_format.name == "xml":
        cmd.append("-xml")
    if job.opt("password"):
        cmd += ["-upw", str(job.opt("password"))]
    stem = job.workdir / "out"
    cmd += [str(job.source), str(stem)]
    run(cmd)
    produced = list(job.workdir.glob("out*.html")) + list(job.workdir.glob("out*.xml"))
    if not produced:
        raise ConversionError("pdftohtml produced no output")
    shutil.move(str(produced[0]), job.target)
    return [job.target]


@converter(
    "pdftocairo",
    ("pdf",),
    ("svg", "eps", "ps", "png", "jpeg", "tiff", "pdf"),
    requires=(Tool("pdftocairo", package="poppler-utils"),),
    cost=13,
    options=("dpi", "pages", "frame", "grayscale", "password", "width", "height"),
    description="Vector and raster export of PDF pages with cairo",
    same_format=False,
)
def pdftocairo_convert(job: Job) -> list[Path]:
    exe = Tool("pdftocairo").path()
    assert exe
    tgt = job.tgt_format.name
    cmd = [exe, f"-{tgt if tgt != 'jpeg' else 'jpeg'}"]
    if tgt in ("png", "jpeg", "tiff"):
        cmd += ["-r", str(int(job.opt("dpi", 150) or 150))]
        if job.opt("grayscale"):
            cmd.append("-gray")
        if job.opt("width"):
            cmd += ["-scale-to-x", str(int(job.opt("width"))), "-scale-to-y", "-1"]
    if job.opt("password"):
        cmd += ["-upw", str(job.opt("password"))]
    cmd += _first_last(job)
    vector = tgt in ("svg", "eps", "ps", "pdf")
    if vector:
        if tgt in ("svg", "eps") and not _first_last(job):
            cmd += ["-f", "1", "-l", "1"]
        cmd += [str(job.source), str(job.target)]
        run(cmd)
        return [job.target]
    prefix = job.workdir / "page"
    cmd += [str(job.source), str(prefix)]
    run(cmd)
    ext = {"png": "png", "jpeg": "jpg", "tiff": "tif"}[tgt]
    produced = sorted(job.workdir.glob(f"page-*.{ext}"))
    if not produced:
        raise ConversionError("pdftocairo produced no pages")
    if len(produced) == 1:
        shutil.move(str(produced[0]), job.target)
        return [job.target]
    outputs = []
    for i, p in enumerate(produced):
        out = job.numbered(i, len(produced))
        shutil.move(str(p), out)
        outputs.append(out)
    return outputs


# -------------------------------------------------------------- Ghostscript
_GS_DEVICES = {
    "pdf": "pdfwrite", "ps": "ps2write", "eps": "eps2write", "png": "png16m", "jpeg": "jpeg", "tiff": "tiff24nc",
    "bmp": "bmp16m", "pcx": "pcx24b", "ppm": "ppm", "pgm": "pgm", "pbm": "pbm", "pnm": "pnm", "txt": "txtwrite",
    "xps": "xpswrite", "pam": "pam", "psd": "psdrgb", "fax": "faxg3",
}


@converter(
    "ghostscript",
    ("pdf", "ps", "eps", "ai"),
    tuple(_GS_DEVICES),
    requires=(GS,),
    cost=15,
    options=("dpi", "pages", "frame", "grayscale", "password", "compress", "quality"),
    description="PostScript/PDF interpretation with Ghostscript",
    same_format=True,
    predicate=lambda s, t: not (s == t and s in ("ps", "eps")),
)
def gs_convert(job: Job) -> list[Path]:
    exe = GS.path()
    assert exe
    tgt = job.tgt_format.name
    device = _GS_DEVICES[tgt]
    if job.opt("grayscale"):
        device = {"png16m": "pnggray", "jpeg": "jpeggray", "tiff24nc": "tiffgray", "bmp16m": "bmpgray", "pcx24b": "pcxgray", "ppm": "pgm"}.get(device, device)
    cmd = [exe, "-dBATCH", "-dNOPAUSE", "-dQUIET", "-dSAFER", f"-sDEVICE={device}"]
    if job.opt("password"):
        cmd.append(f"-sPDFPassword={job.opt('password')}")
    raster = tgt not in ("pdf", "ps", "eps", "txt", "xps")
    if raster:
        cmd.append(f"-r{int(job.opt('dpi', 150) or 150)}")
        if tgt == "jpeg" and job.opt("quality"):
            cmd.append(f"-dJPEGQ={int(job.opt('quality'))}")
    if tgt == "pdf":
        level = job.opt("compress")
        preset = {0: "/default", 1: "/printer", 2: "/ebook", 3: "/screen"}.get(int(level) if level is not None else 0, "/ebook")
        cmd += [f"-dPDFSETTINGS={preset}", "-dCompatibilityLevel=1.6"]
    if job.src_format.name == "eps" and tgt in ("pdf", "png", "jpeg", "tiff", "bmp", "ppm", "pgm", "pbm", "pnm", "pcx", "pam", "psd"):
        cmd.append("-dEPSCrop")
    fl = _first_last(job)
    if fl:
        cmd += [f"-dFirstPage={fl[1]}", f"-dLastPage={fl[3] if len(fl) > 3 else fl[1]}"]
    if raster and tgt not in ("pdf",):
        pattern = job.workdir / f"page-%03d.{job.tgt_format.extension}"
        cmd += [f"-sOutputFile={pattern}", str(job.source)]
        run(cmd)
        produced = sorted(job.workdir.glob("page-*"))
        if not produced:
            raise ConversionError("Ghostscript produced no pages")
        if len(produced) == 1:
            shutil.move(str(produced[0]), job.target)
            return [job.target]
        outputs = []
        for i, p in enumerate(produced):
            out = job.numbered(i, len(produced))
            shutil.move(str(p), out)
            outputs.append(out)
        return outputs
    cmd += [f"-sOutputFile={job.target}", str(job.source)]
    run(cmd)
    return [job.target]


# ------------------------------------------------------------------ img2pdf
@converter(
    "img2pdf",
    ("jpeg", "png", "gif", "tiff", "jp2", "bmp", "webp", "avif", "heif"),
    ("pdf",),
    requires=(Tool("img2pdf", package="img2pdf"),),
    cost=8,
    options=("dpi", "page_size", "title", "author"),
    description="Lossless image to PDF embedding with img2pdf",
)
def img2pdf_convert(job: Job) -> list[Path]:
    exe = Tool("img2pdf").path()
    assert exe
    cmd = [exe, "-o", str(job.target)]
    if job.opt("dpi"):
        cmd += ["--imgsize", f"{int(job.opt('dpi'))}dpi"]
    if job.opt("title"):
        cmd += ["--title", str(job.opt("title"))]
    if job.opt("author"):
        cmd += ["--author", str(job.opt("author"))]
    cmd.append(str(job.source))
    try:
        run(cmd)
    except ConversionError as exc:
        # img2pdf refuses images with alpha channels; fall back to MuPDF/Pillow.
        raise ConversionError(f"img2pdf: {exc}") from exc
    return [job.target]


@converter("img2pdf-merge", ("jpeg", "png", "gif", "tiff", "jp2", "bmp"), ("pdf",), requires=(Tool("img2pdf", package="img2pdf"),), cost=9, many_to_one=True, options=("dpi", "title", "author"), description="Combine images into a PDF losslessly")
def img2pdf_merge(job: Job) -> list[Path]:
    exe = Tool("img2pdf").path()
    assert exe
    cmd = [exe, "-o", str(job.target)]
    if job.opt("title"):
        cmd += ["--title", str(job.opt("title"))]
    cmd += [str(s) for s in job.sources]
    run(cmd)
    return [job.target]


# --------------------------------------------------------------------- qpdf
@converter("qpdf", ("pdf",), ("pdf",), requires=(Tool("qpdf", package="qpdf"),), cost=13, same_format=True, options=("password", "pages", "compress"), description="Structural PDF rewrite with qpdf (linearise, decrypt/encrypt, pages)")
def qpdf_convert(job: Job) -> list[Path]:
    exe = Tool("qpdf").path()
    assert exe
    cmd = [exe, "--warning-exit-0", "--linearize"]
    pw = job.opt("password")
    if pw:
        cmd += [f"--password={pw}", "--decrypt"]
    if job.opt("compress") is not None:
        cmd += ["--object-streams=generate", "--compress-streams=y", "--recompress-flate"]
    cmd.append(str(job.source))
    if job.opt("pages"):
        cmd += ["--pages", ".", str(job.opt("pages")), "--"]
    cmd.append(str(job.target))
    run(cmd)
    return [job.target]
