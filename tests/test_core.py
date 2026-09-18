"""Backend-independent behaviour: format table, sniffing, options, routing."""

from __future__ import annotations

from pathlib import Path

import pytest

from omniconv.core import formats, options, sniff
from omniconv.core.engine import ENGINE, Engine, unique_path
from omniconv.core.errors import NoRouteError, UnknownFormatError
from omniconv.core.registry import HOP_PENALTY, REGISTRY, Converter, Registry, Step
from omniconv.core.requirements import Tool


def test_format_table_is_consistent():
    names = [f.name for f in formats.all_formats()]
    assert len(names) == len(set(names))
    for f in formats.all_formats():
        assert f.category in formats.CATEGORIES
        assert f.extensions and f.mime and f.description


def test_lookup_by_name_and_extension():
    assert formats.get("jpg").name == "jpeg"
    assert formats.get(".PNG").name == "png"
    assert formats.by_extension("archive.tar.gz").name == "tar.gz"
    assert formats.by_extension("x.TAR.XZ").name == "tar.xz"
    assert formats.by_extension("noext") is None
    with pytest.raises(UnknownFormatError):
        formats.get("definitely-not-a-format")


def test_output_path_strips_compound_extension():
    assert formats.output_path(Path("/x/a.tar.gz"), formats.get("zip")) == Path("/x/a.zip")
    assert formats.output_path(Path("/x/photo.JPEG"), formats.get("webp"), Path("/out")) == Path("/out/photo.webp")


def test_parse_pages():
    assert options.parse_pages("1-3,7,2", 10) == [0, 1, 2, 6]
    assert options.parse_pages(None, 3) == [0, 1, 2]
    assert options.parse_pages("-2,9-", 10) == [0, 1, 8, 9]
    assert options.parse_pages("99", 3) == []


def test_coerce_options():
    out = options.coerce_options({"quality": "80", "grayscale": "yes", "custom": 1, "width": ""})
    assert out == {"quality": 80, "grayscale": True, "custom": 1}


def test_sniff_prefers_content_over_wrong_extension(tmp_path):
    png = tmp_path / "wrong.jpg"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 64)
    assert sniff.detect(png).name == "png"
    apng = tmp_path / "a.png"
    apng.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 8 + b"acTL" + b"\0" * 64)
    assert sniff.detect(apng).name == "apng"
    eps = tmp_path / "f.eps"
    eps.write_bytes(b"%!PS-Adobe-3.0 EPSF-3.0\n")
    assert sniff.detect(eps).name == "eps"
    ps = tmp_path / "f.ps"
    ps.write_bytes(b"%!PS-Adobe-3.0\n")
    assert sniff.detect(ps).name == "ps"


def test_sniff_zip_containers(tmp_path):
    import zipfile

    docx = tmp_path / "doc.bin"
    with zipfile.ZipFile(docx, "w") as zf:
        zf.writestr("word/document.xml", "<w/>")
    assert sniff.detect(docx).name == "docx"
    odt = tmp_path / "x.zip"
    with zipfile.ZipFile(odt, "w") as zf:
        zf.writestr("mimetype", "application/vnd.oasis.opendocument.text")
    assert sniff.detect(odt).name == "odt"


def test_sniff_text_signature_is_weak_for_markup(tmp_path):
    md = tmp_path / "page.md"
    md.write_text("<span>starts with a tag</span> but is markdown\n")
    assert sniff.detect(md).name == "md"
    html = tmp_path / "page.txt"
    html.write_text("<!DOCTYPE html><html></html>")
    assert sniff.detect(html).name == "txt"


def _fake(name, sources, targets, cost=10, ok=True):
    return Converter(name=name, sources=frozenset(sources), targets=frozenset(targets), func=lambda job: None, cost=cost, requires=() if ok else (Tool("no-such-tool-xyz"),))


def test_routing_prefers_direct_then_cheapest_chain():
    reg = Registry()
    reg.register(_fake("a2b", {"png"}, {"jpeg"}, cost=10))
    reg.register(_fake("b2c", {"jpeg"}, {"webp"}, cost=10))
    reg.register(_fake("a2c-expensive", {"png"}, {"webp"}, cost=100))
    route = reg.find_route("png", "webp")
    assert [s.name for s in route] == ["a2c-expensive"] if 100 + HOP_PENALTY < 2 * (10 + HOP_PENALTY) else ["a2b", "b2c"]
    assert route[0].src == "png" and route[-1].tgt == "webp"


def test_routing_ignores_unavailable_converters():
    reg = Registry()
    reg.register(_fake("broken", {"png"}, {"jpeg"}, ok=False))
    assert reg.find_route("png", "jpeg") is None
    assert reg.candidates_needing_install("png", "jpeg")[0].name == "broken"


def test_routing_respects_hop_limit_and_category_hubs():
    reg = Registry()
    reg.register(_fake("s1", {"png"}, {"mp3"}))
    reg.register(_fake("s2", {"mp3"}, {"docx"}))
    reg.register(_fake("s3", {"docx"}, {"webp"}))
    # mp3 is neither an image, a document nor a webp-category hub, so the
    # chain through it is not allowed.
    assert reg.find_route("png", "webp") is None


def test_same_format_requires_flag():
    reg = Registry()
    reg.register(_fake("copy", {"pdf"}, {"pdf"}))
    assert reg.find_route("pdf", "pdf") is None
    reg2 = Registry()
    c = Converter(name="rewrite", sources=frozenset({"pdf"}), targets=frozenset({"pdf"}), func=lambda j: None, same_format=True)
    reg2.register(c)
    assert [s.name for s in reg2.find_route("pdf", "pdf")] == ["rewrite"]


def test_unique_path(tmp_path):
    p = tmp_path / "a.txt"
    assert unique_path(p) == p
    p.write_text("x")
    assert unique_path(p) == tmp_path / "a (1).txt"


def test_engine_reports_missing_file(tmp_path):
    res = ENGINE.convert(tmp_path / "missing.png", "jpeg")
    assert not res.ok and "not a file" in res.error


def test_engine_reports_no_route(tmp_path):
    src = tmp_path / "x.wav"
    src.write_bytes(b"RIFF\0\0\0\0WAVEfmt " + b"\0" * 32)
    res = ENGINE.convert(src, "xcf")
    assert not res.ok and "no available converter" in res.error


def test_registry_loaded_backends():
    names = {c.name for c in REGISTRY.all()}
    assert {"pillow", "imagemagick", "ffmpeg-audio", "ffmpeg-video", "pymupdf-render", "libreoffice", "pandoc", "python-data", "archive-repack"} <= names
