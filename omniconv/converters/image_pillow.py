"""Raster images through Pillow.

Pillow is the preferred image backend because it runs in-process, honours
every image option and preserves ICC profiles and EXIF unless asked not to.
The set of readable and writable formats is taken from Pillow's own plugin
registry, so a build without libwebp or OpenJPEG simply offers fewer formats.
"""

from __future__ import annotations

from pathlib import Path

from omniconv.core.engine import Job
from omniconv.core.errors import ConversionError
from omniconv.core.registry import converter
from omniconv.core.requirements import Module, Tool
from omniconv.converters._common import fit_size, parse_colour, size_args

# Pillow plugin id -> omniconv format names handled by that plugin.
_PLUGIN_FORMATS: dict[str, tuple[str, ...]] = {
    "PNG": ("png", "apng"),
    "JPEG": ("jpeg",),
    "GIF": ("gif",),
    "BMP": ("bmp",),
    "DIB": ("bmp",),
    "TIFF": ("tiff",),
    "WEBP": ("webp",),
    "ICO": ("ico",),
    "ICNS": ("icns",),
    "PPM": ("ppm", "pgm", "pbm", "pnm"),
    "TGA": ("tga",),
    "PCX": ("pcx",),
    "DDS": ("dds",),
    "XBM": ("xbm",),
    "XPM": ("xpm",),
    "SGI": ("sgi",),
    "PSD": ("psd",),
    "IM": ("im",),
    "QOI": ("qoi",),
    "CUR": ("cur",),
    "FITS": ("fits",),
    "MPO": ("mpo",),
    "PFM": ("pfm",),
    "BLP": ("blp",),
    "FTEX": ("ftex",),
    "EPS": ("eps",),
    "PDF": ("pdf",),
    "JPEG2000": ("jp2",),
    "HEIF": ("heif",),
    "AVIF": ("avif",),
    "SUN": ("ras",),
    "JXL": ("jxl",),
    "WMF": ("wmf", "emf"),
    "DCX": ("dcx",),
    "PCD": ("pcd",),
    "FLI": ("fli",),
    "MSP": ("msp",),
    "PALM": ("palm",),
    "GBR": ("gbr",),
}

# Targets that cannot store an alpha channel; transparency is flattened.
_NO_ALPHA = {"jpeg", "bmp", "pcx", "eps", "pdf", "ppm", "pgm", "pbm", "pnm", "xbm", "sgi", "im", "mpo", "jp2", "fits", "pfm", "tga_no"}
_ANIMATED = {"gif", "webp", "apng", "tiff", "pdf", "mng"}
# Allowed pixel modes per target; the first entry is used when a conversion is needed.
_MODES_FOR = {
    "pbm": ("1",), "pgm": ("L",), "ppm": ("RGB",), "xbm": ("1",), "jpeg": ("RGB", "L", "CMYK"), "mpo": ("RGB",),
    "jp2": ("RGB", "L", "RGBA"), "pdf": ("RGB", "L", "1", "P", "CMYK"), "eps": ("RGB", "L", "CMYK"),
    "pcx": ("RGB", "L", "P", "1"), "fits": ("L",), "pfm": ("F",),
}
_PLUGIN_FOR_TARGET = {name: plugin for plugin, names in _PLUGIN_FORMATS.items() for name in names}
_PLUGIN_FOR_TARGET["apng"] = "PNG"
_PLUGIN_FOR_TARGET["bmp"] = "BMP"
_PLUGIN_FOR_TARGET["wmf"] = "WMF"


def _pillow_registry() -> tuple[set[str], set[str]]:
    from PIL import Image

    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
        try:
            pillow_heif.register_avif_opener()
        except Exception:
            pass
    except Exception:
        pass
    try:
        import pillow_jxl  # noqa: F401
    except Exception:
        pass
    Image.init()
    readable = set(Image.OPEN)
    writable = set(Image.SAVE)
    return readable, writable


