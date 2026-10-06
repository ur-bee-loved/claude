"""Small single-purpose command-line tools.

Most of these tools take an input path and an output path and nothing else,
so they are described as data: a name, the executable, the formats it reads
and writes and an argument template. The template placeholders are:

    {tool}   resolved executable      {in}     input path
    {out}    output path              {outdir} output directory
    {ext}    output extension         {fmt}    output format name (or a mapped name)

Tools that need more logic (multi-file output, stdout capture, environment
set-up) get a small dedicated function further down.
"""

from __future__ import annotations

import functools
import glob
import os
import shutil
from pathlib import Path
from typing import Callable, Iterable

from omniconv.core import formats
from omniconv.core.engine import Job
from omniconv.core.errors import ConversionError
from omniconv.core.procs import run
from omniconv.core.registry import converter
from omniconv.core.requirements import Tool

RAW_FORMATS = ("dng", "cr2", "cr3", "nef", "nrw", "arw", "raf", "orf", "rw2", "pef", "srw", "x3f", "mrw", "kdc", "erf", "3fr", "iiq", "mef", "dcr", "crw", "sr2")
MODEL_FORMATS = ("obj", "stl", "ply", "gltf", "glb", "dae", "fbx", "3ds", "x3d", "3mf", "off", "x", "blend", "assxml")


def _register_simple(
    name: str,
    tool: Tool,
    sources: Iterable[str],
    targets: Iterable[str],
    argv: list[str],
    *,
    cost: int = 20,
    same_format: bool = False,
    options: Iterable[str] = (),
    description: str = "",
    predicate: Callable[[str, str], bool] | None = None,
    fmt_map: dict[str, str] | None = None,
    stdout: bool = False,
    extra: Callable[[Job], list[str]] | None = None,
    env: Callable[[Job], dict[str, str]] | None = None,
) -> None:
    def func(job: Job) -> list[Path]:
        exe = tool.path()
        assert exe
        ctx = {
            "tool": exe,
            "in": str(job.source),
            "out": str(job.target),
            "outdir": str(job.target.parent),
            "ext": job.tgt_format.extension,
            "fmt": (fmt_map or {}).get(job.tgt_format.name, job.tgt_format.name),
        }
        cmd = [a.format(**ctx) for a in argv]
        if extra:
            cmd[1:1] = extra(job)
        proc = run(cmd, cwd=job.workdir, env=env(job) if env else None)
        if stdout:
            job.target.write_bytes(proc.stdout)
        return [job.target]

    func.__name__ = name.replace("-", "_")
    converter(name, sources, targets, requires=(tool,), cost=cost, options=options, description=description, same_format=same_format, predicate=predicate)(func)


def _quality(flag: str, default: int | None = None) -> Callable[[Job], list[str]]:
    def extra(job: Job) -> list[str]:
        q = job.opt("quality", default)
        return [flag, str(int(q))] if q is not None else []

    return extra


# ------------------------------------------------------------------ HTML rendering
_register_simple("wkhtmltopdf", Tool("wkhtmltopdf", package="wkhtmltopdf"), ("html",), ("pdf",), ["{tool}", "-q", "--enable-local-file-access", "{in}", "{out}"], cost=16, description="Render HTML to PDF with the WebKit-based wkhtmltopdf")
_register_simple("wkhtmltoimage", Tool("wkhtmltoimage", package="wkhtmltopdf"), ("html",), ("png", "jpeg", "bmp", "svg"), ["{tool}", "-q", "--enable-local-file-access", "-f", "{ext}", "{in}", "{out}"], cost=16, fmt_map={"jpeg": "jpg"}, description="Render HTML to an image with wkhtmltoimage")
_register_simple("weasyprint", Tool("weasyprint", package="weasyprint"), ("html",), ("pdf",), ["{tool}", "{in}", "{out}"], cost=15, description="Render HTML to PDF with WeasyPrint (CSS paged media)")


