# portmap

Interactive map of switch ports, patch panels and desks. Each device port has
its own box showing what is connected, its IP, MAC, reference name, patch-panel
position and the desk at the other end of the cable, colored by state.

The page is plain HTML, CSS and JavaScript modules (no framework, no build
step). `server.py` serves it and saves every edit to one JSON file. Python
3.10+, standard library only; `import_xlsx.py` also needs `openpyxl`.

```sh
pip install openpyxl                        # only for the import
./import_xlsx.py "Readequação Infra.xlsx"   # creates data/network.json
./server.py --open                          # http://localhost:8765/
```

Without `data/network.json` the page shows `data/network.example.json` (made-up
data) and the first edit creates the real file.

`data/network.json` and `data/backups/` are git-ignored: they hold device
names, IPs and MACs, and the repository is public.

## Using it

- **Devices** view: one panel per switch, router or modem. Click a panel's
  header to fold it to one line (name, port counts and a state bar), or use
  **Expand all / Collapse all**. The browser remembers which panels you left
  open; the first panel starts open the very first time.
- **Reordering:** drag a device by the grip at the left of its header and drop
  it above or below another one (the panels shrink while you drag). With the
  grip focused, ↑ and ↓ move it one place. The order is saved in the data
  file. Touch screens cannot drag; use the keyboard there.
- Inside a panel, the front-panel drawing shows every port (odd on top, even
  below; a yellow corner marks a port flagged *Infraestrutura coletiva*). Hover a port, or reach it
  with Tab, to see a summary card: name, connected device, IP, MAC, patch
  position, desk and note. Click it to edit.
- **Show port list** under the drawing opens the full boxes for that device,
  with every field visible at once.
- **Racks** view: the same folding panels, each rack drawn as patch panels
  (`PP1`…) by ports (`T01`…). A yellow dot marks a position with a desk
  recorded; a cyan top edge marks a position that a device port points to.
  Hovering a position shows its desk and wired ports.
