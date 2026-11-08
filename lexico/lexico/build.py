from __future__ import annotations

import gzip
import io
import json
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .text import LANGS, key, tags_str

SCHEMA = Path(__file__).with_name("schema.sql")

AFFIX_POS = {"prefix", "suffix", "infix", "interfix", "circumfix", "affix"}
DROP_FORM_TAGS = {"table-tags", "inflection-template", "class", "romanization", "canonical"}
MORPH_TEMPLATES = {"af", "affix", "prefix", "suffix", "confix", "compound", "surf", "blend"}
ETYMON_KIND = {
    "inh": "inh", "inh+": "inh", "inh-lite": "inh",
    "der": "der", "der+": "der", "uder": "der", "der-lite": "der",
    "bor": "bor", "bor+": "bor", "lbor": "bor", "ubor": "bor", "slbor": "bor",
    "learned borrowing": "bor", "obor": "bor",
}
RELATION_KEYS = {"synonyms": "synonym", "antonyms": "antonym", "derived": "derived", "related": "related"}

PT_SUPERSCRIPT = re.compile(r"⁽[^⁾]*⁾")
PT_RELATIONAL = re.compile(
    r"^(?:relativ[oa]s?|pertencentes?|referentes?|concernentes?|relacionad[oa]s?|própri[oa]s?|semelhantes?)"
    r"(?:\s+ou\s+\w+)?"
    r"\s+(?:a|ao|à|aos|às|de|do|da|dos|das|com|em|no|na|nos|nas)"
    r"\s+(?:(?:um|uma|o|a|os|as)\s+)?([\wÀ-ÿ-]+)",
    re.IGNORECASE,
)
PROPER_NEXT = re.compile(r"\s+(?:d[aeo]s?\s+)?[A-ZÀ-Ý]")
EN_RELATIONAL = re.compile(
    r"(?:^|\()\s*(?:of|relating to|pertaining to)"
    r"(?:,?\s*(?:or\s+)?(?:relating|pertaining|belonging)\s+to)?"
    r"(?:,?\s*or\s+\w+(?:\s+\w+)?)?"
    r"\s+(?:an?\s+|the\s+)?([a-z][a-z-]+)",
    re.IGNORECASE,
)


def open_lines(path: str):
    if path == "-":
        return io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, encoding="utf-8")


def records(path: str, stats: dict):
    with open_lines(path) as fh:
        for line in fh:
            stats["lines"] += 1
            if stats["lines"] % 200000 == 0:
                print(f"  {path}: {stats['lines']} lines", file=sys.stderr)
            try:
                rec = json.loads(line)
            except ValueError:
                stats["bad_json"] += 1
                continue
            if rec.get("lang_code") in LANGS and rec.get("word") and rec.get("pos"):
                yield rec


def syllables_of(rec: dict) -> str | None:
    hy = rec.get("hyphenations")
    if hy and isinstance(hy, list) and hy[0].get("parts"):
        return "-".join(hy[0]["parts"])
    old = rec.get("hyphenation")
    if old and isinstance(old, list) and isinstance(old[0], str):
        return old[0].replace("‧", "-").replace("·", "-")
    for f in rec.get("forms") or []:
        if "canonical" in (f.get("tags") or []) and "." in f.get("form", ""):
            return f["form"].replace(".", "-")
    return None


def is_form_entry(senses: list) -> bool:
    return bool(senses) and all(s.get("form_of") or "form-of" in (s.get("tags") or []) for s in senses)


def numbered(args: dict, start: int):
    i = start
    while str(i) in args:
        yield i, args[str(i)]
        i += 1


ETY_OP = re.compile(r"^:([A-Za-z]+)")
ETY_LANG = re.compile(r"^([A-Za-z]{2,3}(?:-[A-Za-z]{2,4})*|[A-Z]{1,3}\.):(?=\S)")
ETY_MORPH_OPS = {"af", "affix", "compound", "surf", "blend", "prefix", "suffix", "confix"}
ETY_ETYMON_OPS = {
    "inh": "inh", "bor": "bor", "lbor": "bor", "ubor": "bor", "slbor": "bor", "obor": "bor",
    "der": "der", "uder": "der", "calque": "der", "clq": "der", "deverbal": "der",
}
EN_LANG_NAME = {"pt": "Portuguese", "es": "Spanish", "de": "German", "fr": "French", "en": "English"}
TREE_LANGS = {
    "Latin": "la", "Late Latin": "la-lat", "Medieval Latin": "la-med", "New Latin": "la-new",
    "Vulgar Latin": "la-vul", "Ancient Greek": "grc", "Proto-Indo-European": "ine-pro",
    "Proto-Italic": "itc-pro", "Proto-Germanic": "gem-pro", "Old High German": "goh",
    "Middle High German": "gmh", "Old French": "fro", "Middle French": "frm", "Old Spanish": "osp",
    "Old Galician-Portuguese": "roa-opt", "Old English": "ang", "Middle English": "enm", "Arabic": "ar",
    "Frankish": "frk", "Old Norse": "non", "Italian": "it",
}
TREE_TAILS = ("lbor", "ubor", "uder", "inh", "der", "bor", "meta", "calque", "clq", "af", "surf", "blend",
              "clipping", "ellipsis", "psm")


