"""Helpers shared by several backends."""

from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import Any

from omniconv.core.engine import Job
from omniconv.core.requirements import AnyOf, Module

# PyMuPDF is importable as ``pymupdf`` (new) or ``fitz`` (legacy).
PYMUPDF = AnyOf((Module("pymupdf", "pymupdf"), Module("fitz", "pymupdf")))

_NAMED_COLOURS = {
    "white": (255, 255, 255),
    "black": (0, 0, 0),
    "transparent": (0, 0, 0, 0),
    "red": (255, 0, 0),
    "green": (0, 128, 0),
    "blue": (0, 0, 255),
    "gray": (128, 128, 128),
    "grey": (128, 128, 128),
}


def parse_colour(value: str | None, default: tuple[int, ...] = (255, 255, 255)) -> tuple[int, ...]:
    if not value:
        return default
    v = value.strip().lower()
    if v in _NAMED_COLOURS:
        return _NAMED_COLOURS[v]
    m = re.fullmatch(r"#?([0-9a-f]{6})([0-9a-f]{2})?", v)
    if m:
        rgb = tuple(int(m.group(1)[i : i + 2], 16) for i in (0, 2, 4))
        if m.group(2):
            return rgb + (int(m.group(2), 16),)
        return rgb
    m = re.fullmatch(r"#?([0-9a-f]{3})", v)
    if m:
        return tuple(int(c * 2, 16) for c in m.group(1))
    return default


def fit_size(width: int, height: int, want_w: int | None, want_h: int | None) -> tuple[int, int]:
    """Compute a new size keeping the aspect ratio when only one side is given."""
    if want_w and want_h:
        return int(want_w), int(want_h)
    if want_w:
        return int(want_w), max(1, round(height * want_w / width))
    if want_h:
        return max(1, round(width * want_h / height)), int(want_h)
    return width, height


def parse_time(value: str | float | int | None) -> float | None:
    """Accept seconds or HH:MM:SS(.fff) and return seconds."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    parts = str(value).strip().split(":")
    total = 0.0
    for part in parts:
        total = total * 60 + float(part)
    return total


@functools.lru_cache(maxsize=None)
def tool_output(*cmd: str) -> str:
    """Cached stdout of a tool, used to probe capabilities (encoders, formats)."""
    from omniconv.core.procs import run

    try:
        return run(cmd, check=False, timeout=60).stdout.decode("utf-8", "replace")
    except Exception:
        return ""


def opt_int(job: Job, name: str) -> int | None:
    v = job.options.get(name)
    return int(v) if v not in (None, "") else None


def size_args(job: Job) -> tuple[int | None, int | None]:
    return opt_int(job, "width"), opt_int(job, "height")


def load_pymupdf():
    """Import PyMuPDF under its new name, falling back to the legacy ``fitz``."""
    try:
        import pymupdf as module
    except ImportError:
        import fitz as module
    try:
        # MuPDF prints CSS and font warnings to stderr; they are not errors here.
        module.TOOLS.mupdf_display_errors(False)
    except Exception:
        pass
    return module