@converter(
    "chromium",
    ("html", "svg"),
    ("pdf", "png"),
    requires=(Tool("chromium", ("chromium-browser", "google-chrome", "google-chrome-stable", "chrome", "msedge", "brave-browser", "brave", "microsoft-edge"), package="chromium"),),
    cost=18,
    options=("width", "height"),
    description="Render HTML or SVG with a headless Chromium browser (best HTML fidelity)",
)
def chromium_render(job: Job) -> list[Path]:
    exe = Tool("chromium", ("chromium-browser", "google-chrome", "google-chrome-stable", "chrome", "msedge", "brave-browser", "brave", "microsoft-edge")).path()
    assert exe
    profile = job.workdir / "chromium-profile"
    cmd = [exe, "--headless=new", "--disable-gpu", "--no-sandbox", f"--user-data-dir={profile}", "--no-first-run", "--hide-scrollbars", "--run-all-compositor-stages-before-draw", "--virtual-time-budget=5000"]
    if job.tgt_format.name == "pdf":
        cmd += [f"--print-to-pdf={job.target}", "--no-pdf-header-footer"]
    else:
        w, h = job.opt("width") or 1280, job.opt("height") or 900
        cmd += [f"--screenshot={job.target}", f"--window-size={int(w)},{int(h)}"]
    cmd.append(job.source.resolve().as_uri())
    run(cmd, timeout=300)
    if not job.target.exists():
        raise ConversionError("chromium produced no output")
    return [job.target]


# ---------------------------------------------------------------- markup / TeX
_register_simple("asciidoctor", Tool("asciidoctor", package="asciidoctor"), ("asciidoc",), ("html", "docbook"), ["{tool}", "-b", "{fmt}", "-o", "{out}", "{in}"], cost=14, fmt_map={"html": "html5", "docbook": "docbook5"}, description="AsciiDoc to HTML or DocBook with Asciidoctor")
_register_simple("asciidoctor-pdf", Tool("asciidoctor-pdf", package="asciidoctor-pdf"), ("asciidoc",), ("pdf",), ["{tool}", "-o", "{out}", "{in}"], cost=16, description="AsciiDoc to PDF with Asciidoctor PDF")
_register_simple("typst", Tool("typst", package="typst"), ("typst",), ("pdf", "svg", "png"), ["{tool}", "compile", "{in}", "{out}"], cost=12, description="Compile Typst markup")
_register_simple("dvipdfmx", Tool("dvipdfmx", ("dvipdfm", "dvipdf"), package="texlive-base"), ("dvi",), ("pdf",), ["{tool}", "-o", "{out}", "{in}"], cost=12, description="DVI to PDF")
_register_simple("dvips", Tool("dvips", package="texlive-base"), ("dvi",), ("ps",), ["{tool}", "-q", "-o", "{out}", "{in}"], cost=12, description="DVI to PostScript")
_register_simple("dvisvgm", Tool("dvisvgm", package="texlive-base"), ("dvi",), ("svg",), ["{tool}", "-n", "-o", "{out}", "{in}"], cost=12, description="DVI to SVG")


@converter(
    "latex",
    ("tex",),
    ("pdf", "dvi"),
    requires=(Tool("pdflatex", ("xelatex", "lualatex", "tectonic", "latex"), package="texlive-latex-base"),),
    cost=18,
    description="Compile a LaTeX document (pdflatex, xelatex, lualatex or tectonic; two passes)",
)
def latex_compile(job: Job) -> list[Path]:
    tool = Tool("pdflatex", ("xelatex", "lualatex", "tectonic", "latex"))
    exe = tool.path()
    assert exe
    build = job.workdir / "latex"
    build.mkdir(exist_ok=True)
    src = build / job.source.name
    shutil.copy2(job.source, src)
    name = Path(exe).name
    if job.tgt_format.name == "dvi":
        cmd = [exe, "-interaction=nonstopmode", "-halt-on-error", "-output-format=dvi", src.name] if name != "latex" else [exe, "-interaction=nonstopmode", "-halt-on-error", src.name]
    elif name == "tectonic":
        cmd = [exe, "--keep-logs", "-o", str(build), str(src)]
    else:
        cmd = [exe, "-interaction=nonstopmode", "-halt-on-error", src.name]
    env = {"TEXINPUTS": f"{job.source.parent}{os.pathsep}", "HOME": str(job.workdir)}
    passes = 1 if name == "tectonic" else 2
    for _ in range(passes):
        run(cmd, cwd=build, env=env, timeout=600)
    produced = build / f"{src.stem}.{job.tgt_format.extension}"
    if not produced.exists():
        raise ConversionError("LaTeX produced no output")
    shutil.move(str(produced), job.target)
    return [job.target]


