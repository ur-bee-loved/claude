"""Qt 6 front end, used on Windows and macOS (and on Linux without GTK 4).

The layout mirrors the GTK window: a file list on the left that accepts
drops, a sidebar on the right with the target format, output folder and
options, and a convert button along the bottom. Conversions run on a
``QThread`` and report back through signals, so the window stays
responsive and every widget is only touched from the main thread.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, Signal

from omniconv import __version__
from omniconv.core import formats, platform
from omniconv.core.engine import ENGINE, Result
from omniconv.core.formats import Format
from omniconv.core.options import OPTION_SPECS, OptionSpec
from omniconv.core.registry import REGISTRY
from omniconv.core.sniff import detect

CATEGORY_LABELS = {
    "image": "Image", "vector": "Vector graphics", "audio": "Audio", "video": "Video", "subtitle": "Subtitles",
    "document": "Document", "ebook": "E-book", "data": "Data", "archive": "Archive", "font": "Font", "model": "3D model",
}
CATEGORY_ORDER = {c: i for i, c in enumerate(formats.CATEGORIES)}
PREFERRED_TARGETS = {
    "image": ("png", "jpeg", "webp", "pdf"), "vector": ("png", "pdf", "svg"), "audio": ("mp3", "flac", "wav", "ogg"),
    "video": ("mp4", "mkv", "webm", "gif"), "subtitle": ("srt", "vtt"), "document": ("pdf", "docx", "html", "txt"),
    "ebook": ("epub", "pdf", "mobi"), "data": ("json", "csv", "yaml"), "archive": ("zip", "tar.gz", "7z"),
    "font": ("woff2", "woff", "ttf"), "model": ("glb", "obj", "stl"),
}
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _human_size(n: float) -> str:
    for unit in ("B", "kB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def app_icon() -> QtGui.QIcon:
    icon = QtGui.QIcon()
    ico = DATA_DIR / "omniconv.ico"
    svg = DATA_DIR / "io.github.omniconv.Omniconv.svg"
    if ico.exists():
        icon.addFile(str(ico))
    if svg.exists():
        icon.addFile(str(svg))
    return icon


class FileEntry:
    """One input file and its conversion state."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.format: Format | None = detect(path)
        self.status = "queued"
        self.message = ""
        self.result: Result | None = None


class FileList(QtWidgets.QTreeWidget):
    """The file table. Accepts file drops from the desktop."""

    files_dropped = Signal(list)
    COLUMNS = ("File", "Format", "Size", "Status")

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setColumnCount(len(self.COLUMNS))
        self.setHeaderLabels(self.COLUMNS)
        self.setRootIsDecorated(False)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAcceptDrops(True)
        self.setUniformRowHeights(True)
        header = self.header()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(True)
        self.icons = QtWidgets.QFileIconProvider()

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def add_entry(self, entry: FileEntry) -> QtWidgets.QTreeWidgetItem:
        fmt = entry.format
        size = _human_size(entry.path.stat().st_size) if entry.path.exists() else ""
        item = QtWidgets.QTreeWidgetItem([entry.path.name, fmt.name.upper() if fmt else "unknown", size, ""])
        item.setIcon(0, self.icons.icon(QtCore.QFileInfo(str(entry.path))))
        item.setToolTip(0, str(entry.path))
        item.setToolTip(1, fmt.description if fmt else "Format not recognised")
        item.setData(0, Qt.ItemDataRole.UserRole, entry)
        self.addTopLevelItem(item)
        self.refresh_item(item)
        return item

    def refresh_item(self, item: QtWidgets.QTreeWidgetItem) -> None:
        entry: FileEntry = item.data(0, Qt.ItemDataRole.UserRole)
        style = self.style()
        text = {"queued": "", "running": "converting…", "done": entry.message, "failed": entry.message}[entry.status]
        item.setText(3, text)
        item.setToolTip(3, entry.message)
        if entry.status == "done":
            item.setIcon(3, style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogApplyButton))
        elif entry.status == "failed":
            item.setIcon(3, style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MessageBoxCritical))
        elif entry.status == "running":
            item.setIcon(3, style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_BrowserReload))
        else:
            item.setIcon(3, QtGui.QIcon())

    def entries(self) -> list[FileEntry]:
        return [self.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole) for i in range(self.topLevelItemCount())]

    def item_for(self, entry: FileEntry) -> QtWidgets.QTreeWidgetItem | None:
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item.data(0, Qt.ItemDataRole.UserRole) is entry:
                return item
        return None


