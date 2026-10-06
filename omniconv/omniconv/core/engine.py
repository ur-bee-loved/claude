"""Execution engine: turns a route into files on disk."""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from omniconv.core import formats, sniff
from omniconv.core.errors import ConversionError, NoRouteError, OmniconvError, UnknownFormatError
from omniconv.core.formats import Format
from omniconv.core.options import coerce_options
from omniconv.core.registry import REGISTRY, Converter, Registry, Route, Step

Logger = Callable[[str], None]


@dataclass
class Job:
    """Everything a converter needs for one step of a route."""

    source: Path
    target: Path
    src_format: Format
    tgt_format: Format
    options: dict[str, Any]
    workdir: Path
    log: Logger = lambda msg: None
    sources: list[Path] = field(default_factory=list)  # for many-to-one converters

    def opt(self, name: str, default: Any = None) -> Any:
        value = self.options.get(name)
        return default if value is None else value

    def numbered(self, index: int, total: int) -> Path:
        """Output path for the ``index``-th of ``total`` outputs (0-based)."""
        width = max(len(str(total)), 1)
        return self.target.with_name(f"{self.target.stem}-{index + 1:0{width}d}{self.target.suffix}")

    def scratch(self, suffix: str) -> Path:
        """A fresh file path inside the job's scratch directory."""
        fd, name = tempfile.mkstemp(suffix=suffix, dir=self.workdir)
        os.close(fd)
        os.unlink(name)
        return Path(name)


@dataclass
class Result:
    source: Path
    target_format: Format | None
    outputs: list[Path] = field(default_factory=list)
    route: Route = field(default_factory=list)
    seconds: float = 0.0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def route_text(self) -> str:
        if not self.route:
            return "-"
        return self.route[0].src + "".join(f" -({s.name})-> {s.tgt}" for s in self.route)


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for n in range(1, 10000):
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise ConversionError(f"cannot find a free name for {path}")


def detect_format(path: Path) -> Format:
    fmt = sniff.detect(path)
    if fmt is None:
        raise UnknownFormatError(f"cannot determine the format of {path}")
    return fmt


