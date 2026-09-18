"""Application object: sets up GTK, actions and the main window."""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from omniconv import __version__  # noqa: E402

APP_ID = "io.github.omniconv.Omniconv"


class OmniconvApplication(Adw.Application):
    def __init__(self, initial_files: list[str]) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.initial_files = initial_files
        self.window = None
        GLib.set_application_name("Omniconv")

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self._add_action("quit", lambda *_: self.quit(), "<Primary>q")
        self._add_action("about", self._on_about)
        self._add_action("backends", self._on_backends)
        self._add_action("add-files", lambda *_: self.window and self.window.open_file_dialog(), "<Primary>o")
        self._add_action("clear", lambda *_: self.window and self.window.clear_files())
        self._add_action("convert", lambda *_: self.window and self.window.start_conversion(), "<Primary>Return")

    def _add_action(self, name: str, callback, accel: str | None = None) -> None:
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        if accel:
            self.set_accels_for_action(f"app.{name}", [accel])

    def do_activate(self) -> None:
        from omniconv.gui.window import MainWindow

        if self.window is None:
            self.window = MainWindow(application=self)
            if self.initial_files:
                self.window.add_paths(self.initial_files)
        self.window.present()

    def do_open(self, files, n_files, hint) -> None:
        self.do_activate()
        self.window.add_paths([f.get_path() for f in files if f.get_path()])

    def _on_about(self, *_):
        about = Adw.AboutWindow(
            transient_for=self.window,
            application_name="Omniconv",
            application_icon="io.github.omniconv.Omniconv",
            developer_name="Omniconv contributors",
            version=__version__,
            comments="Convert files between image, audio, video, document, ebook, data, archive and font formats using the tools installed on your system.",
            website="https://github.com/ur-bee-loved/claude",
            license_type=Gtk.License.MIT_X11,
        )
        about.present()

    def _on_backends(self, *_):
        from omniconv.gui.window import BackendsWindow

        BackendsWindow(transient_for=self.window).present()


def run_app(files: list[str] | None = None) -> int:
    app = OmniconvApplication(list(files or []))
    return app.run([sys.argv[0]])
