"""Conversion options.

Options are plain key/value pairs passed to converters in a dictionary.
The specs below exist so the CLI can generate flags and the GUI can build
widgets from one source of truth; a converter simply reads the keys it
honours and ignores the rest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class OptionSpec:
    name: str
    type: type
    help: str
    default: Any = None
    categories: tuple[str, ...] = ()
    choices: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None

    def coerce(self, value: Any) -> Any:
        if value is None or value == "":
            return None
        if self.type is bool:
            if isinstance(value, str):
                return value.lower() in ("1", "true", "yes", "on")
            return bool(value)
        return self.type(value)


# fmt: off
OPTION_SPECS: dict[str, OptionSpec] = {s.name: s for s in [
    OptionSpec("quality", int, "Lossy encoder quality, 1-100", None, ("image", "vector", "document", "video"), minimum=1, maximum=100),
    OptionSpec("width", int, "Target width in pixels (aspect kept if height is omitted)", None, ("image", "vector", "video", "document"), minimum=1),
    OptionSpec("height", int, "Target height in pixels", None, ("image", "vector", "video", "document"), minimum=1),
    OptionSpec("dpi", int, "Resolution used when rasterising documents or vectors", 150, ("image", "vector", "document"), minimum=1),
    OptionSpec("grayscale", bool, "Convert to grayscale", False, ("image", "video", "document")),
    OptionSpec("rotate", int, "Rotate clockwise by this many degrees", None, ("image", "document")),
    OptionSpec("background", str, "Colour used to flatten transparency, e.g. white or #ffffff", None, ("image", "vector", "document")),
    OptionSpec("strip_metadata", bool, "Drop EXIF/XMP and other metadata", False, ("image", "audio", "video")),
    OptionSpec("optimize", bool, "Ask the encoder for extra compression effort", False, ("image",)),
    OptionSpec("lossless", bool, "Prefer lossless encoding where the format allows it", False, ("image",)),
    OptionSpec("frame", int, "For multi-page/animated sources: pick a single page or frame (0-based)", None, ("image", "document")),
    OptionSpec("bitrate", str, "Audio bitrate, e.g. 192k", None, ("audio", "video")),
    OptionSpec("sample_rate", int, "Audio sample rate in Hz", None, ("audio", "video")),
    OptionSpec("channels", int, "Audio channel count (1 mono, 2 stereo)", None, ("audio", "video"), minimum=1, maximum=8),
    OptionSpec("normalize", bool, "Apply EBU R128 loudness normalisation", False, ("audio", "video")),
    OptionSpec("volume", str, "Volume adjustment, e.g. 0.5 or +3dB", None, ("audio", "video")),
    OptionSpec("start", str, "Trim: start time (seconds or HH:MM:SS)", None, ("audio", "video")),
    OptionSpec("duration", str, "Trim: duration (seconds or HH:MM:SS)", None, ("audio", "video")),
    OptionSpec("video_bitrate", str, "Video bitrate, e.g. 2M", None, ("video",)),
    OptionSpec("crf", int, "Constant rate factor (lower is better quality)", None, ("video",), minimum=0, maximum=63),
    OptionSpec("fps", float, "Frame rate", None, ("video", "image")),
    OptionSpec("no_audio", bool, "Drop audio streams", False, ("video",)),
    OptionSpec("video_codec", str, "Force a video codec, e.g. libx265", None, ("video",)),
    OptionSpec("audio_codec", str, "Force an audio codec, e.g. libopus", None, ("audio", "video")),
    OptionSpec("pages", str, "Page selection, e.g. 1-3,7 (1-based)", None, ("document", "image", "ebook")),
    OptionSpec("password", str, "Password for encrypted input or for encrypting output", None, ("document",)),
    OptionSpec("compress", int, "Compression level (0-9) for archives, or PDF compression preset 0-3", None, ("archive", "document"), minimum=0, maximum=9),
    OptionSpec("ocr_language", str, "Tesseract language code(s) for OCR, e.g. eng+deu", "eng", ("document", "image")),
    OptionSpec("encoding", str, "Text encoding for text-based inputs", None, ("data", "document")),
    OptionSpec("delimiter", str, "Field delimiter for CSV-like formats", None, ("data",)),
    OptionSpec("indent", int, "Indentation for pretty-printed output", 2, ("data",)),
    OptionSpec("sheet", str, "Sheet name or index for spreadsheets", None, ("data", "document")),
    OptionSpec("title", str, "Document title metadata", None, ("document", "ebook")),
    OptionSpec("author", str, "Document author metadata", None, ("document", "ebook")),
    OptionSpec("font_size", int, "Base font size for text-to-document conversions", 11, ("document",)),
    OptionSpec("page_size", str, "Paper size for generated documents (A4, Letter, ...)", "A4", ("document",), choices=("A4", "A5", "Letter", "Legal")),
]}
# fmt: on


def coerce_options(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise user-provided option values according to the specs; unknown
    keys are passed through untouched so backends can accept extras."""
    out: dict[str, Any] = {}
    for key, value in raw.items():
        spec = OPTION_SPECS.get(key)
        if spec is None:
            out[key] = value
            continue
        coerced = spec.coerce(value)
        if coerced is not None:
            out[key] = coerced
    return out


def specs_for(categories: set[str]) -> list[OptionSpec]:
    return [s for s in OPTION_SPECS.values() if s.categories and set(s.categories) & categories]


def parse_pages(spec: str | None, page_count: int) -> list[int]:
    """Parse ``"1-3,7"`` into 0-based indices, clipped to ``page_count``."""
    if not spec:
        return list(range(page_count))
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, _, hi = part.partition("-")
            lo_i = int(lo) if lo.strip() else 1
            hi_i = int(hi) if hi.strip() else page_count
            pages.extend(range(lo_i - 1, min(hi_i, page_count)))
        else:
            idx = int(part) - 1
            if 0 <= idx < page_count:
                pages.append(idx)
    seen: set[int] = set()
    ordered = []
    for p in pages:
        if 0 <= p < page_count and p not in seen:
            seen.add(p)
            ordered.append(p)
    return ordered
