import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import schema

V1 = {
    "version": 1,
    "revision": 4,
    "site": "Old",
    "states": [
        {"id": "full_chain", "label": "Cadeia completa funcional", "color": "#3d8bff"},
        {"id": "available", "label": "Disponível", "color": "#8a96ab"},
        {"id": "custom", "label": "Meu estado", "color": "#123456"},
    ],
    "devices": [{"id": "sw", "type": "switch", "name": "SW", "ports": 4, "port_data": {
        "1": {"state": "link_activity", "name": "A", "critical": True, "ip": "10.0.0.1"},
        "2": {"state": "available", "name": "B"},
        "3": {"state": "custom"},
    }}],
    "racks": [{"id": "R1", "name": "Rack", "panels": 2, "ports_per_panel": 4, "cells": {
        "PP1 T01": {"state": "full_chain"},
        "PP1 T02": {"state": "unidentified"},
        "PP1 T03": {"state": "link_only", "note": "antiga"},
    }}],
    "endpoints": [
        {"patch": "R1 PP1 T01", "setor": "Sales", "referencia": "Mesa 1", "baia": "1", "letra": "A",
         "jack": "Endpoint 1", "cabling": "Íntegra"},
        {"patch": "R1 PP1 T02", "referencia": "Sala 1", "cabling": "Parcialmente Danificada "},
        {"patch": "R1 PP1 T03", "referencia": "Mesa 2", "cabling": "estranho"},
        {"patch": "R1 PP1 T01", "referencia": "Mesa 9", "jack": "Endpoint 2", "cabling": "Íntegra"},
    ],
}


@pytest.fixture
def upgraded():
    return schema.migrate(copy.deepcopy(V1))


def test_upgrade_result_is_valid(upgraded):
    assert upgraded["version"] == 2
    assert upgraded["revision"] == 4
    assert schema.validate(upgraded) == []


def test_upgrade_states(upgraded):
    ids = [s["id"] for s in upgraded["states"]]
    assert ids == [s["id"] for s in schema.STATES] + ["custom"]
    port = upgraded["devices"][0]["port_data"]
    assert port["1"]["state"] == "in_use"
    assert port["2"]["state"] == schema.DEFAULT_STATE
    assert port["3"]["state"] == "custom"
    cells = upgraded["racks"][0]["cells"]
    assert [cells[k]["state"] for k in ("PP1 T01", "PP1 T02", "PP1 T03")] == ["available", "unidentified", "enabled"]


def test_upgrade_renames_critical_and_keeps_typed_data(upgraded):
    p = upgraded["devices"][0]["port_data"]["1"]
    assert p["collective"] is True and "critical" not in p
    assert p["ip"] == "10.0.0.1" and p["name"] == "A"


def test_upgrade_desks(upgraded):
    desks = upgraded["desks"]
    assert "endpoints" not in upgraded
    assert desks["R1 PP1 T01"] == {"setor": "Sales", "referencia": "Mesa 1", "baia": "1", "letra": "A", "cabling": "ok"}
    assert desks["R1 PP1 T02"]["cabling"] == "partial"
    assert desks["R1 PP1 T03"]["cabling"] == "unidentified"


def test_upgrade_keeps_what_it_cannot_map_in_notes(upgraded):
    cells = upgraded["racks"][0]["cells"]
    assert "estranho" in cells["PP1 T03"]["note"] and cells["PP1 T03"]["note"].startswith("antiga")
    assert "Mesa 9" in cells["PP1 T01"]["note"]


def test_upgrade_is_idempotent(upgraded):
    again = schema.migrate(copy.deepcopy(upgraded))
    assert again == upgraded


@pytest.mark.parametrize("text, expected", [
    ("Íntegra", "ok"), ("  integra ", "ok"), ("Parcialmente Danificada", "partial"),
    ("sem soquete", "no_socket"), ("Não instalada", "not_installed"), ("Inexistente", "not_installed"),
    ("Não identificada", "unidentified"), ("outra coisa", None), ("", None), (None, None),
])
def test_cabling_id(text, expected):
    assert schema.cabling_id(text) == expected
