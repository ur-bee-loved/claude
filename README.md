# Omniconv

Omniconv is a native Linux file converter. It has a GTK 4 / libadwaita
desktop window and an equivalent command line, and it converts between
image, vector, audio, video, subtitle, document (including PDF), e-book,
structured-data, archive and font formats.

It does not reimplement any codec. Instead it orchestrates the conversion
tools that already exist on a Linux system (ffmpeg, ImageMagick,
Ghostscript, poppler, LibreOffice, pandoc, calibre, tesseract, and several
Python libraries) behind one interface, and it chains them automatically
when no single tool covers a conversion.

On the system used during development (Ubuntu 24.04 with the packages from
`scripts/install-deps.sh`) the registry reports 100 usable backends out of
121 defined, 314 recognised source formats and roughly 42,000 reachable
source-to-target pairs. Those numbers depend entirely on what is installed;
`omniconv doctor` prints the figures for your machine.

## Contents

1. [Installation](#installation)
2. [Usage](#usage)
3. [How it works](#how-it-works)
4. [Supported formats](#supported-formats)
5. [Options](#options)
6. [Known limitations](#known-limitations)
7. [Development](#development)

## Installation

Omniconv itself is pure Python (3.10 or newer). Every backend is optional:
the application checks at start-up which tools and libraries are present and
offers only the conversions those can perform.

```sh
git clone https://github.com/ur-bee-loved/claude omniconv
cd omniconv
./scripts/install-deps.sh     # system backends via apt, dnf, pacman or zypper
make install                  # pip install + desktop entry, icon, metainfo
omniconv doctor               # shows what was detected
```

`install-deps.sh -n` prints what it would install without changing
anything. The script checks which tools are already on your `PATH` and
requests only the packages for the missing ones, asks the package manager
to skip anything it cannot resolve rather than abort, and then retries any
tool still missing one package at a time (trying alternative package names
in turn). A single conflicting or misnamed package therefore never blocks
the rest of the list. Re-run the script after adding a repository, or after
a failed run, and it picks up where it left off.

The apt package names were exercised on Ubuntu 24.04. The dnf, pacman and
zypper names follow those distributions' conventions but were not all
verified on a live system; a wrong name costs one error line in the retry
stage and nothing else.

**Fedora note.** Fedora's own `ffmpeg-free` lacks the x264 and x265
encoders, so MP4 output uses the MPEG-4 Part 2 codec until you enable RPM
Fusion and run `sudo dnf swap ffmpeg-free ffmpeg --allowerasing`. The
installer never requests `ffmpeg` when any ffmpeg is already present,
precisely to avoid the conflict between the two packages.

**Debian and Ubuntu note.** Chromium is not requested through apt because
Ubuntu ships it as a snap; install it however you prefer if you want the
headless-browser HTML renderer. Typst is not packaged for Ubuntu 24.04.

`make install` installs into `~/.local`; use `sudo make install
PREFIX=/usr/local` for a system-wide install. To try it without installing:

```sh
python3 -m omniconv doctor
python3 -m omniconv gui
```

The graphical interface needs the GObject introspection bindings for GTK 4
and libadwaita (`python3-gi gir1.2-gtk-4.0 gir1.2-adw-1` on Debian and
Ubuntu, `python3-gobject gtk4 libadwaita` on Fedora). The command line works
without them.

### Which packages matter for what

| Backend | Enables |
|---|---|
| Pillow (`pip install pillow pillow-heif`) | most raster image work, HEIC/AVIF |
| ImageMagick (`imagemagick`) | camera RAW, XCF, EXR, DICOM, PICT and about 60 other image formats |
| ffmpeg | all audio and video transcoding, subtitle conversion, frame extraction |
| PyMuPDF (`pip install pymupdf`) | PDF rendering, text/SVG extraction, PDF rewriting, EPUB/XPS/CBZ to PDF |
| poppler-utils, Ghostscript, qpdf, img2pdf | alternative PDF paths, PostScript, PDF compression presets |
| LibreOffice (writer, calc, impress, draw) | DOC/DOCX/ODT/RTF/XLS/XLSX/PPT/PPTX and legacy office formats |
| pandoc | Markdown, reStructuredText, LaTeX, Org, DocBook, EPUB, DOCX, and other markup |
| calibre | MOBI, AZW3, FB2, LIT, LRF and other e-book formats |
| librsvg, CairoSVG, Inkscape, potrace | SVG rendering, bitmap tracing, WMF/EMF/DXF |
| tesseract, OCRmyPDF | text recognition from images and scanned PDFs |
| fontTools, FontForge | TTF/OTF/WOFF/WOFF2/TTX, Type 1, BDF |
| sox, lame, flac, vorbis-tools, opus-tools, mpg123, faad, wavpack, speex, twolame | audio fallbacks when ffmpeg is missing |
| TiMidity++ or FluidSynth | MIDI to audio |
| 7-Zip, libarchive (`bsdtar`), unar, zstd, lz4 | exotic archives (RAR, CAB, ISO, DEB, RPM, XAR) and extra compressors |
| Graphviz | DOT graphs to SVG, PNG, PDF and more |
| assimp | 3D models: OBJ, STL, PLY, glTF/GLB, COLLADA, FBX, 3DS, X3D, 3MF |
| wkhtmltopdf, WeasyPrint, Chromium | HTML rendering to PDF and images |
| Asciidoctor, Typst, TeX Live, groff | AsciiDoc, Typst, LaTeX and man page compilation |
| DjVuLibre, pdf2djvu | DjVu to PDF/images/text and back |
| libwebp, libheif, libjxl tools | WebP, HEIF/AVIF and JPEG XL codecs when Pillow lacks them |
| optipng, pngquant, jpegoptim, gifsicle, svgo, scour | same-format optimisation (`-t png` on a PNG) |
| antiword, catdoc, odt2txt, docx2txt, unrtf, Gnumeric | lightweight text extraction and spreadsheet conversion |
| dcraw, darktable, RawTherapee | camera RAW development |

## Usage

### Graphical interface

Run `omniconv gui` or start Omniconv from the application menu. Drop files
onto the window (or press `+`), choose a target from the "Convert to" list,
optionally set an output folder and options, and press Convert. The list of
targets only contains formats that every listed file can reach, and the
"Route" row shows which backends will be used. When several inputs can be
combined into one output (images into a PDF, PDFs into a PDF, files into an
archive, clips into one audio or video file) a "Merge into one file" switch
appears.

### Command line

```sh
omniconv convert photo.heic -t jpeg                      # next to the source
omniconv convert *.wav -t mp3 --bitrate 192k -o out/     # into a directory
omniconv convert paper.docx -t png --dpi 200             # one PNG per page
omniconv convert video.mkv -t mp3 --start 00:01:00 --duration 30
omniconv convert video.mp4 -t jpeg --fps 1               # one frame per second
omniconv convert scan.pdf -t pdf --compress 3            # smaller PDF
omniconv convert book.pdf -t pdf --split                 # one file per page
omniconv convert book.pdf -t png --extract-images        # embedded images
omniconv convert data.csv -t xlsx
omniconv convert font.ttf -t woff2
omniconv in.png out.webp                                 # shortcut form

omniconv merge a.png b.jpg c.pdf -o bundle.pdf
omniconv merge part1.mp4 part2.mp4 -o joined.mp4
omniconv merge frame*.png -o slideshow.mp4 --fps 2            # image sequence to video
omniconv merge report.md figure.png -o report.zip

omniconv formats                    # every format with an installed backend
omniconv formats --from pdf         # what PDF can become, and how
omniconv formats --to woff2         # what can become WOFF2
omniconv route docx png             # explains the chain that would run
omniconv info file.mp4              # identify a file and show its properties
omniconv doctor                     # backend availability and install hints
```

`--backend NAME` forces a specific converter, which is useful for comparing
backends (`omniconv route png pdf` lists the alternatives). `--overwrite`
replaces existing outputs; by default a numbered name such as
`photo (1).jpg` is used and the input file is never touched.

## How it works

The design question behind a "convert anything" tool is not how to encode a
JPEG; libraries do that. It is how to organise dozens of tools with
overlapping abilities so that the right one runs, and so that a missing tool
narrows the feature set instead of breaking the program.

### Formats as nodes, converters as edges

`omniconv/core/formats.py` is a table of about 290 formats. Each entry has a
canonical name (`jpeg`, not `jpg`), the extensions it may carry, a MIME type
and a category. Converters refer to formats only by canonical name.

`omniconv/core/registry.py` holds converters. A converter declares the
formats it reads, the formats it writes, the tools or Python modules it
needs, a cost, and the options it honours. Together the converters form a
directed graph whose nodes are formats. A converter is only an edge in the
graph when its requirements are satisfied, which is how the application
degrades gracefully.

Two details keep the format lists honest. First, several backends compute
their lists at run time from the tool itself: Pillow's plugin registry,
`convert -list format`, `ffmpeg -encoders` and `ffmpeg -muxers`,
`pandoc --list-input-formats`. A Pillow build without libwebp, or an ffmpeg
without libmp3lame, therefore does not advertise WebP or MP3. Second, a
converter can attach a predicate to exclude individual pairs (LibreOffice
cannot turn a spreadsheet into a presentation, even though it reads the one
and writes the other).

### Route finding

A request such as "DOCX to PNG" becomes a shortest-path search
(Dijkstra) over the graph. Each hop costs the converter's cost plus a fixed
penalty, so a direct converter always beats a chain when one exists, and
among chains the one through cheaper, faster tools wins. Intermediate
formats are restricted to the categories of the endpoints plus the two hub
categories (documents and raster images), which prevents nonsensical detours
such as routing an image conversion through an audio file. A small
additional penalty on intermediates outside a short list of preferred hubs
(PNG, PDF, WAV, HTML, JSON, TAR, ...) breaks ties towards lossless,
widely readable formats. Routes are limited to three hops.

The result is a list of steps, each naming the converter and the exact
source and target format of that step. `omniconv route` prints it; the GUI
shows it in the "Route" row.

### Execution

`omniconv/core/engine.py` runs a route. Each step receives a `Job`
describing its input file, the output path to write, the two formats, the
option dictionary and a scratch directory. A step may produce several files
(a PDF rendered page by page), in which case the next step runs once per
file. Intermediates live in a temporary directory that is removed
afterwards. Errors from external tools are captured with the last lines of
their standard error so that failure messages are specific.

Content sniffing (`omniconv/core/sniff.py`) inspects the first bytes of
every input before trusting its extension, so a PNG that was renamed to
`.jpg` is treated as a PNG. ZIP-based containers (DOCX, ODT, EPUB, CBZ) are
told apart by their contents. Where a signature is ambiguous (an MP4
container holding only audio, the Ogg family, plain-text markup) the
extension is used as the tiebreaker.

### Front ends

The CLI (`omniconv/cli.py`) and the GUI (`omniconv/gui/`) are thin. Both
generate their option flags and widgets from one table of option
specifications (`omniconv/core/options.py`), so a new option is declared
once. The GUI runs conversions on a worker thread and marshals results back
to the GTK main loop.

## Supported formats

The exact set depends on the installed backends. `omniconv formats` prints
the live table. The families below are covered when the corresponding
backends are present.

* **Images:** PNG, APNG, JPEG, GIF, BMP, TIFF, WebP, ICO, ICNS, HEIF/HEIC,
  AVIF, JPEG 2000, JPEG XL, PNM family, TGA, PCX, DDS, XBM, XPM, SGI, PSD,
  XCF (read), OpenEXR, Radiance HDR, DPX, FITS, DICOM (read), QOI, camera
  RAW (read: DNG, CR2, CR3, NEF, ARW, RAF, ORF, RW2, PEF and others), MIFF,
  MNG, Sun raster, WBMP, JBIG, PICT, XWD, Sixel and more.
* **Vector:** SVG, SVGZ, EPS, PostScript, AI, WMF, EMF, DXF, CGM; bitmap
  tracing to SVG with potrace.
* **Audio:** MP3, WAV, FLAC, Ogg Vorbis, Opus, AAC, M4A/M4B, ALAC, WMA, AIFF,
  AU, AC-3, E-AC-3, DTS, AMR, MKA, CAF, W64, MP2, WavPack, TTA, Speex, GSM,
  VOC, MLP, 8SVX, raw PCM, SBC, aptX, G.722; audio extraction from any video.
* **Video:** MP4, MKV, WebM, AVI, MOV, FLV, WMV, MPEG-1/2, MPEG-TS, 3GP,
  Ogg Theora, VOB, MXF, Y4M, DV, SWF, F4V, raw H.264/H.265, IVF, NUT;
  animated GIF/APNG/WebP; frame extraction to any still-image format.
* **Subtitles:** SRT, WebVTT, ASS, SSA, TTML, LRC, MicroDVD; extraction
  from video containers.
* **Documents:** PDF, plain text, Markdown, HTML, DOCX, DOC, ODT, RTF, WPS,
  WPD, AbiWord, Pages, LaTeX, reStructuredText, Org, Textile, MediaWiki,
  DokuWiki, AsciiDoc (write), Typst, man pages, DocBook, OPML, Jupyter
  notebooks, XPS, DjVu, PPTX, PPT, ODP, Keynote, XLSX, XLS, ODS, Numbers,
  ODG, Visio, Publisher.
* **PDF operations:** render pages to images at any DPI, extract text, HTML,
  SVG or JSON structure, extract embedded images, select and rotate pages,
  split into pages, merge, compress with presets, encrypt and decrypt,
  convert images, SVG, EPUB, XPS and CBZ to PDF, OCR scanned pages.
* **E-books:** EPUB, MOBI, AZW3, FB2, LIT, LRF, PDB, CBZ, CBR, HTMLZ, TXTZ,
  SNB, TCR, PMLZ, RB, CHM (read), KEPUB.
* **Data:** JSON, JSON Lines, YAML, TOML, XML, CSV, TSV, INI, plist,
  MessagePack, XLSX, SQLite; tables to HTML and Markdown.
* **Archives:** ZIP, TAR, tar.gz, tar.bz2, tar.xz, tar.zst, 7z, RAR (read),
  gz, bz2, xz, lzma, zst, lz4, CAB, ISO, ARJ, LHA, WIM, cpio, ar, DEB, RPM,
  JAR, APK (read); any file into an archive; several files into one archive.
* **Fonts:** TTF, OTF, WOFF, WOFF2, TTX, dfont; Type 1, BDF, PCF and SVG
  fonts with FontForge.
* **3D models:** OBJ, STL, PLY, glTF, GLB, COLLADA, FBX, 3DS, X3D, 3MF,
  OFF, DirectX X (via assimp).
* **Other:** Graphviz DOT graphs to any image or vector format; MIDI files
  to any audio format (synthesised with TiMidity++ or FluidSynth);
  BibTeX, BibLaTeX and CSL JSON bibliographies (via pandoc).

## Options

Options are passed as `--name value` on the command line or set in the GUI
sidebar. Each backend applies the ones it understands and ignores the rest.

| Option | Applies to | Meaning |
|---|---|---|
| `quality` | image, video, PDF rendering | lossy encoder quality 1-100 |
| `width`, `height` | image, vector, video, document rendering | resize; aspect kept if one is given |
| `dpi` | rasterising documents and vectors | resolution, default 150 |
| `grayscale`, `rotate`, `background` | image, document | colour, rotation, colour behind transparency |
| `strip_metadata`, `optimize`, `lossless` | image, media | metadata removal, extra compression, lossless mode |
| `frame`, `pages` | multi-page or animated sources | page or frame selection, e.g. `1-3,7` |
| `bitrate`, `sample_rate`, `channels` | audio, video | audio encoding parameters |
| `normalize`, `volume` | audio, video | EBU R128 loudness normalisation, gain |
| `start`, `duration` | audio, video | trimming, seconds or `HH:MM:SS` |
| `video_bitrate`, `crf`, `fps`, `no_audio`, `video_codec`, `audio_codec` | video | video encoding parameters |
| `password` | PDF | open an encrypted file, or encrypt the output |
| `compress` | archives, PDF | compression level 0-9, or PDF preset 0-3 |
| `ocr_language` | OCR | tesseract language codes, e.g. `eng+deu` |
| `encoding`, `delimiter`, `indent`, `sheet` | data | text encoding, CSV delimiter, pretty-print indent, sheet or table |
| `title`, `author`, `font_size`, `page_size` | generated documents | metadata and layout |

### Which backends were exercised

The integration tests and the development smoke runs executed the
following backends on real files: Pillow, ImageMagick, ffmpeg (audio,
video, frames, subtitles, concat), sox, lame, flac, oggenc, opusenc,
PyMuPDF, pypdf, pdftoppm, pdftotext, pdftohtml, pdftocairo, pdfimages,
pdfseparate, pdfunite, Ghostscript, img2pdf, qpdf, rsvg-convert, CairoSVG,
LibreOffice, pandoc, calibre, tesseract, the pure-Python text, data and
archive converters, fontTools, woff2 tools, Graphviz, assimp, TiMidity++,
groff, Asciidoctor, unrtf, docx2txt, Gnumeric, DjVuLibre, pdf2djvu, cjxl,
cwebp, dwebp, gif2webp, optipng, pngquant, jpegoptim, gifsicle, wavpack,
speex, twolame, wkhtmltopdf and wkhtmltoimage.

The following backends are written from the tools' documented command
lines but were not executed during development because the tool was not
installable here: Inkscape, potrace, FontForge, OCRmyPDF, WeasyPrint,
Chromium (the headless-browser backend), Typst, asciidoctor-pdf, pdflatex
and the other TeX engines, dvipdfmx/dvips/dvisvgm, FluidSynth, avifenc,
avifdec, heif-enc (installed but without encoders), dcraw (installed, no
RAW sample), darktable-cli, rawtherapee-cli, mpg123, faad, fdkaac, mac,
svgo, scour, sfnt2woff, woff2sfnt, catdoc, xls2csv, catppt, antiword,
odt2txt and darktable. Treat those as best-effort until you have run them
once; `omniconv route` and `--backend` make it easy to test a single one.

## Known limitations

These are properties of the underlying tools or of deliberate design
choices rather than bugs, and are worth knowing before relying on a result.

* **PDF to DOCX/ODT** goes through LibreOffice's PDF import, which places
  text in frames; the result is editable but does not recover the original
  paragraph structure. Calibre is the alternative (`--backend calibre`).
* **Text from images and scanned PDFs** depends on tesseract and on the
  scan quality; low-resolution images may yield nothing.
* **Plain text as pandoc input** is read as strict Markdown, so characters
  such as `*` or `#` at line starts are interpreted as markup. The
  pure-Python `text-to-html` and `html-to-pdf` converters treat text
  literally and are preferred for `.txt` to HTML or PDF.
* **CSV or record lists to TOML** are wrapped as an array of tables named
  `rows`, because TOML has no top-level array.
* **Vector to raster conversions** rasterise at the given `dpi`. Raster to
  SVG embeds the bitmap by default; for a traced outline convert to PBM
  first and then run potrace (`omniconv convert x.png -t pbm`, then
  `omniconv convert x.pbm -t svg`).
* **Same-name inputs** converting into the same folder (`a.png` and `a.jpg`
  to WebP) produce `a.webp` and `a (1).webp`.
* **Legacy or proprietary formats** (RAW variants, Pages, Keynote, Publisher)
  depend on the decoder inside ImageMagick or LibreOffice and may be
  incomplete for recent file versions.
* The application shells out to external programs and passes file paths
  as arguments, never through a shell, so unusual file names are safe.
  Archive extraction rejects entries that would escape the target
  directory.

## Development

```sh
python3 -m pytest          # unit tests plus integration tests that skip
                           # when a backend is missing
python3 -m omniconv doctor
```

### Adding a backend

Create a module in `omniconv/converters/`, decorate a function with
`@converter(...)`, and add the module name to `_MODULES` in
`omniconv/converters/__init__.py`. The decorator takes the source and
target format names (or a callable that computes them from the tool),
the requirements, a cost and the options the function honours. The function
receives a `Job` and writes `job.target`, returning the list of files it
produced. Nothing else has to change: the route finder, the CLI and the GUI
pick the new edges up automatically.

Costs are the tuning knob. In-process Python libraries sit around 10,
fast external tools around 12-20, LibreOffice at 30 and calibre at 30, so
that heavy processes are used only when nothing lighter can do the job.

### Layout

```
omniconv/
  core/        formats table, sniffing, requirements, registry + routing, engine, options
  converters/  one module per backend
  gui/         GTK 4 / libadwaita application and window
  cli.py       command-line interface
  data/        desktop entry, icon, AppStream metainfo
scripts/       dependency installer
tests/         pytest suite
```

## License

MIT. Omniconv only invokes the external tools listed above; each of them is
distributed under its own license.