def ety_part(raw: str, default_lang: str) -> tuple[str, str, dict]:
    term, mods, depth, buf, name = "", {}, 0, "", None
    i = raw.find("<")
    term = raw if i < 0 else raw[:i]
    rest = "" if i < 0 else raw[i:]
    for ch in rest:
        if ch == "<":
            depth += 1
            if depth == 1:
                buf, name = "", None
                continue
        elif ch == ">":
            depth -= 1
            if depth == 0:
                if name:
                    mods.setdefault(name, buf)
                continue
        if depth >= 1:
            if name is None and ch == ":" and depth == 1:
                name = buf
                buf = ""
            else:
                buf += ch
    lang = default_lang
    m = ETY_LANG.match(term)
    if m:
        lang, term = m.group(1), term[m.end():]
    return lang, term.strip(), mods


def ety_templates(rec: dict):
    seen = set()
    for t in rec.get("etymology_templates") or []:
        if t.get("name") != "ety":
            continue
        a = t.get("args") or {}
        m = ETY_OP.match(a.get("2", ""))
        if not m:
            continue
        sig = json.dumps(a, sort_keys=True)
        if sig in seen:
            continue
        seen.add(sig)
        lang = a.get("1") or rec["lang_code"]
        parts = [ety_part(v, lang) for _, v in numbered(a, 3) if v]
        yield m.group(1), [p for p in parts if p[1] and p[1] != "-"], a


def strip_tree_tail(text: str) -> str:
    for tail in TREE_TAILS:
        for end in (tail + ".?", tail + "."):
            if text.endswith(end):
                return text[: -len(end)]
    return text


def tree_etymons(rec: dict) -> list[tuple[str, str, str, str | None]]:
    text = rec.get("etymology_text") or ""
    if not text.startswith("Etymology tree"):
        return []
    out = []
    names = sorted(TREE_LANGS, key=len, reverse=True)
    for line in text.split("\n")[1:]:
        for name in names:
            if line.startswith(name + " "):
                term = strip_tree_tail(line[len(name) + 1:]).strip()
                if term:
                    out.append(("tree", TREE_LANGS[name], term, None))
                break
    return out


def clean_etymology(text: str | None, word: str, lang: str) -> str | None:
    if not text:
        return None
    if not text.startswith("Etymology tree"):
        return text.strip() or None
    lines = text.split("\n")
    marker = f"{EN_LANG_NAME.get(lang, '')} {word}"
    cut = max((i for i, ln in enumerate(lines) if ln.strip() == marker), default=None)
    prose = lines[cut + 1:] if cut is not None else lines[-1:]
    return "\n".join(prose).strip() or None


def morphemes_of(rec: dict) -> list[tuple[str, str | None, str | None]]:
    for op, parts, _ in ety_templates(rec):
        if op in ETY_MORPH_OPS and len(parts) >= 2:
            return [(term, mods.get("t") or mods.get("gloss"), lang) for lang, term, mods in parts]
    for t in rec.get("etymology_templates") or []:
        name = t.get("name")
        if name not in MORPH_TEMPLATES:
            continue
        a = t.get("args") or {}
        base_lang = a.get("1") or rec["lang_code"]
        parts = []
        for i, part in numbered(a, 2):
            if not part:
                continue
            gloss = a.get(f"t{i - 1}") or a.get(f"gloss{i - 1}") or None
            lang = a.get(f"lang{i - 1}") or base_lang
            parts.append([part, gloss, lang])
        if not parts:
            continue
        if name == "prefix":
            for p in parts[:-1]:
                if not p[0].endswith("-"):
                    p[0] += "-"
        elif name == "suffix" and len(parts) > 1:
            for p in parts[1:]:
                if not p[0].startswith("-"):
                    p[0] = "-" + p[0]
        elif name == "confix" and len(parts) >= 2:
            if not parts[0][0].endswith("-"):
                parts[0][0] += "-"
            if not parts[-1][0].startswith("-"):
                parts[-1][0] = "-" + parts[-1][0]
        if len(parts) < 2:
            continue
        return [tuple(p) for p in parts]
    return []


