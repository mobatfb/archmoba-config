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
TOOL_VERSION = "2.0.9"

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

                        elif command == "text":
                            text_value = str(message.get("text", "") or "")
                            if text_value:
                                payload = json.dumps(text_value)
                                try:
                                    window.run_js(
                                        """
(() => {
  const text = PAYLOAD;
  const el = document.activeElement;
  if (!el) return false;

  const inputLike =
    el instanceof HTMLInputElement ||
    el instanceof HTMLTextAreaElement;

  if (inputLike || el.isContentEditable) {
    try {
      if (document.queryCommandSupported &&
          document.queryCommandSupported('insertText')) {
        if (document.execCommand('insertText', false, text)) {
          return true;
        }
      }
    } catch (_) {}

    if (inputLike) {
      const value = String(el.value || '');
      const start =
        typeof el.selectionStart === 'number'
          ? el.selectionStart
          : value.length;
      const end =
        typeof el.selectionEnd === 'number'
          ? el.selectionEnd
          : start;
      const next = value.slice(0, start) + text + value.slice(end);

      const proto =
        el instanceof HTMLTextAreaElement
          ? HTMLTextAreaElement.prototype
          : HTMLInputElement.prototype;
      const descriptor =
        Object.getOwnPropertyDescriptor(proto, 'value');

      if (descriptor && descriptor.set) {
        descriptor.set.call(el, next);
      } else {
        el.value = next;
      }

      const pos = start + text.length;
      try { el.setSelectionRange(pos, pos); } catch (_) {}

      try {
        el.dispatchEvent(
          new InputEvent('input', {
            bubbles: true,
            inputType: 'insertText',
            data: text
          })
        );
      } catch (_) {
        el.dispatchEvent(new Event('input', { bubbles: true }));
      }
      return true;
    }

    if (el.isContentEditable) {
      try {
        const selection = window.getSelection();
        if (selection && selection.rangeCount) {
          selection.deleteFromDocument();
          const node = document.createTextNode(text);
          const range = selection.getRangeAt(0);
          range.insertNode(node);
          range.setStartAfter(node);
          range.collapse(true);
          selection.removeAllRanges();
          selection.addRange(range);
          el.dispatchEvent(new Event('input', { bubbles: true }));
          return true;
        }
      } catch (_) {}
    }
  }
  return false;
})()
                                        """.replace("PAYLOAD", payload)
                                    )
                                except Exception:
                                    pass

                        elif command == "key":
                            key_name = str(message.get("key", "") or "")
                            shift = bool(message.get("shift", False))
                            ctrl = bool(message.get("ctrl", False))
                            payload = json.dumps(
                                {
                                    "key": key_name,
                                    "shift": shift,
                                    "ctrl": ctrl,
                                }
                            )
                            try:
                                window.run_js(
                                    """
(() => {
  const info = PAYLOAD;
  const el = document.activeElement;
  if (!el) return false;

  const inputLike =
    el instanceof HTMLInputElement ||
    el instanceof HTMLTextAreaElement;

  const fireKey = (type, key) => {
    try {
      el.dispatchEvent(
        new KeyboardEvent(type, {
          key,
          bubbles: true,
          cancelable: true,
          shiftKey: !!info.shift,
          ctrlKey: !!info.ctrl
        })
      );
    } catch (_) {}
  };

  if (info.ctrl && String(info.key).toLowerCase() === 'a') {
    if (inputLike) {
      try {
        el.setSelectionRange(0, String(el.value || '').length);
        return true;
      } catch (_) {}
    }
    if (el.isContentEditable) {
      try {
        const range = document.createRange();
        range.selectNodeContents(el);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        return true;
      } catch (_) {}
    }
  }

  if (info.key === 'BackSpace') {
    try {
      if (document.execCommand('delete')) return true;
    } catch (_) {}
    if (inputLike) {
      const value = String(el.value || '');
      let start = el.selectionStart ?? value.length;
      let end = el.selectionEnd ?? start;
      if (start === end && start > 0) start -= 1;
      const next = value.slice(0, start) + value.slice(end);
      el.value = next;
      try { el.setSelectionRange(start, start); } catch (_) {}
      el.dispatchEvent(new Event('input', { bubbles: true }));
      return true;
    }
  }

  if (info.key === 'Delete') {
    try {
      if (document.execCommand('forwardDelete')) return true;
    } catch (_) {}
    if (inputLike) {
      const value = String(el.value || '');
      let start = el.selectionStart ?? value.length;
      let end = el.selectionEnd ?? start;
      if (start === end && end < value.length) end += 1;
      const next = value.slice(0, start) + value.slice(end);
      el.value = next;
      try { el.setSelectionRange(start, start); } catch (_) {}
      el.dispatchEvent(new Event('input', { bubbles: true }));
      return true;
    }
  }

  if (
    inputLike &&
    ['Left', 'Right', 'Home', 'End'].includes(info.key)
  ) {
    const value = String(el.value || '');
    let start = el.selectionStart ?? value.length;
    let end = el.selectionEnd ?? start;
    let pos = end;

    if (info.key === 'Left') pos = Math.max(0, start - 1);
    if (info.key === 'Right') pos = Math.min(value.length, end + 1);
    if (info.key === 'Home') pos = 0;
    if (info.key === 'End') pos = value.length;

    try { el.setSelectionRange(pos, pos); } catch (_) {}
    return true;
  }

  if (info.key === 'Return') {
    fireKey('keydown', 'Enter');

    if (el instanceof HTMLTextAreaElement || el.isContentEditable) {
      try {
        if (document.execCommand('insertLineBreak')) {
          fireKey('keyup', 'Enter');
          return true;
        }
      } catch (_) {}
    }

    try {
      if (el.form && typeof el.form.requestSubmit === 'function') {
        el.form.requestSubmit();
        fireKey('keyup', 'Enter');
        return true;
      }
    } catch (_) {}

    fireKey('keyup', 'Enter');
    return true;
  }

  if (info.key === 'Tab') {
    fireKey('keydown', 'Tab');
    fireKey('keyup', 'Tab');
    return true;
  }

  return false;
})()
                                    """.replace("PAYLOAD", payload)
                                )
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
        self._render_hwnd = 0
        self._embedded = False
        self._embed_attempts = 0
        self._resize_job = None
        self._last_left_button_down = False
        self._web_keyboard_mode = False

        self._token = secrets.token_hex(8)
        self._child_title = "PTM_WEBVIEW_" + self._token
        self._authkey = secrets.token_bytes(24)

        self._state_path = self._get_state_path()
        self._storage_dir = str(self._get_storage_dir())
        self._load_state()

        self._build_ui()
        self.after(80, self._poll_ipc)
        self.after(120, self._poll_keyboard_target)
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

        # Proxy invisible de teclado. PTM mantiene siempre el foco real y
        # reenvía las teclas a la web únicamente después de un clic web.
        self.keyboard_proxy = tk.Entry(
            self,
            width=1,
            bd=0,
            relief="flat",
            takefocus=False,
        )
        self.keyboard_proxy.place(
            x=-100,
            y=-100,
            width=1,
            height=1,
        )
        self.keyboard_proxy.bind(
            "<KeyPress>",
            self._on_web_proxy_keypress,
        )

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
                self.after(120, self._refresh_webview_focus_hwnd)
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
        """Configura Win32 una sola vez con firmas compatibles con Python 3.14."""
        user32 = ctypes.windll.user32

        HWND = ctypes.c_void_p
        BOOL = ctypes.c_int
        DWORD = ctypes.c_ulong
        UINT = ctypes.c_uint

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

        get_long.argtypes = [HWND, ctypes.c_int]
        get_long.restype = ctypes.c_ssize_t

        set_long.argtypes = [
            HWND,
            ctypes.c_int,
            ctypes.c_ssize_t,
        ]
        set_long.restype = ctypes.c_ssize_t

        user32.FindWindowW.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_wchar_p,
        ]
        user32.FindWindowW.restype = HWND

        user32.SetParent.argtypes = [HWND, HWND]
        user32.SetParent.restype = HWND

        user32.ShowWindow.argtypes = [HWND, ctypes.c_int]
        user32.ShowWindow.restype = BOOL

        user32.SetWindowPos.argtypes = [
            HWND,
            HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            UINT,
        ]
        user32.SetWindowPos.restype = BOOL

        user32.GetWindowThreadProcessId.argtypes = [
            HWND,
            ctypes.POINTER(DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = DWORD

        user32.SetForegroundWindow.argtypes = [HWND]
        user32.SetForegroundWindow.restype = BOOL

        user32.SetActiveWindow.argtypes = [HWND]
        user32.SetActiveWindow.restype = HWND

        user32.SetFocus.argtypes = [HWND]
        user32.SetFocus.restype = HWND

        user32.AttachThreadInput.argtypes = [
            DWORD,
            DWORD,
            BOOL,
        ]
        user32.AttachThreadInput.restype = BOOL

        user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        user32.GetAsyncKeyState.restype = ctypes.c_short

        user32.GetClassNameW.argtypes = [
            HWND,
            ctypes.c_wchar_p,
            ctypes.c_int,
        ]
        user32.GetClassNameW.restype = ctypes.c_int

        user32.IsWindowVisible.argtypes = [HWND]
        user32.IsWindowVisible.restype = BOOL

        return user32, get_long, set_long

    def _find_webview_focus_hwnd(self):
        """Encuentra el HWND Chromium que recibe el teclado del contenido web."""
        if os.name != "nt" or not self._child_hwnd:
            return 0

        try:
            user32, _get_long, _set_long = self._win_api()
            candidates = []

            WNDENUMPROC = ctypes.WINFUNCTYPE(
                ctypes.c_bool,
                ctypes.c_void_p,
                ctypes.c_void_p,
            )

            def enum_proc(hwnd, _lparam):
                try:
                    handle = int(hwnd or 0)
                    if not handle:
                        return True

                    buffer = ctypes.create_unicode_buffer(256)
                    if user32.GetClassNameW(
                        handle,
                        buffer,
                        len(buffer),
                    ) <= 0:
                        return True

                    name = buffer.value or ""
                    visible = bool(user32.IsWindowVisible(handle))

                    score = 0
                    if name == "Chrome_RenderWidgetHostHWND":
                        score = 100
                    elif name == "Chrome_WidgetWin_0":
                        score = 90
                    elif name == "Chrome_WidgetWin_1":
                        score = 80
                    elif "Chrome" in name:
                        score = 60

                    if score:
                        if visible:
                            score += 5
                        candidates.append((score, handle, name))
                except Exception:
                    pass
                return True

            callback = WNDENUMPROC(enum_proc)
            user32.EnumChildWindows(
                int(self._child_hwnd),
                callback,
                0,
            )

            if not candidates:
                return int(self._webview_hwnd or self._child_hwnd)

            candidates.sort(reverse=True)
            return int(candidates[0][1])
        except Exception:
            return int(self._webview_hwnd or self._child_hwnd)

    def _refresh_webview_focus_hwnd(self):
        if not self._embedded:
            return
        self._render_hwnd = self._find_webview_focus_hwnd()

    def _attempt_embed(self):
        if not self._alive or os.name != "nt":
            return

        try:
            user32, get_long, set_long = self._win_api()

            # Mantener HWND como entero. En Python 3.14 envolver un
            # c_void_p dentro de otro c_void_p produce:
            # "cannot be converted to pointer".
            hwnd = int(self._child_hwnd or 0)
            if not hwnd:
                found = user32.FindWindowW(
                    None,
                    self._child_title,
                )
                hwnd = int(found or 0)

            if not hwnd:
                self._embed_attempts += 1
                if self._embed_attempts < 80:
                    self.after(50, self._attempt_embed)
                else:
                    self._show_browser_error(
                        "WebView2 inició, pero PTM no pudo encontrar su ventana."
                    )
                return

            parent_hwnd = int(self.browser_host.winfo_id())

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
                    hwnd,
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
                hwnd,
                parent_hwnd,
            )
            set_long(
                hwnd,
                GWL_STYLE,
                style,
            )

            self._child_hwnd = hwnd
            self._embedded = True

            self.placeholder.place_forget()
            self.status_var.set("Listo")
            self._resize_embedded(force=True)

            user32.ShowWindow(
                hwnd,
                5,
            )

            self._send(
                {
                    "cmd": "zoom",
                    "factor": self.zoom_level,
                }
            )
            self.after(160, self._refresh_webview_focus_hwnd)

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

            user32, _get_long, _set_long = self._win_api()
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
                int(self._child_hwnd),
                0,
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
            user32, _get_long, _set_long = self._win_api()
            user32.ShowWindow(
                int(self._child_hwnd),
                5 if visible else 0,
            )
        except Exception:
            pass

    # ---------- Teclado web mediante proxy Tk ----------
    def _poll_keyboard_target(self):
        """
        PTM conserva siempre el foco. Un clic web activa el proxy de teclado;
        cualquier clic fuera de la web desactiva el proxy y deja a Tkinter
        manejar el teclado normalmente.
        """
        if not self._alive:
            return

        try:
            if os.name == "nt":
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
                        inside_web = False

                        if self._embedded:
                            try:
                                x0 = int(self.browser_host.winfo_rootx())
                                y0 = int(self.browser_host.winfo_rooty())
                                x1 = x0 + int(self.browser_host.winfo_width())
                                y1 = y0 + int(self.browser_host.winfo_height())
                                inside_web = (
                                    x0 <= point.x < x1
                                    and y0 <= point.y < y1
                                )
                            except tk.TclError:
                                inside_web = False

                        if inside_web:
                            self._web_keyboard_mode = True

                            def focus_proxy():
                                try:
                                    if (
                                        self._alive
                                        and self._web_keyboard_mode
                                        and self.keyboard_proxy.winfo_exists()
                                    ):
                                        self.keyboard_proxy.focus_force()
                                except Exception:
                                    pass

                            # El clic primero posiciona el caret/selección dentro
                            # del DOM; inmediatamente después Tk recupera el foco
                            # físico para poder reenviar el teclado.
                            self.after(25, focus_proxy)
                        else:
                            self._web_keyboard_mode = False
                            self._restore_tk_input_focus(
                                point.x,
                                point.y,
                            )

                self._last_left_button_down = down
        except Exception:
            pass

        try:
            self.after(30, self._poll_keyboard_target)
        except tk.TclError:
            pass

    def _restore_tk_input_focus(self, root_x, root_y):
        try:
            top = self.winfo_toplevel()
            widget = top.winfo_containing(
                int(root_x),
                int(root_y),
            )
        except Exception:
            widget = None

        if widget is None:
            return

        input_types = (
            tk.Entry,
            tk.Text,
            tk.Spinbox,
            ttk.Entry,
            ttk.Combobox,
            ttk.Spinbox,
        )

        if not isinstance(widget, input_types):
            return

        def apply_focus(w=widget):
            try:
                if w.winfo_exists():
                    w.focus_force()
            except Exception:
                pass

        try:
            self.after_idle(apply_focus)
        except tk.TclError:
            pass

    def _on_web_proxy_keypress(self, event):
        if not self._web_keyboard_mode:
            return None

        state = int(getattr(event, "state", 0) or 0)
        ctrl = bool(state & 0x0004)
        shift = bool(state & 0x0001)
        keysym = str(getattr(event, "keysym", "") or "")
        char = str(getattr(event, "char", "") or "")

        if ctrl:
            lower = keysym.lower()

            if lower == "v":
                try:
                    text_value = self.clipboard_get()
                except Exception:
                    text_value = ""
                if text_value:
                    self._send(
                        {
                            "cmd": "text",
                            "text": text_value,
                        }
                    )
                return "break"

            if lower == "a":
                self._send(
                    {
                        "cmd": "key",
                        "key": "a",
                        "ctrl": True,
                        "shift": shift,
                    }
                )
                return "break"

            # No secuestrar otros atajos de PTM.
            return "break"

        special = {
            "BackSpace": "BackSpace",
            "Delete": "Delete",
            "Left": "Left",
            "Right": "Right",
            "Home": "Home",
            "End": "End",
            "Return": "Return",
            "KP_Enter": "Return",
            "Tab": "Tab",
        }

        if keysym in special:
            self._send(
                {
                    "cmd": "key",
                    "key": special[keysym],
                    "shift": shift,
                    "ctrl": False,
                }
            )
            return "break"

        if char and ord(char[0]) >= 32:
            self._send(
                {
                    "cmd": "text",
                    "text": char,
                }
            )
            return "break"

        return "break"

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
        self._render_hwnd = 0
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
        self._render_hwnd = 0
        self._embedded = False

    # ---------- Ciclo PTM ----------
    def on_show(self):
        self._web_keyboard_mode = False
        self._set_embedded_visible(True)
        self.after(25, lambda: self._resize_embedded(force=True))
        self.after(100, self._refresh_webview_focus_hwnd)

    def on_hide(self):
        self._web_keyboard_mode = False
        self._set_embedded_visible(False)
        self._save_state()

    def on_close(self):
        self._alive = False
        self._web_keyboard_mode = False
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
