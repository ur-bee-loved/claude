"""Archives and single-file compression.

Archive-to-archive conversion extracts to a scratch directory and repacks.
Python's ``tarfile``/``zipfile``/``gzip``/``bz2``/``lzma`` modules cover the
common cases without external tools; 7-Zip handles the exotic ones and any
format that only it can create.
"""

from __future__ import annotations

import bz2
import gzip
import lzma
import os
import shutil
import stat
import tarfile
import zipfile
from pathlib import Path

from omniconv.core import formats
from omniconv.core.engine import Job
from omniconv.core.errors import ConversionError
from omniconv.core.procs import run
from omniconv.core.registry import converter
from omniconv.core.requirements import AnyOf, Module, Tool

SEVENZIP = Tool("7z", ("7za", "7zr", "7zz"), package="p7zip-full")
ZSTD = Tool("zstd", package="zstd")
LZ4 = Tool("lz4", package="lz4")
UNRAR = Tool("unrar", package="unrar")
BSDTAR = Tool("bsdtar", package="libarchive-tools")
UNAR = Tool("unar", package="unar")

_TAR_MODES = {"tar": "", "tar.gz": "gz", "tar.bz2": "bz2", "tar.xz": "xz"}
_PY_ARCHIVE = ("zip", "tar", "tar.gz", "tar.bz2", "tar.xz", "jar")
_SEVENZ_READ = ("7z", "rar", "cab", "iso", "arj", "lzh", "wim", "cpio", "ar", "deb", "rpm", "dmg", "apk", "z", "cbz", "cbr", "xps", "epub", "docx", "xlsx", "pptx", "odt", "ods", "odp")
_BSDTAR_READ = ("7z", "rar", "cab", "iso", "cpio", "ar", "deb", "xar", "lzh", "z", "cbz", "cbr", "apk")
_SEVENZ_WRITE = ("7z", "wim")
_SINGLE = ("gz", "bz2", "xz", "lzma", "zst", "lz4")


def _safe_extract_tar(tf: tarfile.TarFile, dest: Path) -> None:
    for member in tf.getmembers():
        target = (dest / member.name).resolve()
        if not str(target).startswith(str(dest.resolve()) + os.sep) and target != dest.resolve():
            raise ConversionError(f"unsafe path in archive: {member.name}")
    try:
        tf.extractall(dest, filter="data")
    except TypeError:
        tf.extractall(dest)


def _safe_extract_zip(zf: zipfile.ZipFile, dest: Path) -> None:
    for name in zf.namelist():
        target = (dest / name).resolve()
        if not str(target).startswith(str(dest.resolve()) + os.sep) and target != dest.resolve():
            raise ConversionError(f"unsafe path in archive: {name}")
    zf.extractall(dest)


def extract(source: Path, fmt: str, dest: Path, password: str | None = None) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if fmt in ("zip", "jar", "cbz", "epub", "docx", "xlsx", "pptx", "odt", "ods", "odp", "xps", "apk") and zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as zf:
            if password:
                zf.setpassword(password.encode())
            _safe_extract_zip(zf, dest)
        return
    if fmt in _TAR_MODES or (fmt in ("tar.zst",) and tarfile.is_tarfile(source)):
        with tarfile.open(source, "r:*") as tf:
            _safe_extract_tar(tf, dest)
        return
    if fmt == "tar.zst":
        exe = ZSTD.path()
        if not exe:
            raise ConversionError("zstd is required to read .tar.zst")
        tmp = dest.parent / "unzst.tar"
        run([exe, "-d", "-q", "-f", "-o", str(tmp), str(source)])
        with tarfile.open(tmp, "r:") as tf:
            _safe_extract_tar(tf, dest)
        tmp.unlink()
        return
    exe = SEVENZIP.path()
    if exe:
        cmd = [exe, "x", "-y", f"-o{dest}", str(source)]
        if password:
            cmd.insert(2, f"-p{password}")
        run(cmd)
        return
    if fmt in ("rar", "cbr") and UNRAR.available():
        run([UNRAR.path(), "x", "-y", str(source), str(dest) + os.sep])
        return
    if BSDTAR.available():
        run([BSDTAR.path(), "-xf", str(source), "-C", str(dest)])
        return
    if UNAR.available():
        run([UNAR.path(), "-q", "-o", str(dest), str(source)])
        return
    raise ConversionError(f"no tool available to extract {fmt} (install p7zip-full or libarchive-tools)")


