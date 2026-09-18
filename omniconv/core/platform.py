"""Locating external tools on each operating system.

On Linux a tool is either on ``PATH`` or absent, and ``shutil.which`` is
the whole story. Windows is different in three ways that this module
absorbs so the backends do not have to know about them:

* Installers put binaries under *Program Files* and only some of them add
  the directory to ``PATH`` (LibreOffice, calibre, Ghostscript, Tesseract
  and 7-Zip do not). The table below lists where each tool lands, with
  globs for version-numbered directories.
* Some executables carry different names: Ghostscript's console binary is
  ``gswin64c.exe``; ImageMagick 6's ``convert`` must never be tried because
  ``C:\\Windows\\System32\\convert.exe`` is the NTFS filesystem converter.
* Windows keeps an *App Paths* registry key for many applications, which
  gives a location even for tools installed somewhere unusual.

macOS gets the same treatment in miniature: Homebrew prefixes and the
bundle paths of the few applications that ship a command-line tool.
"""

from __future__ import annotations

import functools
import glob
import os
import shutil
import sys
from pathlib import Path

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

# Names that must not be looked up on Windows because a system utility of
# the same name would be found instead.
WINDOWS_FORBIDDEN = frozenset({"convert", "timeout", "find", "sort", "expand", "print"})

# Linux tool name -> names to try on Windows, in order.
WINDOWS_NAMES: dict[str, tuple[str, ...]] = {
    "gs": ("gswin64c", "gswin32c", "gs"),
    "chromium": ("chrome", "msedge", "brave", "chromium"),
    "python3": ("python", "py"),
    "7z": ("7z", "7za", "7zr", "7zz"),
    "soffice": ("soffice", "soffice.com"),
}

# Directories searched after PATH on Windows. Package managers that install
# portable tools put shims here, and MSYS2 provides most of the small Unix
# utilities (sox, potrace, rsvg-convert, optipng, ...).
_WINDOWS_EXTRA_DIRS = (
    r"%LOCALAPPDATA%\Microsoft\WinGet\Links",
    r"%ProgramData%\chocolatey\bin",
    r"%USERPROFILE%\scoop\shims",
    r"C:\msys64\ucrt64\bin",
    r"C:\msys64\mingw64\bin",
    r"C:\msys64\usr\bin",
    r"C:\tools",
)

