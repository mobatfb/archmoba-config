# ARGUMENTOS: visor web navegador internet url pagina html texto enlaces historial favoritos zoom seguro
import json
import os
import queue
import re
import ssl
import threading
import tkinter as tk
import tkinter.font as tkfont
from html.parser import HTMLParser
from pathlib import Path
from tkinter import ttk
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urljoin, urlparse
from urllib.request import Request, urlopen

TOOL_NAME = "Visor Web"
TOOL_DESCRIPTION = (
    "Visor web seguro integrado en PTM. Muestra paginas como contenido "
    "estructurado con titulos, texto y enlaces clicables."
)
TOOL_VERSION = "1.0.2"

HOME_URL = "https://www.wikipedia.org/"
SEARCH_URL = "https://html.duckduckgo.com/html/?q={query}"
MAX_DOWNLOAD_BYTES = 4 * 1024 * 1024


class _SafeHTMLParser(HTMLParser):
    BLOCK_TAGS = {
        "p", "div", "section", "article", "header", "footer", "main",
        "aside", "nav", "blockquote", "pre", "table", "tr", "ul", "ol",
        "dl", "figure", "figcaption",
    }
    HEADING_TAGS = {"h1": "h1", "h2": "h2", "h3": "h3", "h4": "h3", "h5": "h3", "h6": "h3"}

    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.parts = []
        self.main_parts = []
        self.title = ""
        self._in_title = False
        self._skip_depth = 0
        self._main_depth = 0
        self._element_stack = []
        self._style_stack = ["body"]
        self._href_stack = [None]

    def _style(self):
        return self._style_stack[-1] if self._style_stack else "body"

    def _href(self):
        return self._href_stack[-1] if self._href_stack else None

    def _append(self, text, style=None, href=None):
        if not text:
            return
        part = (
            text,
            style or self._style(),
            href if href is not None else self._href(),
        )
        self.parts.append(part)
        if self._main_depth > 0:
            self.main_parts.append(part)

    def _newline(self, count=1):
        if not self.parts:
            return
        current = "".join(part[0] for part in self.parts[-3:])
        have = len(current) - len(current.rstrip("\n"))
        need = max(0, count - have)
        if need:
            part = ("\n" * need, "body", None)
            self.parts.append(part)
            if self._main_depth > 0:
                self.main_parts.append(part)

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = dict(attrs)

        if tag in {"script", "style", "noscript", "template", "svg"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return

        if tag == "title":
            self._in_title = True
            return

        # Los sitios modernos suelen separar el contenido útil con <main>,
        # <article> o role="main". Guardamos ese flujo por separado para
        # evitar mostrar primero cabeceras, menús y navegación lateral.
        is_main_container = (
            tag in {"main", "article"}
            or str(attrs.get("role", "")).strip().lower() == "main"
        )
        if tag not in {
            "area", "base", "br", "col", "embed", "hr", "img",
            "input", "link", "meta", "param", "source", "track", "wbr",
        }:
            self._element_stack.append((tag, is_main_container))

        if is_main_container:
            self._main_depth += 1

        if tag in self.HEADING_TAGS:
            self._newline(2)
            self._style_stack.append(self.HEADING_TAGS[tag])
        elif tag == "a":
            href = attrs.get("href", "").strip()
            resolved = urljoin(self.base_url, href) if href else None
            self._href_stack.append(resolved)
            self._style_stack.append("link")
        elif tag == "strong" or tag == "b":
            self._style_stack.append("bold")
        elif tag == "em" or tag == "i":
            self._style_stack.append("italic")
        elif tag == "code":
            self._style_stack.append("code")
        elif tag == "pre":
            self._newline(1)
            self._style_stack.append("code")
        elif tag == "br":
            self._newline(1)
        elif tag == "li":
            self._newline(1)
            self._append("• ", "body", None)
        elif tag == "img":
            alt = (attrs.get("alt") or "").strip()
            if alt:
                self._append(f"[Imagen: {alt}]", "muted", None)
        elif tag == "hr":
            self._newline(1)
            self._append("────────────────────────────────────────", "muted", None)
            self._newline(1)
        elif tag in self.BLOCK_TAGS:
            self._newline(1)
        elif tag in {"td", "th"}:
            if self.parts:
                self._append("   ", "body", None)

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag in {"script", "style", "noscript", "template", "svg"}:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return

        if tag == "title":
            self._in_title = False
            return

        if tag in self.HEADING_TAGS:
            if len(self._style_stack) > 1:
                self._style_stack.pop()
            self._newline(2)
        elif tag == "a":
            if len(self._href_stack) > 1:
                self._href_stack.pop()
            if len(self._style_stack) > 1:
                self._style_stack.pop()
        elif tag in {"strong", "b", "em", "i", "code", "pre"}:
            if len(self._style_stack) > 1:
                self._style_stack.pop()
            if tag == "pre":
                self._newline(1)
        elif tag == "li":
            self._newline(1)
        elif tag in self.BLOCK_TAGS:
            self._newline(1)
        elif tag == "tr":
            self._newline(1)

        # Cerrar correctamente el contexto main/article/role=main aunque
        # existan muchos contenedores del mismo tipo anidados.
        if self._element_stack:
            match_index = None
            for i in range(len(self._element_stack) - 1, -1, -1):
                if self._element_stack[i][0] == tag:
                    match_index = i
                    break

            if match_index is not None:
                closing = self._element_stack[match_index:]
                del self._element_stack[match_index:]
                for _name, entered_main in closing:
                    if entered_main:
                        self._main_depth = max(0, self._main_depth - 1)

    def handle_data(self, data):
        if self._skip_depth:
            return

        if self._in_title:
            self.title += data
            return

        if self._style() == "code":
            text = data
        else:
            text = re.sub(r"[ \t\r\f\v]+", " ", data)
            text = re.sub(r"\n+", " ", text)

        if not text:
            return

        if self.parts:
            previous = self.parts[-1][0]
            if (
                text.startswith(" ")
                and previous.endswith((" ", "\n", "\t"))
            ):
                text = text.lstrip(" ")

        self._append(text)

    def document(self):
        title = re.sub(r"\s+", " ", self.title).strip()

        # Preferir el contenido principal cuando exista y tenga sustancia.
        # Esto elimina de la vista inicial menús, barras laterales y pie.
        main_text = "".join(part[0] for part in self.main_parts)
        main_text = re.sub(r"\s+", " ", main_text).strip()
        if len(main_text) >= 120:
            return title, self.main_parts

        return title, self.parts


class WebViewerTool(ttk.Frame):
    def __init__(self, parent, app=None):
        super().__init__(parent)
        self.app = app
        self._alive = True
        self._events = queue.Queue()
        self._request_id = 0

        self.address_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Listo")
        self.title_var = tk.StringVar(value="Visor Web")
        self.zoom_var = tk.StringVar(value="100%")

        self.history = []
        self.history_index = -1
        self.favorites = []
        self.zoom_level = 1.0
        self._last_url = ""
        self._current_parts = []
        self._current_title = "Visor Web"

        self._state_path = self._get_state_path()
        self._load_state()
        self._build_ui()
        self._configure_text_tags()
        self._refresh_favorites_menu()
        self._update_nav_buttons()
        self.after(80, self._poll_events)

        start_url = self._last_url or HOME_URL
        self.after(150, lambda: self.navigate(start_url, record=True))

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

        favorites = data.get("favorites", [])
        if isinstance(favorites, list):
            self.favorites = [
                str(item).strip()
                for item in favorites
                if str(item).strip()
            ][:30]

        self._last_url = str(data.get("last_url", "") or "").strip()

        try:
            self.zoom_level = max(
                0.6,
                min(1.8, float(data.get("zoom", 1.0))),
            )
        except Exception:
            self.zoom_level = 1.0

    def _save_state(self):
        try:
            self._state_path.write_text(
                json.dumps(
                    {
                        "favorites": self.favorites[:30],
                        "last_url": self.address_var.get().strip(),
                        "zoom": self.zoom_level,
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    # ---------- UI ----------
    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        toolbar = ttk.Frame(self, padding=(8, 7, 8, 4))
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

        ttk.Label(toolbar, text="URL:").grid(
            row=0, column=4, padx=(7, 5)
        )

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
            secondary, text="Favoritos ▾"
        )
        self.favorites_btn.grid(row=0, column=1, padx=(0, 8))
        self.favorites_menu = tk.Menu(self.favorites_btn, tearoff=0)
        self.favorites_btn.configure(menu=self.favorites_menu)

        ttk.Label(
            secondary,
            textvariable=self.title_var,
            anchor="w",
        ).grid(row=0, column=2, sticky="ew", padx=(4, 8))

        ttk.Button(
            secondary,
            text="−",
            width=3,
            command=lambda: self.change_zoom(-0.1),
        ).grid(row=0, column=3, padx=2)

        ttk.Label(
            secondary,
            textvariable=self.zoom_var,
            width=6,
            anchor="center",
        ).grid(row=0, column=4, padx=2)

        ttk.Button(
            secondary,
            text="+",
            width=3,
            command=lambda: self.change_zoom(0.1),
        ).grid(row=0, column=5, padx=2)

        ttk.Button(
            secondary,
            text="100%",
            command=self.reset_zoom,
        ).grid(row=0, column=6, padx=(3, 0))

        content = ttk.Frame(self, padding=(8, 0, 8, 0))
        content.grid(row=2, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)

        self.text = tk.Text(
            content,
            wrap="word",
            relief="flat",
            bd=0,
            padx=18,
            pady=14,
            cursor="arrow",
            undo=False,
            state="disabled",
        )
        self.text.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(
            content,
            orient="vertical",
            command=self.text.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scrollbar.set)

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
            text="Modo seguro · HTML como texto estructurado",
        ).grid(row=0, column=1, padx=(8, 0))

        self.address_var.trace_add(
            "write", lambda *_: self._update_clear_button()
        )
        self._update_clear_button()
        self._update_zoom_text()

    def _configure_text_tags(self):
        base = max(8, int(round(11 * self.zoom_level)))
        family = "Segoe UI"

        self.font_body = tkfont.Font(
            family=family, size=base
        )
        self.font_bold = tkfont.Font(
            family=family, size=base, weight="bold"
        )
        self.font_italic = tkfont.Font(
            family=family, size=base, slant="italic"
        )
        self.font_h1 = tkfont.Font(
            family=family,
            size=max(base + 7, int(round(base * 1.65))),
            weight="bold",
        )
        self.font_h2 = tkfont.Font(
            family=family,
            size=max(base + 4, int(round(base * 1.38))),
            weight="bold",
        )
        self.font_h3 = tkfont.Font(
            family=family,
            size=max(base + 2, int(round(base * 1.18))),
            weight="bold",
        )
        self.font_code = tkfont.Font(
            family="Consolas",
            size=max(8, base - 1),
        )

        self.text.configure(font=self.font_body)
        self.text.tag_configure("body", font=self.font_body)
        self.text.tag_configure("bold", font=self.font_bold)
        self.text.tag_configure("italic", font=self.font_italic)
        self.text.tag_configure("h1", font=self.font_h1, spacing1=10, spacing3=8)
        self.text.tag_configure("h2", font=self.font_h2, spacing1=9, spacing3=6)
        self.text.tag_configure("h3", font=self.font_h3, spacing1=7, spacing3=5)
        self.text.tag_configure("code", font=self.font_code, background="#F4F4F4")
        self.text.tag_configure("muted", foreground="#666666")
        self.text.tag_configure("link", foreground="#0563C1", underline=True)

    # ---------- Direcciones ----------
    def _normalize_address(self, raw):
        value = str(raw or "").strip()
        if not value:
            return ""

        lower = value.lower()
        if lower.startswith(("http://", "https://")):
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
        try:
            self.clear_btn.configure(
                state=("normal" if self.address_var.get() else "disabled")
            )
        except Exception:
            pass

    # ---------- Navegacion ----------
    def navigate(self, raw_url, record=True):
        target = self._normalize_address(raw_url)
        if not target:
            self.address_entry.focus_set()
            return

        parsed = urlparse(target)
        if parsed.scheme not in {"http", "https"}:
            self.status_var.set("Solo se permiten direcciones http:// y https://")
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

        self._request_id += 1
        request_id = self._request_id
        self.address_var.set(target)
        self.title_var.set("Visor Web")
        self.status_var.set("Cargando...")
        self._show_loading(target)
        self._update_nav_buttons()

        threading.Thread(
            target=self._download_worker,
            args=(request_id, target),
            daemon=True,
        ).start()

    def _download_worker(self, request_id, target):
        try:
            request = Request(
                target,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/124 Safari/537.36"
                    ),
                    "Accept": "text/html,text/plain;q=0.9,*/*;q=0.5",
                    "Accept-Language": "es,en;q=0.8",
                    "Connection": "close",
                },
            )

            context = ssl.create_default_context()
            with urlopen(
                request,
                timeout=15,
                context=context,
            ) as response:
                final_url = response.geturl()
                content_type = response.headers.get_content_type()
                charset = response.headers.get_content_charset() or "utf-8"

                raw = response.read(MAX_DOWNLOAD_BYTES + 1)
                truncated = len(raw) > MAX_DOWNLOAD_BYTES
                raw = raw[:MAX_DOWNLOAD_BYTES]

            try:
                text = raw.decode(charset, errors="replace")
            except LookupError:
                text = raw.decode("utf-8", errors="replace")

            if content_type in {"text/html", "application/xhtml+xml"}:
                parser = _SafeHTMLParser(final_url)
                parser.feed(text)
                parser.close()
                title, parts = parser.document()
            elif content_type.startswith("text/") or content_type in {
                "application/json",
                "application/xml",
            }:
                title = final_url
                parts = [(text, "code", None)]
            else:
                title = final_url
                parts = [
                    (
                        "Este recurso no es una pagina de texto que el visor "
                        f"seguro pueda mostrar. Tipo recibido: {content_type}",
                        "body",
                        None,
                    )
                ]

            self._events.put(
                (
                    "loaded",
                    request_id,
                    {
                        "url": final_url,
                        "title": title or final_url,
                        "parts": parts,
                        "truncated": truncated,
                    },
                )
            )
        except HTTPError as exc:
            self._events.put(
                (
                    "error",
                    request_id,
                    f"Error HTTP {exc.code}: {exc.reason}",
                )
            )
        except URLError as exc:
            self._events.put(
                (
                    "error",
                    request_id,
                    f"No se pudo conectar: {exc.reason}",
                )
            )
        except Exception as exc:
            self._events.put(
                (
                    "error",
                    request_id,
                    f"No se pudo abrir la pagina: {exc}",
                )
            )

    def _poll_events(self):
        if not self._alive:
            return

        try:
            while True:
                kind, request_id, payload = self._events.get_nowait()
                if request_id != self._request_id:
                    continue

                if kind == "loaded":
                    self._apply_document(payload)
                else:
                    self._show_error(str(payload))
        except queue.Empty:
            pass

        try:
            self.after(80, self._poll_events)
        except tk.TclError:
            pass

    def _apply_document(self, payload):
        final_url = payload["url"]
        title = payload["title"]
        parts = payload["parts"]

        self.address_var.set(final_url)
        self._last_url = final_url
        self._current_title = title
        self._current_parts = parts

        if 0 <= self.history_index < len(self.history):
            self.history[self.history_index] = final_url

        self.title_var.set(title[:90])
        self._render_document()

        if payload.get("truncated"):
            self.status_var.set(
                "Listo · contenido limitado a 4 MB por seguridad"
            )
        else:
            self.status_var.set("Listo")

        self._update_nav_buttons()
        self._update_favorite_button()
        self._save_state()

    def _render_document(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")

        for index, (value, style, href) in enumerate(self._current_parts):
            if not value:
                continue

            if href:
                tag_name = f"link_{index}"
                self.text.insert("end", value, ("link", tag_name))
                self.text.tag_configure(tag_name)
                self.text.tag_bind(
                    tag_name,
                    "<Enter>",
                    lambda _e: self.text.configure(cursor="hand2"),
                )
                self.text.tag_bind(
                    tag_name,
                    "<Leave>",
                    lambda _e: self.text.configure(cursor="arrow"),
                )
                self.text.tag_bind(
                    tag_name,
                    "<Button-1>",
                    lambda _e, url=href: self.navigate(url, record=True),
                )
            else:
                self.text.insert("end", value, (style or "body",))

        self.text.configure(state="disabled")
        self.text.yview_moveto(0)

    def _show_loading(self, target):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("end", "Cargando pagina...\n\n", ("h2",))
        self.text.insert("end", target, ("muted",))
        self.text.configure(state="disabled")

    def _show_error(self, message):
        self.status_var.set(message)
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("end", "No se pudo abrir la pagina\n\n", ("h2",))
        self.text.insert("end", message, ("body",))
        self.text.configure(state="disabled")
        self._update_nav_buttons()

    def go_back(self):
        if self.history_index <= 0:
            return
        self.history_index -= 1
        self.navigate(self.history[self.history_index], record=False)

    def go_forward(self):
        if self.history_index >= len(self.history) - 1:
            return
        self.history_index += 1
        self.navigate(self.history[self.history_index], record=False)

    def go_home(self):
        self.navigate(HOME_URL, record=True)

    def reload_page(self):
        current = self.address_var.get().strip()
        if current:
            self.navigate(current, record=False)

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

    # ---------- Favoritos ----------
    def toggle_favorite(self):
        url = self.address_var.get().strip()
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
        url = self.address_var.get().strip()
        self.favorite_btn.configure(
            text=("★ Favorito" if url in self.favorites else "☆ Favorito")
        )

    def _refresh_favorites_menu(self):
        self.favorites_menu.delete(0, "end")

        if not self.favorites:
            self.favorites_menu.add_command(
                label="Sin favoritos",
                state="disabled",
            )
            return

        for url in self.favorites:
            label = url if len(url) <= 55 else url[:52] + "..."
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
            0.6,
            min(1.8, round(self.zoom_level + delta, 2)),
        )
        self._configure_text_tags()
        self._update_zoom_text()
        if self._current_parts:
            current_y = self.text.yview()[0]
            self._render_document()
            self.text.yview_moveto(current_y)
        self._save_state()

    def reset_zoom(self):
        self.zoom_level = 1.0
        self._configure_text_tags()
        self._update_zoom_text()
        if self._current_parts:
            current_y = self.text.yview()[0]
            self._render_document()
            self.text.yview_moveto(current_y)
        self._save_state()

    def _update_zoom_text(self):
        self.zoom_var.set(f"{int(round(self.zoom_level * 100))}%")

    # ---------- Ciclo PTM ----------
    def on_show(self):
        self._update_nav_buttons()

    def on_hide(self):
        self._save_state()

    def on_close(self):
        self._alive = False
        self._request_id += 1
        self._save_state()


App = WebViewerTool


if __name__ == "__main__":
    root = tk.Tk()
    root.title(TOOL_NAME)
    root.geometry("1000x680")
    root.minsize(720, 480)
    WebViewerTool(root).pack(fill="both", expand=True)
    root.mainloop()
