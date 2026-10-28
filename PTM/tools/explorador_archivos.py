# ARGUMENTOS: explorador archivos carpetas windows 11 pestañas tabs copiar pegar cortar dispositivos hdd ssd usb cd dvd unidades discos
import ctypes
import fnmatch
import datetime as _dt
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

TOOL_NAME = "Explorador de Archivos"
TOOL_DESCRIPTION = (
    "Explorador de archivos tipo Windows 11 con pestañas, buscador integrado, "
    "copiar/cortar/pegar, navegacion y panel lateral de HDD, SSD, USB, CD/DVD "
    "y unidades de red."
)
TOOL_VERSION = "1.0.2"


class ExplorerTab(ttk.Frame):
    def __init__(self, parent, owner, tab_id, start_path):
        super().__init__(parent)
        self.owner = owner
        self.tab_id = tab_id
        self.path = Path(start_path)
        self.history = []
        self.future = []
        self.items = []
        self.loading_token = 0
        self._iid_to_path = {}
        self._sort_column = "name"
        self._sort_reverse = False

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        wrap = ttk.Frame(self)
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            wrap,
            columns=("name", "type", "size", "modified"),
            show="headings",
            selectmode="extended",
        )
        self.tree.grid(row=0, column=0, sticky="nsew")

        self.tree.heading("name", text="Nombre", command=lambda: self.sort_by("name"))
        self.tree.heading("type", text="Tipo", command=lambda: self.sort_by("type"))
        self.tree.heading("size", text="Tamaño", command=lambda: self.sort_by("size"))
        self.tree.heading(
            "modified", text="Fecha de modificación", command=lambda: self.sort_by("modified")
        )

        self.tree.column("name", width=360, minwidth=160, anchor="w")
        self.tree.column("type", width=145, minwidth=90, anchor="w")
        self.tree.column("size", width=100, minwidth=70, anchor="e")
        self.tree.column("modified", width=160, minwidth=120, anchor="w")

        vbar = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        vbar.grid(row=0, column=1, sticky="ns")
        hbar = ttk.Scrollbar(wrap, orient="horizontal", command=self.tree.xview)
        hbar.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)

        self.tree.bind("<Double-Button-1>", self._open_selected)
        self.tree.bind("<Return>", self._open_selected)
        self.tree.bind("<BackSpace>", lambda _e: self.owner.go_up())
        self.tree.bind("<F5>", lambda _e: self.refresh())
        self.tree.bind("<F2>", lambda _e: self.owner.rename_selected())
        self.tree.bind("<Delete>", lambda _e: self.owner.delete_selected())
        self.tree.bind("<Control-c>", lambda _e: self.owner.copy_selected(False))
        self.tree.bind("<Control-x>", lambda _e: self.owner.copy_selected(True))
        self.tree.bind("<Control-v>", lambda _e: self.owner.paste_files())
        self.tree.bind("<Control-a>", self._select_all)
        self.tree.bind("<Control-l>", lambda _e: self.owner.focus_address())
        self.tree.bind("<Control-t>", lambda _e: self.owner.new_tab(self.path))
        self.tree.bind("<Button-3>", self._show_context_menu)

        self.refresh(first=True)

    def _select_all(self, _event=None):
        self.tree.selection_set(self.tree.get_children(""))
        return "break"

    def _show_context_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            if iid not in self.tree.selection():
                self.tree.selection_set(iid)
            self.tree.focus(iid)
        self.owner.show_context_menu(event.x_root, event.y_root)
        return "break"

    def _open_selected(self, _event=None):
        selected = self.selected_paths()
        if not selected:
            return "break"
        path = selected[0]
        if path.is_dir():
            self.navigate(path)
        else:
            self.owner.open_path(path)
        return "break"

    def selected_paths(self):
        out = []
        for iid in self.tree.selection():
            raw = self._iid_to_path.get(iid)
            if raw:
                out.append(Path(raw))
        return out

    def navigate(self, path, record=True):
        path = Path(path)
        try:
            path = path.resolve()
        except Exception:
            path = path.absolute()
        if not path.is_dir():
            return

        if record and self.path != path:
            self.history.append(self.path)
            if len(self.history) > 80:
                self.history = self.history[-80:]
            self.future.clear()

        self.path = path
        self.owner._tab_path_changed(self)
        self.refresh()

    def back(self):
        if not self.history:
            return
        target = self.history.pop()
        self.future.append(self.path)
        self.path = target
        self.owner._tab_path_changed(self)
        self.refresh()

    def forward(self):
        if not self.future:
            return
        target = self.future.pop()
        self.history.append(self.path)
        self.path = target
        self.owner._tab_path_changed(self)
        self.refresh()

    def refresh(self, first=False):
        self.loading_token += 1
        token = self.loading_token
        path = self.path
        self.owner.status_var.set(f"Cargando {path}...")

        def worker():
            result = []
            error = None
            try:
                with os.scandir(path) as entries:
                    for entry in entries:
                        try:
                            stat = entry.stat(follow_symlinks=False)
                            is_dir = entry.is_dir(follow_symlinks=False)
                            suffix = "" if is_dir else Path(entry.name).suffix.lower()
                            result.append(
                                {
                                    "path": entry.path,
                                    "name": entry.name,
                                    "is_dir": is_dir,
                                    "type": self.owner.describe_type(entry.name, is_dir),
                                    "size": 0 if is_dir else int(stat.st_size),
                                    "modified": float(stat.st_mtime),
                                    "suffix": suffix,
                                }
                            )
                        except (PermissionError, FileNotFoundError, OSError):
                            continue
            except Exception as exc:
                error = str(exc)

            self.owner._ui_queue.put(
                ("directory", self.tab_id, token, result, error, first)
            )

        threading.Thread(target=worker, daemon=True).start()

    def apply_directory_result(self, token, items, error):
        if token != self.loading_token:
            return
        if error:
            self.owner.status_var.set(error)
            return
        self.items = items
        self.refresh_view()

    def refresh_view(self):
        query = self.owner.search_var.get().strip().lower()
        items = self.items
        if query:
            items = [
                item for item in items
                if query in item["name"].lower() or query in item["type"].lower()
            ]

        key = self._sort_column
        reverse = self._sort_reverse

        def sort_key(item):
            group = 0 if item["is_dir"] else 1
            if key == "name":
                value = item["name"].lower()
            elif key == "type":
                value = item["type"].lower()
            elif key == "size":
                value = item["size"]
            else:
                value = item["modified"]
            return (group, value)

        items = sorted(items, key=sort_key, reverse=reverse)

        self.tree.delete(*self.tree.get_children(""))
        self._iid_to_path.clear()

        for index, item in enumerate(items):
            iid = f"i{index}"
            self._iid_to_path[iid] = item["path"]
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    ("📁 " if item["is_dir"] else "📄 ") + item["name"],
                    item["type"],
                    "" if item["is_dir"] else self.owner.format_size(item["size"]),
                    self.owner.format_time(item["modified"]),
                ),
            )

        self.owner.status_var.set(
            f"{len(items)} elemento(s) · {self.path}"
        )

    def sort_by(self, column):
        if self._sort_column == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = False
        self.refresh_view()


