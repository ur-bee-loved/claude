# lexico

Deterministic lexical-morphology lookup for Portuguese, Spanish, German,
French and English, built to run on a Raspberry Pi 2B/3B (1 GB RAM). It
reproduces the four modes of the `lexico` skill from Wiktionary data, with
no language model:

| Mode | Command (any alias) | Output |
|---|---|---|
| 1. Desconstrução | `desconstruir`, `deconstruct`, `descomponer`, `zerlegen`, `decomposer` | syllables, morphemes with glosses, definition, etymology |
| 2. Adjetivo erudito | `adjetivo`, `adjective`, `adjektiv`, `adjectif` | adjectives "relativo a X", with origin |
| 3. Sinônimos | `sinonimo`, `sinônimo`, `sinónimo`, `synonym`, `synonyme` | synonyms by register, same-root words |
| 4. Outras formas | `formas`, `outras-formas`, `other-forms`, `otras-formas`, `andere-formen`, `autres-formes` | inflections, degree, adjective, derived words, root, cognates |

```
$ python -m lexico desconstruir sombrinha -l pt
Som-bri-nha
sombra -inha
sombra, espaço privado de luz pela interposição de um corpo opaco entre ele e o objeto luminoso
-inha, sufixo formador de substantivos
Definição: guarda-chuva feminino
Etimologia: From sombra (“shade; shadow”) + -inha. (en)
Etimologia (pt.wiktionary): (Morfologia) sombra + -inha.
Fonte: en.wiktionary; pt.wiktionary (via kaikki.org, base de 2026-11-08)
```

## Two machines

The laptop downloads and processes the data; the Pi only reads the finished
database. Runtime code uses the Python 3.9+ standard library only.

### Laptop: build the database

```sh
./fetch.sh data                  # all five languages, about 7 GB of JSONL
./fetch.sh data "pt de"          # or only some
python -m lexico build data --out lexico.db \
    --adjetivos ~/path/to/lexico/references/adjetivos-eruditos.md \
    --radicais  ~/path/to/lexico/references/radicais.md
```

`--adjetivos` and `--radicais` load the reference tables from your `lexico`
skill. They are optional; rows from them are shown as "sua tabela" and take
precedence over Wiktionary. `--all-forms` keeps the full conjugation and
declension tables (by default only the forms that mode 4 prints are stored).
The build streams each file line by line, so memory stays flat.

Measured in the cloud container used for development, not on a laptop:

| Languages | Build time | Peak RAM | `lexico.db` |
|---|---|---|---|
| pt | 30 s | 21 MB | 207 MB |
| pt + de | 54 s | not measured | 365 MB |
| pt, es, de, fr, en | 191 s | 39 MB | 1.25 GB |

The five-language database holds 3.7 million entries. It fits on any SD card
that holds Raspberry Pi OS; to make it smaller, fetch and build fewer
languages (English alone is about half of the input).

### Raspberry Pi: copy and run

```sh
rsync -av --exclude data --exclude '*.db' ./ pi@raspberrypi.local:lexico/
rsync -av --progress lexico.db pi@raspberrypi.local:lexico/
ssh pi@raspberrypi.local
cd lexico
python3 -m lexico formas anjo -l pt
python3 -m lexico serve --host 0.0.0.0 --port 8080
```

Raspberry Pi OS Lite already has Python 3 with `sqlite3`; nothing else needs
installing. To keep the web page running:

```sh
sudo cp deploy/lexico-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lexico-web
```

The unit assumes user `pi` and the folder `/home/pi/lexico`; edit it if
yours differ. The page is at `http://<pi>:8080/`, and `/txt?w=anjo&m=formas&l=pt`
returns plain text for `curl`. There is no authentication: keep it on the LAN.

Lookups averaged 1.1 ms on the five-language database on the development
machine. It has not been measured on a Pi; expect it to be several times
slower, which should still be well under a second. The first query after boot
will be slower while the SD card is read.

## Sources

| Source | kaikki.org path | Gives |
|---|---|---|
| English Wiktionary | `dictionary/<Language>/` | etymology templates, morphemes, syllables, forms, cognates; glosses in English |
| Portuguese Wiktionary | `ptwiktionary/<Língua>/` | Portuguese glosses, synonyms, etymology text, syllables (`canonical` form) |

