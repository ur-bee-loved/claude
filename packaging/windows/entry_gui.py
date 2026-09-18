"""PyInstaller entry point for the windowed Omniconv.exe.

A windowed executable has no console, so Python's standard streams are
``None`` and anything written to them, including tracebacks raised inside
the Qt event loop, is lost. They are redirected to a log file in the user
data directory so a failure always leaves something to read.
"""

import os
import sys

os.environ.setdefault("OMNICONV_TOOLKIT", "qt")


def _redirect_streams() -> None:
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        from omniconv.core.platform import user_data_dir

        log_dir = user_data_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        stream = open(log_dir / "omniconv-gui.log", "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = stream
        if sys.stderr is None:
            sys.stderr = stream
    except Exception:
        pass


_redirect_streams()

from omniconv.gui.launcher import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
