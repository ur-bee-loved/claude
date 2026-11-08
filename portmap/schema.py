"""Data model of the portmap file: states, validation and upgrades from older versions.

Shared by server.py (load and save) and import_xlsx.py (new files). Standard
library only.
"""

import re

SCHEMA_VERSION = 2

# Every port or patch position without a state is in this one.
DEFAULT_STATE = "unidentified"

# The states a new data file starts with. The file keeps its own copy, so a
# state can be recolored or renamed there without touching code.
STATES = [
    {"id": "in_use", "label": "Em uso", "color": "#2bff88", "pattern": "solid"},
    {"id": "enabled", "label": "Habilitada", "color": "#ffb000", "pattern": "solid"},
    {"id": "available", "label": "Disponível", "color": "#3d8bff", "pattern": "solid"},
    {"id": "vital", "label": "Vital", "color": "#ff2bd6", "pattern": "solid"},
    {"id": "damaged", "label": "Danificado", "color": "#ff3355", "pattern": "solid"},
    {"id": "gateway", "label": "Link Gateway", "color": "#e8eef8", "pattern": "solid"},
    {"id": "unidentified", "label": "Não identificado", "color": "#6f8196", "pattern": "hatched"},
]

# Values of a desk's "Status infra cabeada". The labels and colors are in
# web/js/model.js (CABLING_STATUSES); the server only stores the ids.
CABLING_IDS = ("ok", "partial", "no_socket", "not_installed", "unidentified")
DEFAULT_CABLING = "unidentified"

PATCH_RE = re.compile(r"^R\d+ PP\d+ T\d{2,}$")

# Text found in the spreadsheet or in version 1 files -> cabling id.
CABLING_TEXT = {
    "íntegra": "ok",
    "integra": "ok",
    "parcialmente danificada": "partial",
    "sem soquete": "no_socket",
    "não instalada": "not_installed",
    "nao instalada": "not_installed",
    "inexistente": "not_installed",
    "não identificada": "unidentified",
    "nao identificada": "unidentified",
}


def cabling_id(text):
    """Cabling id for a spreadsheet text, or None when it is not recognized."""
    return CABLING_TEXT.get(" ".join(str(text or "").split()).casefold())


def _is_int(v, lo, hi):
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def validate(doc):
    """Return a list of problems; an empty list means the document can be saved."""
    errors = []
    if not isinstance(doc, dict):
        return ["document must be a JSON object"]
    if doc.get("version") != SCHEMA_VERSION:
        errors.append(f"version must be {SCHEMA_VERSION}")

    states = doc.get("states")
    state_ids = set()
    if not isinstance(states, list) or not states:
        errors.append("states must be a non-empty list")
    else:
        for i, s in enumerate(states):
            if not isinstance(s, dict) or not all(isinstance(s.get(k), str) and s.get(k) for k in ("id", "label", "color")):
                errors.append(f"states[{i}] needs id, label and color")
            elif s["id"] in state_ids:
                errors.append(f"states[{i}]: duplicate id {s['id']!r}")
            else:
                state_ids.add(s["id"])
        if state_ids and DEFAULT_STATE not in state_ids:
            errors.append(f"states must include the default state {DEFAULT_STATE!r}")

    devices = doc.get("devices")
    if not isinstance(devices, list):
        errors.append("devices must be a list")
        devices = []
    ids = set()
    for i, d in enumerate(devices):
        where = f"devices[{i}]"
        if not isinstance(d, dict):
            errors.append(f"{where} must be an object")
            continue
        if not isinstance(d.get("id"), str) or not d["id"]:
            errors.append(f"{where}.id must be a non-empty string")
        elif d["id"] in ids:
            errors.append(f"{where}: duplicate id {d['id']!r}")
        else:
            ids.add(d["id"])
        if not isinstance(d.get("name"), str):
            errors.append(f"{where}.name must be a string")
        if not _is_int(d.get("ports"), 1, 512):
            errors.append(f"{where}.ports must be an integer from 1 to 512")
            continue
        port_data = d.get("port_data", {})
        if not isinstance(port_data, dict):
            errors.append(f"{where}.port_data must be an object")
            continue
        for key, port in port_data.items():
            if not key.isdigit() or not 1 <= int(key) <= d["ports"]:
                errors.append(f"{where}.port_data: port {key!r} is outside 1..{d['ports']}")
            elif not isinstance(port, dict):
                errors.append(f"{where}.port_data[{key}] must be an object")
            elif state_ids and port.get("state", DEFAULT_STATE) not in state_ids:
                errors.append(f"{where}.port_data[{key}]: unknown state {port.get('state')!r}")

    sizes = {d["id"]: d["ports"] for d in devices
             if isinstance(d, dict) and isinstance(d.get("id"), str) and _is_int(d.get("ports"), 1, 512)}
    for d in devices:
        if not isinstance(d, dict) or not isinstance(d.get("port_data"), dict):
            continue
        for key, port in d["port_data"].items():
            link = port.get("link") if isinstance(port, dict) else None
            if link is None:
                continue
            if not isinstance(link, dict) or link.get("device") not in sizes \
                    or not _is_int(link.get("port"), 1, sizes[link["device"]]):
                errors.append(f"device {d.get('id')!r} port {key}: link points at a missing device or port")

    racks = doc.get("racks")
    if not isinstance(racks, list):
        errors.append("racks must be a list")
        racks = []
    rack_ids = set()
    for i, r in enumerate(racks):
        where = f"racks[{i}]"
        if not isinstance(r, dict) or not isinstance(r.get("id"), str) or not re.fullmatch(r"R\d+", r.get("id", "")):
            errors.append(f"{where}.id must look like R1")
            continue
        if r["id"] in rack_ids:
            errors.append(f"{where}: duplicate id {r['id']!r}")
        rack_ids.add(r["id"])
        if not _is_int(r.get("panels"), 1, 64) or not _is_int(r.get("ports_per_panel"), 1, 96):
            errors.append(f"{where}: panels must be 1..64 and ports_per_panel 1..96")
        cells = r.get("cells", {})
        if not isinstance(cells, dict):
            errors.append(f"{where}.cells must be an object")
        elif state_ids:
            for key, cell in cells.items():
                if isinstance(cell, dict) and cell.get("state", DEFAULT_STATE) not in state_ids:
                    errors.append(f"{where}.cells[{key!r}]: unknown state {cell.get('state')!r}")

    # One desk per patch position: a map keyed by position cannot hold two.
    desks = doc.get("desks", {})
    if not isinstance(desks, dict):
        errors.append("desks must be an object keyed by patch position")
    else:
        for patch, desk in desks.items():
            if not PATCH_RE.match(str(patch)):
                errors.append(f"desks[{patch!r}]: the key must look like 'R1 PP8 T05'")
            elif not isinstance(desk, dict) or not all(isinstance(v, str) for v in desk.values()):
                errors.append(f"desks[{patch!r}] must be an object of text values")
    return errors


