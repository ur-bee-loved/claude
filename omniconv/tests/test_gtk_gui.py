"""The GTK 4 front end, driven under a virtual display.

These need PyGObject with the GTK 4 and libadwaita typelibs, which a pip
environment does not provide; CI runs them in a venv built on the system
Python with --system-site-packages. Everywhere else they skip.
"""

from __future__ import annotations

import pytest

try:
    # A broken PyGObject raises plain ImportError, which importorskip does
    # not treat as "missing", so catch it here.
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gdk, Gio, Gtk
except (ValueError, ImportError) as exc:
    pytest.skip(f"PyGObject with GTK 4 and libadwaita unavailable: {exc}", allow_module_level=True)

if not Gtk.init_check():
    pytest.skip("no display for GTK", allow_module_level=True)

Adw.init()

from omniconv.gui.window import BackendsWindow, MainWindow  # noqa: E402
from tests.conftest import backend  # noqa: E402


@pytest.fixture(scope="module")
def gtk_app():
    app = Adw.Application(application_id="io.github.omniconv.Omniconv.Tests")
    app.register(None)
    return app


@pytest.fixture
def window(gtk_app):
    w = MainWindow(application=gtk_app)
    yield w
    w.destroy()


def _pump(iterations: int = 50) -> None:
    ctx = __import__("gi.repository", fromlist=["GLib"]).GLib.MainContext.default()
    for _ in range(iterations):
        if not ctx.iteration(False):
            break


def test_window_builds(window):
    assert window.get_title() == "Omniconv"
    assert window.target_names == []
    assert window.entries == []


def test_targets_follow_inputs(window, samples):
    if not backend("pillow"):
        pytest.skip("Pillow missing")
    window.add_paths([str(samples / "sample.png"), str(samples / "sample.jpg")])
    _pump()
    assert len(window.entries) == 2
    assert "webp" in window.target_names and "pdf" in window.target_names
    assert window.selected_target() is not None


def test_option_rows_use_the_shared_labels(window, samples):
    if not backend("pillow"):
        pytest.skip("Pillow missing")
    window.add_paths([str(samples / "sample.png")])
    window.target_row.set_selected(window.target_names.index("jpeg"))
    _pump()
    assert window.collect_options() == {}
    titles = {w.get_title() for _, w in window.option_widgets.values() if hasattr(w, "get_title")}
    assert "DPI" in titles, sorted(titles)
    assert not any(t == "Dpi" for t in titles)


def test_dropping_files_adds_them(window, samples):
    """The drop target hands over a Gdk.FileList; go through the same call."""
    paths = [samples / "sample.png", samples / "sample.txt"]
    value = Gdk.FileList.new_from_array([Gio.File.new_for_path(str(p)) for p in paths])
    assert window._on_drop(None, value, 0, 0) is True
    _pump()
    assert sorted(e.path.name for e in window.entries) == ["sample.png", "sample.txt"]


def test_backends_window_builds(gtk_app):
    w = BackendsWindow(application=gtk_app)
    assert w.get_title() == "Backends"
    w.destroy()
