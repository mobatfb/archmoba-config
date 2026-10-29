# ARGUMENTOS: multimedia vlc video audio musica imagenes fotos reproductor player playlist lista reproduccion arrastrar soltar drag drop mp4 mkv avi mp3 flac jpg png
import importlib
import json
import os
import queue
import random
import secrets
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from multiprocessing.connection import Client, Listener
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

TOOL_NAME = "Visor Multimedia"
TOOL_DESCRIPTION = (
    "Visor multimedia tipo VLC integrado en PTM para imagenes, videos y musica, "
    "con playlist, arrastrar y soltar, progreso, volumen, velocidad y repeticion."
)
TOOL_VERSION = "1.1.0"

CHILD_FLAG = "--ptm-media-child"

IMAGE_EXTS = {
    ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff",
}
AUDIO_EXTS = {
    ".mp3", ".wav", ".flac", ".ogg", ".oga", ".m4a", ".aac", ".wma", ".opus",
}
VIDEO_EXTS = {
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".mpeg", ".mpg", ".m4v",
    ".wmv", ".ts", ".m2ts", ".mts", ".3gp", ".ogv",
}
SUPPORTED_EXTS = IMAGE_EXTS | AUDIO_EXTS | VIDEO_EXTS


def _child_send(conn, payload):
    try:
        conn.send(payload)
        return True
    except Exception:
        return False


def _find_vlc_dir():
    candidates = []

    for key in ("VLC_PATH", "VLC_HOME"):
        raw = os.environ.get(key)
        if raw:
            candidates.append(Path(raw))

    exe = shutil.which("vlc")
    if exe:
        candidates.append(Path(exe).resolve().parent)

    for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        raw = os.environ.get(key)
        if raw:
            candidates.append(Path(raw) / "VideoLAN" / "VLC")

    candidates.extend([
        Path(r"C:\Program Files\VideoLAN\VLC"),
        Path(r"C:\Program Files (x86)\VideoLAN\VLC"),
    ])

    seen = set()
    for path in candidates:
        try:
            resolved = path.expanduser().resolve()
        except Exception:
            resolved = path

        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)

        if (resolved / "libvlc.dll").is_file():
            return resolved

    return None


def _media_child(port, auth_hex, initial_hwnd):
    conn = None
    dll_guard = None
    player = None
    instance = None

    try:
        conn = Client(
            ("127.0.0.1", int(port)),
            authkey=bytes.fromhex(auth_hex),
        )
        _child_send(conn, {"type": "starting"})

        if os.name == "nt":
            vlc_dir = _find_vlc_dir()
            if vlc_dir is not None:
                os.environ["PATH"] = str(vlc_dir) + os.pathsep + os.environ.get("PATH", "")
                try:
                    dll_guard = os.add_dll_directory(str(vlc_dir))
                except Exception:
                    dll_guard = None

        try:
            vlc = importlib.import_module("vlc")
            try:
                version = str(vlc.libvlc_get_version() or "")
            except Exception:
                version = ""
        except Exception as exc:
            raise RuntimeError(
                "No se encontro LibVLC. Instala VLC Desktop de VideoLAN para "
                "reproducir audio y video. Detalle: " + str(exc)
            )

        instance = vlc.Instance(
            "--no-video-title-show",
            "--quiet",
            "--no-snapshot-preview",
        )
        player = instance.media_player_new()

        state = {
            "alive": True,
            "hwnd": int(initial_hwnd or 0),
            "path": "",
            "volume": 75,
            "rate": 1.0,
            "last_report": None,
            "ended_sent": False,
        }

        def apply_target():
            hwnd = int(state["hwnd"] or 0)
            if not hwnd:
                return

            try:
                if os.name == "nt":
                    player.set_hwnd(hwnd)
                elif sys.platform.startswith("linux"):
                    player.set_xwindow(hwnd)
                elif sys.platform == "darwin":
                    player.set_nsobject(hwnd)
            except Exception:
                pass

            try:
                player.video_set_mouse_input(False)
            except Exception:
                pass
            try:
                player.video_set_key_input(False)
            except Exception:
                pass

        apply_target()
        player.audio_set_volume(int(state["volume"]))

        _child_send(
            conn,
            {
                "type": "ready",
                "vlc_version": version,
            },
        )

        while state["alive"]:
            try:
                if conn.poll(0.04):
                    message = conn.recv()
                    if not isinstance(message, dict):
                        continue

                    command = str(message.get("cmd", "")).lower()

                    if command == "target":
                        try:
                            state["hwnd"] = int(message.get("hwnd", 0) or 0)
                        except Exception:
                            state["hwnd"] = 0
                        apply_target()

                    elif command == "load":
                        path = str(message.get("path", "") or "").strip()
                        if not path:
                            continue

                        state["path"] = path
                        state["ended_sent"] = False
                        media = instance.media_new(str(Path(path).resolve()))
                        player.set_media(media)
                        apply_target()

                        try:
                            player.audio_set_volume(int(state["volume"]))
                        except Exception:
                            pass

                        autoplay = bool(message.get("autoplay", True))
                        if autoplay:
                            player.play()
                            time.sleep(0.08)
                            try:
                                player.set_rate(float(state["rate"]))
                            except Exception:
                                pass

                        _child_send(
                            conn,
                            {
                                "type": "loaded",
                                "path": path,
                            },
                        )

                    elif command == "play":
                        player.play()
                        time.sleep(0.05)
                        try:
                            player.set_rate(float(state["rate"]))
                        except Exception:
                            pass

                    elif command == "pause":
                        try:
                            player.set_pause(1)
                        except Exception:
                            player.pause()

                    elif command == "resume":
                        try:
                            player.set_pause(0)
                        except Exception:
                            player.play()

                    elif command == "toggle":
                        if player.is_playing():
                            try:
                                player.set_pause(1)
                            except Exception:
                                player.pause()
                        else:
                            try:
                                player.set_pause(0)
                            except Exception:
                                player.play()

                    elif command == "stop":
                        player.stop()
                        state["ended_sent"] = False

                    elif command == "seek":
                        try:
                            ms = max(0, int(float(message.get("ms", 0))))
                            player.set_time(ms)
                        except Exception:
                            pass

                    elif command == "volume":
                        try:
                            value = max(0, min(100, int(float(message.get("value", 75)))))
                            state["volume"] = value
                            player.audio_set_volume(value)
                        except Exception:
                            pass

                    elif command == "rate":
                        try:
                            value = max(0.25, min(4.0, float(message.get("value", 1.0))))
                            state["rate"] = value
                            player.set_rate(value)
                        except Exception:
                            pass

                    elif command == "close":
                        state["alive"] = False
                        try:
                            player.stop()
                        except Exception:
                            pass
                        break

                now = time.monotonic()
                if state["path"] and (state["last_report"] is None or now - state["last_report"] >= 0.25):
                    state["last_report"] = now

                    try:
                        current_ms = max(0, int(player.get_time()))
                    except Exception:
                        current_ms = 0
                    try:
                        length_ms = max(0, int(player.get_length()))
                    except Exception:
                        length_ms = 0
                    try:
                        is_playing = bool(player.is_playing())
                    except Exception:
                        is_playing = False
                    try:
                        current_state = str(player.get_state())
                    except Exception:
                        current_state = ""

                    _child_send(
                        conn,
                        {
                            "type": "state",
                            "path": state["path"],
                            "time": current_ms,
                            "length": length_ms,
                            "playing": is_playing,
                            "state": current_state,
                        },
                    )

                    if "Ended" in current_state:
                        if not state["ended_sent"]:
                            state["ended_sent"] = True
                            _child_send(
                                conn,
                                {
                                    "type": "ended",
                                    "path": state["path"],
                                },
                            )
                    else:
                        state["ended_sent"] = False

            except (EOFError, OSError):
                break
            except Exception as exc:
                _child_send(
                    conn,
                    {
                        "type": "warning",
                        "message": str(exc),
                    },
                )
                time.sleep(0.08)

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
            if player is not None:
                player.stop()
        except Exception:
            pass
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass
        try:
            if dll_guard is not None:
                dll_guard.close()
        except Exception:
            pass


