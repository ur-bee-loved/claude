"""E-books through calibre's ``ebook-convert``."""

from __future__ import annotations

import os
from pathlib import Path

from omniconv.core.engine import Job
from omniconv.core.procs import run
from omniconv.core.registry import converter
from omniconv.core.requirements import Tool

EBOOK_CONVERT = Tool("ebook-convert", package="calibre")

SOURCES = ("azw3", "cbz", "cbr", "chm", "djvu", "docx", "epub", "fb2", "html", "htmlz", "lit", "lrf", "mobi", "odt", "pdf", "pdb", "rb", "rtf", "snb", "tcr", "txt", "txtz", "kepub", "md", "pmlz")
TARGETS = ("azw3", "docx", "epub", "fb2", "htmlz", "lit", "lrf", "mobi", "pdb", "pdf", "pmlz", "rb", "rtf", "snb", "tcr", "txt", "txtz", "zip", "kepub")


@converter(
    "calibre",
    SOURCES,
    TARGETS,
    requires=(EBOOK_CONVERT,),
    cost=30,
    options=("title", "author", "page_size", "font_size"),
    description="E-book conversion with calibre",
    predicate=lambda s, t: s != t and not (s == "html" and t == "htmlz") and t != "zip",
)
def calibre_convert(job: Job) -> list[Path]:
    exe = EBOOK_CONVERT.path()
    assert exe
    target = job.target
    if job.tgt_format.name == "kepub":
        target = job.target.with_suffix(".kepub.epub")
    cmd = [exe, str(job.source), str(target)]
    if job.opt("title"):
        cmd += ["--title", str(job.opt("title"))]
    if job.opt("author"):
        cmd += ["--authors", str(job.opt("author"))]
    if job.tgt_format.name == "pdf":
        cmd += ["--paper-size", str(job.opt("page_size", "a4")).lower(), "--pdf-default-font-size", str(int(job.opt("font_size", 11)))]
    if job.src_format.name == "md":
        cmd += ["--input-encoding", "utf-8", "--formatting-type", "markdown"]
    env = {"HOME": str(job.workdir), "QT_QPA_PLATFORM": "offscreen"}
    if os.geteuid() == 0:
        # calibre's PDF output embeds Chromium, which refuses to run as root
        # unless sandboxing is disabled.
        env["QTWEBENGINE_CHROMIUM_FLAGS"] = "--no-sandbox"
    run(cmd, env=env, timeout=1200)
    if target != job.target and target.exists():
        target.rename(job.target)
    return [job.target]