def _search_name_matches(name, pattern):
    pattern = str(pattern or "").strip().lower()
    if not pattern:
        return True
    pattern = pattern.replace("%", "*").replace("_", "?")
    if "*" in pattern or "?" in pattern:
        return fnmatch.fnmatch(name.lower(), pattern)
    return pattern in name.lower()


class SearchTab(ttk.Frame):
    """Pestaña fija de búsqueda integrada visualmente en el Explorador."""

    EXTENSIONS = (
        "Todas",
        ".xlsx", ".xls", ".xlsm", ".csv",
        ".pdf", ".docx", ".doc", ".txt", ".pptx", ".py",
        ".jpg", ".jpeg", ".png", ".gif", ".webp",
        ".mp3", ".wav", ".flac", ".mp4", ".mkv", ".avi",
        ".zip", ".rar", ".7z",
    )

    def __init__(self, parent, owner):
        super().__init__(parent)
        self.owner = owner
        self.scope_var = tk.StringVar(value=str(owner.default_start_path()))
        self.pattern_var = tk.StringVar()
        self.extension_var = tk.StringVar(value="Todas")
        self.info_var = tk.StringVar(
            value="Escribe un nombre o patrón y pulsa Buscar."
        )
        self.results = []
        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        self._searching = False
        self._folders_scanned = 0
        self._files_scanned = 0

        self._build_ui()
        self.after(70, self._process_queue)

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        head = ttk.Frame(self, padding=(6, 5, 6, 4))
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(1, weight=1)

        ttk.Label(
            head,
            text="Buscar archivos",
            font=("Segoe UI", 12, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=(0, 12))

        ttk.Label(
            head,
            text="Busca en una carpeta, unidad o dispositivo sin salir del Explorador",
            style="ExplorerMuted.TLabel",
        ).grid(row=0, column=1, sticky="w")

        scope = ttk.Frame(self, padding=(6, 2, 6, 3))
        scope.grid(row=1, column=0, sticky="ew")
        scope.columnconfigure(1, weight=1)

        ttk.Label(scope, text="Buscar en:").grid(
            row=0, column=0, sticky="w"
        )
        self.scope_entry = ttk.Entry(
            scope,
            textvariable=self.scope_var,
        )
        self.scope_entry.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(7, 5),
        )
        self.scope_entry.bind("<Return>", lambda _e: self.start_search())

        ttk.Button(
            scope,
            text="Examinar...",
            command=self.choose_scope,
        ).grid(row=0, column=2, padx=(0, 4))

        ttk.Button(
            scope,
            text="Pestaña actual",
            command=self.use_current_folder,
        ).grid(row=0, column=3)

        criteria = ttk.Frame(self, padding=(6, 3, 6, 5))
        criteria.grid(row=2, column=0, sticky="ew")
        criteria.columnconfigure(1, weight=1)

        ttk.Label(criteria, text="Nombre o patrón:").grid(
            row=0, column=0, sticky="w"
        )

        self.pattern_entry = ttk.Entry(
            criteria,
            textvariable=self.pattern_var,
        )
        self.pattern_entry.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(7, 6),
        )
        self.pattern_entry.bind("<Return>", lambda _e: self.start_search())

        ttk.Label(criteria, text="Extensión:").grid(
            row=0, column=2, sticky="e", padx=(4, 4)
        )

        self.extension_combo = ttk.Combobox(
            criteria,
            textvariable=self.extension_var,
            values=self.EXTENSIONS,
            state="normal",
            width=10,
        )
        self.extension_combo.grid(row=0, column=3, padx=(0, 6))

        self.search_button = ttk.Button(
            criteria,
            text="Buscar",
            command=self.start_search,
        )
        self.search_button.grid(row=0, column=4, padx=(0, 4))

        self.stop_button = ttk.Button(
            criteria,
            text="Detener",
            command=self.stop_search,
            state="disabled",
        )
        self.stop_button.grid(row=0, column=5)

        ttk.Label(
            criteria,
            text=(
                "Admite texto, %, _, * y ?. Ej.: maest, maest%.xlsx o "
                "%informe%.pdf"
            ),
            style="ExplorerMuted.TLabel",
        ).grid(
            row=1,
            column=0,
            columnspan=6,
            sticky="w",
            pady=(5, 0),
        )

        table_wrap = ttk.Frame(self, padding=(6, 0, 6, 0))
        table_wrap.grid(row=3, column=0, sticky="nsew")
        table_wrap.columnconfigure(0, weight=1)
        table_wrap.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            table_wrap,
            columns=("name", "type", "location", "modified"),
            show="headings",
            selectmode="browse",
        )
        self.tree.grid(row=0, column=0, sticky="nsew")

        self.tree.heading("name", text="Nombre")
        self.tree.heading("type", text="Tipo")
        self.tree.heading("location", text="Ubicación")
        self.tree.heading("modified", text="Fecha de modificación")

        self.tree.column("name", width=285, minwidth=150, anchor="w")
        self.tree.column("type", width=145, minwidth=90, anchor="w")
        self.tree.column("location", width=420, minwidth=180, anchor="w")
        self.tree.column("modified", width=150, minwidth=120, anchor="w")

        vbar = ttk.Scrollbar(
            table_wrap,
            orient="vertical",
            command=self.tree.yview,
        )
        vbar.grid(row=0, column=1, sticky="ns")

        hbar = ttk.Scrollbar(
            table_wrap,
            orient="horizontal",
            command=self.tree.xview,
        )
        hbar.grid(row=1, column=0, sticky="ew")

        self.tree.configure(
            yscrollcommand=vbar.set,
            xscrollcommand=hbar.set,
        )
        self.tree.bind("<Double-Button-1>", self.open_selected)
        self.tree.bind("<Return>", self.open_selected)

        bottom = ttk.Frame(self, padding=(6, 5, 6, 5))
        bottom.grid(row=4, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)

        ttk.Label(
            bottom,
            textvariable=self.info_var,
            style="ExplorerMuted.TLabel",
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")

        actions = ttk.Frame(bottom)
        actions.grid(row=0, column=1, sticky="e", padx=(8, 0))

        ttk.Button(
            actions,
            text="Abrir archivo",
            command=self.open_selected,
        ).pack(side="left")

        ttk.Button(
            actions,
            text="Abrir carpeta",
            command=self.open_location,
        ).pack(side="left", padx=(5, 0))

    def set_scope(self, path):
        path = Path(path)
        if path.is_dir():
            self.scope_var.set(str(path))
            self.info_var.set(f"Buscar en {path}")
            self.owner.status_var.set(f"Buscar en {path}")

    def choose_scope(self):
        folder = filedialog.askdirectory(
            initialdir=self.scope_var.get() or str(Path.home()),
            parent=self.winfo_toplevel(),
        )
        if folder:
            self.set_scope(folder)

    def use_current_folder(self):
        folder = self.owner.last_folder_path()
        if folder is None:
            folder = self.owner.default_start_path()
        self.set_scope(folder)

    def start_search(self):
        if self._searching:
            return

        raw_scope = os.path.expandvars(
            os.path.expanduser(self.scope_var.get().strip().strip('"'))
        )
        base = Path(raw_scope)
        if not base.is_dir():
            messagebox.showerror(
                "Carpeta inválida",
                "Selecciona una carpeta o unidad existente.",
                parent=self.winfo_toplevel(),
            )
            return

        pattern = self.pattern_var.get()
        extension = self.extension_var.get().strip().lower()
        if extension and extension != "todas" and not extension.startswith("."):
            extension = "." + extension

        self.tree.delete(*self.tree.get_children(""))
        self.results.clear()
        self._folders_scanned = 0
        self._files_scanned = 0
        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        self._searching = True

        self.search_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.info_var.set("Buscando... las coincidencias aparecen en tiempo real.")
        self.owner.status_var.set(f"Buscando en {base}...")

        def worker():
            folders = 0
            files = 0
            try:
                for folder, _subfolders, names in os.walk(
                    base,
                    onerror=lambda _error: None,
                ):
                    if self._stop_event.is_set():
                        break

                    folders += 1

                    for name in names:
                        if self._stop_event.is_set():
                            break

                        files += 1
                        lower = name.lower()

                        if not _search_name_matches(name, pattern):
                            continue
                        if extension not in ("", "todas") and not lower.endswith(extension):
                            continue

                        path = Path(folder) / name
                        try:
                            stat = path.stat()
                            modified = float(stat.st_mtime)
                        except Exception:
                            modified = 0.0

                        self._queue.put(
                            (
                                "file",
                                str(path),
                                name,
                                folder,
                                modified,
                            )
                        )

                    if folders % 20 == 0:
                        self._queue.put(("progress", folders, files))

                self._queue.put(
                    (
                        "done",
                        folders,
                        files,
                        self._stop_event.is_set(),
                        None,
                    )
                )
            except Exception as exc:
                self._queue.put(
                    (
                        "done",
                        folders,
                        files,
                        self._stop_event.is_set(),
                        str(exc),
                    )
                )

        threading.Thread(target=worker, daemon=True).start()

    def _process_queue(self):
        if not self.winfo_exists():
            return

        for _ in range(250):
            try:
                event = self._queue.get_nowait()
            except queue.Empty:
                break

            kind = event[0]

            if kind == "file":
                _, raw_path, name, folder, modified = event
                path = Path(raw_path)
                index = len(self.results)
                self.results.append(path)

                self.tree.insert(
                    "",
                    "end",
                    iid=f"r{index}",
                    values=(
                        "📄 " + name,
                        self.owner.describe_type(name, False),
                        folder,
                        self.owner.format_time(modified),
                    ),
                )

            elif kind == "progress":
                _, self._folders_scanned, self._files_scanned = event

            elif kind == "done":
                (
                    _,
                    self._folders_scanned,
                    self._files_scanned,
                    cancelled,
                    error,
                ) = event

                self._searching = False
                self.search_button.configure(state="normal")
                self.stop_button.configure(state="disabled")

                message = "Búsqueda detenida" if cancelled else "Búsqueda finalizada"
                if error:
                    message += ": " + error

                summary = (
                    f"{message}. {len(self.results)} coincidencia(s); "
                    f"{self._files_scanned} archivo(s) examinados en "
                    f"{self._folders_scanned} carpeta(s)."
                )
                self.info_var.set(summary)
                self.owner.status_var.set(summary)

        if self._searching:
            summary = (
                f"Buscando... {len(self.results)} coincidencia(s) · "
                f"{self._files_scanned} archivo(s) · "
                f"{self._folders_scanned} carpeta(s)"
            )
            self.info_var.set(summary)
            self.owner.status_var.set(summary)

        try:
            self.after(70, self._process_queue)
        except tk.TclError:
            pass

    def stop_search(self):
        if not self._searching:
            return
        self._stop_event.set()
        self.stop_button.configure(state="disabled")
        self.info_var.set(
            f"Deteniendo búsqueda... {len(self.results)} coincidencia(s)"
        )

    def selected_path(self):
        selection = self.tree.selection()
        if not selection:
            return None

        iid = selection[0]
        if not iid.startswith("r"):
            return None

        try:
            return self.results[int(iid[1:])]
        except (ValueError, IndexError):
            return None

    def open_selected(self, _event=None):
        path = self.selected_path()
        if path is not None:
            self.owner.open_external_path(path)
        return "break"

    def open_location(self):
        path = self.selected_path()
        if path is None:
            return
        self.owner.new_tab(path.parent)

    def on_close(self):
        self._stop_event.set()


class FileExplorerTool(ttk.Frame):
    def __init__(self, parent, app=None):
        super().__init__(parent)
        self.app = app
        self._alive = True
        self._ui_queue = queue.Queue()
        self._tabs = []
        self._active_tab_id = None
        self._next_tab_id = 1
        self._search_tab_id = "search"
        self._search_page = None
        self._last_folder_path = None
        self._clipboard_paths = []
        self._clipboard_cut = False
        self._devices = {}
        self._operation_running = False

        self.address_var = tk.StringVar()
        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Explorador listo")

        self._build_ui()
        self._build_context_menu()
        self._build_search_tab()
        self.new_tab(self.default_start_path())
        self.refresh_devices()
        self.after(80, self._poll_ui_queue)

    # ---------- UI ----------
    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        style = ttk.Style(self)
        style.configure("ExplorerTitle.TLabel", font=("Segoe UI", 14, "bold"))
        style.configure("ExplorerMuted.TLabel", foreground="#707070")
        style.configure("ExplorerNav.TButton", padding=(8, 4))

        # Barra de pestañas estilo Windows 11.
        tabs_outer = ttk.Frame(self, padding=(7, 5, 7, 3))
        tabs_outer.grid(row=0, column=0, sticky="ew")
        tabs_outer.columnconfigure(0, weight=1)

        self.tab_strip = tk.Frame(tabs_outer, bg="#f3f3f3", height=32)
        self.tab_strip.grid(row=0, column=0, sticky="ew")
        self.tab_strip.pack_propagate(False)

        self.tab_inner = tk.Frame(self.tab_strip, bg="#f3f3f3")
        self.tab_inner.pack(side="left", fill="y")

        self.new_tab_btn = tk.Button(
            self.tab_strip,
            text="+",
            font=("Segoe UI", 12),
            width=3,
            relief="flat",
            bd=0,
            bg="#f3f3f3",
            activebackground="#e7e7e7",
            command=lambda: self.new_tab(self.active_path() or self.default_start_path()),
        )
        self.new_tab_btn.pack(side="left", padx=(3, 0), fill="y")

        # Barra de navegación.
        toolbar = ttk.Frame(self, padding=(7, 3, 7, 5))
        toolbar.grid(row=1, column=0, sticky="ew")
        toolbar.columnconfigure(6, weight=1)

        self.back_btn = ttk.Button(toolbar, text="←", width=3, command=self.go_back)
        self.back_btn.grid(row=0, column=0, padx=2)

        self.forward_btn = ttk.Button(toolbar, text="→", width=3, command=self.go_forward)
        self.forward_btn.grid(row=0, column=1, padx=2)

        self.up_btn = ttk.Button(toolbar, text="↑", width=3, command=self.go_up)
        self.up_btn.grid(row=0, column=2, padx=2)

        self.refresh_btn = ttk.Button(toolbar, text="⟳", width=3, command=self.refresh_active)
        self.refresh_btn.grid(row=0, column=3, padx=2)

        self.new_folder_btn = ttk.Button(toolbar, text="Nueva carpeta", command=self.new_folder)
        self.new_folder_btn.grid(row=0, column=4, padx=(7, 3))

        self.address_entry = ttk.Entry(toolbar, textvariable=self.address_var)
        self.address_entry.grid(row=0, column=6, sticky="ew", padx=(8, 3))
        self.address_entry.bind("<Return>", self._go_address)
        self.address_entry.bind("<Escape>", lambda _e: self._sync_address())

        self.go_btn = ttk.Button(toolbar, text="Ir", width=4, command=self._go_address)
        self.go_btn.grid(row=0, column=7, padx=(0, 7))

        self.search_entry = ttk.Entry(toolbar, textvariable=self.search_var, width=22)
        self.search_entry.grid(row=0, column=8, sticky="e")
        self.search_entry.insert(0, "")
        self.search_var.trace_add("write", lambda *_: self._refresh_filter())

        # Área principal.
        main = ttk.Panedwindow(self, orient="horizontal")
        main.grid(row=2, column=0, sticky="nsew", padx=7, pady=(0, 4))

        left = ttk.Frame(main, padding=(6, 6))
        main.add(left, weight=1)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)

        left_head = ttk.Frame(left)
        left_head.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        left_head.columnconfigure(0, weight=1)
        ttk.Label(left_head, text="Ubicaciones", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Button(left_head, text="⟳", width=3, command=self.refresh_devices).grid(row=0, column=1)

        self.side_tree = ttk.Treeview(left, show="tree", selectmode="browse")
        self.side_tree.grid(row=1, column=0, sticky="nsew")
        side_scroll = ttk.Scrollbar(left, orient="vertical", command=self.side_tree.yview)
        side_scroll.grid(row=1, column=1, sticky="ns")
        self.side_tree.configure(yscrollcommand=side_scroll.set)
        self.side_tree.bind("<<TreeviewSelect>>", self._side_selected)
        self.side_tree.bind("<Double-Button-1>", self._side_selected)

        self.side_tree.insert("", "end", iid="quick", text="Acceso rápido", open=True)
        self.side_tree.insert("", "end", iid="devices", text="Dispositivos", open=True)
        self._populate_quick_access()

        right = ttk.Frame(main)
        main.add(right, weight=5)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        self.content_stack = ttk.Frame(right)
        self.content_stack.grid(row=0, column=0, sticky="nsew")
        self.content_stack.columnconfigure(0, weight=1)
        self.content_stack.rowconfigure(0, weight=1)

        # Pie.
        footer = ttk.Frame(self, padding=(9, 2, 9, 6))
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)

        ttk.Label(
            footer,
            textvariable=self.status_var,
            style="ExplorerMuted.TLabel",
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")

        self.clipboard_label = ttk.Label(
            footer,
            text="",
            style="ExplorerMuted.TLabel",
            anchor="e",
        )
        self.clipboard_label.grid(row=0, column=1, padx=(8, 0))

    def _build_context_menu(self):
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Abrir", command=self.open_selected)
        self.context_menu.add_command(label="Abrir en nueva pestaña", command=self.open_selected_new_tab)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Copiar", command=lambda: self.copy_selected(False))
        self.context_menu.add_command(label="Cortar", command=lambda: self.copy_selected(True))
        self.context_menu.add_command(label="Pegar", command=self.paste_files)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Cambiar nombre", command=self.rename_selected)
        self.context_menu.add_command(label="Eliminar", command=self.delete_selected)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Nueva carpeta", command=self.new_folder)
        self.context_menu.add_command(label="Actualizar", command=self.refresh_active)

    def show_context_menu(self, x_root, y_root):
        try:
            self.context_menu.tk_popup(x_root, y_root)
        finally:
            self.context_menu.grab_release()

    # ---------- Pestañas ----------
    def _build_search_tab(self):
        page = SearchTab(self.content_stack, self)
        page.grid(row=0, column=0, sticky="nsew")
        self._search_page = page

        header = tk.Frame(self.tab_inner, bg="#f3f3f3", bd=0)
        button = tk.Button(
            header,
            text="Buscar",
            width=13,
            anchor="center",
            relief="flat",
            bd=0,
            padx=9,
            bg="#e9e9e9",
            activebackground="#ffffff",
            command=lambda: self.activate_tab(self._search_tab_id),
        )
        button.pack(side="left", fill="y")
        header.pack(side="left", padx=(0, 2), fill="y")

        self._tabs.append(
            {
                "id": self._search_tab_id,
                "kind": "search",
                "page": page,
                "header": header,
                "button": button,
                "close": None,
            }
        )

    def _set_search_mode(self, enabled):
        state = "disabled" if enabled else "normal"

        for widget in (
            self.back_btn,
            self.forward_btn,
            self.up_btn,
            self.refresh_btn,
            self.new_folder_btn,
            self.go_btn,
        ):
            try:
                widget.configure(state=state)
            except Exception:
                pass

        try:
            self.address_entry.configure(state=state)
        except Exception:
            pass

        try:
            self.search_entry.configure(state=state)
        except Exception:
            pass

        if enabled:
            self.search_var.set("")
            self.address_var.set("Buscar archivos")
        else:
            self._sync_address()

    def new_tab(self, path=None):
        path = Path(path or self.default_start_path())
        if not path.is_dir():
            path = self.default_start_path()

        tab_id = self._next_tab_id
        self._next_tab_id += 1

        page = ExplorerTab(self.content_stack, self, tab_id, path)
        page.grid(row=0, column=0, sticky="nsew")

        header = tk.Frame(self.tab_inner, bg="#f3f3f3", bd=0)
        button = tk.Button(
            header,
            text=self.tab_title(path),
            width=18,
            anchor="w",
            relief="flat",
            bd=0,
            padx=9,
            bg="#e9e9e9",
            activebackground="#ffffff",
            command=lambda tid=tab_id: self.activate_tab(tid),
        )
        button.pack(side="left", fill="y")

        close = tk.Button(
            header,
            text="×",
            width=2,
            relief="flat",
            bd=0,
            bg="#e9e9e9",
            activebackground="#dedede",
            command=lambda tid=tab_id: self.close_tab(tid),
        )
        close.pack(side="left", fill="y")
        header.pack(side="left", padx=(0, 2), fill="y")

        meta = {
            "id": tab_id,
            "kind": "folder",
            "page": page,
            "header": header,
            "button": button,
            "close": close,
        }
        self._tabs.append(meta)
        self.activate_tab(tab_id)
        return page

    def activate_tab(self, tab_id):
        meta = self._meta_for_tab(tab_id)
        if not meta:
            return

        self._active_tab_id = tab_id
        meta["page"].tkraise()

        for item in self._tabs:
            active = item["id"] == tab_id
            bg = "#ffffff" if active else "#e9e9e9"
            item["button"].configure(bg=bg)

            close = item.get("close")
            if close is not None:
                close.configure(bg=bg)

        is_search = meta.get("kind") == "search"
        self._set_search_mode(is_search)

        if is_search:
            self.status_var.set(meta["page"].info_var.get())
        else:
            self._last_folder_path = Path(meta["page"].path)
            self.search_var.set("")
            self.status_var.set(str(meta["page"].path))

    def close_tab(self, tab_id):
        meta = self._meta_for_tab(tab_id)
        if not meta or meta.get("kind") == "search":
            return
        index = self._tabs.index(meta)
        meta["page"].destroy()
        meta["header"].destroy()
        self._tabs.remove(meta)

        if not self._tabs:
            self._active_tab_id = None
            self.new_tab(self.default_start_path())
            return

        if self._active_tab_id == tab_id:
            target_index = min(index, len(self._tabs) - 1)
            self.activate_tab(self._tabs[target_index]["id"])

    def _meta_for_tab(self, tab_id):
        for meta in self._tabs:
            if meta["id"] == tab_id:
                return meta
        return None

    def active_tab(self):
        meta = self._meta_for_tab(self._active_tab_id)
        if not meta or meta.get("kind") != "folder":
            return None
        return meta["page"]

    def active_path(self):
        tab = self.active_tab()
        return tab.path if tab else None

    def last_folder_path(self):
        tab = self.active_tab()
        if tab is not None:
            self._last_folder_path = Path(tab.path)
            return self._last_folder_path
        if self._last_folder_path is not None:
            return Path(self._last_folder_path)
        return None

    def _tab_path_changed(self, tab):
        meta = self._meta_for_tab(tab.tab_id)
        if meta:
            meta["button"].configure(text=self.tab_title(tab.path))
        if tab.tab_id == self._active_tab_id:
            self._last_folder_path = Path(tab.path)
            self._sync_address()
            self.search_var.set("")

    def tab_title(self, path):
        path = Path(path)
        name = path.name or str(path)
        if len(name) > 18:
            name = name[:15] + "..."
        return name

    # ---------- Navegación ----------
    def default_start_path(self):
        home = Path.home()
        return home if home.is_dir() else Path.cwd()

    def go_back(self):
        tab = self.active_tab()
        if tab:
            tab.back()

    def go_forward(self):
        tab = self.active_tab()
        if tab:
            tab.forward()

    def go_up(self):
        tab = self.active_tab()
        if not tab:
            return
        parent = tab.path.parent
        if parent != tab.path:
            tab.navigate(parent)

    def refresh_active(self):
        tab = self.active_tab()
        if tab:
            tab.refresh()
        self.refresh_devices()

    def focus_address(self):
        self.address_entry.focus_set()
        self.address_entry.selection_range(0, "end")
        return "break"

    def _sync_address(self):
        path = self.active_path()
        if path is not None:
            self.address_var.set(str(path))

    def _go_address(self, _event=None):
        raw = self.address_var.get().strip().strip('"')
        if not raw:
            return "break"
        raw = os.path.expandvars(os.path.expanduser(raw))
        path = Path(raw)
        tab = self.active_tab()
        if not tab:
            return "break"
        if path.is_dir():
            tab.navigate(path)
        elif path.is_file():
            self.open_path(path)
        else:
            self.status_var.set("La ruta no existe")
            self._sync_address()
        return "break"

    def _refresh_filter(self):
        tab = self.active_tab()
        if tab:
            tab.refresh_view()

    # ---------- Apertura ----------
    def open_external_path(self, path):
        path = Path(path)
        try:
            if os.name == "nt":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            self.status_var.set(f"No se pudo abrir: {exc}")

    def open_path(self, path):
        path = Path(path)
        if path.is_dir():
            tab = self.active_tab()
            if tab:
                tab.navigate(path)
            else:
                self.new_tab(path)
            return
        self.open_external_path(path)

    def open_selected(self):
        tab = self.active_tab()
        if not tab:
            return
        paths = tab.selected_paths()
        if not paths:
            return
        self.open_path(paths[0])

    def open_selected_new_tab(self):
        tab = self.active_tab()
        if not tab:
            return
        paths = tab.selected_paths()
        if not paths:
            return
        path = paths[0]
        if path.is_dir():
            self.new_tab(path)
        else:
            self.open_path(path)

    # ---------- Copiar / cortar / pegar ----------
    def copy_selected(self, cut=False):
        tab = self.active_tab()
        if not tab:
            return "break"
        paths = tab.selected_paths()
        if not paths:
            return "break"
        self._clipboard_paths = [Path(p) for p in paths]
        self._clipboard_cut = bool(cut)
        action = "Cortados" if cut else "Copiados"
        self.clipboard_label.configure(
            text=f"{action}: {len(paths)} elemento(s)"
        )
        self.status_var.set(f"{action} {len(paths)} elemento(s)")
        return "break"

    def paste_files(self):
        tab = self.active_tab()
        if not tab or not self._clipboard_paths or self._operation_running:
            return "break"
        destination = tab.path
        sources = [Path(p) for p in self._clipboard_paths]
        cut = self._clipboard_cut
        self._operation_running = True
        self.status_var.set("Moviendo..." if cut else "Copiando...")

        def worker():
            errors = []
            completed = 0
            for source in sources:
                try:
                    if not source.exists():
                        continue
                    target = self.unique_target(destination / source.name)
                    if cut:
                        shutil.move(str(source), str(target))
                    else:
                        if source.is_dir():
                            shutil.copytree(source, target)
                        else:
                            shutil.copy2(source, target)
                    completed += 1
                except Exception as exc:
                    errors.append(f"{source.name}: {exc}")
            self._ui_queue.put(
                ("fileop", "move" if cut else "copy", completed, errors)
            )

        threading.Thread(target=worker, daemon=True).start()
        return "break"

    def unique_target(self, target):
        target = Path(target)
        if not target.exists():
            return target
        parent = target.parent
        if target.is_dir() or not target.suffix:
            stem = target.name
            suffix = ""
        else:
            stem = target.stem
            suffix = target.suffix
        candidate = parent / f"{stem} - copia{suffix}"
        index = 2
        while candidate.exists():
            candidate = parent / f"{stem} - copia ({index}){suffix}"
            index += 1
        return candidate

    # ---------- Gestión de archivos ----------
    def new_folder(self):
        tab = self.active_tab()
        if not tab:
            return
        name = simpledialog.askstring(
            "Nueva carpeta",
            "Nombre de la carpeta:",
            parent=self.winfo_toplevel(),
        )
        if not name:
            return
        name = name.strip()
        if not name or any(c in name for c in '<>:"/\\|?*'):
            messagebox.showerror("Nombre no válido", "El nombre contiene caracteres no permitidos.")
            return
        try:
            (tab.path / name).mkdir()
            tab.refresh()
        except Exception as exc:
            messagebox.showerror("Nueva carpeta", str(exc))

    def rename_selected(self):
        tab = self.active_tab()
        if not tab:
            return "break"
        paths = tab.selected_paths()
        if len(paths) != 1:
            return "break"
        source = paths[0]
        new_name = simpledialog.askstring(
            "Cambiar nombre",
            "Nuevo nombre:",
            initialvalue=source.name,
            parent=self.winfo_toplevel(),
        )
        if not new_name or new_name == source.name:
            return "break"
        try:
            source.rename(source.with_name(new_name))
            tab.refresh()
        except Exception as exc:
            messagebox.showerror("Cambiar nombre", str(exc))
        return "break"

    def delete_selected(self):
        tab = self.active_tab()
        if not tab or self._operation_running:
            return "break"
        paths = tab.selected_paths()
        if not paths:
            return "break"
        names = "\n".join(p.name for p in paths[:8])
        if len(paths) > 8:
            names += f"\n... y {len(paths)-8} más"
        if not messagebox.askyesno(
            "Eliminar",
            "Se eliminarán permanentemente estos elementos:\n\n" + names,
            parent=self.winfo_toplevel(),
        ):
            return "break"

        self._operation_running = True
        self.status_var.set("Eliminando...")

        def worker():
            errors = []
            completed = 0
            for path in paths:
                try:
                    if path.is_dir() and not path.is_symlink():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                    completed += 1
                except Exception as exc:
                    errors.append(f"{path.name}: {exc}")
            self._ui_queue.put(("fileop", "delete", completed, errors))

        threading.Thread(target=worker, daemon=True).start()
        return "break"

    # ---------- Acceso rápido y dispositivos ----------
    def _populate_quick_access(self):
        home = Path.home()
        candidates = [
            ("Inicio", home),
            ("Escritorio", home / "Desktop"),
            ("Descargas", home / "Downloads"),
            ("Documentos", home / "Documents"),
            ("Imágenes", home / "Pictures"),
            ("Música", home / "Music"),
            ("Videos", home / "Videos"),
        ]
        for index, (label, path) in enumerate(candidates):
            if path.is_dir():
                iid = f"q:{index}"
                self.side_tree.insert("quick", "end", iid=iid, text=label)
                self._devices[iid] = {"path": str(path), "kind": "quick"}

    def refresh_devices(self):
        self.status_var.set("Actualizando dispositivos...")

        def worker():
            basic = self._scan_drives_basic()
            enriched = self._enrich_drives_windows(basic)
            self._ui_queue.put(("devices", enriched))

        threading.Thread(target=worker, daemon=True).start()

    def _scan_drives_basic(self):
        drives = []
        if os.name != "nt":
            try:
                usage = shutil.disk_usage("/")
                drives.append(
                    {
                        "root": "/",
                        "label": "Sistema",
                        "kind": "Unidad",
                        "free": usage.free,
                        "total": usage.total,
                        "model": "",
                    }
                )
            except Exception:
                pass
            return drives

        kernel32 = ctypes.windll.kernel32
        mask = int(kernel32.GetLogicalDrives())
        get_type = kernel32.GetDriveTypeW
        get_type.argtypes = [ctypes.c_wchar_p]
        get_type.restype = ctypes.c_uint

        DRIVE_TYPES = {
            2: "USB / extraíble",
            3: "Unidad fija",
            4: "Red",
            5: "CD / DVD",
            6: "RAM",
        }

        for index in range(26):
            if not (mask & (1 << index)):
                continue
            letter = chr(ord("A") + index)
            root = f"{letter}:\\"
            drive_type = int(get_type(root))
            label = self._volume_label(root)
            try:
                usage = shutil.disk_usage(root)
                free = usage.free
                total = usage.total
            except Exception:
                free = 0
                total = 0
            drives.append(
                {
                    "root": root,
                    "letter": letter,
                    "label": label,
                    "kind": DRIVE_TYPES.get(drive_type, "Unidad"),
                    "drive_type": drive_type,
                    "free": free,
                    "total": total,
                    "model": "",
                    "bus": "",
                    "media": "",
                }
            )
        return drives

    def _volume_label(self, root):
        if os.name != "nt":
            return ""
        try:
            kernel32 = ctypes.windll.kernel32
            volume_name = ctypes.create_unicode_buffer(261)
            fs_name = ctypes.create_unicode_buffer(261)
            serial = ctypes.c_ulong()
            max_component = ctypes.c_ulong()
            flags = ctypes.c_ulong()
            ok = kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(root),
                volume_name,
                len(volume_name),
                ctypes.byref(serial),
                ctypes.byref(max_component),
                ctypes.byref(flags),
                fs_name,
                len(fs_name),
            )
            return volume_name.value if ok else ""
        except Exception:
            return ""

    def _enrich_drives_windows(self, drives):
        if os.name != "nt" or not drives:
            return drives

        fixed_letters = [
            d.get("letter") for d in drives
            if d.get("drive_type") in (2, 3) and d.get("letter")
        ]
        if not fixed_letters:
            return drives

        letters_ps = ",".join(f"'{x}'" for x in fixed_letters)
        script = (
            f"$letters=@({letters_ps});"
            "$out=@();"
            "foreach($l in $letters){"
            "try{"
            "$p=Get-Partition -DriveLetter $l -ErrorAction Stop;"
            "$d=$p|Get-Disk -ErrorAction Stop;"
            "$pd=Get-PhysicalDisk -ErrorAction SilentlyContinue | Where-Object {"
            "$_.FriendlyName -eq $d.FriendlyName -or [string]$_.DeviceId -eq [string]$d.Number"
            "} | Select-Object -First 1;"
            "$out += [pscustomobject]@{Drive=$l;Model=$d.FriendlyName;Bus=[string]$d.BusType;Media=[string]$pd.MediaType}"
            "}catch{}"
            "};$out|ConvertTo-Json -Compress"
        )

        try:
            creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    script,
                ],
                capture_output=True,
                text=True,
                timeout=8,
                creationflags=creationflags,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return drives
            data = json.loads(result.stdout)
            if isinstance(data, dict):
                data = [data]
            mapping = {str(x.get("Drive", "")).upper(): x for x in data if isinstance(x, dict)}
        except Exception:
            return drives

        for drive in drives:
            info = mapping.get(str(drive.get("letter", "")).upper())
            if not info:
                continue
            model = str(info.get("Model", "") or "")
            bus = str(info.get("Bus", "") or "")
            media = str(info.get("Media", "") or "")
            drive["model"] = model
            drive["bus"] = bus
            drive["media"] = media

            probe = f"{media} {model}".lower()
            if "usb" in bus.lower():
                drive["kind"] = "USB"
            elif "ssd" in probe or "solid state" in probe:
                drive["kind"] = "SSD"
            elif "hdd" in probe or "hard disk" in probe:
                drive["kind"] = "HDD"
            elif drive.get("drive_type") == 3:
                drive["kind"] = "HDD / SSD"

        return drives

    def _apply_devices(self, drives):
        for iid in self.side_tree.get_children("devices"):
            self.side_tree.delete(iid)
            self._devices.pop(iid, None)

        for index, drive in enumerate(drives):
            iid = f"d:{index}"
            label = drive.get("label") or "Unidad"
            root = drive.get("root", "")
            kind = drive.get("kind", "Unidad")
            free = drive.get("free", 0)
            total = drive.get("total", 0)

            if total:
                detail = f"{self.format_size(free)} libres de {self.format_size(total)}"
            else:
                detail = "Sin medio" if kind == "CD / DVD" else ""

            text = f"{root}  {label}  ·  {kind}"
            if detail:
                text += f"  ·  {detail}"
            self.side_tree.insert("devices", "end", iid=iid, text=text)
            self._devices[iid] = drive

        self.status_var.set(f"{len(drives)} dispositivo(s) detectado(s)")

    def _side_selected(self, _event=None):
        selection = self.side_tree.selection()
        if not selection:
            return
        iid = selection[0]
        info = self._devices.get(iid)
        if not info:
            return
        raw = info.get("path") or info.get("root")
        if not raw:
            return
        path = Path(raw)

        if self._active_tab_id == self._search_tab_id:
            if path.is_dir() and self._search_page is not None:
                self._search_page.set_scope(path)
            elif info.get("kind") == "CD / DVD":
                self.status_var.set("No hay medio disponible en la unidad óptica")
            return

        tab = self.active_tab()
        if tab and path.is_dir():
            tab.navigate(path)
        elif info.get("kind") == "CD / DVD":
            self.status_var.set("No hay medio disponible en la unidad óptica")

    # ---------- Cola UI ----------
    def _poll_ui_queue(self):
        if not self._alive:
            return
        try:
            while True:
                message = self._ui_queue.get_nowait()
                kind = message[0]

                if kind == "directory":
                    _, tab_id, token, items, error, _first = message
                    meta = self._meta_for_tab(tab_id)
                    if meta:
                        meta["page"].apply_directory_result(token, items, error)

                elif kind == "devices":
                    self._apply_devices(message[1])

                elif kind == "fileop":
                    _, operation, completed, errors = message
                    self._operation_running = False
                    if operation == "move" and not errors:
                        self._clipboard_paths = []
                        self._clipboard_cut = False
                        self.clipboard_label.configure(text="")
                    self.refresh_active()
                    if errors:
                        self.status_var.set(
                            f"Completados: {completed} · errores: {len(errors)}"
                        )
                        messagebox.showwarning(
                            "Operación completada con errores",
                            "\n".join(errors[:12]),
                            parent=self.winfo_toplevel(),
                        )
                    else:
                        verbs = {
                            "copy": "Copiados",
                            "move": "Movidos",
                            "delete": "Eliminados",
                        }
                        self.status_var.set(
                            f"{verbs.get(operation, 'Procesados')} {completed} elemento(s)"
                        )
        except queue.Empty:
            pass

        try:
            self.after(80, self._poll_ui_queue)
        except tk.TclError:
            pass

    # ---------- Utilidades ----------
    @staticmethod
    def describe_type(name, is_dir):
        if is_dir:
            return "Carpeta de archivos"
        suffix = Path(name).suffix.lower().lstrip(".")
        known = {
            "txt": "Documento de texto",
            "pdf": "Documento PDF",
            "doc": "Documento Word",
            "docx": "Documento Word",
            "xls": "Hoja de Excel",
            "xlsx": "Hoja de Excel",
            "ppt": "Presentación",
            "pptx": "Presentación",
            "jpg": "Imagen JPEG",
            "jpeg": "Imagen JPEG",
            "png": "Imagen PNG",
            "gif": "Imagen GIF",
            "webp": "Imagen WebP",
            "mp3": "Audio MP3",
            "wav": "Audio WAV",
            "flac": "Audio FLAC",
            "mp4": "Video MP4",
            "mkv": "Video MKV",
            "avi": "Video AVI",
            "zip": "Archivo ZIP",
            "rar": "Archivo RAR",
            "7z": "Archivo 7-Zip",
            "exe": "Aplicación",
            "py": "Archivo Python",
        }
        return known.get(suffix, f"Archivo {suffix.upper()}" if suffix else "Archivo")

    @staticmethod
    def format_size(value):
        try:
            size = float(value)
        except Exception:
            return ""
        units = ["B", "KB", "MB", "GB", "TB", "PB"]
        for unit in units:
            if size < 1024 or unit == units[-1]:
                if unit == "B":
                    return f"{int(size)} {unit}"
                return f"{size:.1f} {unit}"
            size /= 1024
        return ""

    @staticmethod
    def format_time(timestamp):
        try:
            return _dt.datetime.fromtimestamp(timestamp).strftime("%d/%m/%Y %H:%M")
        except Exception:
            return ""

    # ---------- Ciclo PTM ----------
    def on_show(self):
        pass

    def on_hide(self):
        pass

    def on_close(self):
        self._alive = False
        if self._search_page is not None:
            self._search_page.on_close()


App = FileExplorerTool


def _run_standalone():
    root = tk.Tk()
    root.title(TOOL_NAME)
    root.geometry("1180x760")
    root.minsize(820, 520)
    tool = FileExplorerTool(root)
    tool.pack(fill="both", expand=True)
    root.protocol("WM_DELETE_WINDOW", lambda: (tool.on_close(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    _run_standalone()