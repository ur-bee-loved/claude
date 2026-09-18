"""Integration tests. Each case is skipped when its backend is missing, so
the suite passes on a bare system and grows with the installed tools."""

from __future__ import annotations

import pytest

from omniconv.core import sniff
from omniconv.core.engine import ENGINE
from tests.conftest import backend, has_module, has_tool

CASES = [
    # (source file, target, backend that must exist)
    ("sample.png", "jpeg", "pillow"),
    ("sample.png", "webp", "pillow"),
    ("sample.png", "ico", "pillow"),
    ("sample.png", "pdf", "pillow"),
    ("sample.jpg", "png", "pillow"),
    ("anim.gif", "webp", "pillow"),
    ("anim.gif", "apng", "pillow"),
    ("sample.png", "xpm", "imagemagick"),
    ("sample.svg", "png", "rsvg-convert"),
    ("sample.svg", "pdf", "rsvg-convert"),
    ("sample.wav", "mp3", "ffmpeg-audio"),
    ("sample.wav", "flac", "ffmpeg-audio"),
    ("sample.wav", "ogg", "ffmpeg-audio"),
    ("sample.wav", "opus", "ffmpeg-audio"),
    ("sample.mp4", "mkv", "ffmpeg-video"),
    ("sample.mp4", "gif", "ffmpeg-video"),
    ("sample.mp4", "png", "ffmpeg-frames"),
    ("sample.srt", "vtt", "ffmpeg-subtitles"),
    ("sample.pdf", "png", "pymupdf-render"),
    ("sample.pdf", "txt", "pymupdf-extract"),
    ("sample.pdf", "svg", "pymupdf-extract"),
    ("sample.md", "html", "text-to-html"),
    ("sample.md", "pdf", "html-to-pdf"),
    ("sample.txt", "pdf", "html-to-pdf"),
    ("sample.md", "docx", "pandoc"),
    ("sample.md", "epub", "pandoc"),
    ("sample.md", "rst", "pandoc"),
    ("sample.csv", "json", "python-data"),
    ("sample.csv", "yaml", "python-data"),
    ("sample.json", "toml", "python-data"),
    ("sample.json", "xml", "python-data"),
    ("sample.csv", "xlsx", "openpyxl"),
    ("sample.tar.gz", "zip", "archive-repack"),
    ("sample.tar.gz", "tar.xz", "archive-repack"),
]


@pytest.mark.parametrize("source,target,needs", CASES, ids=[f"{s}->{t}" for s, t, _ in CASES])
def test_single_conversion(samples, tmp_path, source, target, needs):
    src = samples / source
    if not src.exists():
        pytest.skip(f"fixture {source} could not be generated on this system")
    if not backend(needs):
        pytest.skip(f"backend {needs} not available")
    res = ENGINE.convert(src, target, output_dir=tmp_path)
    assert res.ok, res.error
    assert res.outputs and all(p.exists() and p.stat().st_size > 0 for p in res.outputs)
    detected = sniff.detect(res.outputs[0])
    assert detected is not None and detected.name == target, f"output detected as {detected}"


def test_multi_hop_route_docx_to_png_or_skip(samples, tmp_path):
    if not (backend("pandoc") and (backend("libreoffice") or backend("pymupdf-render"))):
        pytest.skip("needs pandoc plus a PDF renderer")
    docx = ENGINE.convert(samples / "sample.md", "docx", output_dir=tmp_path)
    assert docx.ok, docx.error
    res = ENGINE.convert(docx.outputs[0], "png", output_dir=tmp_path)
    assert res.ok, res.error
    assert len(res.route) >= 1


def test_pdf_page_selection_and_rewrite(samples, tmp_path):
    if not backend("pymupdf-render"):
        pytest.skip("PyMuPDF missing")
    res = ENGINE.convert(samples / "sample.pdf", "png", output_dir=tmp_path)
    assert res.ok and len(res.outputs) == 2
    res = ENGINE.convert(samples / "sample.pdf", "png", output_dir=tmp_path, options={"pages": "2"})
    assert res.ok and len(res.outputs) == 1
    res = ENGINE.convert(samples / "sample.pdf", "pdf", output_dir=tmp_path, options={"pages": "1", "rotate": 90})
    assert res.ok, res.error
    from omniconv.converters._common import load_pymupdf

    doc = load_pymupdf().open(str(res.outputs[0]))
    assert doc.page_count == 1 and doc[0].rotation == 90


def test_image_options_resize_and_grayscale(samples, tmp_path):
    if not backend("pillow"):
        pytest.skip("Pillow missing")
    res = ENGINE.convert(samples / "sample.png", "jpeg", output_dir=tmp_path, options={"width": 60, "grayscale": True, "quality": 50})
    assert res.ok, res.error
    from PIL import Image

    with Image.open(res.outputs[0]) as im:
        assert im.size == (60, 40) and im.mode == "L"


def test_merge_images_into_pdf(samples, tmp_path):
    if not (backend("pymupdf-merge") or backend("img2pdf-merge") or backend("pillow-multipage")):
        pytest.skip("no PDF merger")
    res = ENGINE.merge([samples / "sample.png", samples / "sample.jpg"], tmp_path / "out.pdf")
    assert res.ok, res.error
    assert sniff.detect(res.outputs[0]).name == "pdf"


def test_conflict_policy(samples, tmp_path):
    if not backend("python-data"):
        pytest.skip()
    first = ENGINE.convert(samples / "sample.csv", "json", output_dir=tmp_path)
    second = ENGINE.convert(samples / "sample.csv", "json", output_dir=tmp_path)
    assert first.outputs[0].name == "sample.json" and second.outputs[0].name == "sample (1).json"
    third = ENGINE.convert(samples / "sample.csv", "json", output_dir=tmp_path, on_conflict="error")
    assert not third.ok and "exists" in third.error
    fourth = ENGINE.convert(samples / "sample.csv", "json", output_dir=tmp_path, on_conflict="overwrite")
    assert fourth.ok and fourth.outputs[0].name == "sample.json"


def test_data_roundtrip(samples, tmp_path):
    import json

    res = ENGINE.convert(samples / "sample.json", "yaml", output_dir=tmp_path)
    assert res.ok
    back = ENGINE.convert(res.outputs[0], "json", output_dir=tmp_path / "back")
    assert back.ok
    assert json.loads(back.outputs[0].read_text()) == json.loads((samples / "sample.json").read_text())


def test_cli_smoke(samples, tmp_path, capsys):
    from omniconv.cli import main

    assert main(["route", "png", "jpeg"]) in (0, 1)
    assert main(["doctor"]) == 0
    assert main(["formats", "--from", "csv"]) == 0
    out = capsys.readouterr().out
    assert "json" in out
    if backend("python-data"):
        assert main(["convert", str(samples / "sample.csv"), "-t", "json", "-o", str(tmp_path)]) == 0
        assert (tmp_path / "sample.json").exists()
        assert main([str(samples / "sample.csv"), str(tmp_path / "shortcut.yaml")]) == 0
        assert (tmp_path / "shortcut.yaml").exists()
