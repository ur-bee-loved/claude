"""Small subprocess wrapper shared by all command-line backends."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Sequence

from omniconv.core.errors import ConversionError

DEFAULT_TIMEOUT = 1800


def run(
    cmd: Sequence[str | os.PathLike[str]],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: float | None = DEFAULT_TIMEOUT,
    stdin_data: bytes | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    """Run ``cmd`` and raise ``ConversionError`` with the captured stderr
    when it exits non-zero. ``env`` entries are merged over ``os.environ``."""
    argv = [os.fspath(a) for a in cmd]
    merged_env = None
    if env:
        merged_env = dict(os.environ)
        merged_env.update(env)
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            env=merged_env,
            input=stdin_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ConversionError(f"command not found: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ConversionError(f"command timed out after {timeout}s: {argv[0]}") from exc
    if check and proc.returncode != 0:
        raise ConversionError(
            f"{argv[0]} exited with status {proc.returncode}",
            stderr=proc.stderr.decode("utf-8", "replace"),
        )
    return proc


def output_text(cmd: Sequence[str | os.PathLike[str]], **kwargs) -> str:
    return run(cmd, **kwargs).stdout.decode("utf-8", "replace")
