#!/bin/sh
# Install the system backends Omniconv can use. Every package is optional:
# the application detects what is present and offers only those conversions.
#
# Usage:  ./scripts/install-deps.sh [-n|--dry-run] [--manager apt|dnf|pacman|zypper]
#
# How it works, and why it is written this way:
#   1. Each line of the table below names the command a backend needs and the
#      package that provides it on each distribution. A tool that is already
#      on PATH is skipped, so nothing already installed is requested again.
#      This also avoids conflicts such as Fedora's ffmpeg-free versus RPM
#      Fusion's ffmpeg: if any ffmpeg is present, none is requested.
#   2. The remaining packages are requested in one transaction with the
#      manager's "skip what you cannot resolve" flags, so one unavailable or
#      conflicting package does not abort the whole install.
#   3. Anything still missing afterwards is retried one package at a time,
#      trying alternative names in turn. A wrong name therefore costs one
#      error line, never the rest of the list.
#
# Table format:  probe|apt|dnf|pacman|zypper
#   probe    a command name, or "python:module" for a Python import test,
#            or "gtk" for the GTK 4 + libadwaita binding check
#   fields   "-" means not packaged for that distribution;
#            "a&b" installs a and b together; "a,b" tries a, then b.
# Package names for apt were exercised on Ubuntu 24.04. The dnf, pacman and
# zypper names follow each distribution's conventions but were not all
# verified on a live system; the per-package fallback keeps a mistake local.
set -u

TABLE='
ffmpeg|ffmpeg|ffmpeg-free,ffmpeg|ffmpeg|ffmpeg
magick,convert|imagemagick|ImageMagick|imagemagick|ImageMagick
gs|ghostscript|ghostscript|ghostscript|ghostscript
pdftoppm|poppler-utils|poppler-utils|poppler|poppler-tools
pandoc|pandoc|pandoc|pandoc-cli|pandoc
soffice,libreoffice|libreoffice-writer&libreoffice-calc&libreoffice-impress&libreoffice-draw|libreoffice-writer&libreoffice-calc&libreoffice-impress&libreoffice-draw|libreoffice-fresh|libreoffice-writer&libreoffice-calc&libreoffice-impress&libreoffice-draw
img2pdf|img2pdf|img2pdf,python3-img2pdf|img2pdf|img2pdf
qpdf|qpdf|qpdf|qpdf|qpdf
rsvg-convert|librsvg2-bin|librsvg2-tools|librsvg|rsvg-convert
potrace|potrace|potrace|potrace|potrace
inkscape|inkscape|inkscape|inkscape|inkscape
cwebp|webp|libwebp-tools|libwebp|libwebp-tools
sox|sox|sox|sox|sox
lame|lame|lame|lame|lame
flac|flac|flac|flac|flac
oggenc|vorbis-tools|vorbis-tools|vorbis-tools|vorbis-tools
opusenc|opus-tools|opus-tools|opus-tools|opus-tools
7z,7za,7zz|p7zip-full|p7zip&p7zip-plugins,7zip|p7zip|p7zip-full
zstd|zstd|zstd|zstd|zstd
lz4|lz4|lz4|lz4|lz4
ebook-convert|calibre|calibre|calibre|calibre
tesseract|tesseract-ocr|tesseract|tesseract&tesseract-data-eng|tesseract-ocr
ocrmypdf|ocrmypdf|ocrmypdf|ocrmypdf|ocrmypdf
fontforge|fontforge|fontforge|fontforge|fontforge
dot|graphviz|graphviz|graphviz|graphviz
timidity|timidity&freepats|timidity++|timidity++|timidity
fluidsynth|fluidsynth&fluid-soundfont-gm|fluidsynth&fluid-soundfont-gm|fluidsynth&soundfont-fluid|fluidsynth&fluid-soundfont-gm
optipng|optipng|optipng|optipng|optipng
jpegoptim|jpegoptim|jpegoptim|jpegoptim|jpegoptim
gifsicle|gifsicle|gifsicle|gifsicle|gifsicle
pngquant|pngquant|pngquant|pngquant|pngquant
heif-convert|libheif-examples|libheif-tools|libheif|libheif-tools
cjxl|libjxl-tools|libjxl-utils|libjxl|libjxl-tools
avifenc|libavif-bin|libavif-tools|libavif|libavif-tools
assimp|assimp-utils|assimp|assimp|assimp
ddjvu|djvulibre-bin|djvulibre|djvulibre|djvulibre
pdf2djvu|pdf2djvu|pdf2djvu|pdf2djvu|pdf2djvu
antiword|antiword|antiword|antiword|antiword
catdoc|catdoc|catdoc|catdoc|catdoc
odt2txt|odt2txt|odt2txt|odt2txt|odt2txt
docx2txt|docx2txt|docx2txt|docx2txt|docx2txt
unrtf|unrtf|unrtf|unrtf|unrtf
ssconvert|gnumeric|gnumeric|gnumeric|gnumeric
woff2_compress|woff2|woff2-tools|woff2|woff2-tools
mpg123|mpg123|mpg123|mpg123|mpg123
faad|faad|faad2|faad2|faad2
wavpack|wavpack|wavpack|wavpack|wavpack
speexenc|speex|speex-tools|speex|speex
twolame|twolame|twolame|twolame|twolame
bsdtar|libarchive-tools|bsdtar|libarchive|bsdtar
unar|unar|unar|unarchiver|unar
asciidoctor|asciidoctor|rubygem-asciidoctor|asciidoctor|asciidoctor
dcraw|dcraw|dcraw|dcraw|dcraw
groff|groff|groff|groff|groff
wkhtmltopdf|wkhtmltopdf|-|-|wkhtmltopdf
typst|-|typst|typst|typst
weasyprint|weasyprint|weasyprint|python-weasyprint|python3-weasyprint
scour|scour|scour,python3-scour|scour|python3-scour
svgo|node-svgo|-|svgo|-
darktable-cli|darktable|darktable|darktable|darktable
rawtherapee-cli|rawtherapee|rawtherapee|rawtherapee|rawtherapee
chromium,chromium-browser,google-chrome,brave-browser|-|chromium|chromium|chromium
pdflatex|texlive-latex-base|texlive-scheme-basic|texlive-basic&texlive-latex|texlive-latex
dvisvgm|dvisvgm|texlive-dvisvgm|texlive-binextra|texlive-dvisvgm-bin
pip3|python3-pip|python3-pip|python-pip|python3-pip
gtk|python3-gi&python3-gi-cairo&gir1.2-gtk-4.0&gir1.2-adw-1|python3-gobject&gtk4&libadwaita|python-gobject&gtk4&libadwaita|python3-gobject&typelib-1_0-Gtk-4_0&typelib-1_0-Adw-1
'

