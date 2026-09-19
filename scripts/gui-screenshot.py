#!/usr/bin/env python3
"""Render the Qt window to PNG files without a desktop.

Qt's offscreen platform still rasterises widgets, so the layout can be
inspected on a build machine that has no display. CI runs this on both
Windows and Linux and uploads the images, which is the only way the
Windows window gets looked at at all.

Usage: python scripts/gui-screenshot.py OUTDIR [--scale N]
"""

from __future__ import annotations

import argparse
import os
import struct
import sys
import tempfile
import zlib
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def sample_files(directory: Path) -> list[Path]:
    """Write a handful of small inputs covering several categories, so the
    format column, the target list and the options panel all have content."""
    made: list[Path] = []

    png = directory / "diagram.png"
    raw = b"".join(b"\x00" + bytes([(x * 4) % 256, (x * 2) % 256, 200]) * 32 for x in range(32))
    chunks = b""
    for tag, payload in (
        (b"IHDR", struct.pack(">IIBBBBB", 32, 32, 8, 2, 0, 0, 0)),
        (b"IDAT", zlib.compress(raw)),
        (b"IEND", b""),
    ):
        chunks += struct.pack(">I", len(payload)) + tag + payload
        chunks += struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + chunks)
    made.append(png)

    jpg = directory / "photo.jpg"
    try:
        from PIL import Image

        Image.new("RGB", (64, 48), (120, 90, 200)).save(jpg)
        made.append(jpg)
    except Exception:
        pass

    txt = directory / "notes.txt"
    txt.write_text("Omniconv screenshot sample.\n" * 4, encoding="utf-8")
    made.append(txt)
    return made


def save(widget, path: Path) -> None:
    pixmap = widget.grab()
    if not pixmap.save(str(path), "PNG"):
        raise SystemExit(f"could not write {path}")
    print(f"{path.name}: {pixmap.width()}x{pixmap.height()}, {path.stat().st_size} bytes")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("outdir", type=Path)
    parser.add_argument("--keep-samples", action="store_true")
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    from PySide6 import QtCore, QtWidgets

    from omniconv.gui.qt_app import BackendsDialog, MainWindow, create_app

    app = create_app([sys.argv[0]])
    app.processEvents()

    window = MainWindow()
    window.resize(1000, 640)
    window.show()
    app.processEvents()
    save(window, args.outdir / "01-empty.png")

    tmp = Path(tempfile.mkdtemp(prefix="omniconv-shot-"))
    paths = sample_files(tmp)
    window.add_paths([str(p) for p in paths])
    app.processEvents()
    save(window, args.outdir / "02-files-added.png")

    # The result column, the summary line and the "open output folder"
    # button only appear after a run, so drive one synchronously.
    window.start_conversion()
    if window.worker is not None:
        window.worker.wait(120_000)
        for _ in range(20):
            app.processEvents()
            QtCore.QThread.msleep(20)
    save(window, args.outdir / "03-converted.png")

    small = MainWindow()
    small.resize(*small.minimumSize().toTuple())
    small.show()
    small.add_paths([str(p) for p in paths])
    app.processEvents()
    save(small, args.outdir / "04-minimum-size.png")

    dialog = BackendsDialog(window)
    dialog.show()
    app.processEvents()
    save(dialog, args.outdir / "05-backends.png")

    print(f"samples in {tmp}" if args.keep_samples else "samples discarded")
    if not args.keep_samples:
        for p in tmp.glob("*"):
            p.unlink()
        tmp.rmdir()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
