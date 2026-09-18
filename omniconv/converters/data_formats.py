"""Structured data: JSON, YAML, TOML, XML, CSV/TSV, INI, plist, spreadsheets.

Every reader produces a plain Python object (dicts, lists, scalars) and
every writer consumes one, so any reader can be paired with any writer.
Tabular writers (CSV, TSV, XLSX) need a list of records; when the data has
another shape a clear error is raised instead of a mangled file.
"""

from __future__ import annotations

import configparser
import csv
import io
import json
import plistlib
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from omniconv.core.engine import Job
from omniconv.core.errors import ConversionError
from omniconv.core.registry import converter
from omniconv.core.requirements import AnyOf, Module

# ------------------------------------------------------------------ readers

def _read_bytes(job: Job) -> bytes:
    return job.source.read_bytes()


def _read_text(job: Job) -> str:
    enc = job.opt("encoding") or "utf-8-sig"
    try:
        return _read_bytes(job).decode(enc)
    except UnicodeDecodeError:
        return _read_bytes(job).decode("latin-1")


def _sniff_delimiter(sample: str, fallback: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return fallback


def _load_csv(job: Job, default_delim: str) -> list[dict[str, Any]]:
    text = _read_text(job)
    delim = job.opt("delimiter") or _sniff_delimiter(text[:4096], default_delim)
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    rows = []
    for row in reader:
        rows.append({k: _auto_scalar(v) for k, v in row.items() if k is not None})
    return rows


def _auto_scalar(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    s = value.strip()
    if s == "":
        return ""
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    try:
        if s.lstrip("-").isdigit():
            return int(s)
        return float(s)
    except ValueError:
        return value


def _xml_to_obj(elem: ET.Element) -> Any:
    children = list(elem)
    node: dict[str, Any] = {}
    for k, v in elem.attrib.items():
        node["@" + k] = v
    if not children:
        text = (elem.text or "").strip()
        if not node:
            return _auto_scalar(text)
        if text:
            node["#text"] = text
        return node
    for child in children:
        value = _xml_to_obj(child)
        if child.tag in node:
            if not isinstance(node[child.tag], list):
                node[child.tag] = [node[child.tag]]
            node[child.tag].append(value)
        else:
            node[child.tag] = value
    return node


def _obj_to_xml(tag: str, obj: Any, parent: ET.Element | None = None) -> ET.Element:
    elem = ET.Element(tag) if parent is None else ET.SubElement(parent, tag)
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.startswith("@"):
                elem.set(k[1:], str(v))
            elif k == "#text":
                elem.text = str(v)
            elif isinstance(v, list):
                for item in v:
                    _obj_to_xml(_safe_tag(k), item, elem)
            else:
                _obj_to_xml(_safe_tag(k), v, elem)
    elif isinstance(obj, list):
        for item in obj:
            _obj_to_xml("item", item, elem)
    elif obj is not None:
        elem.text = str(obj)
    return elem


def _safe_tag(name: str) -> str:
    out = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(name))
    if not out or out[0].isdigit() or out[0] in "-.":
        out = "_" + out
    return out


def _load_ini(job: Job) -> dict[str, dict[str, Any]]:
    cp = configparser.ConfigParser(interpolation=None)
    cp.optionxform = str  # keep key case
    cp.read_string(_read_text(job))
    data: dict[str, dict[str, Any]] = {}
    if cp.defaults():
        data["DEFAULT"] = {k: _auto_scalar(v) for k, v in cp.defaults().items()}
    for section in cp.sections():
        data[section] = {k: _auto_scalar(v) for k, v in cp.items(section) if k not in cp.defaults()}
    return data


def _load_xlsx(job: Job) -> Any:
    import openpyxl

    wb = openpyxl.load_workbook(str(job.source), read_only=True, data_only=True)
    sheet_opt = job.opt("sheet")
    sheets = {}
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            sheets[ws.title] = []
            continue
        header = [str(h) if h is not None else f"col{i + 1}" for i, h in enumerate(rows[0])]
        sheets[ws.title] = [dict(zip(header, r)) for r in rows[1:]]
    if sheet_opt is not None:
        key = sheet_opt if sheet_opt in sheets else list(sheets)[int(sheet_opt)] if str(sheet_opt).isdigit() else None
        if key is None:
            raise ConversionError(f"sheet not found: {sheet_opt}")
        return sheets[key]
    if len(sheets) == 1:
        return next(iter(sheets.values()))
    return sheets


def _load_sqlite(job: Job) -> Any:
    con = sqlite3.connect(f"file:{job.source}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    data = {}
    for t in tables:
        data[t] = [dict(r) for r in con.execute(f'SELECT * FROM "{t}"')]
    con.close()
    which = job.opt("sheet")
    if which is not None:
        if which not in data:
            raise ConversionError(f"table not found: {which}")
        return data[which]
    if len(data) == 1:
        return next(iter(data.values()))
    return data


def _load(job: Job) -> Any:
    src = job.src_format.name
    if src == "json":
        return json.loads(_read_text(job))
    if src == "jsonl":
        return [json.loads(line) for line in _read_text(job).splitlines() if line.strip()]
    if src == "yaml":
        import yaml

        docs = list(yaml.safe_load_all(_read_text(job)))
        return docs[0] if len(docs) == 1 else docs
    if src == "toml":
        import tomllib

        return tomllib.loads(_read_text(job))
    if src == "xml":
        root = ET.fromstring(_read_text(job).encode("utf-8"))
        return {root.tag: _xml_to_obj(root)}
    if src == "csv":
        return _load_csv(job, ",")
    if src == "tsv":
        return _load_csv(job, "\t")
    if src == "ini":
        return _load_ini(job)
    if src == "plist":
        return plistlib.loads(_read_bytes(job))
    if src == "xlsx":
        return _load_xlsx(job)
    if src == "sqlite":
        return _load_sqlite(job)
    if src == "msgpack":
        import msgpack

        return msgpack.unpackb(_read_bytes(job), raw=False)
    raise ConversionError(f"no reader for {src}")


# ------------------------------------------------------------------ writers

def _records(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list) and all(isinstance(r, dict) for r in data):
        return data
    if isinstance(data, list) and all(not isinstance(r, (dict, list)) for r in data):
        return [{"value": r} for r in data]
    if isinstance(data, dict):
        values = list(data.values())
        if values and all(isinstance(v, list) and all(isinstance(r, dict) for r in v) for v in values):
            # Several sheets/tables: flatten with a sheet column.
            out = []
            for name, rows in data.items():
                for r in rows:
                    out.append({"_sheet": name, **r})
            return out
        if all(not isinstance(v, (dict, list)) for v in values):
            return [data]
        return [{"key": k, "value": json.dumps(v) if isinstance(v, (dict, list)) else v} for k, v in data.items()]
    raise ConversionError("data is not tabular; convert to JSON/YAML instead")


def _columns(rows: list[dict[str, Any]]) -> list[str]:
    cols: list[str] = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    return cols


def _cell(v: Any) -> Any:
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return "" if v is None else v


def _write_csv(job: Job, data: Any, delim: str) -> None:
    rows = _records(data)
    cols = _columns(rows)
    with open(job.target, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter=job.opt("delimiter") or delim, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: _cell(r.get(k)) for k in cols})


def _write_ini(job: Job, data: Any) -> None:
    if not isinstance(data, dict):
        raise ConversionError("INI output needs a mapping of sections")
    cp = configparser.ConfigParser(interpolation=None)
    cp.optionxform = str
    flat = {}
    for k, v in data.items():
        if isinstance(v, dict):
            cp[k] = {str(kk): _cell(vv) if not isinstance(vv, bool) else str(vv).lower() for kk, vv in v.items()}
        else:
            flat[str(k)] = _cell(v)
    if flat:
        cp["DEFAULT"] = {k: str(v) for k, v in flat.items()}
    with open(job.target, "w", encoding="utf-8") as fh:
        cp.write(fh)


def _write_xlsx(job: Job, data: Any) -> None:
    import openpyxl

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    sheets: dict[str, list[dict[str, Any]]]
    if isinstance(data, dict) and data and all(isinstance(v, list) and all(isinstance(r, dict) for r in v) for v in data.values()):
        sheets = data
    else:
        sheets = {"Sheet1": _records(data)}
    for name, rows in sheets.items():
        ws = wb.create_sheet(title=str(name)[:31] or "Sheet")
        cols = _columns(rows)
        ws.append(cols)
        for r in rows:
            ws.append([_cell(r.get(c)) for c in cols])
    wb.save(str(job.target))


def _write_sqlite(job: Job, data: Any) -> None:
    if job.target.exists():
        job.target.unlink()
    con = sqlite3.connect(str(job.target))
    tables: dict[str, list[dict[str, Any]]]
    if isinstance(data, dict) and data and all(isinstance(v, list) and all(isinstance(r, dict) for r in v) for v in data.values()):
        tables = data
    else:
        tables = {job.source.stem.replace("-", "_").replace(" ", "_") or "data": _records(data)}
    for name, rows in tables.items():
        cols = _columns(rows)
        if not cols:
            continue
        safe = "".join(c if c.isalnum() or c == "_" else "_" for c in name)
        con.execute(f'CREATE TABLE "{safe}" ({", ".join(f"[{c}]" for c in cols)})')
        con.executemany(f'INSERT INTO "{safe}" VALUES ({", ".join("?" * len(cols))})', [[_cell(r.get(c)) for c in cols] for r in rows])
    con.commit()
    con.close()


def _write_html_table(job: Job, data: Any) -> None:
    import html as h

    rows = _records(data)
    cols = _columns(rows)
    parts = ["<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\"><style>table{border-collapse:collapse}td,th{border:1px solid #999;padding:.2em .5em}</style></head><body><table>"]
    parts.append("<tr>" + "".join(f"<th>{h.escape(str(c))}</th>" for c in cols) + "</tr>")
    for r in rows:
        parts.append("<tr>" + "".join(f"<td>{h.escape(str(_cell(r.get(c))))}</td>" for c in cols) + "</tr>")
    parts.append("</table></body></html>\n")
    job.target.write_text("\n".join(parts), encoding="utf-8")


def _write_md_table(job: Job, data: Any) -> None:
    rows = _records(data)
    cols = _columns(rows)
    esc = lambda v: str(v).replace("|", "\\|").replace("\n", " ")
    lines = ["| " + " | ".join(esc(c) for c in cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for r in rows:
        lines.append("| " + " | ".join(esc(_cell(r.get(c))) for c in cols) + " |")
    job.target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _dump(job: Job, data: Any) -> None:
    tgt = job.tgt_format.name
    indent = int(job.opt("indent", 2) or 2)
    if tgt == "json":
        job.target.write_text(json.dumps(data, indent=indent, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    elif tgt == "jsonl":
        rows = data if isinstance(data, list) else [data]
        job.target.write_text("".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows), encoding="utf-8")
    elif tgt == "yaml":
        import yaml

        job.target.write_text(yaml.safe_dump(json.loads(json.dumps(data, default=str)), sort_keys=False, allow_unicode=True, indent=indent), encoding="utf-8")
    elif tgt == "toml":
        import tomli_w

        if isinstance(data, list):
            # TOML has no top-level array; records become an array of tables.
            data = {"rows": data}
        if not isinstance(data, dict):
            raise ConversionError("TOML output needs a mapping at the top level")
        cleaned = json.loads(json.dumps(data, default=str))
        job.target.write_bytes(tomli_w.dumps(_strip_none(cleaned)).encode("utf-8"))
    elif tgt == "xml":
        if isinstance(data, dict) and len(data) == 1 and isinstance(next(iter(data.values())), (dict, list)):
            root_tag, body = next(iter(data.items()))
            root = _obj_to_xml(_safe_tag(root_tag), body)
        else:
            root = _obj_to_xml("root", data)
        ET.indent(root, space=" " * indent)
        job.target.write_bytes(b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="utf-8") + b"\n")
    elif tgt == "csv":
        _write_csv(job, data, ",")
    elif tgt == "tsv":
        _write_csv(job, data, "\t")
    elif tgt == "ini":
        _write_ini(job, data)
    elif tgt == "plist":
        job.target.write_bytes(plistlib.dumps(json.loads(json.dumps(data, default=str)), sort_keys=False))
    elif tgt == "xlsx":
        _write_xlsx(job, data)
    elif tgt == "sqlite":
        _write_sqlite(job, data)
    elif tgt == "html":
        _write_html_table(job, data)
    elif tgt == "md":
        _write_md_table(job, data)
    elif tgt == "msgpack":
        import msgpack

        job.target.write_bytes(msgpack.packb(json.loads(json.dumps(data, default=str)), use_bin_type=True))
    else:
        raise ConversionError(f"no writer for {tgt}")


def _strip_none(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_none(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_strip_none(v) for v in obj if v is not None]
    return obj


_PY_SOURCES = ("json", "jsonl", "yaml", "toml", "xml", "csv", "tsv", "ini", "plist")
_PY_TARGETS = ("json", "jsonl", "yaml", "toml", "xml", "csv", "tsv", "ini", "plist", "html", "md", "sqlite")


@converter(
    "python-data",
    _PY_SOURCES + ("sqlite",),
    _PY_TARGETS,
    cost=5,
    options=("indent", "delimiter", "encoding", "sheet"),
    description="Structured data conversion (JSON, YAML, TOML, XML, CSV, TSV, INI, plist, SQLite)",
    predicate=lambda s, t: s != t,
)
def data_convert(job: Job) -> list[Path]:
    try:
        data = _load(job)
    except ConversionError:
        raise
    except Exception as exc:
        raise ConversionError(f"cannot parse {job.src_format.name}: {exc}") from exc
    _dump(job, data)
    return [job.target]


@converter(
    "openpyxl",
    _PY_SOURCES + ("xlsx", "sqlite"),
    ("xlsx",) + _PY_TARGETS,
    requires=(Module("openpyxl", "openpyxl"),),
    cost=6,
    options=("indent", "delimiter", "encoding", "sheet"),
    description="Spreadsheet (XLSX) to and from structured data",
    predicate=lambda s, t: s != t and (s == "xlsx" or t == "xlsx"),
)
def xlsx_convert(job: Job) -> list[Path]:
    data = _load(job)
    _dump(job, data)
    return [job.target]


@converter(
    "msgpack",
    _PY_SOURCES + ("msgpack",),
    _PY_TARGETS + ("msgpack",),
    requires=(Module("msgpack", "msgpack"),),
    cost=7,
    description="MessagePack to and from structured data",
    predicate=lambda s, t: s != t and (s == "msgpack" or t == "msgpack"),
)
def msgpack_convert(job: Job) -> list[Path]:
    _dump(job, _load(job))
    return [job.target]


@converter("ipynb-export", ("ipynb",), ("json", "md", "txt"), cost=6, description="Jupyter notebook to JSON, Markdown or plain source text")
def ipynb_export(job: Job) -> list[Path]:
    nb = json.loads(_read_text(job))
    tgt = job.tgt_format.name
    if tgt == "json":
        job.target.write_text(json.dumps(nb, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return [job.target]
    parts = []
    for cell in nb.get("cells", []):
        src = "".join(cell.get("source", []))
        kind = cell.get("cell_type")
        if tgt == "md":
            if kind == "markdown":
                parts.append(src)
            elif kind == "code":
                lang = nb.get("metadata", {}).get("kernelspec", {}).get("language", "python")
                parts.append(f"```{lang}\n{src}\n```")
        else:
            if kind == "code":
                parts.append(src)
            else:
                parts.append("\n".join("# " + line for line in src.splitlines()))
    job.target.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
    return [job.target]
