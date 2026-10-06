"""Converter registry and route finding.

Formats are nodes of a directed graph and converters are labelled edges.
A request to turn ``docx`` into ``png`` may have no direct edge, but the
graph contains ``docx -> pdf`` (LibreOffice) and ``pdf -> png`` (PyMuPDF),
so a shortest-path search over available converters yields a two-step
route. Costs are per converter, plus a fixed penalty per hop, so a direct
route always beats a chain when one exists.
"""

from __future__ import annotations

import heapq
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, TYPE_CHECKING

from omniconv.core import formats
from omniconv.core.errors import MissingDependencyError
from omniconv.core.requirements import Requirement

if TYPE_CHECKING:  # pragma: no cover
    from omniconv.core.engine import Job

ConvertFunc = Callable[["Job"], "list[Path] | Path | None"]
FormatSet = frozenset[str] | Callable[[], Iterable[str]]

HOP_PENALTY = 8
MAX_HOPS = 3
# Intermediate formats are restricted to these categories in addition to the
# categories of the endpoints. PDF and raster images act as universal hubs.
HUB_CATEGORIES = frozenset({"document", "image"})
# Intermediates outside this set carry a small extra penalty, so that among
# equally cheap two-step routes the one through a lossless, widely readable
# format (PNG rather than EPS, WAV rather than MP3) is chosen.
PREFERRED_HUBS = frozenset({"png", "tiff", "pdf", "wav", "flac", "mkv", "mp4", "html", "docx", "md", "json", "tar", "zip", "ttf", "svg", "epub", "txt", "csv"})
HUB_PENALTY = 3


def _resolve(value: FormatSet) -> frozenset[str]:
    if callable(value):
        return formats.names(value())
    return value


@dataclass(frozen=True)
class Converter:
    name: str
    sources: FormatSet
    targets: FormatSet
    func: ConvertFunc
    requires: tuple[Requirement, ...] = ()
    cost: int = 10
    options: tuple[str, ...] = ()
    description: str = ""
    same_format: bool = False
    many_to_one: bool = False
    predicate: Callable[[str, str], bool] | None = None
    _cache: dict[str, Any] = field(default_factory=dict, repr=False, compare=False, hash=False)

    def available(self) -> bool:
        if "available" not in self._cache:
            self._cache["available"] = all(r.available() for r in self.requires)
        return self._cache["available"]

    def missing(self) -> list[Requirement]:
        return [r for r in self.requires if not r.available()]

    def source_names(self) -> frozenset[str]:
        if "sources" not in self._cache:
            self._cache["sources"] = _resolve(self.sources)
        return self._cache["sources"]

    def target_names(self) -> frozenset[str]:
        if "targets" not in self._cache:
            self._cache["targets"] = _resolve(self.targets)
        return self._cache["targets"]

    def supports(self, src: str, tgt: str) -> bool:
        if src == tgt and not (self.same_format or self.many_to_one):
            return False
        if src not in self.source_names() or tgt not in self.target_names():
            return False
        if self.predicate is not None and not self.predicate(src, tgt):
            return False
        return True

    def run(self, job: "Job") -> list[Path]:
        if not self.available():
            missing = ", ".join(r.describe() for r in self.missing())
            raise MissingDependencyError(f"{self.name} needs {missing}")
        result = self.func(job)
        if result is None:
            return [job.target]
        if isinstance(result, Path):
            return [result]
        return list(result)

    def reset(self) -> None:
        self._cache.clear()


@dataclass(frozen=True)
class Step:
    """One hop of a route: apply ``conv`` to turn ``src`` into ``tgt``."""

    conv: Converter
    src: str
    tgt: str

    @property
    def name(self) -> str:
        return self.conv.name


Route = list[Step]


