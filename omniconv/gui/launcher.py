"""Pick a GUI toolkit for the current platform.

GTK 4 with libadwaita is the native choice on Linux desktops; Qt 6 is the
native choice on Windows and macOS. ``OMNICONV_TOOLKIT=gtk`` or ``=qt``
overrides the choice, which is handy for testing both on one machine.
"""

from __future__ import annotations

import os
import sys

from omniconv.core import platform


def available_toolkits() -> list[str]:
    out = []
    try:
        import gi  # noqa: F401

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        out.append("gtk")
    except Exception:
        pass
    try:
        import PySide6  # noqa: F401

        out.append("qt")
    except Exception:
        pass
    return out


def choose_toolkit() -> str | None:
    forced = os.environ.get("OMNICONV_TOOLKIT", "").lower()
    have = available_toolkits()
    if forced in ("gtk", "qt"):
        return forced if forced in have else None
    order = ("qt", "gtk") if (platform.IS_WINDOWS or platform.IS_MAC) else ("gtk", "qt")
    for tk in order:
        if tk in have:
            return tk
    return None


def install_hint() -> str:
    if platform.IS_WINDOWS or platform.IS_MAC:
        return "pip install PySide6"
    return "sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1   (or: pip install PySide6)"


def _report(message: str) -> None:
    """Print to stderr and, on Windows, also show a native message box: the
    windowed launcher has no console, so stderr alone would be invisible."""
    print(message, file=sys.stderr)
    if platform.IS_WINDOWS:
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, "Omniconv", 0x10)  # MB_ICONERROR
        except Exception:
            pass


def run(files: list[str] | None = None) -> int:
    tk = choose_toolkit()
    if tk == "gtk":
        from omniconv.gui.app import run_app
    elif tk == "qt":
        from omniconv.gui.qt_app import run_app
    else:
        _report("No GUI toolkit found. Install one with:\n\n  " + install_hint())
        return 1
    return run_app(files)


def main() -> int:
    """Entry point for the ``omniconv-gui`` launcher (a windowed executable
    on Windows, so there is no console to print to on failure)."""
    try:
        return run(sys.argv[1:])
    except Exception:
        import traceback

        _report("Omniconv could not start:\n\n" + traceback.format_exc())
        return 1
