"""Backend modules. Importing this package registers every converter.

Each module must import cleanly even when its backend is absent: optional
libraries are imported inside the conversion functions, and external tools
are only looked up when a converter's availability is queried.
"""

from __future__ import annotations

import importlib
import logging

_MODULES = (
    "image_pillow",
    "image_magick",
    "vector",
    "ffmpeg_media",
    "audio_tools",
    "pdf_tools",
    "office",
    "pandoc_docs",
    "ebook",
    "text_docs",
    "data_formats",
    "archives",
    "fonts",
    "ocr",
)

_loaded = False


def load_all() -> None:
    """Import every backend module once. Failures are logged, not raised,
    so one broken module can never take the whole application down."""
    global _loaded
    if _loaded:
        return
    for mod in _MODULES:
        try:
            importlib.import_module(f"omniconv.converters.{mod}")
        except Exception as exc:  # pragma: no cover - defensive
            logging.getLogger(__name__).warning("backend %s failed to load: %s", mod, exc)
    _loaded = True
