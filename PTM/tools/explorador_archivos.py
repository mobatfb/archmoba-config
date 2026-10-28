# ARGUMENTOS: explorador archivos carpetas windows 11 pestañas tabs copiar pegar cortar dispositivos hdd ssd usb cd dvd unidades discos
import ctypes
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
    "Explorador de archivos tipo Windows 11 con pestañas, copiar/cortar/pegar, "
    "navegacion y panel lateral de HDD, SSD, USB, CD/DVD y unidades de red."
)
TOOL_VERSION = "1.0.0"


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
                    item["name"],
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


class FileExplorerTool(ttk.Frame):
    def __init__(self, parent, app=None):
        super().__init__(parent)
        self.app = app
        self._alive = True
        self._ui_queue = queue.Queue()
        self._tabs = []
        self._active_tab_id = None
        self._next_tab_id = 1
        self._clipboard_paths = []
        self._clipboard_cut = False
        self._devices = {}
        self._operation_running = False

        self.address_var = tk.StringVar()
        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Explorador listo")

        self._build_ui()
        self._build_context_menu()
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

        ttk.Button(toolbar, text="←", width=3, command=self.go_back).grid(row=0, column=0, padx=2)
        ttk.Button(toolbar, text="→", width=3, command=self.go_forward).grid(row=0, column=1, padx=2)
        ttk.Button(toolbar, text="↑", width=3, command=self.go_up).grid(row=0, column=2, padx=2)
        ttk.Button(toolbar, text="⟳", width=3, command=self.refresh_active).grid(row=0, column=3, padx=2)
        ttk.Button(toolbar, text="Nueva carpeta", command=self.new_folder).grid(row=0, column=4, padx=(7, 3))

        self.address_entry = ttk.Entry(toolbar, textvariable=self.address_var)
        self.address_entry.grid(row=0, column=6, sticky="ew", padx=(8, 3))
        self.address_entry.bind("<Return>", self._go_address)
        self.address_entry.bind("<Escape>", lambda _e: self._sync_address())

        ttk.Button(toolbar, text="Ir", width=4, command=self._go_address).grid(row=0, column=7, padx=(0, 7))

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
            item["close"].configure(bg=bg)

        self._sync_address()
        self.search_var.set("")
        self.status_var.set(str(meta["page"].path))

    def close_tab(self, tab_id):
        meta = self._meta_for_tab(tab_id)
        if not meta:
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
        return meta["page"] if meta else None

    def active_path(self):
        tab = self.active_tab()
        return tab.path if tab else None

    def _tab_path_changed(self, tab):
        meta = self._meta_for_tab(tab.tab_id)
        if meta:
            meta["button"].configure(text=self.tab_title(tab.path))
        if tab.tab_id == self._active_tab_id:
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
    def open_path(self, path):
        path = Path(path)
        try:
            if path.is_dir():
                tab = self.active_tab()
                if tab:
                    tab.navigate(path)
                return
            if os.name == "nt":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            self.status_var.set(f"No se pudo abrir: {exc}")

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