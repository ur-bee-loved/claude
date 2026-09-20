"""Raster and vector images through ImageMagick.

ImageMagick reads and writes far more formats than Pillow (RAW camera files,
XCF, EXR, DPX, DICOM, PICT, ...) and rasterises PostScript and PDF through
Ghostscript. It runs as an external process and is a little slower, so it
is registered with a higher cost and used where Pillow cannot.

The list of formats is parsed from ``convert -list format`` (or ``magick``
on ImageMagick 7) at first use, so the converter only offers what the local
build supports.
"""

from __future__ import annotations

import re
from pathlib import Path

from omniconv.core.engine import Job
from omniconv.core.procs import run
from omniconv.core.registry import converter
from omniconv.core.requirements import Tool
from omniconv.converters._common import tool_output

# ImageMagick 7 ships "magick"; version 6 ships "convert". The platform
# layer refuses to look up "convert" on Windows, where that name belongs to
# the NTFS filesystem converter.
MAGICK = Tool("magick", ("convert",), package="imagemagick")

# ImageMagick coder name -> omniconv format name.
_IM_TO_FMT: dict[str, str] = {
    "PNG": "png", "APNG": "apng", "JPEG": "jpeg", "GIF": "gif", "BMP": "bmp", "TIFF": "tiff", "WEBP": "webp",
    "ICO": "ico", "ICNS": "icns", "HEIC": "heif", "HEIF": "heif", "AVIF": "avif", "JP2": "jp2", "JXL": "jxl",
    "PPM": "ppm", "PGM": "pgm", "PBM": "pbm", "PNM": "pnm", "PAM": "pam", "TGA": "tga", "PCX": "pcx", "DDS": "dds",
    "XBM": "xbm", "XPM": "xpm", "SGI": "sgi", "PSD": "psd", "PSB": "psb", "XCF": "xcf", "EXR": "exr", "HDR": "hdr",
    "DPX": "dpx", "FITS": "fits", "DCM": "dcm", "CUR": "cur", "QOI": "qoi", "DNG": "dng", "CR2": "cr2", "CR3": "cr3",
    "NEF": "nef", "NRW": "nrw", "ARW": "arw", "RAF": "raf", "ORF": "orf", "RW2": "rw2", "PEF": "pef", "SRW": "srw",
    "X3F": "x3f", "MRW": "mrw", "KDC": "kdc", "ERF": "erf", "3FR": "3fr", "IIQ": "iiq", "MEF": "mef", "DCR": "dcr",
    "CRW": "crw", "SR2": "sr2", "MIFF": "miff", "MNG": "mng", "SUN": "ras", "WBMP": "wbmp", "JBIG": "jbig2",
    "PFM": "pfm", "FLIF": "flif", "SVG": "svg", "SVGZ": "svgz", "EPS": "eps", "PS": "ps", "AI": "ai", "WMF": "wmf",
    "EMF": "emf", "DXF": "dxf", "CGM": "cgm", "PDF": "pdf", "DCX": "dcx", "PCD": "pcd", "FLI": "fli", "PALM": "palm",
    "PICT": "pict", "XWD": "xwd", "SIXEL": "sixel", "CIN": "cin", "JNG": "jng", "VIFF": "viff", "WPG": "wpg",
    "G3": "g3", "G4": "g4", "CUT": "cut", "ART": "art", "RLA": "rla", "RLE": "rle", "TIM": "tim", "PGX": "pgx",
    "IPL": "ipl", "MAT": "mat", "VICAR": "vicar", "OTB": "otb", "UYVY": "uyvy", "CALS": "cals", "HRZ": "hrz",
    "AAI": "aai", "AVS": "avs", "FAX": "fax", "JBG": "jbg", "MTV": "mtv", "PTIF": "ptif", "VIPS": "vips",
    "DJVU": "djvu", "XPS": "xps", "TTF": "ttf", "OTF": "otf", "PFB": "pfb", "PFA": "pfb",
}
_FMT_TO_IM = {}
for _im, _fmt in _IM_TO_FMT.items():
    _FMT_TO_IM.setdefault(_fmt, _im)
_FMT_TO_IM.update({"heif": "HEIC", "pfb": "PFB", "jpeg": "JPEG"})

_LINE = re.compile(r"^\s*([A-Z0-9-]+)\*?\s+(\S+)\s+([rw+-]{3})\s")


