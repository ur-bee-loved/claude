"""Declarative dependency checks.

Every converter declares what it needs as a tuple of ``Requirement`` objects.
The registry evaluates them lazily and caches the result, so listing formats
is cheap and a missing backend never raises at import time.
"""

from __future__ import annotations

import functools
import importlib.util
import shutil
from dataclasses import dataclass


class Requirement:
    def available(self) -> bool:  # pragma: no cover - abstract
        raise NotImplementedError

    def describe(self) -> str:  # pragma: no cover - abstract
        raise NotImplementedError

    def hint(self) -> str:
        return ""


@functools.lru_cache(maxsize=None)
def _which(name: str) -> str | None:
    return shutil.which(name)


@functools.lru_cache(maxsize=None)
def _has_module(name: str) -> bool:
    try:
        if importlib.util.find_spec(name) is None:
            return False
    except (ImportError, ValueError):
        return False
    try:
        importlib.import_module(name)
    except Exception:
        return False
    return True


@dataclass(frozen=True)
class Tool(Requirement):
    """An executable on ``PATH``. ``alternatives`` lists equivalent names
    (for example ImageMagick 7 ships ``magick`` while 6 ships ``convert``)."""

    name: str
    alternatives: tuple[str, ...] = ()
    package: str = ""

    def path(self) -> str | None:
        for candidate in (self.name, *self.alternatives):
            found = _which(candidate)
            if found:
                return found
        return None

    def available(self) -> bool:
        return self.path() is not None

    def describe(self) -> str:
        return f"command '{self.name}'"

    def hint(self) -> str:
        return f"install package '{self.package}'" if self.package else ""


@dataclass(frozen=True)
class Module(Requirement):
    """An importable Python module. ``pip`` is the distribution name."""

    name: str
    pip: str = ""

    def available(self) -> bool:
        return _has_module(self.name)

    def describe(self) -> str:
        return f"python module '{self.name}'"

    def hint(self) -> str:
        return f"pip install {self.pip or self.name}"


@dataclass(frozen=True)
class AnyOf(Requirement):
    """Satisfied when at least one of the alternatives is available."""

    alternatives: tuple[Requirement, ...]

    def available(self) -> bool:
        return any(r.available() for r in self.alternatives)

    def describe(self) -> str:
        return " or ".join(r.describe() for r in self.alternatives)

    def hint(self) -> str:
        return "; ".join(h for h in (r.hint() for r in self.alternatives) if h)


def reset_cache() -> None:
    _which.cache_clear()
    _has_module.cache_clear()