class Worker(QtCore.QThread):
    """Runs the conversions off the GUI thread."""

    progressed = Signal(object, object)  # entry, Result or None
    finished_all = Signal()

    def __init__(self, entries: list[FileEntry], target: Format, options: dict[str, Any], on_conflict: str, output_dir: Path | None, merge: bool) -> None:
        super().__init__()
        self.entries = entries
        self.target = target
        self.options = options
        self.on_conflict = on_conflict
        self.output_dir = output_dir
        self.merge = merge
        self.cancel = threading.Event()

    def run(self) -> None:
        try:
            if self.merge:
                first = self.entries[0].path
                out_dir = self.output_dir or first.parent
                output = out_dir / f"{first.stem}-merged.{self.target.extension}"
                res = ENGINE.merge([e.path for e in self.entries], output, options=self.options, on_conflict=self.on_conflict)
                for e in self.entries:
                    self.progressed.emit(e, res)
                return
            for e in self.entries:
                if self.cancel.is_set():
                    self.progressed.emit(e, None)
                    continue
                res = ENGINE.convert(e.path, self.target, output_dir=self.output_dir, options=self.options, on_conflict=self.on_conflict)
                self.progressed.emit(e, res)
        finally:
            self.finished_all.emit()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Omniconv")
        self.setWindowIcon(app_icon())
        self.resize(1000, 640)
        self.setMinimumSize(700, 440)
        self.option_widgets: dict[str, tuple[OptionSpec, QtWidgets.QWidget]] = {}
        self.target_names: list[str] = []
        self.output_dir: Path | None = None
        self.worker: Worker | None = None
        from omniconv.converters import load_all

        load_all()
        self._build_actions()
        self._build_menu()
        self._build_body()
        self._build_bottom()
        self._refresh_targets()
        self._update_summary()

    # ------------------------------------------------------------ building
    def _build_actions(self) -> None:
        style = self.style()
        self.act_add = QtGui.QAction(style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_FileDialogNewFolder), "&Add files…", self)
        self.act_add.setShortcut(QtGui.QKeySequence.StandardKey.Open)
        self.act_add.triggered.connect(self.open_file_dialog)
        self.act_add_folder = QtGui.QAction("Add &folder…", self)
        self.act_add_folder.triggered.connect(self.open_folder_dialog)
        self.act_remove = QtGui.QAction("&Remove selected", self)
        self.act_remove.setShortcut(QtGui.QKeySequence.StandardKey.Delete)
        self.act_remove.triggered.connect(self.remove_selected)
        self.act_clear = QtGui.QAction("&Clear list", self)
        self.act_clear.triggered.connect(self.clear_files)
        self.act_convert = QtGui.QAction("Con&vert", self)
        self.act_convert.setShortcut("Ctrl+Return")
        self.act_convert.triggered.connect(self.start_conversion)
        self.act_backends = QtGui.QAction("&Backends and formats…", self)
        self.act_backends.triggered.connect(self.show_backends)
        self.act_about = QtGui.QAction("&About Omniconv", self)
        self.act_about.triggered.connect(self.show_about)
        self.act_quit = QtGui.QAction("&Quit", self)
        self.act_quit.setShortcut(QtGui.QKeySequence.StandardKey.Quit)
        self.act_quit.triggered.connect(self.close)

    def _build_menu(self) -> None:
        bar = self.menuBar()
        m = bar.addMenu("&File")
        m.addAction(self.act_add)
        m.addAction(self.act_add_folder)
        m.addSeparator()
        m.addAction(self.act_remove)
        m.addAction(self.act_clear)
        m.addSeparator()
        m.addAction(self.act_convert)
        m.addSeparator()
        m.addAction(self.act_quit)
        m = bar.addMenu("&Tools")
        m.addAction(self.act_backends)
        m = bar.addMenu("&Help")
        m.addAction(self.act_about)
        tb = self.addToolBar("Main")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        tb.addAction(self.act_add)
        tb.addAction(self.act_clear)

    def _build_body(self) -> None:
        splitter = QtWidgets.QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        # Left: file list with an empty-state hint layered over it.
        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 4, 8)
        self.file_list = FileList()
        self.file_list.files_dropped.connect(self.add_paths)
        self.file_list.itemSelectionChanged.connect(lambda: self.act_remove.setEnabled(bool(self.file_list.selectedItems())))
        self.empty_hint = QtWidgets.QLabel("Drop files here, or use File ▸ Add files.\nThen pick a target format on the right.")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.setStyleSheet("color: palette(mid); font-size: 11pt;")
        self.stack = QtWidgets.QStackedLayout()
        self.stack.setStackingMode(QtWidgets.QStackedLayout.StackingMode.StackAll)
        holder = QtWidgets.QWidget()
        holder.setLayout(self.stack)
        self.stack.addWidget(self.file_list)
        self.stack.addWidget(self.empty_hint)
        self.empty_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        left_layout.addWidget(holder)
        splitter.addWidget(left)

        # Right: sidebar in a scroll area.
        side = QtWidgets.QWidget()
        side_layout = QtWidgets.QVBoxLayout(side)
        side_layout.setContentsMargins(4, 8, 8, 8)

        target_box = QtWidgets.QGroupBox("Target")
        form = QtWidgets.QFormLayout(target_box)
        self.target_combo = QtWidgets.QComboBox()
        self.target_combo.setEditable(True)
        self.target_combo.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
        self.target_combo.completer().setCompletionMode(QtWidgets.QCompleter.CompletionMode.PopupCompletion)
        self.target_combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.target_combo.currentIndexChanged.connect(lambda *_: self._on_target_changed())
        form.addRow("Convert to", self.target_combo)
        self.target_hint = QtWidgets.QLabel("Add files to see available targets")
        self.target_hint.setStyleSheet("color: palette(mid);")
        form.addRow("", self.target_hint)
        self.route_label = QtWidgets.QLabel("—")
        self.route_label.setWordWrap(True)
        self.route_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Route", self.route_label)
        self.merge_check = QtWidgets.QCheckBox("Merge all inputs into one file")
        self.merge_check.setToolTip("Combine all inputs (PDF, TIFF, GIF, archive, audio/video, slideshow)")
        self.merge_check.setVisible(False)
        form.addRow("", self.merge_check)
        side_layout.addWidget(target_box)

        out_box = QtWidgets.QGroupBox("Output")
        form = QtWidgets.QFormLayout(out_box)
        row = QtWidgets.QHBoxLayout()
        self.outdir_edit = QtWidgets.QLineEdit()
        self.outdir_edit.setPlaceholderText("Same folder as each source file")
        self.outdir_edit.setReadOnly(True)
        browse = QtWidgets.QToolButton()
        browse.setText("…")
        browse.setToolTip("Choose folder")
        browse.clicked.connect(self._choose_output_dir)
        reset = QtWidgets.QToolButton()
        reset.setText("×")
        reset.setToolTip("Use source folders")
        reset.clicked.connect(lambda: self._set_output_dir(None))
        row.addWidget(self.outdir_edit)
        row.addWidget(browse)
        row.addWidget(reset)
        form.addRow("Folder", row)
        self.overwrite_check = QtWidgets.QCheckBox("Overwrite existing files")
        self.overwrite_check.setToolTip("Otherwise a numbered name is used")
        form.addRow("", self.overwrite_check)
        side_layout.addWidget(out_box)

        self.options_box = QtWidgets.QGroupBox("Options")
        self.options_form = QtWidgets.QFormLayout(self.options_box)
        self.options_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        side_layout.addWidget(self.options_box)
        side_layout.addStretch(1)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setWidget(side)
        scroll.setMinimumWidth(320)
        splitter.addWidget(scroll)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([620, 380])

    def _build_bottom(self) -> None:
        bar = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 8)
        self.summary_label = QtWidgets.QLabel("")
        self.summary_label.setStyleSheet("color: palette(mid);")
        layout.addWidget(self.summary_label, 1)
        self.open_folder_button = QtWidgets.QPushButton("Open output folder")
        self.open_folder_button.setVisible(False)
        self.open_folder_button.clicked.connect(self._open_output_folder)
        layout.addWidget(self.open_folder_button)
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(lambda: self.worker and self.worker.cancel.set())
        layout.addWidget(self.cancel_button)
        self.convert_button = QtWidgets.QPushButton("Convert")
        self.convert_button.setDefault(True)
        self.convert_button.setEnabled(False)
        self.convert_button.clicked.connect(self.start_conversion)
        layout.addWidget(self.convert_button)
        dock = QtWidgets.QStatusBar()
        dock.addPermanentWidget(bar, 1)
        dock.setSizeGripEnabled(True)
        self.setStatusBar(dock)

    # ------------------------------------------------------------- files
    def open_file_dialog(self) -> None:
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Add files")
        if paths:
            self.add_paths(paths)

    def open_folder_dialog(self) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Add folder")
        if folder:
            self.add_paths([folder])

    def add_paths(self, paths: list[str]) -> None:
        existing = {e.path for e in self.file_list.entries()}
        added = 0
        for raw in paths:
            p = Path(raw)
            children = sorted(c for c in p.iterdir() if c.is_file()) if p.is_dir() else [p]
            for child in children:
                if not child.is_file() or child in existing:
                    continue
                self.file_list.add_entry(FileEntry(child))
                existing.add(child)
                added += 1
        if added:
            self._refresh_targets()
        self._update_summary()

    def remove_selected(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        for item in self.file_list.selectedItems():
            self.file_list.takeTopLevelItem(self.file_list.indexOfTopLevelItem(item))
        self._refresh_targets()
        self._update_summary()

    def clear_files(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        self.file_list.clear()
        self.open_folder_button.setVisible(False)
        self._refresh_targets()
        self._update_summary()

    # ----------------------------------------------------------- targets
    def _refresh_targets(self) -> None:
        previous = self.selected_target()
        entries = self.file_list.entries()
        source_formats = {e.format.name for e in entries if e.format}
        common: set[str] | None = None
        for name in source_formats:
            reach = set(REGISTRY.reachable(name))
            common = reach if common is None else common & reach
        source_cats = [e.format.category for e in entries if e.format]
        main_cat = max(set(source_cats), key=source_cats.count) if source_cats else None

        def order(n: str) -> tuple:
            cat = formats.FORMATS[n].category
            return (0 if cat == main_cat else 1, CATEGORY_ORDER.get(cat, 99), n)

        names = sorted(common or [], key=order)
        self.target_names = names
        self.target_combo.blockSignals(True)
        self.target_combo.clear()
        for n in names:
            f = formats.FORMATS[n]
            self.target_combo.addItem(f"{f.name}  ·  {f.description}  [{CATEGORY_LABELS.get(f.category, f.category)}]", n)
        idx = 0
        if previous and previous.name in names:
            idx = names.index(previous.name)
        elif names:
            for candidate in PREFERRED_TARGETS.get(main_cat or "", ()):
                if candidate in names and candidate not in source_formats:
                    idx = names.index(candidate)
                    break
        if names:
            self.target_combo.setCurrentIndex(idx)
        self.target_combo.blockSignals(False)
        self.target_hint.setText(f"{len(names)} formats reachable from every listed file" if names else "Add files to see available targets")
        self._on_target_changed()

    def selected_target(self) -> Format | None:
        idx = self.target_combo.currentIndex()
        if idx < 0 or idx >= len(self.target_names):
            return None
        return formats.FORMATS[self.target_names[idx]]

    def _on_target_changed(self) -> None:
        tgt = self.selected_target()
        entries = self.file_list.entries()
        self.convert_button.setEnabled(bool(tgt and entries))
        self.act_convert.setEnabled(bool(tgt and entries))
        if not tgt:
            self.route_label.setText("—")
            self.merge_check.setVisible(False)
            self._rebuild_options(set())
            return
        routes = []
        for name in sorted({e.format.name for e in entries if e.format}):
            r = REGISTRY.find_route(name, tgt.name)
            if r:
                routes.append(name + " → " + " → ".join(f"{s.tgt} ({s.name})" for s in r))
        self.route_label.setText("\n".join(routes) if routes else "—")
        mergeable = len(entries) > 1 and any(c.many_to_one and c.available() and tgt.name in c.target_names() for c in REGISTRY.all())
        self.merge_check.setVisible(mergeable)
        self._rebuild_options({tgt.category} | {e.format.category for e in entries if e.format})

    # ----------------------------------------------------------- options
    def _rebuild_options(self, categories: set[str]) -> None:
        while self.options_form.rowCount():
            self.options_form.removeRow(0)
        self.option_widgets.clear()
        for spec in OPTION_SPECS.values():
            if not spec.categories or not (set(spec.categories) & categories):
                continue
            widget = self._make_option_widget(spec)
            widget.setToolTip(spec.help)
            label = spec.name.replace("_", " ").capitalize()
            if spec.type is bool:
                self.options_form.addRow("", widget)
            else:
                self.options_form.addRow(label, widget)
            self.option_widgets[spec.name] = (spec, widget)
        self.options_box.setVisible(bool(self.option_widgets))

    def _make_option_widget(self, spec: OptionSpec) -> QtWidgets.QWidget:
        if spec.type is bool:
            w = QtWidgets.QCheckBox(spec.name.replace("_", " ").capitalize())
            w.setChecked(bool(spec.default))
            return w
        if spec.choices:
            w = QtWidgets.QComboBox()
            w.addItems(list(spec.choices))
            if spec.default in spec.choices:
                w.setCurrentIndex(spec.choices.index(spec.default))
            return w
        if spec.type in (int, float):
            w = QtWidgets.QSpinBox() if spec.type is int else QtWidgets.QDoubleSpinBox()
            lo = spec.minimum if (spec.minimum is not None and spec.default is not None) else 0
            hi = spec.maximum if spec.maximum is not None else 100000
            w.setRange(lo, hi)
            if spec.default is None:
                w.setSpecialValueText("unchanged")
                w.setValue(0)
            else:
                w.setValue(spec.default)
            return w
        w = QtWidgets.QLineEdit()
        w.setPlaceholderText(spec.help)
        if spec.default:
            w.setText(str(spec.default))
        return w

    def collect_options(self) -> dict[str, Any]:
        opts: dict[str, Any] = {}
        for name, (spec, w) in self.option_widgets.items():
            if isinstance(w, QtWidgets.QCheckBox):
                if w.isChecked() != bool(spec.default):
                    opts[name] = w.isChecked()
            elif isinstance(w, QtWidgets.QComboBox):
                value = w.currentText()
                if value != spec.default:
                    opts[name] = value
            elif isinstance(w, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
                value = w.value()
                if spec.default is None and value == 0:
                    continue
                if spec.default is not None and value == spec.default:
                    continue
                if spec.minimum is not None and value < spec.minimum:
                    continue
                opts[name] = int(value) if spec.type is int else float(value)
            elif isinstance(w, QtWidgets.QLineEdit):
                text = w.text().strip()
                if text and text != str(spec.default or ""):
                    opts[name] = text
        return opts

    # ------------------------------------------------------------ output
    def _choose_output_dir(self) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose output folder")
        if folder:
            self._set_output_dir(Path(folder))

    def _set_output_dir(self, path: Path | None) -> None:
        self.output_dir = path
        self.outdir_edit.setText(str(path) if path else "")

    def _open_output_folder(self) -> None:
        folder = self.output_dir
        if folder is None:
            for e in self.file_list.entries():
                if e.result and e.result.outputs:
                    folder = e.result.outputs[0].parent
                    break
        if folder is not None:
            platform.open_in_file_manager(folder)

    # -------------------------------------------------------- conversion
    def start_conversion(self) -> None:
        tgt = self.selected_target()
        entries = self.file_list.entries()
        if not tgt or not entries or (self.worker and self.worker.isRunning()):
            return
        options = self.collect_options()
        on_conflict = "overwrite" if self.overwrite_check.isChecked() else "rename"
        merge = self.merge_check.isVisible() and self.merge_check.isChecked()
        for e in entries:
            e.status = "running"
            e.message = ""
            e.result = None
            item = self.file_list.item_for(e)
            if item:
                self.file_list.refresh_item(item)
        self.convert_button.setEnabled(False)
        self.act_convert.setEnabled(False)
        self.cancel_button.setVisible(True)
        self.open_folder_button.setVisible(False)
        self.summary_label.setText(f"Converting {len(entries)} file(s) to {tgt.name.upper()}…")
        self.worker = Worker(entries, tgt, options, on_conflict, self.output_dir, merge)
        self.worker.progressed.connect(self._on_result)
        self.worker.finished_all.connect(self._on_finished)
        self.worker.start()

    def _on_result(self, entry: FileEntry, res: Result | None) -> None:
        if res is None:
            entry.status = "queued"
            entry.message = "cancelled"
        else:
            entry.result = res
            if res.ok:
                entry.status = "done"
                names = ", ".join(p.name for p in res.outputs[:3]) + (" …" if len(res.outputs) > 3 else "")
                entry.message = f"{names} ({res.seconds:.1f}s)"
            else:
                entry.status = "failed"
                entry.message = (res.error or "failed").splitlines()[0]
        item = self.file_list.item_for(entry)
        if item:
            self.file_list.refresh_item(item)

    def _on_finished(self) -> None:
        entries = self.file_list.entries()
        done = sum(1 for e in entries if e.status == "done")
        failed = sum(1 for e in entries if e.status == "failed")
        self.convert_button.setEnabled(True)
        self.act_convert.setEnabled(True)
        self.cancel_button.setVisible(False)
        self.open_folder_button.setVisible(done > 0)
        text = f"{done} converted" + (f", {failed} failed" if failed else "")
        self.summary_label.setText(text)
        self.statusBar().showMessage(text, 5000)
        if failed:
            first = next(e for e in entries if e.status == "failed")
            QtWidgets.QMessageBox.warning(self, "Some conversions failed", f"{text}.\n\n{first.path.name}: {first.message}")

    def _update_summary(self) -> None:
        entries = self.file_list.entries()
        self.empty_hint.setVisible(not entries)
        unknown = sum(1 for e in entries if e.format is None)
        if not entries:
            self.summary_label.setText("Drop files here or press Ctrl+O to begin")
        else:
            text = f"{len(entries)} file(s)"
            if unknown:
                text += f", {unknown} of unknown format"
            self.summary_label.setText(text)
        enabled = bool(self.selected_target() and entries)
        self.convert_button.setEnabled(enabled)
        self.act_convert.setEnabled(enabled)
        self.act_remove.setEnabled(bool(self.file_list.selectedItems()))

    # ----------------------------------------------------------- dialogs
    def show_backends(self) -> None:
        BackendsDialog(self).exec()

    def show_about(self) -> None:
        QtWidgets.QMessageBox.about(
            self,
            "About Omniconv",
            f"<b>Omniconv {__version__}</b><br>Convert files between image, audio, video, document, e-book, data, "
            "archive and font formats using the tools installed on your system.<br><br>"
            "<a href='https://github.com/ur-bee-loved/claude'>github.com/ur-bee-loved/claude</a>",
        )

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel.set()
            self.worker.wait(2000)
        super().closeEvent(event)


class BackendsDialog(QtWidgets.QDialog):
    """Lists every converter with its availability and install hint."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Backends")
        self.resize(760, 560)
        layout = QtWidgets.QVBoxLayout(self)
        tree = QtWidgets.QTreeWidget()
        tree.setColumnCount(4)
        tree.setHeaderLabels(["Backend", "Status", "In / out", "Description and requirements"])
        tree.setRootIsDecorated(False)
        tree.setAlternatingRowColors(True)
        style = self.style()
        n_avail = 0
        for conv in sorted(REGISTRY.all(), key=lambda c: (not c.available(), c.name)):
            if conv.available():
                n_avail += 1
                item = QtWidgets.QTreeWidgetItem([conv.name, "available", f"{len(conv.source_names())} / {len(conv.target_names())}", conv.description])
                item.setIcon(1, style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogApplyButton))
            else:
                hint = "; ".join(f"{r.describe()}" + (f" ({r.hint()})" if r.hint() else "") for r in conv.missing())
                item = QtWidgets.QTreeWidgetItem([conv.name, "missing", "", f"{conv.description}. Needs: {hint}"])
                item.setIcon(1, style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MessageBoxWarning))
            item.setToolTip(3, item.text(3))
            tree.addTopLevelItem(item)
        for i in range(3):
            tree.resizeColumnToContents(i)
        pairs = sum(len(REGISTRY.reachable(f.name)) for f in formats.all_formats())
        summary = QtWidgets.QLabel(f"{n_avail} of {len(REGISTRY.all())} backends usable; {pairs} source→target pairs reachable. Install a missing tool and restart Omniconv to enable it.")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        layout.addWidget(tree, 1)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


def create_app(argv: list[str] | None = None) -> QtWidgets.QApplication:
    if platform.IS_WINDOWS:
        # Follow the Windows light/dark setting (Qt 6.5+ honours this flag).
        os.environ.setdefault("QT_QPA_PLATFORM", "windows:darkmode=2")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Omniconv")
    app.setApplicationDisplayName("Omniconv")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Omniconv")
    app.setWindowIcon(app_icon())
    return app


def run_app(files: list[str] | None = None) -> int:
    app = create_app([sys.argv[0]])
    window = MainWindow()
    if files:
        window.add_paths(list(files))
    window.show()
    return app.exec()
