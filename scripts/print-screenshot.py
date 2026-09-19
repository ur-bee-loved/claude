#!/usr/bin/env python3
"""Print a screenshot as base64 so it can be read straight from a CI log.

The build artifacts are not reachable from every environment that reviews
these runs, but the log always is. The image is scaled down first, which
keeps the layout legible while keeping the log small.

Usage: python scripts/print-screenshot.py IMAGE [--width 640]
"""

from __future__ import annotations

import argparse
import base64
import io
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--chunk", type=int, default=200)
    args = parser.parse_args()

    from PIL import Image

    image = Image.open(args.image)
    original = image.size
    image.thumbnail((args.width, args.width * 4), Image.LANCZOS)
    buffer = io.BytesIO()
    image.convert("P", palette=Image.ADAPTIVE, colors=128).save(buffer, "PNG", optimize=True)
    data = base64.b64encode(buffer.getvalue()).decode("ascii")
    print(f"BEGIN_SCREENSHOT {args.image.name} {original[0]}x{original[1]} -> {image.width}x{image.height} {len(data)} chars")
    for i in range(0, len(data), args.chunk):
        print(data[i : i + args.chunk])
    print("END_SCREENSHOT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