def etymons_of(rec: dict) -> list[tuple[str, str, str, str | None]]:
    out = []
    for op, parts, _ in ety_templates(rec):
        kind = ETY_ETYMON_OPS.get(op)
        if kind:
            for lang, term, mods in parts:
                if lang != rec["lang_code"]:
                    out.append((kind, lang, term, mods.get("t") or mods.get("gloss")))
    for t in rec.get("etymology_templates") or []:
        kind = ETYMON_KIND.get(t.get("name"))
        if not kind:
            continue
        a = t.get("args") or {}
        lang, term = a.get("2", ""), a.get("3", "")
        if not lang or term in ("", "-"):
            continue
        gloss = a.get("t") or a.get("gloss") or a.get("5") or None
        out.append((kind, lang, term, gloss))
    out.extend(tree_etymons(rec))
    return list(dict.fromkeys(out))


def cognates_of(rec: dict) -> list[tuple[str, str, str]]:
    out = []
    for _, _, a in ety_templates(rec):
        for w in (a.get("doublet") or "").split(","):
            lang, term, _ = ety_part(w.strip(), rec["lang_code"])
            if term:
                out.append(("doublet", term, lang))
    for t in rec.get("etymology_templates") or []:
        a = t.get("args") or {}
        if t.get("name") in ("cog", "cognate", "noncog") and a.get("1") and a.get("2") not in (None, "", "-"):
            out.append(("cognate", a["2"], a["1"]))
        elif t.get("name") in ("doublet", "dbt"):
            for _, w in numbered(a, 2):
                if w:
                    out.append(("doublet", w, a.get("1") or rec["lang_code"]))
    return out


def relations_of(rec: dict):
    holders = [rec] + list(rec.get("senses") or [])
    for h in holders:
        for field, kind in RELATION_KEYS.items():
            for item in h.get(field) or []:
                w = item.get("word") if isinstance(item, dict) else None
                if w and w != rec["word"]:
                    yield kind, w, tags_str(item.get("tags"))


DEGREE_TAGS = {"diminutive", "augmentative", "comparative", "superlative"}
PERSON_TAGS = {"first-person", "second-person", "third-person"}
NOT_INDICATIVE = {"subjunctive", "imperative", "conditional", "optative"}
DECLENSION_TAGS = {"strong", "weak", "mixed", "includes-article", "without-article"}
GENDER_NUMBER = {"plural", "singular", "feminine", "masculine", "neuter"}


def keep_form(pos: str, tags: set) -> bool:
    if tags & DEGREE_TAGS:
        return True
    if pos == "verb":
        return (
            ("infinitive" in tags and not tags & PERSON_TAGS)
            or "participle" in tags
            or "gerund" in tags
            or ({"first-person", "singular", "present"} <= tags and not tags & NOT_INDICATIVE)
        )
    if tags & DECLENSION_TAGS or tags & {"dative", "accusative"}:
        return False
    return bool(tags & (GENDER_NUMBER | {"nominative", "genitive"}))


def gloss_text(sense: dict) -> str:
    gl = sense.get("glosses") or sense.get("raw_glosses") or []
    return " ".join(g.strip() for g in gl if g and g.strip())