_GROFF_DEVICES = {"txt": "utf8", "html": "html", "pdf": "pdf", "ps": "ps"}


@functools.lru_cache(maxsize=1)
def _groff_targets() -> frozenset[str]:
    """Only the output devices this groff installation can drive. Debian's
    groff-base, for example, has the terminal and PostScript devices but not
    HTML or PDF, which live in the full groff package."""
    exe = Tool("groff").path()
    if not exe:
        return frozenset()
    usable = set()
    for fmt, device in _GROFF_DEVICES.items():
        try:
            proc = run([exe, "-T" + device], stdin_data=b"", check=False, timeout=30)
        except Exception:
            continue
        if proc.returncode == 0:
            usable.add(fmt)
    return frozenset(usable)


@converter("groff", ("man",), _groff_targets, requires=(Tool("groff", package="groff"),), cost=12, description="Format a manual page with groff")
def groff_convert(job: Job) -> list[Path]:
    exe = Tool("groff").path()
    assert exe
    device = _GROFF_DEVICES[job.tgt_format.name]
    cmd = [exe, "-man", "-T" + device, str(job.source)]
    if device == "utf8":
        cmd.insert(1, "-c")
    proc = run(cmd)
    data = proc.stdout
    if device == "utf8":
        # Remove overstrike sequences (bold/underline emulation) for plain text.
        import re

        text = data.decode("utf-8", "replace")
        text = re.sub(r".\x08", "", text)
        data = text.encode("utf-8")
    job.target.write_bytes(data)
    return [job.target]


_register_simple("graphviz", Tool("dot", package="graphviz"), ("dot",), ("svg", "png", "pdf", "ps", "eps", "jpeg", "gif", "webp", "bmp", "tiff", "json", "dot"), ["{tool}", "-T{fmt}", "-o", "{out}", "{in}"], cost=8, fmt_map={"jpeg": "jpg", "dot": "canon"}, same_format=True, description="Lay out a Graphviz graph")

# --------------------------------------------------------------- legacy office
_register_simple("antiword", Tool("antiword", package="antiword"), ("doc",), ("txt",), ["{tool}", "-t", "-w", "0", "{in}"], cost=12, stdout=True, description="Word 97-2003 text extraction with antiword")
_register_simple("catdoc", Tool("catdoc", package="catdoc"), ("doc",), ("txt",), ["{tool}", "-w", "{in}"], cost=13, stdout=True, description="Word 97-2003 text extraction with catdoc")
_register_simple("xls2csv", Tool("xls2csv", package="catdoc"), ("xls",), ("csv",), ["{tool}", "{in}"], cost=13, stdout=True, description="Excel 97-2003 to CSV with catdoc's xls2csv")
_register_simple("catppt", Tool("catppt", package="catdoc"), ("ppt",), ("txt",), ["{tool}", "{in}"], cost=13, stdout=True, description="PowerPoint 97-2003 text extraction")
_register_simple("odt2txt", Tool("odt2txt", package="odt2txt"), ("odt", "ods", "odp", "sxw"), ("txt",), ["{tool}", "--output={out}", "{in}"], cost=12, description="OpenDocument text extraction")
_register_simple("docx2txt", Tool("docx2txt", package="docx2txt"), ("docx",), ("txt",), ["{tool}", "{in}", "{out}"], cost=12, description="DOCX text extraction")
_register_simple("unrtf", Tool("unrtf", package="unrtf"), ("rtf",), ("html", "txt", "tex"), ["{tool}", "--{fmt}", "{in}"], cost=13, stdout=True, fmt_map={"tex": "latex", "txt": "text"}, description="RTF to HTML, text or LaTeX with unrtf")
_register_simple("ssconvert", Tool("ssconvert", package="gnumeric"), ("xls", "xlsx", "ods", "csv", "tsv", "gnumeric", "html"), ("xlsx", "xls", "ods", "csv", "html", "pdf", "tex", "gnumeric", "txt"), ["{tool}", "{in}", "{out}"], cost=22, env=lambda job: {"HOME": str(job.workdir)}, predicate=lambda s, t: s != t, description="Spreadsheet conversion with Gnumeric's ssconvert")

