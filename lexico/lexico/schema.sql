PRAGMA foreign_keys = ON;

CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE entry (
    id           INTEGER PRIMARY KEY,
    lang         TEXT    NOT NULL,
    word         TEXT    NOT NULL,
    word_key     TEXT    NOT NULL,
    pos          TEXT    NOT NULL,
    etym_no      INTEGER NOT NULL DEFAULT 0,
    syllables    TEXT,
    etymology    TEXT,
    etymology_pt TEXT,
    is_form      INTEGER NOT NULL DEFAULT 0,
    source       TEXT    NOT NULL
);
CREATE INDEX entry_key  ON entry (word_key, lang);
CREATE INDEX entry_word ON entry (lang, word, pos);

CREATE TABLE sense (
    entry_id   INTEGER NOT NULL REFERENCES entry (id),
    n          INTEGER NOT NULL,
    gloss      TEXT    NOT NULL,
    gloss_lang TEXT    NOT NULL,
    tags       TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX sense_entry ON sense (entry_id);

CREATE TABLE form (
    entry_id INTEGER NOT NULL REFERENCES entry (id),
    form     TEXT    NOT NULL,
    tags     TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX form_entry ON form (entry_id);

CREATE TABLE form_of (
    entry_id INTEGER NOT NULL REFERENCES entry (id),
    lemma    TEXT    NOT NULL,
    tags     TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX form_of_entry ON form_of (entry_id);

CREATE TABLE morpheme (
    entry_id INTEGER NOT NULL REFERENCES entry (id),
    n        INTEGER NOT NULL,
    morph    TEXT    NOT NULL,
    gloss    TEXT,
    lang     TEXT
);
CREATE INDEX morpheme_entry ON morpheme (entry_id);

CREATE TABLE etymon (
    entry_id INTEGER NOT NULL REFERENCES entry (id),
    n        INTEGER NOT NULL,
    kind     TEXT    NOT NULL,
    lang     TEXT    NOT NULL,
    term     TEXT    NOT NULL,
    gloss    TEXT
);
CREATE INDEX etymon_entry ON etymon (entry_id);
CREATE INDEX etymon_term  ON etymon (lang, term);

CREATE TABLE relation (
    entry_id INTEGER NOT NULL REFERENCES entry (id),
    kind     TEXT    NOT NULL,
    word     TEXT    NOT NULL,
    lang     TEXT    NOT NULL,
    tags     TEXT    NOT NULL DEFAULT '',
    source   TEXT    NOT NULL
);
CREATE INDEX relation_entry ON relation (entry_id, kind);

CREATE TABLE affix (
    lang       TEXT NOT NULL,
    affix      TEXT NOT NULL,
    kind       TEXT NOT NULL,
    gloss      TEXT,
    gloss_lang TEXT,
    source     TEXT NOT NULL
);
CREATE INDEX affix_lang ON affix (lang);

CREATE TABLE adjective_of (
    lang     TEXT NOT NULL,
    noun_key TEXT NOT NULL,
    adjective TEXT NOT NULL,
    via      TEXT NOT NULL,
    note     TEXT
);
CREATE INDEX adjective_of_noun ON adjective_of (lang, noun_key);
