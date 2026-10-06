"""The format table.

A *format* is a named file type. Converters never talk about file extensions
directly; they refer to the canonical ``name`` of a format (``"jpeg"``,
``"tar.gz"``, ``"docx"``). The table below maps each name to the extensions
it may carry on disk, a MIME type and a category used by the front ends to
group formats.

The first extension listed for a format is the one used when writing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from omniconv.core.errors import UnknownFormatError

CATEGORIES = (
    "image",
    "vector",
    "audio",
    "video",
    "subtitle",
    "document",
    "ebook",
    "data",
    "archive",
    "font",
    "model",
)


@dataclass(frozen=True)
class Format:
    name: str
    category: str
    extensions: tuple[str, ...]
    mime: str
    description: str

    @property
    def extension(self) -> str:
        return self.extensions[0]

    def __str__(self) -> str:
        return self.name


def _f(name: str, category: str, exts: str, mime: str, description: str) -> Format:
    return Format(name, category, tuple(exts.split()), mime, description)


# fmt: off
_FORMAT_LIST: list[Format] = [
    # ---------------------------------------------------------------- image
    _f("png",   "image", "png",            "image/png",              "Portable Network Graphics"),
    _f("apng",  "image", "apng",           "image/apng",             "Animated PNG"),
    _f("jpeg",  "image", "jpg jpeg jpe jfif", "image/jpeg",          "JPEG image"),
    _f("gif",   "image", "gif",            "image/gif",              "Graphics Interchange Format"),
    _f("bmp",   "image", "bmp dib",        "image/bmp",              "Windows bitmap"),
    _f("tiff",  "image", "tif tiff",       "image/tiff",             "Tagged Image File Format"),
    _f("webp",  "image", "webp",           "image/webp",             "WebP image"),
    _f("ico",   "image", "ico",            "image/x-icon",           "Windows icon"),
    _f("icns",  "image", "icns",           "image/icns",             "macOS icon"),
    _f("heif",  "image", "heic heif",      "image/heif",             "High Efficiency Image Format"),
    _f("avif",  "image", "avif",           "image/avif",             "AV1 Image File Format"),
    _f("jp2",   "image", "jp2 j2k jpx",    "image/jp2",              "JPEG 2000"),
    _f("jxl",   "image", "jxl",            "image/jxl",              "JPEG XL"),
    _f("ppm",   "image", "ppm",            "image/x-portable-pixmap", "Portable pixmap"),
    _f("pgm",   "image", "pgm",            "image/x-portable-graymap", "Portable graymap"),
    _f("pbm",   "image", "pbm",            "image/x-portable-bitmap", "Portable bitmap"),
    _f("pnm",   "image", "pnm",            "image/x-portable-anymap", "Portable anymap"),
    _f("pam",   "image", "pam",            "image/x-portable-arbitrarymap", "Portable arbitrary map"),
    _f("tga",   "image", "tga",            "image/x-tga",            "Truevision TGA"),
    _f("pcx",   "image", "pcx",            "image/x-pcx",            "ZSoft PCX"),
    _f("dds",   "image", "dds",            "image/vnd.ms-dds",       "DirectDraw Surface"),
    _f("xbm",   "image", "xbm",            "image/x-xbitmap",        "X bitmap"),
    _f("xpm",   "image", "xpm",            "image/x-xpixmap",        "X pixmap"),
    _f("sgi",   "image", "sgi rgb bw",     "image/sgi",              "Silicon Graphics image"),
    _f("psd",   "image", "psd",            "image/vnd.adobe.photoshop", "Adobe Photoshop document"),
    _f("xcf",   "image", "xcf",            "image/x-xcf",            "GIMP image"),
    _f("exr",   "image", "exr",            "image/x-exr",            "OpenEXR"),
    _f("hdr",   "image", "hdr",            "image/vnd.radiance",     "Radiance HDR"),
    _f("dpx",   "image", "dpx",            "image/x-dpx",            "Digital Picture Exchange"),
    _f("fits",  "image", "fits fit fts",   "image/fits",             "Flexible Image Transport System"),
    _f("dcm",   "image", "dcm dicom",      "application/dicom",      "DICOM medical image"),
    _f("cur",   "image", "cur",            "image/x-win-bitmap",     "Windows cursor"),
    _f("im",    "image", "im",             "image/x-pil-im",         "PIL raw image"),
    _f("qoi",   "image", "qoi",            "image/qoi",              "Quite OK Image"),
    _f("dng",   "image", "dng",            "image/x-adobe-dng",      "Adobe Digital Negative"),
    _f("cr2",   "image", "cr2",            "image/x-canon-cr2",      "Canon RAW"),
    _f("nef",   "image", "nef",            "image/x-nikon-nef",      "Nikon RAW"),
    _f("arw",   "image", "arw",            "image/x-sony-arw",       "Sony RAW"),
    _f("raf",   "image", "raf",            "image/x-fuji-raf",       "Fujifilm RAW"),
    _f("orf",   "image", "orf",            "image/x-olympus-orf",    "Olympus RAW"),
    _f("rw2",   "image", "rw2",            "image/x-panasonic-rw2",  "Panasonic RAW"),
    _f("miff",  "image", "miff",           "image/x-miff",           "Magick Image File Format"),
    _f("mng",   "image", "mng",            "video/x-mng",            "Multiple-image Network Graphics"),
    _f("ras",   "image", "ras sun",        "image/x-cmu-raster",     "Sun raster"),
    _f("wbmp",  "image", "wbmp",           "image/vnd.wap.wbmp",     "Wireless bitmap"),
    _f("jbig2", "image", "jb2 jbig2",      "image/x-jbig2",          "JBIG2 bilevel image"),
    _f("blp",   "image", "blp",            "image/x-blp",            "Blizzard texture"),
    _f("ftex",  "image", "ftc ftu",        "image/x-ftex",           "Independence War texture"),
    _f("mpo",   "image", "mpo",            "image/mpo",              "Multi Picture Object"),
    _f("pfm",   "image", "pfm",            "image/x-portable-floatmap", "Portable float map"),
    _f("flif",  "image", "flif",           "image/flif",             "Free Lossless Image Format"),
    _f("dcx",   "image", "dcx",            "image/x-dcx",            "Intel DCX (multi-page PCX)"),
    _f("pcd",   "image", "pcd",            "image/x-photo-cd",       "Kodak Photo CD"),
    _f("fli",   "image", "fli flc",        "video/x-flic",           "Autodesk FLIC animation"),
    _f("msp",   "image", "msp",            "image/x-msp",            "Microsoft Paint (MSP)"),
    _f("palm",  "image", "palm",           "image/x-palm",           "Palm pixmap"),
    _f("gbr",   "image", "gbr",            "image/x-gimp-gbr",       "GIMP brush"),
    _f("pict",  "image", "pict pct",       "image/x-pict",           "Apple PICT"),
    _f("xwd",   "image", "xwd",            "image/x-xwindowdump",    "X Window dump"),
    _f("sixel", "image", "sixel six",      "image/x-sixel",          "Sixel terminal graphics"),
    _f("cin",   "image", "cin",            "image/cineon",           "Kodak Cineon"),
    _f("jng",   "image", "jng",            "image/x-jng",            "JPEG Network Graphics"),
    _f("viff",  "image", "viff xv",        "image/x-viff",           "Khoros VIFF"),
    _f("wpg",   "image", "wpg",            "image/x-wpg",            "WordPerfect graphics"),
    _f("cr3",   "image", "cr3",            "image/x-canon-cr3",      "Canon RAW 3"),
    _f("pef",   "image", "pef",            "image/x-pentax-pef",     "Pentax RAW"),
    _f("srw",   "image", "srw",            "image/x-samsung-srw",    "Samsung RAW"),
    _f("x3f",   "image", "x3f",            "image/x-sigma-x3f",      "Sigma RAW"),
    _f("mrw",   "image", "mrw",            "image/x-minolta-mrw",    "Minolta RAW"),
    _f("kdc",   "image", "kdc",            "image/x-kodak-kdc",      "Kodak RAW"),
    _f("erf",   "image", "erf",            "image/x-epson-erf",      "Epson RAW"),
    _f("3fr",   "image", "3fr",            "image/x-hasselblad-3fr", "Hasselblad RAW"),
    _f("iiq",   "image", "iiq",            "image/x-phaseone-iiq",   "Phase One RAW"),
    _f("mef",   "image", "mef",            "image/x-mamiya-mef",     "Mamiya RAW"),
    _f("nrw",   "image", "nrw",            "image/x-nikon-nrw",      "Nikon RAW (NRW)"),
    _f("dcr",   "image", "dcr",            "image/x-kodak-dcr",      "Kodak DCR"),
    _f("crw",   "image", "crw",            "image/x-canon-crw",      "Canon CRW"),
    _f("sr2",   "image", "sr2 srf",        "image/x-sony-sr2",       "Sony SR2/SRF"),
    _f("g3",    "image", "g3",             "image/g3fax",            "Group 3 fax"),
    _f("g4",    "image", "g4",             "image/g4fax",            "Group 4 fax"),
    _f("psb",   "image", "psb",            "image/vnd.adobe.photoshop", "Adobe Photoshop large document"),
    _f("cut",   "image", "cut",            "image/x-halo-cut",       "Dr. Halo CUT"),
    _f("art",   "image", "art",            "image/x-pfs-art",        "PFS: 1st Publisher clip art"),
    _f("rla",   "image", "rla",            "image/x-rla",            "Alias/Wavefront RLA"),
    _f("rle",   "image", "rle",            "image/x-rle",            "Utah RLE"),
    _f("tim",   "image", "tim",            "image/x-tim",            "PSX TIM"),
    _f("pgx",   "image", "pgx",            "image/x-pgx",            "JPEG 2000 PGX"),
    _f("ipl",   "image", "ipl",            "image/x-ipl",            "IPL image sequence"),
    _f("mat",   "image", "mat",            "application/x-matlab-data", "MATLAB level 5 image"),
    _f("vicar", "image", "vicar vic",      "image/x-vicar",          "VICAR rasterfile"),
    _f("otb",   "image", "otb",            "image/x-otb",            "On-the-air bitmap"),
    _f("uyvy",  "image", "uyvy",           "image/x-uyvy",           "16-bit/pixel interleaved YUV"),
    _f("cals",  "image", "cal cals",       "image/x-cals",           "CALS Type 1 raster"),
    _f("hrz",   "image", "hrz",            "image/x-hrz",            "Slow-scan TV"),
    _f("aai",   "image", "aai",            "image/x-aai",            "AAI Dune image"),
    _f("avs",   "image", "avs",            "image/x-avs",            "AVS X image"),
    _f("fax",   "image", "fax",            "image/x-fax",            "Group 3 FAX"),
    _f("jbg",   "image", "jbg",            "image/x-jbig",           "JBIG1"),
    _f("mtv",   "image", "mtv",            "image/x-mtv",            "MTV raytracing image"),
    _f("ptif",  "image", "ptif",           "image/tiff",             "Pyramid encoded TIFF"),
    _f("vips",  "image", "vips v",         "image/x-vips",           "VIPS image"),
    # --------------------------------------------------------------- vector
    _f("svg",   "vector", "svg",           "image/svg+xml",          "Scalable Vector Graphics"),
    _f("svgz",  "vector", "svgz",          "image/svg+xml",          "Compressed SVG"),
    _f("eps",   "vector", "eps epsf epsi", "application/postscript", "Encapsulated PostScript"),
    _f("ps",    "vector", "ps",            "application/postscript", "PostScript"),
    _f("ai",    "vector", "ai",            "application/illustrator", "Adobe Illustrator (PDF-based)"),
    _f("wmf",   "vector", "wmf",           "image/wmf",              "Windows Metafile"),
    _f("emf",   "vector", "emf",           "image/emf",              "Enhanced Metafile"),
    _f("dxf",   "vector", "dxf",           "image/vnd.dxf",          "AutoCAD DXF"),
    _f("cgm",   "vector", "cgm",           "image/cgm",              "Computer Graphics Metafile"),
    _f("dot",   "vector", "dot gv",        "text/vnd.graphviz",      "Graphviz DOT graph"),
    # ---------------------------------------------------------------- audio
    _f("mp3",   "audio", "mp3",            "audio/mpeg",             "MPEG-1 Layer III"),
    _f("wav",   "audio", "wav",            "audio/wav",              "Waveform audio"),
    _f("flac",  "audio", "flac",           "audio/flac",             "Free Lossless Audio Codec"),
    _f("ogg",   "audio", "ogg oga",        "audio/ogg",              "Ogg Vorbis"),
    _f("opus",  "audio", "opus",           "audio/opus",             "Opus in Ogg container"),
    _f("aac",   "audio", "aac",            "audio/aac",              "Raw AAC (ADTS)"),
    _f("m4a",   "audio", "m4a",            "audio/mp4",              "MPEG-4 audio"),
    _f("wma",   "audio", "wma",            "audio/x-ms-wma",         "Windows Media Audio"),
    _f("aiff",  "audio", "aiff aif aifc",  "audio/aiff",             "Audio Interchange File Format"),
    _f("au",    "audio", "au snd",         "audio/basic",            "Sun/NeXT audio"),
    _f("ac3",   "audio", "ac3",            "audio/ac3",              "Dolby Digital AC-3"),
    _f("eac3",  "audio", "eac3",           "audio/eac3",             "Dolby Digital Plus"),
    _f("dts",   "audio", "dts",            "audio/vnd.dts",          "DTS Coherent Acoustics"),
    _f("amr",   "audio", "amr",            "audio/amr",              "Adaptive Multi-Rate"),
    _f("mka",   "audio", "mka",            "audio/x-matroska",       "Matroska audio"),
    _f("caf",   "audio", "caf",            "audio/x-caf",            "Core Audio Format"),
    _f("w64",   "audio", "w64",            "audio/x-w64",            "Sony Wave64"),
    _f("mp2",   "audio", "mp2",            "audio/mpeg",             "MPEG-1 Layer II"),
    _f("ape",   "audio", "ape",            "audio/x-ape",            "Monkey's Audio"),
    _f("wv",    "audio", "wv",             "audio/x-wavpack",        "WavPack"),
    _f("tta",   "audio", "tta",            "audio/x-tta",            "True Audio"),
    _f("spx",   "audio", "spx",            "audio/ogg",              "Speex"),
    _f("gsm",   "audio", "gsm",            "audio/x-gsm",            "GSM 06.10"),
    _f("voc",   "audio", "voc",            "audio/x-voc",            "Creative Voice"),
    _f("mlp",   "audio", "mlp",            "audio/x-mlp",            "Meridian Lossless Packing"),
    _f("ra",    "audio", "ra rm",          "audio/x-realaudio",      "RealAudio"),
    _f("m4b",   "audio", "m4b",            "audio/mp4",              "MPEG-4 audiobook"),
    _f("weba",  "audio", "weba",           "audio/webm",             "WebM audio"),
    _f("alac",  "audio", "alac",           "audio/mp4",              "Apple Lossless (in MP4)"),
    _f("pcm",   "audio", "pcm raw",        "audio/L16",              "Raw signed 16-bit PCM"),
    _f("sbc",   "audio", "sbc",            "audio/x-sbc",            "Bluetooth SBC"),
    _f("wavpack","audio", "wvp",           "audio/x-wavpack",        "WavPack (alt. extension)"),
    _f("oma",   "audio", "oma",            "audio/x-oma",            "Sony OpenMG audio"),
    _f("8svx",  "audio", "8svx",           "audio/x-8svx",           "Amiga 8SVX"),
    _f("aptx",  "audio", "aptx",           "audio/aptx",             "aptX"),
    _f("g722",  "audio", "g722",           "audio/g722",             "G.722 ADPCM"),
    _f("midi",  "audio", "mid midi kar",   "audio/midi",             "Standard MIDI file"),
    # ---------------------------------------------------------------- video
    _f("mp4",   "video", "mp4 m4v",        "video/mp4",              "MPEG-4 Part 14"),
    _f("mkv",   "video", "mkv",            "video/x-matroska",       "Matroska video"),
    _f("webm",  "video", "webm",           "video/webm",             "WebM"),
    _f("avi",   "video", "avi",            "video/x-msvideo",        "Audio Video Interleave"),
    _f("mov",   "video", "mov qt",         "video/quicktime",        "QuickTime movie"),
    _f("flv",   "video", "flv",            "video/x-flv",            "Flash video"),
    _f("wmv",   "video", "wmv asf",        "video/x-ms-wmv",         "Windows Media Video"),
    _f("mpeg",  "video", "mpg mpeg mpe m1v m2v", "video/mpeg",       "MPEG-1/2 program stream"),
    _f("ts",    "video", "ts mts m2ts",    "video/mp2t",             "MPEG transport stream"),
    _f("3gp",   "video", "3gp 3g2",        "video/3gpp",             "3GPP mobile video"),
    _f("ogv",   "video", "ogv",            "video/ogg",              "Ogg Theora"),
    _f("vob",   "video", "vob",            "video/dvd",              "DVD video object"),
    _f("mxf",   "video", "mxf",            "application/mxf",        "Material Exchange Format"),
    _f("y4m",   "video", "y4m",            "video/x-yuv4mpeg",       "YUV4MPEG2 raw video"),
    _f("dv",    "video", "dv",             "video/dv",               "Digital Video"),
    _f("rm",    "video", "rmvb",           "application/vnd.rn-realmedia", "RealMedia"),
    _f("swf",   "video", "swf",            "application/x-shockwave-flash", "Shockwave Flash"),
    _f("f4v",   "video", "f4v",            "video/x-f4v",            "Flash MP4 video"),
    _f("h264",  "video", "h264 264",       "video/h264",             "Raw H.264 elementary stream"),
    _f("hevc",  "video", "hevc h265 265",  "video/h265",             "Raw H.265 elementary stream"),
    _f("ivf",   "video", "ivf",            "video/x-ivf",            "Indeo video file (VP8/VP9/AV1)"),
    _f("nut",   "video", "nut",            "video/x-nut",            "NUT container"),
    _f("divx",  "video", "divx",           "video/x-msvideo",        "DivX (AVI)"),
    # ------------------------------------------------------------- subtitle
    _f("srt",   "subtitle", "srt",         "application/x-subrip",   "SubRip subtitles"),
    _f("vtt",   "subtitle", "vtt",         "text/vtt",               "WebVTT subtitles"),
    _f("ass",   "subtitle", "ass",         "text/x-ssa",             "Advanced SubStation Alpha"),
    _f("ssa",   "subtitle", "ssa",         "text/x-ssa",             "SubStation Alpha"),
    _f("ttml",  "subtitle", "ttml dfxp",   "application/ttml+xml",   "Timed Text Markup Language"),
    _f("lrc",   "subtitle", "lrc",         "text/x-lrc",             "LRC lyrics"),
    _f("sub",   "subtitle", "sub",         "text/x-microdvd",        "MicroDVD subtitles"),
    # ------------------------------------------------------------- document
    _f("pdf",   "document", "pdf",         "application/pdf",        "Portable Document Format"),
    _f("txt",   "document", "txt text",    "text/plain",             "Plain text"),
    _f("md",    "document", "md markdown mkd", "text/markdown",      "Markdown"),
    _f("html",  "document", "html htm xhtml", "text/html",           "HTML"),
    _f("docx",  "document", "docx",        "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "Word document (OOXML)"),
    _f("doc",   "document", "doc",         "application/msword",     "Word 97-2003 document"),
    _f("odt",   "document", "odt",         "application/vnd.oasis.opendocument.text", "OpenDocument text"),
    _f("fodt",  "document", "fodt",        "application/vnd.oasis.opendocument.text-flat-xml", "Flat OpenDocument text"),
    _f("rtf",   "document", "rtf",         "application/rtf",        "Rich Text Format"),
    _f("wps",   "document", "wps",         "application/vnd.ms-works", "Microsoft Works document"),
    _f("wpd",   "document", "wpd",         "application/vnd.wordperfect", "WordPerfect document"),
    _f("abw",   "document", "abw",         "application/x-abiword",  "AbiWord document"),
    _f("pages", "document", "pages",       "application/x-iwork-pages-sffpages", "Apple Pages"),
    _f("tex",   "document", "tex latex",   "application/x-latex",    "LaTeX source"),
    _f("rst",   "document", "rst",         "text/x-rst",             "reStructuredText"),
    _f("org",   "document", "org",         "text/x-org",             "Emacs Org mode"),
    _f("textile","document", "textile",    "text/x-textile",         "Textile"),
    _f("mediawiki","document", "wiki mediawiki", "text/x-wiki",      "MediaWiki markup"),
    _f("dokuwiki","document", "dokuwiki",  "text/x-dokuwiki",        "DokuWiki markup"),
    _f("asciidoc","document", "adoc asciidoc", "text/x-asciidoc",    "AsciiDoc"),
    _f("typst", "document", "typ typst",   "text/x-typst",           "Typst markup"),
    _f("man",   "document", "man 1 7",     "application/x-troff-man", "roff manual page"),
    _f("docbook","document", "dbk docbook", "application/docbook+xml", "DocBook XML"),
    _f("opml",  "document", "opml",        "text/x-opml",            "Outline Processor Markup Language"),
    _f("ipynb", "document", "ipynb",       "application/x-ipynb+json", "Jupyter notebook"),
    _f("jira",  "document", "jira",        "text/x-jira",            "Jira wiki markup"),
    _f("muse",  "document", "muse",        "text/x-muse",            "Emacs Muse"),
    _f("t2t",   "document", "t2t",         "text/x-txt2tags",        "txt2tags"),
    _f("haddock","document", "haddock",    "text/x-haddock",         "Haddock markup"),
    _f("pandoc-json","document", "pandoc.json", "application/json", "Pandoc AST (JSON)"),
    _f("xps",   "document", "xps oxps",    "application/vnd.ms-xpsdocument", "XML Paper Specification"),
    _f("djvu",  "document", "djvu djv",    "image/vnd.djvu",         "DjVu"),
    _f("pptx",  "document", "pptx",        "application/vnd.openxmlformats-officedocument.presentationml.presentation", "PowerPoint presentation (OOXML)"),
    _f("ppt",   "document", "ppt",         "application/vnd.ms-powerpoint", "PowerPoint 97-2003"),
    _f("odp",   "document", "odp",         "application/vnd.oasis.opendocument.presentation", "OpenDocument presentation"),
    _f("key",   "document", "key",         "application/x-iwork-keynote-sffkey", "Apple Keynote"),
    _f("xlsx",  "document", "xlsx",        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "Excel workbook (OOXML)"),
    _f("xls",   "document", "xls",         "application/vnd.ms-excel", "Excel 97-2003"),
    _f("ods",   "document", "ods",         "application/vnd.oasis.opendocument.spreadsheet", "OpenDocument spreadsheet"),
    _f("numbers","document", "numbers",    "application/x-iwork-numbers-sffnumbers", "Apple Numbers"),
    _f("odg",   "document", "odg",         "application/vnd.oasis.opendocument.graphics", "OpenDocument drawing"),
    _f("vsd",   "document", "vsd vsdx",    "application/vnd.visio",  "Microsoft Visio"),
    _f("pub",   "document", "pub",         "application/x-mspublisher", "Microsoft Publisher"),
    _f("sxw",   "document", "sxw",         "application/vnd.sun.xml.writer", "OpenOffice.org 1.0 text"),
    _f("uot",   "document", "uot",         "application/x-uof",      "Unified Office Format text"),
    _f("dotx",  "document", "dotx dot",    "application/vnd.openxmlformats-officedocument.wordprocessingml.template", "Word template"),
    _f("dvi",   "document", "dvi",         "application/x-dvi",      "TeX device-independent file"),
    _f("gnumeric","document", "gnumeric",  "application/x-gnumeric", "Gnumeric spreadsheet"),
    _f("bibtex","document", "bib bibtex",  "text/x-bibtex",          "BibTeX bibliography"),
    _f("biblatex","document", "biblatex",  "text/x-bibtex",          "BibLaTeX bibliography"),
    _f("csljson","document", "csl.json",   "application/vnd.citationstyles.csl+json", "CSL JSON bibliography"),
    # ---------------------------------------------------------------- ebook
    _f("epub",  "ebook", "epub",           "application/epub+zip",   "EPUB"),
    _f("mobi",  "ebook", "mobi prc",       "application/x-mobipocket-ebook", "Mobipocket"),
    _f("azw3",  "ebook", "azw3 azw kf8",   "application/vnd.amazon.mobi8-ebook", "Kindle KF8"),
    _f("fb2",   "ebook", "fb2",            "application/x-fictionbook+xml", "FictionBook 2"),
    _f("lit",   "ebook", "lit",            "application/x-ms-reader", "Microsoft Reader"),
    _f("lrf",   "ebook", "lrf",            "application/x-sony-bbeb", "Sony BroadBand eBook"),
    _f("pdb",   "ebook", "pdb",            "application/vnd.palm",   "Palm database (eReader/Plucker)"),
    _f("cbz",   "ebook", "cbz",            "application/vnd.comicbook+zip", "Comic book archive (zip)"),
    _f("cbr",   "ebook", "cbr",            "application/vnd.comicbook-rar", "Comic book archive (rar)"),
    _f("htmlz", "ebook", "htmlz",          "application/x-htmlz",    "Zipped HTML ebook"),
    _f("txtz",  "ebook", "txtz",           "application/x-txtz",     "Zipped text ebook"),
    _f("snb",   "ebook", "snb",            "application/x-snb",      "Shanda Bambook"),
    _f("tcr",   "ebook", "tcr",            "application/x-tcr",      "Psion TCR"),
    _f("pmlz",  "ebook", "pmlz",           "application/x-pmlz",     "eReader PML (zipped)"),
    _f("rb",    "ebook", "rb",             "application/x-rocketbook", "RocketBook"),
    _f("chm",   "ebook", "chm",            "application/vnd.ms-htmlhelp", "Compiled HTML Help"),
    _f("kepub", "ebook", "kepub",          "application/epub+zip",   "Kobo EPUB"),
    # ----------------------------------------------------------------- data
    _f("json",  "data", "json",            "application/json",       "JSON"),
    _f("jsonl", "data", "jsonl ndjson",    "application/x-ndjson",   "Newline-delimited JSON"),
    _f("yaml",  "data", "yaml yml",        "application/yaml",       "YAML"),
    _f("toml",  "data", "toml",            "application/toml",       "TOML"),
    _f("xml",   "data", "xml",             "application/xml",        "XML"),
    _f("csv",   "data", "csv",             "text/csv",               "Comma-separated values"),
    _f("tsv",   "data", "tsv tab",         "text/tab-separated-values", "Tab-separated values"),
    _f("ini",   "data", "ini cfg conf",    "text/plain",             "INI configuration"),
    _f("plist", "data", "plist",           "application/x-plist",    "Apple property list"),
    _f("msgpack","data", "msgpack mpk",    "application/msgpack",    "MessagePack"),
    _f("pickle","data", "pkl pickle",      "application/octet-stream", "Python pickle"),
    _f("sqlite","data", "sqlite db sqlite3", "application/vnd.sqlite3", "SQLite database"),
    _f("parquet","data", "parquet",        "application/vnd.apache.parquet", "Apache Parquet"),
    _f("vcf",   "data", "vcf vcard",       "text/vcard",             "vCard contacts"),
    _f("ics",   "data", "ics",             "text/calendar",          "iCalendar"),
    _f("bson",  "data", "bson",            "application/bson",       "Binary JSON"),
    # -------------------------------------------------------------- archive
    _f("zip",   "archive", "zip",          "application/zip",        "ZIP archive"),
    _f("tar",   "archive", "tar",          "application/x-tar",      "Tape archive"),
    _f("tar.gz","archive", "tar.gz tgz",   "application/gzip",       "gzip-compressed tar"),
    _f("tar.bz2","archive", "tar.bz2 tbz2 tbz", "application/x-bzip2", "bzip2-compressed tar"),
    _f("tar.xz","archive", "tar.xz txz",   "application/x-xz",       "xz-compressed tar"),
    _f("tar.zst","archive", "tar.zst tzst", "application/zstd",      "zstd-compressed tar"),
    _f("7z",    "archive", "7z",           "application/x-7z-compressed", "7-Zip archive"),
    _f("rar",   "archive", "rar",          "application/vnd.rar",    "RAR archive"),
    _f("gz",    "archive", "gz",           "application/gzip",       "gzip single file"),
    _f("bz2",   "archive", "bz2",          "application/x-bzip2",    "bzip2 single file"),
    _f("xz",    "archive", "xz",           "application/x-xz",       "xz single file"),
    _f("zst",   "archive", "zst",          "application/zstd",       "zstd single file"),
    _f("lz4",   "archive", "lz4",          "application/x-lz4",      "LZ4 single file"),
    _f("lzma",  "archive", "lzma",         "application/x-lzma",     "LZMA single file"),
    _f("cpio",  "archive", "cpio",         "application/x-cpio",     "cpio archive"),
    _f("ar",    "archive", "a ar",         "application/x-archive",  "Unix ar archive"),
    _f("iso",   "archive", "iso",          "application/x-iso9660-image", "ISO 9660 image"),
    _f("cab",   "archive", "cab",          "application/vnd.ms-cab-compressed", "Microsoft cabinet"),
    _f("deb",   "archive", "deb",          "application/vnd.debian.binary-package", "Debian package"),
    _f("rpm",   "archive", "rpm",          "application/x-rpm",      "RPM package"),
    _f("wim",   "archive", "wim",          "application/x-ms-wim",   "Windows imaging"),
    _f("jar",   "archive", "jar war ear",  "application/java-archive", "Java archive"),
    _f("apk",   "archive", "apk",          "application/vnd.android.package-archive", "Android package"),
    _f("dmg",   "archive", "dmg",          "application/x-apple-diskimage", "Apple disk image"),
    _f("arj",   "archive", "arj",          "application/x-arj",      "ARJ archive"),
    _f("lzh",   "archive", "lzh lha",      "application/x-lzh-compressed", "LHA archive"),
    _f("z",     "archive", "z",            "application/x-compress", "Unix compress"),
    _f("xar",   "archive", "xar pkg",      "application/x-xar",      "XAR archive"),
    # ----------------------------------------------------------------- font
    _f("ttf",   "font", "ttf",             "font/ttf",               "TrueType font"),
    _f("otf",   "font", "otf",             "font/otf",               "OpenType font"),
    _f("woff",  "font", "woff",            "font/woff",              "Web Open Font Format"),
    _f("woff2", "font", "woff2",           "font/woff2",             "Web Open Font Format 2"),
    _f("ttx",   "font", "ttx",             "application/xml",        "fontTools XML font dump"),
    _f("eot",   "font", "eot",             "application/vnd.ms-fontobject", "Embedded OpenType"),
    _f("dfont", "font", "dfont",           "application/x-dfont",    "Mac data-fork font"),
    _f("pfb",   "font", "pfb pfa",         "application/x-font-type1", "Type 1 font"),
    _f("bdf",   "font", "bdf",             "application/x-font-bdf", "Glyph Bitmap Distribution Format"),
    _f("pcf",   "font", "pcf",             "application/x-font-pcf", "Portable Compiled Format"),
    _f("svgfont","font", "svg.font",       "image/svg+xml",          "SVG font"),
    # ---------------------------------------------------------------- model
    _f("obj",   "model", "obj",            "model/obj",              "Wavefront OBJ"),
    _f("stl",   "model", "stl",            "model/stl",              "Stereolithography"),
    _f("ply",   "model", "ply",            "application/x-ply",      "Stanford polygon"),
    _f("gltf",  "model", "gltf",           "model/gltf+json",        "GL Transmission Format (JSON)"),
    _f("glb",   "model", "glb",            "model/gltf-binary",      "GL Transmission Format (binary)"),
    _f("dae",   "model", "dae",            "model/vnd.collada+xml",  "COLLADA"),
    _f("fbx",   "model", "fbx",            "application/x-fbx",      "Autodesk FBX"),
    _f("3ds",   "model", "3ds",            "image/x-3ds",            "3D Studio"),
    _f("x3d",   "model", "x3d",            "model/x3d+xml",          "X3D"),
    _f("3mf",   "model", "3mf",            "model/3mf",              "3D Manufacturing Format"),
    _f("off",   "model", "off",            "application/x-off",      "Object File Format"),
    _f("x",     "model", "x",              "application/x-directx",  "DirectX X"),
    _f("blend", "model", "blend",          "application/x-blender",  "Blender scene"),
    _f("assxml","model", "assxml",         "application/xml",        "Assimp XML dump"),
]
# fmt: on

FORMATS: dict[str, Format] = {f.name: f for f in _FORMAT_LIST}
assert len(FORMATS) == len(_FORMAT_LIST), "duplicate format name"

# Extension index. Compound extensions (``tar.gz``) are checked before the
# single ones, longest first, so ``archive.tar.gz`` resolves to ``tar.gz``.
_BY_EXTENSION: dict[str, Format] = {}
for _fmt in _FORMAT_LIST:
    for _ext in _fmt.extensions:
        _BY_EXTENSION.setdefault(_ext.lower(), _fmt)
_EXTENSIONS_LONGEST_FIRST = sorted(_BY_EXTENSION, key=len, reverse=True)


def get(name: str) -> Format:
    """Return the format with canonical ``name`` (or a known extension)."""
    key = name.lower().lstrip(".")
    if key in FORMATS:
        return FORMATS[key]
    if key in _BY_EXTENSION:
        return _BY_EXTENSION[key]
    raise UnknownFormatError(f"unknown format: {name!r}")


def by_extension(filename: str | Path) -> Format | None:
    """Guess a format from a filename. Returns ``None`` if nothing matches."""
    lower = str(filename).lower()
    base = lower.rsplit("/", 1)[-1]
    for ext in _EXTENSIONS_LONGEST_FIRST:
        if base.endswith("." + ext):
            return _BY_EXTENSION[ext]
    return None


def all_formats(category: str | None = None) -> list[Format]:
    fmts = list(_FORMAT_LIST)
    if category:
        fmts = [f for f in fmts if f.category == category]
    return fmts


def names(fmts: Iterable[Format | str]) -> frozenset[str]:
    """Normalise a mix of formats and names into a set of canonical names."""
    out = set()
    for item in fmts:
        out.add(item.name if isinstance(item, Format) else get(item).name)
    return frozenset(out)


def output_path(source: Path, fmt: Format, directory: Path | None = None) -> Path:
    """Compute the default output path for converting ``source`` to ``fmt``."""
    src_fmt = by_extension(source)
    stem = source.name
    if src_fmt is not None:
        for ext in src_fmt.extensions:
            if stem.lower().endswith("." + ext):
                stem = stem[: -(len(ext) + 1)]
                break
    else:
        stem = source.stem
    target_dir = directory if directory is not None else source.parent
    return target_dir / f"{stem}.{fmt.extension}"