class Engine:
    def __init__(self, registry: Registry | None = None, temp_root: Path | None = None) -> None:
        self.registry = registry or REGISTRY
        self.temp_root = temp_root

    # ------------------------------------------------------------- planning
    def plan(self, src: Format | str, tgt: Format | str) -> Route:
        src_f = src if isinstance(src, Format) else formats.get(src)
        tgt_f = tgt if isinstance(tgt, Format) else formats.get(tgt)
        route = self.registry.find_route(src_f.name, tgt_f.name)
        if route is None:
            raise NoRouteError(self._no_route_message(src_f, tgt_f))
        return route

    def _no_route_message(self, src_f: Format, tgt_f: Format) -> str:
        msg = f"no available converter chain from {src_f.name} to {tgt_f.name}"
        missing = self.registry.candidates_needing_install(src_f.name, tgt_f.name)
        if missing:
            hints = []
            for conv in missing[:3]:
                needs = "; ".join(f"{r.describe()} ({r.hint()})" if r.hint() else r.describe() for r in conv.missing())
                hints.append(f"{conv.name} would work if you install: {needs}")
            msg += "\n" + "\n".join("  " + h for h in hints)
        return msg

    def targets_for(self, src: Format | str) -> list[Format]:
        src_f = src if isinstance(src, Format) else formats.get(src)
        names = self.registry.reachable(src_f.name)
        return sorted((formats.FORMATS[n] for n in names), key=lambda f: (f.category, f.name))

    # ------------------------------------------------------------ execution
    def convert(
        self,
        source: Path | str,
        target: Format | str | None = None,
        *,
        output: Path | str | None = None,
        output_dir: Path | str | None = None,
        options: dict[str, Any] | None = None,
        on_conflict: str = "rename",
        log: Logger | None = None,
        backend: str | None = None,
    ) -> Result:
        """Convert one file. Exactly one of ``target`` (a format name) or
        ``output`` (a path whose extension names the format) is required.
        ``backend`` forces a single named converter instead of the cheapest
        route (used for split/extract operations and for comparisons)."""
        source = Path(source)
        log = log or (lambda msg: None)
        started = time.monotonic()
        result = Result(source=source, target_format=None)
        try:
            if not source.is_file():
                raise OmniconvError(f"not a file: {source}")
            src_f = detect_format(source)
            if output is not None:
                output = Path(output)
                tgt_f = formats.by_extension(output) if target is None else (target if isinstance(target, Format) else formats.get(target))
                if tgt_f is None:
                    raise UnknownFormatError(f"cannot infer target format from {output}")
                final = output
            else:
                if target is None:
                    raise OmniconvError("a target format or output path is required")
                tgt_f = target if isinstance(target, Format) else formats.get(target)
                final = formats.output_path(source, tgt_f, Path(output_dir) if output_dir else None)
            result.target_format = tgt_f
            route = self._forced(backend, src_f, tgt_f) if backend else self.plan(src_f, tgt_f)
            result.route = route
            final = self._resolve_conflict(final, source, on_conflict)
            final.parent.mkdir(parents=True, exist_ok=True)
            opts = coerce_options(options or {})
            result.outputs = self._run_route(route, source, src_f, tgt_f, final, opts, log)
        except OmniconvError as exc:
            result.error = str(exc)
        except Exception as exc:  # backend bug or unexpected failure
            result.error = f"{type(exc).__name__}: {exc}"
        result.seconds = time.monotonic() - started
        return result

    def _forced(self, backend: str, src_f: Format, tgt_f: Format) -> Route:
        for conv in self.registry.all():
            if conv.name == backend:
                if not conv.available():
                    needs = ", ".join(r.describe() for r in conv.missing())
                    raise NoRouteError(f"backend {backend} is not available (needs {needs})")
                if not conv.supports(src_f.name, tgt_f.name):
                    raise NoRouteError(f"backend {backend} does not convert {src_f.name} to {tgt_f.name}")
                return [Step(conv, src_f.name, tgt_f.name)]
        raise NoRouteError(f"unknown backend: {backend}")

    def _resolve_conflict(self, final: Path, source: Path, on_conflict: str) -> Path:
        if final.resolve() == source.resolve():
            # Never clobber the input; in-place conversions get a new name.
            return unique_path(final)
        if not final.exists():
            return final
        if on_conflict == "overwrite":
            return final
        if on_conflict == "error":
            raise OmniconvError(f"output exists: {final}")
        return unique_path(final)

    def _run_route(
        self,
        route: Route,
        source: Path,
        src_f: Format,
        tgt_f: Format,
        final: Path,
        opts: dict[str, Any],
        log: Logger,
    ) -> list[Path]:
        workdir = Path(tempfile.mkdtemp(prefix="omniconv-", dir=self.temp_root))
        try:
            inputs = [source]
            last = len(route) - 1
            outputs: list[Path] = []
            for index, step in enumerate(route):
                step_src = formats.FORMATS[step.src]
                step_tgt = formats.FORMATS[step.tgt]
                step_outputs: list[Path] = []
                for n, path in enumerate(inputs):
                    if index == last:
                        target = final if len(inputs) == 1 else final.with_name(f"{final.stem}-{n + 1:03d}{final.suffix}")
                    else:
                        target = workdir / f"step{index}-{n}.{step_tgt.extension}"
                    job = Job(path, target, step_src, step_tgt, opts, workdir, log)
                    log(f"[{step.name}] {step.src} -> {step.tgt}: {path.name}")
                    produced = step.conv.run(job)
                    for p in produced:
                        if not p.exists():
                            raise ConversionError(f"{step.name} reported {p} but the file is missing")
                    step_outputs.extend(produced)
                inputs = step_outputs
                outputs = step_outputs
            return outputs
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    def convert_many(
        self,
        sources: Iterable[Path | str],
        target: Format | str,
        *,
        output_dir: Path | str | None = None,
        options: dict[str, Any] | None = None,
        on_conflict: str = "rename",
        workers: int = 2,
        progress: Callable[[Result], None] | None = None,
        log: Logger | None = None,
        backend: str | None = None,
    ) -> list[Result]:
        sources = [Path(s) for s in sources]
        results: list[Result | None] = [None] * len(sources)
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {
                pool.submit(
                    self.convert, src, target, output_dir=output_dir, options=options, on_conflict=on_conflict, log=log, backend=backend
                ): i
                for i, src in enumerate(sources)
            }
            for fut in as_completed(futures):
                res = fut.result()
                results[futures[fut]] = res
                if progress:
                    progress(res)
        return [r for r in results if r is not None]

    def merge(
        self,
        sources: Sequence[Path | str],
        output: Path | str,
        *,
        options: dict[str, Any] | None = None,
        on_conflict: str = "rename",
        log: Logger | None = None,
    ) -> Result:
        """Combine several inputs into one output (images -> PDF, PDFs -> PDF,
        files -> archive). Inputs that are not directly mergeable are first
        converted to a mergeable intermediate."""
        sources = [Path(s) for s in sources]
        output = Path(output)
        log = log or (lambda msg: None)
        started = time.monotonic()
        result = Result(source=sources[0] if sources else Path("."), target_format=None)
        try:
            if not sources:
                raise OmniconvError("nothing to merge")
            tgt_f = formats.by_extension(output)
            if tgt_f is None:
                raise UnknownFormatError(f"cannot infer target format from {output}")
            result.target_format = tgt_f
            src_fs = [detect_format(s) for s in sources]
            merger = self._pick_merger(src_fs, tgt_f)
            final = self._resolve_conflict(output, sources[0], on_conflict)
            final.parent.mkdir(parents=True, exist_ok=True)
            opts = coerce_options(options or {})
            workdir = Path(tempfile.mkdtemp(prefix="omniconv-", dir=self.temp_root))
            try:
                prepared: list[Path] = []
                for src, fmt in zip(sources, src_fs):
                    if merger.supports(fmt.name, tgt_f.name):
                        prepared.append(src)
                        continue
                    # Convert into one of the merger's accepted formats first.
                    inter = self._best_intermediate(fmt, merger, tgt_f)
                    sub = self.convert(src, inter, output_dir=workdir, options=opts, on_conflict="rename", log=log)
                    if not sub.ok:
                        raise ConversionError(f"{src.name}: {sub.error}")
                    prepared.extend(sub.outputs)
                job = Job(prepared[0], final, detect_format(prepared[0]), tgt_f, opts, workdir, log, sources=prepared)
                result.route = [Step(merger, detect_format(prepared[0]).name, tgt_f.name)]
                result.outputs = merger.run(job)
            finally:
                shutil.rmtree(workdir, ignore_errors=True)
        except OmniconvError as exc:
            result.error = str(exc)
        except Exception as exc:
            result.error = f"{type(exc).__name__}: {exc}"
        result.seconds = time.monotonic() - started
        return result

    def _pick_merger(self, src_fs: list[Format], tgt_f: Format) -> Converter:
        candidates = [
            c for c in self.registry.all()
            if c.many_to_one and c.available() and tgt_f.name in c.target_names()
        ]
        if not candidates:
            raise NoRouteError(f"no available converter merges files into {tgt_f.name}")
        # Prefer the merger that directly accepts the most inputs.
        def score(c: Converter) -> tuple[int, int]:
            accepted = sum(1 for f in src_fs if c.supports(f.name, tgt_f.name))
            return (-accepted, c.cost)
        return sorted(candidates, key=score)[0]

    def _best_intermediate(self, src_f: Format, merger: Converter, tgt_f: Format) -> Format:
        best: tuple[int, Format] | None = None
        for name in merger.source_names():
            if not merger.supports(name, tgt_f.name):
                continue
            route = self.registry.find_route(src_f.name, name)
            if route is None:
                continue
            cost = sum(s.conv.cost for s in route) + len(route) * 8
            if best is None or cost < best[0]:
                best = (cost, formats.FORMATS[name])
        if best is None:
            raise NoRouteError(f"cannot prepare {src_f.name} for merging into {tgt_f.name}")
        return best[1]


ENGINE = Engine()
