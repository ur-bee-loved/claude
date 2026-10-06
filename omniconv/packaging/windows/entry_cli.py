"""PyInstaller entry point for the console omniconv.exe."""

import sys

from omniconv.cli import main

if __name__ == "__main__":
    sys.exit(main())
