from __future__ import annotations

from functools import cache

from . import query
from .text import key

MIN_AFFIX = 2
MIN_STEM = 3
MAX_WORD = 40
STEM_VOWELS = ("", "a", "o", "e")
LINKING = {"de": ("s", "es", "n", "en", "e", "er"), "pt": ("i", "o"), "es": ("i", "o"), "fr": ("i", "o"), "en": ("i", "o")}


def _affix_index(db, lang):
    pre, suf = {}, {}
    for r in query.affixes(db, lang):
        a = r["affix"]
        core = key(a.strip("-"))
        if len(core) < MIN_AFFIX:
            continue
        if r["kind"] == "suffix" or (a.startswith("-") and not a.endswith("-")):
            suf.setdefault(core, r)
        else:
            pre.setdefault(core, r)
    return pre, suf


def segment(db, word: str, lang: str) -> list[dict] | None:
    w = word
    n = len(w)
    if n < MIN_STEM + MIN_AFFIX or n > MAX_WORD:
        return None
    pre, suf = _affix_index(db, lang)
    links = LINKING.get(lang, ())

    @cache
    def stem_lemma(s: str):
        if len(s) < MIN_STEM or s.lower() == w.lower():
            return None
        for v in STEM_VOWELS:
            if (s + v).lower() != w.lower():
                found = query.lemma_spelling(db, s + v, lang)
                if found:
                    return found
        return None

    def options(i: int, only_suffix: bool):
        for j in range(n, i, -1):
            piece = w[i:j]
            k = key(piece)
            if (j == n or only_suffix) and k in suf:
                yield j, {"morph": piece, "kind": "suffix", "row": suf[k]}, True
            if only_suffix:
                continue
            if j < n and k in pre:
                yield j, {"morph": piece, "kind": "prefix", "row": pre[k]}, False
            lemma = stem_lemma(piece)
            if lemma:
                yield j, {"morph": piece, "kind": "stem", "lemma": lemma}, False
            if piece.lower() in links and 0 < i and j < n:
                yield j, {"morph": piece, "kind": "link"}, False

    @cache
    def best(i: int, in_suffix: bool):
        if i == n:
            return ()
        result = None
        for j, piece, is_suffix in options(i, in_suffix):
            rest = best(j, in_suffix or is_suffix)
            if rest is None:
                continue
            cand = (piece,) + rest
            if result is None or _cost(cand) < _cost(result):
                result = cand
        return result

    pieces = best(0, False)
    if not pieces or len(pieces) < 2:
        return None
    if all(p["kind"] in ("stem", "link") for p in pieces) and lang != "de":
        return None
    if pieces[-1]["kind"] == "link" or pieces[0]["kind"] == "link":
        return None
    out = []
    for p in pieces:
        if p["kind"] in ("prefix", "suffix"):
            row = p["row"]
            out.append({"morph": p["morph"], "kind": p["kind"], "lemma": row["affix"], "gloss": row["gloss"],
                        "source": row["source"]})
        elif p["kind"] == "stem":
            shown = p["lemma"] if p["lemma"].lower() == p["morph"].lower() else p["morph"]
            out.append({"morph": shown, "kind": "stem", "lemma": p["lemma"],
                        "gloss": query.first_gloss(db, p["lemma"], lang), "source": "entry"})
        else:
            out.append({"morph": p["morph"], "kind": "link", "lemma": None, "gloss": None, "source": None})
    return out


def _cost(pieces) -> tuple:
    links = sum(1 for p in pieces if p["kind"] == "link")
    user = sum(1 for p in pieces if p.get("row") is not None and p["row"]["source"] == "radicais.md")
    return (len(pieces) + links, -user)
