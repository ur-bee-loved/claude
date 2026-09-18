"""The tool finder, exercised with a simulated Windows layout on any OS."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from omniconv.core import platform


@pytest.fixture
def fake_windows(tmp_path, monkeypatch):
    """Pretend to be Windows with Program Files under ``tmp_path``."""
    pf = tmp_path / "Program Files"
    pf.mkdir()
    monkeypatch.setattr(platform, "IS_WINDOWS", True)
    monkeypatch.setattr(platform, "IS_MAC", False)
    monkeypatch.setenv("ProgramFiles", str(pf))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "missing-x86"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("ProgramData", str(tmp_path / "programdata"))
    monkeypatch.setattr(platform, "_WINDOWS_ROOTS", ("%ProgramFiles%", "%ProgramFiles(x86)%", "%LOCALAPPDATA%\\Programs", "%LOCALAPPDATA%", "%ProgramData%"))
    monkeypatch.setattr(platform, "_WINDOWS_EXTRA_DIRS", (str(tmp_path / "shims"),))
    # An empty PATH, so that tools really installed on the test machine
    # cannot satisfy a lookup that should come from the simulated layout.
    (tmp_path / "emptybin").mkdir()
    monkeypatch.setenv("PATH", str(tmp_path / "emptybin"))
    platform.reset_cache()
    yield pf
    platform.reset_cache()


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"MZ")
    return path


def _shim(directory: Path, name: str) -> tuple[Path, Path]:
    """Create ``name`` and ``name.exe`` side by side: ``shutil.which`` on
    Windows only matches names with a PATHEXT extension, on Linux only the
    bare name, and the tests must hold on both."""
    bare = _touch(directory / name)
    bare.chmod(0o755)
    exe = _touch(directory / f"{name}.exe")
    exe.chmod(0o755)
    return bare, exe


def test_expand_handles_windows_style_variables(monkeypatch):
    monkeypatch.setenv("OMNI_TEST_VAR", "value")
    assert platform._expand("%OMNI_TEST_VAR%/x") == "value/x"
    assert platform._expand("%OMNI_UNSET_VAR%/x") == ""


def test_known_install_directory_is_found(fake_windows):
    exe = _touch(fake_windows / "LibreOffice" / "program" / "soffice.com")
    assert platform.find_executable("soffice") == str(exe)


def test_newest_versioned_directory_wins(fake_windows):
    _touch(fake_windows / "gs" / "gs9.56" / "bin" / "gswin64c.exe")
    newest = _touch(fake_windows / "gs" / "gs10.03" / "bin" / "gswin64c.exe")
    # "gs" is what the backends ask for; Windows names it gswin64c.
    assert platform.find_executable("gs") == str(newest)


def test_convert_is_never_looked_up_on_windows(fake_windows, tmp_path, monkeypatch):
    # A "convert" on PATH (the NTFS filesystem converter on Windows, or
    # ImageMagick 6 on Linux) must never be used.
    bindir = tmp_path / "system32"
    _shim(bindir, "convert")
    monkeypatch.setenv("PATH", str(bindir))
    platform.reset_cache()
    assert shutil.which("convert") is not None
    assert platform.find_executable("convert") is None


def test_shim_directory_is_searched(fake_windows, tmp_path):
    shims = tmp_path / "shims"
    bare, exe = _shim(shims, "qpdf")
    assert shutil.which("qpdf") is None
    assert platform.find_executable("qpdf") in (str(bare), str(exe))


def test_version_key_orders_numerically():
    names = ["gs9.56", "gs10.03", "gs10.02", "gs8.71"]
    assert sorted(names, key=platform._version_key) == ["gs8.71", "gs9.56", "gs10.02", "gs10.03"]


def test_missing_tool_returns_none(fake_windows):
    assert platform.find_executable("definitely-not-a-tool-xyz") is None


def test_native_lookup_agrees_with_which():
    platform.reset_cache()
    # python is on PATH wherever the tests run; the finder must agree.
    name = "python" if platform.IS_WINDOWS else "python3"
    assert platform.find_executable(name) == shutil.which(name)
    kwargs = platform.hidden_console_kwargs()
    assert (kwargs == {}) != platform.IS_WINDOWS