def pack(src_dir: Path, fmt: str, target: Path, level: int | None = None) -> None:
    entries = sorted(src_dir.iterdir())
    if fmt in ("zip", "jar", "cbz"):
        comp = zipfile.ZIP_DEFLATED
        with zipfile.ZipFile(target, "w", compression=comp, compresslevel=level) as zf:
            for path in sorted(src_dir.rglob("*")):
                zf.write(path, path.relative_to(src_dir))
        return
    if fmt in _TAR_MODES:
        mode = "w:" + _TAR_MODES[fmt]
        kwargs = {}
        if level is not None and _TAR_MODES[fmt] in ("gz", "bz2"):
            kwargs["compresslevel"] = level
        if level is not None and _TAR_MODES[fmt] == "xz":
            kwargs["preset"] = level
        with tarfile.open(target, mode, **kwargs) as tf:
            for entry in entries:
                tf.add(entry, arcname=entry.name)
        return
    if fmt == "tar.zst":
        exe = ZSTD.path()
        if not exe:
            raise ConversionError("zstd is required to write .tar.zst")
        tmp = target.with_suffix(".tmp.tar")
        with tarfile.open(tmp, "w:") as tf:
            for entry in entries:
                tf.add(entry, arcname=entry.name)
        run([exe, "-q", "-f", f"-{level if level is not None else 3}", "--rm", "-o", str(target), str(tmp)])
        return
    exe = SEVENZIP.path()
    if exe and fmt in ("7z", "wim", "zip", "tar", "gz", "bz2", "xz"):
        kind = {"7z": "7z", "wim": "wim", "zip": "zip", "tar": "tar", "gz": "gzip", "bz2": "bzip2", "xz": "xz"}[fmt]
        cmd = [exe, "a", "-y", f"-t{kind}"]
        if level is not None:
            cmd.append(f"-mx={level}")
        cmd += [str(target), *[str(e) for e in entries]]
        run(cmd)
        return
    raise ConversionError(f"no tool available to create {fmt}")


def _archive_sources() -> set[str]:
    out = set(_PY_ARCHIVE) | {"cbz", "epub", "xps"}
    if ZSTD.available():
        out.add("tar.zst")
    if SEVENZIP.available():
        out.update(_SEVENZ_READ)
    if BSDTAR.available() or UNAR.available():
        out.update(_BSDTAR_READ)
    if UNRAR.available():
        out.update(("rar", "cbr"))
    return out


def _archive_targets() -> set[str]:
    out = set(_PY_ARCHIVE) | {"cbz"}
    if ZSTD.available():
        out.add("tar.zst")
    if SEVENZIP.available():
        out.update(_SEVENZ_WRITE)
    return out


@converter(
    "archive-repack",
    _archive_sources,
    _archive_targets,
    cost=10,
    options=("compress", "password"),
    description="Convert between archive formats by extracting and repacking",
    predicate=lambda s, t: s != t and not (s in ("epub", "docx", "xlsx", "pptx", "odt", "ods", "odp") and t not in ("zip", "tar", "tar.gz", "tar.bz2", "tar.xz", "tar.zst", "7z")),
)
def repack(job: Job) -> list[Path]:
    work = job.workdir / "unpacked"
    extract(job.source, job.src_format.name, work, job.opt("password"))
    level = job.opt("compress")
    pack(work, job.tgt_format.name, job.target, int(level) if level is not None else None)
    shutil.rmtree(work, ignore_errors=True)
    return [job.target]


def _open_compressed(path: Path, fmt: str):
    if fmt == "gz":
        return gzip.open(path, "rb")
    if fmt == "bz2":
        return bz2.open(path, "rb")
    if fmt in ("xz", "lzma"):
        return lzma.open(path, "rb")
    raise ConversionError(f"unsupported: {fmt}")


def _decompress_to(source: Path, fmt: str, dest: Path) -> None:
    if fmt in ("gz", "bz2", "xz", "lzma"):
        with _open_compressed(source, fmt) as src, open(dest, "wb") as dst:
            shutil.copyfileobj(src, dst)
    elif fmt == "zst":
        exe = ZSTD.path()
        if not exe:
            raise ConversionError("zstd is required")
        run([exe, "-d", "-q", "-f", "-o", str(dest), str(source)])
    elif fmt == "lz4":
        exe = LZ4.path()
        if not exe:
            raise ConversionError("lz4 is required")
        run([exe, "-d", "-q", "-f", str(source), str(dest)])
    elif fmt == "z":
        exe = SEVENZIP.path()
        if not exe:
            raise ConversionError("7z is required for .Z")
        run([exe, "e", "-y", f"-o{dest.parent}", f"-so", str(source)], check=True)


