"""Omniconv: a native Linux file conversion application.

The package is organised in three layers:

* ``omniconv.core`` holds the format table, the converter registry, the
  route-finding algorithm and the execution engine. It knows nothing about
  any particular backend.
* ``omniconv.converters`` contains one module per backend (Pillow, ffmpeg,
  ImageMagick, Ghostscript, LibreOffice, pandoc, ...). Each module registers
  converters with the registry and declares which external tools or Python
  modules it needs. A converter whose requirements are not met is simply
  invisible, so the application degrades gracefully on a minimal system.
* ``omniconv.cli`` and ``omniconv.gui`` are thin front ends over the engine.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
