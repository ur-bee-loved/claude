from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from .text import key

POS_ORDER = "CASE pos WHEN 'noun' THEN 0 WHEN 'adj' THEN 1 WHEN 'verb' THEN 2 WHEN 'adv' THEN 3 ELSE 4 END"


def connect(path: str | Path) -> sqlite3.Connection:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"database not found: {p}")
    db = sqlite3.connect(f"file:{p.resolve()}?mode=ro", uri=True, check_same_thread=False)
    db.row_factory = sqlite3.Row
    return db


def meta(db) -> dict:
    return {r["key"]: r["value"] for r in db.execute("SELECT key, value FROM meta")}


def languages_of(db, word: str) -> list[str]:
    rows = db.execute("SELECT DISTINCT lang FROM entry WHERE word_key=? ORDER BY lang", (key(word),))
    return [r["lang"] for r in rows]


def find_entries(db, word: str, lang: str | None = None, pos: str | None = None) -> list[sqlite3.Row]:
    where, args = ["word_key=?"], [key(word)]
    if lang:
        where.append("lang=?")
        args.append(lang)
    if pos:
        where.append("pos=?")
        args.append(pos)
    sql = f"SELECT * FROM entry WHERE {' AND '.join(where)} ORDER BY is_form, {POS_ORDER}, etym_no, id"
    rows = db.execute(sql, args).fetchall()
    exact = [r for r in rows if r["word"] == word]
    if exact:
        return exact
    lower = [r for r in rows if r["word"].lower() == word.lower()]
    return lower or rows


def senses(db, entry_id: int) -> list[sqlite3.Row]:
    return db.execute(
        "SELECT gloss, gloss_lang, tags FROM sense WHERE entry_id=? ORDER BY gloss_lang<>'pt', n", (entry_id,)
    ).fetchall()


def morphemes(db, entry_id: int) -> list[sqlite3.Row]:
    return db.execute("SELECT morph, gloss, lang FROM morpheme WHERE entry_id=? ORDER BY n", (entry_id,)).fetchall()


def etymons(db, entry_id: int) -> list[sqlite3.Row]:
    return db.execute("SELECT kind, lang, term, gloss FROM etymon WHERE entry_id=? ORDER BY n", (entry_id,)).fetchall()


def relations(db, entry_id: int, kind: str) -> list[sqlite3.Row]:
    return db.execute(
        "SELECT word, lang, tags, source FROM relation WHERE entry_id=? AND kind=? ORDER BY rowid", (entry_id, kind)
    ).fetchall()


def forms(db, entry_id: int) -> list[sqlite3.Row]:
    return db.execute("SELECT form, tags FROM form WHERE entry_id=? ORDER BY rowid", (entry_id,)).fetchall()


def lemmas_of(db, entry_id: int) -> list[str]:
    rows = db.execute("SELECT DISTINCT lemma FROM form_of WHERE entry_id=?", (entry_id,))
    return [r["lemma"] for r in rows]


def lemma_entries(db, word: str, lang: str) -> list[sqlite3.Row]:
    return [e for e in find_entries(db, word, lang) if not e["is_form"]]


def affixes(db, lang: str) -> list[sqlite3.Row]:
    return db.execute(
        "SELECT affix, kind, gloss, gloss_lang, source FROM affix WHERE lang=?"
        " ORDER BY source='radicais.md' DESC, length(affix) DESC",
        (lang,),
    ).fetchall()


def lemma_spelling(db, word: str, lang: str) -> str | None:
    row = db.execute(
        "SELECT word FROM entry WHERE word_key=? AND lang=? AND is_form=0 AND lower(word)=? ORDER BY word<>? LIMIT 1",
        (key(word), lang, word.lower(), word),
    ).fetchone()
    return row["word"] if row else None


def first_gloss(db, word: str, lang: str) -> str | None:
    for e in lemma_entries(db, word, lang):
        s = senses(db, e["id"])
        if s:
            return s[0]["gloss"]
    return None


def morpheme_gloss(db, morph: str, lang: str) -> str | None:
    row = db.execute(
        "SELECT gloss FROM affix WHERE lang=? AND affix=? AND gloss IS NOT NULL"
        " ORDER BY source='radicais.md' DESC, gloss_lang='pt' DESC LIMIT 1",
        (lang, morph),
    ).fetchone()
    if row:
        return row["gloss"]
    return first_gloss(db, morph, lang)


_EN_HEAD = re.compile(r"^(?:\([^)]*\)\s*)?(?:an?\s+|the\s+|to\s+)?([a-z][a-z-]+)", re.IGNORECASE)


def adjectives_for(db, noun: str, lang: str) -> list[dict]:
    out, seen = [], set()

    def add(rows):
        for r in rows:
            k = (r["adjective"], r["via"])
            if r["adjective"] not in {a for a, _ in seen}:
                out.append(dict(r))
            seen.add(k)

    keys = {key(noun)}
    for e in lemma_entries(db, noun, lang):
        for f in forms(db, e["id"]):
            if "plural" in f["tags"].split():
                keys.add(key(f["form"]))
    marks = ",".join("?" * len(keys))
    add(db.execute(
        f"SELECT adjective, via, note FROM adjective_of WHERE lang=? AND noun_key IN ({marks})"
        " ORDER BY via<>'adjetivos-eruditos.md', via<>'pt-gloss'",
        [lang, *keys],
    ))
    en_heads = set()
    if lang == "en":
        en_heads.add(key(noun))
    else:
        for e in lemma_entries(db, noun, lang):
            if e["pos"] != "noun":
                continue
            for s in senses(db, e["id"]):
                if s["gloss_lang"] == "en":
                    m = _EN_HEAD.match(s["gloss"])
                    if m:
                        en_heads.add(key(m.group(1)))
    en_heads -= keys
    if en_heads:
        marks = ",".join("?" * len(en_heads))
        add(db.execute(
            f"SELECT adjective, via, note FROM adjective_of WHERE lang=? AND via='en-gloss' AND noun_key IN ({marks})",
            [lang, *en_heads],
        ))
    return out


def same_root(db, entry_id: int, lang: str, limit: int = 15) -> list[str]:
    rows = db.execute(
        """
        SELECT DISTINCT e.word FROM etymon a
        JOIN etymon b ON b.lang=a.lang AND b.term=a.term AND b.entry_id<>a.entry_id
        JOIN entry e ON e.id=b.entry_id
        WHERE a.entry_id=? AND e.lang=? AND e.is_form=0 AND e.word<>(SELECT word FROM entry WHERE id=?)
          AND a.lang IN ('la', 'la-lat', 'la-med', 'la-new', 'la-vul', 'grc', 'gem-pro', 'goh', 'gmh', 'ang', 'frk')
          AND a.term NOT LIKE '-%' AND a.term NOT LIKE '%-' AND a.term NOT LIKE '*%'
        ORDER BY e.word LIMIT ?
        """,
        (entry_id, lang, entry_id, limit),
    ).fetchall()
    return [r["word"] for r in rows]


def register_tags(db, word: str, lang: str) -> set[str]:
    common = None
    for e in lemma_entries(db, word, lang):
        for s in senses(db, e["id"]):
            t = set(s["tags"].split())
            common = t if common is None else common & t
    return common or set()
