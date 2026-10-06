# Apps

A collection of independent applications. Each one lives in its own
folder with its own README, dependencies, tests and CI workflow, and
nothing is shared between them.

| App | What it does | Docs |
|---|---|---|
| [omniconv](omniconv/) | Desktop file converter for Linux and Windows (GTK 4 / Qt 6 window and a command line) that drives ffmpeg, ImageMagick, LibreOffice, pandoc and other installed tools | [omniconv/README.md](omniconv/README.md) |
| [netaudit](netaudit/) | Network monitoring with fping and mtr, stored in SQLite with UTC timestamps, plus SQL reports on loss, latency, availability and outages | [netaudit/README.md](netaudit/README.md) |

## Layout

```
.github/workflows/
  omniconv.yml     runs only when omniconv/ or this file changes
  netaudit.yml     runs only when netaudit/ or this file changes
omniconv/          pyproject.toml, Makefile, package, scripts, packaging, tests
netaudit/          netaudit.py, sql/, tests
```

Work inside an app's folder; every command in its README assumes that
folder is the current directory:

```sh
git clone https://github.com/ur-bee-loved/claude
cd claude/omniconv     # or claude/netaudit
```

## Adding an app

1. Create `<app>/` with its own `README.md`, tests and, if it has data or
   local configuration, its own `.gitignore`.
2. Add `.github/workflows/<app>.yml` with `paths: ["<app>/**",
   ".github/workflows/<app>.yml"]` and `defaults.run.working-directory:
   <app>`, so it runs only for its own changes.
3. Add a row to the table above.

## License

omniconv is MIT-licensed ([omniconv/LICENSE](omniconv/LICENSE)). See each
app's folder for its terms.
