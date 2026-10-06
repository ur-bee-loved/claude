"""Font containers through fontTools (and FontForge when installed)."""

from __future__ import annotations

from pathlib import Path

from omniconv.core.engine import Job
from omniconv.core.errors import ConversionError
from omniconv.core.procs import run
from omniconv.core.registry import converter
from omniconv.core.requirements import Module, Tool

FONTTOOLS = Module("fontTools", "fonttools")
FONTFORGE = Tool("fontforge", package="fontforge")

_FT_FORMATS = ("ttf", "otf", "woff", "woff2", "ttx", "dfont")


def _ft_targets() -> set[str]:
    out = {"ttf", "otf", "woff", "ttx"}
    if Module("brotli").available():
        out.add("woff2")
    return out


@converter(
    "fonttools",
    _FT_FORMATS,
    _ft_targets,
    requires=(FONTTOOLS,),
    cost=8,
    description="Change font container/flavor with fontTools (TTF/OTF/WOFF/WOFF2/TTX)",
    predicate=lambda s, t: s != t and not ((s == "ttf" and t == "otf") or (s == "otf" and t == "ttf")),
)
def fonttools_convert(job: Job) -> list[Path]:
    from fontTools.ttLib import TTFont

    src, tgt = job.src_format.name, job.tgt_format.name
    if src == "ttx":
        font = TTFont()
        font.importXML(str(job.source))
    else:
        font = TTFont(str(job.source))
    if tgt == "ttx":
        font.saveXML(str(job.target))
        return [job.target]
    font.flavor = {"woff": "woff", "woff2": "woff2"}.get(tgt)
    if tgt in ("ttf", "otf"):
        has_cff = "CFF " in font or "CFF2" in font
        if tgt == "otf" and not has_cff:
            raise ConversionError("this font has TrueType outlines; saving as .otf would only rename it")
        if tgt == "ttf" and has_cff:
            raise ConversionError("this font has CFF outlines; converting outlines needs FontForge")
    font.save(str(job.target))
    return [job.target]


_FF_FORMATS = ("ttf", "otf", "woff", "woff2", "pfb", "bdf", "dfont", "svgfont", "eot")


@converter(
    "fontforge",
    _FF_FORMATS + ("pcf",),
    ("ttf", "otf", "woff", "woff2", "pfb", "bdf", "dfont", "svgfont"),
    requires=(FONTFORGE,),
    cost=20,
    description="Font conversion including outline conversion with FontForge",
    predicate=lambda s, t: s != t,
)
def fontforge_convert(job: Job) -> list[Path]:
    exe = FONTFORGE.path()
    assert exe
    target = job.target
    if job.tgt_format.name == "svgfont":
        target = job.target.with_suffix(".svg")
    if job.tgt_format.name == "pfb":
        target = job.target.with_suffix(".pfb")
    script = f'Open($1); Generate($2)' if job.tgt_format.name != "bdf" else 'Open($1); BitmapsAvail([32]); Generate($2, "bdf")'
    run([exe, "-lang=ff", "-c", script, str(job.source), str(target)], env={"HOME": str(job.workdir)})
    if target != job.target and target.exists():
        target.rename(job.target)
    return [job.target]
