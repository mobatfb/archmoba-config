# ARGUMENTOS: ptm launcher lanzador buscador ejecutor py python herramientas scripts pestañas icono flotante
import ast
import csv
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import tkinter as tk
import urllib.request
import zipfile
from pathlib import Path
from tkinter import filedialog, messagebox

APP_TITLE = "PTM - Buscador y lanzador de herramientas"
APP_VERSION = "1.0.0"

REPO_RAW_BASE = "https://raw.githubusercontent.com/mobatfb/archmoba-config/main/TESTAPP"
GUIDE_URL = f"{REPO_RAW_BASE}/guide.csv"

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
RED = "#FF1616"
ON_ACCENT = "#FFFFFF"

WHITE = "#17191C" if DARK_MODE else "#FFFFFF"
BLACK = "#F2F4F7" if DARK_MODE else "#101010"
LIGHT = "#22252A" if DARK_MODE else "#F4F4F4"
MID = "#3A3F46" if DARK_MODE else "#D7D7D7"
MUTED = "#A9AFB8" if DARK_MODE else "#666666"


class TabButton(tk.Canvas):
    """Pestaña dibujada por código con esquina roja tipo PTM."""

    def __init__(self, parent, title, on_open, on_close=None, active=False, width=118, height=30):
        super().__init__(parent, width=width, height=height, highlightthickness=0, bd=0, bg=WHITE)
        self.title = title
        self.on_open = on_open
        self.on_close = on_close
        self.tab_width = width
        self.tab_height = height
        self.active = active
        self.bind("<Button-1>", self._click)
        self.bind("<Button-3>", self._right_click)
        self.draw()

    def set_active(self, active):
        self.active = active
        self.draw()

    def set_size(self, width):
        self.tab_width = width
        self.configure(width=width)
        self.draw()

    def draw(self):
        self.delete("all")
        w, h = self.tab_width, self.tab_height
        fill = WHITE if self.active else TEAL
        fg = (BLACK if DARK_MODE else TEAL_DARK) if self.active else ON_ACCENT
        outline = TEAL_DARK
        self.create_rectangle(1, 1, w - 1, h - 1, fill=fill, outline=outline, width=1)
        self.create_polygon(w - 18, 1, w - 1, 1, w - 1, 18, fill=RED, outline=RED)
        if self.active:
            self.create_rectangle(1, h - 5, w - 1, h - 1, fill=RED, outline=RED)
        max_chars = max(7, int((w - 20) / 7.2))
        shown = self.title if len(self.title) <= max_chars else self.title[: max_chars - 1] + "…"
        self.create_text(w / 2, h / 2 - (2 if self.active else 0), text=shown,
                         fill=fg, font=("Segoe UI", 9, "bold" if self.active else "normal"))

    def _click(self, event):
        # En pestañas de herramientas, la esquina roja también sirve para cerrarlas.
        if self.on_close and event.x >= self.tab_width - 22 and event.y <= 22:
            self.on_close()
        else:
            self.on_open()

    def _right_click(self, _event):
        if self.on_close:
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label="Cerrar pestaña", command=self.on_close)
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
        self.bind("<Double-Button-1>", lambda _e: self.app.show_main())

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
            self.app.toggle_main()

    def _menu(self, _event):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Abrir PTM", command=self.app.show_main)
        menu.add_command(label="Recargar herramientas", command=self.app.reload_tools)
        menu.add_command(label="Abrir carpeta de herramientas", command=self.app.open_tools_folder)
        menu.add_separator()
        menu.add_command(label="Salir", command=self.app.exit_app)
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

        self.query = tk.StringVar()
        self.show_all_results = False
        self.tools = []
        self.open_tabs = {}       # key -> metadata/content
        self.tab_widgets = {}
        self.current_key = "home"
        self.current_tool_widget = None
        self.current_tool_module = None

        self._apply_responsive_geometry()
        self.overrideredirect(True)
        self.protocol("WM_DELETE_WINDOW", self.hide_main)

        self._build_shell()
        self.reload_tools()
        self.show_home()

        self.floating = FloatingPTM(self)
        self.bind("<Escape>", lambda _e: self.hide_main())

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

        self.close_canvas = tk.Canvas(self.top, width=30, height=30, bg=WHITE,
                                      highlightthickness=0, bd=0, cursor="hand2")
        self.close_canvas.pack(side="right", padx=(8, 4), pady=(2, 0))
        self.close_canvas.create_line(8, 8, 22, 22, fill=BLACK, width=2)
        self.close_canvas.create_line(22, 8, 8, 22, fill=BLACK, width=2)
        self.close_canvas.bind("<Button-1>", lambda _e: self.hide_main())

        self.separator = tk.Frame(self.outer, bg=WHITE, height=2)
        self.separator.pack(fill="x")

        self.content = tk.Frame(self.outer, bg=WHITE)
        self.content.pack(fill="both", expand=True, padx=10, pady=(2, 4))

        self.footer = tk.Frame(self.outer, bg=WHITE, height=24)
        self.footer.pack(fill="x", padx=10, pady=(0, 5))
        self.footer.pack_propagate(False)

        self.version_label = tk.Label(
            self.footer,
            text=f"PTM v{APP_VERSION}",
            bg=WHITE,
            fg=MUTED,
            font=("Segoe UI", 8),
            anchor="e",
        )
        self.version_label.pack(side="right", padx=(0, 4))

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

        keys = ["home"] + list(self.open_tabs.keys())
        available = max(520, self.winfo_width() - 70)
        tab_width = max(90, min(130, available // max(1, len(keys))))

        home = TabButton(
            self.tabs_holder,
            "PTM",
            on_open=self.show_home,
            active=(self.current_key == "home"),
            width=tab_width,
        )
        home.pack(side="left", padx=(0, 6))
        self.tab_widgets["home"] = home

        for key in self.open_tabs:
            meta = self.open_tabs[key]
            tab = TabButton(
                self.tabs_holder,
                meta["name"],
                on_open=lambda k=key: self.switch_to_tool(k),
                on_close=lambda k=key: self.close_tool_tab(k),
                active=(self.current_key == key),
                width=tab_width,
            )
            tab.pack(side="left", padx=(0, 6))
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
        self.search_btn.bind("<Button-1>", lambda _e: self.open_first_result())

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
        self.results_canvas.bind(
            "<MouseWheel>",
            lambda e: self.results_canvas.yview_scroll(
                int(-1 * (e.delta / 120)), "units"
            ),
        )

        self._apply_search_layout(expanded=False)

    def _apply_search_layout(self, expanded=False):
        """Cambia la composición del inicio al pulsar Enter."""
        if not hasattr(self, "center"):
            return

        self.logo.grid_forget()
        self.logo_compact.grid_forget()
        self.search_wrap.grid_forget()
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
            self.hint.grid(
                row=1, column=1, sticky="ew",
                pady=(3, 3)
            )
            self.results_container.grid(
                row=2, column=1, sticky="ew"
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
            self.hint.grid(
                row=2, column=0, columnspan=2,
                sticky="ew", pady=(6, 4)
            )
            self.results_container.grid(
                row=3, column=0, columnspan=2,
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

    # ---------- Herramientas ----------
    def reload_tools(self):
        """Carga exclusivamente el catálogo guide.csv."""
        self.tools = []
        try:
            rows = self._load_guide_rows()
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
            dependencies = str(row.get("dependencias", "")).strip()
            author = str(row.get("autor", "")).strip()
            slug = str(row.get("slug", "")).strip()
            try:
                visits = int(str(row.get("visitas", "0")).strip() or "0")
            except ValueError:
                visits = 0

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
                "dependencies": dependencies,
                "author": author,
                "visits": visits,
                "main_file": str(row.get("archivo_principal", "")).strip(),
                "search": (
                    f"{slug} {Path(repo_path).stem} {name} {description} "
                    f"{keywords} {category} {version} {dependencies} {author}"
                ).lower(),
            })

        if hasattr(self, "results_frame") and self.results_frame.winfo_exists():
            self.refresh_results()

    def _load_guide_rows(self):
        """Descarga guide.csv de GitHub y usa la copia local solo como respaldo."""
        text = None
        remote_error = None

        try:
            request = urllib.request.Request(
                f"{GUIDE_URL}?v={time.time_ns()}",
                headers={
                    "User-Agent": "PTM/1.0",
                    "Cache-Control": "no-cache",
                },
            )
            with urllib.request.urlopen(request, timeout=12) as response:
                text = response.read().decode("utf-8-sig")
            self.guide_path.write_text(text, encoding="utf-8")
        except Exception as exc:
            remote_error = exc

        if text is None:
            if self.guide_path.is_file():
                text = self.guide_path.read_text(encoding="utf-8-sig")
            else:
                raise RuntimeError(f"GitHub no respondió y no existe copia local ({remote_error})")

        reader = csv.DictReader(io.StringIO(text), delimiter=";")
        if not reader.fieldnames or "ruta" not in reader.fieldnames:
            raise ValueError("guide.csv no contiene la columna 'ruta'.")
        return list(reader)

    def _ensure_tool_local(self, tool):
        """Descarga el .py indicado por guide.csv antes de abrirlo."""
        repo_path = str(tool.get("repo_path", "")).strip().replace("\\", "/").lstrip("/")
        if not repo_path:
            raise ValueError("La herramienta no tiene una ruta válida en guide.csv.")

        local_path = self.base_dir / Path(repo_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        remote_url = f"{REPO_RAW_BASE}/{repo_path}?v={time.time_ns()}"
        request = urllib.request.Request(
            remote_url,
            headers={
                "User-Agent": "PTM/1.0",
                "Cache-Control": "no-cache",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                data = response.read()
            # Validar sintaxis antes de reemplazar una copia funcional.
            source = data.decode("utf-8-sig")
            compile(source, repo_path, "exec")
            temp_path = local_path.with_suffix(local_path.suffix + ".tmp")
            temp_path.write_bytes(data)
            temp_path.replace(local_path)
        except Exception:
            if not local_path.is_file():
                raise

        return local_path

    def filtered_tools(self):
        q = self.query.get().strip().lower()
        if not q:
            return []

        tokens = [t for t in q.replace(",", " ").split() if t]
        matches = [tool for tool in self.tools if all(t in tool["search"] for t in tokens)]

        # Evitar duplicados por id/slug/ruta y priorizar las más visitadas.
        unique = {}
        for tool in matches:
            key = tool.get("id") or tool.get("slug") or tool.get("repo_path") or str(tool["path"])
            current = unique.get(key)
            if current is None or int(tool.get("visits", 0)) > int(current.get("visits", 0)):
                unique[key] = tool

        return sorted(
            unique.values(),
            key=lambda tool: (-int(tool.get("visits", 0)), tool["name"].lower()),
        )

    def _on_search_key_release(self, event):
        if getattr(event, "keysym", "") == "Return":
            return
        self.show_all_results = False
        self._apply_search_layout(expanded=False)
        self.refresh_results()

    def _show_all_search_results(self, _event=None):
        self.show_all_results = True
        self._apply_search_layout(expanded=True)
        self.refresh_results()
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
                meta.pack(anchor="e")

                mode = tool.get("mode", "").strip() or "Integrado"
                dependencies = tool.get("dependencies", "").strip() or "Sin dependencias"
                author = tool.get("author", "").strip() or "Sin autor"
                extra = tk.Label(
                    right,
                    text=f"{author} · {mode} · {dependencies}",
                    bg=LIGHT,
                    fg=MUTED,
                    font=("Segoe UI", 8),
                    anchor="e",
                    justify="right",
                )
                extra.pack(anchor="e", pady=(4, 0))

                clickable = (row, left, right, label, desc, meta, extra)
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
                widget.bind("<Double-Button-1>", lambda _e, t=tool: self.open_tool(t))
                widget.bind("<Button-1>", lambda _e, t=tool: self.open_tool(t))

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
        mode_menu = tk.OptionMenu(container, mode_var, "Integrado", "Externo")
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

    def open_tool(self, tool):
        try:
            tool["path"] = self._ensure_tool_local(tool)
        except Exception as exc:
            messagebox.showerror(
                "PTM",
                f"No se pudo descargar la herramienta desde el catálogo:\n\n{exc}"
            )
            return

        key = str(tool["path"].resolve())
        if key in self.open_tabs:
            self.switch_to_tool(key)
            return

        if str(tool.get("mode", "")).strip().lower() == "externo":
            frame = tk.Frame(self.content, bg=WHITE)
            info = tk.Frame(frame, bg=WHITE)
            info.pack(expand=True)
            tk.Label(
                info, text=tool["name"], bg=WHITE, fg=BLACK,
                font=("Segoe UI", 20, "bold")
            ).pack(pady=(0, 8))
            if tool.get("description"):
                tk.Label(
                    info, text=tool["description"], bg=WHITE, fg=MUTED,
                    font=("Segoe UI", 10), wraplength=520, justify="center"
                ).pack(pady=(0, 10))
            tk.Button(
                info, text="Ejecutar herramienta",
                command=lambda p=tool["path"]: self.run_external(p),
                bg=TEAL, fg=ON_ACCENT, activebackground=TEAL_DARK,
                activeforeground=ON_ACCENT, relief="flat", padx=18, pady=8
            ).pack(pady=8)

            self.open_tabs[key] = {
                "name": tool["name"],
                "tool": tool,
                "frame": frame,
                "module": None,
            }
            self.switch_to_tool(key)
            return

        try:
            module_name = f"ptm_tool_{tool['path'].stem}_{abs(hash(key))}"
            spec = importlib.util.spec_from_file_location(module_name, tool["path"])
            if spec is None or spec.loader is None:
                raise RuntimeError("No se pudo preparar el módulo.")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as exc:
            messagebox.showerror("PTM", f"No se pudo cargar {tool['path'].name}:\n\n{exc}")
            return

        factory = getattr(module, "create_tool", None)
        frame = tk.Frame(self.content, bg=WHITE)
        if callable(factory):
            try:
                widget = factory(frame, self)
                widget.pack(fill="both", expand=True)
            except Exception as exc:
                frame.destroy()
                messagebox.showerror("PTM", f"Error al abrir {tool['name']}:\n\n{exc}")
                return
        else:
            # Herramientas antiguas siguen siendo utilizables, aunque no puedan integrarse.
            info = tk.Frame(frame, bg=WHITE)
            info.pack(expand=True)
            tk.Label(info, text=tool["name"], bg=WHITE, fg=BLACK,
                     font=("Segoe UI", 20, "bold")).pack(pady=(0, 10))
            tk.Label(info, text="Este archivo no contiene create_tool(parent, app).",
                     bg=WHITE, fg=MUTED, font=("Segoe UI", 10)).pack(pady=5)
            tk.Button(info, text="Ejecutar como programa externo",
                      command=lambda p=tool["path"]: self.run_external(p),
                      bg=TEAL, fg=ON_ACCENT, activebackground=TEAL_DARK,
                      relief="flat", padx=16, pady=8).pack(pady=10)

        self.open_tabs[key] = {
            "name": tool["name"],
            "tool": tool,
            "frame": frame,
            "module": module,
        }
        self.switch_to_tool(key)

    def switch_to_tool(self, key):
        if key not in self.open_tabs:
            return
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
        self.lift()
        self.attributes("-topmost", True)
        self.after(120, lambda: self.attributes("-topmost", False))

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
        self.destroy()


if __name__ == "__main__":
    PTMApp().mainloop()