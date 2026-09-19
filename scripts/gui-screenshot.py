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


def report_fonts(QtGui) -> None:
    """Name the font actually in use, and fail if it has no glyphs.

    Qt's offscreen platform on Windows has no font database, so every
    character renders as a missing-glyph box and the layout is measured
    with the wrong metrics. That is invisible in an assertion and obvious
    in an image, so say it in the log either way.
    """
    font = QtGui.QGuiApplication.font()
    resolved = QtGui.QFontInfo(font).family()
    families = QtGui.QFontDatabase.families()
    metrics = QtGui.QFontMetrics(font)
    print(f"font: requested {font.family()!r}, resolved {resolved!r}, {len(families)} families in the database")
    if not families:
        raise SystemExit(
            "no fonts available: every glyph would render as a box and the "
            "layout would be measured with the wrong metrics"
        )


def dark_palette(QtGui):
    """Approximates the palette Windows hands a dark-mode application, so
    hard-coded colours and unreadable contrast show up in the images."""
    from PySide6.QtCore import Qt

    p = QtGui.QPalette()
    window, base, text = QtGui.QColor(32, 32, 32), QtGui.QColor(25, 25, 25), QtGui.QColor(230, 230, 230)
    for role, colour in (
        (QtGui.QPalette.ColorRole.Window, window),
        (QtGui.QPalette.ColorRole.Base, base),
        (QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor(45, 45, 45)),
        (QtGui.QPalette.ColorRole.Button, window),
        (QtGui.QPalette.ColorRole.WindowText, text),
        (QtGui.QPalette.ColorRole.Text, text),
        (QtGui.QPalette.ColorRole.ButtonText, text),
        (QtGui.QPalette.ColorRole.ToolTipBase, window),
        (QtGui.QPalette.ColorRole.ToolTipText, text),
        (QtGui.QPalette.ColorRole.PlaceholderText, QtGui.QColor(140, 140, 140)),
        (QtGui.QPalette.ColorRole.Mid, QtGui.QColor(140, 140, 140)),
        (QtGui.QPalette.ColorRole.Highlight, QtGui.QColor(0, 120, 212)),
        (QtGui.QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white),
    ):
        p.setColor(role, colour)
    return p


def save(widget, path: Path) -> None:
    pixmap = widget.grab()
    if not pixmap.save(str(path), "PNG"):
        raise SystemExit(f"could not write {path}")
    print(f"{path.name}: {pixmap.width()}x{pixmap.height()}, {path.stat().st_size} bytes")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("outdir", type=Path)
    parser.add_argument("--keep-samples", action="store_true")
    parser.add_argument("--dark", action="store_true", help="render with a dark palette")
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    from PySide6 import QtCore, QtGui

    from omniconv.gui.qt_app import BackendsDialog, MainWindow, create_app

    app = create_app([sys.argv[0]])
    report_fonts(QtGui)
    if args.dark:
        app.setStyle("Fusion")
        app.setPalette(dark_palette(QtGui))
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

    # The banner only appears on a sparse install, which is exactly the
    # state a fresh Windows machine is in, so force it for one image.
    window.banner.banner_label.setText(
        "12 of 122 conversion backends are installed. Many formats need external tools "
        "(ffmpeg, ImageMagick, Ghostscript, LibreOffice, ...). Run scripts\\install-deps.ps1 "
        "to install them, then restart Omniconv."
    )
    window.banner.setVisible(True)
    app.processEvents()
    save(window, args.outdir / "06-sparse-install-banner.png")

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
