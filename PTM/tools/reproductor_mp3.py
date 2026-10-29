# ARGUMENTOS: mp3 audio musica music reproductor player playlist lista reproduccion portada album artista id3 reanudar resume posicion pygame mutagen pillow
import io
import json
import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

TOOL_NAME = "Reproductor MP3"
TOOL_DESCRIPTION = "Reproductor MP3 profesional con playlist, portada, metadata ID3 y reanudacion de reproduccion."
TOOL_VERSION = "2.0.8"


class Mp3PlayerTool(ttk.Frame):
    def __init__(self, parent, app=None):
        super().__init__(parent)
        self.app = app
        self._pygame = None
        self._mutagen_file = None
        self._id3_cls = None
        self._image_cls = None
        self._imagetk = None
        self.audio_ok = False

        self.playlist = []
        self.recent_tracks = []  # Historial local de canciones reproducidas.
        self.favorite_tracks = []  # Favoritos persistentes, independientes de recientes.
        self.all_tracks = {}  # Ruta -> duracion; solo MP3 de mas de 60 segundos.
        self._all_index = {}  # Cache de metadatos de todos los MP3 encontrados.
        self._scan_queue = queue.Queue(maxsize=64)
        self._scan_cancel = threading.Event()
        self._scan_thread = None
        self._scan_started = False
        self._scan_active = False
        self._all_render_token = 0
        self._all_rendering = False
        self._visible_all_paths = []
        self.current_index = -1
        self.loaded_path = None
        self.duration = 0.0
        self.base_position = 0.0
        self.started_ticks = 0.0
        self.paused = False
        self.playing = False
        self._resume_positions = {}
        self._last_position_save = time.monotonic()
        self.dragging_progress = False
        self.finished_guard = False
        self.cover_photo = None
        self._save_job = None

        self.title_var = tk.StringVar(value="Sin reproduccion")
        self.artist_var = tk.StringVar(value="Selecciona o agrega canciones")
        self.album_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Biblioteca lista")
        self.time_var = tk.StringVar(value="0:00 / 0:00")
        self.volume = tk.DoubleVar(value=70)
        self.progress = tk.DoubleVar(value=0)
        self.search_var = tk.StringVar()
        self.queue_count_var = tk.StringVar(value="Cola: 0")
        self.recent_count_var = tk.StringVar(value="0 escuchadas")
        self.favorite_count_var = tk.StringVar(value="0 favoritos")
        self.all_count_var = tk.StringVar(value="0 MP3 de más de 1 minuto")
        self.scan_status_var = tk.StringVar(value="Abre Todos para buscar MP3 en el equipo")

        self.state_path = self._state_file()
        self._build_ui()
        self._init_drag_drop()
        self._init_backends()
        self._load_state()
        self._load_scan_cache()
        self._refresh_playlist()
        self._refresh_recent()
        self._refresh_favorites()
        self._apply_volume()
        self.after(250, self._tick)
        self.after(150, self._poll_scan_queue)

    # ---------- Estado persistente ----------
    def _state_file(self):
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            base = Path(local_appdata) / "ARCHMOBA" / "PTM" / "reproductor_mp3"
        else:
            base = Path.home() / ".archmoba" / "PTM" / "reproductor_mp3"
        base.mkdir(parents=True, exist_ok=True)
        return base / "state.json"

    def _load_state(self):
        try:
            if not self.state_path.is_file():
                return
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.volume.set(float(data.get("volume", 70)))
            items = []
            for raw in data.get("playlist", []):
                p = Path(str(raw)).expanduser()
                if p.is_file() and p.suffix.lower() == ".mp3":
                    items.append(str(p))
            self.playlist = items
            # Caché compatible con state.json anterior; guarda rutas, no copias MP3.
            seen_recent = set()
            self.recent_tracks = []
            raw_recent = data.get("recent_tracks", [])
            if not isinstance(raw_recent, list):
                raw_recent = []
            for raw in raw_recent[:200]:
                p = Path(str(raw)).expanduser()
                if not p.is_file() or p.suffix.lower() != ".mp3":
                    continue
                path = str(p.resolve())
                if path not in seen_recent:
                    seen_recent.add(path)
                    self.recent_tracks.append(path)
                if len(self.recent_tracks) >= 40:
                    break
            self.favorite_tracks = []
            seen_favorites = set()
            raw_favorites = data.get("favorite_tracks", [])
            if not isinstance(raw_favorites, list):
                raw_favorites = []
            for raw in raw_favorites[:5000]:
                path = str(Path(str(raw)).expanduser())
                if path not in seen_favorites:
                    seen_favorites.add(path)
                    self.favorite_tracks.append(path)
            self._resume_positions = {
                str(k): max(0.0, float(v))
                for k, v in dict(data.get("positions", {})).items()
            }
            last = str(data.get("last_track", ""))
            if last and last in self.playlist:
                self.current_index = self.playlist.index(last)
        except Exception:
            self._resume_positions = {}
        if not hasattr(self, "_resume_positions"):
            self._resume_positions = {}

    def _save_state(self):
        try:
            self._remember_position()
            data = {
                "version": 3,
                "playlist": self.playlist,
                "recent_tracks": self.recent_tracks[:40],
                "favorite_tracks": self.favorite_tracks,
                "last_track": self.current_path() or "",
                "positions": self._resume_positions,
                "volume": int(float(self.volume.get())),
            }
            tmp = self.state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
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
        self.configure(padding=0)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        style = ttk.Style(self)
        style.configure("PlayerTitle.TLabel", font=("Segoe UI", 17, "bold"))
        style.configure("TrackTitle.TLabel", font=("Segoe UI", 14, "bold"))
        style.configure("Muted.TLabel", foreground="#707070")
        style.configure("Transport.TButton", font=("Segoe UI Symbol", 12), padding=(10, 5))

        # Cabecera compacta: PTM ya posee su propia navegacion por pestañas.
        header = ttk.Frame(self, padding=(18, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=TOOL_NAME, style="PlayerTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(header, text=f"v{TOOL_VERSION}", style="Muted.TLabel").grid(
            row=0, column=1, sticky="e"
        )

        body = ttk.Panedwindow(self, orient="horizontal")
        body.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 6))

        # Biblioteca con tres pestañas, como en el diseño de referencia.
        left = ttk.Frame(body, padding=6)
        body.add(left, weight=2)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(4, weight=1)

        title_row = ttk.Frame(left)
        title_row.grid(row=0, column=0, sticky="ew")
        title_row.columnconfigure(0, weight=1)
        ttk.Label(
            title_row, text="Biblioteca MP3", font=("Segoe UI", 11, "bold")
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            title_row, textvariable=self.queue_count_var, style="Muted.TLabel"
        ).grid(row=0, column=1, sticky="e")

        actions = ttk.Frame(left)
        actions.grid(row=1, column=0, sticky="ew", pady=(6, 5))
        ttk.Button(actions, text="+ MP3", command=self.add_files).pack(side="left")
        ttk.Button(actions, text="+ Carpeta", command=self.add_folder).pack(
            side="left", padx=(5, 0)
        )
        ttk.Button(actions, text="Escanear equipo", command=self.start_scan).pack(
            side="left", padx=(5, 0)
        )
        self.stop_scan_btn = ttk.Button(
            actions, text="Detener", command=self.stop_scan, state="disabled"
        )
        self.stop_scan_btn.pack(side="left", padx=(5, 0))

        self.drop_hint = ttk.Label(
            left, textvariable=self.scan_status_var, style="Muted.TLabel",
            anchor="w", wraplength=400,
        )
        self.drop_hint.grid(row=2, column=0, sticky="ew", pady=(0, 4))

        search = ttk.Entry(left, textvariable=self.search_var)
        search.grid(row=3, column=0, sticky="ew", pady=(0, 5))
        self.search_var.trace_add("write", lambda *_: self._refresh_active_tab())

        style.configure(
            "MP3.TNotebook", background="#D6E3FF", borderwidth=0
        )
        style.configure(
            "MP3.TNotebook.Tab", padding=(15, 8),
            font=("Segoe UI", 10), background="#D5E2FA",
        )
        style.map(
            "MP3.TNotebook.Tab",
            background=[("selected", "#FFFFFF"), ("!selected", "#D5E2FA")],
            foreground=[("selected", "#172638"), ("!selected", "#34445D")],
        )

        self.library_tabs = ttk.Notebook(left, style="MP3.TNotebook")
        self.library_tabs.grid(row=4, column=0, sticky="nsew")
        self.tab_recent = ttk.Frame(self.library_tabs, padding=6)
        self.tab_favorites = ttk.Frame(self.library_tabs, padding=6)
        self.tab_all = ttk.Frame(self.library_tabs, padding=6)
        self.library_tabs.add(self.tab_recent, text="Recientes")
        self.library_tabs.add(self.tab_favorites, text="Favoritos")
        self.library_tabs.add(self.tab_all, text="Todos")
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
        for tab, widget in (
            ("recent", self.recent_listbox),
            ("favorites", self.favorite_listbox),
            ("all", self.all_listbox),
        ):
            widget.bind(
                "<Double-Button-1>",
                lambda event, source=tab: self._open_tab_selected(source, event),
            )
            widget.bind(
                "<Return>",
                lambda event, source=tab: self._open_tab_selected(source, event),
            )
            widget.bind(
                "<Button-3>",
                lambda event, source=tab: self._tab_context_menu(source, event),
            )
            widget.bind(
                "<Control-Button-1>",
                lambda event, source=tab: self._tab_context_menu(source, event),
            )

        # Reproductor compacto y responsivo para la altura real de una pestaña PTM.
        right = ttk.Frame(body, padding=(14, 4))
        body.add(right, weight=3)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        player = ttk.Frame(right)
        player.grid(row=0, column=0, sticky="nsew")
        player.columnconfigure(0, weight=1)

        cover_shell = ttk.Frame(player, width=180, height=180)
        cover_shell.grid(row=0, column=0, pady=(0, 8))
        cover_shell.grid_propagate(False)
        self.cover_label = tk.Label(
            cover_shell,
            text="♫",
            font=("Segoe UI Symbol", 48),
            bg="#20252B",
            fg="#E8EDF2",
            bd=0,
        )
        self.cover_label.place(relx=0, rely=0, relwidth=1, relheight=1)

        ttk.Label(
            player,
            textvariable=self.title_var,
            style="TrackTitle.TLabel",
            anchor="center",
            wraplength=430,
        ).grid(row=1, column=0, sticky="ew")
        ttk.Label(
            player, textvariable=self.artist_var, anchor="center"
        ).grid(row=2, column=0, sticky="ew", pady=(2, 0))
        ttk.Label(
            player,
            textvariable=self.album_var,
            style="Muted.TLabel",
            anchor="center",
        ).grid(row=3, column=0, sticky="ew", pady=(1, 6))

        progress_row = ttk.Frame(player)
        progress_row.grid(row=4, column=0, sticky="ew")
        progress_row.columnconfigure(0, weight=1)
        self.progress_scale = ttk.Scale(
            progress_row,
            from_=0,
            to=1000,
            variable=self.progress,
            command=self._progress_drag,
        )
        self.progress_scale.grid(row=0, column=0, sticky="ew")
        self.progress_scale.bind("<ButtonPress-1>", self._progress_press)
        self.progress_scale.bind("<ButtonRelease-1>", self._progress_release)
        ttk.Label(
            progress_row, textvariable=self.time_var, width=12, anchor="e"
        ).grid(row=0, column=1, padx=(8, 0))

        controls = ttk.Frame(player)
        controls.grid(row=5, column=0, pady=(6, 5))
        ttk.Button(
            controls, text="⏮", style="Transport.TButton", command=self.previous_track
        ).grid(row=0, column=0, padx=3)
        self.play_btn = ttk.Button(
            controls, text="▶", style="Transport.TButton", command=self.play_pause
        )
        self.play_btn.grid(row=0, column=1, padx=3)
        ttk.Button(
            controls, text="⏹", style="Transport.TButton", command=self.stop
        ).grid(row=0, column=2, padx=3)
        ttk.Button(
            controls, text="⏭", style="Transport.TButton", command=self.next_track
        ).grid(row=0, column=3, padx=3)

        volume_row = ttk.Frame(player)
        volume_row.grid(row=6, column=0, sticky="ew", pady=(0, 2))
        volume_row.columnconfigure(1, weight=1)
        ttk.Label(volume_row, text="Vol.").grid(row=0, column=0, padx=(0, 7))
        ttk.Scale(
            volume_row,
            from_=0,
            to=100,
            variable=self.volume,
            command=self._volume_changed,
        ).grid(row=0, column=1, sticky="ew")
        self.volume_label = ttk.Label(
            volume_row, text="70%", width=5, anchor="e"
        )
        self.volume_label.grid(row=0, column=2, padx=(7, 0))

        ttk.Label(
            player,
            textvariable=self.status_var,
            style="Muted.TLabel",
            anchor="center",
            wraplength=480,
        ).grid(row=7, column=0, sticky="ew", pady=(3, 0))

    def _make_tab_list(self, parent, count_var, action_text=None, action=None):
        """Construye una pestaña con encabezado, contador y scroll."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        header = ttk.Frame(parent)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header, textvariable=count_var, style="Muted.TLabel"
        ).grid(row=0, column=0, sticky="w")
        if action_text and action:
            ttk.Button(header, text=action_text, command=action).grid(
                row=0, column=1, sticky="e"
            )
        holder = ttk.Frame(parent)
        holder.grid(row=1, column=0, sticky="nsew")
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(0, weight=1)
        widget = tk.Listbox(
            holder, selectmode="browse", activestyle="none",
            bd=0, highlightthickness=1, font=("Segoe UI", 9),
        )
        widget.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(
            holder, orient="vertical", command=widget.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        widget.configure(yscrollcommand=scrollbar.set)
        return widget

    def _on_tab_changed(self, _event=None):
        if self.library_tabs.select() == str(self.tab_all):
            self._refresh_all()
            if not self._scan_started:
                self.start_scan()
        elif self.library_tabs.select() == str(self.tab_favorites):
            self._refresh_favorites()
        else:
            self._refresh_recent()

    def _refresh_active_tab(self):
        selected = self.library_tabs.select()
        if selected == str(self.tab_all):
            self._refresh_all()
        elif selected == str(self.tab_favorites):
            self._refresh_favorites()
        else:
            self._refresh_recent()

    @staticmethod
    def _matches_search(path, query):
        if not query:
            return True
        return query in str(path).casefold()

    def _refresh_favorites(self):
        self.favorite_listbox.delete(0, "end")
        q = self.search_var.get().strip().casefold()
        self._visible_favorite_paths = [
            path for path in self.favorite_tracks
            if self._matches_search(path, q)
        ]
        self.favorite_count_var.set(
            f"{len(self._visible_favorite_paths)} de {len(self.favorite_tracks)}"
            if q else f"{len(self.favorite_tracks)} favoritos"
        )
        if not self._visible_favorite_paths:
            self.favorite_listbox.insert("end", "Todavía no tienes favoritos")
            return
        for i, path in enumerate(self._visible_favorite_paths, 1):
            marker = "▶ " if path == self.loaded_path and self.playing else "★ "
            self.favorite_listbox.insert(
                "end", f"{marker}{i:02d}. {Path(path).stem}"
            )

    def _tab_widget_paths(self, source):
        if source == "recent":
            return self.recent_listbox, self._visible_recent_paths
        if source == "favorites":
            return self.favorite_listbox, self._visible_favorite_paths
        return self.all_listbox, self._visible_all_paths

    def _open_tab_selected(self, source, _event=None):
        widget, paths = self._tab_widget_paths(source)
        selection = widget.curselection()
        if selection and selection[0] < len(paths):
            self._play_path(paths[selection[0]])

    def _play_path(self, path):
        if not Path(path).is_file():
            messagebox.showwarning(
                "MP3 no disponible",
                "No se encontró el archivo:\n" + str(path), parent=self,
            )
            return
        if path not in self.playlist:
            self.playlist.append(path)
        self._load_track(self.playlist.index(path), autoplay=True)

    def _tab_context_menu(self, source, event):
        widget, paths = self._tab_widget_paths(source)
        if not paths:
            return
        index = widget.nearest(event.y)
        bounds = widget.bbox(index)
        if not bounds or not (bounds[1] <= event.y < bounds[1] + bounds[3]):
            return
        if index < 0 or index >= len(paths):
            return
        widget.selection_clear(0, "end")
        widget.selection_set(index)
        widget.activate(index)
        path = paths[index]
        menu = tk.Menu(widget, tearoff=0)
        menu.add_command(
            label="▶ Reproducir",
            command=lambda selected=path: self._play_path(selected),
        )
        if path in self.favorite_tracks:
            menu.add_command(
                label="★ Quitar de favoritos",
                command=lambda selected=path: self._toggle_favorite(selected),
            )
        else:
            menu.add_command(
                label="☆ Añadir a favoritos",
                command=lambda selected=path: self._toggle_favorite(selected),
            )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _toggle_favorite(self, path):
        if path in self.favorite_tracks:
            self.favorite_tracks.remove(path)
            self.status_var.set("Quitado de favoritos: " + Path(path).stem)
        else:
            self.favorite_tracks.insert(0, path)
            self.status_var.set("Añadido a favoritos: " + Path(path).stem)
        self._refresh_favorites()
        self._refresh_recent()
        self._update_all_row(path)
        self._schedule_save()

    def _init_drag_drop(self):
        """Admite arrastrar MP3 y carpetas a cualquiera de las tres pestañas."""
        try:
            from tkinterdnd2 import DND_FILES, TkinterDnD

            root = self.winfo_toplevel()
            TkinterDnD._require(root)
            for widget in (
                self.recent_listbox, self.favorite_listbox, self.all_listbox
            ):
                TkinterDnD.DnDWrapper.drop_target_register(widget, DND_FILES)
                TkinterDnD.DnDWrapper.dnd_bind(
                    widget, "<<Drop>>", self._on_drop_files
                )
        except Exception:
            pass

    def _on_drop_files(self, event):
        try:
            raw_items = self.tk.splitlist(event.data)
        except Exception:
            raw_items = [getattr(event, "data", "")]

        paths = []
        for raw in raw_items:
            if not raw:
                continue
            p = Path(str(raw))
            if p.is_dir():
                paths.extend(
                    str(x) for x in sorted(
                        p.rglob("*.mp3"), key=lambda q: q.name.lower()
                    )
                )
            elif p.is_file() and p.suffix.lower() == ".mp3":
                paths.append(str(p))

        if paths:
            self._add_paths(paths)
            self.status_var.set(
                f"{len(paths)} elemento(s) recibido(s) por arrastrar y soltar"
            )
        return "copy"

    # ---------- Backends ----------
    def _init_backends(self):
        problems = []
        try:
            import pygame
            pygame.mixer.init()
            self._pygame = pygame
            self.audio_ok = True
        except Exception as exc:
            problems.append(f"Audio: {exc}")

        try:
            from mutagen import File as MutagenFile
            from mutagen.id3 import ID3
            self._mutagen_file = MutagenFile
            self._id3_cls = ID3
        except Exception as exc:
            problems.append(f"Metadata: {exc}")

        try:
            from PIL import Image, ImageTk
            self._image_cls = Image
            self._imagetk = ImageTk
        except Exception as exc:
            problems.append(f"Portadas: {exc}")

        if problems:
            self.status_var.set(" | ".join(problems))
        else:
            self.status_var.set("Audio, metadata y portadas listos")

    def ensure_audio(self):
        if self.audio_ok:
            return True
        messagebox.showerror("Audio no disponible", "No se pudo iniciar pygame para reproducir audio.")
        return False

    # ---------- Playlist ----------
    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="Agregar MP3 a la lista",
            filetypes=[("Archivos MP3", "*.mp3"), ("Todos los archivos", "*.*")],
        )
        self._add_paths(paths)

    def add_folder(self):
        folder = filedialog.askdirectory(title="Agregar carpeta de musica")
        if not folder:
            return
        paths = sorted(Path(folder).rglob("*.mp3"), key=lambda p: p.name.lower())
        self._add_paths([str(p) for p in paths])

    def _add_paths(self, paths):
        added = 0
        existing = set(self.playlist)
        for raw in paths:
            p = Path(raw)
            if p.is_file() and p.suffix.lower() == ".mp3":
                s = str(p.resolve())
                if s not in existing:
                    self.playlist.append(s)
                    existing.add(s)
                    added += 1
        self._refresh_playlist()
        self._schedule_save()
        self.status_var.set(f"{added} archivo(s) agregado(s). Total: {len(self.playlist)}")
        if self.current_index < 0 and self.playlist:
            self.current_index = 0
            self._load_track(0, autoplay=False)

    def _filtered_indices(self):
        """Compatibilidad con la cola de reproduccion existente."""
        q = self.search_var.get().strip().casefold()
        if not q:
            return list(range(len(self.playlist)))
        return [
            i for i, path in enumerate(self.playlist)
            if q in Path(path).stem.casefold()
        ]

    def _refresh_playlist(self):
        """La cola sigue activa para Anterior/Siguiente, pero no ocupa otra pestaña."""
        self.queue_count_var.set(f"Cola: {len(self.playlist)}")

    def _open_selected(self, _event=None):
        """Compatibilidad con versiones anteriores: reproduce la pista de la cola."""
        if self.playlist:
            index = self.current_index if self.current_index >= 0 else 0
            self._load_track(index, autoplay=True)

    def _refresh_recent(self):
        self.recent_listbox.delete(0, "end")
        q = self.search_var.get().strip().casefold()
        self._visible_recent_paths = [
            path for path in self.recent_tracks if self._matches_search(path, q)
        ]
        self.recent_count_var.set(
            f"{len(self._visible_recent_paths)} de {len(self.recent_tracks)}"
            if q else f"{len(self.recent_tracks)} escuchadas"
        )
        if not self._visible_recent_paths:
            self.recent_listbox.insert("end", "Aún no hay canciones recientes")
            return
        for i, path in enumerate(self._visible_recent_paths, 1):
            marker = "▶ " if path == self.loaded_path and self.playing else ""
            self.recent_listbox.insert(
                "end", f"{marker}{i:02d}. {Path(path).stem}"
            )

    def _mark_recent(self, path):
        """Registra una pista solo después de iniciar la reproducción."""
        if not path:
            return
        normalized = str(Path(path).expanduser().resolve())
        self.recent_tracks = [
            normalized, *(item for item in self.recent_tracks if item != normalized)
        ][:40]
        self._refresh_recent()
        self._schedule_save()

    def _open_recent(self, _event=None):
        self._open_tab_selected("recent", _event)

    def clear_recent(self):
        """Borra el historial sin eliminar canciones ni modificar la playlist."""
        if not self.recent_tracks:
            return
        if not messagebox.askyesno(
            "Borrar historial",
            "¿Borrar las canciones escuchadas recientemente?\n"
            "No se eliminarán los archivos MP3 ni la lista actual.",
            parent=self,
        ):
            return
        self.recent_tracks = []
        self._refresh_recent()
        self._schedule_save()
        self.status_var.set("Historial de recientes borrado")

    def remove_selected(self):
        """Compatibilidad: elimina la pista actual de la cola, no del disco."""
        path = self.current_path()
        if not path:
            return
        self.playlist.remove(path)
        if self.playlist:
            self.current_index = min(self.current_index, len(self.playlist) - 1)
            self._load_track(self.current_index, autoplay=False)
        else:
            self.current_index = -1
            self.stop(reset_ui=True)
        self._refresh_playlist()
        self._schedule_save()

    def clear_playlist(self):
        if self.playlist and not messagebox.askyesno("Limpiar lista", "¿Quitar todas las canciones de la lista de reproduccion?"):
            return
        self.stop(reset_ui=True)
        self.playlist = []
        self.current_index = -1
        # Limpiar la lista actual no elimina el historial ni las posiciones guardadas.
        self._refresh_playlist()
        self._schedule_save()

    def current_path(self):
        if 0 <= self.current_index < len(self.playlist):
            return self.playlist[self.current_index]
        return None

    # ---------- Metadata y portada ----------
    def _read_metadata(self, path):
        title = Path(path).stem
        artist = "Artista desconocido"
        album = "Album desconocido"
        duration = 0.0
        cover = None

        if self._mutagen_file is not None:
            try:
                audio = self._mutagen_file(path, easy=True)
                if audio is not None:
                    info = getattr(audio, "info", None)
                    duration = float(getattr(info, "length", 0.0) or 0.0)
                    tags = getattr(audio, "tags", None) or {}
                    title = (tags.get("title") or [title])[0]
                    artist = (tags.get("artist") or [artist])[0]
                    album = (tags.get("album") or [album])[0]
            except Exception:
                pass

        if self._id3_cls is not None:
            try:
                tags = self._id3_cls(path)
                for tag in tags.values():
                    if getattr(tag, "FrameID", "") == "APIC" and getattr(tag, "data", None):
                        cover = bytes(tag.data)
                        break
            except Exception:
                pass

        return str(title), str(artist), str(album), duration, cover

    def _set_cover(self, data):
        self.cover_photo = None
        if data and self._image_cls is not None and self._imagetk is not None:
            try:
                image = self._image_cls.open(io.BytesIO(data)).convert("RGB")
                image.thumbnail((180, 180))
                canvas = self._image_cls.new("RGB", (180, 180), (32, 37, 43))
                x = (180 - image.width) // 2
                y = (180 - image.height) // 2
                canvas.paste(image, (x, y))
                self.cover_photo = self._imagetk.PhotoImage(canvas)
                self.cover_label.configure(image=self.cover_photo, text="")
                return
            except Exception:
                pass
        self.cover_label.configure(image="", text="♫")

    # ---------- Reproduccion ----------
    def _load_track(self, index, autoplay=False, start_position=None):
        if not self.playlist or not (0 <= index < len(self.playlist)):
            return False
        if not self.ensure_audio():
            return False

        self._remember_position()
        path = self.playlist[index]
        if not Path(path).is_file():
            self.status_var.set("El archivo ya no existe: " + Path(path).name)
            return False

        try:
            self._pygame.mixer.music.stop()
            self._pygame.mixer.music.load(path)
            self.playing = False
        except Exception as exc:
            messagebox.showerror("No se pudo abrir el MP3", str(exc))
            return False

        self.current_index = index
        self.loaded_path = path
        title, artist, album, duration, cover = self._read_metadata(path)
        self.duration = duration
        self.title_var.set(title)
        self.artist_var.set(artist)
        self.album_var.set(album)
        self._set_cover(cover)
        self.paused = False
        self.play_btn.configure(text="▶")
        self.finished_guard = False

        resume = self._resume_positions.get(path, 0.0) if start_position is None else float(start_position)
        if self.duration and resume >= max(0.0, self.duration - 3):
            resume = 0.0
        self.base_position = max(0.0, resume)
        self.progress.set(self._position_to_progress(self.base_position))
        self._update_time_label(self.base_position)
        self._refresh_playlist()
        self._schedule_save()

        if autoplay:
            self._start_playback(self.base_position)
        else:
            self.status_var.set(
                f"Listo: {title}" + (f" · reanuda en {self._fmt_time(self.base_position)}" if self.base_position > 1 else "")
            )
        return True

    def _start_playback(self, position=0.0):
        """Inicia la reproducción y activa un reloj independiente de get_busy()."""
        if not self.ensure_audio():
            return False
        if not self.loaded_path:
            if not self.playlist:
                self.add_files()
                return False
            index = self.current_index if 0 <= self.current_index < len(self.playlist) else 0
            if not self._load_track(index, autoplay=False):
                return False
        position = max(0.0, float(position))
        if self.duration > 0:
            position = min(position, self.duration)
        try:
            self._pygame.mixer.music.play(start=position)
        except Exception:
            try:
                self._pygame.mixer.music.play()
                if position > 0:
                    self._pygame.mixer.music.set_pos(position)
            except Exception as exc:
                self.playing = False
                self.paused = False
                messagebox.showerror("Error de reproducción", str(exc), parent=self)
                return False
        self.base_position = position
        self.started_ticks = time.monotonic()
        self.playing = True
        self.paused = False
        self.finished_guard = False
        self.play_btn.configure(text="⏸")
        self.progress.set(self._position_to_progress(position))
        self._update_time_label(position)
        self.status_var.set(f"Reproduciendo · {self.title_var.get()}")
        self._mark_recent(self.loaded_path)
        self._refresh_favorites()
        return True


    def play_pause(self):
        """Pausa/reanuda por estado propio, nunca por get_busy()."""
        if not self.ensure_audio():
            return
        if not self.playlist:
            self.add_files()
            return
        if self.current_index < 0:
            if not self._load_track(0, autoplay=False):
                return
        if self.loaded_path != self.current_path():
            if not self._load_track(self.current_index, autoplay=False):
                return
        if self.paused and self.playing:
            try:
                self._pygame.mixer.music.unpause()
            except Exception as exc:
                messagebox.showerror("Reanudar", str(exc), parent=self)
                return
            self.started_ticks = time.monotonic()
            self.paused = False
            self.play_btn.configure(text="⏸")
            self.status_var.set(f"Reproduciendo · {self.title_var.get()}")
            return
        if self.playing:
            position = self.current_position()
            try:
                self._pygame.mixer.music.pause()
            except Exception as exc:
                messagebox.showerror("Pausar", str(exc), parent=self)
                return
            self.base_position = position
            self.paused = True
            self.play_btn.configure(text="▶")
            self.progress.set(self._position_to_progress(position))
            self._update_time_label(position)
            self.status_var.set("Pausado · posición conservada")
            self._resume_positions[self.loaded_path] = position
            self._schedule_save()
            return
        self._start_playback(self.base_position)


    def stop(self, reset_ui=False):
        self._remember_position(freeze=True)
        if self.audio_ok:
            try:
                self._pygame.mixer.music.stop()
            except Exception:
                pass
        self.playing = False
        self.paused = False
        self.finished_guard = True
        self.play_btn.configure(text="▶")
        if reset_ui:
            self.loaded_path = None
            self.duration = 0.0
            self.base_position = 0.0
            self.progress.set(0)
            self.title_var.set("Sin reproducción")
            self.artist_var.set("Selecciona o agrega canciones")
            self.album_var.set("")
            self.time_var.set("0:00 / 0:00")
            self._set_cover(None)
        else:
            self.status_var.set("Detenido · posición guardada")
        self._schedule_save()


    def previous_track(self):
        if not self.playlist:
            return
        pos = self.current_position()
        if pos > 5:
            self.seek(0)
            return
        idx = (self.current_index - 1) % len(self.playlist)
        self._load_track(idx, autoplay=True, start_position=0)

    def next_track(self):
        if not self.playlist:
            return
        idx = (self.current_index + 1) % len(self.playlist)
        self._load_track(idx, autoplay=True, start_position=0)

    def seek(self, seconds):
        """Mover la barra conserva el estado de pausa o detención."""
        if not self.loaded_path:
            return
        seconds = max(0.0, float(seconds))
        if self.duration > 0:
            seconds = min(seconds, self.duration)
        was_paused = self.paused
        was_playing = self.playing
        if was_playing:
            if not self._start_playback(seconds):
                return
            if was_paused:
                try:
                    self._pygame.mixer.music.pause()
                except Exception as exc:
                    messagebox.showerror("Pausar", str(exc), parent=self)
                    return
                self.base_position = seconds
                self.paused = True
                self.play_btn.configure(text="▶")
                self.status_var.set("Pausado · posición conservada")
        else:
            self.base_position = seconds
            self.progress.set(self._position_to_progress(seconds))
            self._update_time_label(seconds)
        self._resume_positions[self.loaded_path] = seconds
        self._schedule_save()


    def current_position(self):
        """Reloj monotónico que no se congela si pygame reporta busy=False."""
        if not self.loaded_path:
            return 0.0
        if not self.playing or self.paused:
            return self.base_position
        elapsed = max(0.0, time.monotonic() - self.started_ticks)
        position = self.base_position + elapsed
        return min(position, self.duration) if self.duration > 0 else position


    def _remember_position(self, freeze=False):
        """Guarda la posición sin alterar el reloj mientras suena la canción."""
        path = self.loaded_path
        if not path:
            return
        position = self.current_position()
        if self.duration and position >= max(0.0, self.duration - 2):
            position = 0.0
        position = max(0.0, position)
        if freeze or not self.playing or self.paused:
            self.base_position = position
        self._resume_positions[path] = position

    # ---------- Progreso / volumen ----------


    def _position_to_progress(self, position):
        if self.duration <= 0:
            return 0.0
        return max(0.0, min(1000.0, (position / self.duration) * 1000.0))

    def _progress_to_position(self):
        if self.duration <= 0:
            return 0.0
        return (float(self.progress.get()) / 1000.0) * self.duration

    def _progress_press(self, _event=None):
        self.dragging_progress = True

    def _progress_drag(self, _value=None):
        if self.dragging_progress:
            self._update_time_label(self._progress_to_position())

    def _progress_release(self, _event=None):
        if not self.dragging_progress:
            return
        self.dragging_progress = False
        self.seek(self._progress_to_position())

    def _volume_changed(self, _value=None):
        self._apply_volume()
        self._schedule_save()

    def _apply_volume(self):
        value = max(0, min(100, int(float(self.volume.get()))))
        self.volume_label.configure(text=f"{value}%")
        if self.audio_ok:
            try:
                self._pygame.mixer.music.set_volume(value / 100.0)
            except Exception:
                pass

    # ---------- Temporizador ----------
    def _tick(self):
        """Actualiza barra/tiempo y detecta el fin sin perder el temporizador."""
        try:
            if self.loaded_path:
                pos = self.current_position()
                if not self.dragging_progress:
                    self.progress.set(self._position_to_progress(pos))
                    self._update_time_label(pos)
                if self.playing and not self.paused and self.duration > 0:
                    # get_busy sólo se consulta para detectar el final real;
                    # nunca para avanzar el reloj ni para decidir si pausar.
                    try:
                        busy = bool(self._pygame.mixer.music.get_busy())
                    except Exception:
                        busy = True
                    if (not busy and pos >= max(0.0, self.duration - 0.75)
                            and not self.finished_guard
                            and time.monotonic() - self.started_ticks > 0.5):
                        self.finished_guard = True
                        self.playing = False
                        self._resume_positions[self.loaded_path] = 0.0
                        self.base_position = 0.0
                        self.next_track()
                now = time.monotonic()
                if now - self._last_position_save >= 8.0:
                    self._last_position_save = now
                    if self.loaded_path:
                        self._resume_positions[self.loaded_path] = self.current_position()
                    self._schedule_save()
        except tk.TclError:
            return
        except Exception as exc:
            # Un error puntual no debe detener para siempre la barra.
            try:
                self.status_var.set(f"Aviso del reproductor: {exc}")
            except Exception:
                pass
        try:
            if self.winfo_exists():
                self.after(250, self._tick)
        except tk.TclError:
            pass


    def _update_time_label(self, position):
        self.time_var.set(f"{self._fmt_time(position)} / {self._fmt_time(self.duration)}")

    @staticmethod
    def _fmt_time(seconds):
        try:
            seconds = max(0, int(seconds or 0))
        except Exception:
            seconds = 0
        return f"{seconds // 60}:{seconds % 60:02d}"

    # ---------- Escaneo completo del equipo y cache ----------

    def _scan_cache_path(self):
        return self.state_path.with_name("all_mp3_cache.json")

    def _load_scan_cache(self):
        """Carga el indice persistente sin volver a leer cada MP3."""
        try:
            cache_path = self._scan_cache_path()
            if not cache_path.is_file():
                return
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 1:
                return
            for item in data.get("tracks", []):
                if not isinstance(item, dict):
                    continue
                path = item.get("path")
                if not isinstance(path, str) or not path.lower().endswith(".mp3"):
                    continue
                duration = float(item.get("duration", 0))
                entry = {
                    "path": path,
                    "duration": duration,
                    "size": int(item.get("size", -1)),
                    "mtime_ns": int(item.get("mtime_ns", -1)),
                }
                self._all_index[path] = entry
                if duration > 60.0:
                    self.all_tracks[path] = duration
            self.scan_status_var.set(
                f"Caché cargada: {len(self.all_tracks)} MP3 de más de 1 minuto"
            )
        except (OSError, ValueError, TypeError, KeyError):
            self._all_index = {}
            self.all_tracks = {}

    def _scan_roots(self):
        """Discos locales Windows; en Linux incluye / y montajes accesibles."""
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
                # 2 extraible, 3 fijo, 5 CD/DVD. Evita unidades de red.
                if kernel.GetDriveTypeW(drive) in (2, 3, 5):
                    roots.append(drive)
            return roots
        except Exception:
            return [os.path.abspath(os.sep)]

    def start_scan(self):
        """Muestra la cache existente y busca solo archivos nuevos o modificados."""
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
            f"Caché: {len(self.all_tracks)} MP3 · "
            "buscando únicamente archivos nuevos o modificados..."
        )
        self._scan_thread = threading.Thread(
            target=self._scan_worker, daemon=True, name="PTM-MP3-Scan"
        )
        self._scan_thread.start()

    def stop_scan(self):
        if self._scan_thread and self._scan_thread.is_alive():
            self._scan_cancel.set()
            self.scan_status_var.set("Deteniendo búsqueda...")

    def _queue_scan_message(self, message, force=False):
        """Envia resultados al hilo de Tk, incluso el cierre de un escaneo cancelado."""
        if force:
            try:
                self._scan_queue.put(message, timeout=1.5)
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

    def _write_scan_cache(self, previous, updates):
        """Fusiona la cache previa con novedades y escribe un JSON atomico."""
        if not updates:
            return
        merged = dict(previous)
        merged.update(updates)
        cache_path = self._scan_cache_path()
        tmp = cache_path.with_suffix(".tmp")
        try:
            tmp.write_text(
                json.dumps(
                    {"version": 1, "tracks": list(merged.values())},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            os.replace(tmp, cache_path)
        finally:
            # Si falla la escritura no debe quedar un archivo temporal suelto.
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    def _scan_worker(self):
        """Indexa de forma incremental: reutiliza la cache sin reabrir MP3 antiguos.

        Se recorren carpetas para detectar rutas nuevas, pero los MP3 con
        mismo tamaño y fecha no se vuelven a analizar con mutagen.
        La cache anterior nunca se reemplaza por un subconjunto del escaneo.
        """
        previous = dict(self._all_index)
        updates = {}
        batch = []
        directories = 0
        found_mp3 = 0
        reused = 0
        added = 0
        changed = 0
        valid_new = 0
        error = ""
        cache_error = ""
        last_checkpoint = time.monotonic()
        try:
            from mutagen.mp3 import MP3

            skip_root_dirs = {"proc", "sys", "dev"}
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
                        dirs[:] = [d for d in dirs if d not in skip_root_dirs]
                    dirs[:] = [
                        d for d in dirs
                        if not os.path.islink(os.path.join(folder, d))
                    ]
                    directories += 1
                    for filename in files:
                        if self._scan_cancel.is_set():
                            break
                        if not filename.lower().endswith(".mp3"):
                            continue
                        path = os.path.join(folder, filename)
                        try:
                            stat = os.stat(path)
                        except OSError:
                            continue
                        found_mp3 += 1
                        cached = previous.get(path)
                        if (cached and cached.get("size") == stat.st_size
                                and cached.get("mtime_ns") == stat.st_mtime_ns):
                            reused += 1
                            continue

                        # Leer duracion solamente en MP3 nuevos o modificados.
                        try:
                            duration = float(MP3(path).info.length)
                        except Exception:
                            duration = 0.0
                        updates[path] = {
                            "path": path,
                            "duration": duration,
                            "size": stat.st_size,
                            "mtime_ns": stat.st_mtime_ns,
                        }
                        if cached is None:
                            added += 1
                        else:
                            changed += 1
                        if duration > 60.0:
                            valid_new += 1
                            batch.append((path, duration))
                            if len(batch) >= 20:
                                if not self._queue_scan_message(("batch", batch)):
                                    break
                                batch = []

                        # Guardar avances mientras se escanea sin bloquear Tk.
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
                            ("progress", directories, found_mp3, valid_new, reused)
                        ):
                            break
                    if self._scan_cancel.is_set():
                        break
        except Exception as exc:
            error = str(exc)
        finally:
            # Enviar también el grupo incompleto de 1 a 19 canciones.
            if batch:
                self._queue_scan_message(("batch", batch), force=True)
            # Conservar el cache anterior y añadir los registros descubiertos,
            # incluso cuando el usuario detuvo el escaneo.
            if updates:
                try:
                    self._write_scan_cache(previous, updates)
                    cache_error = ""
                except OSError as exc:
                    cache_error = str(exc)
            self._queue_scan_message(
                (
                    "finished", updates, directories, found_mp3, reused,
                    added, changed, valid_new, self._scan_cancel.is_set(),
                    error, cache_error,
                ),
                force=True,
            )

    def _poll_scan_queue(self):
        """Aplica lotes nuevos sin borrar ni reconstruir el indice en cache."""
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
                    _, directories, mp3_count, new_valid, reused = message
                    self.scan_status_var.set(
                        f"Buscando... {directories} carpetas · "
                        f"{reused} MP3 reutilizados · {new_valid} válidos nuevos"
                    )
                elif kind == "finished":
                    (
                        _, updates, directories, mp3_count, reused,
                        added, changed, new_valid, cancelled, error, cache_error,
                    ) = message
                    self._all_index.update(updates)
                    refresh_needed = False
                    for path, entry in updates.items():
                        duration = float(entry.get("duration", 0))
                        if duration > 60.0:
                            self.all_tracks[path] = duration
                        elif path in self.all_tracks:
                            self.all_tracks.pop(path, None)
                            refresh_needed = True
                    if refresh_needed:
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
                            f"{added} nuevos · {changed} actualizados · "
                            f"{len(self.all_tracks)} MP3 válidos en Todos"
                        )
                    if cache_error:
                        self.scan_status_var.set(
                            "No se pudo guardar la caché: " + cache_error
                        )
            if self._scan_thread and not self._scan_thread.is_alive():
                self.stop_scan_btn.configure(state="disabled")
                if self._scan_active and self._scan_queue.empty():
                    self._scan_active = False
                    if self._scan_cancel.is_set():
                        self.scan_status_var.set("Escaneo detenido · caché conservada")
        except tk.TclError:
            return
        try:
            if self.winfo_exists():
                self.after(150, self._poll_scan_queue)
        except tk.TclError:
            pass

    def _all_row_text(self, path):
        duration = self.all_tracks.get(path, 0)
        star = "★ " if path in self.favorite_tracks else ""
        return f"{star}{Path(path).stem}   ·   {self._fmt_time(duration)}"

    def _refresh_all(self):
        """Pinta el listado en lotes para evitar congelar la interfaz."""
        self._all_render_token += 1
        token = self._all_render_token
        self._all_rendering = True
        self.all_listbox.delete(0, "end")
        q = self.search_var.get().strip().casefold()
        self._visible_all_paths = sorted(
            (path for path in self.all_tracks if self._matches_search(path, q)),
            key=lambda path: (Path(path).name.casefold(), path.casefold()),
        )
        self.all_count_var.set(
            f"{len(self._visible_all_paths)} de {len(self.all_tracks)} MP3"
            if q else f"{len(self.all_tracks)} MP3 de más de 1 minuto"
        )
        if not self._visible_all_paths:
            self._all_rendering = False
            self.all_listbox.insert("end", "Sin MP3 encontrados · pulsa Escanear")
            return
        self._render_all_chunk(token, 0)

    def _render_all_chunk(self, token, offset):
        if token != self._all_render_token:
            return
        end = min(offset + 20, len(self._visible_all_paths))
        for path in self._visible_all_paths[offset:end]:
            self.all_listbox.insert("end", self._all_row_text(path))
        if end < len(self._visible_all_paths):
            self.after(1, lambda: self._render_all_chunk(token, end))
        else:
            self._all_rendering = False

    def _append_all_batch(self, batch):
        """Enlista MP3 en grupos de 20 a medida que llegan del escaneo.

        Si hay un renderizado de cache en curso, agrega los nuevos al trabajo
        pendiente para no perder coincidencias.
        """
        q = self.search_var.get().strip().casefold()
        for path, duration in batch:
            old = self.all_tracks.get(path)
            self.all_tracks[path] = duration
            if old is not None:
                if old != duration:
                    self._update_all_row(path)
                continue
            if not self._matches_search(path, q):
                continue
            # Actualizar siempre el indice visible, aunque la cache
            # todavia este dibujandose en lotes.
            if not self._visible_all_paths and not self._all_rendering:
                self.all_listbox.delete(0, "end")
            self._visible_all_paths.append(path)
            if not self._all_rendering:
                self.all_listbox.insert("end", self._all_row_text(path))
        self.all_count_var.set(
            f"{len(self._visible_all_paths)} de {len(self.all_tracks)} MP3"
            if q else f"{len(self.all_tracks)} MP3 de más de 1 minuto"
        )

    def _update_all_row(self, path):
        try:
            i = self._visible_all_paths.index(path)
            if i < self.all_listbox.size():
                self.all_listbox.delete(i)
                self.all_listbox.insert(i, self._all_row_text(path))
        except (ValueError, tk.TclError):
            pass

    def on_close(self):
        self._scan_cancel.set()
        self._all_render_token += 1
        self._remember_position()
        self._save_state()
        if self.audio_ok:
            try:
                self._pygame.mixer.music.stop()
                self._pygame.mixer.music.unload()
            except Exception:
                pass


App = Mp3PlayerTool


def main():
    root = tk.Tk()
    root.title(TOOL_NAME)
    root.geometry("980x560")
    root.minsize(760, 430)

    tool = App(root)
    tool.pack(fill="both", expand=True)

    def close_window():
        tool.on_close()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close_window)
    root.mainloop()


if __name__ == "__main__":
    main()