class Registry:
    def __init__(self) -> None:
        self._converters: list[Converter] = []
        self._lock = threading.Lock()
        self._graph: dict[str, dict[str, list[Converter]]] | None = None

    # ---------------------------------------------------------- registration
    def register(self, conv: Converter) -> Converter:
        with self._lock:
            self._converters.append(conv)
            self._graph = None
        return conv

    def all(self) -> list[Converter]:
        return list(self._converters)

    def available(self) -> list[Converter]:
        return [c for c in self._converters if c.available()]

    def unavailable(self) -> list[Converter]:
        return [c for c in self._converters if not c.available()]

    def reset(self) -> None:
        from omniconv.core.requirements import reset_cache

        reset_cache()
        for c in self._converters:
            c.reset()
        self._graph = None

    # ------------------------------------------------------------------ graph
    def graph(self) -> dict[str, dict[str, list[Converter]]]:
        """Adjacency: ``graph[src][tgt]`` is the list of available converters
        sorted by cost. Built lazily and cached."""
        if self._graph is not None:
            return self._graph
        with self._lock:
            if self._graph is not None:
                return self._graph
            g: dict[str, dict[str, list[Converter]]] = {}
            for conv in self._converters:
                if not conv.available() or conv.many_to_one:
                    continue
                for src in conv.source_names():
                    for tgt in conv.target_names():
                        if conv.supports(src, tgt):
                            g.setdefault(src, {}).setdefault(tgt, []).append(conv)
            for src in g:
                for tgt in g[src]:
                    g[src][tgt].sort(key=lambda c: c.cost)
            self._graph = g
            return g

    def direct(self, src: str, tgt: str) -> list[Converter]:
        return list(self.graph().get(src, {}).get(tgt, []))

    def direct_targets(self, src: str) -> set[str]:
        return set(self.graph().get(src, {}))

    def mergers(self, src: str, tgt: str) -> list[Converter]:
        """Converters that combine several ``src`` files into one ``tgt``."""
        out = [c for c in self._converters if c.many_to_one and c.available() and c.supports(src, tgt)]
        return sorted(out, key=lambda c: c.cost)

    # ---------------------------------------------------------------- routing
    def find_route(self, src: str, tgt: str, max_hops: int = MAX_HOPS) -> Route | None:
        """Dijkstra over the format graph. Returns the steps to apply in
        order, or ``None`` if the target is unreachable."""
        if src == tgt:
            direct = self.direct(src, tgt)
            return [Step(direct[0], src, tgt)] if direct else None
        routes = self._dijkstra(src, max_hops, stop_at=tgt)
        return routes.get(tgt)

    def reachable(self, src: str, max_hops: int = MAX_HOPS) -> dict[str, Route]:
        """Every target reachable from ``src`` with its cheapest route."""
        routes = self._dijkstra(src, max_hops, stop_at=None)
        routes.pop(src, None)
        for conv in self.direct(src, src):
            routes[src] = [Step(conv, src, src)]
            break
        return routes

    def _dijkstra(self, src: str, max_hops: int, stop_at: str | None) -> dict[str, Route]:
        graph = self.graph()
        src_cat = formats.get(src).category
        allowed_cats = HUB_CATEGORIES | {src_cat}
        if stop_at is not None:
            allowed_cats = allowed_cats | {formats.get(stop_at).category}
        best: dict[str, tuple[int, Route]] = {src: (0, [])}
        heap: list[tuple[int, int, str, Route]] = [(0, 0, src, [])]
        while heap:
            cost, hops, node, route = heapq.heappop(heap)
            if best.get(node, (cost + 1, None))[0] < cost:
                continue
            if node == stop_at:
                break
            if hops >= max_hops:
                continue
            for tgt, convs in graph.get(node, {}).items():
                if tgt == src:
                    continue
                conv = convs[0]
                new_cost = cost + conv.cost + HOP_PENALTY
                if tgt != stop_at and tgt not in PREFERRED_HUBS:
                    new_cost += HUB_PENALTY
                # An intermediate format must be a plausible hub: same category as
                # the endpoints, or one of the universal hub categories.
                tgt_cat = formats.get(tgt).category
                if tgt != stop_at and tgt_cat not in allowed_cats and stop_at is not None:
                    continue
                step = Step(conv, node, tgt)
                if stop_at is None and tgt_cat not in allowed_cats and hops + 1 < max_hops:
                    # When enumerating, still record the target but do not expand
                    # further through a non-hub category.
                    if tgt not in best or best[tgt][0] > new_cost:
                        best[tgt] = (new_cost, route + [step])
                    continue
                if tgt not in best or best[tgt][0] > new_cost:
                    best[tgt] = (new_cost, route + [step])
                    heapq.heappush(heap, (new_cost, hops + 1, tgt, route + [step]))
        return {k: v[1] for k, v in best.items() if k != src}

    def candidates_needing_install(self, src: str, tgt: str) -> list[Converter]:
        """Unavailable converters that would handle ``src -> tgt`` directly."""
        return [c for c in self._converters if not c.available() and c.supports(src, tgt)]


REGISTRY = Registry()


def converter(
    name: str,
    sources: Iterable[str] | Callable[[], Iterable[str]],
    targets: Iterable[str] | Callable[[], Iterable[str]],
    *,
    requires: Iterable[Requirement] = (),
    cost: int = 10,
    options: Iterable[str] = (),
    description: str = "",
    same_format: bool = False,
    many_to_one: bool = False,
    predicate: Callable[[str, str], bool] | None = None,
) -> Callable[[ConvertFunc], ConvertFunc]:
    """Decorator that registers ``func`` as a converter in the global registry."""

    def decorate(func: ConvertFunc) -> ConvertFunc:
        conv = Converter(
            name=name,
            sources=sources if callable(sources) else formats.names(sources),
            targets=targets if callable(targets) else formats.names(targets),
            func=func,
            requires=tuple(requires),
            cost=cost,
            options=tuple(options),
            description=description or (func.__doc__ or "").strip().splitlines()[0] if (description or func.__doc__) else "",
            same_format=same_format,
            many_to_one=many_to_one,
            predicate=predicate,
        )
        REGISTRY.register(conv)
        return func

    return decorate
