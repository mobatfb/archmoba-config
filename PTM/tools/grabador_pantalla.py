# ARGUMENTOS: grabar pantalla video mp4 seleccionar marco region ventana monitor fps grabador
"""Grabador de pantalla con seleccion rectangular para PTM."""
import os
import queue
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

TOOL_NAME = "Grabador de Pantalla"
TOOL_DESCRIPTION = "Graba una region seleccionada de la pantalla y exporta video MP4."
TOOL_VERSION = "1.0.0"


class ScreenRecorder(tk.Frame):
    def __init__(self, parent, app=None):
        super().__init__(parent, bg="#101827")
        self.host_app = app
        self.region = None
        self.worker = None
        self.stop_event = threading.Event()
        self.messages = queue.Queue()
        self.fps = tk.IntVar(value=20)
        self.path = tk.StringVar(value=str(Path.home() / "Videos" / "ARCHMOBA"))
        self.status = tk.StringVar(value="Selecciona un marco para comenzar.")
        self.recording = False
        self._closed = False
        self._make_ui()
        self.after(150, self._poll)

    def _make_ui(self):
        tk.Label(self, text="GRABADOR DE PANTALLA", bg="#101827", fg="#eff6ff",
                 font=("Segoe UI", 17, "bold")).pack(anchor="w", padx=20, pady=(20, 7))
        tk.Label(self, text="Selecciona un marco en pantalla y guardalo como MP4.",
                 bg="#101827", fg="#a9b8d0").pack(anchor="w", padx=20)
        panel = tk.Frame(self, bg="#17243a", padx=16, pady=16)
        panel.pack(fill="x", padx=20, pady=20)
        tk.Label(panel, text="Area de captura", bg="#17243a", fg="white").grid(row=0, column=0, sticky="w")
        self.region_label = tk.Label(panel, text="Sin seleccionar", bg="#17243a", fg="#81d4ff")
        self.region_label.grid(row=0, column=1, sticky="w", padx=15)
        self.pick_button = ttk.Button(panel, text="Seleccionar marco", command=self.select_region)
        self.pick_button.grid(row=0, column=2, sticky="e", padx=10)
        tk.Label(panel, text="FPS", bg="#17243a", fg="white").grid(row=1, column=0, sticky="w", pady=15)
        ttk.Combobox(panel, textvariable=self.fps, values=(10, 15, 20, 24, 30),
                     width=8, state="readonly").grid(row=1, column=1, sticky="w", padx=15)
        tk.Label(panel, text="Guardar en", bg="#17243a", fg="white").grid(row=2, column=0, sticky="w")
        ttk.Entry(panel, textvariable=self.path, width=45).grid(row=2, column=1, sticky="ew", padx=15)
        ttk.Button(panel, text="Carpeta...", command=self.choose_folder).grid(row=2, column=2)
        panel.columnconfigure(1, weight=1)
        buttons = tk.Frame(self, bg="#101827")
        buttons.pack(fill="x", padx=20)
        self.start_button = ttk.Button(buttons, text="Iniciar grabacion", command=self.start)
        self.start_button.pack(side="left", padx=(0, 10))
        self.stop_button = ttk.Button(buttons, text="Detener y guardar", command=self.stop, state="disabled")
        self.stop_button.pack(side="left")
        tk.Label(self, textvariable=self.status, bg="#101827", fg="#81d4ff",
                 justify="left", wraplength=650).pack(anchor="w", padx=20, pady=20)
        tk.Label(self, text="La captura no incluye audio. Esc cancela la seleccion del marco.",
                 bg="#101827", fg="#94a3b8").pack(anchor="w", padx=20)

    def choose_folder(self):
        folder = filedialog.askdirectory(initialdir=self.path.get() if Path(self.path.get()).is_dir() else str(Path.home()))
        if folder:
            self.path.set(folder)

    def select_region(self):
        if self.recording:
            return
        try:
            import mss
            with mss.mss() as sct:
                desktop = sct.monitors[0]
                left, top = desktop["left"], desktop["top"]
                width, height = desktop["width"], desktop["height"]
        except Exception as exc:
            messagebox.showerror("Captura", "Instala mss: python -m pip install mss\n\n" + str(exc))
            return
        overlay = tk.Toplevel(self)
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.configure(bg="#1e293b")
        overlay.geometry(f"{width}x{height}{left:+d}{top:+d}")
        try:
            overlay.attributes("-alpha", 0.36)
        except tk.TclError:
            pass
        canvas = tk.Canvas(overlay, bg="#19253b", highlightthickness=0, cursor="crosshair")
        canvas.pack(fill="both", expand=True)
        canvas.create_text(width // 2, 40, text="ARRASTRA PARA SELECCIONAR EL MARCO - ESC PARA CANCELAR",
                           fill="white", font=("Segoe UI", 15, "bold"))
        state = {"start": None, "rect": None}

        def down(event):
            state["start"] = (event.x, event.y)
            if state["rect"]:
                canvas.delete(state["rect"])
            state["rect"] = canvas.create_rectangle(event.x, event.y, event.x, event.y,
                                                    outline="#00e5ff", width=3, fill="")

        def drag(event):
            if state["start"] and state["rect"]:
                canvas.coords(state["rect"], *state["start"], event.x, event.y)

        def up(event):
            if not state["start"]:
                return
            sx, sy = state["start"]
            x, y = min(sx, event.x), min(sy, event.y)
            w, h = abs(event.x - sx), abs(event.y - sy)
            overlay.destroy()
            if w < 32 or h < 32:
                self.status.set("Marco demasiado pequeno. Selecciona al menos 32 x 32.")
                return
            self.region = {"left": left + x, "top": top + y, "width": w, "height": h}
            self.region_label.configure(text=f"{w} x {h}  ({left+x}, {top+y})")
            self.status.set("Marco listo para grabar.")
        canvas.bind("<ButtonPress-1>", down)
        canvas.bind("<B1-Motion>", drag)
        canvas.bind("<ButtonRelease-1>", up)
        overlay.bind("<Escape>", lambda _: overlay.destroy())
        overlay.focus_force()
        overlay.grab_set()

    def start(self):
        if self.recording:
            return
        if not self.region:
            messagebox.showwarning("Grabacion", "Selecciona primero el marco.")
            return
        try:
            import cv2
            import numpy
            import mss
        except ImportError as exc:
            messagebox.showerror("Dependencias", "Instala: python -m pip install mss opencv-python numpy\n\n" + str(exc))
            return
        try:
            folder = Path(self.path.get()).expanduser()
            folder.mkdir(parents=True, exist_ok=True)
            output = folder / ("ARCHMOBA_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".mp4")
        except OSError as exc:
            messagebox.showerror("Carpeta", str(exc))
            return
        self.stop_event.clear()
        self.recording = True
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.pick_button.configure(state="disabled")
        self.status.set("Grabando... pulsa Detener y guardar.")
        self.worker = threading.Thread(target=self._record, args=(dict(self.region), int(self.fps.get()), output), daemon=True)
        self.worker.start()

    def _record(self, region, fps, output):
        writer = None
        frames = 0
        try:
            import cv2
            import numpy as np
            import mss
            # El codificador MP4 necesita dimensiones pares.
            w = region["width"] - region["width"] % 2
            h = region["height"] - region["height"] % 2
            if w < 2 or h < 2:
                raise RuntimeError("Region invalida")
            writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
            if not writer.isOpened():
                raise RuntimeError("No se pudo abrir el codificador MP4")
            interval = 1.0 / fps
            deadline = time.perf_counter()
            with mss.mss() as sct:
                while not self.stop_event.is_set():
                    image = np.asarray(sct.grab(region))
                    frame = cv2.cvtColor(image[:h, :w], cv2.COLOR_BGRA2BGR)
                    writer.write(frame)
                    frames += 1
                    deadline += interval
                    wait = deadline - time.perf_counter()
                    if wait > 0:
                        self.stop_event.wait(wait)
                    elif wait < -interval:
                        deadline = time.perf_counter()
            self.messages.put(("done", str(output), frames))
        except Exception as exc:
            self.messages.put(("error", str(exc), frames))
        finally:
            if writer is not None:
                writer.release()

    def stop(self):
        if self.recording:
            self.status.set("Finalizando video MP4...")
            self.stop_button.configure(state="disabled")
            self.stop_event.set()

    def _poll(self):
        if self._closed:
            return
        try:
            while True:
                kind, info, frames = self.messages.get_nowait()
                self.recording = False
                self.start_button.configure(state="normal")
                self.stop_button.configure(state="disabled")
                self.pick_button.configure(state="normal")
                if kind == "done":
                    self.status.set(f"Guardado: {info} ({frames} fotogramas)")
                else:
                    self.status.set(f"Error: {info}")
                    messagebox.showerror("Grabador", info)
        except queue.Empty:
            pass
        self.after(150, self._poll)

    def on_close(self):
        self._closed = True
        self.stop_event.set()


App = ScreenRecorder


def create_tool(parent, app=None):
    return ScreenRecorder(parent, app)


def main():
    root = tk.Tk()
    root.title(TOOL_NAME)
    root.geometry("800x440")
    widget = ScreenRecorder(root)
    widget.pack(fill="both", expand=True)
    root.protocol("WM_DELETE_WINDOW", lambda: (widget.on_close(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