def _sources() -> set[str]:
    readable, _ = _pillow_registry()
    out: set[str] = set()
    for plugin, names in _PLUGIN_FORMATS.items():
        if plugin in readable:
            out.update(names)
    out.discard("pdf")  # Pillow writes PDF but does not read it
    if "JPEG" in readable:
        out.add("mpo")
    if "eps" in out and not Tool("gs").available():
        out.discard("eps")
    out.discard("wmf")
    out.discard("emf")
    return out


def _targets() -> set[str]:
    _, writable = _pillow_registry()
    out: set[str] = set()
    for plugin, names in _PLUGIN_FORMATS.items():
        if plugin in writable:
            out.update(names)
    out.discard("wmf")
    out.discard("emf")
    return out


def _flatten(im, colour):
    from PIL import Image

    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, tuple(colour[:3]) + (255,))
        bg.alpha_composite(rgba)
        return bg.convert("RGB")
    return im


def _prepare_frame(im, job: Job, tgt: str):
    from PIL import ImageOps

    frame = im
    try:
        frame = ImageOps.exif_transpose(frame) or frame
    except Exception:
        pass
    rotate = job.opt("rotate")
    if rotate:
        frame = frame.rotate(-int(rotate), expand=True)
    w, h = size_args(job)
    if w or h:
        frame = frame.resize(fit_size(frame.width, frame.height, w, h))
    if tgt in _NO_ALPHA:
        frame = _flatten(frame, parse_colour(job.opt("background")))
    if job.opt("grayscale"):
        frame = frame.convert("LA") if "A" in frame.getbands() else frame.convert("L")
    allowed = _MODES_FOR.get(tgt)
    if allowed and frame.mode not in allowed:
        wanted = allowed[0]
        if wanted == "1":
            frame = frame.convert("L").convert("1")
        elif wanted == "RGB" and "L" in allowed and frame.mode in ("LA", "I", "I;16"):
            frame = frame.convert("L")
        else:
            frame = frame.convert(wanted)
    if tgt in ("ico", "icns") and frame.mode not in ("RGBA", "RGB"):
        frame = frame.convert("RGBA")
    if tgt == "gif" and frame.mode not in ("P", "L", "RGB", "RGBA"):
        frame = frame.convert("RGB")
    if tgt in ("bmp", "tga", "pcx", "dds", "sgi", "tiff") and frame.mode in ("I;16", "F"):
        frame = frame.convert("L")
    if tgt == "webp" and frame.mode not in ("RGB", "RGBA"):
        frame = frame.convert("RGBA" if "A" in frame.getbands() else "RGB")
    if tgt in ("heif", "avif") and frame.mode not in ("RGB", "RGBA"):
        frame = frame.convert("RGBA" if "A" in frame.getbands() else "RGB")
    if tgt == "qoi" and frame.mode not in ("RGB", "RGBA"):
        frame = frame.convert("RGBA" if "A" in frame.getbands() else "RGB")
    if tgt == "png" and frame.mode == "CMYK":
        frame = frame.convert("RGB")
    return frame


def _save_kwargs(im, job: Job, tgt: str) -> dict:
    kwargs: dict = {}
    quality = job.opt("quality")
    if tgt in ("jpeg", "webp", "avif", "heif", "jp2", "mpo") and quality:
        kwargs["quality"] = int(quality)
    if tgt == "jp2" and quality:
        kwargs.pop("quality", None)
        kwargs["quality_mode"] = "rates"
        kwargs["quality_layers"] = [max(1.0, 100.0 / int(quality))]
    if job.opt("optimize") and tgt in ("png", "jpeg", "gif"):
        kwargs["optimize"] = True
    if job.opt("lossless") and tgt in ("webp", "jxl"):
        kwargs["lossless"] = True
    if tgt == "jp2" and job.opt("lossless"):
        kwargs["irreversible"] = False
    dpi = job.opt("dpi")
    if dpi and tgt in ("png", "jpeg", "tiff", "bmp", "pdf", "pcx"):
        kwargs["dpi"] = (int(dpi), int(dpi))
    if not job.opt("strip_metadata"):
        if "icc_profile" in im.info and tgt in ("png", "jpeg", "webp", "tiff", "avif", "heif", "jp2"):
            kwargs["icc_profile"] = im.info["icc_profile"]
        if "exif" in im.info and tgt in ("jpeg", "webp", "tiff", "png", "avif", "heif"):
            kwargs["exif"] = im.info["exif"]
    if tgt == "tiff":
        kwargs["compression"] = "tiff_lzw" if im.mode != "1" else "group4"
    if tgt == "ico":
        kwargs["sizes"] = [(s, s) for s in (16, 32, 48, 64, 128, 256) if s <= max(im.size)] or [im.size]
    return kwargs


