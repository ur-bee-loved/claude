# Installation helpers. "make install" installs for the current user;
# "sudo make install PREFIX=/usr/local" installs system-wide.

PREFIX ?= $(HOME)/.local
PYTHON ?= python3
APP_ID  = io.github.omniconv.Omniconv
DATA    = omniconv/data

.PHONY: help install uninstall deps test lint run gui doctor

help:
	@echo "targets: deps install uninstall test lint run gui doctor"

deps:
	./scripts/install-deps.sh

install:
	$(PYTHON) -m pip install --user --break-system-packages ".[all]" 2>/dev/null || $(PYTHON) -m pip install --user ".[all]"
	install -Dm644 $(DATA)/$(APP_ID).desktop      $(PREFIX)/share/applications/$(APP_ID).desktop
	install -Dm644 $(DATA)/$(APP_ID).svg          $(PREFIX)/share/icons/hicolor/scalable/apps/$(APP_ID).svg
	install -Dm644 $(DATA)/$(APP_ID).metainfo.xml $(PREFIX)/share/metainfo/$(APP_ID).metainfo.xml
	-update-desktop-database $(PREFIX)/share/applications 2>/dev/null || true
	-gtk-update-icon-cache -q -t -f $(PREFIX)/share/icons/hicolor 2>/dev/null || true
	@echo "installed; run 'omniconv gui' or find Omniconv in your application menu"

uninstall:
	$(PYTHON) -m pip uninstall -y omniconv
	rm -f $(PREFIX)/share/applications/$(APP_ID).desktop \
	      $(PREFIX)/share/icons/hicolor/scalable/apps/$(APP_ID).svg \
	      $(PREFIX)/share/metainfo/$(APP_ID).metainfo.xml

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check omniconv tests

run:
	$(PYTHON) -m omniconv $(ARGS)

gui:
	$(PYTHON) -m omniconv gui

doctor:
	$(PYTHON) -m omniconv doctor