# Tool name -> glob patterns relative to each of the roots below. The last
# match in sorted order wins, which picks the newest version-numbered dir.
_WINDOWS_ROOTS = ("%ProgramFiles%", "%ProgramFiles(x86)%", "%LOCALAPPDATA%\\Programs", "%LOCALAPPDATA%", "%ProgramData%", "C:\\")
_WINDOWS_KNOWN: dict[str, tuple[str, ...]] = {
    # soffice.com stays attached to the console and waits for the conversion; soffice.exe may return early.
    "soffice": (r"LibreOffice\program\soffice.com", r"LibreOffice\program\soffice.exe", r"LibreOffice*\program\soffice.com", r"LibreOffice*\program\soffice.exe"),
    "ebook-convert": (r"Calibre2\ebook-convert.exe", r"Calibre\ebook-convert.exe"),
    "gswin64c": (r"gs\gs*\bin\gswin64c.exe",),
    "gswin32c": (r"gs\gs*\bin\gswin32c.exe",),
    "tesseract": (r"Tesseract-OCR\tesseract.exe",),
    "inkscape": (r"Inkscape\bin\inkscape.exe", r"Inkscape\inkscape.exe"),
    "7z": (r"7-Zip\7z.exe",),
    "dot": (r"Graphviz\bin\dot.exe", r"Graphviz*\bin\dot.exe"),
    "magick": (r"ImageMagick*\magick.exe",),
    "pandoc": (r"Pandoc\pandoc.exe",),
    "ffmpeg": (r"ffmpeg\bin\ffmpeg.exe", r"ffmpeg*\bin\ffmpeg.exe"),
    "ffprobe": (r"ffmpeg\bin\ffprobe.exe", r"ffmpeg*\bin\ffprobe.exe"),
    "pdftoppm": (r"poppler*\Library\bin\pdftoppm.exe", r"poppler*\bin\pdftoppm.exe"),
    "pdftotext": (r"poppler*\Library\bin\pdftotext.exe", r"poppler*\bin\pdftotext.exe"),
    "pdftohtml": (r"poppler*\Library\bin\pdftohtml.exe", r"poppler*\bin\pdftohtml.exe"),
    "pdftocairo": (r"poppler*\Library\bin\pdftocairo.exe", r"poppler*\bin\pdftocairo.exe"),
    "pdfimages": (r"poppler*\Library\bin\pdfimages.exe", r"poppler*\bin\pdfimages.exe"),
    "pdfseparate": (r"poppler*\Library\bin\pdfseparate.exe", r"poppler*\bin\pdfseparate.exe"),
    "pdfunite": (r"poppler*\Library\bin\pdfunite.exe", r"poppler*\bin\pdfunite.exe"),
    "qpdf": (r"qpdf*\bin\qpdf.exe",),
    "potrace": (r"potrace*\potrace.exe",),
    "sox": (r"sox-*\sox.exe",),
    "fontforge": (r"FontForgeBuilds\bin\fontforge.exe",),
    "chrome": (r"Google\Chrome\Application\chrome.exe",),
    "msedge": (r"Microsoft\Edge\Application\msedge.exe",),
    "brave": (r"BraveSoftware\Brave-Browser\Application\brave.exe",),
    "wkhtmltopdf": (r"wkhtmltopdf\bin\wkhtmltopdf.exe",),
    "wkhtmltoimage": (r"wkhtmltopdf\bin\wkhtmltoimage.exe",),
    "timidity": (r"TiMidity++\timidity.exe", r"timidity\timidity.exe"),
    "fluidsynth": (r"fluidsynth*\bin\fluidsynth.exe", r"FluidSynth\bin\fluidsynth.exe"),
    "assimp": (r"Assimp\bin\x64\assimp.exe", r"Assimp\bin\assimp.exe"),
    "darktable-cli": (r"darktable\bin\darktable-cli.exe",),
    "rawtherapee-cli": (r"RawTherapee*\rawtherapee-cli.exe",),
    "pdflatex": (r"MiKTeX\miktex\bin\x64\pdflatex.exe", r"texlive\*\bin\windows\pdflatex.exe", r"texlive\*\bin\win32\pdflatex.exe"),
    "dvisvgm": (r"MiKTeX\miktex\bin\x64\dvisvgm.exe", r"texlive\*\bin\windows\dvisvgm.exe"),
    "ddjvu": (r"DjVuLibre\ddjvu.exe",),
    "djvutxt": (r"DjVuLibre\djvutxt.exe",),
    "typst": (r"typst\typst.exe",),
    "cwebp": (r"libwebp*\bin\cwebp.exe",),
    "dwebp": (r"libwebp*\bin\dwebp.exe",),
    "gif2webp": (r"libwebp*\bin\gif2webp.exe",),
    "cjxl": (r"jxl*\cjxl.exe", r"libjxl*\cjxl.exe"),
    "djxl": (r"jxl*\djxl.exe", r"libjxl*\djxl.exe"),
    "exiftool": (r"exiftool*\exiftool.exe",),
}

_MAC_EXTRA_DIRS = ("/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin", "/Library/TeX/texbin")
_MAC_KNOWN: dict[str, tuple[str, ...]] = {
    "soffice": ("/Applications/LibreOffice.app/Contents/MacOS/soffice",),
    "ebook-convert": ("/Applications/calibre.app/Contents/MacOS/ebook-convert",),
    "inkscape": ("/Applications/Inkscape.app/Contents/MacOS/inkscape",),
    "chromium": ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Chromium.app/Contents/MacOS/Chromium", "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
    "darktable-cli": ("/Applications/darktable.app/Contents/MacOS/darktable-cli",),
    "rawtherapee-cli": ("/Applications/RawTherapee.app/Contents/MacOS/rawtherapee-cli",),
    "fontforge": ("/Applications/FontForge.app/Contents/Resources/opt/local/bin/fontforge",),
}


_PERCENT_VAR = __import__("re").compile(r"%([^%]+)%")


def _expand(pattern: str) -> str:
    """Expand ``%NAME%`` (Windows style) and ``$NAME`` variables and ``~``.
    ``os.path.expandvars`` only understands ``%NAME%`` on Windows itself;
    doing it here keeps the lookup testable on any platform."""
    expanded = _PERCENT_VAR.sub(lambda m: os.environ.get(m.group(1), m.group(0)), pattern)
    if "%" in expanded:
        return ""
    return os.path.expandvars(os.path.expanduser(expanded))


def _candidates(name: str) -> tuple[str, ...]:
    if IS_WINDOWS:
        return WINDOWS_NAMES.get(name, (name,))
    return (name,)


