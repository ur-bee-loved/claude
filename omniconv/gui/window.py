"""Main window.

Layout: a file list on the left (drop files onto it), a settings sidebar on
the right (target format, output folder, options) and a convert button.
Conversions run on a worker thread; results are marshalled back to the GTK
main loop with ``GLib.idle_add``.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk  # noqa: E402

from omniconv.core import formats  # noqa: E402
from omniconv.core.engine import ENGINE, Result  # noqa: E402
from omniconv.core.formats import Format  # noqa: E402
from omniconv.core.options import OPTION_SPECS, OptionSpec  # noqa: E402
from omniconv.core.registry import REGISTRY  # noqa: E402
from omniconv.core.sniff import detect  # noqa: E402

CATEGORY_LABELS = {
    "image": "Image",
    "vector": "Vector graphics",
    "audio": "Audio",
    "video": "Video",
    "subtitle": "Subtitles",
    "document": "Document",
    "ebook": "E-book",
    "data": "Data",
    "archive": "Archive",
    "font": "Font",
    "model": "3D model",
}
CATEGORY_ORDER = {c: i for i, c in enumerate(formats.CATEGORIES)}
# Reasonable default target per category, tried in order.
PREFERRED_TARGETS = {
    "image": ("png", "jpeg", "webp", "pdf"),
    "vector": ("png", "pdf", "svg"),
    "audio": ("mp3", "flac", "wav", "ogg"),
    "video": ("mp4", "mkv", "webm", "gif"),
    "subtitle": ("srt", "vtt"),
    "document": ("pdf", "docx", "html", "txt"),
    "ebook": ("epub", "pdf", "mobi"),
    "data": ("json", "csv", "yaml"),
    "archive": ("zip", "tar.gz", "7z"),
    "font": ("woff2", "woff", "ttf"),
    "model": ("glb", "obj", "stl"),
}
CATEGORY_ICONS = {
    "image": "image-x-generic-symbolic",
    "vector": "image-x-generic-symbolic",
    "audio": "audio-x-generic-symbolic",
    "video": "video-x-generic-symbolic",
    "subtitle": "text-x-generic-symbolic",
    "document": "x-office-document-symbolic",
    "ebook": "x-office-document-symbolic",
    "data": "text-x-generic-symbolic",
    "archive": "package-x-generic-symbolic",
    "font": "font-x-generic-symbolic",
    "model": "applications-graphics-symbolic",
}


def _human_size(n: int) -> str:
    for unit in ("B", "kB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


class FileEntry(GObject.Object):
    """One input file and its conversion state."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path
        self.format: Format | None = detect(path)
        self.status = "queued"
        self.message = ""
        self.result: Result | None = None


