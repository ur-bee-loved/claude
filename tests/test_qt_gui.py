"""The Qt front end, driven headlessly on the offscreen platform."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from omniconv.gui.qt_app import MainWindow, create_app  # noqa: E402
from tests.conftest import backend  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return create_app(["pytest"])


@pytest.fixture
def window(app):
    w = MainWindow()
    w.show()
    yield w
    w.close()


def _wait_for_worker(window: MainWindow, timeout_ms: int = 60000) -> None:
    deadline = QtCore.QDeadlineTimer(timeout_ms)
    while window.worker is not None and window.worker.isRunning() and not deadline.hasExpired():
        QtWidgets.QApplication.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 50)
    QtWidgets.QApplication.processEvents()


def test_empty_window_state(window):
    assert not window.convert_button.isEnabled()
    assert window.target_names == []
    assert "Add files" in window.target_hint.text()


def test_targets_follow_inputs(window, samples):
    if not backend("pillow"):
        pytest.skip("Pillow missing")
    window.add_paths([str(samples / "sample.png"), str(samples / "sample.jpg")])
    # Targets are formats every input can reach. A format reaches itself only
    # when a same-format optimiser is installed, so assert on formats that
    # differ from both inputs.
    assert "webp" in window.target_names and "bmp" in window.target_names and "pdf" in window.target_names
    assert window.selected_target() is not None
    assert window.convert_button.isEnabled()
    assert window.merge_check.isVisible()


def test_option_widgets_report_only_changes(window, samples):
    if not backend("pillow"):
        pytest.skip("Pillow missing")
    window.add_paths([str(samples / "sample.png")])
    window.target_combo.setCurrentIndex(window.target_names.index("jpeg"))
    assert window.collect_options() == {}
    spec, widget = window.option_widgets["width"]
    widget.setValue(64)
    spec, grey = window.option_widgets["grayscale"]
    grey.setChecked(True)
    assert window.collect_options() == {"width": 64, "grayscale": True}


def test_batch_conversion_updates_rows(window, samples, tmp_path):
    if not backend("pillow"):
        pytest.skip("Pillow missing")
    window.add_paths([str(samples / "sample.png"), str(samples / "sample.jpg")])
    window.target_combo.setCurrentIndex(window.target_names.index("webp"))
    window._set_output_dir(tmp_path)
    window.start_conversion()
    _wait_for_worker(window)
    entries = window.file_list.entries()
    assert [e.status for e in entries] == ["done", "done"], [e.message for e in entries]
    assert (tmp_path / "sample.webp").exists() and (tmp_path / "sample (1).webp").exists()
    assert window.open_folder_button.isVisible()
    assert "2 converted" in window.summary_label.text()


def _drop(widget, paths):
    """Post a real drop onto the file table, the way the shell does."""
    mime = QtCore.QMimeData()
    mime.setUrls([QtCore.QUrl.fromLocalFile(str(p)) for p in paths])
    centre = widget.viewport().rect().center()
    for cls, kind in (
        (QtGui.QDragEnterEvent, "enter"),
        (QtGui.QDragMoveEvent, "move"),
        (QtGui.QDropEvent, "drop"),
    ):
        # Only QDropEvent takes a QPointF; the drag events take a QPoint.
        pos = QtCore.QPointF(centre) if kind == "drop" else centre
        event = cls(pos, QtCore.Qt.DropAction.CopyAction, mime, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
        # A scroll area receives drags on its viewport, not on itself.
        QtWidgets.QApplication.sendEvent(widget.viewport(), event)
        assert event.isAccepted(), kind
    QtWidgets.QApplication.processEvents()


def test_dropping_files_adds_them(window, samples):
    _drop(window.file_list, [samples / "sample.png", samples / "sample.txt"])
    names = sorted(e.path.name for e in window.file_list.entries())
    assert names == ["sample.png", "sample.txt"]
    assert not window.empty_hint.isVisible()


def test_dropping_ignores_non_file_payloads(window):
    mime = QtCore.QMimeData()
    mime.setText("not a file")
    event = QtGui.QDropEvent(
        QtCore.QPointF(window.file_list.viewport().rect().center()),
        QtCore.Qt.DropAction.CopyAction, mime, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier,
    )
    QtWidgets.QApplication.sendEvent(window.file_list.viewport(), event)
    assert window.file_list.entries() == []


def test_empty_hint_is_on_top_of_the_table(window):
    # StackAll draws every page; only the current one is raised, so the
    # hint is invisible unless it is the current widget.
    assert window.stack.currentWidget() is window.empty_hint
    assert window.empty_hint.isVisible()


def test_sidebar_fits_the_window_at_its_minimum_size(window, samples):
    """A sidebar wider than its pane clips the target picker and the
    output buttons, which is only visible in a rendered window."""
    if not backend("pillow"):
        pytest.skip("Pillow missing")
    window.add_paths([str(samples / "sample.png"), str(samples / "sample.txt")])
    QtWidgets.QApplication.processEvents()
    # The options panel changes what the sidebar needs, so take the minimum
    # after they exist.
    window.resize(window.minimumSize())
    QtWidgets.QApplication.processEvents()
    scroll = window.scroll
    assert scroll.widget().minimumSizeHint().width() <= scroll.viewport().width()
    assert not scroll.horizontalScrollBar().isVisible()
    assert not window.file_list.horizontalScrollBar().isVisible()


def test_window_renders_to_a_pixmap(window, samples, tmp_path):
    """Nothing here has a display, so rasterising the window is the only
    check that it actually draws."""
    window.add_paths([str(samples / "sample.png")])
    QtWidgets.QApplication.processEvents()
    pixmap = window.grab()
    assert pixmap.width() == window.width() and pixmap.height() == window.height()
    out = tmp_path / "window.png"
    assert pixmap.save(str(out), "PNG") and out.stat().st_size > 1000


@pytest.mark.parametrize("point_size", [9, 14, 20])
def test_sidebar_fits_at_any_font_size(app, samples, point_size):
    """Segoe UI needs about a third more room than the Linux default, which
    is how a fixed window minimum came to clip the sidebar on Windows. The
    minimum is derived from the sidebar, so any font has to fit."""
    if not backend("pillow"):
        pytest.skip("Pillow missing")
    original = app.font()
    try:
        app.setFont(QtGui.QFont(original.family(), point_size))
        w = MainWindow()
        w.show()
        w.add_paths([str(samples / "sample.png"), str(samples / "sample.txt")])
        QtWidgets.QApplication.processEvents()
        w.resize(w.minimumSize())
        QtWidgets.QApplication.processEvents()
        assert w.scroll.widget().minimumSizeHint().width() <= w.scroll.viewport().width()
        assert not w.scroll.horizontalScrollBar().isVisible()
        w.close()
    finally:
        app.setFont(original)