class MultimediaViewerTool(ttk.Frame):
    def __init__(self, parent, app=None):
        super().__init__(parent)
        self.app = app

        self.playlist = []
        self.recent_tracks = []  # Los ultimos 40 archivos abiertos.
        self.favorite_tracks = []  # Favoritos persistentes.
        self.all_tracks = {}  # Ruta -> duracion (0 para imagenes).
        self._all_index = {}  # Metadatos persistentes de archivos escaneados.
        self._scan_queue = queue.Queue(maxsize=128)
        self._scan_cancel = threading.Event()
        self._scan_thread = None
        self._scan_started = False
        self._scan_active = False
        self._all_render_token = 0
        self._all_rendering = False
        self._visible_all_paths = []
        self._visible_recent_paths = []
        self._visible_favorite_paths = []
        self.current_index = -1
        self.visible_indices = []
        self.current_kind = "idle"

        self._alive = True
        self._listener = None
        self._conn = None
        self._process = None
        self._ipc_queue = queue.Queue()
        self._send_lock = threading.Lock()
        self._authkey = secrets.token_bytes(24)
        self._vlc_ready = False
        self._vlc_error = ""
        self._pending_media = None

        self._image_module = None
        self._imagetk_module = None
        self._source_image = None
        self._photo = None
        self._image_resize_job = None

        self.duration_ms = 0
        self.current_ms = 0
        self._seeking = False
        self._last_state = ""
        self._save_job = None

        self.title_var = tk.StringVar(value="Sin reproduccion")
        self.detail_var = tk.StringVar(value="Arrastra imagenes, videos o musica")
        self.status_var = tk.StringVar(value="Preparando visor multimedia...")
        self.time_var = tk.StringVar(value="0:00 / 0:00")
        self.search_var = tk.StringVar()
        self.queue_count_var = tk.StringVar(value="0 elementos")
        self.recent_count_var = tk.StringVar(value="0 recientes")
        self.favorite_count_var = tk.StringVar(value="0 favoritos")
        self.all_count_var = tk.StringVar(value="0 multimedia")
        self.scan_status_var = tk.StringVar(
            value="Abre Todos para buscar multimedia en el equipo"
        )
        self.volume_var = tk.DoubleVar(value=75)
        self.progress_var = tk.DoubleVar(value=0)
        self.rate_var = tk.StringVar(value="1.0x")
        self.repeat_var = tk.BooleanVar(value=False)
        self.shuffle_var = tk.BooleanVar(value=False)

        self.state_path = self._state_file()

        self._build_ui()
        self._init_image_backend()
        self._init_drag_drop()
        self._load_state()
        self._load_scan_cache()
        self._refresh_playlist()
        self._refresh_recent()
        self._refresh_favorites()
        self._refresh_all()
        self.after(150, self._poll_scan_queue)
        self.after(80, self._poll_ipc)
        self.after(200, self._start_media_process)

    # ---------- Estado ----------
    def _state_file(self):
        local = os.environ.get("LOCALAPPDATA")
        if local:
            base = Path(local) / "ARCHMOBA" / "PTM" / "visor_multimedia"
        else:
            base = Path.home() / ".archmoba" / "PTM" / "visor_multimedia"
        base.mkdir(parents=True, exist_ok=True)
        return base / "state.json"

    def _load_state(self):
        try:
            if not self.state_path.is_file():
                return

            data = json.loads(self.state_path.read_text(encoding="utf-8"))

            items = []
            for raw in data.get("playlist", []):
                path = Path(str(raw)).expanduser()
                if path.is_file() and path.suffix.lower() in SUPPORTED_EXTS:
                    items.append(str(path))
            self.playlist = items

            # Estado antiguo compatible: nuevas claves opcionales.
            self.recent_tracks = []
            seen = set()
            for raw in data.get("recent_tracks", [])[:200]:
                path = str(Path(str(raw)).expanduser())
                if path not in seen and Path(path).suffix.lower() in SUPPORTED_EXTS:
                    seen.add(path)
                    self.recent_tracks.append(path)
                if len(self.recent_tracks) >= 40:
                    break
            self.favorite_tracks = []
            seen = set()
            for raw in data.get("favorite_tracks", [])[:5000]:
                path = str(Path(str(raw)).expanduser())
                if path not in seen and Path(path).suffix.lower() in SUPPORTED_EXTS:
                    seen.add(path)
                    self.favorite_tracks.append(path)

            self.volume_var.set(
                max(0, min(100, float(data.get("volume", 75))))
            )
            rate = float(data.get("rate", 1.0))
            if rate not in {0.5, 0.75, 1.0, 1.25, 1.5, 2.0}:
                rate = 1.0
            self.rate_var.set(f"{rate:g}x")
            self.repeat_var.set(bool(data.get("repeat", False)))
            self.shuffle_var.set(bool(data.get("shuffle", False)))

            last = str(data.get("last_file", "") or "")
            if last and last in self.playlist:
                self.current_index = self.playlist.index(last)
        except Exception:
            pass

    def _save_state(self):
        try:
            current = self.current_path() or ""
            data = {
                "version": 2,
                "playlist": self.playlist,
                "recent_tracks": self.recent_tracks[:40],
                "favorite_tracks": self.favorite_tracks,
                "last_file": current,
                "volume": int(float(self.volume_var.get())),
                "rate": self.current_rate(),
                "repeat": bool(self.repeat_var.get()),
                "shuffle": bool(self.shuffle_var.get()),
            }
            tmp = self.state_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp, self.state_path)
        except Exception:
            pass

    def _schedule_save(self):
        if self._save_job is not None:
            try:
                self.after_cancel(self._save_job)
            except Exception:
                pass
        self._save_job = self.after(500, self._save_state)

    # ---------- UI ----------
    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        style = ttk.Style(self)
        style.configure("MediaTitle.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("MediaTrack.TLabel", font=("Segoe UI", 12, "bold"))
        style.configure("MediaMuted.TLabel", foreground="#707070")
        style.configure(
            "MediaTransport.TButton",
            font=("Segoe UI Symbol", 12),
            padding=(9, 5),
        )

        header = ttk.Frame(self, padding=(14, 7, 14, 5))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        ttk.Label(
            header,
            text=TOOL_NAME,
            style="MediaTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(
            header,
            text=f"v{TOOL_VERSION}",
            style="MediaMuted.TLabel",
        ).grid(row=0, column=1, sticky="e")

        body = ttk.Panedwindow(self, orient="horizontal")
        body.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 5))

        # Biblioteca con pestañas; conserva la cola anterior en Lista actual.
        left = ttk.Frame(body, padding=5)
        body.add(left, weight=2)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(4, weight=1)

        ttk.Label(
            left, text="Biblioteca multimedia", font=("Segoe UI", 11, "bold")
        ).grid(row=0, column=0, sticky="w")

        actions = ttk.Frame(left)
        actions.grid(row=1, column=0, sticky="ew", pady=(6, 4))
        ttk.Button(
            actions, text="+ Archivos", command=self.add_files
        ).pack(side="left")
        ttk.Button(
            actions, text="+ Carpeta", command=self.add_folder
        ).pack(side="left", padx=(4, 0))
        ttk.Button(
            actions, text="Escanear", command=self.start_scan
        ).pack(side="left", padx=(4, 0))
        self.stop_scan_btn = ttk.Button(
            actions, text="Detener", command=self.stop_scan, state="disabled"
        )
        self.stop_scan_btn.pack(side="left", padx=(4, 0))

        self.drop_hint = ttk.Label(
            left, textvariable=self.scan_status_var,
            style="MediaMuted.TLabel", anchor="w", wraplength=360,
        )
        self.drop_hint.grid(row=2, column=0, sticky="ew", pady=(0, 4))

        self.search_entry = ttk.Entry(left, textvariable=self.search_var)
        self.search_entry.grid(row=3, column=0, sticky="ew", pady=(0, 5))
        self.search_var.trace_add(
            "write", lambda *_: self._refresh_all_tabs()
        )

        style.configure(
            "MediaLibrary.TNotebook", background="#D6E3FF", borderwidth=0
        )
        style.configure(
            "MediaLibrary.TNotebook.Tab", padding=(12, 7),
            font=("Segoe UI", 9), background="#D5E2FA",
        )
        style.map(
            "MediaLibrary.TNotebook.Tab",
            background=[("selected", "#FFFFFF"), ("!selected", "#D5E2FA")],
            foreground=[("selected", "#172638"), ("!selected", "#34445D")],
        )
        self.library_tabs = ttk.Notebook(left, style="MediaLibrary.TNotebook")
        self.library_tabs.grid(row=4, column=0, sticky="nsew")
        self.tab_recent = ttk.Frame(self.library_tabs, padding=5)
        self.tab_favorites = ttk.Frame(self.library_tabs, padding=5)
        self.tab_all = ttk.Frame(self.library_tabs, padding=5)
        self.tab_queue = ttk.Frame(self.library_tabs, padding=5)
        self.library_tabs.add(self.tab_recent, text="Recientes")
        self.library_tabs.add(self.tab_favorites, text="Favoritos")
        self.library_tabs.add(self.tab_all, text="Todos")
        self.library_tabs.add(self.tab_queue, text="Lista actual")
        self.library_tabs.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self.recent_listbox = self._make_tab_list(
            self.tab_recent, self.recent_count_var,
            "Borrar historial", self.clear_recent,
        )
        self.favorite_listbox = self._make_tab_list(
            self.tab_favorites, self.favorite_count_var,
        )
        self.all_listbox = self._make_tab_list(
            self.tab_all, self.all_count_var,
        )
        self.listbox = self._make_tab_list(
            self.tab_queue, self.queue_count_var,
        )
        queue_buttons = ttk.Frame(self.tab_queue)
        queue_buttons.grid(row=2, column=0, sticky="ew", pady=(5, 0))
        ttk.Button(
            queue_buttons, text="Quitar", command=self.remove_selected
        ).pack(side="left")
        ttk.Button(
            queue_buttons, text="Limpiar", command=self.clear_playlist
        ).pack(side="left", padx=(5, 0))

        for source, widget in (
            ("recent", self.recent_listbox),
            ("favorites", self.favorite_listbox),
            ("all", self.all_listbox),
            ("queue", self.listbox),
        ):
            widget.bind(
                "<Double-Button-1>",
                lambda event, tab=source: self._open_tab_selected(tab, event),
            )
            widget.bind(
                "<Return>",
                lambda event, tab=source: self._open_tab_selected(tab, event),
            )
            widget.bind(
                "<Button-3>",
                lambda event, tab=source: self._tab_context_menu(tab, event),
            )
            widget.bind(
                "<Control-Button-1>",
                lambda event, tab=source: self._tab_context_menu(tab, event),
            )

        options = ttk.Frame(left)
        options.grid(row=5, column=0, sticky="ew", pady=(5, 0))
        ttk.Checkbutton(
            options, text="Repetir", variable=self.repeat_var,
            command=self._schedule_save,
        ).pack(side="left")
        ttk.Checkbutton(
            options, text="Aleatorio", variable=self.shuffle_var,
            command=self._schedule_save,
        ).pack(side="left", padx=(8, 0))

        # Visor
        right = ttk.Frame(body, padding=5)
        body.add(right, weight=5)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)

        ttk.Label(
            right,
            textvariable=self.title_var,
            style="MediaTrack.TLabel",
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")

        ttk.Label(
            right,
            textvariable=self.detail_var,
            style="MediaMuted.TLabel",
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", pady=(1, 5))

        self.stage = tk.Frame(
            right,
            bg="#101010",
            highlightthickness=0,
            bd=0,
        )
        self.stage.grid(row=2, column=0, sticky="nsew")
        self.stage.bind("<Configure>", self._on_stage_resize)
        self.stage.bind("<Double-Button-1>", lambda _e: self.toggle_play())

        self.overlay = tk.Label(
            self.stage,
            bg="#101010",
            fg="#F4F4F4",
            text="Arrastra contenido aqui",
            font=("Segoe UI", 15, "bold"),
            compound="top",
            justify="center",
        )
        self.overlay.place(
            relx=0,
            rely=0,
            relwidth=1,
            relheight=1,
        )

        # Progreso
        progress_row = ttk.Frame(right)
        progress_row.grid(row=3, column=0, sticky="ew", pady=(5, 0))
        progress_row.columnconfigure(0, weight=1)

        self.progress_scale = ttk.Scale(
            progress_row,
            from_=0,
            to=1000,
            orient="horizontal",
            variable=self.progress_var,
        )
        self.progress_scale.grid(row=0, column=0, sticky="ew")
        self.progress_scale.bind("<ButtonPress-1>", self._seek_start)
        self.progress_scale.bind("<ButtonRelease-1>", self._seek_end)

        ttk.Label(
            progress_row,
            textvariable=self.time_var,
            width=15,
            anchor="e",
        ).grid(row=0, column=1, padx=(7, 0))

        # Controles
        controls = ttk.Frame(right)
        controls.grid(row=4, column=0, sticky="ew", pady=(5, 0))
        controls.columnconfigure(6, weight=1)

        ttk.Button(
            controls,
            text="⏮",
            width=4,
            style="MediaTransport.TButton",
            command=self.previous_item,
        ).grid(row=0, column=0, padx=(0, 3))

        self.play_btn = ttk.Button(
            controls,
            text="▶",
            width=4,
            style="MediaTransport.TButton",
            command=self.toggle_play,
        )
        self.play_btn.grid(row=0, column=1, padx=3)

        ttk.Button(
            controls,
            text="⏹",
            width=4,
            style="MediaTransport.TButton",
            command=self.stop_playback,
        ).grid(row=0, column=2, padx=3)

        ttk.Button(
            controls,
            text="⏭",
            width=4,
            style="MediaTransport.TButton",
            command=self.next_item,
        ).grid(row=0, column=3, padx=3)

        ttk.Label(
            controls,
            text="Velocidad:",
        ).grid(row=0, column=4, padx=(10, 4))

        self.rate_combo = ttk.Combobox(
            controls,
            textvariable=self.rate_var,
            values=("0.5x", "0.75x", "1x", "1.25x", "1.5x", "2x"),
            state="readonly",
            width=6,
        )
        self.rate_combo.grid(row=0, column=5)
        self.rate_combo.bind("<<ComboboxSelected>>", self._on_rate_changed)

        volume_wrap = ttk.Frame(controls)
        volume_wrap.grid(row=0, column=7, sticky="e", padx=(12, 0))

        ttk.Label(volume_wrap, text="Vol.").pack(side="left", padx=(0, 4))

        self.volume_scale = ttk.Scale(
            volume_wrap,
            from_=0,
            to=100,
            orient="horizontal",
            length=120,
            variable=self.volume_var,
            command=self._on_volume,
        )
        self.volume_scale.pack(side="left")

        ttk.Label(
            volume_wrap,
            textvariable=self.volume_var,
            width=4,
            anchor="e",
        ).pack(side="left", padx=(4, 0))

        footer = ttk.Frame(self, padding=(14, 3, 14, 7))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)

        ttk.Label(
            footer,
            textvariable=self.status_var,
            style="MediaMuted.TLabel",
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")

        ttk.Button(
            footer,
            text="Reiniciar motor VLC",
            command=self.restart_media_engine,
        ).grid(row=0, column=1, padx=(8, 0))

    # ---------- Archivos / playlist ----------
    # ---------- Pestañas de biblioteca ----------

    def _make_tab_list(self, parent, count_var, button_text=None, button_cmd=None):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        header = ttk.Frame(parent)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header, textvariable=count_var, style="MediaMuted.TLabel"
        ).grid(row=0, column=0, sticky="w")
        if button_text and button_cmd:
            ttk.Button(
                header, text=button_text, command=button_cmd
            ).grid(row=0, column=1, sticky="e")
        holder = ttk.Frame(parent)
        holder.grid(row=1, column=0, sticky="nsew")
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(0, weight=1)
        widget = tk.Listbox(
            holder, activestyle="none", selectmode="extended",
            exportselection=False, highlightthickness=1, bd=0,
        )
        widget.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(
            holder, orient="vertical", command=widget.yview
        )
        scroll.grid(row=0, column=1, sticky="ns")
        widget.configure(yscrollcommand=scroll.set)
        return widget

    def _on_tab_changed(self, _event=None):
        if self.library_tabs.select() == str(self.tab_all):
            self._refresh_all()
            if not self._scan_started:
                self.start_scan()

    def _refresh_all_tabs(self):
        self._refresh_playlist()
        self._refresh_recent()
        self._refresh_favorites()
        self._refresh_all()

    def _filter_paths(self, paths):
        q = self.search_var.get().strip().casefold()
        return [
            p for p in paths if not q or q in str(p).casefold()
        ]

    def _refresh_recent(self):
        self.recent_listbox.delete(0, "end")
        self._visible_recent_paths = self._filter_paths(self.recent_tracks)
        q = self.search_var.get().strip()
        self.recent_count_var.set(
            f"{len(self._visible_recent_paths)} de {len(self.recent_tracks)}"
            if q else f"{len(self.recent_tracks)} recientes"
        )
        if not self._visible_recent_paths:
            self.recent_listbox.insert("end", "Aún no hay archivos abiertos")
            return
        for path in self._visible_recent_paths:
            star = "★ " if path in self.favorite_tracks else ""
            self.recent_listbox.insert(
                "end", f"{star}{self._media_label(path)}"
            )

    def _refresh_favorites(self):
        self.favorite_listbox.delete(0, "end")
        self._visible_favorite_paths = self._filter_paths(self.favorite_tracks)
        q = self.search_var.get().strip()
        self.favorite_count_var.set(
            f"{len(self._visible_favorite_paths)} de {len(self.favorite_tracks)}"
            if q else f"{len(self.favorite_tracks)} favoritos"
        )
        if not self._visible_favorite_paths:
            self.favorite_listbox.insert("end", "Todavía no hay favoritos")
            return
        for path in self._visible_favorite_paths:
            self.favorite_listbox.insert(
                "end", "★ " + self._media_label(path)
            )

    def _media_label(self, path):
        kind = self.media_kind(path)
        prefix = {"image": "[IMG]", "audio": "[AUD]", "video": "[VID]"}
        label = f"{prefix.get(kind, '[---]')} {Path(path).name}"
        if kind in ("audio", "video") and path in self.all_tracks:
            label += f"  ·  {self._format_ms(self.all_tracks[path] * 1000)}"
        return label

    def _mark_recent(self, path):
        if not path:
            return
        self.recent_tracks = [
            path, *(p for p in self.recent_tracks if p != path)
        ][:40]
        self._refresh_recent()
        self._schedule_save()

    def clear_recent(self):
        if not self.recent_tracks:
            return
        if not messagebox.askyesno(
            "Borrar historial",
            "¿Borrar los archivos abiertos recientemente?\n"
            "No se eliminarán archivos ni favoritos.",
            parent=self,
        ):
            return
        self.recent_tracks = []
        self._refresh_recent()
        self._schedule_save()

    def _tab_paths(self, source):
        if source == "recent":
            return self.recent_listbox, self._visible_recent_paths
        if source == "favorites":
            return self.favorite_listbox, self._visible_favorite_paths
        if source == "all":
            return self.all_listbox, self._visible_all_paths
        return self.listbox, [
            self.playlist[i] for i in self.visible_indices
            if i < len(self.playlist)
        ]

    def _open_tab_selected(self, source, _event=None):
        widget, paths = self._tab_paths(source)
        selected = widget.curselection()
        if selected and selected[0] < len(paths):
            self._play_path(paths[selected[0]])
        return "break"

    def _play_path(self, path):
        if not Path(path).is_file():
            messagebox.showwarning(
                "Archivo no disponible",
                "No se encontró el archivo:\n" + path,
                parent=self,
            )
            return
        if path not in self.playlist:
            self._add_paths([path])
        if path in self.playlist:
            self.play_index(self.playlist.index(path))

    def _tab_context_menu(self, source, event):
        widget, paths = self._tab_paths(source)
        if not paths:
            return "break"
        index = widget.nearest(event.y)
        bounds = widget.bbox(index)
        if not bounds or not (bounds[1] <= event.y < bounds[1] + bounds[3]):
            return "break"
        if index >= len(paths):
            return "break"
        widget.selection_clear(0, "end")
        widget.selection_set(index)
        widget.activate(index)
        path = paths[index]
        menu = tk.Menu(widget, tearoff=0)
        menu.add_command(
            label="▶ Reproducir / Abrir",
            command=lambda p=path: self._play_path(p),
        )
        if path in self.favorite_tracks:
            menu.add_command(
                label="★ Quitar de favoritos",
                command=lambda p=path: self._toggle_favorite(p),
            )
        else:
            menu.add_command(
                label="☆ Añadir a favoritos",
                command=lambda p=path: self._toggle_favorite(p),
            )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _toggle_favorite(self, path):
        if path in self.favorite_tracks:
            self.favorite_tracks.remove(path)
            self.status_var.set("Quitado de favoritos: " + Path(path).name)
        else:
            self.favorite_tracks.insert(0, path)
            self.status_var.set("Añadido a favoritos: " + Path(path).name)
        self._refresh_favorites()
        self._refresh_recent()
        self._refresh_playlist()
        self._update_all_row(path)
        self._schedule_save()

    def _scan_cache_path(self):
        return self.state_path.with_name("all_multimedia_cache.json")

    def media_kind(self, path):
        suffix = Path(path).suffix.lower()
        if suffix in IMAGE_EXTS:
            return "image"
        if suffix in AUDIO_EXTS:
            return "audio"
        if suffix in VIDEO_EXTS:
            return "video"
        return "unknown"

    def current_path(self):
        if 0 <= self.current_index < len(self.playlist):
            return self.playlist[self.current_index]
        return None

    def _expand_paths(self, raw_paths):
        found = []
        for raw in raw_paths:
            path = Path(str(raw)).expanduser()
            if path.is_dir():
                try:
                    children = sorted(
                        (
                            p for p in path.rglob("*")
                            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
                        ),
                        key=lambda p: (str(p.parent).lower(), p.name.lower()),
                    )
                    found.extend(str(p) for p in children)
                except Exception:
                    pass
            elif path.is_file() and path.suffix.lower() in SUPPORTED_EXTS:
                found.append(str(path))
        return found

    def _add_paths(self, paths):
        added = 0
        existing = {str(Path(p)).lower() for p in self.playlist}

        for raw in paths:
            path = str(Path(raw).resolve())
            key = path.lower()
            if key in existing:
                continue
            self.playlist.append(path)
            existing.add(key)
            added += 1

        if added:
            self._refresh_playlist()
            self.status_var.set(f"{added} elemento(s) agregado(s)")
            self._schedule_save()

            if self.current_index < 0 and self.playlist:
                self.current_index = 0
                self._select_current_in_list()

        return added

    def add_files(self):
        filetypes = [
            ("Multimedia", "*.mp4 *.mkv *.avi *.mov *.webm *.wmv *.mp3 *.wav *.flac *.ogg *.m4a *.aac *.jpg *.jpeg *.png *.bmp *.gif *.webp *.tif *.tiff"),
            ("Videos", "*.mp4 *.mkv *.avi *.mov *.webm *.mpeg *.mpg *.m4v *.wmv *.ts *.m2ts *.mts *.3gp *.ogv"),
            ("Audio", "*.mp3 *.wav *.flac *.ogg *.oga *.m4a *.aac *.wma *.opus"),
            ("Imagenes", "*.jpg *.jpeg *.png *.bmp *.gif *.webp *.tif *.tiff"),
            ("Todos", "*.*"),
        ]
        files = filedialog.askopenfilenames(
            title="Agregar contenido multimedia",
            filetypes=filetypes,
        )
        if files:
            self._add_paths(self._expand_paths(files))

    def add_folder(self):
        folder = filedialog.askdirectory(
            title="Agregar carpeta multimedia"
        )
        if folder:
            paths = self._expand_paths([folder])
            self._add_paths(paths)
            if not paths:
                self.status_var.set("La carpeta no contiene archivos compatibles")

    def remove_selected(self):
        selection = list(self.listbox.curselection())
        if not selection:
            return

        actual = sorted(
            {
                self.visible_indices[i]
                for i in selection
                if 0 <= i < len(self.visible_indices)
            },
            reverse=True,
        )

        current_path = self.current_path()

        for index in actual:
            if 0 <= index < len(self.playlist):
                del self.playlist[index]

        if not self.playlist:
            self.current_index = -1
            self.stop_playback()
            self._show_idle()
        elif current_path and current_path in self.playlist:
            self.current_index = self.playlist.index(current_path)
        else:
            self.current_index = min(
                max(0, self.current_index),
                len(self.playlist) - 1,
            )

        self._refresh_playlist()
        self._select_current_in_list()
        self._schedule_save()

    def clear_playlist(self):
        if not self.playlist:
            return
        if not messagebox.askyesno(
            "Limpiar lista",
            "¿Quitar todos los elementos de la lista de reproduccion?",
        ):
            return

        self.stop_playback()
        self.playlist.clear()
        self.current_index = -1
        self._refresh_playlist()
        self._show_idle()
        self._schedule_save()

    def _refresh_playlist(self):
        query = self.search_var.get().strip().lower()
        current = self.current_path()

        self.listbox.delete(0, "end")
        self.visible_indices = []

        for index, raw in enumerate(self.playlist):
            path = Path(raw)
            searchable = f"{path.name} {path.parent}".lower()
            if query and query not in searchable:
                continue

            kind = self.media_kind(path)
            prefix = {
                "image": "[IMG]",
                "audio": "[AUD]",
                "video": "[VID]",
            }.get(kind, "[---]")

            self.visible_indices.append(index)
            self.listbox.insert("end", f"{prefix} {path.name}")

        self.queue_count_var.set(
            f"{len(self.visible_indices)} de {len(self.playlist)}"
            if query else f"{len(self.playlist)} elementos"
        )
        if current:
            self._select_current_in_list()

    def _select_current_in_list(self):
        if self.current_index < 0:
            return
        try:
            visible = self.visible_indices.index(self.current_index)
        except ValueError:
            return

        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(visible)
        self.listbox.see(visible)

    def _on_playlist_double_click(self, _event=None):
        selection = self.listbox.curselection()
        if not selection:
            return "break"

        visible = int(selection[0])
        if 0 <= visible < len(self.visible_indices):
            self.play_index(self.visible_indices[visible])
        return "break"

    # ---------- Drag and drop ----------
    def _init_drag_drop(self):
        try:
            dnd = importlib.import_module("tkinterdnd2")
            DND_FILES = getattr(dnd, "DND_FILES")
            TkinterDnD = getattr(dnd, "TkinterDnD")
            root = self.winfo_toplevel()
            TkinterDnD._require(root)
            for widget in (
                self.listbox, self.recent_listbox, self.favorite_listbox,
                self.all_listbox, self.drop_hint, self.stage, self.overlay,
            ):
                TkinterDnD.DnDWrapper.drop_target_register(widget, DND_FILES)
                TkinterDnD.DnDWrapper.dnd_bind(
                    widget, "<<Drop>>", self._on_drop_files,
                )
        except Exception:
            pass

    def _on_drop_files(self, event):
        try:
            raw_items = self.tk.splitlist(event.data)
        except Exception:
            raw_items = [getattr(event, "data", "")]

        paths = self._expand_paths(raw_items)
        added = self._add_paths(paths)

        if added and self.current_index < 0:
            self.current_index = 0

        if added:
            self.status_var.set(
                f"{added} elemento(s) recibido(s) por arrastrar y soltar"
            )
        return "copy"

    # ---------- Imagenes ----------
    def _init_image_backend(self):
        try:
            pil_image = importlib.import_module("PIL.Image")
            image_tk = importlib.import_module("PIL.ImageTk")
            self._image_module = pil_image
            self._imagetk_module = image_tk
        except Exception as exc:
            self.status_var.set("Imagenes no disponibles: " + str(exc))

    def _show_image(self, path):
        self._send_media({"cmd": "stop"})
        self.current_kind = "image"
        self.play_btn.configure(text="▶")
        self.progress_var.set(0)
        self.time_var.set("Imagen")

        if self._image_module is None or self._imagetk_module is None:
            self.overlay.configure(
                text="No se pudo cargar Pillow para mostrar imagenes",
                image="",
            )
            self.overlay.place(
                relx=0,
                rely=0,
                relwidth=1,
                relheight=1,
            )
            return

        try:
            image = self._image_module.open(path)
            image.load()
            self._source_image = image.copy()
            image.close()
            self.overlay.place(
                relx=0,
                rely=0,
                relwidth=1,
                relheight=1,
            )
            self._render_image()
            self.status_var.set("Imagen lista")
        except Exception as exc:
            self._source_image = None
            self.overlay.configure(
                text="No se pudo abrir la imagen\n" + str(exc),
                image="",
            )
            self.status_var.set("Error al abrir imagen")

    def _on_stage_resize(self, _event=None):
        if self.current_kind != "image" or self._source_image is None:
            return

        if self._image_resize_job is not None:
            try:
                self.after_cancel(self._image_resize_job)
            except Exception:
                pass

        self._image_resize_job = self.after(80, self._render_image)

    def _render_image(self):
        self._image_resize_job = None

        if (
            self.current_kind != "image"
            or self._source_image is None
            or self._imagetk_module is None
        ):
            return

        try:
            width = max(50, int(self.stage.winfo_width()) - 18)
            height = max(50, int(self.stage.winfo_height()) - 18)

            source = self._source_image.copy()
            resampling = getattr(
                getattr(self._image_module, "Resampling", self._image_module),
                "LANCZOS",
            )
            source.thumbnail((width, height), resampling)

            self._photo = self._imagetk_module.PhotoImage(source)
            self.overlay.configure(
                image=self._photo,
                text="",
            )
        except Exception:
            pass

    def _show_audio(self, path):
        self.current_kind = "audio"
        self._source_image = None
        self._photo = None
        self.overlay.configure(
            image="",
            text=f"AUDIO\n\n{Path(path).name}",
            font=("Segoe UI", 16, "bold"),
        )
        self.overlay.place(
            relx=0,
            rely=0,
            relwidth=1,
            relheight=1,
        )

    def _show_video_surface(self):
        self.current_kind = "video"
        self._source_image = None
        self._photo = None
        self.overlay.place_forget()

        try:
            hwnd = int(self.stage.winfo_id())
            self._prepare_video_hwnd(hwnd)
            self._send_media(
                {
                    "cmd": "target",
                    "hwnd": hwnd,
                }
            )
        except Exception:
            pass

    def _show_idle(self):
        self.current_kind = "idle"
        self._source_image = None
        self._photo = None
        self.title_var.set("Sin reproduccion")
        self.detail_var.set("Arrastra imagenes, videos o musica")
        self.time_var.set("0:00 / 0:00")
        self.progress_var.set(0)
        self.play_btn.configure(text="▶")
        self.overlay.configure(
            image="",
            text="Arrastra contenido aqui",
            font=("Segoe UI", 15, "bold"),
        )
        self.overlay.place(
            relx=0,
            rely=0,
            relwidth=1,
            relheight=1,
        )

    def _prepare_video_hwnd(self, hwnd):
        if os.name != "nt" or not hwnd:
            return
        try:
            user32 = __import__("ctypes").windll.user32
            ctypes = __import__("ctypes")
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

            GWL_STYLE = -16
            WS_CLIPCHILDREN = 0x02000000
            style = int(get_long(hwnd, GWL_STYLE))
            set_long(hwnd, GWL_STYLE, style | WS_CLIPCHILDREN)
        except Exception:
            pass

    # ---------- Motor VLC aislado ----------
    def _windowless_python(self):
        executable = Path(sys.executable)
        if os.name == "nt" and executable.name.lower() == "python.exe":
            candidate = executable.with_name("pythonw.exe")
            if candidate.exists():
                return str(candidate)
        return str(executable)

    def _start_media_process(self):
        if not self._alive:
            return

        if self._process is not None and self._process.poll() is None:
            return

        self._vlc_ready = False
        self._vlc_error = ""
        self.status_var.set("Iniciando motor VLC aislado...")

        try:
            self.update_idletasks()
            hwnd = int(self.stage.winfo_id())
            self._prepare_video_hwnd(hwnd)

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
                str(hwnd),
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
                target=self._accept_media_child,
                daemon=True,
            ).start()

        except Exception as exc:
            self._vlc_error = str(exc)
            self.status_var.set(
                "Motor VLC no disponible · las imagenes siguen funcionando"
            )

    def _accept_media_child(self):
        listener = self._listener
        if listener is None:
            return

        try:
            conn = listener.accept()
            self._conn = conn
            self._ipc_queue.put({"type": "connected"})

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
                        "message": str(exc),
                    }
                )
        finally:
            try:
                listener.close()
            except Exception:
                pass

    def _send_media(self, payload):
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
                self._handle_media_message(message)
        except queue.Empty:
            pass

        if (
            self._process is not None
            and self._process.poll() is not None
            and self._alive
        ):
            exit_code = self._process.poll()
            self._process = None
            self._vlc_ready = False
            if not self._vlc_error:
                self._vlc_error = f"Motor VLC cerrado (codigo {exit_code})"
                self.status_var.set(
                    "Motor VLC cerrado · PTM y el visor de imagenes siguen activos"
                )

        try:
            self.after(90, self._poll_ipc)
        except tk.TclError:
            pass

    def _handle_media_message(self, message):
        kind = str(message.get("type", ""))

        if kind == "starting":
            self.status_var.set("Cargando LibVLC...")

        elif kind == "ready":
            self._vlc_ready = True
            self._vlc_error = ""
            version = str(message.get("vlc_version", "") or "").strip()
            self.status_var.set(
                "Motor VLC listo" + (f" · {version}" if version else "")
            )

            self._send_media(
                {
                    "cmd": "volume",
                    "value": int(float(self.volume_var.get())),
                }
            )
            self._send_media(
                {
                    "cmd": "rate",
                    "value": self.current_rate(),
                }
            )

            if self._pending_media:
                path = self._pending_media
                self._pending_media = None
                self._load_av(path)

        elif kind == "state":
            path = str(message.get("path", "") or "")
            if path and path != (self.current_path() or ""):
                return

            try:
                self.current_ms = max(0, int(message.get("time", 0) or 0))
                self.duration_ms = max(0, int(message.get("length", 0) or 0))
            except Exception:
                pass

            if not self._seeking:
                if self.duration_ms > 0:
                    self.progress_var.set(
                        min(
                            1000,
                            max(
                                0,
                                (self.current_ms / self.duration_ms) * 1000,
                            ),
                        )
                    )
                else:
                    self.progress_var.set(0)

            self.time_var.set(
                f"{self._format_ms(self.current_ms)} / {self._format_ms(self.duration_ms)}"
            )

            playing = bool(message.get("playing", False))
            state_text = str(message.get("state", "") or "")
            self._last_state = state_text
            self.play_btn.configure(text="⏸" if playing else "▶")

        elif kind == "loaded":
            self.status_var.set("Reproduciendo")
            self.play_btn.configure(text="⏸")

        elif kind == "ended":
            self.play_btn.configure(text="▶")
            self._handle_ended()

        elif kind == "warning":
            message_text = str(message.get("message", "") or "")
            if message_text:
                self.status_var.set(message_text)

        elif kind == "error":
            self._vlc_ready = False
            self._vlc_error = str(
                message.get("message", "Motor VLC no disponible")
            )
            self.status_var.set(
                "Audio/video no disponible · instala VLC Desktop · imagenes OK"
            )
            if self.current_kind in {"audio", "video"}:
                self.overlay.configure(
                    image="",
                    text=(
                        "VLC no disponible\n\n"
                        "Instala VLC Desktop de VideoLAN\n"
                        "para reproducir audio y video."
                    ),
                    font=("Segoe UI", 13, "bold"),
                )
                self.overlay.place(
                    relx=0,
                    rely=0,
                    relwidth=1,
                    relheight=1,
                )

    def restart_media_engine(self):
        self._stop_media_process()
        self._authkey = secrets.token_bytes(24)
        self._conn = None
        self._listener = None
        self._process = None
        self._vlc_error = ""
        self.after(120, self._start_media_process)

    def _stop_media_process(self):
        self._send_media({"cmd": "close"})

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
                process.wait(timeout=1.0)
            except Exception:
                try:
                    process.terminate()
                except Exception:
                    pass

        self._process = None
        self._vlc_ready = False

    # ---------- Reproduccion ----------
    def play_index(self, index):
        if not (0 <= index < len(self.playlist)):
            return

        self.current_index = index
        path = self.playlist[index]
        kind = self.media_kind(path)

        self.title_var.set(Path(path).name)
        self.detail_var.set(
            f"{kind.upper()} · {Path(path).parent}"
        )
        self.current_ms = 0
        self.duration_ms = 0
        self.progress_var.set(0)
        self._select_current_in_list()
        self._mark_recent(path)
        self._schedule_save()

        if kind == "image":
            self._show_image(path)
            return

        if kind == "audio":
            self._show_audio(path)
            self._load_av(path)
            return

        if kind == "video":
            self._show_video_surface()
            self._load_av(path)
            return

        self.status_var.set("Formato no compatible")

    def _load_av(self, path):
        if not self._vlc_ready:
            self._pending_media = path
            if self._process is None:
                self._start_media_process()
            elif self._vlc_error:
                self.status_var.set(
                    "Audio/video requiere VLC Desktop · imagenes siguen disponibles"
                )
            else:
                self.status_var.set("Esperando motor VLC...")
            return

        try:
            hwnd = int(self.stage.winfo_id())
        except Exception:
            hwnd = 0

        self._send_media({"cmd": "target", "hwnd": hwnd})
        self._send_media(
            {
                "cmd": "load",
                "path": path,
                "autoplay": True,
            }
        )
        self._send_media(
            {
                "cmd": "volume",
                "value": int(float(self.volume_var.get())),
            }
        )
        self._send_media(
            {
                "cmd": "rate",
                "value": self.current_rate(),
            }
        )

    def toggle_play(self):
        path = self.current_path()

        if path is None:
            if self.playlist:
                self.play_index(0)
            return

        kind = self.media_kind(path)

        if kind == "image":
            self.next_item()
            return

        if not self._vlc_ready:
            self._pending_media = path
            if self._process is None:
                self._start_media_process()
            return

        self._send_media({"cmd": "toggle"})

    def stop_playback(self):
        self._pending_media = None
        self._send_media({"cmd": "stop"})
        self.play_btn.configure(text="▶")
        self.current_ms = 0
        self.progress_var.set(0)

        if self.current_kind in {"audio", "video"}:
            self.time_var.set(
                f"0:00 / {self._format_ms(self.duration_ms)}"
            )

    def next_item(self):
        if not self.playlist:
            return

        if self.shuffle_var.get() and len(self.playlist) > 1:
            choices = [
                i for i in range(len(self.playlist))
                if i != self.current_index
            ]
            self.play_index(random.choice(choices))
            return

        if self.current_index < 0:
            index = 0
        else:
            index = self.current_index + 1

        if index >= len(self.playlist):
            if self.repeat_var.get():
                index = 0
            else:
                self.stop_playback()
                return

        self.play_index(index)

    def previous_item(self):
        if not self.playlist:
            return

        if self.current_index < 0:
            index = 0
        else:
            index = self.current_index - 1

        if index < 0:
            index = len(self.playlist) - 1 if self.repeat_var.get() else 0

        self.play_index(index)

    def _handle_ended(self):
        if self.repeat_var.get() and len(self.playlist) == 1:
            self.play_index(self.current_index)
        else:
            self.next_item()

    def _seek_start(self, _event=None):
        self._seeking = True

    def _seek_end(self, _event=None):
        if self.current_kind not in {"audio", "video"}:
            self._seeking = False
            return

        try:
            ratio = max(
                0.0,
                min(1.0, float(self.progress_var.get()) / 1000.0),
            )
            target = int(self.duration_ms * ratio)
            self._send_media({"cmd": "seek", "ms": target})
        except Exception:
            pass
        finally:
            self._seeking = False

    def _on_volume(self, _value=None):
        try:
            value = int(float(self.volume_var.get()))
        except Exception:
            value = 75
        self._send_media({"cmd": "volume", "value": value})
        self._schedule_save()

    def current_rate(self):
        raw = self.rate_var.get().strip().lower().rstrip("x")
        try:
            return max(0.25, min(4.0, float(raw)))
        except Exception:
            return 1.0

    def _on_rate_changed(self, _event=None):
        self._send_media(
            {
                "cmd": "rate",
                "value": self.current_rate(),
            }
        )
        self._schedule_save()

    @staticmethod
    def _format_ms(value):
        try:
            total = max(0, int(value) // 1000)
        except Exception:
            total = 0

        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    # ---------- Ciclo PTM ----------
    def on_show(self):
        if self.current_kind == "video" and self._vlc_ready:
            try:
                hwnd = int(self.stage.winfo_id())
                self._prepare_video_hwnd(hwnd)
                self._send_media({"cmd": "target", "hwnd": hwnd})
            except Exception:
                pass

    def on_hide(self):
        self._save_state()

    # ---------- Escaneo incremental de multimedia ----------

    def _load_scan_cache(self):
        try:
            path = self._scan_cache_path()
            if not path.is_file():
                return
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 1:
                return
            for item in data.get("tracks", []):
                if not isinstance(item, dict):
                    continue
                path = item.get("path")
                if not isinstance(path, str):
                    continue
                kind = self.media_kind(path)
                if kind == "unknown":
                    continue
                duration = max(0.0, float(item.get("duration", 0)))
                self._all_index[path] = {
                    "path": path,
                    "duration": duration,
                    "size": int(item.get("size", -1)),
                    "mtime_ns": int(item.get("mtime_ns", -1)),
                }
                if kind == "image" or duration > 60.0:
                    self.all_tracks[path] = duration
            self.scan_status_var.set(
                f"Caché cargada: {len(self.all_tracks)} archivos · "
                "escaneo incremental disponible"
            )
        except (OSError, ValueError, TypeError):
            self._all_index = {}
            self.all_tracks = {}

    def _write_scan_cache(self, previous, updates):
        if not updates:
            return
        merged = dict(previous)
        merged.update(updates)
        path = self._scan_cache_path()
        temp = path.with_suffix(".tmp")
        try:
            temp.write_text(
                json.dumps(
                    {"version": 1, "tracks": list(merged.values())},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            os.replace(temp, path)
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass

    def _scan_roots(self):
        if os.name != "nt":
            return [os.path.abspath(os.sep)]
        try:
            import ctypes
            kernel = ctypes.windll.kernel32
            mask = int(kernel.GetLogicalDrives())
            roots = []
            for i in range(26):
                if not (mask & (1 << i)):
                    continue
                drive = chr(ord("A") + i) + ":\\"
                if kernel.GetDriveTypeW(drive) in (2, 3, 5):
                    roots.append(drive)
            return roots
        except Exception:
            return [os.path.abspath(os.sep)]

    @staticmethod
    def _probe_duration(path, kind):
        """Duración sin cargar el video en la ventana; ffprobe/mutagen/VLC."""
        if kind == "image":
            return 0.0

        # mutagen cubre MP3, FLAC, M4A y algunos MP4.
        if kind == "audio" or Path(path).suffix.lower() in (".mp4", ".m4v"):
            try:
                from mutagen import File as MutagenFile
                media = MutagenFile(path)
                if media is not None and media.info is not None:
                    duration = float(media.info.length)
                    if duration > 0:
                        return duration
            except Exception:
                pass

        ffprobe = shutil.which("ffprobe")
        if ffprobe:
            try:
                result = subprocess.run(
                    [
                        ffprobe, "-v", "error",
                        "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", path,
                    ],
                    capture_output=True, text=True, timeout=8,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if result.returncode == 0:
                    duration = float(result.stdout.strip())
                    if duration > 0:
                        return duration
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass

        # VLC se ejecuta en otro proceso para no comprometer PTM.
        probe_code = (
            "import sys\n"
            "try:\n"
            " import vlc\n"
            " i=vlc.Instance('--quiet','--no-video-title-show')\n"
            " m=i.media_new(sys.argv[1])\n"
            " try:\n"
            "  m.parse_with_options(vlc.MediaParseFlag.local, 3500)\n"
            " except Exception:\n"
            "  m.parse()\n"
            " print(max(0, m.get_duration()) / 1000.0)\n"
            "except Exception:\n"
            " print(0)\n"
        )
        try:
            result = subprocess.run(
                [sys.executable, "-c", probe_code, path],
                capture_output=True, text=True, timeout=7,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0:
                duration = float(result.stdout.strip().splitlines()[-1])
                return max(0.0, duration)
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
            pass
        return 0.0

    def start_scan(self):
        if self._scan_active or (
            self._scan_thread and self._scan_thread.is_alive()
        ):
            self.status_var.set("Ya hay un escaneo en curso")
            return
        self._scan_started = True
        self._scan_active = True
        self._scan_cancel.clear()
        self.stop_scan_btn.configure(state="normal")
        self.scan_status_var.set(
            f"{len(self.all_tracks)} en caché · "
            "buscando archivos nuevos o modificados..."
        )
        self._scan_thread = threading.Thread(
            target=self._scan_worker, daemon=True,
            name="PTM-Multimedia-Scan",
        )
        self._scan_thread.start()

    def stop_scan(self):
        if self._scan_active:
            self._scan_cancel.set()
            self.scan_status_var.set("Deteniendo · conservando caché...")

    def _queue_scan_message(self, message, force=False):
        if force:
            try:
                self._scan_queue.put(message, timeout=1.0)
                return True
            except queue.Full:
                return False
        while not self._scan_cancel.is_set():
            try:
                self._scan_queue.put(message, timeout=0.2)
                return True
            except queue.Full:
                continue
        return False

    def _scan_worker(self):
        """Recorre discos, reutiliza metadatos sin releer archivos sin cambios."""
        previous = dict(self._all_index)
        updates = {}
        batch = []
        directories = 0
        reused = 0
        new_count = 0
        modified = 0
        new_valid = 0
        error = ""
        cache_error = ""
        last_checkpoint = time.monotonic()
        try:
            for root in self._scan_roots():
                if self._scan_cancel.is_set():
                    break
                for folder, dirs, files in os.walk(
                    root, topdown=True, followlinks=False,
                    onerror=lambda _err: None,
                ):
                    if self._scan_cancel.is_set():
                        break
                    if os.name != "nt" and folder == os.path.abspath(os.sep):
                        dirs[:] = [
                            d for d in dirs if d not in ("proc", "sys", "dev")
                        ]
                    dirs[:] = [
                        d for d in dirs
                        if not os.path.islink(os.path.join(folder, d))
                    ]
                    directories += 1
                    for filename in files:
                        if self._scan_cancel.is_set():
                            break
                        path = os.path.join(folder, filename)
                        kind = self.media_kind(path)
                        if kind == "unknown":
                            continue
                        try:
                            stat = os.stat(path)
                        except OSError:
                            continue
                        old = previous.get(path)
                        if (old and old.get("size") == stat.st_size
                                and old.get("mtime_ns") == stat.st_mtime_ns):
                            reused += 1
                            continue

                        duration = self._probe_duration(path, kind)
                        updates[path] = {
                            "path": path, "duration": duration,
                            "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                        }
                        if old:
                            modified += 1
                        else:
                            new_count += 1
                        if kind == "image" or duration > 60.0:
                            new_valid += 1
                            batch.append((path, duration))
                            if len(batch) >= 20:
                                if not self._queue_scan_message(("batch", batch)):
                                    break
                                batch = []
                        now = time.monotonic()
                        if updates and now - last_checkpoint >= 10.0:
                            try:
                                self._write_scan_cache(previous, updates)
                                cache_error = ""
                            except OSError as exc:
                                cache_error = str(exc)
                            last_checkpoint = now
                    if directories % 200 == 0:
                        if not self._queue_scan_message(
                            ("progress", directories, reused, new_valid)
                        ):
                            break
                    if self._scan_cancel.is_set():
                        break
        except Exception as exc:
            error = str(exc)
        finally:
            if batch:
                self._queue_scan_message(("batch", batch), force=True)
            if updates:
                try:
                    self._write_scan_cache(previous, updates)
                    cache_error = ""
                except OSError as exc:
                    cache_error = str(exc)
            self._queue_scan_message(
                (
                    "finished", updates, directories, reused, new_count,
                    modified, new_valid, self._scan_cancel.is_set(),
                    error, cache_error,
                ),
                force=True,
            )

    def _poll_scan_queue(self):
        try:
            for _ in range(24):
                try:
                    message = self._scan_queue.get_nowait()
                except queue.Empty:
                    break
                kind = message[0]
                if kind == "batch":
                    self._append_all_batch(message[1])
                elif kind == "progress":
                    _, directories, reused, new_valid = message
                    self.scan_status_var.set(
                        f"Buscando... {directories} carpetas · "
                        f"{reused} desde caché · {new_valid} nuevos válidos"
                    )
                elif kind == "finished":
                    (
                        _, updates, directories, reused, new_count, modified,
                        new_valid, cancelled, error, cache_error,
                    ) = message
                    self._all_index.update(updates)
                    needs_refresh = False
                    for path, entry in updates.items():
                        duration = float(entry.get("duration", 0))
                        if self.media_kind(path) == "image" or duration > 60.0:
                            self.all_tracks[path] = duration
                        elif path in self.all_tracks:
                            self.all_tracks.pop(path, None)
                            needs_refresh = True
                    if needs_refresh:
                        self._refresh_all()
                    self._scan_active = False
                    self.stop_scan_btn.configure(state="disabled")
                    if error:
                        self.scan_status_var.set(
                            f"Error de escaneo: {error} · caché conservada"
                        )
                    else:
                        status = "Escaneo detenido" if cancelled else "Escaneo completo"
                        self.scan_status_var.set(
                            f"{status} · {reused} desde caché · "
                            f"{new_count} nuevos · {modified} actualizados · "
                            f"{len(self.all_tracks)} multimedia en Todos"
                        )
                    if cache_error:
                        self.scan_status_var.set(
                            "No se pudo guardar la caché: " + cache_error
                        )
            if self._scan_thread and not self._scan_thread.is_alive():
                self.stop_scan_btn.configure(state="disabled")
                if self._scan_active and self._scan_queue.empty():
                    self._scan_active = False
        except tk.TclError:
            return
        try:
            if self.winfo_exists():
                self.after(150, self._poll_scan_queue)
        except tk.TclError:
            pass

    def _refresh_all(self):
        """Dibuja el cache en grupos de 20 para no congelar Tk."""
        self._all_render_token += 1
        token = self._all_render_token
        self._all_rendering = True
        self.all_listbox.delete(0, "end")
        self._visible_all_paths = sorted(
            self._filter_paths(self.all_tracks),
            key=lambda p: (Path(p).name.casefold(), p.casefold()),
        )
        query = self.search_var.get().strip()
        self.all_count_var.set(
            f"{len(self._visible_all_paths)} de {len(self.all_tracks)}"
            if query else f"{len(self.all_tracks)} multimedia"
        )
        if not self._visible_all_paths:
            self._all_rendering = False
            self.all_listbox.insert(
                "end", "Sin archivos · pulsa Escanear equipo"
            )
            return
        self._render_all_chunk(token, 0)

    def _render_all_chunk(self, token, offset):
        if token != self._all_render_token:
            return
        end = min(offset + 20, len(self._visible_all_paths))
        for path in self._visible_all_paths[offset:end]:
            self.all_listbox.insert("end", self._media_label(path))
        if end < len(self._visible_all_paths):
            self.after(1, lambda: self._render_all_chunk(token, end))
        else:
            self._all_rendering = False

    def _append_all_batch(self, batch):
        query = self.search_var.get().strip().casefold()
        for path, duration in batch:
            old = self.all_tracks.get(path)
            self.all_tracks[path] = duration
            if old is not None:
                self._update_all_row(path)
                continue
            if query and query not in str(path).casefold():
                continue
            if not self._visible_all_paths and not self._all_rendering:
                self.all_listbox.delete(0, "end")
            self._visible_all_paths.append(path)
            if not self._all_rendering:
                self.all_listbox.insert("end", self._media_label(path))
        self.all_count_var.set(
            f"{len(self._visible_all_paths)} de {len(self.all_tracks)}"
            if query else f"{len(self.all_tracks)} multimedia"
        )

    def _update_all_row(self, path):
        try:
            index = self._visible_all_paths.index(path)
            if index < self.all_listbox.size():
                self.all_listbox.delete(index)
                self.all_listbox.insert(index, self._media_label(path))
        except (ValueError, tk.TclError):
            pass

    def on_close(self):
        self._scan_cancel.set()
        self._all_render_token += 1
        self._alive = False
        self._save_state()
        self._stop_media_process()


App = MultimediaViewerTool


def _run_standalone():
    root = tk.Tk()
    root.title(TOOL_NAME)
    root.geometry("1120x720")
    root.minsize(760, 500)

    tool = MultimediaViewerTool(root)
    tool.pack(fill="both", expand=True)

    def close():
        tool.on_close()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == CHILD_FLAG:
        if len(sys.argv) < 5:
            raise SystemExit(2)

        _media_child(
            sys.argv[2],
            sys.argv[3],
            sys.argv[4],
        )
    else:
        _run_standalone()
