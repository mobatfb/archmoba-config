# ARGUMENTOS: amdev archmomadev launcher apps aplicaciones catalogo remoto github
import json
import os
import subprocess
import sys
import time
import tkinter as tk
import urllib.request
from pathlib import Path
from tkinter import messagebox

APP_NAME = "ArchMomaDEV"
APP_SHORT = "AMDEV"
APP_VERSION = "1.0.2"
APP_UPDATE_DATE = "27/10/2026"
APP_UPDATE_TIME = "18:51"

REPO_RAW_BASE = "https://raw.githubusercontent.com/mobatfb/archmoba-config/main"
APPS_URL = f"{REPO_RAW_BASE}/apps.json"

TEAL = "#176684"
TEAL_DARK = "#0F536E"
RED = "#FF1616"
WHITE = "#FFFFFF"
BLACK = "#101010"
LIGHT = "#F4F4F4"
MID = "#D7D7D7"
MUTED = "#666666"


def detect_system_dark_mode():
    if sys.platform == "win32":
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return int(value) == 0
        except Exception:
            return False
    return "dark" in os.environ.get("GTK_THEME", "").lower()


DARK_MODE = detect_system_dark_mode()
BG = "#17191C" if DARK_MODE else WHITE
FG = "#F2F4F7" if DARK_MODE else BLACK
CARD = "#22252A" if DARK_MODE else LIGHT
BORDER = "#3A3F46" if DARK_MODE else MID
MUTED_FG = "#A9AFB8" if DARK_MODE else MUTED


class FloatingAMDEV(tk.Toplevel):
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

        self.w = 112
        self.h = 52
        self.geometry(f"{self.w}x{self.h}+0+0")
        self.canvas = tk.Canvas(
            self, width=self.w, height=self.h,
            bg="#010101", highlightthickness=0, bd=0,
            cursor="hand2"
        )
        self.canvas.pack(fill="both", expand=True)
        self._draw()

        self.canvas.bind("<Button-1>", self._down)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._up)
        self.canvas.bind("<Button-3>", self._menu)

        self._dragging = False
        self._press_xy = (0, 0)
        self._place_default()

    def _draw(self):
        self.canvas.delete("all")
        self.canvas.create_rectangle(2, 2, self.w - 2, self.h - 2, fill=TEAL, outline=FG, width=1)
        self.canvas.create_polygon(self.w - 20, 2, self.w - 2, 2, self.w - 2, 20, fill=RED, outline=RED)
        self.canvas.create_rectangle(2, self.h - 9, self.w - 2, self.h - 2, fill=RED, outline=RED)
        self.canvas.create_text(self.w / 2, 20, text=APP_SHORT, fill=WHITE, font=("Segoe UI", 18, "bold"))
        self.canvas.create_text(self.w / 2, self.h - 6, text=APP_NAME, fill=WHITE, font=("Segoe UI", 5, "bold"))

    def _place_default(self):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{self.w}x{self.h}+{max(10, sw-self.w-18)}+{max(10, sh-self.h-70)}")

    def _down(self, event):
        self._dragging = False
        self._press_xy = (event.x_root, event.y_root)
        self._origin = (self.winfo_x(), self.winfo_y())

    def _drag(self, event):
        dx = event.x_root - self._press_xy[0]
        dy = event.y_root - self._press_xy[1]
        if abs(dx) + abs(dy) > 4:
            self._dragging = True
        self.geometry(f"+{self._origin[0] + dx}+{self._origin[1] + dy}")

    def _up(self, event):
        if not self._dragging:
            self.app.show_app_menu(event.x_root, event.y_root)

    def _menu(self, _event):
        self.app.show_app_menu(self.winfo_pointerx(), self.winfo_pointery())


class AMDEVApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} - {APP_SHORT}")
        self.configure(bg=BG)
        self.overrideredirect(True)

        self.base_dir = Path(
            os.environ.get("LOCALAPPDATA", str(Path.home()))
        ) / "ARCHMOBA" / "AMDEV"
        self.cache_dir = self.base_dir / "apps"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.apps_cache = self.base_dir / "apps.json"

        self.geometry(self._default_geometry())
        self.protocol("WM_DELETE_WINDOW", self.hide_main)

        self.apps = []
        self._build_ui()
        self.load_apps()

        self.floating = FloatingAMDEV(self)
        self.withdraw()
        self.bind("<Escape>", lambda _e: self.hide_app_menu())

    def _default_geometry(self):
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w = min(720, max(600, int(sw * 0.48)))
        h = min(560, max(430, int(sh * 0.55)))
        x = max(20, (sw - w) // 2)
        y = max(20, (sh - h) // 2)
        return f"{w}x{h}+{x}+{y}"

    def _build_ui(self):
        self.outer = tk.Frame(self, bg=BG, bd=1, relief="solid")
        self.outer.pack(fill="both", expand=True)

        top = tk.Frame(self.outer, bg=BG, height=42)
        top.pack(fill="x", padx=10, pady=(8, 0))
        top.pack_propagate(False)
        top.bind("<Button-1>", self._start_move)
        top.bind("<B1-Motion>", self._move)

        tk.Label(
            top, text=f"{APP_NAME}  |  {APP_SHORT}",
            bg=BG, fg=FG, font=("Segoe UI", 12, "bold")
        ).pack(side="left", padx=6)

        close = tk.Canvas(top, width=30, height=30, bg=BG, highlightthickness=0, bd=0, cursor="hand2")
        close.pack(side="right")
        close.create_line(8, 8, 22, 22, fill=FG, width=2)
        close.create_line(22, 8, 8, 22, fill=FG, width=2)
        close.bind("<Button-1>", lambda _e: self.hide_main())

        body = tk.Frame(self.outer, bg=BG)
        body.pack(fill="both", expand=True, padx=22, pady=18)

        tk.Label(
            body,
            text="Aplicaciones",
            bg=BG, fg=FG,
            font=("Segoe UI", 24, "bold"),
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            body,
            text="Selecciona una aplicación. AMDEV leerá su config.json, descargará el app.py y lo ejecutará.",
            bg=BG, fg=MUTED_FG,
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
            wraplength=620,
        ).pack(fill="x", pady=(4, 14))

        self.status = tk.Label(
            body, text="", bg=BG, fg=MUTED_FG,
            font=("Segoe UI", 8), anchor="w"
        )
        self.status.pack(fill="x", pady=(0, 7))

        self.list_frame = tk.Frame(body, bg=BG)
        self.list_frame.pack(fill="both", expand=True)

        footer = tk.Frame(self.outer, bg=BG, height=34)
        footer.pack(fill="x", padx=12, pady=(0, 8))
        footer.pack_propagate(False)

        tk.Label(
            footer,
            text=f"{APP_SHORT} v{APP_VERSION}\nActualizado: {APP_UPDATE_DATE}  {APP_UPDATE_TIME}",
            bg=BG, fg=MUTED_FG,
            font=("Segoe UI", 7), justify="right"
        ).pack(side="right", padx=4)

    def _start_move(self, event):
        self._move_offset = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def _move(self, event):
        self.geometry(f"+{event.x_root - self._move_offset[0]}+{event.y_root - self._move_offset[1]}")

    def _request_text(self, url, timeout=12):
        request = urllib.request.Request(
            f"{url}{'&' if '?' in url else '?'}v={time.time_ns()}",
            headers={"User-Agent": "AMDEV/1.0", "Cache-Control": "no-cache"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8-sig")

    def load_apps(self):
        for child in self.list_frame.winfo_children():
            child.destroy()

        text = None
        try:
            text = self._request_text(APPS_URL)
            self.apps_cache.write_text(text, encoding="utf-8")
            self.status.configure(text="Catálogo actualizado desde GitHub.")
        except Exception as exc:
            if self.apps_cache.is_file():
                text = self.apps_cache.read_text(encoding="utf-8-sig")
                self.status.configure(text=f"Usando catálogo local. GitHub no respondió: {exc}")
            else:
                self.status.configure(text=f"No se pudo cargar apps.json: {exc}")
                return

        try:
            payload = json.loads(text)
            self.apps = [
                item for item in payload.get("apps", [])
                if item.get("active", True)
            ]
        except Exception as exc:
            self.status.configure(text=f"apps.json no es válido: {exc}")
            return

        if not self.apps:
            tk.Label(
                self.list_frame, text="No hay aplicaciones disponibles.",
                bg=BG, fg=MUTED_FG, font=("Segoe UI", 10)
            ).pack(anchor="w")
            return

        for item in self.apps:
            self._add_app_card(item)

    def _add_app_card(self, item):
        card = tk.Frame(
            self.list_frame, bg=CARD,
            highlightbackground=BORDER, highlightthickness=1,
            cursor="hand2"
        )
        card.pack(fill="x", pady=4)

        left = tk.Frame(card, bg=CARD)
        left.pack(side="left", fill="both", expand=True, padx=12, pady=10)

        name = tk.Label(
            left, text=item.get("name", item.get("id", "App")),
            bg=CARD, fg=FG, font=("Segoe UI", 11, "bold"),
            anchor="w", cursor="hand2"
        )
        name.pack(fill="x")

        desc = tk.Label(
            left, text=item.get("description", ""),
            bg=CARD, fg=MUTED_FG, font=("Segoe UI", 8),
            anchor="w", cursor="hand2"
        )
        desc.pack(fill="x", pady=(3, 0))

        arrow = tk.Label(
            card, text="›", bg=CARD, fg=RED,
            font=("Segoe UI", 22, "bold"), cursor="hand2"
        )
        arrow.pack(side="right", padx=14)

        for widget in (card, left, name, desc, arrow):
            widget.bind("<Button-1>", lambda _e, app=item: self.launch_app(app))

    def launch_app(self, item):
        config_path = str(item.get("config", "")).strip().replace("\\", "/").lstrip("/")
        if not config_path:
            messagebox.showerror(APP_SHORT, "La aplicación no tiene config.json definido.")
            return

        try:
            self.status.configure(text=f"Leyendo {config_path}...")
            self.update_idletasks()

            config_text = self._request_text(f"{REPO_RAW_BASE}/{config_path}")
            config = json.loads(config_text)

            if config.get("maintenance", False):
                messagebox.showinfo(APP_SHORT, f"{config.get('name', item.get('name', 'La aplicación'))} está en mantenimiento.")
                return

            app_path = str(config.get("app_path", "")).strip().replace("\\", "/").lstrip("/")
            if not app_path:
                raise ValueError("El config.json no contiene app_path.")

            app_id = str(item.get("id", "app")).strip() or "app"
            local_dir = self.cache_dir / app_id
            local_dir.mkdir(parents=True, exist_ok=True)
            local_app = local_dir / "app.py"

            self.status.configure(text=f"Descargando {app_path}...")
            self.update_idletasks()

            source = self._request_text(f"{REPO_RAW_BASE}/{app_path}", timeout=20)
            compile(source, app_path, "exec")

            temp = local_app.with_suffix(".py.tmp")
            temp.write_text(source, encoding="utf-8")
            temp.replace(local_app)

            local_config = local_dir / "config.json"
            local_config.write_text(config_text, encoding="utf-8")

            self.status.configure(
                text=f"Ejecutando {config.get('name', item.get('name', app_id))} v{config.get('version', '')}..."
            )
            subprocess.Popen(
                [sys.executable, str(local_app)],
                cwd=str(local_dir),
            )
        except Exception as exc:
            messagebox.showerror(APP_SHORT, f"No se pudo iniciar la aplicación:\n\n{exc}")
            self.status.configure(text=f"Error: {exc}")

    def show_app_menu(self, x=None, y=None):
        """Muestra una lista pequeña nativa, igual a un menú de clic derecho."""
        self.load_apps()

        menu = tk.Menu(
            self,
            tearoff=0,
            bg=BG,
            fg=FG,
            activebackground=TEAL,
            activeforeground=WHITE,
            bd=1,
            relief="solid",
        )

        if not self.apps:
            menu.add_command(label="No hay aplicaciones disponibles", state="disabled")
        else:
            for item in self.apps:
                name = item.get("name", item.get("id", "App"))
                menu.add_command(
                    label=name,
                    command=lambda app_item=item: self.launch_app(app_item),
                )

        menu.add_separator()
        menu.add_command(label="Recargar aplicaciones", command=self.load_apps)
        menu.add_command(label="Abrir AMDEV", command=self.show_main)
        menu.add_separator()
        menu.add_command(label="Salir", command=self.exit_app)

        if x is None or y is None:
            x = self.floating.winfo_rootx()
            y = self.floating.winfo_rooty()

        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def hide_app_menu(self):
        # Se mantiene por compatibilidad con llamadas existentes.
        pass

    def toggle_main(self):
        if self.state() == "withdrawn":
            self.show_main()
        else:
            self.hide_main()

    def show_main(self):
        self.hide_app_menu()
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.after(120, lambda: self.attributes("-topmost", False))
        self.load_apps()

    def hide_main(self):
        self.withdraw()

    def exit_app(self):
        try:
            self.floating.destroy()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    app = AMDEVApp()
    app.mainloop()