# ---------------------------------------------------------------------- DjVu
_register_simple("ddjvu", Tool("ddjvu", package="djvulibre-bin"), ("djvu",), ("pdf", "tiff", "pbm", "pgm", "ppm", "pnm"), ["{tool}", "-format={fmt}", "{in}", "{out}"], cost=12, description="Render DjVu with DjVuLibre")
_register_simple("djvutxt", Tool("djvutxt", package="djvulibre-bin"), ("djvu",), ("txt",), ["{tool}", "{in}", "{out}"], cost=12, description="DjVu text layer extraction")
_register_simple("pdf2djvu", Tool("pdf2djvu", package="pdf2djvu"), ("pdf",), ("djvu",), ["{tool}", "-q", "-o", "{out}", "{in}"], cost=15, description="PDF to DjVu")

# --------------------------------------------------------------- poppler extras
@converter("pdfimages", ("pdf",), ("png", "jpeg", "tiff", "ppm", "pbm"), requires=(Tool("pdfimages", package="poppler-utils"),), cost=62, options=("pages",), description="Extract embedded images with poppler (use with --extract-images)")
def pdfimages_extract(job: Job) -> list[Path]:
    exe = Tool("pdfimages").path()
    assert exe
    flag = {"png": "-png", "jpeg": "-j", "tiff": "-tiff", "ppm": None, "pbm": None}[job.tgt_format.name]
    cmd = [exe]
    if flag:
        cmd.append(flag)
    pages = job.opt("pages")
    if pages and "-" in str(pages) and "," not in str(pages):
        lo, _, hi = str(pages).partition("-")
        cmd += ["-f", lo or "1"] + (["-l", hi] if hi else [])
    prefix = job.workdir / "img"
    cmd += [str(job.source), str(prefix)]
    run(cmd)
    produced = sorted(job.workdir.glob("img-*"))
    if not produced:
        raise ConversionError("no embedded images found")
    outputs = []
    for i, p in enumerate(produced):
        out = job.target.with_name(f"{job.target.stem}-{i + 1:03d}{p.suffix}")
        shutil.move(str(p), out)
        outputs.append(out)
    return outputs


@converter("pdfseparate", ("pdf",), ("pdf",), requires=(Tool("pdfseparate", package="poppler-utils"),), cost=52, same_format=True, description="Split a PDF into pages with poppler (use with --split)")
def pdfseparate_split(job: Job) -> list[Path]:
    exe = Tool("pdfseparate").path()
    assert exe
    pattern = job.workdir / "page-%d.pdf"
    run([exe, str(job.source), str(pattern)])
    produced = sorted(job.workdir.glob("page-*.pdf"), key=lambda p: int(p.stem.split("-")[1]))
    outputs = []
    for i, p in enumerate(produced):
        out = job.numbered(i, len(produced))
        shutil.move(str(p), out)
        outputs.append(out)
    return outputs


@converter("pdfunite", ("pdf",), ("pdf",), requires=(Tool("pdfunite", package="poppler-utils"),), cost=15, many_to_one=True, description="Merge PDFs with poppler")
def pdfunite_merge(job: Job) -> list[Path]:
    exe = Tool("pdfunite").path()
    assert exe
    run([exe, *[str(s) for s in job.sources], str(job.target)])
    return [job.target]