PYPKGS="pillow pillow-heif pymupdf pypdf reportlab markdown openpyxl tomli-w PyYAML cairosvg fonttools brotli msgpack"

DRY=0
MANAGER=""
while [ $# -gt 0 ]; do
    case "$1" in
        -n|--dry-run) DRY=1 ;;
        --manager) shift; MANAGER="$1" ;;
        -h|--help) sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

if [ -z "$MANAGER" ]; then
    for m in apt-get dnf pacman zypper; do
        if command -v "$m" >/dev/null 2>&1; then MANAGER="$m"; break; fi
    done
    [ "$MANAGER" = "apt-get" ] && MANAGER=apt
fi
case "$MANAGER" in
    apt) COL=2 ;; dnf) COL=3 ;; pacman) COL=4 ;; zypper) COL=5 ;;
    *) echo "no supported package manager found (apt, dnf, pacman, zypper)." >&2
       echo "install ffmpeg, imagemagick, ghostscript, poppler, pandoc, libreoffice and the GTK 4 / libadwaita Python bindings by hand." >&2
       exit 1 ;;
esac

SUDO=""
[ "$(id -u)" -ne 0 ] && SUDO="sudo"

say() { printf '%s\n' "$*"; }
run() {
    if [ "$DRY" -eq 1 ]; then say "  [dry-run] $*"; return 0; fi
    "$@"
}

# ---- probes ---------------------------------------------------------------
have_tool() {
    # $1 is a comma-separated list of equivalent command names.
    old_ifs=$IFS; IFS=','
    for c in $1; do
        IFS=$old_ifs
        command -v "$c" >/dev/null 2>&1 && return 0
        IFS=','
    done
    IFS=$old_ifs
    return 1
}
have_gtk() {
    python3 - <<'PY' >/dev/null 2>&1
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk
PY
}
probe_ok() {
    case "$1" in
        gtk) have_gtk ;;
        python:*) python3 -c "import ${1#python:}" >/dev/null 2>&1 ;;
        *) have_tool "$1" ;;
    esac
}