class FileRow(Adw.ActionRow):
    def __init__(self, entry: FileEntry, on_remove) -> None:
        super().__init__()
        self.entry = entry
        self.set_title(GLib.markup_escape_text(entry.path.name))
        self.set_title_lines(1)
        fmt = entry.format
        size = _human_size(entry.path.stat().st_size) if entry.path.exists() else ""
        subtitle = f"{fmt.name.upper()} · {fmt.description} · {size}" if fmt else f"Unknown format · {size}"
        self.set_subtitle(GLib.markup_escape_text(subtitle))
        icon = Gtk.Image.new_from_icon_name(CATEGORY_ICONS.get(fmt.category, "text-x-generic-symbolic") if fmt else "dialog-question-symbolic")
        self.add_prefix(icon)
        self.status_label = Gtk.Label(label="", css_classes=["dim-label", "caption"], xalign=1)
        self.status_label.set_ellipsize(3)
        self.status_label.set_max_width_chars(28)
        self.spinner = Gtk.Spinner()
        self.status_icon = Gtk.Image()
        remove = Gtk.Button(icon_name="edit-delete-symbolic", css_classes=["flat"], valign=Gtk.Align.CENTER, tooltip_text="Remove")
        remove.connect("clicked", lambda *_: on_remove(self))
        self.remove_button = remove
        box = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
        box.append(self.status_label)
        box.append(self.spinner)
        box.append(self.status_icon)
        box.append(remove)
        self.add_suffix(box)
        self.refresh()

    def refresh(self) -> None:
        e = self.entry
        self.spinner.set_visible(e.status == "running")
        if e.status == "running":
            self.spinner.start()
        else:
            self.spinner.stop()
        self.status_icon.set_visible(e.status in ("done", "failed"))
        if e.status == "done":
            self.status_icon.set_from_icon_name("emblem-ok-symbolic")
            self.status_icon.remove_css_class("error")
            self.status_icon.add_css_class("success")
        elif e.status == "failed":
            self.status_icon.set_from_icon_name("dialog-error-symbolic")
            self.status_icon.remove_css_class("success")
            self.status_icon.add_css_class("error")
        self.status_label.set_text(e.message)
        self.status_label.set_tooltip_text(e.message)
        self.remove_button.set_sensitive(e.status != "running")


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.set_title("Omniconv")
        self.set_default_size(980, 640)
        self.set_size_request(640, 420)
        self.entries: list[FileEntry] = []
        self.rows: list[FileRow] = []
        self.option_widgets: dict[str, tuple[OptionSpec, Any]] = {}
        self.target_names: list[str] = []
        self.output_dir: Path | None = None
        self.worker: threading.Thread | None = None
        self.cancel_flag = threading.Event()
        from omniconv.converters import load_all

        load_all()
        self._build()

    # ------------------------------------------------------------ building
    def _build(self) -> None:
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)
        toolbar = Adw.ToolbarView()
        self.toast_overlay.set_child(toolbar)

        header = Adw.HeaderBar()
        add_btn = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="Add files (Ctrl+O)")
        add_btn.connect("clicked", lambda *_: self.open_file_dialog())
        header.pack_start(add_btn)
        menu = Gio.Menu()
        menu.append("Backends and formats", "app.backends")
        menu.append("Clear list", "app.clear")
        menu.append("About Omniconv", "app.about")
        menu.append("Quit", "app.quit")
        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        header.pack_end(menu_btn)
        toolbar.add_top_bar(header)

        split = Adw.OverlaySplitView(sidebar_position=Gtk.PackType.END, min_sidebar_width=320, max_sidebar_width=400, sidebar_width_fraction=0.36)
        toolbar.set_content(split)
        split.set_content(self._build_file_pane())
        split.set_sidebar(self._build_sidebar())

        bottom = Gtk.ActionBar()
        self.summary_label = Gtk.Label(label="Drop files here or click + to begin", css_classes=["dim-label"], xalign=0, hexpand=True)
        self.summary_label.set_ellipsize(3)
        bottom.pack_start(self.summary_label)
        self.open_folder_button = Gtk.Button(label="Open output folder", visible=False)
        self.open_folder_button.connect("clicked", self._open_output_folder)
        bottom.pack_end(self.open_folder_button)
        self.cancel_button = Gtk.Button(label="Cancel", visible=False)
        self.cancel_button.connect("clicked", lambda *_: self.cancel_flag.set())
        bottom.pack_end(self.cancel_button)
        self.convert_button = Gtk.Button(label="Convert", css_classes=["suggested-action"], sensitive=False)
        self.convert_button.connect("clicked", lambda *_: self.start_conversion())
        bottom.pack_end(self.convert_button)
        toolbar.add_bottom_bar(bottom)

    def _build_file_pane(self) -> Gtk.Widget:
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.empty = Adw.StatusPage(
            icon_name="document-send-symbolic",
            title="No files yet",
            description="Drag files here, or press the + button. Then pick a target format on the right.",
        )
        pick = Gtk.Button(label="Add files…", css_classes=["pill", "suggested-action"], halign=Gtk.Align.CENTER)
        pick.connect("clicked", lambda *_: self.open_file_dialog())
        self.empty.set_child(pick)
        self.stack.add_named(self.empty, "empty")

        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"], valign=Gtk.Align.START)
        clamp = Adw.Clamp(maximum_size=900, margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        clamp.set_child(self.listbox)
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        scroller.set_child(clamp)
        self.stack.add_named(scroller, "list")
        self.stack.set_visible_child_name("empty")

        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.connect("drop", self._on_drop)
        self.stack.add_controller(drop)
        return self.stack

    def _build_sidebar(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()

        group = Adw.PreferencesGroup(title="Target")
        self.target_row = Adw.ComboRow(title="Convert to", subtitle="Formats reachable from every listed file")
        self.target_row.set_enable_search(True)
        self.target_row.set_expression(Gtk.PropertyExpression.new(Gtk.StringObject, None, "string"))
        self.target_row.connect("notify::selected", lambda *_: self._on_target_changed())
        group.add(self.target_row)
        self.route_row = Adw.ActionRow(title="Route", subtitle="—", subtitle_lines=3, css_classes=["property"])
        group.add(self.route_row)
        self.merge_row = Adw.SwitchRow(title="Merge into one file", subtitle="Combine all inputs (PDF, TIFF, GIF, archive, audio/video)")
        self.merge_row.set_visible(False)
        group.add(self.merge_row)
        page.add(group)

        group = Adw.PreferencesGroup(title="Output")
        self.outdir_row = Adw.ActionRow(title="Folder", subtitle="Same folder as each source file")
        choose = Gtk.Button(icon_name="folder-open-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"], tooltip_text="Choose folder")
        choose.connect("clicked", self._choose_output_dir)
        reset = Gtk.Button(icon_name="edit-clear-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"], tooltip_text="Use source folders")
        reset.connect("clicked", lambda *_: self._set_output_dir(None))
        self.outdir_row.add_suffix(choose)
        self.outdir_row.add_suffix(reset)
        group.add(self.outdir_row)
        self.overwrite_row = Adw.SwitchRow(title="Overwrite existing files", subtitle="Otherwise a numbered name is used")
        group.add(self.overwrite_row)
        page.add(group)

        self.options_group = Adw.PreferencesGroup(title="Options", description="Only options the selected backend understands take effect")
        page.add(self.options_group)
        return page

    # ------------------------------------------------------------- files
    def open_file_dialog(self) -> None:
        dialog = Gtk.FileDialog(title="Add files", modal=True)

        def done(d, res):
            try:
                files = d.open_multiple_finish(res)
            except GLib.Error:
                return
            self.add_paths([f.get_path() for f in files if f.get_path()])

        dialog.open_multiple(self, None, done)

    def _on_drop(self, target, value, x, y) -> bool:
        paths = []
        for f in value.get_files():
            p = f.get_path()
            if p:
                paths.append(p)
        self.add_paths(paths)
        return True

    def add_paths(self, paths: list[str]) -> None:
        added = 0
        for raw in paths:
            p = Path(raw)
            if p.is_dir():
                children = sorted(c for c in p.iterdir() if c.is_file())
            else:
                children = [p]
            for child in children:
                if not child.is_file() or any(e.path == child for e in self.entries):
                    continue
                entry = FileEntry(child)
                self.entries.append(entry)
                row = FileRow(entry, self._remove_row)
                self.rows.append(row)
                self.listbox.append(row)
                added += 1
        if added:
            self.stack.set_visible_child_name("list")
            self._refresh_targets()
        self._update_summary()

    def _remove_row(self, row: FileRow) -> None:
        self.listbox.remove(row)
        self.rows.remove(row)
        self.entries.remove(row.entry)
        if not self.entries:
            self.stack.set_visible_child_name("empty")
        self._refresh_targets()
        self._update_summary()

    def clear_files(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        for row in list(self.rows):
            self.listbox.remove(row)
        self.rows.clear()
        self.entries.clear()
        self.stack.set_visible_child_name("empty")
        self.open_folder_button.set_visible(False)
        self._refresh_targets()
        self._update_summary()

    # ----------------------------------------------------------- targets
    def _refresh_targets(self) -> None:
        previous = self.target_names[self.target_row.get_selected()] if self.target_names and self.target_row.get_selected() != Gtk.INVALID_LIST_POSITION else None
        source_formats = {e.format.name for e in self.entries if e.format}
        common: set[str] | None = None
        for name in source_formats:
            reach = set(REGISTRY.reachable(name))
            common = reach if common is None else common & reach
        source_cats = [e.format.category for e in self.entries if e.format]
        main_cat = max(set(source_cats), key=source_cats.count) if source_cats else None

        def order(n: str) -> tuple:
            cat = formats.FORMATS[n].category
            return (0 if cat == main_cat else 1, CATEGORY_ORDER.get(cat, 99), n)

        names = sorted(common or [], key=order)
        self.target_names = names
        model = Gtk.StringList()
        for n in names:
            f = formats.FORMATS[n]
            model.append(f"{f.name}  ·  {f.description}  [{CATEGORY_LABELS.get(f.category, f.category)}]")
        self.target_row.set_model(model)
        if names:
            if previous in names:
                idx = names.index(previous)
            else:
                idx = 0
                for candidate in PREFERRED_TARGETS.get(main_cat or "", ()):
                    if candidate in names and candidate not in source_formats:
                        idx = names.index(candidate)
                        break
            self.target_row.set_selected(idx)
        self.target_row.set_subtitle(f"{len(names)} formats reachable" if names else "Add files to see available targets")
        self._on_target_changed()

    def selected_target(self) -> Format | None:
        idx = self.target_row.get_selected()
        if idx == Gtk.INVALID_LIST_POSITION or idx >= len(self.target_names):
            return None
        return formats.FORMATS[self.target_names[idx]]

    def _on_target_changed(self) -> None:
        tgt = self.selected_target()
        self.convert_button.set_sensitive(bool(tgt and self.entries))
        if not tgt:
            self.route_row.set_subtitle("—")
            self.merge_row.set_visible(False)
            self._rebuild_options(set())
            return
        routes = []
        for name in sorted({e.format.name for e in self.entries if e.format}):
            r = REGISTRY.find_route(name, tgt.name)
            if r:
                routes.append(name + " → " + " → ".join(f"{s.tgt} ({s.name})" for s in r))
        self.route_row.set_subtitle("\n".join(routes) if routes else "—")
        mergeable = len(self.entries) > 1 and any(c.many_to_one and c.available() and tgt.name in c.target_names() for c in REGISTRY.all())
        self.merge_row.set_visible(mergeable)
        cats = {tgt.category} | {e.format.category for e in self.entries if e.format}
        self._rebuild_options(cats)

    # ----------------------------------------------------------- options
    def _rebuild_options(self, categories: set[str]) -> None:
        for _, widget in self.option_widgets.values():
            self.options_group.remove(widget)
        self.option_widgets.clear()
        for spec in OPTION_SPECS.values():
            if not spec.categories or not (set(spec.categories) & categories):
                continue
            row = self._make_option_row(spec)
            self.options_group.add(row)
            self.option_widgets[spec.name] = (spec, row)
        self.options_group.set_visible(bool(self.option_widgets))

    def _make_option_row(self, spec: OptionSpec) -> Gtk.Widget:
        title = spec.name.replace("_", " ").capitalize()
        if spec.type is bool:
            row = Adw.SwitchRow(title=title, subtitle=spec.help)
            row.set_active(bool(spec.default))
            return row
        if spec.choices:
            row = Adw.ComboRow(title=title, subtitle=spec.help)
            row.set_model(Gtk.StringList.new(list(spec.choices)))
            if spec.default in spec.choices:
                row.set_selected(spec.choices.index(spec.default))
            return row
        if spec.type in (int, float):
            # Optional numeric options use 0 as "not set", so the range always
            # starts at 0 even when the backend minimum is higher.
            lo = spec.minimum if (spec.minimum is not None and spec.default is not None) else 0
            hi = spec.maximum if spec.maximum is not None else 100000
            step = 1 if spec.type is int else 0.5
            row = Adw.SpinRow.new_with_range(lo, hi, step)
            row.set_title(title)
            row.set_subtitle(spec.help if spec.default is not None else spec.help + " (0 = unchanged)")
            row.set_digits(0 if spec.type is int else 2)
            row.set_value(spec.default if spec.default is not None else 0)
            return row
        row = Adw.EntryRow(title=title)
        row.set_tooltip_text(spec.help)
        if spec.default:
            row.set_text(str(spec.default))
        return row

    def collect_options(self) -> dict[str, Any]:
        opts: dict[str, Any] = {}
        for name, (spec, row) in self.option_widgets.items():
            if isinstance(row, Adw.SwitchRow):
                if row.get_active() != bool(spec.default):
                    opts[name] = row.get_active()
            elif isinstance(row, Adw.ComboRow):
                sel = row.get_selected()
                if sel != Gtk.INVALID_LIST_POSITION:
                    value = spec.choices[sel]
                    if value != spec.default:
                        opts[name] = value
            elif isinstance(row, Adw.SpinRow):
                value = row.get_value()
                if spec.default is None and value == 0:
                    continue
                if spec.default is not None and value == spec.default:
                    continue
                if spec.minimum is not None and value < spec.minimum:
                    continue
                opts[name] = int(value) if spec.type is int else float(value)
            elif isinstance(row, Adw.EntryRow):
                text = row.get_text().strip()
                if text and text != str(spec.default or ""):
                    opts[name] = text
        return opts

    # ------------------------------------------------------------ output
    def _choose_output_dir(self, *_) -> None:
        dialog = Gtk.FileDialog(title="Choose output folder", modal=True)

        def done(d, res):
            try:
                folder = d.select_folder_finish(res)
            except GLib.Error:
                return
            if folder and folder.get_path():
                self._set_output_dir(Path(folder.get_path()))

        dialog.select_folder(self, None, done)

    def _set_output_dir(self, path: Path | None) -> None:
        self.output_dir = path
        self.outdir_row.set_subtitle(str(path) if path else "Same folder as each source file")

    def _open_output_folder(self, *_) -> None:
        folder = self.output_dir
        if folder is None:
            for e in self.entries:
                if e.result and e.result.outputs:
                    folder = e.result.outputs[0].parent
                    break
        if folder is None:
            return
        Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(str(folder)).get_uri(), None)

    # -------------------------------------------------------- conversion
    def start_conversion(self) -> None:
        tgt = self.selected_target()
        if not tgt or not self.entries or (self.worker and self.worker.is_alive()):
            return
        options = self.collect_options()
        on_conflict = "overwrite" if self.overwrite_row.get_active() else "rename"
        merge = self.merge_row.get_visible() and self.merge_row.get_active()
        for e, row in zip(self.entries, self.rows):
            e.status = "running"
            e.message = "converting…"
            e.result = None
            row.refresh()
        self.cancel_flag.clear()
        self.convert_button.set_sensitive(False)
        self.cancel_button.set_visible(True)
        self.open_folder_button.set_visible(False)
        self.summary_label.set_text(f"Converting {len(self.entries)} file(s) to {tgt.name.upper()}…")
        self.worker = threading.Thread(target=self._run, args=(tgt, options, on_conflict, merge), daemon=True)
        self.worker.start()

    def _run(self, tgt: Format, options: dict[str, Any], on_conflict: str, merge: bool) -> None:
        try:
            if merge:
                first = self.entries[0].path
                out_dir = self.output_dir or first.parent
                output = out_dir / f"{first.stem}-merged.{tgt.extension}"
                res = ENGINE.merge([e.path for e in self.entries], output, options=options, on_conflict=on_conflict)
                for e in self.entries:
                    GLib.idle_add(self._on_result, e, res)
                return
            for e in self.entries:
                if self.cancel_flag.is_set():
                    e.status = "queued"
                    e.message = "cancelled"
                    GLib.idle_add(self._on_result, e, None)
                    continue
                res = ENGINE.convert(e.path, tgt, output_dir=self.output_dir, options=options, on_conflict=on_conflict)
                GLib.idle_add(self._on_result, e, res)
        finally:
            GLib.idle_add(self._on_finished)

    def _on_result(self, entry: FileEntry, res: Result | None) -> bool:
        if res is not None:
            entry.result = res
            if res.ok:
                entry.status = "done"
                names = ", ".join(p.name for p in res.outputs[:3]) + (" …" if len(res.outputs) > 3 else "")
                entry.message = f"{names} ({res.seconds:.1f}s)"
            else:
                entry.status = "failed"
                entry.message = (res.error or "failed").splitlines()[0]
        for row in self.rows:
            if row.entry is entry:
                row.refresh()
        return False

    def _on_finished(self) -> bool:
        done = sum(1 for e in self.entries if e.status == "done")
        failed = sum(1 for e in self.entries if e.status == "failed")
        self.convert_button.set_sensitive(True)
        self.cancel_button.set_visible(False)
        self.open_folder_button.set_visible(done > 0)
        text = f"{done} converted" + (f", {failed} failed" if failed else "")
        self.summary_label.set_text(text)
        toast = Adw.Toast(title=text, timeout=4)
        if failed:
            first = next(e for e in self.entries if e.status == "failed")
            toast.set_title(f"{text}: {first.path.name}: {first.message}")
            toast.set_timeout(8)
        self.toast_overlay.add_toast(toast)
        return False

    def _update_summary(self) -> None:
        n = len(self.entries)
        unknown = sum(1 for e in self.entries if e.format is None)
        if n == 0:
            self.summary_label.set_text("Drop files here or click + to begin")
        else:
            text = f"{n} file(s)"
            if unknown:
                text += f", {unknown} of unknown format"
            self.summary_label.set_text(text)
        self.convert_button.set_sensitive(bool(self.selected_target() and self.entries))


