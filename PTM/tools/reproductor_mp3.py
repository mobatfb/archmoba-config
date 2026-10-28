# ARGUMENTOS: mp3 audio musica music reproductor player playlist lista reproduccion portada album artista id3 reanudar resume posicion pygame mutagen pillow
import io
import json
import os
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

TOOL_NAME = "Reproductor MP3"
TOOL_DESCRIPTION = "Reproductor MP3 profesional con playlist, portada, metadata ID3 y reanudacion de reproduccion."
TOOL_VERSION = "2.0.1"


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
        self.current_index = -1
        self.loaded_path = None
        self.duration = 0.0
        self.base_position = 0.0
        self.started_ticks = 0.0
        self.paused = False
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

        self.state_path = self._state_file()
        self._build_ui()
        self._init_drag_drop()
        self._init_backends()
        self._load_state()
        self._refresh_playlist()
        self._apply_volume()
        self.after(250, self._tick)

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
                "version": 2,
                "playlist": self.playlist,
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

        # Biblioteca / playlist
        left = ttk.Frame(body, padding=6)
        body.add(left, weight=2)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(4, weight=1)

        ttk.Label(
            left, text="Lista de reproduccion", font=("Segoe UI", 11, "bold")
        ).grid(row=0, column=0, sticky="w")

        actions = ttk.Frame(left)
        actions.grid(row=1, column=0, sticky="ew", pady=(6, 5))
        ttk.Button(actions, text="+ Archivos", command=self.add_files).pack(side="left")
        ttk.Button(actions, text="+ Carpeta", command=self.add_folder).pack(
            side="left", padx=5
        )
        ttk.Button(actions, text="Quitar", command=self.remove_selected).pack(side="left")
        ttk.Button(actions, text="Limpiar", command=self.clear_playlist).pack(
            side="left", padx=5
        )

        self.drop_hint = ttk.Label(
            left,
            text="Arrastra aqui archivos MP3 o carpetas",
            style="Muted.TLabel",
            anchor="w",
        )
        self.drop_hint.grid(row=2, column=0, sticky="ew", pady=(0, 4))

        search = ttk.Entry(left, textvariable=self.search_var)
        search.grid(row=3, column=0, sticky="ew", pady=(0, 5))
        self.search_var.trace_add("write", lambda *_: self._refresh_playlist())

        list_frame = ttk.Frame(left)
        list_frame.grid(row=4, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self.listbox = tk.Listbox(
            list_frame,
            activestyle="none",
            selectmode="extended",
            bd=0,
            highlightthickness=1,
            font=("Segoe UI", 9),
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.bind("<Double-Button-1>", self._open_selected)
        self.listbox.bind("<Return>", self._open_selected)

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

    def _init_drag_drop(self):
        """Activa arrastrar y soltar archivos/carpetas sobre la playlist."""
        try:
            from tkinterdnd2 import DND_FILES, TkinterDnD

            root = self.winfo_toplevel()
            TkinterDnD._require(root)

            # Los widgets tkinter normales pueden usar directamente el wrapper
            # de tkinterdnd2 una vez cargado tkdnd en el interprete Tcl.
            TkinterDnD.DnDWrapper.drop_target_register(self.listbox, DND_FILES)
            TkinterDnD.DnDWrapper.dnd_bind(
                self.listbox, "<<Drop>>", self._on_drop_files
            )
            TkinterDnD.DnDWrapper.drop_target_register(self.drop_hint, DND_FILES)
            TkinterDnD.DnDWrapper.dnd_bind(
                self.drop_hint, "<<Drop>>", self._on_drop_files
            )
            self.drop_hint.configure(
                text="Arrastra aqui archivos MP3 o carpetas"
            )
        except Exception:
            self.drop_hint.configure(
                text="Arrastrar y soltar no disponible · usa + Archivos / + Carpeta"
            )

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
        q = self.search_var.get().strip().lower()
        if not q:
            return list(range(len(self.playlist)))
        result = []
        for i, path in enumerate(self.playlist):
            if q in Path(path).stem.lower():
                result.append(i)
        return result

    def _refresh_playlist(self):
        self.listbox.delete(0, "end")
        self._visible_indices = self._filtered_indices()
        for number, idx in enumerate(self._visible_indices, start=1):
            p = Path(self.playlist[idx])
            marker = "▶ " if idx == self.current_index else ""
            self.listbox.insert("end", f"{marker}{number:02d}. {p.stem}")
        if self.current_index in self._visible_indices:
            pos = self._visible_indices.index(self.current_index)
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(pos)
            self.listbox.see(pos)

    def _open_selected(self, _event=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        visible = self._visible_indices[sel[0]]
        self._load_track(visible, autoplay=True)

    def remove_selected(self):
        selected = list(self.listbox.curselection())
        if not selected:
            return
        actual = sorted({self._visible_indices[i] for i in selected}, reverse=True)
        current_path = self.current_path()
        for idx in actual:
            path = self.playlist.pop(idx)
            self._resume_positions.pop(path, None)
        if current_path and current_path in self.playlist:
            self.current_index = self.playlist.index(current_path)
        elif self.playlist:
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
        self._resume_positions = {}
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
        if not self.loaded_path and self.current_path():
            if not self._load_track(self.current_index, autoplay=False):
                return
        if not self.loaded_path:
            if self.playlist:
                self._load_track(0, autoplay=False)
            else:
                self.add_files()
                return
        try:
            self._pygame.mixer.music.play(start=max(0.0, float(position)))
        except Exception:
            try:
                self._pygame.mixer.music.play()
                if position > 0:
                    self._pygame.mixer.music.set_pos(float(position))
            except Exception as exc:
                messagebox.showerror("Error de reproduccion", str(exc))
                return
        self.base_position = max(0.0, float(position))
        self.started_ticks = time.monotonic()
        self.paused = False
        self.finished_guard = False
        self.play_btn.configure(text="⏸")
        self.status_var.set(f"Reproduciendo · {self.title_var.get()}")

    def play_pause(self):
        if not self.playlist:
            self.add_files()
            return
        if self.current_index < 0:
            self._load_track(0, autoplay=False)

        if self.loaded_path != self.current_path():
            self._load_track(self.current_index, autoplay=False)

        try:
            busy = self._pygame.mixer.music.get_busy() if self.audio_ok else False
        except Exception:
            busy = False

        if self.paused:
            try:
                self._pygame.mixer.music.unpause()
                self.started_ticks = time.monotonic()
                self.paused = False
                self.play_btn.configure(text="⏸")
                self.status_var.set(f"Reproduciendo · {self.title_var.get()}")
            except Exception as exc:
                messagebox.showerror("Error", str(exc))
        elif busy:
            self._remember_position()
            try:
                self._pygame.mixer.music.pause()
                self.paused = True
                self.play_btn.configure(text="▶")
                self.status_var.set("Pausa · posicion guardada")
                self._schedule_save()
            except Exception as exc:
                messagebox.showerror("Error", str(exc))
        else:
            self._start_playback(self.base_position)

    def stop(self, reset_ui=False):
        self._remember_position()
        if self.audio_ok:
            try:
                self._pygame.mixer.music.stop()
            except Exception:
                pass
        self.paused = False
        self.play_btn.configure(text="▶")
        if reset_ui:
            self.loaded_path = None
            self.duration = 0.0
            self.base_position = 0.0
            self.progress.set(0)
            self.title_var.set("Sin reproduccion")
            self.artist_var.set("Selecciona o agrega canciones")
            self.album_var.set("")
            self.time_var.set("0:00 / 0:00")
            self._set_cover(None)
        else:
            self.status_var.set("Detenido · posicion guardada")
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
        if not self.loaded_path:
            return
        seconds = max(0.0, min(float(seconds), self.duration if self.duration else float(seconds)))
        was_paused = self.paused
        self._start_playback(seconds)
        if was_paused:
            try:
                self._pygame.mixer.music.pause()
                self.paused = True
                self.play_btn.configure(text="▶")
            except Exception:
                pass
        self._resume_positions[self.loaded_path] = seconds
        self._schedule_save()

    def current_position(self):
        if not self.loaded_path:
            return 0.0
        if self.paused:
            return self.base_position
        try:
            busy = self._pygame.mixer.music.get_busy()
        except Exception:
            busy = False
        if not busy:
            return self.base_position
        elapsed = max(0.0, time.monotonic() - self.started_ticks)
        return self.base_position + elapsed

    def _remember_position(self):
        path = self.loaded_path
        if not path:
            return
        pos = self.current_position()
        if self.duration and pos >= max(0.0, self.duration - 2):
            pos = 0.0
        self.base_position = max(0.0, pos)
        self._resume_positions[path] = self.base_position

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
        try:
            if self.loaded_path:
                pos = self.current_position()
                if not self.dragging_progress:
                    self.progress.set(self._position_to_progress(pos))
                    self._update_time_label(pos)

                if not self.paused and self.duration > 0:
                    try:
                        busy = self._pygame.mixer.music.get_busy() if self.audio_ok else False
                    except Exception:
                        busy = False
                    if not busy and pos >= max(0.0, self.duration - 1.2) and not self.finished_guard:
                        self.finished_guard = True
                        self._resume_positions[self.loaded_path] = 0.0
                        self.base_position = 0.0
                        self.next_track()

                # Persistencia periodica sin escribir cada 250 ms.
                if int(time.monotonic()) % 8 == 0:
                    self._resume_positions[self.loaded_path] = pos
            self.after(250, self._tick)
        except tk.TclError:
            return

    def _update_time_label(self, position):
        self.time_var.set(f"{self._fmt_time(position)} / {self._fmt_time(self.duration)}")

    @staticmethod
    def _fmt_time(seconds):
        try:
            seconds = max(0, int(seconds or 0))
        except Exception:
            seconds = 0
        return f"{seconds // 60}:{seconds % 60:02d}"

    def on_close(self):
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