Entries are merged on (language, word, part of speech). Glosses from the
English Wiktionary are marked `(en)`. The Portuguese-Wiktionary extracts for
es, de, fr and en are small (4 to 13 MB, against 343 MB for Portuguese), so
words in those languages mostly have English glosses.

Wiktionary text is licensed CC BY-SA 4.0 (and GFDL). A database built from it
is a derived work: keep the attribution if you share it. This is a general
reading of the licence, not legal advice.

## What the deterministic version does not do

- **Induced meaning.** "Definição" is the dictionary's first sense, not a
  definition constructed from the morphemes. That step needs judgement.
- **Nuance between synonyms and usage differences between adjectives.**
  Printed as "não derivável dos dados".
- **Register for untagged synonyms.** A synonym goes to Erudito or Coloquial
  only when Wiktionary tags it (`formal`, `literary`, `colloquial`, ...);
  everything else is listed as Corrente.
- **The `Literal:` line.** Deciding when the induced sense diverges from the
  literal one is a judgement; the etymology is printed instead.
- **"Mesmo radical"** only finds words whose Wiktionary etymology names the
  same Latin, Greek or Germanic term. *sábio* (lat. *sapidus*) and *sapiente*
  (lat. *sapiens*) are not linked, although both go back to *sapere*.

## How morphemes are found

1. The English Wiktionary's own split (`{{ety|...|:af|...}}`, `{{af}}`,
   `{{suffix}}`, `{{compound}}`, ...). About 19,000 Portuguese lemmas have one.
2. Otherwise, automatic segmentation (`segment.py`): the fewest pieces that are
   all known prefixes, suffixes, roots from `radicais.md`, or stems of existing
   words (`sombr` + a = `sombra`), with German linking elements (`-s-`, `-en-`, ...).
   The output always says "segmentação automática ... não verificada". Its
   accuracy has not been measured; treat it as a suggestion.

## Data quirks found while building

These showed up only when the code ran against the real extracts (November 2026):

- The English Wiktionary moved most etymologies to a new `{{ety}}` template:
  operation in argument `2` (`:af`, `:lbor`, `:inh`, ...) and parts as
  `lang:term<t:gloss>`, with nesting. The older `inh`/`bor`/`af` templates
  still appear on some entries; both are parsed.
- `etymology_text` starts with a flattened "Etymology tree". The prose is the
  part after the line `<Language> <word>`.
- In that tree the relation label is glued to the term (`Late Latin angelicuslbor.`).
  The label is stripped by frequency (`lbor` before the rare `slbor`), which
  can still cut a term wrongly.
- Accent-free lookup merges distinct words (*bucal* / *buçal*); exact spelling
  is now tried first.
- Gloss patterns like "relativo a Rio Maior" produce place-name adjectives; a
  capitalised word after the noun is skipped.
- English glosses use "Of a river, ..." to mean "said of rivers" (*turgid*,
  *up*), so only "relating / pertaining / belonging / concerning to" counts.
  The capture is still one word, so "relating to a river delta" (*deltaic*) is
  listed under *river*.
- Some Spanish records store the syllable split as one string with `‧`;
  separators are normalised to hyphens.
- Full German adjective declension tables account for millions of form rows;
  only the forms mode 4 uses are kept by default.

## Layout

```
lexico/
  schema.sql   tables and indexes
  build.py     JSONL -> SQLite (laptop)
  text.py      language list, lookup key, language names
  query.py     read-only lookups
  segment.py   affix-table fallback
  render.py    the four output formats
  cli.py       command line
  web.py       http.server page
tests/         pytest, with hand-written fixtures shaped like real records
deploy/        systemd unit
fetch.sh       downloads the extracts
CLAUDE.md      working rules for Claude Code in this folder
```

## Tests

```sh
python -m pytest -q tests
python -m ruff check --isolated --line-length 120 lexico tests
```

The fixtures in `tests/fixtures/` are hand-written imitations of Wiktextract
records, not copies; they reproduce the quirks listed above so CI does not need
the 7 GB download.
