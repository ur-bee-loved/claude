import pytest

from lexico.build import clean_etymology, ety_part, strip_tree_tail


def test_only_listed_languages_are_loaded(db):
    langs = {r[0] for r in db.execute("SELECT DISTINCT lang FROM entry")}
    assert langs == {"pt", "es", "de", "en"}


def test_ety_af_parts_and_inline_gloss(db):
    rows = db.execute(
        "SELECT morph, gloss FROM morpheme JOIN entry e ON e.id=entry_id WHERE e.word='sombrinha' ORDER BY n"
    ).fetchall()
    assert [tuple(r) for r in rows] == [("sombra", "shade; shadow"), ("-inha", None)]


def test_duplicate_ety_templates_counted_once(db):
    n = db.execute("SELECT COUNT(*) FROM morpheme JOIN entry e ON e.id=entry_id WHERE e.word='sombrinha'").fetchone()[0]
    assert n == 2


@pytest.mark.parametrize("raw, expected", [
    ("la:fluviālis", ("la", "fluviālis", {})),
    ("cento<t:hundred>", ("pt", "cento", {"t": "hundred"})),
    ("la-lat:angelicus<t:angelic><id:x>", ("la-lat", "angelicus", {"t": "angelic", "id": "x"})),
    ("globo<ety:la:globus<t:ball>>", ("pt", "globo", {"ety": "la:globus<t:ball>"})),
])
def test_ety_part(raw, expected):
    assert ety_part(raw, "pt") == expected


@pytest.mark.parametrize("raw, expected", [
    ("angelicuslbor.", "angelicus"),
    ("*h₂élisder.?", "*h₂élis"),
    ("θησαυρός (thēsaurós)bor.", "θησαυρός (thēsaurós)"),
    ("fluvius", "fluvius"),
])
def test_tree_tail(raw, expected):
    assert strip_tree_tail(raw) == expected


def test_etymology_tree_is_cut_from_prose():
    text = "Etymology tree\nLate Latin angelicuslbor.\nPortuguese angélico\nPortuguese angelical\nFrom angélico + -al."
    assert clean_etymology(text, "angelical", "pt") == "From angélico + -al."
    assert clean_etymology("From X.", "y", "pt") == "From X."


def test_tree_etymons_stored(db):
    rows = db.execute(
        "SELECT t.kind, t.lang, t.term FROM etymon t JOIN entry e ON e.id=t.entry_id WHERE e.word='angelical'"
    ).fetchall()
    assert ("tree", "la-lat", "angelicus") in [tuple(r) for r in rows]


def test_pt_merge_adds_portuguese_gloss_and_etymology(db):
    e = db.execute("SELECT id, etymology_pt, source FROM entry WHERE word='sombra' AND lang='pt'").fetchall()
    assert len(e) == 1 and e[0]["source"] == "en"
    assert e[0]["etymology_pt"] == "Do latim umbra."
    langs = [r[0] for r in db.execute("SELECT gloss_lang FROM sense WHERE entry_id=? ORDER BY n", (e[0]["id"],))]
    assert langs == ["en", "pt"]


def test_canonical_form_gives_syllables(db):
    syl = db.execute("SELECT syllables FROM entry WHERE word='hematopoese'").fetchone()[0]
    assert syl == "he-ma-to-po-e-se"


def test_inflected_form_keeps_link_not_sense(db):
    e = db.execute("SELECT id, is_form FROM entry WHERE word='anjos'").fetchone()
    assert e["is_form"] == 1
    assert db.execute("SELECT COUNT(*) FROM sense WHERE entry_id=?", (e["id"],)).fetchone()[0] == 0
    assert db.execute("SELECT lemma FROM form_of WHERE entry_id=?", (e["id"],)).fetchone()[0] == "anjo"


def test_table_tag_forms_dropped(db):
    forms = [r[0] for r in db.execute("SELECT form FROM form")]
    assert "no-table-tags" not in forms


def test_proper_name_adjectives_skipped(db):
    adjs = {r[0] for r in db.execute("SELECT adjective FROM adjective_of WHERE noun_key='rio'")}
    assert "fluvial" in adjs
    assert "rio-maiorense" not in adjs
    assert "renano" not in adjs


def test_meta_records_sources(db):
    meta = dict(db.execute("SELECT key, value FROM meta").fetchall())
    assert "en.wiktionary:en.jsonl" in meta["sources"]
    assert "user:radicais.md" in meta["sources"]


def test_english_relational_needs_relating_to(db):
    adjs = {r[0] for r in db.execute("SELECT adjective FROM adjective_of WHERE lang='en'")}
    assert {"riverine", "deltaic"} <= adjs
    assert "turgid" not in adjs


def test_syllable_separator_normalised(db):
    syl = db.execute("SELECT syllables FROM entry WHERE word='desafortunadamente'").fetchone()[0]
    assert syl == "De-sa-for-tu-na-da-men-te"
