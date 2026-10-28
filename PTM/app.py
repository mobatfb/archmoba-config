# ARGUMENTOS: ptm launcher lanzador buscador ejecutor py python herramientas scripts pestañas icono flotante
import ast
import base64
import csv
import hashlib
import importlib.util
import importlib.metadata
import inspect
import io
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import urllib.error
import urllib.request
import unicodedata
import zipfile
from pathlib import Path
from tkinter import filedialog, messagebox

APP_TITLE = "PTM - Buscador y lanzador de herramientas"
APP_VERSION = "1.0.48"
APP_UPDATE_DATE = "28/10/2026"
APP_UPDATE_TIME = "00:43"

REPO_OWNER = "mobatfb"
REPO_NAME = "archmoba-config"
REPO_RAW_ROOT = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}"
REPO_RAW_BASE = f"{REPO_RAW_ROOT}/main/PTM"
GUIDE_URL = f"{REPO_RAW_BASE}/guide.csv"
GUIDE_API_URL = (
    f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/PTM/guide.csv?ref=main"
)
GUIDE_META_URL = f"{REPO_RAW_BASE}/guide_meta.json"
GUIDE_META_API_URL = (
    f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/PTM/guide_meta.json?ref=main"
)
SELF_CONFIG_URL = f"{REPO_RAW_BASE}/config.json"
SELF_CONFIG_API_URL = (
    f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/PTM/config.json?ref=main"
)

