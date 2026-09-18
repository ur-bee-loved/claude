"""Content-based format detection.

Extensions lie often enough (a ``.jpg`` that is really a PNG, a ``.doc`` that
is really RTF) that the engine looks at the first bytes of a file before
trusting the name. The sniffer only needs to be good enough to override an
obviously wrong extension; the extension remains the tiebreaker for
container formats it cannot disambiguate.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from omniconv.core import formats
from omniconv.core.formats import Format

_MAGIC: list[tuple[int, bytes, str]] = [
    (0, b"\x89PNG\r\n\x1a\n", "png"),
    (0, b"\xff\xd8\xff", "jpeg"),
    (0, b"GIF87a", "gif"),
    (0, b"GIF89a", "gif"),
    (0, b"BM", "bmp"),
    (0, b"II*\x00", "tiff"),
    (0, b"MM\x00*", "tiff"),
    (0, b"%PDF", "pdf"),
    (0, b"%!PS", "ps"),
    (0, b"\xc5\xd0\xd3\xc6", "eps"),
    (0, b"fLaC", "flac"),
    (0, b"ID3", "mp3"),
    (0, b"\xff\xfb", "mp3"),
    (0, b"\xff\xf3", "mp3"),
    (0, b"\xff\xf2", "mp3"),
    (0, b"\x1aE\xdf\xa3", "mkv"),
    (0, b"FLV\x01", "flv"),
    (0, b"0&\xb2u\x8ef\xcf\x11", "wmv"),
    (0, b"\x00\x00\x01\xba", "mpeg"),
    (0, b"\x00\x00\x01\xb3", "mpeg"),
    (0, b"MAC ", "ape"),
    (0, b"wvpk", "wv"),
    (0, b"TTA1", "tta"),
    (0, b".snd", "au"),
    (0, b"caff", "caf"),
    (0, b"Creative Voice File", "voc"),
    (0, b"7z\xbc\xaf\x27\x1c", "7z"),
    (0, b"Rar!\x1a\x07", "rar"),
    (0, b"\x1f\x8b", "gz"),
    (0, b"BZh", "bz2"),
    (0, b"\xfd7zXZ\x00", "xz"),
    (0, b"\x28\xb5\x2f\xfd", "zst"),
    (0, b"\x04\x22\x4d\x18", "lz4"),
    (0, b"!<arch>\n", "ar"),
    (0, b"MSCF", "cab"),
    (0, b"{\\rtf", "rtf"),
    (0, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "doc"),
    (0, b"8BPS", "psd"),
    (0, b"gimp xcf", "xcf"),
    (0, b"v/1\x01", "exr"),
    (0, b"#?RADIANCE", "hdr"),
    (0, b"SDPX", "dpx"),
    (0, b"XPDS", "dpx"),
    (0, b"SIMPLE  =", "fits"),
    (0, b"qoif", "qoi"),
    (0, b"\x00\x00\x01\x00", "ico"),
    (0, b"\x00\x00\x02\x00", "cur"),
    (0, b"icns", "icns"),
    (0, b"DDS ", "dds"),
    (0, b"\x0a", "pcx"),
    (0, b"\x01\xda", "sgi"),
    (0, b"BLP1", "blp"),
    (0, b"BLP2", "blp"),
    (0, b"\x8aMNG", "mng"),
    (0, b"\x59\xa6\x6a\x95", "ras"),
    (0, b"\xff\x0a", "jxl"),
    (0, b"\x00\x00\x00\x0cJXL ", "jxl"),
    (0, b"\x00\x00\x00\x0cjP  ", "jp2"),
    (0, b"\xff\x4f\xff\x51", "jp2"),
    (0, b"\x0b\x77", "ac3"),
    (0, b"\x7f\xfe\x80\x01", "dts"),
    (0, b"#!AMR", "amr"),
    (0, b"AT&TFORM", "djvu"),
    (0, b"YUV4MPEG2", "y4m"),
    (0, b"FWS", "swf"),
    (0, b"CWS", "swf"),
    (0, b"ZWS", "swf"),
    (0, b"wOFF", "woff"),
    (0, b"wOF2", "woff2"),
    (0, b"\x00\x01\x00\x00", "ttf"),
    (0, b"true", "ttf"),
    (0, b"OTTO", "otf"),
    (0, b"%!PS-AdobeFont", "pfb"),
    (0, b"\x80\x01", "pfb"),
    (0, b"STARTFONT", "bdf"),
    (0, b"\x01fcp", "pcf"),
    (0, b"SQLite format 3\x00", "sqlite"),
    (0, b"PAR1", "parquet"),
    (0, b"bplist", "plist"),
    (0, b"\x80\x04\x95", "pickle"),
    (0, b"\xed\xab\xee\xdb", "rpm"),
    (0, b"ITSF", "chm"),
    (0, b"\x60\xea", "arj"),
    (0, b"\x1f\x9d", "z"),
    (0, b"\x1f\xa0", "z"),
    (0, b"MZ", "eot"),  # weak; only used when the extension agrees
    (0, b"FORM", "8svx"),  # IFF container; refined below
    (0, b"RIFF", "riff"),  # refined below
    (0, b"OggS", "ogg"),  # refined below
    (0, b"\x89HDF", "hdf"),
    (0, b"CDF", "cdf"),
]

# ZIP-based container formats are identified by their contents.
_ZIP_MARKERS: list[tuple[str, str]] = [
    ("word/document.xml", "docx"),
    ("ppt/presentation.xml", "pptx"),
    ("xl/workbook.xml", "xlsx"),
    ("META-INF/container.xml", "epub"),
    ("AndroidManifest.xml", "apk"),
    ("META-INF/MANIFEST.MF", "jar"),
]
_ODF_MIMES = {
    "application/vnd.oasis.opendocument.text": "odt",
    "application/vnd.oasis.opendocument.presentation": "odp",
    "application/vnd.oasis.opendocument.spreadsheet": "ods",
    "application/vnd.oasis.opendocument.graphics": "odg",
    "application/epub+zip": "epub",
}


def _sniff_zip(path: Path) -> str | None:
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            if "mimetype" in names:
                mime = zf.read("mimetype").decode("ascii", "replace").strip()
                if mime in _ODF_MIMES:
                    return _ODF_MIMES[mime]
            for marker, name in _ZIP_MARKERS:
                if marker in names:
                    return name
            if names and all(n.lower().rsplit(".", 1)[-1] in ("jpg", "jpeg", "png", "gif", "webp") or n.endswith("/") for n in names):
                return "cbz"
    except (zipfile.BadZipFile, OSError):
        return None
    return "zip"


def _sniff_riff(head: bytes) -> str | None:
    tag = head[8:12]
    return {b"WAVE": "wav", b"AVI ": "avi", b"WEBP": "webp"}.get(tag)


def _sniff_ogg(head: bytes) -> str | None:
    if b"OpusHead" in head:
        return "opus"
    if b"\x80theora" in head:
        return "ogv"
    if b"Speex   " in head:
        return "spx"
    if b"\x01vorbis" in head:
        return "ogg"
    return "ogg"


def _sniff_iso_bmff(head: bytes) -> str | None:
    if head[4:8] != b"ftyp":
        return None
    brand = head[8:12]
    if brand in (b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"):
        return "heif"
    if brand in (b"avif", b"avis"):
        return "avif"
    if brand in (b"M4A ", b"M4B ", b"M4P "):
        return "m4a"
    if brand in (b"qt  ",):
        return "mov"
    if brand in (b"3gp4", b"3gp5", b"3gp6", b"3ge6", b"3gg6", b"3g2a"):
        return "3gp"
    if brand in (b"jp2 ",):
        return "jp2"
    return "mp4"


def _sniff_text(head: bytes, ext_fmt: Format | None) -> str | None:
    """Very light heuristics for text-based formats."""
    try:
        text = head.decode("utf-8")
    except UnicodeDecodeError:
        return None
    stripped = text.lstrip("﻿ \t\r\n").lower()
    if stripped.startswith("<?xml") or stripped.startswith("<"):
        if "<svg" in stripped:
            return "svg"
        if "<!doctype html" in stripped or "<html" in stripped:
            return "html"
        if "<fictionbook" in stripped:
            return "fb2"
        if "<tt " in stripped or "<tt:" in stripped:
            return "ttml"
        if "<plist" in stripped:
            return "plist"
        if "<opml" in stripped:
            return "opml"
        if "<book" in stripped or "<article" in stripped or "docbook" in stripped:
            return "docbook"
        if ext_fmt is not None and ext_fmt.name in ("xml", "docbook", "svg", "html", "ttml", "plist", "opml", "fodt", "xhtml", "ttx", "vsd", "dxf"):
            return ext_fmt.name
        return "xml"
    if stripped.startswith("webvtt"):
        return "vtt"
    if stripped.startswith("[script info]"):
        return "ass"
    if stripped.startswith("begin:vcard"):
        return "vcf"
    if stripped.startswith("begin:vcalendar"):
        return "ics"
    if stripped.startswith("{") and '"cells"' in stripped and '"nbformat"' in stripped:
        return "ipynb"
    return None


def detect(path: Path) -> Format | None:
    """Detect the format of ``path``. The extension wins ties; the content
    wins outright conflicts (a PNG named ``.jpg`` is reported as PNG)."""
    ext_fmt = formats.by_extension(path)
    try:
        with open(path, "rb") as fh:
            head = fh.read(4096)
    except OSError:
        return ext_fmt
    if not head:
        return ext_fmt

    name: str | None = None
    if head[:4] == b"%!PS":
        name = "eps" if b"EPSF" in head[:64] else "ps"
    elif head[:8] == b"\x89PNG\r\n\x1a\n":
        name = "apng" if b"acTL" in head else "png"
    elif head[:4] == b"RIFF":
        name = _sniff_riff(head)
    elif head[:4] == b"OggS":
        name = _sniff_ogg(head)
    elif head[4:8] == b"ftyp":
        name = _sniff_iso_bmff(head)
    elif head[:4] == b"PK\x03\x04":
        name = _sniff_zip(path)
    elif head[257:262] == b"ustar":
        name = "tar"
    else:
        for offset, magic, fmt_name in _MAGIC:
            if head[offset : offset + len(magic)] == magic:
                name = fmt_name
                break
        if name is None:
            name = _sniff_text(head, ext_fmt)

    if name is None or name not in formats.FORMATS:
        return ext_fmt

    # Generic text signatures ("<" means XML, HTML) are weak: a Markdown or
    # wiki file may begin with a tag. Prefer the extension for text-based
    # formats unless the content signature is specific.
    if name in ("xml", "html") and ext_fmt is not None and ext_fmt.category in ("document", "data", "subtitle", "font", "vector"):
        return ext_fmt

    # Weak signatures must agree with the extension to be trusted.
    weak = {"eot", "ico", "cur", "pcx", "sgi", "ttf", "pfb", "8svx", "mp3", "bmp", "ac3", "z"}
    if name in weak and ext_fmt is not None and ext_fmt.name != name:
        return ext_fmt
    if name in weak and ext_fmt is None and name in ("pcx", "sgi", "ac3", "z"):
        return None

    detected = formats.FORMATS[name]
    # Extension refines a family the content cannot distinguish.
    if ext_fmt is not None:
        same_family = {
            ("mp4", "m4a"), ("mp4", "m4b"), ("mp4", "alac"), ("mp4", "f4v"), ("mp4", "mov"),
            ("mkv", "mka"), ("mkv", "webm"), ("mkv", "weba"),
            ("gz", "tar.gz"), ("bz2", "tar.bz2"), ("xz", "tar.xz"), ("zst", "tar.zst"),
            ("zip", "jar"), ("zip", "cbz"), ("zip", "htmlz"), ("zip", "txtz"), ("zip", "pmlz"), ("zip", "kepub"), ("zip", "xps"),
            ("epub", "kepub"), ("ogg", "spx"), ("ogg", "oga"),
            ("doc", "xls"), ("doc", "ppt"), ("doc", "wps"), ("doc", "vsd"), ("doc", "pub"),
            ("mpeg", "vob"), ("ts", "mpeg"), ("wmv", "wma"), ("pdf", "ai"),
            ("ttf", "dfont"), ("xml", "ttx"), ("jpeg", "mpo"), ("tiff", "dng"), ("tiff", "cr2"), ("tiff", "nef"), ("tiff", "arw"), ("tiff", "orf"), ("tiff", "rw2"),
            ("txt", "md"), ("txt", "rst"), ("txt", "org"), ("txt", "tex"),
            ("html", "xhtml"), ("mp3", "mp2"), ("wav", "w64"), ("ar", "deb"), ("psd", "psb"),
            ("gz", "svgz"), ("m4a", "alac"), ("m4a", "m4b"), ("ass", "ssa"), ("ps", "eps"), ("eps", "ps"),
            ("png", "apng"), ("xml", "mediawiki"), ("xml", "ttml"), ("xml", "opml"), ("xml", "docbook"),
            ("xml", "plist"), ("xml", "fb2"), ("xml", "svgfont"), ("xml", "dxf"), ("xml", "fodt"), ("xml", "ttx"),
            ("html", "htmlz"), ("zip", "epub"), ("txt", "asciidoc"), ("txt", "typst"), ("txt", "textile"), ("txt", "dokuwiki"),
            ("txt", "jira"), ("txt", "muse"), ("txt", "haddock"), ("txt", "t2t"), ("txt", "man"), ("txt", "mediawiki"),
        }
        if (detected.name, ext_fmt.name) in same_family:
            return ext_fmt
    return detected
