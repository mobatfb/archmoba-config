# ARGUMENTOS: buscar texto contenido archivos carpetas codigo palabra frase lineas subcarpetas utf8 utf16 busqueda global
"""Search file contents recursively, with a cancellable integrated PTM UI."""
import codecs
import fnmatch
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

TOOL_NAME = "Buscador de texto en archivos"
TOOL_VERSION = "1.0.0"
TOOL_DESCRIPTION = "Busca palabras o frases dentro de archivos y muestra su ruta, línea y contenido."


def detectar_codificacion(sample):
    for bom, encoding in ((codecs.BOM_UTF32_LE, "utf-32"), (codecs.BOM_UTF32_BE, "utf-32"),
                          (codecs.BOM_UTF16_LE, "utf-16"), (codecs.BOM_UTF16_BE, "utf-16")):
        if sample.startswith(bom):
            return encoding
    if b"\0" in sample:
        return None
    if sample and sum(byte < 32 and byte not in (9, 10, 12, 13) for byte in sample) / len(sample) > 0.03:
        return None
    try:
        codecs.getincrementaldecoder("utf-8-sig")().decode(sample, final=False)
        return "utf-8-sig"
    except UnicodeDecodeError:
        return "cp1252"


def buscar_texto(root, text, cancel=None, case_sensitive=False, patterns="*", max_results=5000):
    """Yield match/progress/done events. Searches literal text, one result per line."""
    root = Path(root).expanduser().resolve()
    if not root.is_dir() or not text:
        raise ValueError("Selecciona una carpeta existente y escribe el texto que buscas.")
    cancel = cancel or threading.Event()
    patterns = [part.strip().lower() for part in re.split(r"[;,]", patterns) if part.strip()] or ["*"]
    needle = text if case_sensitive else text.casefold()
    stats = {"files": 0, "matches": 0, "binary": 0, "errors": 0, "reason": "complete"}

    def walk_error(_error):
        stats["errors"] += 1

    for folder, directories, names in os.walk(root, followlinks=False, onerror=walk_error):
        directories[:] = [name for name in directories if name not in (".git", "__pycache__")
                          and not (Path(folder) / name).is_symlink()]
        for name in names:
            if cancel.is_set():
                stats["reason"] = "cancelled"
                yield "done", stats.copy()
                return
            if not any(fnmatch.fnmatchcase(name.lower(), pattern) for pattern in patterns):
                continue
            path = Path(folder) / name
            try:
                if path.is_symlink():
                    continue
                stats["files"] += 1
                with path.open("rb") as file:
                    encoding = detectar_codificacion(file.read(8192))
                if encoding is None:
                    stats["binary"] += 1
                    continue
                with path.open("r", encoding=encoding, errors="replace") as file:
                    for number, line in enumerate(file, 1):
                        if cancel.is_set():
                            break
                        candidate = line if case_sensitive else line.casefold()
                        index = candidate.find(needle)
                        if index < 0:
                            continue
                        stats["matches"] += 1
                        start = max(0, index - 100)
                        snippet = line[start:start + 600].rstrip("\r\n")
                        if start:
                            snippet = "…" + snippet
                        yield "match", (str(path), number, snippet)
                        if stats["matches"] >= max_results:
                            stats["reason"] = "limit"
                            yield "done", stats.copy()
                            return
            except (OSError, UnicodeError):
                stats["errors"] += 1
            if stats["files"] % 100 == 0:
                yield "progress", stats.copy()
    if cancel.is_set():
        stats["reason"] = "cancelled"
    yield "done", stats.copy()


