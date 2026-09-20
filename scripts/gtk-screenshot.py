#!/usr/bin/env python3
"""Render the GTK 4 window to PNG under a virtual display.

GTK needs a real display even to lay widgets out, so this runs under
xvfb-run in CI. It snapshots through GSK rather than a screen-capture
tool, which keeps the image to the window itself.

Usage: xvfb-run -a python scripts/gtk-screenshot.py OUTDIR
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

import importlib.util  # noqa: E402

# The sample files are defined next door; the file name has a dash, so it
# cannot simply be imported.
_spec = importlib.util.spec_from_file_location("omniconv_shots", Path(__file__).resolve().parent / "gui-screenshot.py")
qt_shots = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(qt_shots)


def pump(ms: int = 400) -> None:
    ctx = GLib.MainContext.default()
    deadline = GLib.get_monotonic_time() + ms * 1000
    while GLib.get_monotonic_time() < deadline:
        if not ctx.iteration(False):
            GLib.usleep(5000)


def grab(window, path: Path) -> None:
    """Snapshot through the window's own renderer; fall back to a screen
    capture if the node comes back empty."""
    width, height = window.get_width(), window.get_height()
    native = window.get_native()
    renderer = native.get_renderer() if native else None
    snapshot = Gtk.Snapshot()
    paintable = Gtk.WidgetPaintable.new(window)
    paintable.snapshot(snapshot, width, height)
    node = snapshot.to_node()
    if renderer is not None and node is not None:
        texture = renderer.render_texture(node, None)
        texture.save_to_png(str(path))
    else:
        subprocess.run(["import", "-window", "root", str(path)], check=True)
    print(f"{path.name}: {width}x{height}, {path.stat().st_size} bytes")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("outdir", type=Path)
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    Adw.init()
    from omniconv.gui.window import BackendsWindow, MainWindow

    app = Adw.Application(application_id="io.github.omniconv.Omniconv.Screenshots")
    app.register(None)

    window = MainWindow(application=app)
    window.set_default_size(1000, 640)
    window.present()
    pump()
    grab(window, args.outdir / "01-empty.png")

    tmp = Path(tempfile.mkdtemp(prefix="omniconv-gtk-shot-"))
    paths = qt_shots.sample_files(tmp)
    window.add_paths([str(p) for p in paths])
    pump()
    grab(window, args.outdir / "02-files-added.png")

    window.start_conversion()
    for _ in range(60):
        pump(200)
        if window.worker is None or not window.worker.is_alive():
            break
    pump()
    grab(window, args.outdir / "03-converted.png")

    backends = BackendsWindow(application=app)
    backends.set_default_size(820, 620)
    backends.present()
    pump()
    grab(backends, args.outdir / "04-backends.png")

    for p in tmp.glob("*"):
        p.unlink()
    tmp.rmdir()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
