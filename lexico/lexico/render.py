from __future__ import annotations

from . import query
from .segment import segment
from .text import LANGS, lang_name

MODES = ("desconstruir", "adjetivo", "sinonimo", "formas")

ERUDITE = {"formal", "literary", "learned", "poetic"}
COLLOQUIAL = {"colloquial", "informal", "slang", "vulgar", "familiar", "Internet"}
MARKS = {"rare": "raro", "archaic": "arcaico", "obsolete": "obsoleto", "dated": "antiquado",
         "Brazil": "BR", "Portugal": "PT", "regional": "regional", "dialectal": "dialetal"}
DEGREE = {"diminutive": "dim.", "augmentative": "aum.", "comparative": "comp.", "superlative": "sup."}
CASE_ABBR = {"nominative": "nom.", "genitive": "gen.", "singular": "sg.", "plural": "pl."}
MAX_LIST = 8
NUANCE = "Nuance: — (não derivável dos dados; fica para consulta humana ou para o Claude)"


class Ambiguous(Exception):
    pass


class NotFound(Exception):
    pass


def resolve_lang(db, word: str, lang: str | None) -> str:
    if lang:
        if not query.find_entries(db, word, lang):
            raise NotFound(f'"{word}" não encontrada em {lang_name(lang)}.')
        return lang
    langs = [x for x in query.languages_of(db, word) if x in LANGS]
    if not langs:
        raise NotFound(f'"{word}" não encontrada na base.')
    if len(langs) > 1:
        raise Ambiguous(f'"{word}" existe em mais de uma língua: {", ".join(langs)}. Indique a língua.')
    return langs[0]


def gloss_line(row) -> str:
    if row is None:
        return "—"
    return row["gloss"] if row["gloss_lang"] == "pt" else f'{row["gloss"]} (en)'


def best_gloss(db, word: str, lang: str):
    for e in query.lemma_entries(db, word, lang):
        s = query.senses(db, e["id"])
        if s:
            return s[0]
    return None


def marks(tags: str) -> str:
    found = [MARKS[t] for t in tags.split() if t in MARKS]
    return f" ({', '.join(found)})" if found else ""


def source_line(db, used: list[str]) -> str:
    built = query.meta(db).get("built_at", "?")[:10]
    return f"Fonte: {'; '.join(dict.fromkeys(used))} (via kaikki.org, base de {built})"


def lemma_of(db, word: str, lang: str):
    entries = query.find_entries(db, word, lang)
    lemmas = [e for e in entries if not e["is_form"]]
    if lemmas:
        return lemmas[0], None
    for e in entries:
        for lemma in query.lemmas_of(db, e["id"]):
            le = query.lemma_entries(db, lemma, lang)
            if le:
                return le[0], e
    return entries[0], None


def deconstruct(db, word: str, lang: str | None = None) -> str:
    lang = resolve_lang(db, word, lang)
    entry, _ = lemma_of(db, word, lang)
    used = [f"{entry['source']}.wiktionary"]
    lines = [(entry["syllables"] or entry["word"]).capitalize()
             if entry["syllables"] else f'{entry["word"].capitalize()} (sem divisão silábica registrada)']

    morphs = query.morphemes(db, entry["id"])
    pieces, automatic = [], False
    if morphs:
        for m in morphs:
            g = None
            if m["lang"] in (None, lang):
                row = best_gloss(db, m["morph"], lang)
                if row is not None and row["gloss_lang"] == "pt":
                    g = row["gloss"]
                elif m["gloss"]:
                    g = f'{m["gloss"]} (en)'
                elif row is not None:
                    g = gloss_line(row)
                else:
                    g = query.morpheme_gloss(db, m["morph"], lang)
            else:
                g = f'{m["gloss"]} (en)' if m["gloss"] else None
                g = f"{lang_name(m['lang'])} — {g or 'sem glosa'}"
            pieces.append((m["morph"], g or "—"))
    else:
        seg = segment(db, entry["word"], lang)
        if seg:
            automatic = True
            for p in seg:
                if p["kind"] == "link":
                    pieces.append((f"-{p['morph']}-", "elemento de ligação"))
                    continue
                label = p["morph"] if p["lemma"] in (None, p["morph"]) else f'{p["morph"]} ({p["lemma"]})'
                g = p["gloss"] or "—"
                if p["source"] == "radicais.md":
                    used.append("radicais.md")
                pieces.append((label, g))

    if pieces:
        lines.append(" ".join(p[0] for p in pieces))
        lines.extend(f"{m}, {g}" for m, g in pieces)
    else:
        lines.append(entry["word"])
        lines.append("Sem divisão em morfemas registrada nem encontrada na tabela de afixos.")

    lines.append(f"Definição: {gloss_line(best_gloss(db, entry['word'], lang))}")
    if entry["etymology"]:
        lines.append(f"Etimologia: {entry['etymology']} (en)")
    if entry["etymology_pt"]:
        lines.append(f"Etimologia (pt.wiktionary): {entry['etymology_pt']}")
        used.append("pt.wiktionary")
    if automatic:
        lines.append("Atenção: segmentação automática pela tabela de afixos, não verificada.")
    lines.append(source_line(db, used))
    return "\n".join(lines)


