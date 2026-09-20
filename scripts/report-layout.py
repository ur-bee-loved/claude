#!/usr/bin/env python3
"""Print the measurements the window's layout depends on.

The layout assertions say only pass or fail. These are the numbers behind
them: which font the platform actually resolved, and how wide the sidebar
needs to be in it. Run on the native platform, this is what the window is
really measured against.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    from PySide6 import QtGui, QtWidgets

    from omniconv.gui.qt_app import MainWindow, create_app

    app = create_app([sys.argv[0]])
    font = QtGui.QGuiApplication.font()
    families = QtGui.QFontDatabase.families()
    print(f"platform: {QtGui.QGuiApplication.platformName()}")
    print(f"font: requested {font.family()!r}, resolved {QtGui.QFontInfo(font).family()!r}, {len(families)} families")
    if not families:
        print("no fonts: every measurement below is against a font with no glyphs")

    window = MainWindow()
    window.show()
    app.processEvents()
    print(f"minimum with no files: {window.minimumSize().width()}x{window.minimumSize().height()}")

    import tempfile

    tmp = Path(tempfile.mkdtemp())
    (tmp / "note.txt").write_text("Layout measurement sample.\n", encoding="utf-8")
    window.add_paths([str(tmp / "note.txt")])
    app.processEvents()
    side = window.scroll.widget().minimumSizeHint().width()
    print(f"sidebar needs: {side} px")
    print(f"minimum with options: {window.minimumSize().width()}x{window.minimumSize().height()}")
    window.resize(window.minimumSize())
    app.processEvents()
    print(f"sidebar gets: {window.scroll.viewport().width()} px")
    print(f"fits: {side <= window.scroll.viewport().width()}")
    metrics = QtGui.QFontMetrics(font)
    print(f"'Convert to' is {metrics.horizontalAdvance('Convert to')} px wide")
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