class Builder:
    def __init__(self, db_path: Path, all_forms: bool = False):
        self.all_forms = all_forms
        if db_path.exists():
            db_path.unlink()
        self.db = sqlite3.connect(str(db_path))
        self.db.executescript(SCHEMA.read_text(encoding="utf-8"))
        self.db.execute("PRAGMA journal_mode = OFF")
        self.db.execute("PRAGMA synchronous = OFF")
        self.db.execute("BEGIN")
        self.sources: list[str] = []

    def new_entry(self, rec: dict, source: str, etymology: str | None, etymology_pt: str | None) -> int:
        cur = self.db.execute(
            "INSERT INTO entry (lang, word, word_key, pos, etym_no, syllables, etymology, etymology_pt, is_form, source)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                rec["lang_code"], rec["word"], key(rec["word"]), rec["pos"],
                int(rec.get("etymology_number") or 0), syllables_of(rec),
                etymology, etymology_pt, int(is_form_entry(rec.get("senses") or [])), source,
            ),
        )
        return cur.lastrowid

    def add_senses(self, entry_id: int, rec: dict, gloss_lang: str, start: int) -> int:
        n = start
        only_forms = is_form_entry(rec.get("senses") or [])
        linked = set()
        for s in rec.get("senses") or []:
            tags = tags_str(s.get("tags"))
            g = gloss_text(s)
            if g and not only_forms:
                self.db.execute("INSERT INTO sense VALUES (?,?,?,?,?)", (entry_id, n, g, gloss_lang, tags))
                n += 1
            for fo in s.get("form_of") or []:
                if fo.get("word") and fo["word"] not in linked:
                    linked.add(fo["word"])
                    self.db.execute("INSERT INTO form_of VALUES (?,?,?)", (entry_id, fo["word"], tags))
        return n

    def add_relations(self, entry_id: int, rec: dict, source: str, seen: set | None = None):
        seen = set() if seen is None else seen
        for kind, w, tags in relations_of(rec):
            if (kind, w) in seen:
                continue
            seen.add((kind, w))
            self.db.execute(
                "INSERT INTO relation VALUES (?,?,?,?,?,?)", (entry_id, kind, w, rec["lang_code"], tags, source)
            )

    def add_affix(self, rec: dict, gloss_lang: str, source: str):
        w = rec["word"]
        if rec["pos"] not in AFFIX_POS and not (w.startswith("-") or w.endswith("-")):
            return
        if w.startswith("-") and w.endswith("-"):
            kind = "infix"
        elif w.endswith("-"):
            kind = "prefix"
        elif w.startswith("-"):
            kind = "suffix"
        else:
            kind = rec["pos"]
        glosses = [gloss_text(s) for s in rec.get("senses") or []]
        gloss = next((g for g in glosses if g), None)
        self.db.execute(
            "INSERT INTO affix VALUES (?,?,?,?,?,?)", (rec["lang_code"], w, kind, gloss, gloss_lang, source)
        )

    def add_adjective_links(self, rec: dict, pattern: re.Pattern, via: str):
        if rec["pos"] != "adj":
            return
        seen = set()
        for s in rec.get("senses") or []:
            if s.get("form_of"):
                continue
            g = gloss_text(s)
            m = pattern.search(g)
            if not m or m.group(1)[:1].isupper() or PROPER_NEXT.match(g, m.end()):
                continue
            noun = key(m.group(1))
            if noun in seen:
                continue
            seen.add(noun)
            self.db.execute(
                "INSERT INTO adjective_of VALUES (?,?,?,?,?)", (rec["lang_code"], noun, rec["word"], via, g[:200])
            )

    def load_en(self, path: str):
        stats = {"lines": 0, "bad_json": 0, "entries": 0}
        for rec in records(path, stats):
            ety = clean_etymology(rec.get("etymology_text"), rec["word"], rec["lang_code"])
            eid = self.new_entry(rec, "en", ety, None)
            stats["entries"] += 1
            self.add_senses(eid, rec, "en", 0)
            for n, (morph, gloss, lang) in enumerate(morphemes_of(rec)):
                self.db.execute("INSERT INTO morpheme VALUES (?,?,?,?,?)", (eid, n, morph, gloss, lang))
            for n, (kind, lang, term, gloss) in enumerate(etymons_of(rec)):
                self.db.execute("INSERT INTO etymon VALUES (?,?,?,?,?,?)", (eid, n, kind, lang, term, gloss))
            seen = set()
            for kind, w, lang in cognates_of(rec):
                if (kind, w, lang) not in seen:
                    seen.add((kind, w, lang))
                    self.db.execute("INSERT INTO relation VALUES (?,?,?,?,?,?)", (eid, kind, w, lang, "", "en"))
            self.add_relations(eid, rec, "en")
            for f in rec.get("forms") or []:
                tags = set(f.get("tags") or [])
                form = f.get("form", "")
                if form and form != "-" and not tags & DROP_FORM_TAGS and (self.all_forms or keep_form(rec["pos"], tags)):
                    self.db.execute("INSERT INTO form VALUES (?,?,?)", (eid, form, tags_str(tags)))
            self.add_affix(rec, "en", "en.wiktionary")
            self.add_adjective_links(rec, EN_RELATIONAL, "en-gloss")
        self.sources.append(f"en.wiktionary:{Path(path).name}")
        return stats

    def load_pt(self, path: str):
        stats = {"lines": 0, "bad_json": 0, "merged": 0, "new": 0}
        for rec in records(path, stats):
            ety = " ".join(rec.get("etymology_texts") or []) or None
            if ety:
                ety = PT_SUPERSCRIPT.sub("", ety).lstrip(": ").strip() or None
            row = self.db.execute(
                "SELECT id, syllables, etymology_pt FROM entry WHERE lang=? AND word=? AND pos=? ORDER BY etym_no LIMIT 1",
                (rec["lang_code"], rec["word"], rec["pos"]),
            ).fetchone()
            if row:
                eid, syl, old_ety = row
                stats["merged"] += 1
                updates = {}
                if not syl and syllables_of(rec):
                    updates["syllables"] = syllables_of(rec)
                if ety and not old_ety:
                    updates["etymology_pt"] = ety
                for col, val in updates.items():
                    self.db.execute(f"UPDATE entry SET {col}=? WHERE id=?", (val, eid))
                start = self.db.execute("SELECT COALESCE(MAX(n)+1, 0) FROM sense WHERE entry_id=?", (eid,)).fetchone()[0]
            else:
                eid = self.new_entry(rec, "pt", None, ety)
                stats["new"] += 1
                start = 0
            self.add_senses(eid, rec, "pt", start)
            self.add_relations(eid, rec, "pt")
            self.add_affix(rec, "pt", "pt.wiktionary")
            self.add_adjective_links(rec, PT_RELATIONAL, "pt-gloss")
        self.sources.append(f"pt.wiktionary:{Path(path).name}")
        return stats

    def load_adjetivos(self, path: str) -> int:
        n = 0
        for cells in markdown_rows(path):
            if len(cells) < 2:
                continue
            note = " ".join(c for c in cells[2:] if c) or None
            for adj in cells[1].split("/"):
                adj = adj.strip()
                if adj:
                    self.db.execute(
                        "INSERT INTO adjective_of VALUES (?,?,?,?,?)", ("pt", key(cells[0]), adj, "adjetivos-eruditos.md", note)
                    )
                    n += 1
        self.sources.append(f"user:{Path(path).name}")
        return n

    def load_radicais(self, path: str, lang: str = "pt") -> int:
        n = 0
        for cells in markdown_rows(path):
            if len(cells) < 3:
                continue
            gloss = cells[2]
            if cells[1]:
                gloss = f"{gloss} ({cells[1]})"
            for form in cells[0].split("/"):
                form = form.strip()
                if not form:
                    continue
                kind = "prefix" if form.endswith("-") else "suffix" if form.startswith("-") else "root"
                self.db.execute("INSERT INTO affix VALUES (?,?,?,?,?,?)", (lang, form, kind, gloss, "pt", "radicais.md"))
                n += 1
        self.sources.append(f"user:{Path(path).name}")
        return n

    def finish(self):
        counts = {t: self.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("entry", "sense", "morpheme", "affix", "adjective_of")}
        meta = {
            "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sources": "; ".join(self.sources),
            "counts": json.dumps(counts),
        }
        self.db.executemany("INSERT INTO meta VALUES (?,?)", meta.items())
        self.db.execute("COMMIT")
        self.db.execute("ANALYZE")
        self.db.execute("VACUUM")
        self.db.close()
        return counts