def _capabilities() -> tuple[set[str], set[str]]:
    path = MAGICK.path()
    if not path:
        return set(), set()
    text = tool_output(path, "-list", "format")
    readable: set[str] = set()
    writable: set[str] = set()
    for line in text.splitlines():
        m = _LINE.match(line)
        if not m:
            continue
        coder, mode = m.group(1), m.group(3)
        fmt = _IM_TO_FMT.get(coder)
        if fmt is None:
            continue
        if mode[0] == "r":
            readable.add(fmt)
        if mode[1] == "w":
            writable.add(fmt)
    # Font formats are only rendered as sample images; never treated as raster sources.
    for f in ("ttf", "otf", "pfb"):
        readable.discard(f)
        writable.discard(f)
    if "svg" in writable:
        # ImageMagick's SVG writer embeds a raster; keep it, but let vector backends win.
        pass
    return readable, writable


def _policy_blocks(coder: str) -> bool:
    """Ubuntu ships a policy.xml that may forbid PDF/PS coders."""
    for path in ("/etc/ImageMagick-6/policy.xml", "/etc/ImageMagick-7/policy.xml", "/etc/ImageMagick/policy.xml"):
        try:
            text = Path(path).read_text()
        except OSError:
            continue
        for m in re.finditer(r'<policy\s+domain="coder"\s+rights="none"\s+pattern="([^"]+)"', text):
            pattern = m.group(1).strip("{}")
            if coder in {p.strip() for p in pattern.split(",")}:
                return True
    return False


def _sources() -> set[str]:
    readable, _ = _capabilities()
    for fmt, coder in (("pdf", "PDF"), ("ps", "PS"), ("eps", "EPS"), ("ai", "PDF")):
        if fmt in readable and (_policy_blocks(coder) or not Tool("gs").available()):
            readable.discard(fmt)
    return readable


def _targets() -> set[str]:
    _, writable = _capabilities()
    for fmt, coder in (("pdf", "PDF"), ("ps", "PS"), ("eps", "EPS"), ("ai", "PDF")):
        if fmt in writable and _policy_blocks(coder):
            writable.discard(fmt)
    writable.discard("dxf")
    writable.discard("cgm")
    return writable


def magick_args(job: Job) -> list[str]:
    """Translate the generic options into ImageMagick operators."""
    args: list[str] = []
    density = job.opt("dpi")
    if density and job.src_format.name in ("pdf", "ps", "eps", "ai", "svg", "svgz", "xps", "djvu"):
        args += ["-density", str(int(density))]
    return args


def magick_post_args(job: Job) -> list[str]:
    args: list[str] = []
    tgt = job.tgt_format.name
    bg = job.opt("background")
    if bg:
        args += ["-background", str(bg)]
    if tgt in ("jpeg", "bmp", "pcx", "eps", "pdf", "ppm", "pgm", "pbm", "pnm", "xbm", "ps", "sgi", "wbmp"):
        args += ["-background", str(bg or "white"), "-alpha", "remove", "-alpha", "off"]
    rotate = job.opt("rotate")
    if rotate:
        args += ["-rotate", str(int(rotate))]
    w, h = job.opt("width"), job.opt("height")
    if w or h:
        args += ["-resize", f"{w or ''}x{h or ''}"]
    if job.opt("grayscale"):
        args += ["-colorspace", "Gray"]
    quality = job.opt("quality")
    if quality and tgt in ("jpeg", "webp", "jp2", "heif", "avif", "jxl", "png", "miff", "tiff"):
        args += ["-quality", str(int(quality))]
    if job.opt("strip_metadata"):
        args += ["-strip"]
    if job.opt("lossless") and tgt == "webp":
        args += ["-define", "webp:lossless=true"]
    if tgt in ("pbm", "xbm", "wbmp", "g3", "g4", "fax", "jbig2", "jbg", "otb"):
        args += ["-monochrome"]
    if tgt == "ico":
        args += ["-define", "icon:auto-resize=256,128,64,48,32,16"]
    return args


def _frame_selector(job: Job) -> str:
    frame = job.opt("frame")
    pages = job.opt("pages")
    if frame is not None:
        return f"[{int(frame)}]"
    if pages:
        parts = []
        for part in str(pages).split(","):
            part = part.strip()
            if "-" in part:
                lo, _, hi = part.partition("-")
                parts.append(f"{int(lo or 1) - 1}-{int(hi) - 1}" if hi else f"{int(lo) - 1}-")
            elif part:
                parts.append(str(int(part) - 1))
        return "[" + ",".join(parts) + "]"
    return ""


