# ARGUMENTOS: mp3 audio musica music reproductor player reproducir play pausa pause detener stop volumen volume abrir archivo sonido
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

TOOL_NAME = "Reproductor MP3 básico"
TOOL_DESCRIPTION = "Abre y reproduce archivos MP3 con controles de reproducir, pausar, detener y volumen."


class Mp3PlayerTool(ttk.Frame):
    def __init__(self, parent, app=None):
        super().__init__(parent)
        self.app = app
        self.file_path = tk.StringVar()
        self.track_name = tk.StringVar(value="Ningún MP3 seleccionado")
        self.status = tk.StringVar(value="Selecciona un archivo MP3 para comenzar.")
        self.volume = tk.DoubleVar(value=70)
        self.paused = False
        self.loaded = False
        self.audio_ok = False
        self._pygame = None

        self._build_ui()
        self._init_audio()

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 14))

        if self.app is not None:
            ttk.Button(
                top,
                text="← Volver al buscador de herramientas",
                command=self.app.show_home,
            ).pack(side="left")

        ttk.Label(top, text=TOOL_NAME, font=("Segoe UI", 15, "bold")).pack(
            side="left", padx=12
        )

        box = ttk.LabelFrame(self, text="Archivo de audio", padding=16)
        box.pack(fill="x")

        ttk.Entry(box, textvariable=self.file_path, state="readonly").grid(
            row=0, column=0, sticky="ew", padx=(0, 8)
        )
        ttk.Button(box, text="Abrir MP3...", command=self.choose_file).grid(
            row=0, column=1
        )
        box.columnconfigure(0, weight=1)

        ttk.Label(
            self,
            textvariable=self.track_name,
            font=("Segoe UI", 12, "bold"),
            anchor="center",
        ).pack(fill="x", pady=(24, 12))

        controls = ttk.Frame(self)
        controls.pack(pady=8)

        self.play_btn = ttk.Button(
            controls, text="▶ Reproducir", command=self.play, width=16
        )
        self.play_btn.grid(row=0, column=0, padx=5)

        self.pause_btn = ttk.Button(
            controls, text="⏸ Pausar", command=self.pause_resume, width=16
        )
        self.pause_btn.grid(row=0, column=1, padx=5)

        self.stop_btn = ttk.Button(
            controls, text="■ Detener", command=self.stop, width=16
        )
        self.stop_btn.grid(row=0, column=2, padx=5)

        volume_box = ttk.LabelFrame(self, text="Volumen", padding=12)
        volume_box.pack(fill="x", pady=(20, 8))

        self.volume_scale = ttk.Scale(
            volume_box,
            from_=0,
            to=100,
            variable=self.volume,
            command=self.change_volume,
        )
        self.volume_scale.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self.volume_label = ttk.Label(volume_box, text="70%", width=6)
        self.volume_label.pack(side="right")

        ttk.Label(self, textvariable=self.status, wraplength=900).pack(
            anchor="w", pady=(18, 6)
        )
        ttk.Label(
            self,
            text="Dependencia: pygame. Si no está instalado: pip install pygame",
        ).pack(anchor="w", pady=(4, 0))

    def _init_audio(self):
        try:
            import pygame

            pygame.mixer.init()
            pygame.mixer.music.set_volume(self.volume.get() / 100)
            self._pygame = pygame
            self.audio_ok = True
            self.status.set("Audio listo. Selecciona un archivo MP3.")
        except ModuleNotFoundError:
            self.audio_ok = False
            self.status.set("Falta pygame. Instálalo con: pip install pygame")
        except Exception as exc:
            self.audio_ok = False
            self.status.set(f"No se pudo iniciar el sistema de audio: {exc}")

    def ensure_audio(self):
        if self.audio_ok:
            return True
        messagebox.showerror(
            "Audio no disponible",
            "No se pudo iniciar pygame.\n\nInstala la dependencia con:\n\npip install pygame",
        )
        return False

    def choose_file(self):
        path = filedialog.askopenfilename(
            title="Seleccionar archivo MP3",
            filetypes=[("Archivos MP3", "*.mp3"), ("Todos los archivos", "*.*")],
        )
        if not path:
            return

        self.stop()
        self.file_path.set(path)
        self.track_name.set(Path(path).name)
        self.loaded = False
        self.paused = False
        self.pause_btn.configure(text="⏸ Pausar")
        self.status.set(f"Seleccionado: {Path(path).name}")

    def load_current(self):
        if not self.ensure_audio():
            return False

        path = Path(self.file_path.get().strip())
        if not path.is_file():
            messagebox.showinfo("Sin archivo", "Selecciona primero un archivo MP3.")
            return False

        try:
            self._pygame.mixer.music.load(str(path))
            self.loaded = True
            return True
        except Exception as exc:
            self.loaded = False
            messagebox.showerror("No se pudo abrir el MP3", str(exc))
            return False

    def play(self):
        if not self.loaded and not self.load_current():
            return

        try:
            self._pygame.mixer.music.play()
            self.paused = False
            self.pause_btn.configure(text="⏸ Pausar")
            self.status.set(f"Reproduciendo: {self.track_name.get()}")
        except Exception as exc:
            messagebox.showerror("Error de reproducción", str(exc))

    def pause_resume(self):
        if not self.ensure_audio():
            return
        if not self.loaded:
            self.play()
            return

        try:
            if self.paused:
                self._pygame.mixer.music.unpause()
                self.paused = False
                self.pause_btn.configure(text="⏸ Pausar")
                self.status.set(f"Reproduciendo: {self.track_name.get()}")
            else:
                self._pygame.mixer.music.pause()
                self.paused = True
                self.pause_btn.configure(text="▶ Continuar")
                self.status.set("Reproducción en pausa.")
        except Exception as exc:
            messagebox.showerror("Error", str(exc))

    def stop(self):
        if self.audio_ok:
            try:
                self._pygame.mixer.music.stop()
            except Exception:
                pass
        self.paused = False
        self.pause_btn.configure(text="⏸ Pausar")
        if self.file_path.get():
            self.status.set("Reproducción detenida.")

    def change_volume(self, _value=None):
        value = int(float(self.volume.get()))
        self.volume_label.configure(text=f"{value}%")
        if self.audio_ok:
            try:
                self._pygame.mixer.music.set_volume(value / 100)
            except Exception:
                pass

    def on_close(self):
        self.stop()
        if self.audio_ok:
            try:
                self._pygame.mixer.music.unload()
            except Exception:
                pass


App = Mp3PlayerTool\n\n\ndef main():
    root = tk.Tk()
    root.title(TOOL_NAME)
    root.geometry("820x430")
    root.minsize(680, 360)

    tool = App(root)
    tool.pack(fill="both", expand=True, padx=16, pady=16)

    def close_window():
        tool.on_close()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close_window)
    root.mainloop()


if __name__ == "__main__":
    main()