def markdown_rows(path: str):
    header_seen = False
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("|"):
            header_seen = False
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            header_seen = True
            continue
        if header_seen:
            yield cells


def discover(data_dir: Path) -> tuple[list[str], list[str]]:
    en = sorted(str(p) for p in (data_dir / "en").glob("*.jsonl*"))
    pt = sorted(str(p) for p in (data_dir / "pt").glob("*.jsonl*"))
    return en, pt


def run(out: Path, en: list[str], pt: list[str], adjetivos: str | None, radicais: str | None,
        all_forms: bool = False) -> dict:
    t0 = time.time()
    b = Builder(out, all_forms)
    for path in en:
        print(f"en.wiktionary {path}", file=sys.stderr)
        print(f"  {b.load_en(path)}", file=sys.stderr)
    for path in pt:
        print(f"pt.wiktionary {path}", file=sys.stderr)
        print(f"  {b.load_pt(path)}", file=sys.stderr)
    if adjetivos:
        print(f"adjetivos-eruditos: {b.load_adjetivos(adjetivos)} rows", file=sys.stderr)
    if radicais:
        print(f"radicais: {b.load_radicais(radicais)} rows", file=sys.stderr)
    counts = b.finish()
    print(f"done in {time.time() - t0:.0f}s: {counts}", file=sys.stderr)
    return counts
