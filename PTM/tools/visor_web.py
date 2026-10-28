# ARGUMENTOS: visor web navegador internet url pagina html css wikipedia duckduckgo historial favoritos zoom
import json
import os
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from urllib.parse import quote_plus

from tkinterweb import HtmlFrame

TOOL_NAME = "Visor Web"
TOOL_DESCRIPTION = (
    "Visor web ligero integrado en PTM con barra de direccion, historial, "
    "favoritos, recarga, busqueda y zoom."
)
TOOL_VERSION = "1.0.0"

HOME_URL = "https://www.wikipedia.org/"
SEARCH_URL = "https://html.duckduckgo.com/html/?q={query}"


class WebViewerTool(ttk.Frame):
    def __init__(self, parent, app=None):
        super().__init__(parent)
        self.app = app

        self.address_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Listo")
        self.zoom_var = tk.StringVar(value="100%")
        self.title_var = tk.StringVar(value="Visor Web")

        self.history = []
        self.history_index = -1
        self._history_moving = False
        self._loading = False
        self._last_url = ""

        self.zoom_level = 1.0
        self.favorites = []
        self._state_path = self._get_state_path()
        self._load_state()

        self._build_ui()
        self._build_browser()
        self._update_nav_buttons()

        start_url = self._last_url or HOME_URL
        self.after(120, lambda: self.navigate(start_url, record=True))

    # ---------- Estado ----------
    def _get_state_path(self):
        local = os.environ.get("LOCALAPPDATA")
        if local:
            base = Path(local) / "ARCHMOBA" / "PTM" / "visor_web"
        else:
            base = Path.home() / ".archmoba" / "PTM" / "visor_web"
        base.mkdir(parents=True, exist_ok=True)
        return base / "state.json"

    def _load_state(self):
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
        except Exception:
            return

        saved = data.get("favorites", [])
        if isinstance(saved, list):
            self.favorites = [
                str(item).strip()
                for item in saved
                if str(item).strip()
            ][:30]

        self._last_url = str(data.get("last_url", "") or "").strip()

        try:
            zoom = float(data.get("zoom", 1.0))
            self.zoom_level = max(0.5, min(2.0, zoom))
        except Exception:
            self.zoom_level = 1.0

    def _save_state(self):
        data = {
            "favorites": self.favorites[:30],
            "last_url": self.address_var.get().strip(),
            "zoom": self.zoom_level,
        }
        try:
            self._state_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    # ---------- UI ----------
    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        toolbar = ttk.Frame(self, padding=(8, 7, 8, 5))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(5, weight=1)

        self.back_btn = ttk.Button(
            toolbar, text="←", width=3, command=self.go_back
        )
        self.back_btn.grid(row=0, column=0, padx=(0, 3))

        self.forward_btn = ttk.Button(
            toolbar, text="→", width=3, command=self.go_forward
        )
        self.forward_btn.grid(row=0, column=1, padx=3)

        self.reload_btn = ttk.Button(
            toolbar, text="↻", width=3, command=self.reload_page
        )
        self.reload_btn.grid(row=0, column=2, padx=3)

        ttk.Button(
            toolbar, text="⌂", width=3, command=self.go_home
        ).grid(row=0, column=3, padx=3)

        ttk.Label(toolbar, text="URL:").grid(row=0, column=4, padx=(7, 5))

        address_wrap = ttk.Frame(toolbar)
        address_wrap.grid(row=0, column=5, sticky="ew")
        address_wrap.columnconfigure(0, weight=1)

        self.address_entry = ttk.Entry(
            address_wrap,
            textvariable=self.address_var,
        )
        self.address_entry.grid(row=0, column=0, sticky="ew")
        self.address_entry.bind("<Return>", self._address_enter)

        self.clear_btn = ttk.Button(
            address_wrap,
            text="×",
            width=2,
            command=self.clear_address,
        )
        self.clear_btn.grid(row=0, column=1, padx=(3, 0))

        ttk.Button(
            toolbar, text="Ir", width=4, command=self.go_address
        ).grid(row=0, column=6, padx=(5, 0))

        secondary = ttk.Frame(self, padding=(8, 0, 8, 5))
        secondary.grid(row=1, column=0, sticky="ew")
        secondary.columnconfigure(2, weight=1)

        self.favorite_btn = ttk.Button(
            secondary,
            text="☆ Favorito",
            command=self.toggle_favorite,
        )
        self.favorite_btn.grid(row=0, column=0, padx=(0, 5))

        self.favorites_btn = ttk.Menubutton(
            secondary,
            text="Favoritos ▾",
        )
        self.favorites_btn.grid(row=0, column=1, padx=(0, 8))
        self.favorites_menu = tk.Menu(self.favorites_btn, tearoff=0)
        self.favorites_btn.configure(menu=self.favorites_menu)
        self._refresh_favorites_menu()

        ttk.Label(
            secondary,
            textvariable=self.title_var,
            anchor="w",
        ).grid(row=0, column=2, sticky="ew", padx=(4, 8))

        ttk.Button(
            secondary, text="−", width=3,
            command=lambda: self.change_zoom(-0.1),
        ).grid(row=0, column=3, padx=2)

        ttk.Label(
            secondary,
            textvariable=self.zoom_var,
            width=6,
            anchor="center",
        ).grid(row=0, column=4, padx=2)

        ttk.Button(
            secondary, text="+", width=3,
            command=lambda: self.change_zoom(0.1),
        ).grid(row=0, column=5, padx=2)

        ttk.Button(
            secondary,
            text="100%",
            command=self.reset_zoom,
        ).grid(row=0, column=6, padx=(3, 0))

        self.browser_host = ttk.Frame(self)
        self.browser_host.grid(row=2, column=0, sticky="nsew")
        self.browser_host.columnconfigure(0, weight=1)
        self.browser_host.rowconfigure(0, weight=1)

        status = ttk.Frame(self, padding=(8, 4))
        status.grid(row=3, column=0, sticky="ew")
        status.columnconfigure(0, weight=1)

        ttk.Label(
            status,
            textvariable=self.status_var,
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")

        ttk.Label(
            status,
            text="Visor ligero HTML/CSS",
        ).grid(row=0, column=1, padx=(8, 0))

        self.address_var.trace_add(
            "write", lambda *_: self._update_clear_button()
        )
        self._update_clear_button()

    def _build_browser(self):
        self.browser = HtmlFrame(
            self.browser_host,
            messages_enabled=False,
            vertical_scrollbar="auto",
            horizontal_scrollbar="auto",
            images_enabled=True,
            stylesheets_enabled=True,
            forms_enabled=True,
            objects_enabled=True,
            javascript_enabled=False,
            crash_prevention_enabled=True,
            on_link_click=self._link_clicked,
            on_navigate_fail=self._navigate_failed,
            zoom=self.zoom_level,
        )
        self.browser.grid(row=0, column=0, sticky="nsew")

        self.browser.bind(
            "<<DownloadingResource>>",
            self._loading_started,
            add="+",
        )
        self.browser.bind(
            "<<DoneLoading>>",
            self._loading_done,
            add="+",
        )
        self.browser.bind(
            "<<UrlChanged>>",
            self._url_changed,
            add="+",
        )
        self.browser.bind(
            "<<TitleChanged>>",
            self._title_changed,
            add="+",
        )

        self._update_zoom_text()

    # ---------- Direcciones ----------
    def _normalize_address(self, raw):
        value = str(raw or "").strip()
        if not value:
            return ""

        lower = value.lower()
        if lower.startswith(("http://", "https://", "file://", "view-source:")):
            return value

        if " " in value or "." not in value:
            return SEARCH_URL.format(query=quote_plus(value))

        return "https://" + value

    def _address_enter(self, _event=None):
        self.go_address()
        return "break"

    def go_address(self):
        self.navigate(self.address_var.get(), record=True)

    def clear_address(self):
        self.address_var.set("")
        self.address_entry.focus_set()

    def _update_clear_button(self):
        state = "normal" if self.address_var.get() else "disabled"
        try:
            self.clear_btn.configure(state=state)
        except Exception:
            pass

    # ---------- Navegacion ----------
    def navigate(self, raw_url, record=True):
        target = self._normalize_address(raw_url)
        if not target:
            self.address_entry.focus_set()
            return

        if record:
            if self.history_index < len(self.history) - 1:
                self.history = self.history[: self.history_index + 1]

            if (
                self.history_index < 0
                or not self.history
                or self.history[self.history_index] != target
            ):
                self.history.append(target)
                self.history = self.history[-80:]
                self.history_index = len(self.history) - 1

        self._loading = True
        self.status_var.set("Cargando...")
        self.address_var.set(target)
        self._update_nav_buttons()

        try:
            self.browser.load_url(target)
        except Exception as exc:
            self.status_var.set(f"No se pudo abrir: {exc}")

    def go_back(self):
        if self.history_index <= 0:
            return
        self.history_index -= 1
        self._history_moving = True
        self.navigate(
            self.history[self.history_index],
            record=False,
        )

    def go_forward(self):
        if self.history_index >= len(self.history) - 1:
            return
        self.history_index += 1
        self._history_moving = True
        self.navigate(
            self.history[self.history_index],
            record=False,
        )

    def go_home(self):
        self.navigate(HOME_URL, record=True)

    def reload_page(self):
        self.status_var.set("Recargando...")
        try:
            if hasattr(self.browser, "reload"):
                self.browser.reload()
            else:
                current = self.address_var.get().strip()
                if current:
                    self.browser.load_url(current, force=True)
        except Exception as exc:
            self.status_var.set(f"No se pudo recargar: {exc}")

    def _link_clicked(self, url):
        self.navigate(url, record=True)

    def _update_nav_buttons(self):
        self.back_btn.configure(
            state=("normal" if self.history_index > 0 else "disabled")
        )
        self.forward_btn.configure(
            state=(
                "normal"
                if 0 <= self.history_index < len(self.history) - 1
                else "disabled"
            )
        )

    # ---------- Eventos del motor ----------
    def _loading_started(self, _event=None):
        self._loading = True
        self.status_var.set("Cargando recursos...")

    def _loading_done(self, _event=None):
        self._loading = False
        self._history_moving = False
        current = self._current_url()
        if current:
            self.address_var.set(current)
            self._last_url = current
        self.status_var.set("Listo")
        self._update_nav_buttons()
        self._update_favorite_button()
        self._save_state()

    def _url_changed(self, _event=None):
        current = self._current_url()
        if not current:
            return

        self.address_var.set(current)
        self._last_url = current

        if self._history_moving:
            if 0 <= self.history_index < len(self.history):
                self.history[self.history_index] = current
        else:
            if (
                self.history_index < 0
                or not self.history
                or self.history[self.history_index] != current
            ):
                if self.history_index < len(self.history) - 1:
                    self.history = self.history[: self.history_index + 1]
                self.history.append(current)
                self.history = self.history[-80:]
                self.history_index = len(self.history) - 1

        self._update_nav_buttons()
        self._update_favorite_button()

    def _title_changed(self, _event=None):
        try:
            title = str(self.browser.title or "").strip()
        except Exception:
            title = ""
        self.title_var.set(title or "Visor Web")

    def _navigate_failed(self, url, error=None, code=None):
        message = "No se pudo cargar la pagina"
        if code:
            message += f" ({code})"
        self.status_var.set(message)
        self.address_var.set(str(url or ""))
        return None

    def _current_url(self):
        try:
            return str(self.browser.current_url or "").strip()
        except Exception:
            return self.address_var.get().strip()

    # ---------- Favoritos ----------
    def toggle_favorite(self):
        url = self._current_url()
        if not url:
            return

        if url in self.favorites:
            self.favorites.remove(url)
        else:
            self.favorites.append(url)
            self.favorites = self.favorites[-30:]

        self._refresh_favorites_menu()
        self._update_favorite_button()
        self._save_state()

    def _update_favorite_button(self):
        url = self._current_url()
        if url and url in self.favorites:
            self.favorite_btn.configure(text="★ Favorito")
        else:
            self.favorite_btn.configure(text="☆ Favorito")

    def _refresh_favorites_menu(self):
        self.favorites_menu.delete(0, "end")

        if not self.favorites:
            self.favorites_menu.add_command(
                label="Sin favoritos",
                state="disabled",
            )
            return

        for url in self.favorites:
            label = url
            if len(label) > 55:
                label = label[:52] + "..."
            self.favorites_menu.add_command(
                label=label,
                command=lambda u=url: self.navigate(u, record=True),
            )

        self.favorites_menu.add_separator()
        self.favorites_menu.add_command(
            label="Limpiar favoritos",
            command=self.clear_favorites,
        )

    def clear_favorites(self):
        self.favorites.clear()
        self._refresh_favorites_menu()
        self._update_favorite_button()
        self._save_state()

    # ---------- Zoom ----------
    def change_zoom(self, delta):
        self.zoom_level = max(
            0.5,
            min(2.0, round(self.zoom_level + delta, 2)),
        )
        try:
            self.browser.configure(zoom=self.zoom_level)
        except Exception:
            pass
        self._update_zoom_text()
        self._save_state()

    def reset_zoom(self):
        self.zoom_level = 1.0
        try:
            self.browser.configure(zoom=1.0)
        except Exception:
            pass
        self._update_zoom_text()
        self._save_state()

    def _update_zoom_text(self):
        self.zoom_var.set(f"{int(round(self.zoom_level * 100))}%")

    # ---------- Ciclo PTM ----------
    def on_show(self):
        self._update_nav_buttons()

    def on_hide(self):
        self._save_state()

    def on_close(self):
        self._save_state()
        try:
            self.browser.stop()
        except Exception:
            pass


App = WebViewerTool


if __name__ == "__main__":
    root = tk.Tk()
    root.title(TOOL_NAME)
    root.geometry("1000x680")
    root.minsize(720, 480)
    WebViewerTool(root).pack(fill="both", expand=True)
    root.mainloop()
