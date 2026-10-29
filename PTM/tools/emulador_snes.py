# ARGUMENTOS: snes super nintendo emulador rom sfc smc retroarch snes9x juegos gamepad
"""ARCHMOBA SNES: biblioteca Python para ejecutar ROMs con Snes9x o RetroArch.

El nucleo de emulacion es externo; esta interfaz no emula la CPU SNES en Python.
No distribuye ROMs ni BIOS. Funciona como herramienta integrada en PTM.
"""
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import zipfile
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

TOOL_NAME = "ARCHMOBA SNES"
TOOL_DESCRIPTION = "Biblioteca y lanzador de juegos SNES con Snes9x o RetroArch."
TOOL_VERSION = "1.0.0"
ROM_EXTS = {".sfc", ".smc", ".fig", ".swc", ".zip"}
INNER_EXTS = ROM_EXTS - {".zip"}
MAX_ZIP_ROM = 32 * 1024 * 1024


def _config_dir():
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "ARCHMOBA" / "PTM" / "SNES"
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "archmoba" / "ptm" / "snes"


def _candidate_executables(kind):
    """Encuentra ejecutables locales sin descargar software ni usar shell."""
    names = (["snes9x-x64.exe", "snes9x.exe", "snes9x-gtk", "snes9x"]
             if kind == "Snes9x" else ["retroarch.exe", "retroarch"])
    env = "SNES9X_PATH" if kind == "Snes9x" else "RETROARCH_PATH"
    paths = []
    if os.environ.get(env):
        paths.append(Path(os.environ[env]).expanduser())
    for name in names:
        found = shutil.which(name)
        if found:
            paths.append(Path(found))
    here = Path(__file__).resolve().parent
    for base in (here, here / "emulators", here / "snes9x", here / "retroarch"):
        paths.extend(base / name for name in names)
    if os.name == "nt":
        for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            if os.environ.get(key):
                root = Path(os.environ[key])
                for sub in ("Snes9x", "snes9x", "RetroArch", "RetroArch-Win64"):
                    paths.extend(root / sub / name for name in names)
        for root in (Path("C:/snes9x"), Path("C:/RetroArch-Win64")):
            paths.extend(root / name for name in names)
    for path in paths:
        if path.is_file() and (os.name == "nt" or os.access(path, os.X_OK)):
            return str(path.resolve())
    return ""


def _find_core(executable=""):
    suffixes = (".dll",) if os.name == "nt" else (".so", ".dylib")
    roots = []
    if executable:
        roots.append(Path(executable).expanduser().parent / "cores")
    roots.extend([
        Path.home() / ".config/retroarch/cores",
        Path.home() / ".local/share/retroarch/cores",
        Path.home() / ".var/app/org.libretro.RetroArch/config/retroarch/cores",
        Path("/usr/lib/libretro"),
        Path("/usr/lib/x86_64-linux-gnu/libretro"),
    ])
    for root in roots:
        for name in ("snes9x_libretro", "snes9x2010_libretro", "bsnes_libretro"):
            for suffix in suffixes:
                path = root / (name + suffix)
                if path.is_file():
                    return str(path.resolve())
    return ""


def _unpack_rom(archive, cache_dir):
    """Extrae una ROM compatible de un ZIP, con limite anti-zip-bomb.

    Nunca utiliza rutas internas del ZIP como destinos, evitando path traversal.
    """
    archive = Path(archive)
    with zipfile.ZipFile(archive) as zf:
        members = [item for item in zf.infolist()
                   if not item.is_dir() and Path(item.filename).suffix.lower() in INNER_EXTS]
        if not members:
            raise ValueError("El ZIP no contiene archivos .sfc, .smc, .fig o .swc.")
        members.sort(key=lambda item: (Path(item.filename).suffix.lower() != ".sfc",
                                       item.filename.casefold()))
        member = members[0]
        if member.file_size > MAX_ZIP_ROM:
            raise ValueError("La ROM comprimida supera el limite de 32 MB.")
        stat = archive.stat()
        identity = f"{archive.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{member.filename}"
        key = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        destination = cache_dir / (key + Path(member.filename).suffix.lower())
        if destination.is_file() and destination.stat().st_size == member.file_size:
            return destination
        temp = destination.with_suffix(destination.suffix + ".part")
        try:
            size = 0
            with zf.open(member) as source, temp.open("wb") as output:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_ZIP_ROM:
                        raise ValueError("ZIP rechazado: contenido demasiado grande.")
                    output.write(chunk)
            os.replace(temp, destination)
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
        return destination