class BackendsWindow(Adw.Window):
    """Lists every converter with its availability and install hint."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.set_title("Backends")
        self.set_default_size(720, 560)
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        self.set_content(toolbar)
        page = Adw.PreferencesPage()
        toolbar.set_content(page)
        available = Adw.PreferencesGroup(title="Available backends")
        missing = Adw.PreferencesGroup(title="Missing backends", description="Install these to unlock more conversions, then restart Omniconv.")
        n_avail = 0
        for conv in sorted(REGISTRY.all(), key=lambda c: c.name):
            row = Adw.ActionRow(title=conv.name, subtitle=conv.description)
            if conv.available():
                n_avail += 1
                row.add_suffix(Gtk.Label(label=f"{len(conv.source_names())} in / {len(conv.target_names())} out", css_classes=["dim-label", "caption"]))
                row.add_suffix(Gtk.Image.new_from_icon_name("emblem-ok-symbolic"))
                available.add(row)
            else:
                hint = "; ".join(f"{r.describe()}" + (f" ({r.hint()})" if r.hint() else "") for r in conv.missing())
                row.set_subtitle(f"{conv.description}\nNeeds: {hint}")
                row.add_suffix(Gtk.Image.new_from_icon_name("dialog-warning-symbolic"))
                missing.add(row)
        pairs = sum(len(REGISTRY.reachable(f.name)) for f in formats.all_formats())
        available.set_description(f"{n_avail} of {len(REGISTRY.all())} backends usable; {pairs} source→target pairs reachable")
        page.add(available)
        if n_avail < len(REGISTRY.all()):
            page.add(missing)