_MULTI_OUT_TARGETS = {"png", "jpeg", "bmp", "webp", "tga", "pcx", "xbm", "xpm", "jp2", "ppm", "pgm", "pbm", "pnm", "qoi", "sgi", "ras", "cur", "wbmp", "dpx", "exr", "hdr", "avif", "heif", "jxl", "pfm", "sixel", "xwd", "cin", "jng", "viff", "wpg", "g3", "g4", "cut", "art", "rla", "rle", "tim", "pgx", "ipl", "mat", "vicar", "otb", "uyvy", "cals", "hrz", "aai", "avs", "fax", "mtv", "vips"}


@converter(
    "imagemagick",
    _sources,
    _targets,
    requires=(MAGICK,),
    cost=20,
    options=("quality", "width", "height", "dpi", "grayscale", "rotate", "background", "strip_metadata", "lossless", "frame", "pages"),
    description="Image conversion with ImageMagick",
)
def magick_convert(job: Job) -> list[Path]:
    exe = MAGICK.path()
    assert exe
    src_coder = _FMT_TO_IM.get(job.src_format.name, job.src_format.name.upper())
    tgt_coder = _FMT_TO_IM.get(job.tgt_format.name, job.tgt_format.name.upper())
    if job.tgt_format.name == "apng":
        tgt_coder = "APNG"
    selector = _frame_selector(job)
    multi_src = job.src_format.name in ("pdf", "ps", "eps", "ai", "gif", "tiff", "mng", "apng", "dcx", "fli", "webp", "djvu", "xps", "psd", "miff", "ptif", "dds", "ico", "cur", "icns", "pict")
    multi_out = job.tgt_format.name in _MULTI_OUT_TARGETS and multi_src and not selector
    if multi_out:
        pattern = job.target.with_name(f"{job.target.stem}-%03d{job.target.suffix}")
        out_arg = f"{tgt_coder}:{pattern}"
    else:
        out_arg = f"{tgt_coder}:{job.target}"
    multi_image_targets = ("gif", "apng", "mng", "webp", "tiff", "pdf", "miff", "dcx", "ico", "icns", "psd", "ps", "dds", "ptif", "pam")
    if not multi_out and multi_src and not selector and job.tgt_format.name not in multi_image_targets:
        # Single-image targets get the first frame only.
        selector = "[0]"
    cmd = [exe, *magick_args(job), f"{src_coder}:{job.source}{selector}", *magick_post_args(job)]
    if job.src_format.name in ("gif", "apng", "mng", "fli") and job.tgt_format.name in ("gif", "apng", "mng", "webp", "tiff", "pdf") and not selector:
        cmd += ["-coalesce"]
    cmd.append(out_arg)
    run(cmd)
    if multi_out:
        outputs = sorted(job.target.parent.glob(f"{job.target.stem}-[0-9][0-9][0-9]{job.target.suffix}"))
        if len(outputs) == 1:
            outputs[0].rename(job.target)
            return [job.target]
        if outputs:
            return outputs
    if not job.target.exists():
        # ImageMagick may have appended a frame number for single-image formats.
        alt = sorted(job.target.parent.glob(f"{job.target.stem}-[0-9]*{job.target.suffix}"))
        if alt:
            return alt
    return [job.target]


@converter(
    "imagemagick-multipage",
    _sources,
    ("pdf", "tiff", "gif", "apng", "webp", "mng", "miff", "dcx", "ico", "icns", "psd", "pam"),
    requires=(MAGICK,),
    cost=22,
    many_to_one=True,
    options=("quality", "width", "height", "dpi", "grayscale", "background", "fps"),
    description="Combine images into a multi-page or animated file with ImageMagick",
)
def magick_merge(job: Job) -> list[Path]:
    exe = MAGICK.path()
    assert exe
    tgt_coder = _FMT_TO_IM.get(job.tgt_format.name, job.tgt_format.name.upper())
    cmd = [exe, *magick_args(job)]
    for src in job.sources:
        cmd.append(str(src))
    cmd += magick_post_args(job)
    if job.tgt_format.name in ("gif", "apng", "webp", "mng"):
        fps = float(job.opt("fps", 2) or 2)
        cmd += ["-delay", str(max(1, round(100 / fps))), "-loop", "0"]
    cmd.append(f"{tgt_coder}:{job.target}")
    run(cmd)
    return [job.target]