def _compress_from(source: Path, fmt: str, dest: Path, level: int | None) -> None:
    if fmt == "gz":
        with open(source, "rb") as src, gzip.open(dest, "wb", compresslevel=level if level is not None else 6) as dst:
            shutil.copyfileobj(src, dst)
    elif fmt == "bz2":
        with open(source, "rb") as src, bz2.open(dest, "wb", compresslevel=level if level is not None else 9) as dst:
            shutil.copyfileobj(src, dst)
    elif fmt in ("xz", "lzma"):
        fmt_id = lzma.FORMAT_XZ if fmt == "xz" else lzma.FORMAT_ALONE
        with open(source, "rb") as src, lzma.open(dest, "wb", format=fmt_id, preset=level if level is not None else 6) as dst:
            shutil.copyfileobj(src, dst)
    elif fmt == "zst":
        exe = ZSTD.path()
        if not exe:
            raise ConversionError("zstd is required")
        run([exe, "-q", "-f", f"-{level if level is not None else 3}", "-o", str(dest), str(source)])
    elif fmt == "lz4":
        exe = LZ4.path()
        if not exe:
            raise ConversionError("lz4 is required")
        run([exe, "-q", "-f", f"-{level if level is not None else 1}", str(source), str(dest)])
    else:
        raise ConversionError(f"unsupported: {fmt}")


def _single_formats() -> set[str]:
    out = {"gz", "bz2", "xz", "lzma"}
    if ZSTD.available():
        out.add("zst")
    if LZ4.available():
        out.add("lz4")
    return out


@converter(
    "recompress",
    lambda: _single_formats() | ({"z"} if SEVENZIP.available() else set()),
    _single_formats,
    cost=8,
    options=("compress",),
    description="Change single-file compression (gz, bz2, xz, lzma, zst, lz4)",
    predicate=lambda s, t: s != t,
)
def recompress(job: Job) -> list[Path]:
    raw = job.workdir / "raw.bin"
    _decompress_to(job.source, job.src_format.name, raw)
    level = job.opt("compress")
    _compress_from(raw, job.tgt_format.name, job.target, int(level) if level is not None else None)
    raw.unlink(missing_ok=True)
    return [job.target]


def _everything() -> set[str]:
    return {f.name for f in formats.all_formats()}


@converter(
    "compress-file",
    _everything,
    lambda: _single_formats() | {"zip", "tar", "tar.gz", "tar.bz2", "tar.xz", "7z"} - ({"7z"} if not SEVENZIP.available() else set()),
    cost=45,
    options=("compress",),
    description="Compress any single file into an archive or compressed stream",
    predicate=lambda s, t: formats.get(s).category != "archive",
)
def compress_file(job: Job) -> list[Path]:
    tgt = job.tgt_format.name
    level = job.opt("compress")
    lvl = int(level) if level is not None else None
    if tgt in _SINGLE:
        _compress_from(job.source, tgt, job.target, lvl)
        return [job.target]
    staging = job.workdir / "staging"
    staging.mkdir()
    shutil.copy2(job.source, staging / job.source.name)
    pack(staging, tgt, job.target, lvl)
    return [job.target]


@converter(
    "archive-files",
    _everything,
    lambda: {"zip", "tar", "tar.gz", "tar.bz2", "tar.xz", "cbz"} | ({"7z", "tar.zst"} if SEVENZIP.available() and ZSTD.available() else set()),
    cost=12,
    many_to_one=True,
    options=("compress",),
    description="Bundle several files into one archive",
)
def archive_files(job: Job) -> list[Path]:
    staging = job.workdir / "staging"
    staging.mkdir()
    for src in job.sources:
        dest = staging / src.name
        n = 1
        while dest.exists():
            dest = staging / f"{src.stem} ({n}){src.suffix}"
            n += 1
        shutil.copy2(src, dest)
    level = job.opt("compress")
    pack(staging, job.tgt_format.name, job.target, int(level) if level is not None else None)
    return [job.target]


@converter(
    "unpack-single",
    lambda: _single_formats() | ({"z"} if SEVENZIP.available() else set()),
    lambda: {f.name for f in formats.all_formats() if f.category != "archive"},
    cost=9,
    description="Decompress a single-file stream (file.pdf.gz -> file.pdf)",
    predicate=lambda s, t: True,
)
def unpack_single(job: Job) -> list[Path]:
    _decompress_to(job.source, job.src_format.name, job.target)
    return [job.target]
