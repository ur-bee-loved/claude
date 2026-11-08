import pytest

from lexico import query, render
from lexico.segment import segment


def test_exact_spelling_wins_over_accent_free_key(db):
    assert [e["word"] for e in query.find_entries(db, "bucal", "pt")] == ["bucal"]
    assert [e["word"] for e in query.find_entries(db, "buçal", "pt")] == ["buçal"]


def test_accent_free_fallback(db):
    assert [e["word"] for e in query.find_entries(db, "sabio", "pt")] == ["sábio"]


def test_ambiguous_language(db):
    with pytest.raises(render.Ambiguous):
        render.run(db, "desconstruir", "fluvial")


def test_not_found(db):
    with pytest.raises(render.NotFound):
        render.run(db, "formas", "xyzzy", "pt")


def test_deconstruct_recorded(db):
    out = render.run(db, "desconstruir", "sombrinha", "pt").splitlines()
    assert out[0] == "Som-bri-nha"
    assert out[1] == "sombra -inha"
    assert out[2] == "sombra, espaço privado de luz"
    assert out[3] == "-inha, feminine diminutive suffix (en)"
    assert out[-1].startswith("Fonte: en.wiktionary")
    assert not any("automática" in line for line in out)


def test_deconstruct_automatic_is_flagged(db):
    out = render.run(db, "desconstruir", "hematopoese", "pt")
    assert out.splitlines()[0] == "He-ma-to-po-e-se"
    assert "hemato (hemato-), sangue (haîma, haímatos)" in out
    assert "não verificada" in out
    assert "radicais.md" in out.splitlines()[-1]


def test_segment_needs_known_pieces(db):
    assert segment(db, "fluvial", "pt") is None
    pieces = segment(db, "hematopoese", "pt")
    assert [p["morph"] for p in pieces] == ["hemato", "poese"]


def test_adjective_sources(db):
    out = render.run(db, "adjetivo", "rio", "pt")
    assert out.splitlines()[0] == "rio -> Fluvial"
    assert "glosa do pt.wiktionary" in out
    out = render.run(db, "adjetivo", "boca", "pt")
    assert "bucal" in out and "oral" in out and "sua tabela" in out


def test_adjective_none_found_says_so(db):
    out = render.run(db, "adjetivo", "sombra", "pt")
    assert "nenhum encontrado" in out


def test_synonym_registers(db):
    out = render.run(db, "sinonimo", "sábio", "pt").splitlines()
    assert "Erudito: sapiente" in out
    assert "Coloquial: sabichão" in out
    assert "Corrente: —" in out
    assert out[4].startswith("Nuance: —")


def test_other_forms_noun(db):
    out = render.run(db, "formas", "anjos", "pt").splitlines()
    assert out[0] == '"anjos" é forma flexionada de "anjo".'
    assert "Flexões: anjo, anjos, anja (raro)" in out
    assert "Grau: anjinho (dim.)" in out
    assert "Adjetivo: angelical" in out
    assert "Derivadas: anjo da guarda" in out
    assert "Cognatos: es ángel, fr ange" in out
    radical = next(line for line in out if line.startswith("Radical:"))
    assert "galego-português angeo" in radical and "gr. ἄγγελος (ángelos)" in radical


def test_other_forms_verb(db):
    out = render.run(db, "formas", "abater", "pt")
    assert "Flexões: abater, abatido (particípio), abatendo (gerúndio), abato (1ª pres.)" in out


def test_german_compound_keeps_noun_case(db):
    assert [p["morph"] for p in segment(db, "Handschuh", "de")] == ["Hand", "Schuh"]
    out = render.run(db, "desconstruir", "Handschuh", "de")
    assert "Hand Schuh" in out.splitlines()


def test_german_cases_shown_once(db):
    out = render.run(db, "formas", "Engel", "de").splitlines()
    assert "Flexões: Engel, Engel (nom. sg.), Engels (gen. sg.), Engel (nom. pl.), Engel (gen. pl.)" in out
    assert "Grau: Engelchen (dim.)" in out


def test_declension_tables_not_stored(db):
    forms = [r[0] for r in db.execute("SELECT form FROM form")]
    assert "Engeln" not in forms and "schönen" not in forms
    assert "schöner" in forms


def test_other_forms_prefers_entry_with_forms(db):
    out = render.run(db, "formas", "falar", "pt")
    assert "Flexões: falar, falado (particípio), falando (gerúndio), falo (1ª pres.)" in out