def _frames(im):
    from PIL import ImageSequence

    return list(ImageSequence.Iterator(im))


@converter(
    "pillow",
    _sources,
    _targets,
    requires=(Module("PIL", "pillow"),),
    cost=10,
    options=("quality", "width", "height", "dpi", "grayscale", "rotate", "background", "strip_metadata", "optimize", "lossless", "frame"),
    description="Raster image conversion with Pillow",
)
def pillow_convert(job: Job) -> list[Path]:
    from PIL import Image

    _pillow_registry()
    tgt = job.tgt_format.name
    pil_format = _PLUGIN_FOR_TARGET.get(tgt, tgt.upper())
    with Image.open(job.source) as im:
        im.load()
        n_frames = getattr(im, "n_frames", 1)
        frame_opt = job.opt("frame")
        if n_frames > 1 and tgt in _ANIMATED and frame_opt is None:
            frames = [_prepare_frame(f.copy(), job, tgt) for f in _frames(im)]
            first, rest = frames[0], frames[1:]
            kwargs = _save_kwargs(im, job, tgt)
            kwargs.update(save_all=True, append_images=rest)
            if "duration" in im.info:
                kwargs["duration"] = im.info["duration"]
            if "loop" in im.info:
                kwargs["loop"] = im.info["loop"]
            if tgt == "gif":
                kwargs["disposal"] = 2
            first.save(job.target, format=pil_format, **kwargs)
            return [job.target]
        if n_frames > 1 and frame_opt is None and tgt not in _ANIMATED and job.opt("pages"):
            from omniconv.core.options import parse_pages

            outputs = []
            wanted = parse_pages(job.opt("pages"), n_frames)
            for i, idx in enumerate(wanted):
                im.seek(idx)
                frame = _prepare_frame(im.copy(), job, tgt)
                out = job.numbered(i, len(wanted))
                frame.save(out, format=pil_format, **_save_kwargs(im, job, tgt))
                outputs.append(out)
            return outputs
        if frame_opt is not None and n_frames > 1:
            im.seek(min(int(frame_opt), n_frames - 1))
        frame = _prepare_frame(im.copy(), job, tgt)
        try:
            frame.save(job.target, format=pil_format, **_save_kwargs(im, job, tgt))
        except (OSError, ValueError, KeyError) as exc:
            raise ConversionError(f"Pillow could not write {tgt}: {exc}") from exc
    return [job.target]


@converter(
    "pillow-multipage",
    _sources,
    ("pdf", "tiff", "gif", "webp", "apng"),
    requires=(Module("PIL", "pillow"),),
    cost=12,
    many_to_one=True,
    options=("quality", "width", "height", "dpi", "grayscale", "background"),
    description="Combine several images into one multi-page PDF/TIFF or animation",
)
def pillow_merge(job: Job) -> list[Path]:
    from PIL import Image

    _pillow_registry()
    tgt = job.tgt_format.name
    frames = []
    for path in job.sources:
        with Image.open(path) as im:
            im.load()
            frames.append(_prepare_frame(im.copy(), job, tgt))
    if not frames:
        raise ConversionError("no images to merge")
    kwargs: dict = {"save_all": True, "append_images": frames[1:]}
    if tgt in ("gif", "webp", "apng"):
        kwargs["duration"] = int(1000 / float(job.opt("fps", 2) or 2))
        kwargs["loop"] = 0
    if tgt == "pdf":
        dpi = int(job.opt("dpi", 150) or 150)
        kwargs["resolution"] = float(dpi)
    frames[0].save(job.target, format=_PLUGIN_FOR_TARGET.get(tgt, tgt.upper()), **kwargs)
    return [job.target]