class TextSearchTool(ttk.Frame):
    def __init__(self, parent, app=None):
        super().__init__(parent)
        self.app = app
        default = os.environ.get("AMDEV_LOCAL_ROOT", str(Path(__file__).resolve().parents[2]))
        self.folder = tk.StringVar(value=default)
        self.query = tk.StringVar()
        self.patterns = tk.StringVar(value="*")
        self.case_sensitive = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Busca texto literal en archivos de texto y código. Se omiten binarios, .git y enlaces.")
        self.cancel = threading.Event()
        self.closed = threading.Event()
        self.events = queue.Queue(maxsize=256)
        self.searching = False
        self.results = []
        self._poll_id = None
        self._build_ui()
        self.bind("<Destroy>", self._destroyed, add="+")
        self._poll_id = self.after(70, self._poll)

    def _build_ui(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(4, weight=1)
        ttk.Label(self, text=f"{TOOL_NAME} · v{TOOL_VERSION}", font=("Segoe UI", 15, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        ttk.Label(self, text="Carpeta:").grid(row=1, column=0, sticky="w")
        ttk.Entry(self, textvariable=self.folder).grid(row=1, column=1, sticky="ew", padx=8)
        ttk.Button(self, text="Examinar…", command=self._choose_folder).grid(row=1, column=2)
        ttk.Label(self, text="Texto a buscar:").grid(row=2, column=0, sticky="w", pady=10)
        entry = ttk.Entry(self, textvariable=self.query)
        entry.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(8, 0))
        entry.bind("<Return>", lambda _event: self.search())
        options = ttk.Frame(self)
        options.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        ttk.Label(options, text="Archivos:").pack(side="left")
        ttk.Entry(options, textvariable=self.patterns, width=20).pack(side="left", padx=6)
        ttk.Label(options, text="* o *.py;*.json").pack(side="left")
        ttk.Checkbutton(options, text="Distinguir mayúsculas", variable=self.case_sensitive).pack(side="left", padx=12)
        self.search_button = ttk.Button(options, text="Buscar", command=self.search)
        self.search_button.pack(side="right")
        self.stop_button = ttk.Button(options, text="Detener", command=self.stop, state="disabled")
        self.stop_button.pack(side="right", padx=6)
        table = ttk.Frame(self)
        table.grid(row=4, column=0, columnspan=3, sticky="nsew")
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=("path", "line", "text"), show="headings")
        for key, label, width in (("path", "Archivo", 380), ("line", "Línea", 65), ("text", "Texto encontrado", 600)):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, stretch=key != "line")
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        horizontal = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.tree.bind("<Double-1>", self.open_file)
        ttk.Label(self, textvariable=self.status, wraplength=1000).grid(row=5, column=0, columnspan=3, sticky="w", pady=10)
        buttons = ttk.Frame(self)
        buttons.grid(row=6, column=0, columnspan=3, sticky="w")
        ttk.Button(buttons, text="Abrir archivo", command=self.open_file).pack(side="left")
        ttk.Button(buttons, text="Abrir carpeta", command=lambda: self.open_file(folder=True)).pack(side="left", padx=6)
        ttk.Label(buttons, text="Máximo 5.000 líneas por búsqueda. PDF, imágenes y documentos comprimidos no se extraen.").pack(side="left", padx=8)

    def _choose_folder(self):
        path = filedialog.askdirectory(parent=self, initialdir=self.folder.get())
        if path:
            self.folder.set(path)

    def search(self):
        if self.searching:
            return
        root = Path(self.folder.get()).expanduser()
        text = self.query.get()
        if not root.is_dir() or not text:
            messagebox.showerror(TOOL_NAME, "Selecciona una carpeta existente y escribe el texto a buscar.", parent=self)
            return
        self.tree.delete(*self.tree.get_children())
        self.results.clear()
        self.cancel.clear()
        self.searching = True
        self.search_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status.set("Buscando en todas las subcarpetas…")
        options = (root, text, self.cancel, self.case_sensitive.get(), self.patterns.get())
        threading.Thread(target=self._worker, args=(options,), daemon=True).start()

    def _send(self, event):
        while not self.closed.is_set():
            try:
                self.events.put(event, timeout=0.1)
                return True
            except queue.Full:
                if self.cancel.is_set() and event[0] != "done":
                    return True
        return False

    def _worker(self, options):
        try:
            for event in buscar_texto(*options):
                if not self._send(event):
                    return
        except Exception as error:
            self._send(("error", str(error)))

    def _poll(self):
        if self.closed.is_set():
            return
        for _ in range(200):
            try:
                kind, data = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "match":
                index = len(self.results)
                self.results.append(data)
                self.tree.insert("", "end", iid=str(index), values=data)
                self.status.set(f"Buscando… {len(self.results)} líneas encontradas.")
            elif kind in ("progress", "done"):
                labels = {"complete": "Finalizada", "cancelled": "Detenida", "limit": "Límite de 5.000 resultados alcanzado"}
                label = labels[data["reason"]] if kind == "done" else "Buscando"
                self.status.set(f"{label}: {data['files']} archivos revisados, {data['matches']} líneas coincidentes, "
                                f"{data['binary']} binarios omitidos, {data['errors']} errores de lectura.")
            else:
                self.status.set(f"Error: {data}")
            if kind in ("done", "error"):
                self.searching = False
                self.search_button.configure(state="normal")
                self.stop_button.configure(state="disabled")
        self._poll_id = self.after(70, self._poll)

    def stop(self):
        self.cancel.set()
        self.stop_button.configure(state="disabled")
        self.status.set("Deteniendo búsqueda…")

    def open_file(self, _event=None, folder=False):
        selection = self.tree.selection()
        if not selection:
            return
        path = Path(self.results[int(selection[0])][0])
        try:
            if os.name == "nt":
                if folder:
                    subprocess.Popen(["explorer", "/select,", str(path)])
                else:
                    os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(path)] if folder else ["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path.parent if folder else path)])
        except OSError as error:
            messagebox.showerror(TOOL_NAME, str(error), parent=self)

    def _destroyed(self, event):
        if event.widget is self:
            self.on_close()

    def on_close(self):
        self.closed.set()
        self.cancel.set()
        if self._poll_id is not None:
            try:
                self.after_cancel(self._poll_id)
            except tk.TclError:
                pass
            self._poll_id = None


App = TextSearchTool


def main():
    root = tk.Tk()
    root.title(TOOL_NAME)
    root.geometry("1180x700")
    tool = App(root)
    tool.pack(fill="both", expand=True, padx=14, pady=14)
    root.protocol("WM_DELETE_WINDOW", lambda: (tool.on_close(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
