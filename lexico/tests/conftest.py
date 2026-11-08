import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIX = Path(__file__).with_name("fixtures")
sys.path.insert(0, str(ROOT))

from lexico import build, query


@pytest.fixture(scope="session")
def db_path(tmp_path_factory):
    out = tmp_path_factory.mktemp("db") / "lexico.db"
    build.run(out, [str(FIX / "en.jsonl")], [str(FIX / "pt.jsonl")], str(FIX / "adjetivos.md"), str(FIX / "radicais.md"))
    return out


@pytest.fixture()
def db(db_path):
    conn = query.connect(db_path)
    yield conn
    conn.close()