def _version_tuple(value):
    """Convierte 1.2.3 en una tupla comparable sin depender de librerías externas."""
    parts = []
    for part in str(value).strip().split("."):
        match = re.match(r"(\d+)", part)
        parts.append(int(match.group(1)) if match else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def check_self_update(restart=True):
    """Busca una versión nueva de PTM y reemplaza app.py."""

    try:
        remote_config = None

        # Preferir la API de GitHub para leer el HEAD actual de main.
        try:
            api_request = urllib.request.Request(
                SELF_CONFIG_API_URL,
                headers={
                    "User-Agent": f"PTM/{APP_VERSION}",
                    "Accept": "application/vnd.github+json",
                    "Cache-Control": "no-cache",
                },
            )
            with urllib.request.urlopen(api_request, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
            encoded = str(payload.get("content", "")).replace("\n", "")
            remote_config = json.loads(
                base64.b64decode(encoded).decode("utf-8-sig")
            )
        except Exception:
            remote_config = None

        # Respaldo: RAW tradicional.
        if remote_config is None:
            config_request = urllib.request.Request(
                f"{SELF_CONFIG_URL}?v={time.time_ns()}",
                headers={
                    "User-Agent": f"PTM/{APP_VERSION}",
                    "Cache-Control": "no-cache",
                },
            )
            with urllib.request.urlopen(config_request, timeout=8) as response:
                remote_config = json.loads(response.read().decode("utf-8-sig"))

        remote_version = str(remote_config.get("version", "")).strip()
        if not remote_version:
            return False

        if _version_tuple(remote_version) <= _version_tuple(APP_VERSION):
            return False

        app_path = str(remote_config.get("app_path", "PTM/app.py")).strip().replace("\\", "/").lstrip("/")
        expected_name = Path(app_path).name or "app.py"
        if expected_name.lower() != "app.py":
            raise RuntimeError("config.json no apunta a un app.py válido.")

        release_commit = str(remote_config.get("release_commit", "")).strip()
        if not re.fullmatch(r"[0-9a-fA-F]{40}", release_commit):
            raise RuntimeError("config.json no contiene un release_commit válido.")

        immutable_app_url = f"{REPO_RAW_ROOT}/{release_commit}/{app_path}"

        source = None
        last_error = None
        for attempt in range(4):
            try:
                app_request = urllib.request.Request(
                    f"{immutable_app_url}?v={time.time_ns()}",
                    headers={
                        "User-Agent": f"PTM/{APP_VERSION}",
                        "Cache-Control": "no-cache",
                    },
                )
                with urllib.request.urlopen(app_request, timeout=15) as response:
                    source = response.read().decode("utf-8-sig")
                break
            except Exception as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(0.8)

        if source is None:
            raise RuntimeError(f"No se pudo descargar el release fijado: {last_error}")

        version_match = re.search(
            r'''APP_VERSION\s*=\s*["']([^"']+)["']''',
            source,
        )
        downloaded_version = version_match.group(1).strip() if version_match else ""

        if downloaded_version != remote_version:
            raise RuntimeError(
                f"Versión remota inconsistente: config={remote_version}, app.py={downloaded_version or 'sin versión'}"
            )

        compile(source, "PTM/app.py", "exec")

        current_file = Path(__file__).resolve()
        temp_file = current_file.with_suffix(current_file.suffix + ".update")
        temp_file.write_text(source, encoding="utf-8")
        os.replace(temp_file, current_file)

        if restart:
            subprocess.Popen(
                [sys.executable, str(current_file), *sys.argv[1:]],
                cwd=str(current_file.parent),
            )
        return True
    except Exception:
        # Una falla de actualización nunca debe impedir abrir la versión instalada.
        return False


INSTANCE_LOCK_SOCKET = None
INSTANCE_LOCK_PORT = 47651


def acquire_single_instance_lock():
    """Impide que dos instancias de PTM se ejecuten simultáneamente."""
    global INSTANCE_LOCK_SOCKET
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            lock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        lock.bind(("127.0.0.1", INSTANCE_LOCK_PORT))
        lock.listen(1)
        INSTANCE_LOCK_SOCKET = lock
        return True
    except OSError:
        try:
            lock.close()
        except Exception:
            pass
        return False


def release_single_instance_lock():
    """Libera el bloqueo antes de reiniciar PTM por actualización."""
    global INSTANCE_LOCK_SOCKET
    if INSTANCE_LOCK_SOCKET is not None:
        try:
            INSTANCE_LOCK_SOCKET.close()
        except Exception:
            pass
        INSTANCE_LOCK_SOCKET = None


def detect_system_dark_mode():
    """Detecta si el sistema operativo está usando tema oscuro."""
    if sys.platform == "win32":
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return int(value) == 0
        except Exception:
            return False

    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            return "dark" in result.stdout.strip().lower()
        except Exception:
            return False

    theme = (
        os.environ.get("GTK_THEME", "")
        + " "
        + os.environ.get("COLORFGBG", "")
    ).lower()
    return "dark" in theme


DARK_MODE = detect_system_dark_mode()

# Paleta PTM adaptada automáticamente al tema del sistema.
TEAL = "#176684"
TEAL_DARK = "#0F536E"
TAB_INACTIVE = "#145C77"
TAB_HOVER = "#1B7598"
RED = "#FF1616"
ON_ACCENT = "#FFFFFF"

WHITE = "#17191C" if DARK_MODE else "#FFFFFF"
BLACK = "#F2F4F7" if DARK_MODE else "#101010"
LIGHT = "#22252A" if DARK_MODE else "#F4F4F4"
MID = "#3A3F46" if DARK_MODE else "#D7D7D7"
MUTED = "#A9AFB8" if DARK_MODE else "#666666"


class TabButton(tk.Canvas):
    """Pestaña dibujada por código con esquina roja tipo PTM."""

    def __init__(
        self, parent, title, on_open, on_close=None, active=False,
        width=118, height=30, processing=False,
        on_favorite=None, on_reload=None, favorite=False
    ):
        super().__init__(
            parent, width=width, height=height,
            highlightthickness=0, bd=0, bg=WHITE
        )
        self.title = title
        self.on_open = on_open
        self.on_close = on_close
        self.on_favorite = on_favorite
        self.on_reload = on_reload
        self.favorite = bool(favorite)
        self.tab_width = width
        self.tab_height = height
        self.active = active
        self.processing = processing
        self.hovered = False
        self.spinner_angle = 0
        self.spinner_arc = None
        self._spinner_job = None
        self.bind("<Button-1>", self._click)
        self.bind("<Button-3>", self._right_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Destroy>", self._on_destroy)
        self.draw()
        if self.processing:
            self._schedule_spinner()

    def set_active(self, active):
        self.active = active
        self.draw()

    def set_size(self, width):
        self.tab_width = width
        self.configure(width=width)
        self.draw()

    def draw(self):
        self.delete("all")
        self.spinner_arc = None
        w, h = self.tab_width, self.tab_height
        if self.active:
            fill = WHITE
            fg = BLACK if DARK_MODE else TEAL_DARK
            outline = TEAL_DARK
            outline_width = 2
        else:
            fill = TAB_HOVER if self.hovered else TAB_INACTIVE
            fg = ON_ACCENT
            outline = TEAL_DARK
            outline_width = 1

        self.create_rectangle(
            1, 1, w - 1, h - 1,
            fill=fill, outline=outline, width=outline_width
        )
        self.create_polygon(
            w - 18, 1, w - 1, 1, w - 1, 18,
            fill=RED, outline=RED
        )
        if self.active:
            self.create_rectangle(
                1, h - 6, w - 1, h - 1,
                fill=RED, outline=RED
            )

        if self.processing:
            spinner_color = TEAL if self.active else ON_ACCENT
            self.spinner_arc = self.create_arc(
                7, 8, 19, 20,
                start=self.spinner_angle,
                extent=265,
                style="arc",
                outline=spinner_color,
                width=2,
            )
            max_chars = max(5, int((w - 46) / 7.2))
            shown = (
                self.title
                if len(self.title) <= max_chars
                else self.title[: max_chars - 1] + "…"
            )
            text_x = (25 + (w - 20)) / 2
        else:
            max_chars = max(7, int((w - 20) / 7.2))
            shown = (
                self.title
                if len(self.title) <= max_chars
                else self.title[: max_chars - 1] + "…"
            )
            text_x = w / 2

        self.create_text(
            text_x,
            h / 2 - (2 if self.active else 0),
            text=shown,
            fill=fg,
            font=("Segoe UI", 9, "bold" if self.active else "normal"),
        )

    def _on_enter(self, _event=None):
        if not self.active:
            self.hovered = True
            self.draw()

    def _on_leave(self, _event=None):
        if self.hovered:
            self.hovered = False
            self.draw()

    def _schedule_spinner(self):
        if self.processing and self._spinner_job is None:
            self._spinner_job = self.after(45, self._animate_spinner)

    def _animate_spinner(self):
        self._spinner_job = None
        if not self.processing:
            return
        try:
            if not self.winfo_exists():
                return
            self.spinner_angle = (self.spinner_angle - 18) % 360
            if self.spinner_arc is not None:
                self.itemconfigure(self.spinner_arc, start=self.spinner_angle)
            self._schedule_spinner()
        except tk.TclError:
            return

    def _on_destroy(self, _event=None):
        if self._spinner_job is not None:
            try:
                self.after_cancel(self._spinner_job)
            except tk.TclError:
                pass
            self._spinner_job = None

    def _click(self, event):
        # En pestañas de herramientas, la esquina roja también sirve para cerrarlas.
        if self.on_close and event.x >= self.tab_width - 22 and event.y <= 22:
            self.on_close()
        else:
            self.on_open()

    def _right_click(self, _event):
        if self.on_close:
            menu = tk.Menu(self, tearoff=0)
            if self.on_favorite:
                menu.add_command(
                    label=("Quitar de favoritos" if self.favorite
                           else "Añadir a favoritos"),
                    command=self.on_favorite,
                )
            if self.on_reload:
                menu.add_command(label="Recargar", command=self.on_reload)
            menu.add_command(label="Cerrar", command=self.on_close)
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())


class FloatingPTM(tk.Toplevel):
    """Icono flotante PTM generado 100% con Canvas; no usa PNG/ICO."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="#010101")
        try:
            self.wm_attributes("-transparentcolor", "#010101")
        except tk.TclError:
            pass

        self.w = 96
        self.h = 48
        self.geometry(f"{self.w}x{self.h}+0+0")
        self.canvas = tk.Canvas(self, width=self.w, height=self.h, bg="#010101",
                                highlightthickness=0, bd=0, cursor="hand2")
        self.canvas.pack(fill="both", expand=True)
        self._draw()

        self.canvas.bind("<Button-1>", self._left_down)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._left_up)
        self.canvas.bind("<Button-3>", self._menu)
        self.canvas.bind("<Enter>", lambda _e: self._draw(hover=True))
        self.canvas.bind("<Leave>", lambda _e: self._draw(hover=False))
        self.bind("<Double-Button-1>", lambda _e: self.app.toggle_main())

        self._dragging = False
        self._press_xy = (0, 0)
        self._place_default()

    def _draw(self, hover=False):
        self.canvas.delete("all")
        w, h = self.w, self.h
        fill = "#1E7395" if hover else TEAL
        self.canvas.create_rectangle(2, 2, w - 2, h - 2, fill=fill, outline=BLACK, width=1)
        self.canvas.create_polygon(w - 18, 2, w - 2, 2, w - 2, 18, fill=RED, outline=RED)
        self.canvas.create_rectangle(2, h - 8, w - 2, h - 2, fill=RED, outline=RED)
        self.canvas.create_text(w / 2, 17, text="PTM", fill=ON_ACCENT, font=("Segoe UI", 17, "bold"))
        self.canvas.create_text(w / 2, h - 5, text="Buscador y lanzador", fill=ON_ACCENT,
                                font=("Segoe UI", 5, "bold"))

    def _place_default(self):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(10, sw - self.w - 18)
        y = max(10, sh - self.h - 70)
        self.geometry(f"{self.w}x{self.h}+{x}+{y}")

    def _left_down(self, event):
        self._dragging = False
        self._press_xy = (event.x_root, event.y_root)
        self._origin = (self.winfo_x(), self.winfo_y())

    def _drag(self, event):
        dx = event.x_root - self._press_xy[0]
        dy = event.y_root - self._press_xy[1]
        if abs(dx) + abs(dy) > 4:
            self._dragging = True
        x = self._origin[0] + dx
        y = self._origin[1] + dy
        self.geometry(f"+{x}+{y}")

    def _left_up(self, _event):
        if not self._dragging:
            self.app.show_main()

    def _menu(self, _event):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Abrir PTM", command=self.app.show_main)
        menu.add_command(label="Recargar herramientas", command=self.app.reload_tools)
        menu.add_command(label="Abrir carpeta de herramientas", command=self.app.open_tools_folder)
        menu.add_separator()
        menu.add_command(label="Cerrar PTM por completo", command=self.app.exit_app)
        menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())


class PTMApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.dark_mode = DARK_MODE
        self.configure(bg=WHITE)
        self.base_dir = Path(__file__).resolve().parent
        self.tools_dir = self.base_dir / "tools"
        self.tools_dir.mkdir(exist_ok=True)
        self.guide_path = self.base_dir / "guide.csv"
        self.guide_meta_path = self.base_dir / "guide_meta.json"

        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            self.user_cache_dir = Path(local_appdata) / "ARCHMOBA" / "PTM" / "cache"
        else:
            self.user_cache_dir = Path.home() / ".archmoba" / "PTM" / "cache"
        self.user_state_path = self.user_cache_dir / "user_state.json"
        self.user_state = self._load_user_state()

        self.query = tk.StringVar()
        self.show_all_results = False
        self.tools = []
        self.open_tabs = {}       # key -> metadata/content
        self.tab_widgets = {}
        self.current_key = "home"
        self.current_tool_widget = None
        self.current_tool_module = None
        self._tool_download_events = queue.Queue()
        self._dependency_events = queue.Queue()
        self._failed_download_keys = set()
        self._catalog_events = queue.Queue()
        self._catalog_meta_check_running = False
        self._catalog_meta_check_pending = False
        self._catalog_sync_lock = threading.Lock()
        self._catalog_search_request_id = 0
        self._catalog_search_inflight = 0
        self._search_debounce_job = None
        self._command_cache = {}
        self._self_update_events = queue.Queue()
        self._self_update_check_running = False
        self.pinned = False

        self._apply_responsive_geometry()
        self.overrideredirect(True)
        self.attributes("-topmost", False)
        self.protocol("WM_DELETE_WINDOW", self.hide_main)

        self._build_shell()
        self.reload_tools()
        self.show_home()

        self.floating = FloatingPTM(self)
        self.after(100, self._poll_tool_download_events)
        self.after(100, self._poll_dependency_events)
        self.after(100, self._poll_catalog_events)
        self.after(30000, self._check_self_update_async)
        self.after(500, self._poll_self_update_events)

    # ---------- Actualización en ejecución ----------
    def _check_self_update_async(self):
        if self._self_update_check_running:
            return
        self._self_update_check_running = True

        def worker():
            try:
                updated = check_self_update(restart=False)
                self._self_update_events.put(("done", updated))
            except Exception:
                self._self_update_events.put(("done", False))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_self_update_events(self):
        try:
            while True:
                _kind, updated = self._self_update_events.get_nowait()
                self._self_update_check_running = False
                if updated:
                    current_file = Path(__file__).resolve()
                    release_single_instance_lock()
                    try:
                        if hasattr(self, "floating"):
                            self.floating.destroy()
                    except Exception:
                        pass
                    subprocess.Popen(
                        [sys.executable, str(current_file), *sys.argv[1:]],
                        cwd=str(current_file.parent),
                    )
                    self.destroy()
                    return

                # Si no hubo actualización, programar la próxima comprobación.
                try:
                    self.after(60000, self._check_self_update_async)
                except tk.TclError:
                    return
        except queue.Empty:
            pass

        try:
            self.after(500, self._poll_self_update_events)
        except tk.TclError:
            return

    # ---------- Ventana / proporción ----------
    def _apply_responsive_geometry(self):
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        # El boceto ocupa aprox. 75-80% del ancho y 68-72% del alto.
        width = min(860, max(700, int(sw * 0.58)))
        height = min(760, max(520, int(sh * 0.70)))
        # Nunca exceder la pantalla útil visualmente.
        width = min(width, sw - 80)
        height = min(height, sh - 100)
        x = max(20, (sw - width) // 2)
        y = max(20, (sh - height) // 2 - 10)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(min(820, width), min(520, height))

    def _build_shell(self):
        # Marco exterior simple y limpio.
        self.outer = tk.Frame(self, bg=WHITE, bd=1, relief="solid")
        self.outer.pack(fill="both", expand=True)

        self.top = tk.Frame(self.outer, bg=WHITE, height=42)
        self.top.pack(fill="x", padx=8, pady=(7, 0))
        self.top.pack_propagate(False)

        self.tabs_holder = tk.Frame(self.top, bg=WHITE)
        self.tabs_holder.pack(side="left", fill="both", expand=True)

        self.close_canvas = tk.Canvas(
            self.top, width=30, height=30, bg=WHITE,
            highlightthickness=0, bd=0, cursor="hand2"
        )
        self.close_canvas.pack(side="right", padx=(4, 4), pady=(2, 0))
        self.close_canvas.create_line(8, 8, 22, 22, fill=BLACK, width=2)
        self.close_canvas.create_line(22, 8, 8, 22, fill=BLACK, width=2)
        self.close_canvas.bind("<Button-1>", lambda _e: self.hide_main())

        self.pin_canvas = tk.Canvas(
            self.top, width=30, height=30, bg=WHITE,
            highlightthickness=0, bd=0, cursor="hand2"
        )
        self.pin_canvas.pack(side="right", padx=(2, 0), pady=(2, 0))
        self.pin_canvas.bind("<Button-1>", self.toggle_pin)
        self._draw_pin_button()

        self.separator = tk.Frame(self.outer, bg=WHITE, height=2)
        self.separator.pack(fill="x")

        self.content = tk.Frame(self.outer, bg=WHITE)
        self.content.pack(fill="both", expand=True, padx=10, pady=(2, 4))

        self.footer = tk.Frame(self.outer, bg=WHITE, height=34)
        self.footer.pack(fill="x", padx=10, pady=(0, 9))
        self.footer.pack_propagate(False)

        self.version_box = tk.Frame(self.footer, bg=WHITE)
        self.version_box.pack(side="right", padx=(0, 4), pady=(0, 3))

        self.version_label = tk.Label(
            self.version_box,
            text=f"PTM v{APP_VERSION}",
            bg=WHITE,
            fg=MUTED,
            font=("Segoe UI", 8),
            anchor="e",
        )
        self.version_label.pack(anchor="e")

        self.update_date_label = tk.Label(
            self.version_box,
            text=f"Actualizado: {APP_UPDATE_DATE}  {APP_UPDATE_TIME}",
            bg=WHITE,
            fg=MUTED,
            font=("Segoe UI", 7),
            anchor="e",
        )
        self.update_date_label.pack(anchor="e")

        # Permitir mover la ventana arrastrando zonas libres de la franja superior.
        self.top.bind("<Button-1>", self._start_move)
        self.top.bind("<B1-Motion>", self._move_window)
        self.tabs_holder.bind("<Button-1>", self._start_move)
        self.tabs_holder.bind("<B1-Motion>", self._move_window)

    def _start_move(self, event):
        self._move_offset = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def _move_window(self, event):
        x = event.x_root - self._move_offset[0]
        y = event.y_root - self._move_offset[1]
        self.geometry(f"+{x}+{y}")

    # ---------- Pestañas ----------
    def _render_tabs(self):
        for child in self.tabs_holder.winfo_children():
            child.destroy()
        self.tab_widgets.clear()

        available = max(520, self.winfo_width() - 70)

        # La pestaña inicial se ajusta al contenido "PTM" en lugar de ocupar
        # el mismo ancho que las herramientas.
        home_font = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        home_width = max(58, home_font.measure("PTM") + 34)

        tool_count = len(self.open_tabs)
        tools_available = max(90, available - home_width - 6)
        tab_width = (
            max(90, min(130, tools_available // tool_count))
            if tool_count
            else 90
        )

        home_active = self.current_key == "home"
        home = TabButton(
            self.tabs_holder,
            "PTM",
            on_open=self.show_home,
            active=home_active,
            width=home_width,
            height=(30 if home_active else 25),
        )
        home.pack(side="left", padx=(0, 6), anchor="s")
        self.tab_widgets["home"] = home

        processing_states = {"loading", "preparing", "processing"}

        for key in self.open_tabs:
            meta = self.open_tabs[key]
            is_processing = meta.get("state") in processing_states

            tool = meta.get("tool", {})
            tab_active = self.current_key == key
            tab = TabButton(
                self.tabs_holder,
                meta["name"],
                on_open=lambda k=key: self.switch_to_tool(k),
                on_close=lambda k=key: self.close_tool_tab(k),
                active=tab_active,
                width=tab_width,
                height=(30 if tab_active else 25),
                processing=is_processing,
                favorite=self._is_favorite(tool),
                on_favorite=lambda t=tool: self._toggle_favorite(t),
                on_reload=lambda t=tool: self.reload_tool(t),
            )
            tab.pack(side="left", padx=(0, 6), anchor="s")
            self.tab_widgets[key] = tab

    def _clear_content(self):
        if self.current_tool_widget is not None:
            try:
                if hasattr(self.current_tool_widget, "on_hide"):
                    self.current_tool_widget.on_hide()
            except Exception:
                pass
        for child in self.content.winfo_children():
            child.pack_forget()
            child.grid_forget()

    # ---------- Inicio ----------
    def show_home(self):
        self.current_key = "home"
        self.current_tool_widget = None
        self.current_tool_module = None
        self._clear_content()

        if not hasattr(self, "home_frame") or not self.home_frame.winfo_exists():
            self.home_frame = tk.Frame(self.content, bg=WHITE)
            self._build_home(self.home_frame)
        self.home_frame.pack(fill="both", expand=True)
        self._render_tabs()

    def _build_home(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=0)
        parent.grid_rowconfigure(3, weight=1)

        self.center = tk.Frame(parent, bg=WHITE)
        self.center.grid(row=0, column=0, sticky="n", pady=(72, 0))
        self.center.grid_columnconfigure(0, weight=0)
        self.center.grid_columnconfigure(1, weight=0)

        # Logo grande: se usa en el modo normal, antes de pulsar Enter.
        logo_w, logo_h = 230, 104
        self.logo = tk.Canvas(
            self.center, width=logo_w, height=logo_h, bg=WHITE,
            highlightthickness=0, bd=0
        )
        self.logo.create_rectangle(2, 2, logo_w - 2, logo_h - 2, fill=TEAL, outline=BLACK, width=1)
        self.logo.create_polygon(logo_w - 30, 2, logo_w - 2, 2, logo_w - 2, 30, fill=RED, outline=RED)
        self.logo.create_rectangle(2, logo_h - 20, logo_w - 2, logo_h - 2, fill=RED, outline=RED)
        self.logo.create_text(logo_w / 2, 46, text="PTM", fill=ON_ACCENT, font=("Segoe UI", 38, "bold"))
        self.logo.create_text(
            logo_w / 2, logo_h - 10,
            text="Buscador y lanzador de herramientas",
            fill=ON_ACCENT, font=("Segoe UI", 8, "bold")
        )

        # Logo compacto: al pulsar Enter pasa a la izquierda del buscador,
        # exactamente para liberar espacio vertical para los resultados.
        compact_w, compact_h = 110, 50
        self.logo_compact = tk.Canvas(
            self.center, width=compact_w, height=compact_h, bg=WHITE,
            highlightthickness=0, bd=0
        )
        self.logo_compact.create_rectangle(
            2, 2, compact_w - 2, compact_h - 2,
            fill=TEAL, outline=BLACK, width=1
        )
        self.logo_compact.create_polygon(
            compact_w - 17, 2, compact_w - 2, 2,
            compact_w - 2, 17, fill=RED, outline=RED
        )
        self.logo_compact.create_rectangle(
            2, compact_h - 10, compact_w - 2, compact_h - 2,
            fill=RED, outline=RED
        )
        self.logo_compact.create_text(
            compact_w / 2, 22, text="PTM",
            fill=ON_ACCENT, font=("Segoe UI", 19, "bold")
        )
        self.logo_compact.create_text(
            compact_w / 2, compact_h - 6,
            text="Buscador y lanzador de herramientas",
            fill=ON_ACCENT, font=("Segoe UI", 4, "bold")
        )

        self.search_wrap = tk.Frame(self.center, bg=WHITE)

        # Barra de búsqueda con bordes redondeados como en el boceto.
        self.search_box = tk.Canvas(
            self.search_wrap,
            width=500,
            height=46,
            bg=WHITE,
            highlightthickness=0,
            bd=0,
        )
        self.search_box.pack()
        self._rounded_rect(
            self.search_box, 1, 1, 499, 45,
            radius=15,
            fill=WHITE,
            outline=BLACK,
            width=1,
        )

        self.search_inner = tk.Frame(self.search_box, bg=WHITE, bd=0)
        self.search_box.create_window(12, 23, window=self.search_inner, anchor="w", width=476, height=34)

        self.search_prefix = tk.Label(
            self.search_inner,
            text="Buscar |",
            bg=WHITE,
            fg=BLACK,
            font=("Segoe UI", 11),
            cursor="xterm",
        )
        self.search_prefix.pack(side="left", padx=(5, 2))
        self.search_prefix.bind("<Button-1>", lambda _e: self.search_entry.focus_set())

        self.search_entry = tk.Entry(
            self.search_inner,
            textvariable=self.query,
            width=30,
            relief="flat",
            bd=0,
            font=("Segoe UI", 12),
            fg=BLACK,
            bg=WHITE,
            insertbackground=BLACK,
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.search_entry.bind("<KeyRelease>", self._on_search_key_release)
        self.search_entry.bind("<Return>", self._show_all_search_results)

        self.search_btn = tk.Canvas(
            self.search_inner,
            width=32,
            height=32,
            bg=WHITE,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.search_btn.pack(side="left", padx=(2, 2))
        self.search_btn.create_oval(4, 4, 28, 28, fill=RED, outline=BLACK, width=1)
        self.search_btn.bind("<Button-1>", self._show_all_search_results)

        self.import_btn = tk.Canvas(
            self.search_inner,
            width=34,
            height=32,
            bg=WHITE,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.import_btn.pack(side="left", padx=(0, 4))
        self._draw_import_icon(self.import_btn)
        self.import_btn.bind("<Button-1>", lambda _e: self.import_py())

        self.search_box.bind("<Button-1>", lambda _e: self.search_entry.focus_set())

        self.quick_filters = tk.Frame(self.center, bg=WHITE)
        quick_items = (
            ("Recientes", "%recents%"),
            ("Favoritos", "%favorites%"),
            ("Más usados", "%used%"),
            ("Recomendados", "%recommended%"),
        )
        for index, (label_text, command) in enumerate(quick_items):
            link = tk.Label(
                self.quick_filters,
                text=label_text,
                bg=WHITE,
                fg=MUTED,
                font=("Segoe UI", 8, "underline"),
                cursor="hand2",
            )
            link.pack(side="left", padx=(0 if index == 0 else 14, 0))
            link.bind(
                "<Button-1>",
                lambda _e, cmd=command: self._set_search_command(cmd),
            )

        # Contador encima de los resultados, alineado a la derecha.
        self.hint = tk.Label(
            self.center, text="", bg=WHITE, fg=MUTED,
            font=("Segoe UI", 9), anchor="e"
        )
        # Lista desplazable. Sin Enter muestra 5; con Enter muestra hasta
        # 10 filas visibles y permite desplazarse si existen más resultados.
        self.results_container = tk.Frame(self.center, bg=WHITE, width=500)
        self.results_container.pack_propagate(False)

        self.results_canvas = tk.Canvas(
            self.results_container,
            bg=WHITE,
            highlightthickness=0,
            bd=0,
            width=480,
            height=195,
        )
        self.results_canvas.pack(side="left", fill="both", expand=True)

        self.results_scroll = tk.Scrollbar(
            self.results_container,
            orient="vertical",
            command=self.results_canvas.yview,
        )
        self.results_canvas.configure(yscrollcommand=self.results_scroll.set)

        self.results_frame = tk.Frame(self.results_canvas, bg=WHITE)
        self.results_window = self.results_canvas.create_window(
            (0, 0), window=self.results_frame, anchor="nw"
        )

        self.results_frame.bind(
            "<Configure>",
            lambda _e: self.results_canvas.configure(
                scrollregion=self.results_canvas.bbox("all")
            ),
        )
        self.results_canvas.bind(
            "<Configure>",
            lambda e: self.results_canvas.itemconfigure(
                self.results_window, width=e.width
            ),
        )
        self._bind_results_scroll(self.results_canvas)
        self._bind_results_scroll(self.results_frame)
        self._bind_results_scroll(self.results_container)

        self._apply_search_layout(expanded=False)

    def _scroll_results(self, event):
        """Desplaza la lista aunque el cursor esté sobre tarjetas o textos."""
        if not self.show_all_results:
            return "break"

        first, last = self.results_canvas.yview()
        if first <= 0.0 and last >= 1.0:
            return "break"

        if getattr(event, "num", None) == 4:
            direction = -1
        elif getattr(event, "num", None) == 5:
            direction = 1
        else:
            delta = getattr(event, "delta", 0)
            if delta == 0:
                return "break"
            direction = -1 if delta > 0 else 1

        self.results_canvas.yview_scroll(direction * 3, "units")
        return "break"

    def _bind_results_scroll(self, widget):
        """Enlaza rueda/trackpad al scroll de resultados para cualquier widget."""
        widget.bind("<MouseWheel>", self._scroll_results, add="+")
        widget.bind("<Button-4>", self._scroll_results, add="+")
        widget.bind("<Button-5>", self._scroll_results, add="+")

    def _apply_search_layout(self, expanded=False):
        """Cambia la composición del inicio al pulsar Enter."""
        if not hasattr(self, "center"):
            return

        self.logo.grid_forget()
        self.logo_compact.grid_forget()
        self.search_wrap.grid_forget()
        self.quick_filters.grid_forget()
        self.hint.grid_forget()
        self.results_container.grid_forget()

        if expanded:
            # Diseño de resultados: logo pequeño a la izquierda, buscador a la derecha.
            self.center.grid_configure(pady=(14, 0))
            self.logo_compact.grid(
                row=0, column=0, sticky="n",
                padx=(0, 8), pady=(0, 0)
            )
            self.search_wrap.grid(
                row=0, column=1, sticky="n",
                pady=(0, 0)
            )
            self.quick_filters.grid(
                row=1, column=1, sticky="w",
                pady=(4, 0)
            )
            self.hint.grid(
                row=2, column=1, sticky="ew",
                pady=(3, 3)
            )
            self.results_container.grid(
                row=3, column=1, sticky="ew"
            )
        else:
            # Diseño inicial: logo centrado encima del buscador.
            self.center.grid_configure(pady=(72, 0))
            self.logo.grid(
                row=0, column=0, columnspan=2,
                sticky="n", pady=(0, 0)
            )
            self.search_wrap.grid(
                row=1, column=0, columnspan=2,
                sticky="n", pady=(16, 0)
            )
            self.quick_filters.grid(
                row=2, column=0, columnspan=2,
                sticky="w", pady=(4, 0)
            )
            self.hint.grid(
                row=3, column=0, columnspan=2,
                sticky="ew", pady=(6, 4)
            )
            self.results_container.grid(
                row=4, column=0, columnspan=2,
                sticky="ew"
            )

    @staticmethod
    def _rounded_rect(canvas, x1, y1, x2, y2, radius=14, **kwargs):
        r = radius
        points = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1,
        ]
        return canvas.create_polygon(
            points,
            smooth=True,
            splinesteps=36,
            **kwargs,
        )

    @staticmethod
    def _draw_import_icon(canvas):
        canvas.create_line(15, 4, 15, 18, fill=BLACK, width=2)
        canvas.create_line(10, 9, 15, 4, 20, 9, fill=BLACK, width=2)
        canvas.create_line(7, 16, 7, 23, 24, 23, 24, 16, fill=BLACK, width=2)

    # ---------- Estado local del usuario ----------
    def _load_user_state(self):
        default = {"recents": [], "favorites": [], "usage": {}}
        try:
            if self.user_state_path.is_file():
                data = json.loads(
                    self.user_state_path.read_text(encoding="utf-8-sig")
                )
                if isinstance(data, dict):
                    recents = data.get("recents", [])
                    favorites = data.get("favorites", [])
                    usage = data.get("usage", {})
                    return {
                        "recents": list(recents) if isinstance(recents, list) else [],
                        "favorites": list(favorites) if isinstance(favorites, list) else [],
                        "usage": dict(usage) if isinstance(usage, dict) else {},
                    }
        except Exception:
            pass
        return default

    def _save_user_state(self):
        try:
            self.user_cache_dir.mkdir(parents=True, exist_ok=True)
            temp = self.user_state_path.with_suffix(".tmp")
            temp.write_text(
                json.dumps(self.user_state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temp.replace(self.user_state_path)
            return True
        except OSError:
            return False

    @staticmethod
    def _tool_state_key(tool):
        return (
            str(tool.get("slug", "")).strip()
            or str(tool.get("id", "")).strip()
            or str(tool.get("repo_path", "")).strip()
            or str(tool.get("path", "")).strip()
        )

    def _is_favorite(self, tool):
        key = self._tool_state_key(tool)
        return bool(key and key in self.user_state.get("favorites", []))

    def _toggle_favorite(self, tool):
        key = self._tool_state_key(tool)
        if not key:
            return
        favorites = self.user_state.setdefault("favorites", [])
        if key in favorites:
            favorites.remove(key)
        else:
            favorites.append(key)
        self._save_user_state()
        self._rebuild_command_cache()
        if hasattr(self, "results_frame") and self.results_frame.winfo_exists():
            self.refresh_results()
        self._render_tabs()

    def _record_tool_open(self, tool):
        key = self._tool_state_key(tool)
        if not key:
            return
        recents = self.user_state.setdefault("recents", [])
        if key in recents:
            recents.remove(key)
        recents.insert(0, key)
        del recents[10:]

        usage = self.user_state.setdefault("usage", {})
        try:
            usage[key] = int(usage.get(key, 0)) + 1
        except (TypeError, ValueError):
            usage[key] = 1
        self._save_user_state()
        self._rebuild_command_cache()

    def _tool_by_state_key(self):
        return {
            self._tool_state_key(tool): tool
            for tool in self.tools
            if self._tool_state_key(tool)
        }

    def _rebuild_command_cache(self):
        """Precalcula los filtros especiales para evitar ordenar en cada búsqueda."""
        by_key = self._tool_by_state_key()
        usage = self.user_state.get("usage", {})

        self._command_cache = {
            "%recents%": [
                by_key[key]
                for key in self.user_state.get("recents", [])
                if key in by_key
            ][:10],
            "%favorites%": [
                by_key[key]
                for key in self.user_state.get("favorites", [])
                if key in by_key
            ],
            "%used%": sorted(
                [
                    tool for key, tool in by_key.items()
                    if int(usage.get(key, 0) or 0) > 0
                ],
                key=lambda tool: (
                    -int(usage.get(self._tool_state_key(tool), 0) or 0),
                    tool["name"].lower(),
                ),
            )[:10],
            "%recommended%": sorted(
                self.tools,
                key=lambda tool: (
                    -int(tool.get("visits", 0)),
                    tool["name"].lower(),
                ),
            )[:20],
        }

    def _set_search_command(self, command):
        self.query.set(command)
        self._show_all_search_results()

    def _show_tool_context_menu(self, event, tool):
        key = self._tool_tab_key(tool)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(
            label="Abrir en nueva pestaña",
            command=lambda t=tool: self.open_tool(t, background=True),
        )
        menu.add_separator()
        menu.add_command(
            label=("Quitar de favoritos" if self._is_favorite(tool)
                   else "Añadir a favoritos"),
            command=lambda t=tool: self._toggle_favorite(t),
        )
        menu.add_command(
            label="Recargar",
            command=lambda t=tool: self.reload_tool(t),
        )
        menu.add_command(
            label="Cerrar",
            command=lambda k=key: self.close_tool_tab(k),
            state=("normal" if key in self.open_tabs else "disabled"),
        )
        menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def _open_tool_from_result(self, event, tool):
        """Ctrl+clic abre/carga en segundo plano sin abandonar el buscador."""
        ctrl_pressed = bool(int(getattr(event, "state", 0)) & 0x0004)
        self.open_tool(tool, background=ctrl_pressed)
        return "break"

    def reload_tool(self, tool):
        key = self._tool_tab_key(tool)
        if key in self.open_tabs:
            self.close_tool_tab(key)

        state_key = self._tool_state_key(tool)
        current = next(
            (item for item in self.tools
             if self._tool_state_key(item) == state_key),
            None,
        )
        if current is not None:
            self.open_tool(current, record_usage=False)

    # ---------- Búsqueda ----------
    @staticmethod
    def _normalize_search_text(value):
        """Normaliza texto para buscar sin distinguir tildes, mayúsculas o símbolos."""
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = text.lower()
        text = re.sub(r"[^a-z0-9]+", " ", text)
        return " ".join(text.split())

    @staticmethod
    def _field_token_score(token, field_text, weight):
        """Devuelve puntaje por coincidencia exacta/prefijo/subcadena en un campo."""
        if not token or not field_text:
            return 0

        words = field_text.split()
        if token in words:
            return weight

        if any(word.startswith(token) for word in words):
            return max(1, int(weight * 0.90))

        if token in field_text:
            return max(1, int(weight * 0.70))

        return 0

    def _score_tool_for_query(self, tool, normalized_query, tokens):
        """Calcula relevancia; todos los tokens deben encontrar alguna coincidencia."""
        title = tool.get("search_title", "")
        slug = tool.get("search_slug", "")
        keywords = tool.get("search_keywords", "")
        category = tool.get("search_category", "")
        description = tool.get("search_description", "")
        path = tool.get("search_path", "")
        author = tool.get("search_author", "")
        dependencies = tool.get("search_dependencies", "")

        score = 0

        if normalized_query == title:
            score += 100
        elif title.startswith(normalized_query):
            score += 70

        if normalized_query == slug:
            score += 80
        elif slug.startswith(normalized_query):
            score += 55

        fields = (
            (title, 50),
            (slug, 40),
            (keywords, 30),
            (category, 20),
            (path, 15),
            (description, 10),
            (author, 8),
            (dependencies, 6),
        )

        for token in tokens:
            best = 0
            for field_text, weight in fields:
                best = max(
                    best,
                    self._field_token_score(token, field_text, weight),
                )
            if best == 0:
                return None
            score += best

        return score

    # ---------- Herramientas ----------
    def reload_tools(self, local_only=False, refresh=True):
        """Carga exclusivamente el catálogo guide.csv."""
        self.tools = []
        try:
            rows = self._load_guide_rows(local_only=local_only)
        except Exception as exc:
            rows = []
            if hasattr(self, "hint"):
                self.hint.configure(text=f"No se pudo cargar guide.csv: {exc}")

        for row in rows:
            activo = str(row.get("activo", "1")).strip().lower()
            if activo not in {"1", "true", "si", "sí", "yes", "activo"}:
                continue

            repo_path = str(row.get("ruta", "")).strip().replace("\\", "/").lstrip("/")
            if not repo_path:
                continue

            local_path = self.base_dir / Path(repo_path)
            name = str(row.get("titulo", "")).strip() or Path(repo_path).stem.replace("_", " ").title()
            description = str(row.get("descripcion", "")).strip()
            keywords = str(row.get("keywords", "")).strip()
            category = str(row.get("categoria", "")).strip()
            version = str(row.get("version", "")).strip()
            mode = str(row.get("modo", "Integrado")).strip() or "Integrado"
            file_type = str(row.get("tipo_archivo", "py")).strip().lower() or "py"
            dependencies = str(row.get("dependencias", "")).strip()
            author = str(row.get("autor", "")).strip()
            slug = str(row.get("slug", "")).strip()
            try:
                visits = int(str(row.get("visitas", "0")).strip() or "0")
            except ValueError:
                visits = 0

            normalized_title = self._normalize_search_text(name)
            normalized_slug = self._normalize_search_text(slug)
            normalized_keywords = self._normalize_search_text(keywords)
            normalized_category = self._normalize_search_text(category)
            normalized_description = self._normalize_search_text(description)
            normalized_path = self._normalize_search_text(
                f"{Path(repo_path).stem} {repo_path}"
            )
            normalized_author = self._normalize_search_text(author)
            normalized_dependencies = self._normalize_search_text(dependencies)

            self.tools.append({
                "id": str(row.get("id", "")).strip(),
                "slug": slug,
                "path": local_path,
                "repo_path": repo_path,
                "name": name,
                "keywords": keywords,
                "description": description,
                "category": category,
                "version": version,
                "mode": mode,
                "file_type": file_type,
                "dependencies": dependencies,
                "author": author,
                "visits": visits,
                "main_file": str(row.get("archivo_principal", "")).strip(),
                "search_title": normalized_title,
                "search_slug": normalized_slug,
                "search_keywords": normalized_keywords,
                "search_category": normalized_category,
                "search_description": normalized_description,
                "search_path": normalized_path,
                "search_author": normalized_author,
                "search_dependencies": normalized_dependencies,
                "search": " ".join(
                    part for part in (
                        normalized_slug,
                        normalized_path,
                        normalized_title,
                        normalized_description,
                        normalized_keywords,
                        normalized_category,
                        self._normalize_search_text(version),
                        normalized_dependencies,
                        normalized_author,
                    )
                    if part
                ),
            })

        self._rebuild_command_cache()

        if (
            refresh
            and hasattr(self, "results_frame")
            and self.results_frame.winfo_exists()
        ):
            self.refresh_results()

    def _read_local_guide_meta(self):
        try:
            if self.guide_meta_path.is_file():
                return json.loads(
                    self.guide_meta_path.read_text(encoding="utf-8-sig")
                )
        except Exception:
            pass
        return {}

    def _fetch_remote_guide_meta(self):
        """Consulta solo el archivo pequeño guide_meta.json."""
        last_error = None

        try:
            request = urllib.request.Request(
                GUIDE_META_API_URL,
                headers={
                    "User-Agent": f"PTM/{APP_VERSION}",
                    "Accept": "application/vnd.github+json",
                    "Cache-Control": "no-cache",
                },
            )
            with urllib.request.urlopen(request, timeout=6) as response:
                payload = json.loads(response.read().decode("utf-8"))
            encoded = str(payload.get("content", "")).replace("\n", "")
            if encoded:
                return json.loads(
                    base64.b64decode(encoded).decode("utf-8-sig")
                )
        except Exception as exc:
            last_error = exc

        try:
            request = urllib.request.Request(
                f"{GUIDE_META_URL}?v={time.time_ns()}",
                headers={
                    "User-Agent": f"PTM/{APP_VERSION}",
                    "Cache-Control": "no-cache",
                },
            )
            with urllib.request.urlopen(request, timeout=6) as response:
                return json.loads(response.read().decode("utf-8-sig"))
        except Exception as exc:
            last_error = exc

        raise RuntimeError(f"No se pudo consultar guide_meta.json ({last_error})")

    @staticmethod
    def _guide_meta_matches(local_meta, remote_meta):
        if not local_meta or not remote_meta:
            return False
        return (
            str(local_meta.get("updated_at", "")).strip()
            == str(remote_meta.get("updated_at", "")).strip()
            and str(local_meta.get("guide_sha", "")).strip()
            == str(remote_meta.get("guide_sha", "")).strip()
        )

    def _local_guide_git_sha(self):
        """Calcula el SHA Git real del guide.csv local, normalizando saltos."""
        if not self.guide_path.is_file():
            return ""
        try:
            text = self.guide_path.read_text(encoding="utf-8-sig")
            text = text.replace("\r\n", "\n").replace("\r", "\n")
            data = text.encode("utf-8")
            header = f"blob {len(data)}\0".encode("ascii")
            return hashlib.sha1(header + data).hexdigest()
        except Exception:
            return ""

    def _download_guide_text(self):
        """Descarga guide.csv únicamente cuando la metadata indica un cambio."""
        last_error = None

        try:
            request = urllib.request.Request(
                GUIDE_API_URL,
                headers={
                    "User-Agent": f"PTM/{APP_VERSION}",
                    "Accept": "application/vnd.github+json",
                    "Cache-Control": "no-cache",
                },
            )
            with urllib.request.urlopen(request, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
            encoded = str(payload.get("content", "")).replace("\n", "")
            if encoded:
                return base64.b64decode(encoded).decode("utf-8-sig")
        except Exception as exc:
            last_error = exc

        try:
            request = urllib.request.Request(
                f"{GUIDE_URL}?v={time.time_ns()}",
                headers={
                    "User-Agent": f"PTM/{APP_VERSION}",
                    "Cache-Control": "no-cache",
                },
            )
            with urllib.request.urlopen(request, timeout=8) as response:
                return response.read().decode("utf-8-sig")
        except Exception as exc:
            last_error = exc

        raise RuntimeError(f"No se pudo descargar guide.csv ({last_error})")

    def _sync_guide_if_needed(self):
        """Valida metadata Y contenido real antes de dar guide.csv por vigente."""
        remote_meta = self._fetch_remote_guide_meta()
        local_meta = self._read_local_guide_meta()
        remote_sha = str(remote_meta.get("guide_sha", "")).strip()
        local_guide_sha = self._local_guide_git_sha()

        needs_update = (
            not self.guide_path.is_file()
            or not self._guide_meta_matches(local_meta, remote_meta)
            or not remote_sha
            or local_guide_sha != remote_sha
        )

        if not needs_update:
            return False

        text = self._download_guide_text()
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        self.guide_path.write_bytes(normalized.encode("utf-8"))
        self.guide_meta_path.write_text(
            json.dumps(remote_meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # No aceptar una descarga si no coincide con el SHA publicado.
        downloaded_sha = self._local_guide_git_sha()
        if remote_sha and downloaded_sha != remote_sha:
            raise RuntimeError(
                "El guide.csv descargado no coincide con el SHA publicado."
            )

        return True

    def _check_guide_on_search_async(self):
        """Mientras se escribe, comprueba el catálogo sin bloquear la interfaz."""
        if self._catalog_meta_check_running:
            self._catalog_meta_check_pending = True
            return

        self._catalog_meta_check_running = True
        self._catalog_meta_check_pending = False

        def worker():
            try:
                with self._catalog_sync_lock:
                    changed = self._sync_guide_if_needed()
                self._catalog_events.put(("done", changed, None))
            except Exception as exc:
                self._catalog_events.put(("done", False, exc))

        threading.Thread(target=worker, daemon=True).start()

    def _show_catalog_refreshing_state(self):
        """Oculta resultados viejos mientras Enter verifica el catálogo remoto."""
        if not hasattr(self, "results_frame"):
            return
        for child in self.results_frame.winfo_children():
            child.destroy()
        self.results_scroll.pack_forget()
        self.results_container.configure(height=1)
        self.results_canvas.configure(height=1)
        self.hint.configure(text="Actualizando catálogo...")

    def _sync_guide_before_expanded_search_async(self):
        """Enter/botón rojo: verificar remoto y recién después buscar."""
        self._catalog_search_request_id += 1
        request_id = self._catalog_search_request_id
        query_snapshot = self.query.get()
        self._catalog_search_inflight += 1

        self.show_all_results = True
        self._apply_search_layout(expanded=True)
        self._show_catalog_refreshing_state()

        def worker():
            try:
                # El lock evita que una comprobación por tecleo escriba el guide
                # al mismo tiempo. Esta petición SIEMPRE hace su propia consulta
                # remota después de obtener el turno.
                with self._catalog_sync_lock:
                    changed = self._sync_guide_if_needed()
                self._catalog_events.put(
                    ("search_done", changed, None, request_id, query_snapshot)
                )
            except Exception as exc:
                self._catalog_events.put(
                    ("search_done", False, exc, request_id, query_snapshot)
                )

        threading.Thread(target=worker, daemon=True).start()

    def _poll_catalog_events(self):
        try:
            while True:
                event = self._catalog_events.get_nowait()
                kind = event[0]

                if kind == "done":
                    _kind, changed, error = event
                    self._catalog_meta_check_running = False

                    if changed:
                        self.reload_tools(
                            local_only=True,
                            refresh=(self._catalog_search_inflight == 0),
                        )
                    elif error is not None and hasattr(self, "hint"):
                        # Mientras se escribe se conserva la copia local.
                        pass

                    if self._catalog_meta_check_pending:
                        self._catalog_meta_check_pending = False
                        self._check_guide_on_search_async()

                elif kind == "search_done":
                    _kind, changed, error, request_id, query_snapshot = event
                    self._catalog_search_inflight = max(
                        0, self._catalog_search_inflight - 1
                    )

                    # Solo la petición más reciente decide qué se muestra.
                    if request_id != self._catalog_search_request_id:
                        continue

                    if error is not None:
                        self._show_catalog_refreshing_state()
                        self.hint.configure(
                            text=(
                                "No se pudo verificar el catálogo remoto. "
                                "Vuelve a pulsar Enter."
                            )
                        )
                        continue

                    # Siempre reconstruir self.tools desde el guide verificado,
                    # incluso si GitHub reportó "sin cambios". Esto elimina
                    # cualquier registro viejo que haya quedado solo en memoria.
                    self.reload_tools(local_only=True, refresh=False)

                    # Si el texto cambió mientras se consultaba, usar el texto
                    # actual pero siempre contra el catálogo ya verificado.
                    self.show_all_results = True
                    self._apply_search_layout(expanded=True)
                    self.refresh_results()
        except queue.Empty:
            pass

        try:
            self.after(100, self._poll_catalog_events)
        except tk.TclError:
            pass

    def _load_guide_rows(self, local_only=False):
        """Carga la copia local; al iniciar sincroniza metadata si es necesario."""
        if not local_only:
            try:
                self._sync_guide_if_needed()
            except Exception:
                pass

        if not self.guide_path.is_file():
            # Si no existe ninguna copia local, la descarga es obligatoria.
            remote_meta = self._fetch_remote_guide_meta()
            text = self._download_guide_text()
            self.guide_path.write_text(text, encoding="utf-8")
            self.guide_meta_path.write_text(
                json.dumps(remote_meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        text = self.guide_path.read_text(encoding="utf-8-sig")
        reader = csv.DictReader(io.StringIO(text), delimiter=";")
        if not reader.fieldnames or "ruta" not in reader.fieldnames:
            raise ValueError("guide.csv no contiene la columna 'ruta'.")
        return list(reader)

    def _ensure_tool_local(self, tool):
        """Descarga una herramienta remota y devuelve su archivo Python ejecutable."""
        repo_path = str(tool.get("repo_path", "")).strip().replace("\\", "/").lstrip("/")
        if not repo_path:
            raise ValueError("La herramienta no tiene una ruta válida en guide.csv.")

        local_path = self.base_dir / Path(repo_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        remote_url = f"{REPO_RAW_BASE}/{repo_path}?v={time.time_ns()}"
        request = urllib.request.Request(
            remote_url,
            headers={
                "User-Agent": f"PTM/{APP_VERSION}",
                "Cache-Control": "no-cache",
            },
        )

        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()

        file_type = str(tool.get("file_type", "")).strip().lower()
        if not file_type:
            file_type = Path(repo_path).suffix.lower().lstrip(".")

        if file_type == "zip" or Path(repo_path).suffix.lower() == ".zip":
            temp_zip = local_path.with_suffix(local_path.suffix + ".tmp")
            temp_zip.write_bytes(data)
            try:
                # Validar estructura y CRC antes de reemplazar la copia local.
                with zipfile.ZipFile(temp_zip, "r") as zf:
                    bad_file = zf.testzip()
                    if bad_file:
                        raise ValueError(f"El ZIP está dañado: {bad_file}")

                temp_zip.replace(local_path)

                # Cada versión del paquete se extrae en una carpeta inmutable.
                # Esto evita romper una herramienta externa que siga ejecutándose.
                package_hash = hashlib.sha1(data).hexdigest()[:12]
                slug = str(tool.get("slug", "")).strip() or Path(repo_path).stem
                package_root = self.tools_dir / ".packages" / slug / package_hash
                package_root.parent.mkdir(parents=True, exist_ok=True)

                if not package_root.is_dir():
                    temp_extract = package_root.with_name(package_root.name + ".tmp")
                    shutil.rmtree(temp_extract, ignore_errors=True)
                    temp_extract.mkdir(parents=True, exist_ok=True)
                    try:
                        self._safe_extract_zip(local_path, temp_extract)
                        if package_root.exists():
                            shutil.rmtree(package_root, ignore_errors=True)
                        temp_extract.replace(package_root)
                    except Exception:
                        shutil.rmtree(temp_extract, ignore_errors=True)
                        raise

                main_file = str(tool.get("main_file", "")).strip().replace("\\", "/")
                package_root_resolved = package_root.resolve()

                if main_file:
                    main_path = (package_root / main_file).resolve()
                    if (
                        main_path != package_root_resolved
                        and package_root_resolved not in main_path.parents
                    ):
                        raise ValueError(
                            "archivo_principal está fuera del paquete ZIP."
                        )
                else:
                    candidates = sorted(package_root.rglob("*.py"))
                    if not candidates:
                        raise FileNotFoundError(
                            "El ZIP no contiene ningún archivo Python."
                        )

                    main_path = None
                    for preferred in ("app.py", "main.py", "launcher.py"):
                        main_path = next(
                            (
                                path for path in candidates
                                if path.name.lower() == preferred
                            ),
                            None,
                        )
                        if main_path is not None:
                            break
                    main_path = main_path or candidates[0]

                if not main_path.is_file() or main_path.suffix.lower() != ".py":
                    raise FileNotFoundError(
                        f"No se encontró el archivo principal: "
                        f"{main_file or main_path.name}"
                    )

                source = main_path.read_text(encoding="utf-8-sig")
                compile(source, str(main_path), "exec")
                return main_path
            finally:
                try:
                    if temp_zip.exists():
                        temp_zip.unlink()
                except OSError:
                    pass

        # Herramientas Python simples mantienen el comportamiento tradicional.
        source = data.decode("utf-8-sig")
        compile(source, repo_path, "exec")
        temp_path = local_path.with_suffix(local_path.suffix + ".tmp")
        temp_path.write_bytes(data)
        temp_path.replace(local_path)

        return local_path

    def filtered_tools(self):
        raw_query = self.query.get().strip()
        if not raw_query:
            return []

        command = raw_query.lower()
        if command in self._command_cache:
            return list(self._command_cache.get(command, []))

        normalized_query = self._normalize_search_text(raw_query)
        if not normalized_query:
            return []

        tokens = normalized_query.split()
        ranked = []

        for tool in self.tools:
            score = self._score_tool_for_query(
                tool,
                normalized_query,
                tokens,
            )
            if score is None:
                continue
            ranked.append((score, tool))

        # Evita duplicados y conserva la variante de mayor relevancia.
        unique = {}
        for score, tool in ranked:
            key = (
                tool.get("id")
                or tool.get("slug")
                or tool.get("repo_path")
                or str(tool["path"])
            )
            current = unique.get(key)
            candidate = (
                score,
                int(tool.get("visits", 0)),
                tool,
            )
            if current is None or candidate[:2] > current[:2]:
                unique[key] = candidate

        ordered = sorted(
            unique.values(),
            key=lambda item: (
                -item[0],
                -item[1],
                item[2]["name"].lower(),
            ),
        )
        return [item[2] for item in ordered]

    def _schedule_search_catalog_check(self):
        """Debounce: una sola consulta remota 500 ms después de dejar de escribir."""
        if self._search_debounce_job is not None:
            try:
                self.after_cancel(self._search_debounce_job)
            except tk.TclError:
                pass
            self._search_debounce_job = None

        def run_check():
            self._search_debounce_job = None
            self._check_guide_on_search_async()

        self._search_debounce_job = self.after(500, run_check)

    def _on_search_key_release(self, event):
        if getattr(event, "keysym", "") == "Return":
            return

        # La respuesta visual usa únicamente el índice ya cargado en memoria.
        self.show_all_results = False
        self._apply_search_layout(expanded=False)
        self.refresh_results()

        # GitHub se consulta una sola vez cuando el usuario deja de escribir.
        self._schedule_search_catalog_check()

    def _show_all_search_results(self, _event=None):
        # Enter y el botón rojo nunca muestran resultados de una copia vieja:
        # primero verifican guide_meta/guide y luego calculan coincidencias.
        self._sync_guide_before_expanded_search_async()
        return "break"

    def refresh_results(self):
        if not hasattr(self, "results_frame"):
            return

        for child in self.results_frame.winfo_children():
            child.destroy()

        matches = self.filtered_tools()

        if not self.query.get().strip():
            self.results_scroll.pack_forget()
            self.results_container.configure(height=1)
            self.results_canvas.configure(height=1)
            self.hint.configure(text=f"{len(self.tools)} herramienta(s) disponibles")
            return

        if not matches:
            self.results_scroll.pack_forget()
            self.results_container.configure(height=1)
            self.results_canvas.configure(height=1)
            self.hint.configure(text="Sin coincidencias")
            return

        shown = matches if self.show_all_results else matches[:5]

        # En modo Enter cada resultado es más alto porque muestra detalles.
        if self.show_all_results:
            visible_rows = min(len(shown), 6)
            list_height = max(76, visible_rows * 78)
        else:
            visible_rows = min(len(shown), 5)
            list_height = max(38, visible_rows * 39)

        self.results_container.configure(height=list_height)
        self.results_canvas.configure(height=list_height)
        self.results_canvas.yview_moveto(0)

        if self.show_all_results and len(matches) > 6:
            if not self.results_scroll.winfo_manager():
                self.results_scroll.pack(side="right", fill="y")
        else:
            self.results_scroll.pack_forget()

        if self.show_all_results:
            self.hint.configure(text=f"{len(matches)} coincidencia(s)")
        elif len(matches) > 5:
            self.hint.configure(
                text=f"{len(matches)} coincidencia(s) · mostrando 5 · Enter para ver más"
            )
        else:
            self.hint.configure(text=f"{len(matches)} coincidencia(s)")

        for tool in shown:
            row = tk.Frame(
                self.results_frame,
                bg=LIGHT,
                highlightbackground=MID,
                highlightthickness=1,
            )
            row.pack(fill="x", pady=2)

            if self.show_all_results:
                # Resultado detallado después de pulsar Enter.
                left = tk.Frame(row, bg=LIGHT)
                left.pack(side="left", fill="both", expand=True, padx=(9, 8), pady=7)

                label = tk.Label(
                    left,
                    text=tool["name"],
                    bg=LIGHT,
                    fg=BLACK,
                    font=("Segoe UI", 10, "bold"),
                    anchor="w",
                )
                label.pack(fill="x")

                description = tool.get("description", "").strip() or "Sin descripción."
                desc = tk.Label(
                    left,
                    text=description,
                    bg=LIGHT,
                    fg=MUTED,
                    font=("Segoe UI", 8),
                    anchor="w",
                    justify="left",
                    wraplength=300,
                )
                desc.pack(fill="x", pady=(3, 0))

                right = tk.Frame(row, bg=LIGHT)
                right.pack(side="right", padx=(4, 9), pady=7)

                author = tool.get("author", "").strip() or "Sin autor"
                author_label = tk.Label(
                    right,
                    text=author,
                    bg=LIGHT,
                    fg=BLACK,
                    font=("Segoe UI", 8, "bold"),
                    anchor="e",
                    justify="right",
                )
                author_label.pack(anchor="e")

                category = tool.get("category", "").strip() or "Sin categoría"
                version = tool.get("version", "").strip() or "-"
                meta = tk.Label(
                    right,
                    text=f"{category} · v{version} · {int(tool.get('visits', 0))} visitas",
                    bg=LIGHT,
                    fg=MUTED,
                    font=("Segoe UI", 8),
                    anchor="e",
                    justify="right",
                )
                meta.pack(anchor="e", pady=(2, 0))

                mode = tool.get("mode", "").strip() or "Integrado"
                dependencies = tool.get("dependencies", "").strip() or "Sin dependencias"
                extra = tk.Label(
                    right,
                    text=f"{mode} · {dependencies}",
                    bg=LIGHT,
                    fg=MUTED,
                    font=("Segoe UI", 8),
                    anchor="e",
                    justify="right",
                )
                extra.pack(anchor="e", pady=(4, 0))

                clickable = (row, left, right, label, desc, author_label, meta, extra)
            else:
                # Resultado compacto durante la escritura.
                label = tk.Label(
                    row,
                    text=tool["name"],
                    bg=LIGHT,
                    fg=BLACK,
                    font=("Segoe UI", 10, "bold"),
                    anchor="w",
                )
                label.pack(side="left", fill="x", expand=True, padx=8, pady=5)

                meta_parts = [
                    part for part in (tool.get("category", ""), tool.get("version", "")) if part
                ]
                meta_parts.append(f"{int(tool.get('visits', 0))} visitas")
                meta_text = " · ".join(meta_parts) or tool["path"].name
                meta = tk.Label(
                    row,
                    text=meta_text,
                    bg=LIGHT,
                    fg=MUTED,
                    font=("Segoe UI", 8),
                    anchor="e",
                )
                meta.pack(side="right", padx=8)
                clickable = (row, label, meta)

            for widget in clickable:
                widget.bind(
                    "<Double-Button-1>",
                    lambda e, t=tool: self._open_tool_from_result(e, t),
                )
                widget.bind(
                    "<Button-1>",
                    lambda e, t=tool: self._open_tool_from_result(e, t),
                )
                widget.bind(
                    "<Button-3>",
                    lambda e, t=tool: self._show_tool_context_menu(e, t),
                )
                self._bind_results_scroll(widget)

        # El Canvas debe conocer el alto real después de crear todas las filas.
        self.results_frame.update_idletasks()
        bbox = self.results_canvas.bbox("all")
        if bbox:
            self.results_canvas.configure(scrollregion=bbox)

    def open_first_result(self):
        shown = self.filtered_tools()
        if shown:
            self.open_tool(shown[0])
        elif self.query.get().strip():
            messagebox.showinfo("PTM", "No se encontró ninguna herramienta con ese criterio.")

    def import_py(self):
        dialog = tk.Toplevel(self)
        dialog.title("Añadir herramienta")
        dialog.configure(bg=WHITE)
        dialog.geometry("590x620")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        title_var = tk.StringVar()
        keywords_var = tk.StringVar()
        category_var = tk.StringVar()
        author_var = tk.StringVar(value="ARCHMOBA")
        version_var = tk.StringVar(value="1.0.0")
        mode_var = tk.StringVar(value="Integrado")
        file_var = tk.StringVar()
        main_var = tk.StringVar()

        container = tk.Frame(dialog, bg=WHITE)
        container.pack(fill="both", expand=True, padx=26, pady=22)
        container.grid_columnconfigure(1, weight=1)

        tk.Label(
            container, text="Añadir herramienta", bg=WHITE, fg=BLACK,
            font=("Segoe UI", 18, "bold")
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 18))

        def add_label(row, text):
            tk.Label(
                container, text=text, bg=WHITE, fg=BLACK,
                font=("Segoe UI", 10)
            ).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=6)

        def add_entry(row, variable):
            entry = tk.Entry(
                container, textvariable=variable, relief="solid", bd=1,
                font=("Segoe UI", 10), bg=WHITE, fg=BLACK
            )
            entry.grid(row=row, column=1, columnspan=2, sticky="ew", pady=6, ipady=5)
            return entry

        add_label(1, "Título")
        title_entry = add_entry(1, title_var)

        add_label(2, "Descripción")
        description_text = tk.Text(
            container, height=4, relief="solid", bd=1,
            font=("Segoe UI", 10), wrap="word", bg=WHITE, fg=BLACK
        )
        description_text.grid(row=2, column=1, columnspan=2, sticky="ew", pady=6)

        add_label(3, "Keywords")
        add_entry(3, keywords_var)

        add_label(4, "Categoría")
        add_entry(4, category_var)

        add_label(5, "Autor")
        add_entry(5, author_var)

        add_label(6, "Versión")
        add_entry(6, version_var)

        add_label(7, "Modo")
        mode_menu = tk.OptionMenu(container, mode_var, "Integrado")
        mode_menu.configure(
            bg=WHITE, fg=BLACK, activebackground=LIGHT,
            relief="solid", bd=1, highlightthickness=0,
            font=("Segoe UI", 10)
        )
        mode_menu.grid(row=7, column=1, columnspan=2, sticky="ew", pady=6)

        add_label(8, "Archivo")
        file_entry = tk.Entry(
            container, textvariable=file_var, relief="solid", bd=1,
            font=("Segoe UI", 9), bg=LIGHT, fg=BLACK, state="readonly"
        )
        file_entry.grid(row=8, column=1, sticky="ew", pady=6, ipady=5)

        def detect_main_file(path):
            src = Path(path)
            if src.suffix.lower() == ".py":
                main_var.set(src.name)
                if not title_var.get().strip():
                    title_var.set(src.stem.replace("_", " ").title())
                return

            try:
                with zipfile.ZipFile(src, "r") as zf:
                    py_files = [
                        name for name in zf.namelist()
                        if name.lower().endswith(".py")
                        and not name.endswith("/")
                        and "__pycache__" not in name
                    ]
                if not py_files:
                    main_var.set("")
                    return

                preferred_names = ("main.py", "app.py", "launcher.py")
                selected = ""
                for preferred in preferred_names:
                    selected = next(
                        (name for name in py_files if Path(name).name.lower() == preferred),
                        ""
                    )
                    if selected:
                        break
                main_var.set(selected or py_files[0])

                if not title_var.get().strip():
                    title_var.set(src.stem.replace("_", " ").title())
            except (OSError, zipfile.BadZipFile):
                main_var.set("")

        def choose_file():
            filename = filedialog.askopenfilename(
                parent=dialog,
                title="Seleccionar herramienta",
                filetypes=[
                    ("Herramientas PTM", "*.py *.zip"),
                    ("Python", "*.py"),
                    ("ZIP", "*.zip"),
                ],
            )
            if filename:
                file_var.set(filename)
                detect_main_file(filename)

        tk.Button(
            container, text="Seleccionar...",
            command=choose_file, bg=TEAL, fg=ON_ACCENT,
            activebackground=TEAL_DARK, activeforeground=ON_ACCENT,
            relief="flat", padx=12, pady=5, cursor="hand2"
        ).grid(row=8, column=2, padx=(8, 0), pady=6)

        add_label(9, "Archivo principal")
        add_entry(9, main_var)

        tk.Label(
            container,
            text="Admite .py o .zip. En ZIP puedes cambiar el archivo principal detectado.",
            bg=WHITE, fg=MUTED, font=("Segoe UI", 8)
        ).grid(row=10, column=1, columnspan=2, sticky="w", pady=(0, 10))

        buttons = tk.Frame(container, bg=WHITE)
        buttons.grid(row=11, column=0, columnspan=3, sticky="e", pady=(14, 0))

        def cancel():
            dialog.grab_release()
            dialog.destroy()

        def install():
            source_text = file_var.get().strip()
            title = title_var.get().strip()
            description = description_text.get("1.0", "end").strip()
            keywords = keywords_var.get().strip()
            category = category_var.get().strip()
            author = author_var.get().strip()
            version = version_var.get().strip() or "1.0.0"
            mode = mode_var.get().strip() or "Integrado"
            main_file = main_var.get().strip().replace("\\", "/")

            if not source_text:
                messagebox.showwarning("PTM", "Selecciona un archivo .py o .zip.", parent=dialog)
                return

            source = Path(source_text)
            if source.suffix.lower() not in {".py", ".zip"}:
                messagebox.showwarning("PTM", "Solo se permiten archivos .py o .zip.", parent=dialog)
                return

            if not title:
                messagebox.showwarning("PTM", "Escribe un título para la herramienta.", parent=dialog)
                return

            if not main_file:
                messagebox.showwarning("PTM", "Indica el archivo principal .py.", parent=dialog)
                return

            slug = self._tool_slug(title)
            target_dir = self.tools_dir / slug

            if target_dir.exists():
                if not messagebox.askyesno(
                    "Reemplazar herramienta",
                    f"Ya existe una herramienta llamada '{title}'. ¿Deseas reemplazarla?",
                    parent=dialog,
                ):
                    return
                try:
                    shutil.rmtree(target_dir)
                except OSError as exc:
                    messagebox.showerror("PTM", f"No se pudo reemplazar la herramienta:\n{exc}", parent=dialog)
                    return

            try:
                target_dir.mkdir(parents=True, exist_ok=True)

                if source.suffix.lower() == ".py":
                    if Path(main_file).name != source.name:
                        main_file = source.name
                        main_var.set(main_file)
                    shutil.copy2(source, target_dir / source.name)
                else:
                    self._safe_extract_zip(source, target_dir)

                main_path = (target_dir / main_file).resolve()
                root = target_dir.resolve()
                if root != main_path.parent and root not in main_path.parents:
                    raise ValueError("El archivo principal está fuera de la carpeta de la herramienta.")
                if not main_path.is_file() or main_path.suffix.lower() != ".py":
                    raise FileNotFoundError(f"No se encontró el archivo principal: {main_file}")

                manifest = {
                    "title": title,
                    "description": description,
                    "keywords": keywords,
                    "category": category,
                    "author": author,
                    "version": version,
                    "mode": mode,
                    "main_file": main_file,
                    "source_type": source.suffix.lower().lstrip("."),
                }
                (target_dir / "manifest.json").write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

            except Exception as exc:
                shutil.rmtree(target_dir, ignore_errors=True)
                messagebox.showerror("PTM", f"No se pudo añadir la herramienta:\n\n{exc}", parent=dialog)
                return

            self.reload_tools()
            self.hint.configure(text=f"Herramienta añadida: {title}")
            cancel()
            messagebox.showinfo("PTM", f"'{title}' se añadió correctamente.")

        tk.Button(
            buttons, text="Cancelar", command=cancel,
            bg=LIGHT, fg=BLACK, relief="flat",
            padx=18, pady=7, cursor="hand2"
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            buttons, text="Añadir", command=install,
            bg=TEAL, fg=ON_ACCENT,
            activebackground=TEAL_DARK, activeforeground=ON_ACCENT,
            relief="flat", padx=22, pady=7, cursor="hand2"
        ).pack(side="left")

        dialog.protocol("WM_DELETE_WINDOW", cancel)
        title_entry.focus_set()

    @staticmethod
    def _tool_slug(text):
        value = re.sub(r"[^A-Za-z0-9_-]+", "_", text.strip()).strip("_").lower()
        return value or "herramienta"

    @staticmethod
    def _safe_extract_zip(source, target_dir):
        root = target_dir.resolve()
        with zipfile.ZipFile(source, "r") as zf:
            for member in zf.infolist():
                member_path = (target_dir / member.filename).resolve()
                if root != member_path and root not in member_path.parents:
                    raise ValueError("El ZIP contiene una ruta no permitida.")
            zf.extractall(target_dir)

    @staticmethod
    def _normalize_distribution_name(value):
        value = str(value or "").strip()
        if not value:
            return ""
        value = re.split(r"[<>=!~\[]", value, maxsplit=1)[0].strip()
        return value

    @staticmethod
    def _import_to_package(module_name):
        """Mapea nombres de importación comunes a sus paquetes de pip."""
        mapping = {
            "PIL": "Pillow",
            "cv2": "opencv-python",
            "sklearn": "scikit-learn",
            "yaml": "PyYAML",
            "bs4": "beautifulsoup4",
            "docx": "python-docx",
            "pptx": "python-pptx",
            "fitz": "PyMuPDF",
            "win32api": "pywin32",
            "win32com": "pywin32",
            "pythoncom": "pywin32",
            "serial": "pyserial",
            "dateutil": "python-dateutil",
            "dotenv": "python-dotenv",
            "Crypto": "pycryptodome",
        }
        return mapping.get(module_name, module_name)

    def _compatible_install_package(self, package_spec):
        """Devuelve el paquete pip más compatible con la versión actual de Python."""
        raw = str(package_spec or "").strip()
        name = self._normalize_distribution_name(raw)
        lower = name.lower()

        # pygame clásico actualmente no ofrece wheel para Python 3.14+.
        # pygame-ce expone el mismo módulo: import pygame.
        if lower == "pygame" and sys.version_info >= (3, 14):
            return "pygame-ce"

        return raw

    def _dependency_satisfied(self, package_spec):
        """Comprueba una dependencia considerando aliases de distribución/import."""
        raw = str(package_spec or "").strip()
        name = self._normalize_distribution_name(raw)
        lower = name.lower()

        if not name:
            return True

        if lower == "pygame":
            # Tanto pygame como pygame-ce proporcionan el módulo pygame.
            if self._module_available("pygame"):
                return True
            if self._distribution_installed("pygame"):
                return True
            if self._distribution_installed("pygame-ce"):
                return True
            return False

        return self._distribution_installed(raw)

    def _is_local_module(self, module_name, tool_path):
        base = tool_path.parent
        return (
            (base / f"{module_name}.py").is_file()
            or (base / module_name / "__init__.py").is_file()
            or (base / module_name).is_dir()
        )

    def _extract_imports(self, tool_path):
        """Obtiene imports de primer nivel sin ejecutar el archivo."""
        try:
            source = tool_path.read_text(encoding="utf-8-sig")
            tree = ast.parse(source, filename=str(tool_path))
        except Exception:
            return set()

        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name:
                        found.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                if node.module:
                    found.add(node.module.split(".")[0])
        return found

    def _distribution_installed(self, package_spec):
        name = self._normalize_distribution_name(package_spec)
        if not name:
            return True
        try:
            importlib.metadata.distribution(name)
            return True
        except importlib.metadata.PackageNotFoundError:
            return False
        except Exception:
            return False

    def _module_available(self, module_name):
        try:
            return importlib.util.find_spec(module_name) is not None
        except Exception:
            return False

    def _collect_missing_dependencies(self, tool):
        path = Path(tool["path"])
        declared = str(tool.get("dependencies", "") or "").strip()

        packages = []
        seen = set()

        # 1) Dependencias declaradas en guide.csv.
        if declared:
            for spec in re.split(r"[;,\n]+", declared):
                spec = spec.strip()
                if not spec:
                    continue
                key = spec.lower()
                if key not in seen and not self._dependency_satisfied(spec):
                    packages.append(spec)
                    seen.add(key)

        # 2) Dependencias inferidas directamente de import / from.
        stdlib = set(getattr(sys, "stdlib_module_names", ()))
        stdlib.update({
            "tkinter", "pathlib", "os", "sys", "re", "json", "csv", "io",
            "time", "subprocess", "shutil", "zipfile", "ast", "threading",
            "queue", "math", "datetime", "collections", "functools",
            "itertools", "typing", "urllib", "http", "email", "sqlite3",
            "logging", "tempfile", "glob", "random", "statistics",
        })

        for module_name in sorted(self._extract_imports(path)):
            if module_name in stdlib:
                continue
            if self._is_local_module(module_name, path):
                continue
            if self._module_available(module_name):
                continue

            package = self._import_to_package(module_name)
            key = package.lower()
            if key not in seen:
                packages.append(package)
                seen.add(key)

        return packages

    def _install_dependencies(self, tool, key):
        """Prepara dependencias sin abrir ventanas; todo se muestra en la pestaña."""
        meta = self.open_tabs.get(key)
        if not meta:
            return

        try:
            missing = self._collect_missing_dependencies(tool)
        except Exception as exc:
            self._dependency_events.put(("failed", key, tool, None, exc))
            return

        if not missing:
            self._dependency_events.put(("success", key, tool, None, None))
            return

        meta["state"] = "preparing"
        meta["failure_stage"] = "dependencies"

        def worker():
            try:
                for package in missing:
                    install_package = self._compatible_install_package(package)

                    if install_package != package:
                        status_text = (
                            f"Instalando {install_package}... "
                            f"(compatible con Python "
                            f"{sys.version_info.major}.{sys.version_info.minor})"
                        )
                    else:
                        status_text = f"Instalando {install_package}..."

                    self._dependency_events.put(
                        ("status", key, tool, status_text, None)
                    )

                    cmd = [
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        "--disable-pip-version-check",
                        "--prefer-binary",
                        install_package,
                    ]
                    process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                        universal_newlines=True,
                        creationflags=(
                            subprocess.CREATE_NO_WINDOW
                            if os.name == "nt"
                            else 0
                        ),
                    )

                    started_at = time.monotonic()
                    output_tail = []
                    pip_lines = queue.Queue()
                    reader_finished = threading.Event()

                    def read_pip_output():
                        try:
                            if process.stdout:
                                # iter/readline puede esperar por un salto de línea,
                                # pero solo bloquea este lector secundario.
                                for raw_line in iter(process.stdout.readline, ""):
                                    if raw_line:
                                        pip_lines.put(raw_line)
                        finally:
                            reader_finished.set()

                    threading.Thread(
                        target=read_pip_output,
                        daemon=True,
                    ).start()

                    last_detail = "Esperando respuesta de pip..."
                    last_heartbeat = -1

                    while process.poll() is None:
                        while True:
                            try:
                                raw_line = pip_lines.get_nowait()
                            except queue.Empty:
                                break

                            clean = raw_line.strip()
                            if not clean:
                                continue

                            output_tail.append(clean)
                            if len(output_tail) > 40:
                                output_tail = output_tail[-40:]

                            last_detail = clean
                            if len(last_detail) > 105:
                                last_detail = last_detail[:102] + "..."

                        elapsed = int(time.monotonic() - started_at)
                        if elapsed != last_heartbeat:
                            last_heartbeat = elapsed
                            self._dependency_events.put(
                                (
                                    "status",
                                    key,
                                    tool,
                                    f"Instalando {install_package}... "
                                    f"{elapsed}s\n{last_detail}",
                                    None,
                                )
                            )

                        if elapsed > 900:
                            process.kill()
                            try:
                                process.wait(timeout=5)
                            except Exception:
                                pass
                            raise TimeoutError(
                                f"La instalación de {install_package} superó "
                                "los 15 minutos."
                            )

                        time.sleep(0.20)

                    # Vacía cualquier salida que haya llegado justo al finalizar.
                    reader_finished.wait(timeout=2)
                    while True:
                        try:
                            raw_line = pip_lines.get_nowait()
                        except queue.Empty:
                            break
                        clean = raw_line.strip()
                        if clean:
                            output_tail.append(clean)
                    output_tail = output_tail[-40:]

                    if process.returncode != 0:
                        detail = "\n".join(output_tail).strip()
                        if len(detail) > 1800:
                            detail = detail[-1800:]

                        python_label = (
                            f"{sys.version_info.major}."
                            f"{sys.version_info.minor}."
                            f"{sys.version_info.micro}"
                        )
                        raise RuntimeError(
                            f"No se pudo instalar {install_package} "
                            f"para Python {python_label}.\n\n"
                            f"{detail or 'pip devolvió un error.'}"
                        )

                importlib.invalidate_caches()

                still_missing = []
                for package in missing:
                    normalized = self._normalize_distribution_name(package)
                    lower = normalized.lower()

                    if lower == "pygame":
                        if not self._module_available("pygame"):
                            still_missing.append(package)
                        continue

                    candidates = [
                        name for name, value in {
                            "PIL": "Pillow",
                            "cv2": "opencv-python",
                            "sklearn": "scikit-learn",
                            "yaml": "PyYAML",
                            "bs4": "beautifulsoup4",
                            "docx": "python-docx",
                            "pptx": "python-pptx",
                            "fitz": "PyMuPDF",
                            "serial": "pyserial",
                            "dateutil": "python-dateutil",
                            "dotenv": "python-dotenv",
                            "Crypto": "pycryptodome",
                        }.items()
                        if value.lower() == lower
                    ]

                    if candidates:
                        if not any(self._module_available(name) for name in candidates):
                            still_missing.append(package)
                    elif (
                        not self._dependency_satisfied(package)
                        and not self._module_available(
                            normalized.replace("-", "_")
                        )
                    ):
                        still_missing.append(package)

                if still_missing:
                    raise RuntimeError(
                        "Las siguientes dependencias siguen sin estar disponibles: "
                        + ", ".join(still_missing)
                    )

                self._dependency_events.put(
                    ("success", key, tool, None, None)
                )

            except Exception as exc:
                self._dependency_events.put(
                    ("failed", key, tool, None, exc)
                )

        threading.Thread(target=worker, daemon=True).start()

    def _poll_dependency_events(self):
        """Actualiza la instalación de dependencias dentro de la pestaña."""
        try:
            while True:
                kind, key, tool, status_text, exc = (
                    self._dependency_events.get_nowait()
                )

                meta = self.open_tabs.get(key)
                if not meta:
                    continue

                if kind == "status":
                    meta["state"] = "preparing"
                    status_widget = meta.get("loading_status")
                    if (
                        status_widget is not None
                        and status_widget.winfo_exists()
                    ):
                        status_widget.configure(text=status_text)
                    continue

                if kind == "success":
                    meta["failure_stage"] = None
                    self._load_tool_into_tab(tool, key)
                    continue

                if kind == "failed":
                    meta["failure_stage"] = "dependencies"
                    meta["last_download_error"] = exc
                    self._show_tool_unavailable(tool, key, exc)
                    continue

        except queue.Empty:
            pass

        try:
            self.after(100, self._poll_dependency_events)
        except tk.TclError:
            pass

    def _tool_tab_key(self, tool):
        repo_path = str(tool.get("repo_path", "")).strip()
        if repo_path:
            return f"remote:{repo_path.lower()}"
        return str(Path(tool["path"]).resolve())

    def _clear_tool_frame(self, frame):
        for child in frame.winfo_children():
            child.destroy()

    def _show_tool_loading(self, tool, key, text="Descargando herramienta..."):
        meta = self.open_tabs.get(key)
        if not meta:
            return

        frame = meta["frame"]
        self._clear_tool_frame(frame)

        holder = tk.Frame(frame, bg=WHITE)
        holder.pack(expand=True)

        spinner = tk.Canvas(
            holder,
            width=48,
            height=48,
            bg=WHITE,
            highlightthickness=0,
            bd=0,
        )
        spinner.pack(pady=(0, 12))
        arc = spinner.create_arc(
            7, 7, 41, 41,
            start=0,
            extent=265,
            style="arc",
            outline=TEAL,
            width=4,
        )

        tk.Label(
            holder,
            text=tool.get("name", "Herramienta"),
            bg=WHITE,
            fg=BLACK,
            font=("Segoe UI", 15, "bold"),
        ).pack()

        status = tk.Label(
            holder,
            text=text,
            bg=WHITE,
            fg=MUTED,
            font=("Segoe UI", 9),
        )
        status.pack(pady=(6, 0))
        meta["loading_status"] = status

        def animate(angle=0):
            if not spinner.winfo_exists():
                return
            current = self.open_tabs.get(key)
            if not current or current.get("state") not in {"loading", "preparing"}:
                return
            try:
                spinner.itemconfigure(arc, start=angle)
                spinner.after(45, lambda: animate((angle - 18) % 360))
            except tk.TclError:
                return

        animate()
        self._activate_tool_if_foreground(key)

    def _show_tool_unavailable(self, tool, key, exc=None):
        meta = self.open_tabs.get(key)
        if not meta:
            return

        meta["state"] = "failed"
        meta["download_worker_running"] = False
        meta["download_finished"] = True
        meta["loading_status"] = None
        frame = meta["frame"]
        self._clear_tool_frame(frame)

        holder = tk.Frame(frame, bg=WHITE)
        holder.pack(expand=True)

        icon = tk.Canvas(
            holder,
            width=54,
            height=54,
            bg=WHITE,
            highlightthickness=0,
            bd=0,
        )
        icon.pack(pady=(0, 10))
        icon.create_oval(7, 7, 47, 47, outline=RED, width=3)
        icon.create_line(19, 19, 35, 35, fill=RED, width=3)
        icon.create_line(35, 19, 19, 35, fill=RED, width=3)

        tk.Label(
            holder,
            text=tool.get("name", "Herramienta"),
            bg=WHITE,
            fg=BLACK,
            font=("Segoe UI", 15, "bold"),
        ).pack()

        is_404 = isinstance(exc, urllib.error.HTTPError) and getattr(exc, "code", None) == 404
        failure_stage = meta.get("failure_stage")
        if failure_stage == "dependencies":
            title = "No se pudieron preparar las dependencias"
        else:
            title = "No está disponible" if is_404 else "No se pudo descargar"

        tk.Label(
            holder,
            text=title,
            bg=WHITE,
            fg=RED if is_404 else BLACK,
            font=("Segoe UI", 11, "bold"),
        ).pack(pady=(5, 2))

        detail = ""
        if exc is not None and not is_404:
            detail = str(exc).strip()
        if detail:
            if len(detail) > 260:
                detail = detail[:257] + "..."
            tk.Label(
                holder,
                text=detail,
                bg=WHITE,
                fg=MUTED,
                font=("Segoe UI", 8),
                wraplength=430,
                justify="center",
            ).pack(pady=(2, 8))
        else:
            tk.Label(
                holder,
                text="El archivo no se encuentra disponible en este momento.",
                bg=WHITE,
                fg=MUTED,
                font=("Segoe UI", 8),
            ).pack(pady=(2, 8))

        buttons = tk.Frame(holder, bg=WHITE)
        buttons.pack(pady=(8, 0))

        retry_btn = tk.Button(
            buttons,
            text="Reintentar",
            bg=TEAL,
            fg=ON_ACCENT,
            activebackground=TEAL_DARK,
            activeforeground=ON_ACCENT,
            relief="flat",
            padx=18,
            pady=7,
            cursor="hand2",
            takefocus=False,
        )
        retry_btn.pack(side="left", padx=(0, 8))
        retry_btn.bind(
            "<ButtonRelease-1>",
            lambda event: self._retry_tool_download(event, tool, key),
        )

        close_btn = tk.Button(
            buttons,
            text="Cerrar",
            bg=LIGHT,
            fg=BLACK,
            relief="flat",
            padx=18,
            pady=7,
            cursor="hand2",
            takefocus=False,
        )
        close_btn.pack(side="left")
        close_btn.bind(
            "<ButtonRelease-1>",
            lambda event: self._close_failed_tool_from_click(event, key),
        )

        self._activate_tool_if_foreground(key)

    def _retry_tool_download(self, event, tool, key):
        """Solo un clic físico izquierdo puede iniciar un nuevo ciclo."""
        if event is None or getattr(event, "num", None) != 1:
            return "break"

        meta = self.open_tabs.get(key)
        if not meta:
            return "break"

        if meta.get("state") != "failed":
            return "break"

        if not meta.get("download_finished"):
            return "break"

        self._failed_download_keys.discard(key)
        meta["manual_retry_authorized"] = True
        self._begin_tool_download_session(
            tool,
            key,
            origin="manual_click",
        )
        return "break"

    def _close_failed_tool_from_click(self, event, key):
        if event is not None and getattr(event, "num", None) == 1:
            self.close_tool_tab(key)
        return "break"

    def _start_tool_download(self, tool, key):
        """Primer ciclo de descarga de la pestaña."""
        meta = self.open_tabs.get(key)
        if not meta:
            return

        if meta.get("download_worker_running"):
            return

        if key in self._failed_download_keys:
            self._show_tool_unavailable(
                tool,
                key,
                meta.get("last_download_error"),
            )
            return

        self._begin_tool_download_session(
            tool,
            key,
            origin="initial",
        )

    def _begin_tool_download_session(self, tool, key, origin="initial"):
        """Crea una sesión; tras failed solo acepta un clic manual autorizado."""
        meta = self.open_tabs.get(key)
        if not meta:
            return

        if meta.get("download_worker_running"):
            return

        if meta.get("state") == "failed" or key in self._failed_download_keys:
            if origin != "manual_click" or not meta.get("manual_retry_authorized"):
                return

        if origin == "manual_click":
            meta["manual_retry_authorized"] = False

        session_id = int(meta.get("download_session_id", 0)) + 1
        meta["download_session_id"] = session_id
        meta["download_worker_running"] = True
        meta["download_finished"] = False
        meta["download_attempt"] = 0
        meta["state"] = "loading"
        meta["last_download_error"] = None

        self._show_tool_loading(
            tool,
            key,
            f"PTM v{APP_VERSION} · Descargando... intento 1/5 · sesión única",
        )

        def worker():
            last_error = None

            for attempt in range(1, 6):
                self._tool_download_events.put(
                    ("progress", key, session_id, attempt, tool, None, None)
                )

                try:
                    local_path = self._ensure_tool_local(tool)
                    self._tool_download_events.put(
                        ("success", key, session_id, attempt, tool, local_path, None)
                    )
                    return
                except Exception as exc:
                    last_error = exc

                if attempt < 5:
                    time.sleep(2)

            # Este es el único punto que emite el fallo final.
            self._tool_download_events.put(
                ("failed", key, session_id, 5, tool, None, last_error)
            )

        threading.Thread(target=worker, daemon=True).start()

    def _poll_tool_download_events(self):
        """Actualiza la interfaz sin crear ni reiniciar ciclos automáticamente."""
        try:
            while True:
                kind, key, session_id, attempt, tool, local_path, exc = (
                    self._tool_download_events.get_nowait()
                )

                meta = self.open_tabs.get(key)
                if not meta:
                    continue

                # Ignorar cualquier mensaje de una sesión anterior.
                if int(meta.get("download_session_id", 0)) != int(session_id):
                    continue

                if kind == "progress":
                    if meta.get("state") != "loading":
                        continue
                    meta["download_attempt"] = int(attempt)
                    status_widget = meta.get("loading_status")
                    if status_widget is not None and status_widget.winfo_exists():
                        status_widget.configure(
                            text=f"PTM v{APP_VERSION} · Descargando... intento {attempt}/5"
                        )
                    continue

                if kind == "success":
                    meta["download_worker_running"] = False
                    meta["download_finished"] = True
                    meta["download_attempt"] = int(attempt)
                    self._tool_download_ready(tool, key, local_path)
                    continue

                if kind == "failed":
                    meta["download_worker_running"] = False
                    meta["download_finished"] = True
                    meta["download_attempt"] = 5
                    meta["state"] = "failed"
                    meta["manual_retry_authorized"] = False
                    meta["last_download_error"] = exc
                    self._failed_download_keys.add(key)
                    self._show_tool_unavailable(tool, key, exc)
                    continue

        except queue.Empty:
            pass

        try:
            self.after(100, self._poll_tool_download_events)
        except tk.TclError:
            pass

    def _tool_download_ready(self, tool, key, local_path):
        if key not in self.open_tabs:
            return

        tool["path"] = local_path
        meta = self.open_tabs[key]
        meta["state"] = "preparing"
        self._show_tool_loading(tool, key, "Verificando dependencias...")

        # Dependencias: se preparan en segundo plano y se muestran en esta pestaña.
        self._install_dependencies(tool, key)

    def _resolve_integrated_entry(self, module):
        """Encuentra automáticamente la entrada embebible de una herramienta."""
        for name in ("App", "Application"):
            entry = getattr(module, name, None)
            if callable(entry):
                return entry

        # Si el autor no usa un nombre estándar, detectar una clase Frame
        # definida por el propio módulo.
        for entry in vars(module).values():
            if not inspect.isclass(entry):
                continue
            if getattr(entry, "__module__", None) != module.__name__:
                continue
            try:
                if issubclass(entry, tk.Frame):
                    return entry
            except TypeError:
                continue

        # Compatibilidad temporal con paquetes antiguos.
        legacy = getattr(module, "create_tool", None)
        if callable(legacy):
            return legacy
        return None

    def _instantiate_integrated_entry(self, entry, parent):
        """Instancia App/Application adaptando parent y app según la firma."""
        try:
            signature = inspect.signature(entry)
            params = list(signature.parameters.values())
            positional = [
                p for p in params
                if p.kind in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                )
            ]
            has_varargs = any(
                p.kind == inspect.Parameter.VAR_POSITIONAL
                for p in params
            )
        except (TypeError, ValueError):
            positional = []
            has_varargs = True

        if has_varargs or len(positional) >= 2:
            widget = entry(parent, self)
        elif len(positional) == 1:
            widget = entry(parent)
        else:
            widget = entry()

        if widget is None or not hasattr(widget, "pack"):
            raise TypeError(
                "La entrada integrada debe devolver o construir un widget Tkinter."
            )
        return widget

    def _run_with_embedded_tk(self, parent, callback):
        """Ejecuta Tkinter comun dentro de una pestaña, sin crear ventanas externas."""
        roots = []
        real_tk = tk.Tk
        real_toplevel = tk.Toplevel
        real_mainloop = tk.mainloop

        class EmbeddedRoot(tk.Frame):
            """Sustituto embebido de Tk que tambien puede usarse como clase base."""

            def __init__(self, *args, **kwargs):
                bg = kwargs.pop("bg", kwargs.pop("background", None))
                super().__init__(parent, bg=bg or parent.cget("bg"))
                self.pack(fill="both", expand=True)
                self._ptm_protocols = {}
                roots.append(self)

            def title(self, *args, **kwargs):
                return None

            wm_title = title

            def geometry(self, *args, **kwargs):
                return ""

            wm_geometry = geometry

            def minsize(self, *args, **kwargs):
                return None

            wm_minsize = minsize

            def maxsize(self, *args, **kwargs):
                return None

            wm_maxsize = maxsize

            def resizable(self, *args, **kwargs):
                return None

            wm_resizable = resizable

            def protocol(self, name=None, func=None):
                if name and func:
                    self._ptm_protocols[name] = func
                return self._ptm_protocols.get(name)

            wm_protocol = protocol

            def attributes(self, *args, **kwargs):
                return None

            wm_attributes = attributes

            def iconbitmap(self, *args, **kwargs):
                return None

            wm_iconbitmap = iconbitmap

            def iconphoto(self, *args, **kwargs):
                return None

            wm_iconphoto = iconphoto

            def state(self, *args, **kwargs):
                return "normal"

            wm_state = state

            def withdraw(self):
                return None

            wm_withdraw = withdraw

            def deiconify(self):
                return None

            wm_deiconify = deiconify

            def iconify(self):
                return None

            wm_iconify = iconify

            def overrideredirect(self, *args, **kwargs):
                return None

            wm_overrideredirect = overrideredirect

            def transient(self, *args, **kwargs):
                return None

            wm_transient = transient

            def mainloop(self, *args, **kwargs):
                return None

            def quit(self):
                return None

        class EmbeddedToplevel(EmbeddedRoot):
            """Toplevel integrado: permanece dentro de la misma pestaña PTM."""

        def no_mainloop(*args, **kwargs):
            return None

        class TkProxy:
            def __getattr__(self, name):
                if name == "Tk":
                    return EmbeddedRoot
                if name == "Toplevel":
                    return EmbeddedToplevel
                if name == "mainloop":
                    return no_mainloop
                return getattr(tk, name)

        try:
            # Se usan clases, no funciones, para soportar tambien:
            # class MiVentana(tk.Tk): ...
            tk.Tk = EmbeddedRoot
            tk.Toplevel = EmbeddedToplevel
            tk.mainloop = no_mainloop
            callback()
        finally:
            tk.Tk = real_tk
            tk.Toplevel = real_toplevel
            tk.mainloop = real_mainloop

        return roots, TkProxy()

    def _load_tool_into_tab(self, tool, key):
        meta = self.open_tabs.get(key)
        if not meta:
            return

        frame = meta["frame"]
        self._clear_tool_frame(frame)

        if str(tool.get("mode", "")).strip().lower() == "externo":
            self._show_tool_unavailable(
                tool,
                key,
                RuntimeError(
                    "PTM solo admite herramientas integradas dentro de una pestaña."
                ),
            )
            return

        try:
            module_name = f"ptm_tool_{tool['path'].stem}_{abs(hash(key))}"
            spec = importlib.util.spec_from_file_location(module_name, tool["path"])
            if spec is None or spec.loader is None:
                raise RuntimeError("No se pudo preparar el módulo.")
            module = importlib.util.module_from_spec(spec)

            embedded_roots, tk_proxy = self._run_with_embedded_tk(
                frame,
                lambda: spec.loader.exec_module(module),
            )

            # Si el script hizo "import tkinter as tk", mantener un proxy
            # para que futuros callbacks tampoco puedan abrir ventanas.
            if getattr(module, "tk", None) is tk:
                module.tk = tk_proxy

        except Exception as exc:
            self._show_tool_unavailable(tool, key, exc)
            return

        widget = embedded_roots[0] if embedded_roots else None

        if widget is None:
            entry = self._resolve_integrated_entry(module)
            if callable(entry):
                try:
                    widget = self._instantiate_integrated_entry(entry, frame)
                except Exception as exc:
                    self._show_tool_unavailable(tool, key, exc)
                    return

        # Un principiante puede haber puesto todo dentro de main().
        if widget is None:
            main_func = getattr(module, "main", None)
            if callable(main_func):
                try:
                    embedded_roots, tk_proxy = self._run_with_embedded_tk(
                        frame,
                        main_func,
                    )
                    if getattr(module, "tk", None) is tk:
                        module.tk = tk_proxy
                    widget = embedded_roots[0] if embedded_roots else None
                except Exception as exc:
                    self._show_tool_unavailable(tool, key, exc)
                    return

        if widget is None:
            self._show_tool_unavailable(
                tool,
                key,
                RuntimeError(
                    "No se pudo detectar una interfaz Tkinter para integrar."
                ),
            )
            return

        if not widget.winfo_manager():
            widget.pack(fill="both", expand=True)

        meta["module"] = module
        meta["state"] = "ready"
        meta["loading_status"] = None
        self._activate_tool_if_foreground(key)

    def _activate_tool_if_foreground(self, key):
        """Actualiza la pestaña sin robar el foco si fue abierta en segundo plano."""
        meta = self.open_tabs.get(key)
        if not meta:
            return
        if meta.get("background_open"):
            self._render_tabs()
            return
        self.switch_to_tool(key)

    def open_tool(self, tool, record_usage=True, background=False):
        if record_usage:
            self._record_tool_open(tool)
        key = self._tool_tab_key(tool)

        if key in self.open_tabs:
            if not background:
                self.switch_to_tool(key)
            else:
                self._render_tabs()
            return

        frame = tk.Frame(self.content, bg=WHITE)
        self.open_tabs[key] = {
            "name": tool.get("name", "Herramienta"),
            "tool": tool,
            "frame": frame,
            "module": None,
            "state": "loading",
            "background_open": bool(background),
            "download_attempt": 0,
            "download_session_id": 0,
            "download_worker_running": False,
            "download_finished": False,
            "manual_retry_authorized": False,
            "last_download_error": None,
        }

        self._render_tabs()
        self._show_tool_loading(tool, key)
        self._start_tool_download(tool, key)

    def switch_to_tool(self, key):
        if key not in self.open_tabs:
            return
        self.open_tabs[key]["background_open"] = False
        self.current_key = key
        self._clear_content()
        if hasattr(self, "home_frame") and self.home_frame.winfo_exists():
            self.home_frame.pack_forget()
        meta = self.open_tabs[key]
        meta["frame"].pack(fill="both", expand=True)
        self.current_tool_module = meta["module"]
        # Si la herramienta expuso un único widget hijo, lo usamos para callbacks opcionales.
        children = meta["frame"].winfo_children()
        self.current_tool_widget = children[0] if len(children) == 1 else meta["frame"]
        try:
            if hasattr(self.current_tool_widget, "on_show"):
                self.current_tool_widget.on_show()
        except Exception:
            pass
        self._render_tabs()

    def show_dialog(self, title, message, kind="info", button_text="Aceptar", on_close=None):
        """Muestra un diálogo modal dentro del área de PTM, sin crear otra ventana."""
        # El diálogo pertenece a la pestaña activa, nunca al contenedor global.
        dialog_key = self.current_key
        if not dialog_key or dialog_key == "home":
            return None
        meta = self.open_tabs.get(dialog_key)
        if not meta:
            return None
        host = meta["frame"]
        if not host.winfo_exists():
            return None

        old = meta.get("inline_dialog")
        if old is not None:
            try:
                old.destroy()
            except tk.TclError:
                pass
            meta["inline_dialog"] = None

        # Bloquea los controles de esta herramienta mientras el modal esté abierto.
        disabled_controls = []
        def disable_controls(widget):
            for child in widget.winfo_children():
                disable_controls(child)
                try:
                    if "state" in child.keys():
                        previous = str(child.cget("state"))
                        if previous != "disabled":
                            child.configure(state="disabled")
                            disabled_controls.append((child, previous))
                except (tk.TclError, AttributeError):
                    pass

        disable_controls(host)
        meta["dialog_disabled_controls"] = disabled_controls

        # Backdrop real: captura la pestaña antes de cubrirla, la desenfoca y
        # aplica un velo claro translúcido. El overlay ocupa toda la herramienta,
        # por lo que también intercepta cualquier clic sobre el contenido inferior.
        host.update_idletasks()
        host_w = max(1, host.winfo_width())
        host_h = max(1, host.winfo_height())
        backdrop_photo = None

        try:
            from PIL import Image, ImageEnhance, ImageFilter, ImageGrab, ImageTk

            x1 = host.winfo_rootx()
            y1 = host.winfo_rooty()
            snapshot = ImageGrab.grab(
                bbox=(x1, y1, x1 + host_w, y1 + host_h)
            ).convert("RGBA")
            snapshot = snapshot.filter(ImageFilter.GaussianBlur(radius=4))
            snapshot = ImageEnhance.Brightness(snapshot).enhance(0.96)

            veil = Image.new(
                "RGBA",
                snapshot.size,
                (242, 246, 248, 72),
            )
            snapshot = Image.alpha_composite(snapshot, veil)
            backdrop_photo = ImageTk.PhotoImage(snapshot)
        except Exception:
            backdrop_photo = None

        overlay = tk.Frame(host, bg="#EEF2F4", bd=0, highlightthickness=0)
        overlay.place(x=0, y=0, relwidth=1, relheight=1)
        overlay.lift()
        meta["inline_dialog"] = overlay

        if backdrop_photo is not None:
            backdrop = tk.Label(
                overlay,
                image=backdrop_photo,
                bd=0,
                highlightthickness=0,
            )
            backdrop.place(x=0, y=0, width=host_w, height=host_h)
            overlay._backdrop_photo = backdrop_photo

        # Glow/sombra suave alrededor de la tarjeta, encima del backdrop.
        shadow_outer = tk.Frame(overlay, bg="#D7DDE1", bd=0)
        shadow_outer.place(
            relx=0.5, rely=0.46, anchor="center",
            width=426, height=218
        )
        shadow_mid = tk.Frame(shadow_outer, bg="#C5CDD2", bd=0)
        shadow_mid.place(x=8, y=8, width=410, height=202)

        card = tk.Frame(
            shadow_mid, bg=WHITE, highlightbackground="#AEB7BD",
            highlightthickness=1, bd=0
        )
        card.place(x=8, y=8, width=394, height=186)

        header = tk.Frame(card, bg=WHITE)
        header.pack(fill="x", padx=18, pady=(16, 6))
        tk.Label(
            header, text=title, bg=WHITE, fg=BLACK,
            font=("Segoe UI", 11, "bold"), anchor="w"
        ).pack(side="left", fill="x", expand=True)

        symbol = {"info": "i", "success": "✓", "warning": "!", "error": "×"}.get(
            str(kind).lower(), "i"
        )
        symbol_fg = {
            "success": TEAL, "warning": "#B36B00", "error": RED, "info": TEAL
        }.get(str(kind).lower(), TEAL)

        body = tk.Frame(card, bg=WHITE)
        body.pack(fill="x", padx=20, pady=(8, 14))
        tk.Label(
            body, text=symbol, bg=WHITE, fg=symbol_fg,
            font=("Segoe UI", 22, "bold"), width=2
        ).pack(side="left", anchor="n", padx=(0, 8))
        tk.Label(
            body, text=message, bg=WHITE, fg=BLACK,
            font=("Segoe UI", 10), justify="left", anchor="w",
            wraplength=285
        ).pack(side="left", fill="x", expand=True)

        def close_dialog(event=None):
            if meta.get("inline_dialog") is overlay:
                meta["inline_dialog"] = None
            try:
                overlay.destroy()
            except tk.TclError:
                pass

            # Restaura exactamente el estado que tenía cada control.
            for widget, previous in meta.pop("dialog_disabled_controls", []):
                try:
                    if widget.winfo_exists():
                        widget.configure(state=previous)
                except (tk.TclError, AttributeError):
                    pass

            if callable(on_close):
                on_close()

        footer = tk.Frame(card, bg="#F4F6F7")
        footer.pack(fill="x")
        btn = tk.Button(
            footer, text=button_text, command=close_dialog,
            bg=TEAL, fg=ON_ACCENT, activebackground=TEAL_DARK,
            activeforeground=ON_ACCENT, relief="flat", padx=18, pady=6,
            cursor="hand2"
        )
        btn.pack(side="right", padx=14, pady=10)
        btn.focus_set()
        overlay.bind("<Return>", close_dialog)
        overlay.bind("<Escape>", close_dialog)
        return overlay

    def set_tool_processing(self, active=True, key=None):
        """Marca una pestaña como ocupada durante trabajo propio de la herramienta."""
        target_key = key or self.current_key
        if not target_key or target_key == "home":
            return False

        meta = self.open_tabs.get(target_key)
        if not meta:
            return False

        if active:
            # Solo una herramienta ya cargada debe entrar a processing por esta API.
            if meta.get("state") in {"ready", "processing"}:
                meta["state"] = "processing"
        else:
            if meta.get("state") == "processing":
                meta["state"] = "ready"

        self._render_tabs()
        return True

    def tool_processing(self, key=None):
        """Context manager simple para herramientas que ejecutan trabajo síncrono."""
        app = self

        class _ProcessingContext:
            def __enter__(self_inner):
                app.set_tool_processing(True, key)
                return self_inner

            def __exit__(self_inner, exc_type, exc, tb):
                app.set_tool_processing(False, key)
                return False

        return _ProcessingContext()

    def close_tool_tab(self, key):
        meta = self.open_tabs.get(key)
        if not meta:
            return
        frame = meta["frame"]
        try:
            for child in frame.winfo_children():
                if hasattr(child, "on_close"):
                    child.on_close()
        except Exception:
            pass
        frame.destroy()
        del self.open_tabs[key]
        if self.current_key == key:
            self.show_home()
        else:
            self._render_tabs()

    def run_external(self, path):
        try:
            subprocess.Popen([sys.executable, str(path)], cwd=str(path.parent))
        except OSError as exc:
            messagebox.showerror("PTM", str(exc))

    def _draw_pin_button(self):
        """Dibuja el pin: rojo cuando PTM esta fijado arriba."""
        if not hasattr(self, "pin_canvas"):
            return
        c = self.pin_canvas
        c.delete("all")
        color = RED if self.pinned else MUTED

        # Cabeza del pin.
        c.create_line(10, 8, 20, 8, fill=color, width=2)
        c.create_line(12, 8, 12, 14, fill=color, width=2)
        c.create_line(18, 8, 18, 14, fill=color, width=2)
        c.create_line(10, 14, 20, 14, fill=color, width=2)

        # Punta.
        c.create_line(15, 14, 15, 23, fill=color, width=2)
        c.create_line(15, 23, 12, 26, fill=color, width=2)

        if self.pinned:
            c.create_rectangle(2, 27, 28, 29, fill=RED, outline=RED)

    def toggle_pin(self, _event=None):
        """Activa o desactiva 'siempre al frente' para la ventana principal."""
        self.pinned = not self.pinned
        try:
            self.attributes("-topmost", self.pinned)
            if self.pinned:
                self.lift()
                self.focus_force()
        except tk.TclError:
            pass
        self._draw_pin_button()

    # ---------- Sistema ----------
    def open_tools_folder(self):
        try:
            if os.name == "nt":
                os.startfile(str(self.tools_dir))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(self.tools_dir)])
            else:
                subprocess.Popen(["xdg-open", str(self.tools_dir)])
        except OSError as exc:
            messagebox.showerror("PTM", str(exc))

    def hide_main(self):
        self.withdraw()

    def show_main(self):
        self.deiconify()
        self.attributes("-topmost", self.pinned)
        self.lift()
        if self.pinned:
            self.focus_force()

    def toggle_main(self):
        if self.state() == "withdrawn" or not self.winfo_viewable():
            self.show_main()
        else:
            self.hide_main()

    def exit_app(self):
        try:
            self.floating.destroy()
        except Exception:
            pass
        release_single_instance_lock()
        self.destroy()


if __name__ == "__main__":
    if check_self_update():
        raise SystemExit(0)

    if not acquire_single_instance_lock():
        raise SystemExit(0)

    PTMApp().mainloop()