def origin(db, word: str, lang: str) -> str:
    for e in query.lemma_entries(db, word, lang):
        ets = query.etymons(db, e["id"])
        direct = [x for x in ets if x["kind"] != "tree"]
        classic = [x for x in ets if x["kind"] == "tree" and x["lang"] in ("la", "grc") and not x["term"].startswith(("-", "*"))]
        picked = list(dict.fromkeys(f"{lang_name(x['lang'])} {x['term']}" for x in (direct + classic)[:3]))
        if picked:
            return ", ".join(picked)
    return ""


def adjective(db, noun: str, lang: str | None = None) -> str:
    try:
        lang = resolve_lang(db, noun, lang)
    except NotFound:
        if not lang:
            raise
    rows = query.adjectives_for(db, noun, lang)
    if not rows:
        return "\n".join([
            f'Adjetivo de "{noun}": nenhum encontrado nos dados.',
            "Não há forma erudita registrada; nenhuma forma foi inventada.",
            source_line(db, ["en.wiktionary", "pt.wiktionary"]),
        ])
    via_label = {"adjetivos-eruditos.md": "sua tabela", "pt-gloss": "glosa do pt.wiktionary",
                 "en-gloss": "glosa inglesa, conferir"}
    lines = [f'{noun} -> {", ".join(dict.fromkeys(r["adjective"].capitalize() for r in rows))}']
    used = []
    for r in rows:
        o = origin(db, r["adjective"], lang)
        note = f' — "{r["note"]}"' if r["note"] and r["via"] != "adjetivos-eruditos.md" else ""
        extra = f' — {r["note"]}' if r["note"] and r["via"] == "adjetivos-eruditos.md" else ""
        lines.append(f'{r["adjective"]}: {o or "origem não registrada"} [{via_label.get(r["via"], r["via"])}]{note}{extra}')
        used.append("adjetivos-eruditos.md" if r["via"] == "adjetivos-eruditos.md" else
                    "pt.wiktionary" if r["via"] == "pt-gloss" else "en.wiktionary")
    if len(rows) > 1:
        lines.append("Diferença de uso: não derivável dos dados.")
    lines.append(source_line(db, used))
    return "\n".join(lines)


def register_of(db, word: str, lang: str, tags: str) -> str:
    t = set(tags.split()) or query.register_tags(db, word, lang)
    if t & ERUDITE:
        return "Erudito"
    if t & COLLOQUIAL:
        return "Coloquial"
    return "Corrente"


def synonyms(db, word: str, lang: str | None = None) -> str:
    lang = resolve_lang(db, word, lang)
    entry, _ = lemma_of(db, word, lang)
    groups = {"Erudito": [], "Corrente": [], "Coloquial": []}
    used, seen = set(), set()
    for e in query.lemma_entries(db, entry["word"], lang):
        for r in query.relations(db, e["id"], "synonym"):
            if r["word"] in seen:
                continue
            seen.add(r["word"])
            used.add(f"{r['source']}.wiktionary")
            groups[register_of(db, r["word"], lang, r["tags"])].append(r["word"] + marks(r["tags"]))
    lines = [f'Sinônimos de "{entry["word"]}"']
    lines.extend(f"{k}: {', '.join(v) if v else '—'}" for k, v in groups.items())
    lines.append(NUANCE)
    root = query.same_root(db, entry["id"], lang)
    ets = [x for x in query.etymons(db, entry["id"]) if x["lang"] in ("la", "grc") and not x["term"].startswith(("-", "*"))]
    if root:
        tail = f" ({lang_name(ets[0]['lang'])} {ets[0]['term']})" if ets else ""
        lines.append(f"Mesmo radical: {', '.join(root)}{tail}")
    else:
        lines.append("Mesmo radical: —")
    lines.append(source_line(db, sorted(used) or ["en.wiktionary", "pt.wiktionary"]))
    return "\n".join(lines)


