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

- **Devices** view: one panel per switch or router. The front panel drawing
  shows every port (odd on top, even below), and the boxes under it hold the
  details. Click either one to edit.
- **Racks** view: each rack as patch panels (`PP1`…) by ports (`T01`…). A
  yellow dot marks a position with a desk recorded; a cyan top edge marks a
  position that a device port points to.
- The legend chips filter by state; `/` focuses the search box, which matches
  names, IPs, MACs, patch references and desk fields.
- In the port editor, **Patch panel** takes the spreadsheet's notation
  (`R1 PP8 T05`) and the connection chain under it shows the patch state and
  the desk. **Linked to device** connects two of your own devices (uplinks)
  and updates both ends.
- IPv4 and MAC addresses are validated; MACs are stored as `AA:BB:CC:DD:EE:FF`.
  A port whose IP or MAC is used by another port shows a warning.
- **Export** downloads the current data as JSON; **Import** replaces it with a
  JSON file (the server keeps a backup).

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
  `FFD966` is "Apenas link", bright red `FF0000` is "Danificado". Any other
  color becomes "Não identificado" with a warning.
- **Connected device** (`KIND_RULES`) is guessed from keywords in the name
  (`WIFI` → Access point, `Impressora` → Printer, `Switch`, `Gateway`,
  `Sala` → Room outlet). Names without a keyword (GUI, PESA, MUNIFE) are left
  blank.
- Every entry of the `CRÍTICOS` table is marked critical.
- `OVERRIDES` holds facts that are not in the sheet: Switch 1 port 2 is the
  uplink between the switches, with a note that the Switch 2 end is unknown.
- IP and MAC are not in the spreadsheet; they are typed in the page.

## Data file

```jsonc
{
  "version": 1, "revision": 7, "site": "Infra",
  "states":   [{ "id": "link_only", "label": "Apenas link", "color": "#ffb000", "pattern": "solid" }],
  "devices":  [{ "id": "sw1", "type": "switch", "name": "Switch 1", "ports": 24,
                 "port_data": { "5": { "state": "link_activity", "name": "Relacionamentos WIFI",
                                       "connected": "Access point", "ip": "", "mac": "",
                                       "patch": "R1 PP8 T05", "critical": true,
                                       "link": { "device": "sw2", "port": 1 }, "note": "" } } }],
  "racks":    [{ "id": "R1", "name": "Rack 1", "panels": 13, "ports_per_panel": 24,
                 "cells": { "PP8 T05": { "state": "unidentified", "note": "" } } }],
  "endpoints": [{ "patch": "R1 PP8 T05", "setor": "Relacionamentos (AP A)", "referencia": "Ponto Wifi",
                  "baia": "", "letra": "", "jack": "Endpoint", "cabling": "Íntegra" }]
}
```

Ports and patch positions with only default values are not stored. The
server checks the structure on every save (`validate()` in `server.py`).

## Extending

| to add | change |
|---|---|
| a device (another switch, a router) | **Add device** in the page; no code |
| a rack | **Add rack** in the Racks view |
| a kind of device (firewall, NVR…) | one entry in `DEVICE_TYPES`, `web/js/deviceTypes.js` |
| a state or a different color | the `states` list in the data file (and `STATES` in `import_xlsx.py` for new imports) |
| a port field (VLAN, speed…) | one entry in `PORT_FIELDS`, `web/js/model.js`; the editor and the boxes are built from it |
| a view (floor plan, VLAN table…) | a module exporting `{ id, label, icon, render(root) }`, listed in `VIEWS` in `web/js/main.js` |
| an API (ping, ARP lookup) | a new path in `make_handler()` in `server.py`, called from `web/js/api.js` |

## Layout

```
server.py            HTTP server, validation, atomic save + backups
import_xlsx.py       spreadsheet -> data/network.json
data/                network.example.json (committed), network.json + backups/ (ignored)
web/index.html
web/css/theme.css    colors, fonts, sizes (tokens)
web/css/app.css      layout and components
web/js/main.js       views, routing, header, keyboard shortcuts
web/js/model.js      data functions without DOM access (tested with node --test)
web/js/store.js      current document, change notifications, autosave
web/js/api.js        load/save requests
web/js/deviceTypes.js
web/js/views/        devicesView.js, racksView.js
web/js/components/   port card, faceplate, legend, editors, dialogs, drawer/toasts
tests/               pytest for server.py and import_xlsx.py
web/tests/           node --test for model.js
```

## Tests

```sh
pip install pytest openpyxl
python -m pytest -q tests
node --test web/tests/*.test.mjs
```