# ---- package manager back ends --------------------------------------------
pm_refresh() {
    case "$MANAGER" in
        apt) run $SUDO apt-get update || say "  (apt-get update reported errors; continuing)" ;;
        *) : ;;
    esac
}
pm_install_batch() {
    # Best-effort batch install; returns non-zero if the manager gave up.
    case "$MANAGER" in
        apt) run $SUDO apt-get install -y --no-install-recommends "$@" ;;
        dnf)
            # dnf5 (Fedora 41+) understands --skip-unavailable; dnf4 uses strict=0.
            run $SUDO dnf install -y --skip-broken --skip-unavailable "$@" \
              || run $SUDO dnf install -y --skip-broken --setopt=strict=0 "$@" ;;
        pacman) run $SUDO pacman -S --needed --noconfirm "$@" ;;
        zypper) run $SUDO zypper --non-interactive --ignore-unknown install "$@" ;;
    esac
}
pm_install_one() {
    case "$MANAGER" in
        apt) run $SUDO apt-get install -y --no-install-recommends "$@" ;;
        dnf) run $SUDO dnf install -y --skip-broken "$@" ;;
        pacman) run $SUDO pacman -S --needed --noconfirm "$@" ;;
        zypper) run $SUDO zypper --non-interactive install "$@" ;;
    esac
}

# ---- 1. work out what is missing ------------------------------------------
MISSING=""      # "probe|pkgspec" rows still to satisfy
BATCH=""        # first alternative of every missing row, space separated
say "Package manager: $MANAGER"
say ""
LIST="${TMPDIR:-/tmp}/omniconv-missing.$$"
rm -f "$LIST"
say "Checking which backends are already present:"
printf '%s\n' "$TABLE" | while IFS='|' read -r probe apt dnf pacman zypper; do
    [ -z "$probe" ] && continue
    case "$COL" in 2) spec=$apt ;; 3) spec=$dnf ;; 4) spec=$pacman ;; 5) spec=$zypper ;; esac
    if probe_ok "$probe"; then
        printf '  present  %s\n' "${probe%%,*}"
    elif [ "$spec" = "-" ]; then
        printf '  skipped  %s (not packaged for %s)\n' "${probe%%,*}" "$MANAGER"
    else
        printf '  missing  %-16s -> %s\n' "${probe%%,*}" "$spec"
        printf '%s|%s\n' "$probe" "$spec" >> "$LIST"
    fi
done
if [ ! -s "$LIST" ]; then
    say ""
    say "Every backend the table knows about is already installed."
    rm -f "$LIST"
else
    # ---- 2. one transaction with skip flags -------------------------------
    BATCH=$(cut -d'|' -f2 "$LIST" | cut -d',' -f1 | tr '&' ' ' | tr '\n' ' ')
    say ""
    say "Installing in one transaction:"
    say "  $BATCH"
    pm_refresh
    pm_install_batch $BATCH || say "  (batch install did not complete; retrying package by package)"

    # ---- 3. retry what is still missing, one package at a time -----------
    say ""
    if [ "$DRY" -eq 1 ]; then
        say "Then, for any tool still missing after that transaction, each alternative"
        say "package name is tried on its own (not shown in a dry run)."
    else
        say "Retrying anything still missing, one package at a time:"
        RETRIED=0
        while IFS='|' read -r probe spec; do
            probe_ok "$probe" && continue
            RETRIED=1
            old_ifs=$IFS; IFS=','
            for alt in $spec; do
                IFS=$old_ifs
                pkgs=$(printf '%s' "$alt" | tr '&' ' ')
                say "  ${probe%%,*}: trying $pkgs"
                pm_install_one $pkgs
                if probe_ok "$probe"; then
                    break
                fi
                IFS=','
            done
            IFS=$old_ifs
            probe_ok "$probe" || say "  ${probe%%,*}: still missing (no package in your repositories provides it)"
        done < "$LIST"
        [ "$RETRIED" -eq 0 ] && say "  nothing left to retry"
    fi
    rm -f "$LIST"
fi

# ---- 4. Python backends ---------------------------------------------------
say ""
say "Python backends (user site-packages):"
# --break-system-packages is required on Debian, Ubuntu and Fedora for a
# user-level install alongside distribution Python packages.
run python3 -m pip install --user --break-system-packages $PYPKGS 2>/dev/null \
  || run python3 -m pip install --user $PYPKGS

# ---- 5. notes -------------------------------------------------------------
say ""
if [ "$MANAGER" = "dnf" ] && rpm -q ffmpeg-free >/dev/null 2>&1; then
    say "Note: Fedora's ffmpeg-free lacks the x264/x265 encoders, so MP4 output uses"
    say "the MPEG-4 Part 2 codec. For H.264/H.265, enable RPM Fusion and run:"
    say "  sudo dnf swap ffmpeg-free ffmpeg --allowerasing"
    say ""
fi
say "Done. Run 'omniconv doctor' to see what was detected."