def _pick_inflections(entry, rows, lang) -> list[str]:
    out = []
    if entry["pos"] == "verb":
        wanted = [
            ("infinitivo", lambda t: "infinitive" in t and not t & {"first-person", "second-person", "third-person"}),
            ("particípio", lambda t: "participle" in t and "past" in t),
            ("gerúndio", lambda t: "gerund" in t or ("participle" in t and "present" in t)),
            ("1ª pres.", lambda t: {"first-person", "singular", "present"} <= t
             and not t & {"subjunctive", "imperative", "conditional"}),
        ]
        for label, test in wanted:
            hit = next((r for r in rows if test(set(r["tags"].split()))), None)
            if hit:
                out.append(f'{hit["form"]} ({label}){marks(hit["tags"])}')
        return out
    if lang == "de":
        cells = []
        for case, number in (("nominative", "singular"), ("genitive", "singular"), ("nominative", "plural"), ("genitive", "plural")):
            hit = next((r for r in rows if {case, number} <= set(r["tags"].split())), None)
            if hit:
                cells.append(f'{hit["form"]} ({CASE_ABBR[case]} {CASE_ABBR[number]})')
        if cells:
            return cells
    for r in rows:
        t = set(r["tags"].split())
        if t & set(DEGREE) or t & {"alternative", "abbreviation", "error"}:
            continue
        if t & {"plural", "singular", "feminine", "masculine", "neuter", "nominative", "genitive"}:
            out.append(r["form"] + marks(r["tags"]))
    return list(dict.fromkeys(out))


def other_forms(db, word: str, lang: str | None = None) -> str:
    lang = resolve_lang(db, word, lang)
    entry, form_entry = lemma_of(db, word, lang)
    candidates = query.lemma_entries(db, entry["word"], lang)
    if len(candidates) > 1:
        entry = max(candidates, key=lambda e: len(query.forms(db, e["id"])))
    lines = [f'Outras formas de "{entry["word"]}"']
    if form_entry is not None:
        lines.insert(0, f'"{word}" é forma flexionada de "{entry["word"]}".')
    rows = query.forms(db, entry["id"])
    infl = _pick_inflections(entry, rows, lang)
    lines.append(f"Flexões: {', '.join([entry['word']] + [x for x in infl if not x.startswith(entry['word'] + ' (inf')])}")
    degree = [f'{r["form"]} ({", ".join(DEGREE[t] for t in r["tags"].split() if t in DEGREE)}){marks(r["tags"])}'
              for r in rows if set(r["tags"].split()) & set(DEGREE)]
    degree = list(dict.fromkeys(degree))
    more = " …" if len(degree) > MAX_LIST else ""
    lines.append(f"Grau: {', '.join(degree[:MAX_LIST]) + more if degree else '—'}")
    adjs = query.adjectives_for(db, entry["word"], lang) if entry["pos"] == "noun" else []
    adj_names = [a["adjective"] + (" (?)" if a["via"] == "en-gloss" else "") for a in adjs]
    lines.append(f"Adjetivo: {', '.join(dict.fromkeys(adj_names)) if adjs else '—'}")
    derived = []
    for e in query.lemma_entries(db, entry["word"], lang):
        derived += [r["word"] + marks(r["tags"]) for r in query.relations(db, e["id"], "derived")]
    derived = sorted(dict.fromkeys(derived), key=lambda w: " " in w)
    lines.append(f"Derivadas: {', '.join(derived[:15]) if derived else '—'}")
    o = origin(db, entry["word"], lang)
    lines.append(f"Radical: {o or '—'}")
    cog = []
    for e in query.lemma_entries(db, entry["word"], lang):
        cog += [f"{r['lang']} {r['word']}" for r in query.relations(db, e["id"], "cognate")
                if r["lang"] in LANGS and r["lang"] != lang]
    if cog:
        lines.append(f"Cognatos: {', '.join(dict.fromkeys(cog))}")
    if any(a["via"] == "en-gloss" for a in adjs):
        lines.append("(?) = adjetivo achado pela glosa inglesa; conferir.")
    lines.append(source_line(db, [f"{entry['source']}.wiktionary"]))
    return "\n".join(lines)


def run(db, mode: str, word: str, lang: str | None = None) -> str:
    fn = {"desconstruir": deconstruct, "adjetivo": adjective, "sinonimo": synonyms, "formas": other_forms}[mode]
    return fn(db, word, lang)
