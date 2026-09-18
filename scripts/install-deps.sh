#!/bin/sh
# Install the system backends Omniconv can use. Every package is optional:
# the application detects what is present and offers only those conversions.
set -e

APT="ffmpeg imagemagick ghostscript poppler-utils pandoc libreoffice-writer libreoffice-calc libreoffice-impress libreoffice-draw img2pdf qpdf librsvg2-bin potrace inkscape webp sox lame flac vorbis-tools opus-tools p7zip-full zstd lz4 calibre tesseract-ocr ocrmypdf fontforge graphviz timidity freepats optipng jpegoptim gifsicle pngquant libheif-examples libjxl-tools assimp-utils djvulibre-bin pdf2djvu antiword catdoc odt2txt docx2txt unrtf gnumeric woff2 mpg123 faad wavpack speex twolame libarchive-tools unar asciidoctor dcraw groff wkhtmltopdf python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 python3-pil python3-pip"
DNF="ffmpeg ImageMagick ghostscript poppler-utils pandoc libreoffice-writer libreoffice-calc libreoffice-impress libreoffice-draw img2pdf qpdf librsvg2-tools potrace inkscape libwebp-tools sox lame flac vorbis-tools opus-tools p7zip p7zip-plugins zstd lz4 calibre tesseract ocrmypdf fontforge graphviz timidity++ optipng jpegoptim gifsicle pngquant libheif-tools libjxl-utils assimp djvulibre pdf2djvu antiword catdoc odt2txt unrtf gnumeric woff2-tools mpg123 faad2 wavpack speex-tools twolame bsdtar unar asciidoctor dcraw groff wkhtmltopdf python3-gobject gtk4 libadwaita python3-pillow python3-pip"
PACMAN="ffmpeg imagemagick ghostscript poppler pandoc-cli libreoffice-fresh img2pdf qpdf librsvg potrace inkscape libwebp sox lame flac vorbis-tools opus-tools p7zip zstd lz4 calibre tesseract ocrmypdf fontforge graphviz timidity++ optipng jpegoptim gifsicle pngquant libheif libjxl assimp djvulibre pdf2djvu antiword catdoc odt2txt unrtf gnumeric woff2 mpg123 faad2 wavpack speex twolame libarchive unarchiver asciidoctor dcraw groff wkhtmltopdf python-gobject gtk4 libadwaita python-pillow python-pip"
ZYPPER="ffmpeg ImageMagick ghostscript poppler-tools pandoc libreoffice-writer libreoffice-calc libreoffice-impress libreoffice-draw img2pdf qpdf rsvg-convert potrace inkscape libwebp-tools sox lame flac vorbis-tools opus-tools p7zip-full zstd lz4 calibre tesseract-ocr fontforge python3-gobject typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1 python3-Pillow python3-pip"

SUDO=""
[ "$(id -u)" -ne 0 ] && SUDO="sudo"

if command -v apt-get >/dev/null 2>&1; then
    $SUDO apt-get update
    $SUDO apt-get install -y --no-install-recommends $APT
elif command -v dnf >/dev/null 2>&1; then
    $SUDO dnf install -y $DNF
elif command -v pacman >/dev/null 2>&1; then
    $SUDO pacman -S --needed --noconfirm $PACMAN
elif command -v zypper >/dev/null 2>&1; then
    $SUDO zypper install -y $ZYPPER
else
    echo "unknown package manager; install ffmpeg, imagemagick, ghostscript, poppler, pandoc, libreoffice and the GTK4/libadwaita Python bindings manually" >&2
fi

# Python-side backends. --break-system-packages is needed on Debian/Ubuntu
# for a user-level install; use a virtual environment if you prefer.
python3 -m pip install --user --break-system-packages pillow pillow-heif pymupdf pypdf reportlab markdown openpyxl tomli-w PyYAML cairosvg fonttools brotli msgpack 2>/dev/null \
    || python3 -m pip install --user pillow pillow-heif pymupdf pypdf reportlab markdown openpyxl tomli-w PyYAML cairosvg fonttools brotli msgpack

echo
echo "Done. Run 'omniconv doctor' (or python3 -m omniconv doctor) to see what was detected."