# ------------------------------------------------------------- image codecs
_register_simple("heif-convert", Tool("heif-convert", package="libheif-examples"), ("heif", "avif"), ("jpeg", "png"), ["{tool}", "{in}", "{out}"], cost=14, options=("quality",), extra=_quality("-q"), description="Decode HEIF/AVIF with libheif")
_register_simple("heif-enc", Tool("heif-enc", package="libheif-examples"), ("jpeg", "png"), ("heif", "avif"), ["{tool}", "-o", "{out}", "{in}"], cost=14, options=("quality",), extra=lambda job: (["-A"] if job.tgt_format.name == "avif" else []) + _quality("-q")(job), description="Encode HEIF/AVIF with libheif")
_register_simple("avifenc", Tool("avifenc", package="libavif-bin"), ("jpeg", "png"), ("avif",), ["{tool}", "{in}", "{out}"], cost=13, options=("quality",), extra=_quality("-q"), description="Encode AVIF with libavif")
_register_simple("avifdec", Tool("avifdec", package="libavif-bin"), ("avif",), ("png", "jpeg"), ["{tool}", "{in}", "{out}"], cost=13, description="Decode AVIF with libavif")
_register_simple("cjxl", Tool("cjxl", package="libjxl-tools"), ("png", "jpeg", "gif", "ppm", "pgm", "pam", "exr", "apng"), ("jxl",), ["{tool}", "{in}", "{out}"], cost=12, options=("quality",), extra=_quality("-q"), description="Encode JPEG XL")
_register_simple("djxl", Tool("djxl", package="libjxl-tools"), ("jxl",), ("png", "jpeg", "ppm", "pgm", "pam", "exr", "apng"), ["{tool}", "{in}", "{out}"], cost=12, description="Decode JPEG XL")
_register_simple("cwebp", Tool("cwebp", package="webp"), ("png", "jpeg", "tiff", "webp"), ("webp",), ["{tool}", "-quiet", "{in}", "-o", "{out}"], cost=13, options=("quality", "lossless"), extra=lambda job: _quality("-q")(job) + (["-lossless"] if job.opt("lossless") else []), same_format=True, description="Encode WebP with libwebp")
_register_simple("dwebp", Tool("dwebp", package="webp"), ("webp",), ("png", "pam", "ppm", "pgm", "bmp", "tiff"), ["{tool}", "{in}", "-o", "{out}"], cost=13, extra=lambda job: ["-" + job.tgt_format.name] if job.tgt_format.name != "png" else [], description="Decode WebP with libwebp")
_register_simple("gif2webp", Tool("gif2webp", package="webp"), ("gif",), ("webp",), ["{tool}", "-quiet", "{in}", "-o", "{out}"], cost=12, options=("quality", "lossless"), extra=lambda job: _quality("-q")(job) + (["-lossless"] if job.opt("lossless") else []), description="Animated GIF to animated WebP")

# ------------------------------------------------------------ image optimisers
_register_simple("optipng", Tool("optipng", package="optipng"), ("png", "bmp", "gif", "pnm", "tiff"), ("png",), ["{tool}", "-quiet", "-o2", "-out", "{out}", "{in}"], cost=30, same_format=True, description="Lossless PNG optimisation (also converts BMP/GIF/PNM/TIFF)")
_register_simple("pngquant", Tool("pngquant", package="pngquant"), ("png",), ("png",), ["{tool}", "--force", "--skip-if-larger", "--output", "{out}", "{in}"], cost=32, same_format=True, options=("quality",), extra=lambda job: ["--quality", f"0-{int(job.opt('quality'))}"] if job.opt("quality") else [], description="Lossy PNG palette quantisation")
_register_simple("gifsicle", Tool("gifsicle", package="gifsicle"), ("gif",), ("gif",), ["{tool}", "-O3", "-o", "{out}", "{in}"], cost=30, same_format=True, options=("width", "height"), extra=lambda job: (["--resize", f"{job.opt('width') or '_'}x{job.opt('height') or '_'}"] if job.opt("width") or job.opt("height") else []), description="GIF optimisation and resizing")
_register_simple("svgo", Tool("svgo", package="node-svgo"), ("svg",), ("svg",), ["{tool}", "-q", "-i", "{in}", "-o", "{out}"], cost=30, same_format=True, description="SVG minification with svgo")
_register_simple("scour", Tool("scour", package="scour"), ("svg",), ("svg",), ["{tool}", "-q", "-i", "{in}", "-o", "{out}"], cost=31, same_format=True, description="SVG clean-up with scour")


@converter("jpegoptim", ("jpeg",), ("jpeg",), requires=(Tool("jpegoptim", package="jpegoptim"),), cost=30, same_format=True, options=("quality", "strip_metadata"), description="JPEG optimisation (lossless, or lossy with --quality)")
def jpegoptim_convert(job: Job) -> list[Path]:
    exe = Tool("jpegoptim").path()
    assert exe
    shutil.copy2(job.source, job.target)
    cmd = [exe, "-q", "--force"]
    if job.opt("quality"):
        cmd.append(f"-m{int(job.opt('quality'))}")
    if job.opt("strip_metadata"):
        cmd.append("--strip-all")
    cmd.append(str(job.target))
    run(cmd)
    return [job.target]