def _registry_app_path(exe: str) -> str | None:
    """Windows keeps ``HKLM/HKCU\\...\\App Paths\\<exe>.exe`` for many
    installed programs. Returns the recorded path if it exists."""
    if not IS_WINDOWS:
        return None
    try:
        import winreg  # type: ignore[import-not-found]
    except ImportError:
        return None
    key_name = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}.exe"
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, key_name) as key:
                value, _ = winreg.QueryValueEx(key, None)
                value = os.path.expandvars(str(value)).strip('"')
                if value and os.path.isfile(value):
                    return value
        except OSError:
            continue
    return None


def _registry_special(name: str) -> str | None:
    """A few applications record their install directory under their own key."""
    if not IS_WINDOWS:
        return None
    try:
        import winreg  # type: ignore[import-not-found]
    except ImportError:
        return None
    probes: list[tuple[str, str | None, str]] = []
    if name in ("gswin64c", "gswin32c"):
        # HKLM\SOFTWARE\GPL Ghostscript\<version>\GS_DLL -> <dir>\bin\gsdll64.dll
        for root_name in (r"SOFTWARE\GPL Ghostscript", r"SOFTWARE\Artifex Ghostscript"):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root_name) as root:
                    versions = []
                    i = 0
                    while True:
                        try:
                            versions.append(winreg.EnumKey(root, i))
                            i += 1
                        except OSError:
                            break
                    for version in sorted(versions, reverse=True):
                        with winreg.OpenKey(root, version) as vkey:
                            dll, _ = winreg.QueryValueEx(vkey, "GS_DLL")
                            exe = os.path.join(os.path.dirname(str(dll)), name + ".exe")
                            if os.path.isfile(exe):
                                return exe
            except OSError:
                continue
    if name == "soffice":
        probes.append((r"SOFTWARE\LibreOffice\UNO\InstallPath", None, r"program\soffice.exe"))
    for key_name, value_name, suffix in probes:
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(root, key_name) as key:
                    value, _ = winreg.QueryValueEx(key, value_name)
                    exe = os.path.join(str(value), suffix) if suffix else str(value)
                    if os.path.isfile(exe):
                        return exe
            except OSError:
                continue
    return None


def _search_known(name: str) -> str | None:
    if IS_WINDOWS:
        patterns = _WINDOWS_KNOWN.get(name, ())
        roots = _WINDOWS_ROOTS
    elif IS_MAC:
        for path in _MAC_KNOWN.get(name, ()):
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
        return None
    else:
        return None
    found: list[str] = []
    for root in roots:
        base = _expand(root)
        if not base or not os.path.isdir(base):
            continue
        for pattern in patterns:
            found.extend(glob.glob(os.path.join(base, pattern.replace("\\", os.sep))))
    found = [f for f in found if os.path.isfile(f)]
    if not found:
        return None
    return sorted(found, key=_version_key)[-1]


def _version_key(path: str) -> list:
    """Sort key that orders embedded numbers numerically, so ``gs10.03``
    comes after ``gs9.56`` rather than before it."""
    import re

    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path)]


def _extra_dirs() -> list[str]:
    raw = _WINDOWS_EXTRA_DIRS if IS_WINDOWS else _MAC_EXTRA_DIRS if IS_MAC else ()
    return [d for d in (_expand(p) for p in raw) if os.path.isdir(d)]


@functools.lru_cache(maxsize=None)
def find_executable(name: str) -> str | None:
    """Return the full path of tool ``name`` or ``None``.

    Search order: PATH, then package-manager shim directories, then the
    known install locations for the tool, then the Windows registry.
    Results are cached; call ``reset_cache`` after installing something.
    """
    for candidate in _candidates(name):
        if IS_WINDOWS and candidate in WINDOWS_FORBIDDEN:
            continue
        found = shutil.which(candidate)
        if found:
            return found
        for directory in _extra_dirs():
            found = shutil.which(candidate, path=directory)
            if found:
                return found
        found = _search_known(candidate)
        if found:
            return found
        found = _registry_app_path(candidate) or _registry_special(candidate)
        if found:
            return found
    return None


def reset_cache() -> None:
    find_executable.cache_clear()


def hidden_console_kwargs() -> dict:
    """Extra ``subprocess`` arguments that stop a console window flashing
    up for every external tool when the GUI runs on Windows."""
    if not IS_WINDOWS:
        return {}
    import subprocess

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return {"creationflags": subprocess.CREATE_NO_WINDOW, "startupinfo": startupinfo}


def open_in_file_manager(path: Path) -> None:
    """Reveal a folder in the platform's file manager."""
    import subprocess

    if IS_WINDOWS:
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif IS_MAC:
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def user_data_dir(app: str = "omniconv") -> Path:
    if IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
        return Path(base) / app
    if IS_MAC:
        return Path.home() / "Library" / "Application Support" / app
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / app