class SnesEmulatorTool(ttk.Frame):
    def __init__(self, parent, app=None):
        super().__init__(parent)
        self.app = app
        self.data_dir = _config_dir()
        self.state_file = self.data_dir / "state.json"
        self.roms = []
        self.recent = []
        self.favorites = []
        self.visible = {"all": [], "recent": [], "favorites": []}
        self.lists = {}
        self._selected_path = ""
        self._process = None
        self._running_rom = ""
        self._scan_queue = queue.Queue()
        self._scan_thread = None
        self._scan_cancel = threading.Event()
        self._render_job = None
        self._alive = True
        self.engine_var = tk.StringVar(value="Auto")
        self.exe_var = tk.StringVar()
        self.core_var = tk.StringVar()
        self.fullscreen_var = tk.BooleanVar(value=False)
        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Agrega una ROM propia para empezar.")
        self.title_var = tk.StringVar(value="Selecciona un juego")
        self.info_var = tk.StringVar(value="Archivos admitidos: SFC, SMC, FIG, SWC y ZIP")
        self.count_vars = {key: tk.StringVar(value="0 juegos")
                           for key in ("all", "recent", "favorites")}
        self._build_ui()
        self._load_state()
        self._refresh_lists()
        self.after(150, self._poll)

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        style = ttk.Style(self)
        style.configure("SnesTitle.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("SnesMuted.TLabel", foreground="#687486")
        style.configure("Snes.TNotebook.Tab", padding=(14, 8))
        header = ttk.Frame(self, padding=(15, 10))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="🎮 ARCHMOBA SNES", style="SnesTitle.TLabel").grid(
            row=0, column=0, sticky="w")
        ttk.Label(header, text="v" + TOOL_VERSION, style="SnesMuted.TLabel").grid(
            row=0, column=1, sticky="e")
        body = ttk.Panedwindow(self, orient="horizontal")
        body.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 8))
        left = ttk.Frame(body, padding=5)
        right = ttk.Frame(body, padding=(12, 4))
        body.add(left, weight=2)
        body.add(right, weight=3)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        tools = ttk.Frame(left)
        tools.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(tools, text="+ ROM", command=self.add_roms).pack(side="left")
        ttk.Button(tools, text="+ Carpeta", command=self.add_folder).pack(
            side="left", padx=(5, 0))
        ttk.Button(tools, text="Detener", command=self.stop_scan).pack(
            side="left", padx=(5, 0))
        self.tabs = ttk.Notebook(left, style="Snes.TNotebook")
        self.tabs.grid(row=1, column=0, sticky="nsew")
        for key, title in (("all", "Todos"), ("recent", "Recientes"),
                           ("favorites", "Favoritos")):
            tab = ttk.Frame(self.tabs, padding=5)
            self.tabs.add(tab, text=title)
            tab.columnconfigure(0, weight=1)
            tab.rowconfigure(1, weight=1)
            ttk.Label(tab, textvariable=self.count_vars[key],
                      style="SnesMuted.TLabel").grid(row=0, column=0, sticky="w")
            holder = ttk.Frame(tab)
            holder.grid(row=1, column=0, sticky="nsew", pady=(5, 0))
            holder.columnconfigure(0, weight=1)
            holder.rowconfigure(0, weight=1)
            box = tk.Listbox(holder, activestyle="none", exportselection=False,
                             font=("Segoe UI", 10), bd=0, highlightthickness=1)
            box.grid(row=0, column=0, sticky="nsew")
            scroll = ttk.Scrollbar(holder, orient="vertical", command=box.yview)
            scroll.grid(row=0, column=1, sticky="ns")
            box.configure(yscrollcommand=scroll.set)
            box.bind("<<ListboxSelect>>", lambda event, k=key: self._on_select(k))
            box.bind("<Double-Button-1>", lambda event, k=key: self.play_selected(k))
            box.bind("<Return>", lambda event, k=key: self.play_selected(k))
            box.bind("<Button-3>", lambda event, k=key: self._context_menu(event, k))
            self.lists[key] = box
        self.tabs.bind("<<NotebookTabChanged>>", lambda _event: self._on_select())
        search = ttk.Frame(left)
        search.grid(row=2, column=0, sticky="ew", pady=(9, 0))
        search.columnconfigure(0, weight=1)
        ttk.Label(search, text="Buscar en todas las pestañas",
                  style="SnesMuted.TLabel").grid(row=0, column=0, columnspan=2,
                                                  sticky="w", pady=(0, 4))
        entry = ttk.Entry(search, textvariable=self.search_var)
        entry.grid(row=1, column=0, sticky="ew")
        entry.bind("<Escape>", lambda _event: self.search_var.set(""))
        ttk.Button(search, text="✕", width=3,
                   command=lambda: self.search_var.set("")).grid(
            row=1, column=1, padx=(5, 0))
        self.search_var.trace_add("write", lambda *_: self._schedule_render())

        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        self.preview = tk.Canvas(right, bg="#101827", bd=0, highlightthickness=0,
                                 height=220)
        self.preview.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        self.preview.bind("<Configure>", self._draw_console)
        ttk.Label(right, textvariable=self.title_var,
                  font=("Segoe UI", 13, "bold")).grid(row=1, column=0, sticky="w")
        ttk.Label(right, textvariable=self.info_var,
                  style="SnesMuted.TLabel", wraplength=500).grid(
            row=2, column=0, sticky="w", pady=(2, 8))
        actions = ttk.Frame(right)
        actions.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        ttk.Button(actions, text="▶ Jugar", command=self.play_selected).pack(side="left")
        ttk.Button(actions, text="★ Favorito", command=self.toggle_favorite).pack(
            side="left", padx=(5, 0))
        ttk.Button(actions, text="Abrir carpeta", command=self.open_folder).pack(
            side="left", padx=(5, 0))
        ttk.Button(actions, text="Quitar", command=self.remove_selected).pack(
            side="left", padx=(5, 0))
        config = ttk.LabelFrame(right, text="Motor de emulación", padding=9)
        config.grid(row=4, column=0, sticky="ew")
        config.columnconfigure(1, weight=1)
        ttk.Label(config, text="Motor").grid(row=0, column=0, sticky="w")
        ttk.Combobox(config, textvariable=self.engine_var, state="readonly",
                     values=("Auto", "Snes9x", "RetroArch"), width=13).grid(
            row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Button(config, text="Detectar", command=self.detect_backend).grid(
            row=0, column=2, padx=(6, 0))
        ttk.Label(config, text="Ejecutable").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(config, textvariable=self.exe_var).grid(
            row=1, column=1, sticky="ew", padx=(8, 0), pady=(6, 0))
        ttk.Button(config, text="...", width=3,
                   command=self.choose_executable).grid(row=1, column=2, padx=(6, 0),
                                                         pady=(6, 0))
        ttk.Label(config, text="Núcleo libretro").grid(
            row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(config, textvariable=self.core_var).grid(
            row=2, column=1, sticky="ew", padx=(8, 0), pady=(6, 0))
        ttk.Button(config, text="...", width=3, command=self.choose_core).grid(
            row=2, column=2, padx=(6, 0), pady=(6, 0))
        ttk.Checkbutton(config, text="Pantalla completa al iniciar (RetroArch)",
                        variable=self.fullscreen_var, command=self._save_state).grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(7, 0))
        ttk.Label(config, text="El juego se abre en la ventana del emulador. "
                  "Teclado, mando y guardado se configuran allí.",
                  style="SnesMuted.TLabel", wraplength=490).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Button(right, text="Cerrar juego en ejecución",
                   command=self.close_game).grid(row=5, column=0, sticky="w", pady=(8, 0))
        ttk.Label(self, textvariable=self.status_var, style="SnesMuted.TLabel",
                  padding=(15, 2, 15, 10)).grid(row=2, column=0, sticky="ew")
        for variable in (self.engine_var, self.exe_var, self.core_var):
            variable.trace_add("write", lambda *_: self._save_state())

    def _draw_console(self, event=None):
        c = self.preview
        c.delete("all")
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        cx, cy = w / 2, h / 2
        scale = min(w / 410, h / 245, 1.5)
        def p(x, y):
            return cx + x * scale, cy + y * scale
        c.create_text(*p(0, -82), text="SUPER NINTENDO", fill="#B7C9E5",
                      font=("Segoe UI", max(10, int(16 * scale)), "bold"))
        x1, y1 = p(-165, -55)
        x2, y2 = p(165, 67)
        c.create_rectangle(x1, y1, x2, y2, fill="#D7D7DF", outline="#A7A8BA",
                           width=3)
        x1, y1 = p(-120, -35)
        x2, y2 = p(120, -12)
        c.create_rectangle(x1, y1, x2, y2, fill="#A9A9B7", outline="")
        for x, y, color in ((105, 20, "#7256B5"), (126, 35, "#B36E9E"),
                            (83, 35, "#5A9CBB"), (105, 49, "#6BAE88")):
            px, py = p(x, y)
            r = 10 * scale
            c.create_oval(px-r, py-r, px+r, py+r, fill=color, outline="#E9E9F1")
        c.create_text(*p(-70, 31), text="✚", fill="#404353",
                      font=("Segoe UI Symbol", max(12, int(34 * scale)), "bold"))
        c.create_text(*p(0, 35), text="START   SELECT", fill="#5A5C6B",
                      font=("Segoe UI", max(8, int(10 * scale)), "bold"))
        c.create_text(*p(0, 91), text="ARCHMOBA • SNES", fill="#7895C2",
                      font=("Segoe UI", max(9, int(12 * scale))))

    def _load_state(self):
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return
            for key, attr in (("roms", "roms"), ("recent", "recent"),
                              ("favorites", "favorites")):
                values = data.get(key, [])
                if isinstance(values, list):
                    setattr(self, attr, list(dict.fromkeys(
                        item for item in values if isinstance(item, str))))
            if data.get("engine") in ("Auto", "Snes9x", "RetroArch"):
                self.engine_var.set(data["engine"])
            for key, var in (("executable", self.exe_var), ("core", self.core_var)):
                if isinstance(data.get(key), str):
                    var.set(data[key])
            self.fullscreen_var.set(data.get("fullscreen") is True)
        except (OSError, ValueError, TypeError):
            pass

    def _save_state(self):
        data = {"roms": self.roms, "recent": self.recent,
                "favorites": self.favorites, "engine": self.engine_var.get(),
                "executable": self.exe_var.get(), "core": self.core_var.get(),
                "fullscreen": self.fullscreen_var.get()}
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            temp = self.state_file.with_suffix(".json.tmp")
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            os.replace(temp, self.state_file)
        except OSError:
            pass

    def _schedule_render(self):
        if self._render_job is not None:
            try:
                self.after_cancel(self._render_job)
            except tk.TclError:
                pass
        self._render_job = self.after(110, self._refresh_lists)

    def _refresh_lists(self):
        self._render_job = None
        query = self.search_var.get().strip().casefold()
        for key, paths in (("all", self.roms), ("recent", self.recent),
                           ("favorites", self.favorites)):
            filtered = [path for path in paths if query in path.casefold()]
            self.visible[key] = filtered
            widget = self.lists[key]
            widget.delete(0, "end")
            if filtered:
                widget.insert("end", *("★ " + Path(path).stem if path in self.favorites
                                       else Path(path).stem for path in filtered))
            else:
                widget.insert("end", "Sin coincidencias" if query else "Sin juegos")
            self.count_vars[key].set(f"{len(filtered)} de {len(paths)}" if query
                                     else f"{len(paths)} juegos")

    def _active_tab(self):
        idx = self.tabs.index(self.tabs.select())
        return ("all", "recent", "favorites")[idx]

    def _selected(self, key=None):
        key = key or self._active_tab()
        indices = self.lists[key].curselection()
        paths = self.visible[key]
        if indices and indices[0] < len(paths):
            return paths[indices[0]]
        return self._selected_path if self._selected_path in paths else ""

    def _on_select(self, key=None):
        path = self._selected(key)
        if not path:
            return
        self._selected_path = path
        name = Path(path).stem
        self.title_var.set(name)
        try:
            size = Path(path).stat().st_size / (1024 * 1024)
            self.info_var.set(f"{Path(path).suffix.upper()} • {size:.2f} MB\n{path}")
        except OSError:
            self.info_var.set("Archivo no disponible: " + path)

    def _add_paths(self, paths):
        known = set(self.roms)
        added = 0
        for item in paths:
            path = str(Path(item).expanduser().resolve())
            if Path(path).suffix.lower() in ROM_EXTS and path not in known:
                self.roms.append(path)
                known.add(path)
                added += 1
        if added:
            self.roms.sort(key=lambda path: (Path(path).name.casefold(), path.casefold()))
            self._save_state()
            self._schedule_render()
        return added

    def add_roms(self):
        paths = filedialog.askopenfilenames(
            parent=self, title="Seleccionar ROMs SNES",
            filetypes=[("Juegos SNES", "*.sfc *.smc *.fig *.swc *.zip"),
                       ("Todos", "*.*")])
        if paths:
            added = self._add_paths(paths)
            self.status_var.set(f"{added} juego(s) agregado(s) a la biblioteca.")

    def add_folder(self):
        folder = filedialog.askdirectory(parent=self, title="Carpeta de ROMs SNES")
        if not folder:
            return
        if self._scan_thread and self._scan_thread.is_alive():
            messagebox.showinfo(TOOL_NAME, "Ya hay un escaneo en curso.", parent=self)
            return
        self._scan_cancel.clear()
        self.status_var.set("Buscando ROMs en " + folder)
        self._scan_thread = threading.Thread(target=self._scan_folder,
                                             args=(folder,), daemon=True)
        self._scan_thread.start()

    def _scan_folder(self, folder):
        batch, folders = [], 0
        try:
            for root, dirs, files in os.walk(folder, followlinks=False):
                if self._scan_cancel.is_set():
                    break
                dirs[:] = [name for name in dirs
                           if not os.path.islink(os.path.join(root, name))]
                folders += 1
                for name in files:
                    if self._scan_cancel.is_set():
                        break
                    if Path(name).suffix.lower() in ROM_EXTS:
                        batch.append(os.path.join(root, name))
                        if len(batch) >= 30:
                            self._scan_queue.put(("batch", batch))
                            batch = []
                if folders % 100 == 0:
                    self._scan_queue.put(("progress", folders))
            if batch:
                self._scan_queue.put(("batch", batch))
            self._scan_queue.put(("done", self._scan_cancel.is_set()))
        except Exception as exc:
            self._scan_queue.put(("error", str(exc)))

    def stop_scan(self):
        self._scan_cancel.set()

    def _poll(self):
        if not self._alive:
            return
        try:
            for _ in range(20):
                try:
                    message = self._scan_queue.get_nowait()
                except queue.Empty:
                    break
                kind = message[0]
                if kind == "batch":
                    self._add_paths(message[1])
                elif kind == "progress":
                    self.status_var.set(f"Buscando ROMs... {message[1]} carpetas")
                elif kind == "done":
                    self.status_var.set("Escaneo detenido" if message[1]
                                        else f"Escaneo completo: {len(self.roms)} juegos")
                elif kind == "error":
                    self.status_var.set("Error de escaneo: " + message[1])
            if self._process is not None and self._process.poll() is not None:
                code = self._process.returncode
                self._process = None
                self.status_var.set("Emulador cerrado" if code == 0 else
                                    f"El emulador terminó (código {code}).")
        except tk.TclError:
            return
        try:
            if self.winfo_exists():
                self.after(180, self._poll)
        except tk.TclError:
            pass

    def choose_executable(self):
        path = filedialog.askopenfilename(parent=self, title="Ejecutable Snes9x o RetroArch")
        if path:
            self.exe_var.set(path)
            if "retroarch" in Path(path).name.lower():
                self.engine_var.set("RetroArch")
            elif "snes9x" in Path(path).name.lower():
                self.engine_var.set("Snes9x")

    def choose_core(self):
        path = filedialog.askopenfilename(parent=self, title="Núcleo SNES libretro")
        if path:
            self.core_var.set(path)
            self.engine_var.set("RetroArch")

    def detect_backend(self):
        desired = self.engine_var.get()
        kinds = [desired] if desired != "Auto" else ["Snes9x", "RetroArch"]
        for kind in kinds:
            found = _candidate_executables(kind)
            if found:
                self.engine_var.set(kind)
                self.exe_var.set(found)
                if kind == "RetroArch" and not Path(self.core_var.get()).is_file():
                    self.core_var.set(_find_core(found))
                self.status_var.set(f"Motor detectado: {kind} ({found})")
                return
        self.status_var.set("No se encontró Snes9x ni RetroArch. Selecciona su ejecutable.")

    def _backend_command(self, rom):
        selected = self.engine_var.get()
        manual = self.exe_var.get().strip()
        if selected == "Auto" and manual:
            selected = "RetroArch" if "retroarch" in Path(manual).name.lower() else "Snes9x"
        kinds = [selected] if selected != "Auto" else ["Snes9x", "RetroArch"]
        for kind in kinds:
            exe = manual or _candidate_executables(kind)
            if not exe or not Path(exe).expanduser().is_file():
                continue
            exe = str(Path(exe).expanduser().resolve())
            if kind == "Snes9x":
                return [exe, str(rom)], kind
            core = self.core_var.get().strip() or _find_core(exe)
            if not core or not Path(core).expanduser().is_file():
                raise ValueError("RetroArch necesita un núcleo SNES libretro. "
                                 "Instálalo desde RetroArch y selecciónalo en 'Núcleo libretro'.")
            args = [exe, "-L", str(Path(core).expanduser().resolve()), str(rom)]
            if self.fullscreen_var.get():
                args.insert(1, "--fullscreen")
            return args, kind
        raise ValueError("No se encontró Snes9x ni RetroArch. Instala uno de ellos "
                         "y selecciona su ejecutable con el botón '...'.")

    def play_selected(self, key=None):
        path = self._selected(key)
        if not path:
            messagebox.showinfo(TOOL_NAME, "Selecciona un juego de la biblioteca.", parent=self)
            return
        if self._process is not None and self._process.poll() is None:
            messagebox.showinfo(TOOL_NAME, "Cierra el juego actual antes de abrir otro.",
                                parent=self)
            return
        rom = Path(path)
        if not rom.is_file():
            messagebox.showerror(TOOL_NAME, "No se encontró la ROM:\n" + path,
                                 parent=self)
            return
        try:
            target = (_unpack_rom(rom, self.data_dir / "rom_cache")
                      if rom.suffix.lower() == ".zip" else rom)
            args, engine = self._backend_command(target)
            flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
            self._process = subprocess.Popen(
                args, cwd=str(Path(args[0]).parent), stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=flags, close_fds=True)
            self._running_rom = path
            self.recent = [path] + [item for item in self.recent if item != path]
            self.recent = self.recent[:50]
            self._save_state()
            self._schedule_render()
            self.status_var.set(f"Ejecutando {rom.stem} con {engine} (ventana externa).")
        except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
            messagebox.showerror(TOOL_NAME, str(exc), parent=self)
            self.status_var.set("No se pudo iniciar: " + str(exc))

    def toggle_favorite(self):
        path = self._selected()
        if not path:
            return
        if path in self.favorites:
            self.favorites.remove(path)
        else:
            self.favorites.insert(0, path)
        self._save_state()
        self._schedule_render()

    def remove_selected(self):
        path = self._selected()
        if not path:
            return
        if path in self.roms:
            self.roms.remove(path)
        if path in self.recent:
            self.recent.remove(path)
        if path in self.favorites:
            self.favorites.remove(path)
        self._selected_path = ""
        self.title_var.set("Selecciona un juego")
        self.info_var.set("El archivo original no se elimina del disco.")
        self._save_state()
        self._schedule_render()

    def open_folder(self):
        path = self._selected()
        if not path:
            return
        folder = Path(path).parent
        if not folder.is_dir():
            return
        try:
            if os.name == "nt":
                os.startfile(str(folder))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError as exc:
            messagebox.showerror(TOOL_NAME, str(exc), parent=self)

    def _context_menu(self, event, key):
        widget = self.lists[key]
        index = widget.nearest(event.y)
        if index >= len(self.visible[key]):
            return
        widget.selection_clear(0, "end")
        widget.selection_set(index)
        self._on_select(key)
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="▶ Jugar", command=lambda: self.play_selected(key))
        menu.add_command(label="★ Añadir / quitar favorito", command=self.toggle_favorite)
        menu.add_command(label="Abrir carpeta", command=self.open_folder)
        menu.add_separator()
        menu.add_command(label="Quitar de biblioteca", command=self.remove_selected)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def close_game(self):
        if self._process is None or self._process.poll() is not None:
            self.status_var.set("No hay un juego en ejecución.")
            return
        if not messagebox.askyesno(TOOL_NAME,
                "¿Cerrar el emulador? Guarda primero la partida dentro de él.\n"
                "Forzar el cierre puede perder datos no guardados.", parent=self):
            return
        try:
            self._process.terminate()
            self.status_var.set("Solicitando cierre del emulador...")
        except OSError as exc:
            self.status_var.set("No se pudo cerrar: " + str(exc))

    def on_show(self):
        self._schedule_render()

    def on_hide(self):
        # La partida continua en la ventana del emulador.
        pass

    def on_close(self):
        self._alive = False
        self._scan_cancel.set()
        if self._render_job is not None:
            try:
                self.after_cancel(self._render_job)
            except tk.TclError:
                pass
        self._save_state()
        # No mata el proceso externo: el jugador puede seguir jugando.


App = SnesEmulatorTool


def main():
    root = tk.Tk()
    root.title(TOOL_NAME)
    root.geometry("1080x690")
    root.minsize(780, 520)
    tool = App(root)
    tool.pack(fill="both", expand=True)
    def close():
        tool.on_close()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", close)
    root.mainloop()


if __name__ == "__main__":
    main()