# ------------------------------------------------------------------ camera RAW
_register_simple("dcraw", Tool("dcraw", package="dcraw"), RAW_FORMATS, ("ppm", "tiff"), ["{tool}", "-c", "-w", "{in}"], cost=15, stdout=True, extra=lambda job: ["-T"] if job.tgt_format.name == "tiff" else [], description="Decode camera RAW with dcraw")
_register_simple("darktable-cli", Tool("darktable-cli", package="darktable"), RAW_FORMATS + ("tiff", "png", "jpeg"), ("jpeg", "png", "tiff", "exr", "pfm", "webp", "jp2"), ["{tool}", "{in}", "{out}", "--core", "--configdir", "{outdir}/.dt"], cost=25, env=lambda job: {"HOME": str(job.workdir)}, predicate=lambda s, t: s != t, description="Develop camera RAW with darktable")
_register_simple("rawtherapee-cli", Tool("rawtherapee-cli", package="rawtherapee"), RAW_FORMATS, ("jpeg", "png", "tiff"), ["{tool}", "-o", "{out}", "-{fmt}", "-Y", "-c", "{in}"], cost=26, fmt_map={"jpeg": "j", "png": "n", "tiff": "t"}, description="Develop camera RAW with RawTherapee")

# ---------------------------------------------------------------------- audio
@converter("timidity", ("midi",), ("wav", "au", "aiff", "ogg", "flac"), requires=(Tool("timidity", package="timidity"),), cost=12, options=("sample_rate",), description="Synthesise MIDI to audio with TiMidity++")
def timidity_convert(job: Job) -> list[Path]:
    exe = Tool("timidity").path()
    assert exe
    mode = {"wav": "w", "au": "u", "aiff": "a", "ogg": "v", "flac": "F"}[job.tgt_format.name]
    base = [exe, "-O" + mode, "-o", str(job.target)]
    if job.opt("sample_rate"):
        base += ["-s", str(int(job.opt("sample_rate")))]
    # Distributions ship several instrument configurations; the default one
    # may reference a SoundFont that is not installed, so try each in turn.
    configs: list[list[str]] = [[]]
    for cfg in sorted(glob.glob("/etc/timidity/*.cfg")):
        if not cfg.endswith("timidity.cfg"):
            configs.append(["-c", cfg])
    last: ConversionError | None = None
    for cfg_args in configs:
        try:
            run(base + cfg_args + [str(job.source)], timeout=600)
            if job.target.exists() and job.target.stat().st_size > 0:
                return [job.target]
        except ConversionError as exc:
            last = exc
    raise last or ConversionError("timidity produced no output")


@converter("fluidsynth", ("midi",), ("wav", "flac", "au", "aiff"), requires=(Tool("fluidsynth", package="fluidsynth"),), cost=13, options=("sample_rate",), description="Synthesise MIDI to audio with FluidSynth (needs a SoundFont)")
def fluidsynth_convert(job: Job) -> list[Path]:
    exe = Tool("fluidsynth").path()
    assert exe
    fonts = glob.glob("/usr/share/sounds/sf2/*.sf2") + glob.glob("/usr/share/soundfonts/*.sf2") + glob.glob("/usr/share/sounds/sf3/*.sf3")
    fonts += glob.glob(os.path.expandvars(r"%ProgramFiles%\FluidSynth\**\*.sf2"), recursive=True) + glob.glob(r"C:\soundfonts\*.sf2")
    if os.environ.get("SOUNDFONT"):
        fonts.insert(0, os.environ["SOUNDFONT"])
    if not fonts:
        raise ConversionError("no SoundFont found (install fluid-soundfont-gm)")
    cmd = [exe, "-ni", "-F", str(job.target), "-T", job.tgt_format.name if job.tgt_format.name != "aiff" else "aiff"]
    if job.opt("sample_rate"):
        cmd += ["-r", str(int(job.opt("sample_rate")))]
    cmd += [sorted(fonts)[0], str(job.source)]
    run(cmd, timeout=600)
    return [job.target]


