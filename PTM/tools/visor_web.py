# ARGUMENTOS: visor web navegador internet edge webview2 chromium google youtube javascript css historial favoritos zoom
import ctypes
import importlib
import json
import os
import queue
import secrets
import subprocess
import sys
import threading
import time
import tkinter as tk
from multiprocessing.connection import Client, Listener
from pathlib import Path
from tkinter import ttk
from urllib.parse import quote_plus

TOOL_NAME = "Visor Web"
TOOL_DESCRIPTION = (
    "Navegador web real integrado en PTM con Edge WebView2/Chromium, "
    "JavaScript, CSS, imagenes, historial del navegador, favoritos y zoom."
)
TOOL_VERSION = "2.0.3"

HOME_URL = "https://www.google.com/"
SEARCH_URL = "https://www.google.com/search?q={query}"
CHILD_FLAG = "--ptm-webview-child"


# ---------------------------------------------------------------------------
# Proceso hijo aislado: pywebview + Edge WebView2
# ---------------------------------------------------------------------------
def _child_send(conn, payload):
    try:
        conn.send(payload)
        return True
    except Exception:
        return False


def _browser_child(port, auth_hex, window_title, start_url, storage_dir):
    conn = None
    window = None

    try:
        conn = Client(
            ("127.0.0.1", int(port)),
            authkey=bytes.fromhex(auth_hex),
        )
        _child_send(conn, {"type": "starting"})

        webview = importlib.import_module("webview")

        window = webview.create_window(
            window_title,
            url=start_url,
            width=900,
            height=620,
            min_size=(240, 180),
            x=-32000,
            y=-32000,
            hidden=False,
            frameless=True,
            easy_drag=False,
            shadow=False,
            focus=True,
            text_select=True,
            zoomable=True,
            background_color="#FFFFFF",
        )

        state = {
            "alive": True,
            "zoom": 1.0,
            "last_url": "",
            "last_title": "",
            "last_loaded_url": "",
        }

        def browser_loop():
            form_hwnd = 0
            webview_hwnd = 0
            deadline = time.monotonic() + 10.0

            while state["alive"] and time.monotonic() < deadline:
                try:
                    native = window.native
                    if native is not None:
                        form_hwnd = int(native.Handle.ToInt32())
                        native_webview = getattr(native, "webview", None)
                        if native_webview is not None:
                            webview_hwnd = int(native_webview.Handle.ToInt32())
                        if form_hwnd:
                            break
                except Exception:
                    pass
                time.sleep(0.05)

            _child_send(
                conn,
                {
                    "type": "ready",
                    "renderer": "edgechromium",
                    "title": window_title,
                    "form_hwnd": form_hwnd,
                    "webview_hwnd": webview_hwnd,
                },
            )

            last_report = 0.0

            while state["alive"]:
                try:
                    if conn.poll(0.08):
                        message = conn.recv()
                        if not isinstance(message, dict):
                            continue

                        command = str(message.get("cmd", "")).lower()

                        if command == "navigate":
                            url = str(message.get("url", "") or "").strip()
                            if url:
                                window.load_url(url)

                        elif command == "back":
                            try:
                                window.run_js("history.back();")
                            except Exception:
                                pass

                        elif command == "forward":
                            try:
                                window.run_js("history.forward();")
                            except Exception:
                                pass

                        elif command == "reload":
                            try:
                                window.run_js("location.reload();")
                            except Exception:
                                current = window.get_current_url()
                                if current:
                                    window.load_url(current)

                        elif command == "zoom":
                            try:
                                zoom = float(message.get("factor", 1.0))
                            except Exception:
                                zoom = 1.0
                            state["zoom"] = max(0.5, min(2.0, zoom))
                            percent = int(round(state["zoom"] * 100))
                            try:
                                window.run_js(
                                    "document.documentElement.style.zoom="
                                    + repr(str(percent) + "%")
                                    + ";"
                                )
                            except Exception:
                                pass

                        elif command == "focus":
                            try:
                                native = window.native
                                native_webview = getattr(native, "webview", None)
                                if native is not None and native_webview is not None:
                                    from System import Action

                                    def apply_focus():
                                        try:
                                            native.Activate()
                                        except Exception:
                                            pass
                                        try:
                                            native_webview.Focus()
                                        except Exception:
                                            pass

                                    native.BeginInvoke(Action(apply_focus))
                            except Exception:
                                pass

                        elif command == "close":
                            state["alive"] = False
                            try:
                                window.destroy()
                            except Exception:
                                pass
                            break

                    now = time.monotonic()
                    if now - last_report >= 0.45:
                        last_report = now

                        try:
                            current_url = str(
                                window.get_current_url() or ""
                            ).strip()
                        except Exception:
                            current_url = ""

                        current_title = ""
                        page_loaded = False
                        try:
                            page_loaded = bool(window.events.loaded.is_set())
                        except Exception:
                            pass

                        if page_loaded:
                            try:
                                current_title = str(
                                    window.evaluate_js("document.title") or ""
                                ).strip()
                            except Exception:
                                pass

                        url_changed = current_url != state["last_url"]
                        title_changed = current_title != state["last_title"]

                        if url_changed and page_loaded:
                            percent = int(round(state["zoom"] * 100))
                            try:
                                window.run_js(
                                    "document.documentElement.style.zoom="
                                    + repr(str(percent) + "%")
                                    + ";"
                                )
                            except Exception:
                                pass

                        if url_changed or title_changed:
                            state["last_url"] = current_url
                            state["last_title"] = current_title
                            _child_send(
                                conn,
                                {
                                    "type": "state",
                                    "url": current_url,
                                    "title": current_title,
                                },
                            )

                        if (
                            page_loaded
                            and current_url
                            and current_url != state["last_loaded_url"]
                        ):
                            state["last_loaded_url"] = current_url
                            _child_send(
                                conn,
                                {
                                    "type": "loaded",
                                    "url": current_url,
                                    "title": current_title,
                                },
                            )

                except (EOFError, OSError):
                    state["alive"] = False
                    try:
                        window.destroy()
                    except Exception:
                        pass
                    break
                except Exception as exc:
                    _child_send(
                        conn,
                        {
                            "type": "warning",
                            "message": str(exc),
                        },
                    )
                    time.sleep(0.12)

        try:
            webview.start(
                func=browser_loop,
                gui="edgechromium",
                debug=False,
                private_mode=False,
                storage_path=storage_dir,
            )
        except Exception as exc:
            _child_send(
                conn,
                {
                    "type": "error",
                    "message": (
                        "No se pudo iniciar Edge WebView2. "
                        + str(exc)
                    ),
                },
            )

    except Exception as exc:
        if conn is not None:
            _child_send(
                conn,
                {
                    "type": "error",
                    "message": str(exc),
                },
            )
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Herramienta PTM
# ---------------------------------------------------------------------------
class WebViewerTool(ttk.Frame):
    def __init__(self, parent, app=None):
        super().__init__(parent)
        self.app = app

        self.address_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Preparando Edge WebView2...")
        self.title_var = tk.StringVar(value="Visor Web")
        self.zoom_var = tk.StringVar(value="100%")

        self.favorites = []
        self.zoom_level = 1.0
        self._last_url = HOME_URL

        self._alive = True
        self._listener = None
        self._conn = None
        self._process = None
        self._ipc_queue = queue.Queue()
        self._send_lock = threading.Lock()

        self._child_hwnd = 0
        self._webview_hwnd = 0
        self._embedded = False
        self._embed_attempts = 0
        self._resize_job = None
        self._last_left_button_down = False

        self._token = secrets.token_hex(8)
        self._child_title = "PTM_WEBVIEW_" + self._token
        self._authkey = secrets.token_bytes(24)

        self._state_path = self._get_state_path()
        self._storage_dir = str(self._get_storage_dir())
        self._load_state()

        self._build_ui()
        self.after(80, self._poll_ipc)
        self.after(120, self._poll_browser_focus_click)
        self.after(180, self._start_browser_process)

    # ---------- Estado ----------
    def _get_base_dir(self):
        local = os.environ.get("LOCALAPPDATA")
        if local:
            base = Path(local) / "ARCHMOBA" / "PTM" / "visor_web"
        else:
            base = Path.home() / ".archmoba" / "PTM" / "visor_web"
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _get_state_path(self):
        return self._get_base_dir() / "state.json"

    def _get_storage_dir(self):
        path = self._get_base_dir() / "webview2_data"
        path.mkdir(parents=True, exist_ok=True)
        return path

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
            ][:40]

        last_url = str(data.get("last_url", "") or "").strip()
        if last_url:
            self._last_url = last_url

        try:
            self.zoom_level = max(
                0.5,
                min(2.0, float(data.get("zoom", 1.0))),
            )
        except Exception:
            self.zoom_level = 1.0

    def _save_state(self):
        try:
            self._state_path.write_text(
                json.dumps(
                    {
                        "favorites": self.favorites[:40],
                        "last_url": self.address_var.get().strip()
                        or self._last_url,
                        "zoom": self.zoom_level,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    # ---------- UI ----------
    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        toolbar = ttk.Frame(self, padding=(7, 6, 7, 4))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(5, weight=1)

        self.back_btn = ttk.Button(
            toolbar, text="←", width=3, command=lambda: self._send({"cmd": "back"})
        )
        self.back_btn.grid(row=0, column=0, padx=(0, 3))

        self.forward_btn = ttk.Button(
            toolbar, text="→", width=3, command=lambda: self._send({"cmd": "forward"})
        )
        self.forward_btn.grid(row=0, column=1, padx=3)

        self.reload_btn = ttk.Button(
            toolbar, text="↻", width=3, command=lambda: self._send({"cmd": "reload"})
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

        secondary = ttk.Frame(self, padding=(7, 0, 7, 5))
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

        self.favorites_menu = tk.Menu(
            self.favorites_btn,
            tearoff=0,
        )
        self.favorites_btn.configure(menu=self.favorites_menu)
        self._refresh_favorites_menu()

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

        self.browser_host = tk.Frame(
            self,
            bg="white",
            bd=0,
            highlightthickness=0,
        )
        self.browser_host.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=7,
        )
        self.browser_host.grid_propagate(False)

        self.placeholder = ttk.Frame(self.browser_host)
        self.placeholder.place(
            relx=0,
            rely=0,
            relwidth=1,
            relheight=1,
        )

        self.placeholder.columnconfigure(0, weight=1)
        self.placeholder.rowconfigure(0, weight=1)

        center = ttk.Frame(self.placeholder)
        center.grid(row=0, column=0)

        ttk.Label(
            center,
            text="Visor Web",
            font=("Segoe UI", 15, "bold"),
        ).pack(pady=(0, 7))

        self.placeholder_status = ttk.Label(
            center,
            text="Iniciando Edge WebView2...",
        )
        self.placeholder_status.pack()

        self.retry_btn = ttk.Button(
            center,
            text="Reintentar",
            command=self._restart_browser,
        )

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
            text="Edge WebView2 · proceso aislado",
        ).grid(row=0, column=1, padx=(8, 0))

        self.address_var.trace_add(
            "write",
            lambda *_: self._update_clear_button(),
        )
        self.browser_host.bind(
            "<Configure>",
            self._on_host_configure,
            add="+",
        )

        self._update_clear_button()
        self._update_zoom_text()

    # ---------- Proceso/IPC ----------
    def _windowless_python(self):
        executable = Path(sys.executable)
        if os.name == "nt" and executable.name.lower() == "python.exe":
            candidate = executable.with_name("pythonw.exe")
            if candidate.exists():
                return str(candidate)
        return str(executable)

    def _start_browser_process(self):
        if not self._alive:
            return

        if os.name != "nt":
            self._show_browser_error(
                "Visor Web 2.0 requiere Windows y Microsoft Edge WebView2."
            )
            return

        if self._process is not None and self._process.poll() is None:
            return

        self.status_var.set("Iniciando Edge WebView2...")
        self.placeholder_status.configure(
            text="Iniciando Edge WebView2..."
        )
        self.retry_btn.pack_forget()
        self.placeholder.place(
            relx=0,
            rely=0,
            relwidth=1,
            relheight=1,
        )

        try:
            self._listener = Listener(
                ("127.0.0.1", 0),
                authkey=self._authkey,
            )
            port = int(self._listener.address[1])

            command = [
                self._windowless_python(),
                str(Path(__file__).resolve()),
                CHILD_FLAG,
                str(port),
                self._authkey.hex(),
                self._child_title,
                self._last_url or HOME_URL,
                self._storage_dir,
            ]

            kwargs = {}
            if os.name == "nt":
                kwargs["creationflags"] = int(
                    getattr(subprocess, "CREATE_NO_WINDOW", 0)
                )

            self._process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **kwargs,
            )

            threading.Thread(
                target=self._accept_child,
                daemon=True,
            ).start()

        except Exception as exc:
            self._show_browser_error(
                "No se pudo iniciar el proceso WebView2: " + str(exc)
            )

    def _accept_child(self):
        listener = self._listener
        if listener is None:
            return

        try:
            conn = listener.accept()
            self._conn = conn
            self._ipc_queue.put(
                {"type": "connected"}
            )

            while self._alive:
                try:
                    if conn.poll(0.2):
                        message = conn.recv()
                        if isinstance(message, dict):
                            self._ipc_queue.put(message)
                except (EOFError, OSError):
                    break
                except Exception as exc:
                    self._ipc_queue.put(
                        {
                            "type": "warning",
                            "message": str(exc),
                        }
                    )
                    break
        except Exception as exc:
            if self._alive:
                self._ipc_queue.put(
                    {
                        "type": "error",
                        "message": (
                            "No se pudo conectar con WebView2: "
                            + str(exc)
                        ),
                    }
                )
        finally:
            try:
                listener.close()
            except Exception:
                pass

    def _send(self, payload):
        conn = self._conn
        if conn is None:
            return False

        try:
            with self._send_lock:
                conn.send(payload)
            return True
        except Exception:
            return False

    def _poll_ipc(self):
        if not self._alive:
            return

        try:
            while True:
                message = self._ipc_queue.get_nowait()
                self._handle_child_message(message)
        except queue.Empty:
            pass

        if (
            self._process is not None
            and self._process.poll() is not None
            and self._alive
        ):
            exit_code = self._process.poll()
            self._process = None
            was_embedded = self._embedded
            self._embedded = False
            self._child_hwnd = 0
            self._webview_hwnd = 0

            # Si ya recibimos un error explicito, conservar ese mensaje.
            current = self.status_var.get()
            if (
                "No se pudo" not in current
                and "requiere" not in current
                and "cerró" not in current
            ):
                if was_embedded:
                    message = (
                        "El proceso Edge WebView2 se cerró. "
                        "PTM continúa funcionando."
                    )
                else:
                    message = (
                        "Edge WebView2 no pudo iniciar "
                        f"(código {exit_code}). PTM continúa funcionando."
                    )
                self._show_browser_error(message)

        try:
            self.after(90, self._poll_ipc)
        except tk.TclError:
            pass

    def _handle_child_message(self, message):
        kind = str(message.get("type", ""))

        if kind == "starting":
            self.status_var.set("Cargando motor Edge WebView2...")

        elif kind == "ready":
            try:
                self._child_hwnd = int(message.get("form_hwnd", 0) or 0)
            except Exception:
                self._child_hwnd = 0
            try:
                self._webview_hwnd = int(message.get("webview_hwnd", 0) or 0)
            except Exception:
                self._webview_hwnd = 0

            self.status_var.set("Integrando Edge WebView2 en PTM...")
            self._embed_attempts = 0
            self.after(20, self._attempt_embed)

        elif kind == "loaded":
            url = str(message.get("url", "") or "").strip()
            title = str(message.get("title", "") or "").strip()
            if url:
                self._last_url = url
                if self.address_entry.focus_get() is not self.address_entry:
                    self.address_var.set(url)
            if title:
                self.title_var.set(title[:100])
            if self._embedded:
                self.status_var.set("Listo")
            self._update_favorite_button()
            self._save_state()

        elif kind == "state":
            url = str(message.get("url", "") or "").strip()
            title = str(message.get("title", "") or "").strip()

            if url:
                self._last_url = url
                if self.address_entry.focus_get() is not self.address_entry:
                    self.address_var.set(url)

            if title:
                self.title_var.set(title[:100])
            else:
                self.title_var.set("Visor Web")

            if self._embedded:
                self.status_var.set("Listo")

            self._update_favorite_button()
            self._save_state()

        elif kind == "warning":
            if not self._embedded:
                self.status_var.set(
                    str(message.get("message", "Preparando navegador..."))
                )

        elif kind == "error":
            self._show_browser_error(
                str(
                    message.get(
                        "message",
                        "No se pudo iniciar Edge WebView2.",
                    )
                )
            )

    # ---------- Integración Win32 ----------
    def _win_api(self):
        user32 = ctypes.windll.user32

        get_long = getattr(
            user32,
            "GetWindowLongPtrW",
            user32.GetWindowLongW,
        )
        set_long = getattr(
            user32,
            "SetWindowLongPtrW",
            user32.SetWindowLongW,
        )

        get_long.argtypes = [ctypes.c_void_p, ctypes.c_int]
        get_long.restype = ctypes.c_ssize_t

        set_long.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_ssize_t,
        ]
        set_long.restype = ctypes.c_ssize_t

        return user32, get_long, set_long

    def _attempt_embed(self):
        if not self._alive or os.name != "nt":
            return

        try:
            user32, get_long, set_long = self._win_api()

            user32.FindWindowW.argtypes = [
                ctypes.c_wchar_p,
                ctypes.c_wchar_p,
            ]
            user32.FindWindowW.restype = ctypes.c_void_p

            hwnd = ctypes.c_void_p(self._child_hwnd) if self._child_hwnd else None
            if not hwnd:
                hwnd = user32.FindWindowW(
                    None,
                    self._child_title,
                )

            if not hwnd:
                self._embed_attempts += 1
                if self._embed_attempts < 80:
                    self.after(50, self._attempt_embed)
                else:
                    self._show_browser_error(
                        "WebView2 inició, pero PTM no pudo encontrar su ventana."
                    )
                return

            parent_hwnd = ctypes.c_void_p(
                int(self.browser_host.winfo_id())
            )

            GWL_STYLE = -16
            WS_CHILD = 0x40000000
            WS_VISIBLE = 0x10000000
            WS_POPUP = 0x80000000
            WS_CAPTION = 0x00C00000
            WS_THICKFRAME = 0x00040000
            WS_SYSMENU = 0x00080000
            WS_MINIMIZEBOX = 0x00020000
            WS_MAXIMIZEBOX = 0x00010000
            WS_CLIPSIBLINGS = 0x04000000
            WS_CLIPCHILDREN = 0x02000000

            style = int(
                get_long(
                    ctypes.c_void_p(hwnd),
                    GWL_STYLE,
                )
            )

            style &= ~(
                WS_POPUP
                | WS_CAPTION
                | WS_THICKFRAME
                | WS_SYSMENU
                | WS_MINIMIZEBOX
                | WS_MAXIMIZEBOX
            )
            style |= (
                WS_CHILD
                | WS_VISIBLE
                | WS_CLIPSIBLINGS
                | WS_CLIPCHILDREN
            )

            user32.SetParent(
                ctypes.c_void_p(hwnd),
                parent_hwnd,
            )
            set_long(
                ctypes.c_void_p(hwnd),
                GWL_STYLE,
                style,
            )

            self._child_hwnd = int(hwnd)
            self._embedded = True

            self.placeholder.place_forget()
            self.status_var.set("Listo")
            self._resize_embedded(force=True)

            user32.ShowWindow(
                ctypes.c_void_p(hwnd),
                5,
            )

            self._send(
                {
                    "cmd": "zoom",
                    "factor": self.zoom_level,
                }
            )
            self.after(80, self._focus_embedded_browser)

        except Exception as exc:
            self._show_browser_error(
                "No se pudo incrustar WebView2: " + str(exc)
            )

    def _on_host_configure(self, _event=None):
        if not self._embedded:
            return

        if self._resize_job is not None:
            try:
                self.after_cancel(self._resize_job)
            except Exception:
                pass

        self._resize_job = self.after(
            35,
            self._resize_embedded,
        )

    def _resize_embedded(self, force=False):
        self._resize_job = None

        if not self._embedded or not self._child_hwnd:
            return

        try:
            width = max(1, int(self.browser_host.winfo_width()))
            height = max(1, int(self.browser_host.winfo_height()))

            user32 = ctypes.windll.user32
            SWP_NOZORDER = 0x0004
            SWP_NOACTIVATE = 0x0010
            SWP_FRAMECHANGED = 0x0020
            SWP_SHOWWINDOW = 0x0040

            flags = (
                SWP_NOZORDER
                | SWP_NOACTIVATE
                | SWP_SHOWWINDOW
            )
            if force:
                flags |= SWP_FRAMECHANGED

            user32.SetWindowPos(
                ctypes.c_void_p(self._child_hwnd),
                None,
                0,
                0,
                width,
                height,
                flags,
            )
        except Exception:
            pass

    def _set_embedded_visible(self, visible):
        if not self._child_hwnd or os.name != "nt":
            return

        try:
            ctypes.windll.user32.ShowWindow(
                ctypes.c_void_p(self._child_hwnd),
                5 if visible else 0,
            )
        except Exception:
            pass

    # ---------- Foco teclado Win32 ----------
    def _poll_browser_focus_click(self):
        """Transfiere el foco al WebView2 cuando el usuario hace clic dentro."""
        if not self._alive:
            return

        if os.name == "nt" and self._embedded:
            try:
                user32 = ctypes.windll.user32
                down = bool(user32.GetAsyncKeyState(0x01) & 0x8000)

                if down and not self._last_left_button_down:
                    class POINT(ctypes.Structure):
                        _fields_ = [
                            ("x", ctypes.c_long),
                            ("y", ctypes.c_long),
                        ]

                    point = POINT()
                    if user32.GetCursorPos(ctypes.byref(point)):
                        x0 = int(self.browser_host.winfo_rootx())
                        y0 = int(self.browser_host.winfo_rooty())
                        x1 = x0 + int(self.browser_host.winfo_width())
                        y1 = y0 + int(self.browser_host.winfo_height())

                        if x0 <= point.x < x1 and y0 <= point.y < y1:
                            self._focus_embedded_browser()

                self._last_left_button_down = down
            except Exception:
                pass

        try:
            self.after(35, self._poll_browser_focus_click)
        except tk.TclError:
            pass

    def _focus_embedded_browser(self):
        """Comparte temporalmente las colas de input y da foco al WebView2."""
        if (
            os.name != "nt"
            or not self._embedded
            or not self._child_hwnd
        ):
            return

        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            target_hwnd = int(self._webview_hwnd or self._child_hwnd)
            parent_hwnd = int(self.winfo_toplevel().winfo_id())

            user32.GetWindowThreadProcessId.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_ulong),
            ]
            user32.GetWindowThreadProcessId.restype = ctypes.c_ulong

            parent_pid = ctypes.c_ulong(0)
            child_pid = ctypes.c_ulong(0)

            parent_tid = int(
                user32.GetWindowThreadProcessId(
                    ctypes.c_void_p(parent_hwnd),
                    ctypes.byref(parent_pid),
                )
            )
            child_tid = int(
                user32.GetWindowThreadProcessId(
                    ctypes.c_void_p(target_hwnd),
                    ctypes.byref(child_pid),
                )
            )

            current_tid = int(kernel32.GetCurrentThreadId())
            attach_from = current_tid or parent_tid
            attached = False

            if child_tid and attach_from and child_tid != attach_from:
                try:
                    attached = bool(
                        user32.AttachThreadInput(
                            attach_from,
                            child_tid,
                            True,
                        )
                    )
                except Exception:
                    attached = False

            try:
                try:
                    user32.SetForegroundWindow(
                        ctypes.c_void_p(parent_hwnd)
                    )
                except Exception:
                    pass

                try:
                    user32.SetActiveWindow(
                        ctypes.c_void_p(parent_hwnd)
                    )
                except Exception:
                    pass

                user32.SetFocus(
                    ctypes.c_void_p(target_hwnd)
                )
            finally:
                if attached:
                    try:
                        user32.AttachThreadInput(
                            attach_from,
                            child_tid,
                            False,
                        )
                    except Exception:
                        pass

            # Refuerzo dentro del proceso hijo: enfoca el control WinForms
            # Microsoft.Web.WebView2.WinForms.WebView2.
            self._send({"cmd": "focus"})

        except Exception:
            self._send({"cmd": "focus"})

    # ---------- Navegación ----------
    def _normalize_address(self, raw):
        value = str(raw or "").strip()
        if not value:
            return ""

        lower = value.lower()
        if lower.startswith(("http://", "https://")):
            return value

        if " " in value or "." not in value:
            return SEARCH_URL.format(
                query=quote_plus(value)
            )

        return "https://" + value

    def _address_enter(self, _event=None):
        self.go_address()
        return "break"

    def go_address(self):
        target = self._normalize_address(
            self.address_var.get()
        )
        if not target:
            self.address_entry.focus_set()
            return

        self.address_var.set(target)
        self.status_var.set("Cargando...")
        self._send(
            {
                "cmd": "navigate",
                "url": target,
            }
        )

    def go_home(self):
        self.address_var.set(HOME_URL)
        self.status_var.set("Cargando...")
        self._send(
            {
                "cmd": "navigate",
                "url": HOME_URL,
            }
        )

    def clear_address(self):
        self.address_var.set("")
        try:
            self.address_entry.focus_set()
        except Exception:
            pass

    def _update_clear_button(self):
        try:
            self.clear_btn.configure(
                state=(
                    "normal"
                    if self.address_var.get()
                    else "disabled"
                )
            )
        except Exception:
            pass

    # ---------- Favoritos ----------
    def toggle_favorite(self):
        url = self.address_var.get().strip()
        if not url:
            return

        if url in self.favorites:
            self.favorites.remove(url)
        else:
            self.favorites.append(url)
            self.favorites = self.favorites[-40:]

        self._refresh_favorites_menu()
        self._update_favorite_button()
        self._save_state()

    def _update_favorite_button(self):
        url = self.address_var.get().strip()
        try:
            self.favorite_btn.configure(
                text=(
                    "★ Favorito"
                    if url in self.favorites
                    else "☆ Favorito"
                )
            )
        except Exception:
            pass

    def _refresh_favorites_menu(self):
        self.favorites_menu.delete(0, "end")

        if not self.favorites:
            self.favorites_menu.add_command(
                label="Sin favoritos",
                state="disabled",
            )
            return

        for url in self.favorites:
            label = (
                url
                if len(url) <= 58
                else url[:55] + "..."
            )
            self.favorites_menu.add_command(
                label=label,
                command=lambda u=url: self._navigate_favorite(u),
            )

        self.favorites_menu.add_separator()
        self.favorites_menu.add_command(
            label="Limpiar favoritos",
            command=self.clear_favorites,
        )

    def _navigate_favorite(self, url):
        self.address_var.set(url)
        self._send(
            {
                "cmd": "navigate",
                "url": url,
            }
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
            min(
                2.0,
                round(
                    self.zoom_level + float(delta),
                    2,
                ),
            ),
        )
        self._update_zoom_text()
        self._send(
            {
                "cmd": "zoom",
                "factor": self.zoom_level,
            }
        )
        self._save_state()

    def reset_zoom(self):
        self.zoom_level = 1.0
        self._update_zoom_text()
        self._send(
            {
                "cmd": "zoom",
                "factor": 1.0,
            }
        )
        self._save_state()

    def _update_zoom_text(self):
        self.zoom_var.set(
            f"{int(round(self.zoom_level * 100))}%"
        )

    # ---------- Errores / reinicio ----------
    def _show_browser_error(self, message):
        self._embedded = False
        self._child_hwnd = 0
        self.status_var.set(message)

        try:
            self.placeholder_status.configure(
                text=message,
                wraplength=560,
                justify="center",
            )
            self.placeholder.place(
                relx=0,
                rely=0,
                relwidth=1,
                relheight=1,
            )
            if not self.retry_btn.winfo_manager():
                self.retry_btn.pack(pady=(12, 0))
        except Exception:
            pass

    def _restart_browser(self):
        self._stop_browser()
        self._token = secrets.token_hex(8)
        self._child_title = "PTM_WEBVIEW_" + self._token
        self._authkey = secrets.token_bytes(24)
        self._conn = None
        self._listener = None
        self._process = None
        self._child_hwnd = 0
        self._webview_hwnd = 0
        self._embedded = False
        self._embed_attempts = 0
        self.after(120, self._start_browser_process)

    def _stop_browser(self):
        self._send({"cmd": "close"})

        conn = self._conn
        self._conn = None
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

        listener = self._listener
        self._listener = None
        if listener is not None:
            try:
                listener.close()
            except Exception:
                pass

        process = self._process
        if process is not None:
            try:
                process.wait(timeout=1.2)
            except Exception:
                try:
                    process.terminate()
                except Exception:
                    pass

        self._process = None
        self._child_hwnd = 0
        self._webview_hwnd = 0
        self._embedded = False

    # ---------- Ciclo PTM ----------
    def on_show(self):
        self._set_embedded_visible(True)
        self.after(25, lambda: self._resize_embedded(force=True))
        self.after(90, self._focus_embedded_browser)

    def on_hide(self):
        self._set_embedded_visible(False)
        self._save_state()

    def on_close(self):
        self._alive = False
        self._save_state()
        self._stop_browser()


App = WebViewerTool


def _run_standalone():
    root = tk.Tk()
    root.title(TOOL_NAME)
    root.geometry("1050x720")
    root.minsize(760, 500)

    tool = WebViewerTool(root)
    tool.pack(fill="both", expand=True)

    def close():
        tool.on_close()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == CHILD_FLAG:
        if len(sys.argv) < 7:
            raise SystemExit(2)

        _browser_child(
            sys.argv[2],
            sys.argv[3],
            sys.argv[4],
            sys.argv[5],
            sys.argv[6],
        )
    else:
        _run_standalone()
