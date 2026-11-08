# lexico: rules for Claude Code

## How to work

- This is an academic project. Explain each file before writing the next one; explaining and doing go side by side.
- Use plan mode for any change that touches more than one file: propose, wait for approval, then write.
- Never change, reword, move or delete a comment written by the user, in any file.
- Keep code comments and emoji to a minimum; add a comment only when the code cannot say it.
- Say when you are uncertain instead of sounding confident. Say when a claim rests on too few sources.
- Etymology is easy to get wrong with confidence. Report what the data says, mark what was inferred, and never invent a form.

## Architecture

- Two machines. The laptop downloads the kaikki.org extracts and builds `lexico.db` (`python -m lexico build`). The Raspberry Pi (2B or 3B, 1 GB RAM) only reads the finished database.
- No LLM anywhere. Everything the Pi prints comes from the database or from a fixed rule in the code.
- Runtime code (everything the Pi runs) uses the Python 3.9+ standard library only: `sqlite3`, `http.server`, `argparse`. No third-party packages on the Pi.
- Languages: pt, es, de, fr, en.
- Sources, both from kaikki.org (Wiktextract):
  - English Wiktionary extracts: etymology templates, morphemes, syllables, inflected forms, cognates. Glosses in English.
  - Portuguese Wiktionary extracts: Portuguese glosses and synonyms, merged onto the same (lang, word, pos).
- Every output ends with a `Fonte:` line. Automatic segmentation (the affix-table fallback) is always labelled as unverified.

## Layout

```
lexico/
  schema.sql   tables and indexes
  build.py     JSONL -> SQLite (laptop only)
  query.py     read-only lookups
  segment.py   affix-table fallback for words without a recorded split
  render.py    the four output formats of the lexico skill
  cli.py       command line
  web.py       http.server page
tests/         pytest, against hand-written fixtures shaped like real records
deploy/        systemd unit for the web page
fetch.sh       downloads the extracts (laptop only)
```

## Commands

```sh
./fetch.sh data                              # laptop: download extracts
python -m lexico build --out lexico.db data  # laptop: build the database
python -m lexico desconstruir sombrinha      # anywhere: query
python -m lexico serve --port 8080           # Pi: web page
python -m pytest -q tests
```
