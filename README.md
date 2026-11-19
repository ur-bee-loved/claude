# Apps (archived)

This repository is archived. Each app it held now has its own repository,
with its full history, CI workflow and README:

| App | What it does |
|---|---|
| [omniconv](https://github.com/ur-bee-loved/omniconv) | Desktop file converter for Linux and Windows (GTK 4 / Qt 6 window and a command line) that drives ffmpeg, ImageMagick, LibreOffice, pandoc and other installed tools |
| [netaudit](https://github.com/ur-bee-loved/netaudit) | Network monitoring with fping and mtr, stored in SQLite with UTC timestamps, plus SQL reports on loss, latency, availability and outages |
| [portmap](https://github.com/ur-bee-loved/portmap) | Browser map of switch ports, patch panels and desks (IP, MAC, name, state per port), served and saved by a small Python server, with an importer for the infrastructure spreadsheet |
| [lexico](https://github.com/ur-bee-loved/lexico) | Deterministic lexical-morphology lookup (morphemes, erudite adjectives, synonyms, other forms) for pt, es, de, fr and en, built from Wiktionary on a laptop and served from a Raspberry Pi |
| [assetscan](https://github.com/ur-bee-loved/assetscan) | USB-stick inventory for Windows: double-click on each PC to log its hardware (columns of the asset_manager_v3 hardware sheet) and installed programs; every run is kept on the stick and merged into hardware.csv and software.csv |
| [esp8266_stepper](https://github.com/ur-bee-loved/esp8266_stepper) | Arduino sketch that drives a 28BYJ-48 stepper through a ULN2003 board from an ESP8266 NodeMCU (D1, D2, D5, D6) |

Clone only the one you need; every command in its README runs from the
repository root:

```sh
git clone https://github.com/ur-bee-loved/omniconv
cd omniconv
```

## What is left here

The folders in this repository are the apps as they were when they were
split out on 2026-11-19, and they are no longer updated. Work, issues and
pull requests go to the repositories above.

The ESP8266 sketch was never merged into this branch; it is on the
`claude/bold-hypatia-jl0478` branch here.
