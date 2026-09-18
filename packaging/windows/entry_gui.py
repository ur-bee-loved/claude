"""PyInstaller entry point for the windowed Omniconv.exe."""

import os
import sys

os.environ.setdefault("OMNICONV_TOOLKIT", "qt")

from omniconv.gui.launcher import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
