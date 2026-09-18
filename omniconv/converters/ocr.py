"""Optical character recognition with Tesseract and OCRmyPDF."""

from __future__ import annotations

import shutil
from pathlib import Path

from omniconv.core.engine import Job
from omniconv.core.errors import ConversionError
from omniconv.core.procs import run
from omniconv.core.registry import converter
from omniconv.core.requirements import Tool

TESSERACT = Tool("tesseract", package="tesseract-ocr")
OCRMYPDF = Tool("ocrmypdf", package="ocrmypdf")

_IMG = ("png", "jpeg", "tiff", "bmp", "pnm", "ppm", "pgm", "pbm", "gif", "webp", "jp2")


@converter(
    "tesseract",
    _IMG,
    ("txt", "pdf", "html", "tsv"),
    requires=(TESSERACT,),
    cost=15,
    options=("ocr_language",),
    description="Recognise text in an image (plain text, searchable PDF, hOCR HTML, TSV)",
)
def tesseract_convert(job: Job) -> list[Path]:
    exe = TESSERACT.path()
    assert exe
    tgt = job.tgt_format.name
    base = job.workdir / "ocr"
    kind = {"txt": "txt", "pdf": "pdf", "html": "hocr", "tsv": "tsv"}[tgt]
    lang = str(job.opt("ocr_language", "eng") or "eng")
    run([exe, str(job.source), str(base), "-l", lang, kind], timeout=1200)
    produced = base.with_suffix({"txt": ".txt", "pdf": ".pdf", "html": ".hocr", "tsv": ".tsv"}[tgt])
    if not produced.exists():
        raise ConversionError("tesseract produced no output")
    shutil.move(str(produced), job.target)
    return [job.target]


@converter(
    "ocrmypdf",
    ("pdf",) + _IMG,
    ("pdf",),
    requires=(OCRMYPDF,),
    cost=45,
    same_format=True,
    options=("ocr_language", "rotate"),
    description="Add a searchable text layer to a scanned PDF or image",
)
def ocrmypdf_convert(job: Job) -> list[Path]:
    exe = OCRMYPDF.path()
    assert exe
    cmd = [exe, "-q", "--skip-text", "-l", str(job.opt("ocr_language", "eng") or "eng")]
    if job.src_format.name != "pdf":
        cmd.append("--image-dpi=300")
    cmd += [str(job.source), str(job.target)]
    run(cmd, timeout=1800)
    return [job.target]
