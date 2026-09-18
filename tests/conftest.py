"""Shared fixtures. Sample files are generated on the fly so the repository
carries no binary blobs; tests needing a backend skip when it is absent."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from omniconv.converters import load_all
from omniconv.core.registry import REGISTRY

load_all()


def has_tool(name: str) -> bool:
    return shutil.which(name) is not None


def has_module(name: str) -> bool:
    from omniconv.core.requirements import Module

    return Module(name).available()


def backend(name: str) -> bool:
    return any(c.name == name and c.available() for c in REGISTRY.all())


@pytest.fixture(scope="session")
def samples(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("samples")
    (d / "sample.txt").write_text("Hello world.\n\nA second paragraph of plain text.\n")
    (d / "sample.md").write_text("# Title\n\nSome *emphasis* and a list:\n\n- one\n- two\n")
    (d / "sample.csv").write_text("name,age,city\nAda,36,London\nLinus,54,Portland\n")
    (d / "sample.json").write_text('{"project": "omniconv", "version": 1, "tags": ["a", "b"], "nested": {"x": 1.5}}')
    (d / "sample.srt").write_text("1\n00:00:00,000 --> 00:00:02,000\nHello\n\n2\n00:00:02,500 --> 00:00:04,000\nWorld\n")
    (d / "sample.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="120"><rect width="200" height="120" fill="#eef"/>'
        '<circle cx="60" cy="60" r="40" fill="crimson"/></svg>'
    )
    if has_module("PIL"):
        from PIL import Image, ImageDraw

        im = Image.new("RGBA", (120, 80), (255, 255, 255, 0))
        ImageDraw.Draw(im).ellipse((10, 10, 70, 70), fill=(200, 30, 30, 255))
        im.save(d / "sample.png")
        im.convert("RGB").save(d / "sample.jpg", quality=90)
        frames = [im.rotate(a).convert("RGB") for a in (0, 90, 180)]
        frames[0].save(d / "anim.gif", save_all=True, append_images=frames[1:], duration=100, loop=0)
    if has_module("pymupdf") or has_module("fitz"):
        from omniconv.converters._common import load_pymupdf

        fitz = load_pymupdf()
        doc = fitz.open()
        for i in range(2):
            page = doc.new_page()
            page.insert_text((72, 72), f"Page {i + 1} of the sample", fontsize=18)
        doc.save(str(d / "sample.pdf"))
        doc.close()
    if has_tool("ffmpeg"):
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-ac", "1", str(d / "sample.wav")], check=True)
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=64x48:rate=10:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(d / "sample.mp4")],
            check=True,
        )
    (d / "graph.dot").write_text("digraph G { a -> b; b -> c; }\n")
    (d / "cube.obj").write_text("v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf 1 2 3 4\n")
    (d / "sample.1").write_text(".TH SAMPLE 1\n.SH NAME\nsample \\- a manual page\n.SH DESCRIPTION\nText.\n")
    import struct

    def vlq(n: int) -> bytes:
        out = [n & 0x7F]
        n >>= 7
        while n:
            out.append(0x80 | (n & 0x7F))
            n >>= 7
        return bytes(reversed(out))

    events = b"".join(vlq(0) + bytes([0x90, note, 100]) + vlq(240) + bytes([0x80, note, 0]) for note in (60, 64, 67))
    track = events + vlq(0) + b"\xff\x2f\x00"
    (d / "tune.mid").write_bytes(b"MThd" + struct.pack(">IHHH", 6, 0, 1, 120) + b"MTrk" + struct.pack(">I", len(track)) + track)
    import tarfile

    with tarfile.open(d / "sample.tar.gz", "w:gz") as tf:
        tf.add(d / "sample.txt", arcname="sample.txt")
    return d