_register_simple("mpg123", Tool("mpg123", package="mpg123"), ("mp3", "mp2"), ("wav", "au"), ["{tool}", "-q", "-w", "{out}", "{in}"], cost=28, description="MPEG audio decoding with mpg123")
_register_simple("faad", Tool("faad", package="faad"), ("aac", "m4a"), ("wav",), ["{tool}", "-q", "-o", "{out}", "{in}"], cost=28, description="AAC decoding with faad")
_register_simple("wavpack", Tool("wavpack", package="wavpack"), ("wav",), ("wv",), ["{tool}", "-q", "-y", "{in}", "-o", "{out}"], cost=28, description="WavPack encoding")
_register_simple("wvunpack", Tool("wvunpack", package="wavpack"), ("wv",), ("wav",), ["{tool}", "-q", "-y", "{in}", "-o", "{out}"], cost=28, description="WavPack decoding")
_register_simple("speexenc", Tool("speexenc", package="speex"), ("wav",), ("spx",), ["{tool}", "{in}", "{out}"], cost=28, description="Speex encoding")
_register_simple("speexdec", Tool("speexdec", package="speex"), ("spx",), ("wav",), ["{tool}", "{in}", "{out}"], cost=28, description="Speex decoding")
_register_simple("twolame", Tool("twolame", package="twolame"), ("wav", "aiff"), ("mp2",), ["{tool}", "{in}", "{out}"], cost=28, options=("bitrate",), extra=lambda job: ["-b", str(job.opt("bitrate")).lower().rstrip("k")] if job.opt("bitrate") else [], description="MPEG-1 Layer II encoding with TwoLAME")
_register_simple("fdkaac", Tool("fdkaac", package="fdkaac"), ("wav",), ("m4a",), ["{tool}", "-S", "-o", "{out}", "{in}"], cost=28, options=("bitrate",), extra=lambda job: ["-b", str(job.opt("bitrate")).lower().rstrip("k")] if job.opt("bitrate") else [], description="AAC encoding with fdkaac")
_register_simple("mac", Tool("mac", package="monkeys-audio"), ("wav", "ape"), ("ape", "wav"), ["{tool}", "{in}", "{out}"], cost=28, extra=lambda job: ["-c2000"] if job.tgt_format.name == "ape" else ["-d"], predicate=lambda s, t: s != t, description="Monkey's Audio encoding/decoding")

# ---------------------------------------------------------------------- fonts
@converter("woff2-tools", ("ttf", "otf", "woff2"), ("woff2", "ttf", "otf"), requires=(Tool("woff2_compress", ("woff2_decompress",), package="woff2"),), cost=12, description="WOFF2 compression/decompression with Google's woff2 tools", predicate=lambda s, t: (s == "woff2") != (t == "woff2"))
def woff2_tools(job: Job) -> list[Path]:
    work = job.workdir / "woff2"
    work.mkdir(exist_ok=True)
    src = work / job.source.name
    shutil.copy2(job.source, src)
    if job.tgt_format.name == "woff2":
        exe = Tool("woff2_compress").path()
        if not exe:
            raise ConversionError("woff2_compress not found")
        run([exe, str(src)])
        produced = src.with_suffix(".woff2")
    else:
        exe = Tool("woff2_decompress").path()
        if not exe:
            raise ConversionError("woff2_decompress not found")
        run([exe, str(src)])
        produced = src.with_suffix(".ttf")
    if not produced.exists():
        raise ConversionError("woff2 tool produced no output")
    shutil.move(str(produced), job.target)
    return [job.target]


_register_simple("sfnt2woff", Tool("sfnt2woff-zopfli", ("sfnt2woff",), package="sfnt2woff-zopfli"), ("ttf", "otf"), ("woff",), ["{tool}", "-o", "{out}", "{in}"], cost=13, description="WOFF compression with sfnt2woff")
_register_simple("woff2sfnt", Tool("woff2sfnt-zopfli", ("woff2sfnt",), package="sfnt2woff-zopfli"), ("woff",), ("ttf",), ["{tool}", "{in}"], cost=13, stdout=True, description="WOFF decompression with woff2sfnt")

# ------------------------------------------------------------------- 3D models
_ASSIMP_EXPORT = {"obj": "obj", "stl": "stl", "ply": "ply", "gltf": "gltf2", "glb": "glb2", "dae": "collada", "fbx": "fbx", "3ds": "3ds", "x3d": "x3d", "3mf": "3mf", "x": "x", "assxml": "assxml"}
_register_simple("assimp", Tool("assimp", package="assimp-utils"), MODEL_FORMATS, tuple(_ASSIMP_EXPORT), ["{tool}", "export", "{in}", "{out}", "-f{fmt}"], cost=15, fmt_map=_ASSIMP_EXPORT, predicate=lambda s, t: s != t, description="3D model conversion with Open Asset Import Library (assimp)")