# ---------- upgrades ----------

V1_STATE_IDS = {"full_chain", "link_activity", "link_only", "available", "damaged", "vital", "gateway", "unidentified"}
V1_STATE_MAP = {
    "full_chain": "available",
    "link_activity": "in_use",
    "link_only": "enabled",
    "available": "unidentified",
    "unidentified": "unidentified",
}


def _add_note(doc, patch, text):
    """Append text to the note of a rack position, creating the position if needed."""
    rack_id, _, cell_key = str(patch).partition(" ")
    rack = next((r for r in doc.get("racks", []) if r.get("id") == rack_id), None)
    if rack is None:
        return
    cell = rack.setdefault("cells", {}).setdefault(cell_key, {"state": DEFAULT_STATE})
    cell["note"] = f"{cell['note']}\n{text}" if cell.get("note") else text


def _upgrade_v1(doc):
    """Version 1 -> 2: new state names (the old 'Disponível' and 'Não identificado'
    become one), 'critical' -> 'collective', and one desk per patch position
    instead of a list of endpoints."""
    custom = [s for s in doc.get("states", []) if s.get("id") not in V1_STATE_IDS]
    doc["states"] = [dict(s) for s in STATES] + custom

    def remap(item):
        if "state" in item:
            item["state"] = V1_STATE_MAP.get(item["state"], item["state"])

    for device in doc.get("devices", []):
        for port in device.get("port_data", {}).values():
            remap(port)
            if "critical" in port:
                port["collective"] = port.pop("critical")
    for rack in doc.get("racks", []):
        for cell in rack.get("cells", {}).values():
            remap(cell)

    desks = {}
    for e in doc.pop("endpoints", None) or []:
        patch = e.get("patch")
        if not isinstance(patch, str):
            continue
        desk = {k: str(e[k]) for k in ("setor", "referencia", "baia", "letra") if e.get(k)}
        status = str(e.get("cabling") or "").strip()
        if status:
            known = cabling_id(status)
            desk["cabling"] = known or DEFAULT_CABLING
            if known is None:
                _add_note(doc, patch, f"Status infra cabeada (antes): {status}")
        label = " · ".join(desk[k] for k in ("setor", "referencia", "baia", "letra") if k in desk)
        if patch in desks:
            _add_note(doc, patch, f"Segundo registro de mesa (removido): {label}")
        else:
            desks[patch] = desk
    doc["desks"] = desks
    doc["version"] = 2
    return doc


def migrate(doc):
    """Upgrade an older document and return it. A current document is returned as is."""
    if isinstance(doc, dict) and doc.get("version") == 1:
        return _upgrade_v1(doc)
    return doc
