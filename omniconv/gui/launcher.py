"""Pick a GUI toolkit for the current platform.

GTK 4 with libadwaita is the native choice on Linux desktops; Qt 6 is the
native choice on Windows and macOS. ``OMNICONV_TOOLKIT=gtk`` or ``=qt``
overrides the choice, which is handy for testing both on one machine.
"""

from __future__ import annotations

import os
import sys

from omniconv.core import platform


# Why each toolkit could not be imported, for the error report.
IMPORT_ERRORS: dict[str, str] = {}


def available_toolkits() -> list[str]:
    out = []
    try:
        import gi  # noqa: F401

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        out.append("gtk")
    except Exception as exc:
        IMPORT_ERRORS["gtk"] = f"{type(exc).__name__}: {exc}"
    try:
        import PySide6  # noqa: F401
        from PySide6 import QtWidgets  # noqa: F401

        out.append("qt")
    except Exception as exc:
        IMPORT_ERRORS["qt"] = f"{type(exc).__name__}: {exc}"
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


def error_log_path():
    return platform.user_data_dir() / "launcher-error.log"


def _report(message: str) -> None:
    """Print to stderr, write a log file, and on Windows show a native
    message box: the windowed launcher has no console, so stderr alone
    would be invisible."""
    if sys.stderr is not None:
        print(message, file=sys.stderr)
    try:
        import datetime

        path = error_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"--- {datetime.datetime.now().isoformat(timespec='seconds')} "
                     f"frozen={getattr(sys, 'frozen', False)} executable={sys.executable}\n{message}\n")
    except Exception:
        pass
    # OMNICONV_NO_MSGBOX lets automated runs fail fast instead of blocking
    # on a dialog nobody can dismiss.
    if platform.IS_WINDOWS and not os.environ.get("OMNICONV_NO_MSGBOX"):
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, "Omniconv", 0x10)  # MB_ICONERROR
        except Exception:
            pass


def self_test_path():
    return platform.user_data_dir() / "self-test.log"


def self_test() -> int:
    """Build the window without entering the event loop, and report what
    happened to a log file.

    A windowed executable has no console and, under Qt's offscreen
    platform, its event loop may return as soon as it starts, so "is the
    process still alive" says nothing about whether the build works. This
    does: it imports the toolkit, constructs the main window, loads the
    backends and prints what it found.
    """
    lines: list[str] = []
    status = 0
    try:
        import omniconv
        from omniconv.core.registry import REGISTRY

        tk = choose_toolkit()
        lines.append(f"omniconv {omniconv.__version__} on {sys.platform}, frozen={getattr(sys, 'frozen', False)}")
        lines.append(f"toolkit: {tk or 'none'} (available: {', '.join(available_toolkits()) or 'none'})")
        if tk is None:
            raise RuntimeError("no GUI toolkit available: " + "; ".join(f"{k}: {v}" for k, v in IMPORT_ERRORS.items()))
        if tk == "qt":
            from omniconv.gui.qt_app import MainWindow, create_app

            app = create_app([sys.argv[0]])
            window = MainWindow()
            window.show()
            app.processEvents()
            lines.append(f"window: {window.windowTitle()!r}, {len(REGISTRY.available())}/{len(REGISTRY.all())} backends")
            window.close()
        else:
            import gi

            gi.require_version("Gtk", "4.0")
            from gi.repository import Gtk  # noqa: F401

            from omniconv.gui.window import MainWindow  # noqa: F401

            from omniconv.converters import load_all

            load_all()
            lines.append(f"window class imported, {len(REGISTRY.available())}/{len(REGISTRY.all())} backends")
        lines.append("self-test ok")
    except Exception:
        import traceback

        lines.append("self-test FAILED")
        lines.append(traceback.format_exc())
        status = 1
    report = "\n".join(lines)
    try:
        path = self_test_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report + "\n", encoding="utf-8")
    except Exception:
        pass
    if sys.stdout is not None:
        print(report)
    return status


def run(files: list[str] | None = None) -> int:
    tk = choose_toolkit()
    if tk == "gtk":
        from omniconv.gui.app import run_app
    elif tk == "qt":
        from omniconv.gui.qt_app import run_app
    else:
        details = "\n".join(f"  {name}: {err}" for name, err in IMPORT_ERRORS.items())
        _report("No GUI toolkit found. Install one with:\n\n  " + install_hint() + ("\n\nImport errors:\n" + details if details else ""))
        return 1
    return run_app(files)


def main() -> int:
    """Entry point for the ``omniconv-gui`` launcher (a windowed executable
    on Windows, so there is no console to print to on failure)."""
    args = sys.argv[1:]
    if "--self-test" in args:
        return self_test()
    try:
        return run(args)
    except Exception:
        import traceback

        _report("Omniconv could not start:\n\n" + traceback.format_exc())
        return 1
