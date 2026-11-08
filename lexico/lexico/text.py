from __future__ import annotations

import unicodedata

LANGS = ("pt", "es", "de", "fr", "en")

LANG_NAMES = {
    "pt": "português", "es": "espanhol", "de": "alemão", "fr": "francês", "en": "inglês",
    "la": "lat.", "LL.": "lat. tardio", "ML.": "lat. medieval", "VL.": "lat. vulgar", "NL.": "lat. moderno",
    "la-lat": "lat. tardio", "la-med": "lat. medieval", "la-vul": "lat. vulgar", "la-new": "lat. moderno",
    "grc": "gr.", "el": "gr. moderno", "gem-pro": "protogermânico", "gmw-pro": "protogermânico ocidental", "goh": "alto-alemão antigo",
    "gmh": "alto-alemão médio", "ine-pro": "protoindo-europeu", "fro": "fr. antigo", "frm": "fr. médio",
    "roa-opt": "galego-português", "osp": "esp. antigo", "ang": "inglês antigo", "enm": "inglês médio",
    "ar": "árabe", "it": "it.", "gl": "galego", "ca": "catalão", "nl": "neerlandês", "tl": "tagalo",
    "tpw": "tupi antigo", "itc-pro": "protoitálico", "xno": "anglo-normando", "frk": "frâncico",
}


def key(word: str) -> str:
    decomposed = unicodedata.normalize("NFD", word.strip())
    bare = "".join(c for c in decomposed if not unicodedata.combining(c))
    return bare.casefold()


def tags_str(tags) -> str:
    return " ".join(sorted(set(tags or [])))


def lang_name(code: str | None) -> str:
    if not code:
        return ""
    return LANG_NAMES.get(code, code)