- **Desk** (in a rack position's editor): every position has exactly one
  physical place, a fixed form with **Setor, Mesa, Baia, Letra** and a
  **Status infra cabeada** dropdown (*Íntegra*, *Parcialmente danificada*,
  *Sem soquete*, *Não instalada*, *Não identificada*). An empty status counts
  as *Não identificada* and is shown flagged with a warning mark. *Mesa* also
  holds the sheet's special cases (`Sala 1`, `Impressora`, `Ponto Wifi`…).
- The legend chips filter by state; `/` focuses the search box, which matches
  names, IPs, MACs, patch references and desk fields. While searching, panels
  with matches open by themselves and the others are dimmed.
- In the port editor, **Patch panel** takes the spreadsheet's notation
  (`R1 PP8 T05`) and the connection chain under it shows the patch state and
  the desk. **Linked to device** connects two of your own devices (uplinks)
  and updates both ends. Links in the chain jump to the other end and unfold
  its panel.
- The panel header counts **IDENTIFIED** ports: those not in the default
  state *Não identificado*.
- IPv4 and MAC addresses are validated; MACs are stored as `AA:BB:CC:DD:EE:FF`.
  A port whose IP or MAC is used by another port shows a warning in its box.
- **Export** downloads the current data as JSON; **Import** replaces it with a
  JSON file (the server keeps a backup).

Which panels are open is kept in the browser (`localStorage`), not in the
data file, so each person viewing the page keeps their own layout.

## States

| label | meaning in the sheet |
|---|---|
| Em uso | was "Link E atividade" |
| Habilitada | was "Apenas link" |
| Disponível | was "Cadeia completa funcional" |
| Vital | was "Infra vital" |
| Danificado | unchanged |
| Link Gateway | unchanged |
| Não identificado | the default for every port and position; was both "Disponível" and the cyan "Não identificado". Drawn hatched and muted. |

The states live in the data file (`states`), so a label or color can be
changed there. A port or position in the default state is not stored.

## Server

```sh
./server.py [--host 127.0.0.1] [-p 8765] [-d data/network.json] [--open] [-q]
```

- `--host 0.0.0.0` shares the page on the LAN. There is no login, so anyone who
  can reach the port can change the data.
- Every save writes the file atomically and keeps the previous version in
  `data/backups/` (last 30).
- Each save carries the revision it was based on. If the file changed in the
  meantime (another tab, a new import) the save is refused and the page asks
  you to reload, so nothing is overwritten silently.
- `-h`/`--h`/`--help`, `-V`/`--version`. Environment: `PORTMAP_HOST`,
  `PORTMAP_PORT`, `PORTMAP_DATA`.

## Spreadsheet import

```sh
./import_xlsx.py FILE.xlsx [-o data/network.json] [--force] [--site NAME]
                 [--switch-sheet NAME] [--desk-sheet NAME]
```

| sheet (default) | what is read |
|---|---|
| `Relação Rack - Switch nova` | `SWITCH n (N ports)` blocks: port numbers and their fill color; the `NOME / RACK / SWITCH (nº, porta)` table; `RACK n` grids with `PP`/`T` headers and their fill colors |
| `referência pré-mudança` | every table with `Endpoint` columns: Setor, Referência (or Local), Baia, Letra, the jacks' patch positions and "Status infra cabeada" |

Tables are found by their header text, so moving them inside the sheet is fine.
`--force` replaces an existing data file (after a backup). Anything that
could not be read is printed as a warning.

Choices the import makes, all at the top of `import_xlsx.py`:

- **Colors to states** (`FILL_TO_STATE`), from the legend in the rack sheet.
  Two colors are not in the legend and were confirmed separately: pale yellow
  `FFD966` is "Habilitada", bright red `FF0000` is "Danificado". White, no
  fill and the cyan of the sheet's "Não identificado" are all "Não
  identificado". Any other color is too, with a warning.
- **Connected device** (`KIND_RULES`) is guessed from keywords in the name
  (`WIFI` → Access point, `Impressora` → Printer, `Switch`, `Gateway`,
  `Sala` → Room outlet). Names without a keyword (GUI, PESA, MUNIFE) are left
  blank.
- Every entry of the `CRÍTICOS` table is marked *Infraestrutura coletiva*.
- `OVERRIDES` holds facts that are not in the sheet: Switch 1 port 2 is the
  uplink between the switches, with a note that the Switch 2 end is unknown.
- **Desks:** one record per patch position (Setor, Referência as *Mesa*,
  Baia, Letra, status). The sheet's "Endpoint 1/2" is not kept. If a position
  appears twice the first record wins and a warning is printed. Statuses are
  matched by text (`CABLING_TEXT` in `schema.py`); an unknown text becomes
  *Não identificada* with a warning, and "Inexistente" becomes *Não instalada*.
- IP and MAC are not in the spreadsheet; they are typed in the page.

## Data file

```jsonc
{
  "version": 2, "revision": 7, "site": "Infra",
  "states":   [{ "id": "enabled", "label": "Habilitada", "color": "#ffb000", "pattern": "solid" }],
  "devices":  [{ "id": "sw1", "type": "switch", "name": "Switch 1", "ports": 24,
                 "port_data": { "5": { "state": "in_use", "name": "Relacionamentos WIFI",
                                       "connected": "Access point", "ip": "", "mac": "",
                                       "patch": "R1 PP8 T05", "collective": true,
                                       "link": { "device": "sw2", "port": 1 }, "note": "" } } }],
  "racks":    [{ "id": "R1", "name": "Rack 1", "panels": 13, "ports_per_panel": 24,
                 "cells": { "PP8 T05": { "state": "vital", "note": "" } } }],
  "desks":    { "R1 PP8 T05": { "setor": "Relacionamentos", "referencia": "Ponto Wifi",
                               "baia": "", "letra": "", "cabling": "ok" } }
}
```

Ports and patch positions with only default values are not stored. `desks` is
keyed by patch position, so a position cannot have two. `cabling` is one of
`ok`, `partial`, `no_socket`, `not_installed`, `unidentified`. The order of
`devices` is the order on the page. The server checks the structure on every
save (`validate()` in `schema.py`).

**Older files are upgraded automatically.** A version 1 file (from before the
state renames and the single desk) is converted when the server loads it, and
written in the new format on the next save, with the old file kept in
`data/backups/`. The conversion maps the old states (the old "Disponível" and
"Não identificado" become one), renames `critical` to `collective`, and turns
the list of endpoints into one desk per position; anything it cannot map (an
unknown status, a second record for the same position) is copied into that
position's note. Importing an old JSON export goes through the same upgrade.

## Extending

| to add | change |
|---|---|
| a device (another switch, a router) | **Add device** in the page; no code |
| a rack | **Add rack** in the Racks view |
| a kind of device (firewall, NVR…) | one entry in `DEVICE_TYPES`, `web/js/deviceTypes.js` |
| a state or a different color | the `states` list in the data file (and `STATES` in `schema.py` for new files) |
| a port field (VLAN, speed…) | one entry in `PORT_FIELDS`, `web/js/model.js`; the editor and the boxes are built from it |
| a view (floor plan, VLAN table…) | a module exporting `{ id, label, icon, render(root) }`, listed in `VIEWS` in `web/js/main.js` |
| an API (ping, ARP lookup) | a new path in `make_handler()` in `server.py`, called from `web/js/api.js` |

## Layout

```
server.py            HTTP server, atomic save + backups
schema.py            data model: states, validation, upgrade of older files
import_xlsx.py       spreadsheet -> data/network.json
data/                network.example.json (committed), network.json + backups/ (ignored)
web/index.html
web/css/theme.css    colors, fonts, sizes (tokens)
web/css/app.css      layout and components
web/js/main.js       views, routing, header, keyboard shortcuts
web/js/model.js      data functions without DOM access (tested with node --test)
web/js/store.js      current document, change notifications, autosave
web/js/prefs.js      per-browser view preferences (open panels)
web/js/api.js        load/save requests
web/js/deviceTypes.js
web/js/views/        devicesView.js, racksView.js
web/js/components/   folding panel, faceplate, hover card, port box, legend, editors,
                     dialogs, drawer/toasts
tests/               pytest for server.py, schema.py and import_xlsx.py
web/tests/           node --test for model.js
```

## Tests

```sh
pip install pytest openpyxl
python -m pytest -q tests
node --test web/tests/*.test.mjs
```
