"""The Qt front end, driven headlessly on the offscreen platform."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtWidgets  # noqa: E402

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
