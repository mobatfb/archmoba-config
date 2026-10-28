# ARGUMENTOS: buscar archivos documentos tiempo real nombre patron comodin porcentaje maest xlsx xls csv pdf docx doc txt pptx extension carpeta unidad abrir ubicacion
import fnmatch
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

TOOL_NAME = "Buscador de archivos"
TOOL_DESCRIPTION = "Busca documentos en carpetas o unidades, agrega coincidencias en vivo y permite detener la búsqueda."


def coincide(nombre, patron):
    patron = patron.strip().lower()
    if not patron:
        return True
    patron = patron.replace("%", "*").replace("_", "?")
    if "*" in patron or "?" in patron:
        return fnmatch.fnmatch(nombre.lower(), patron)
    return patron in nombre.lower()


class FileSearchTool(ttk.Frame):
    def __init__(self, parent, app=None):
        super().__init__(parent)
        self.app = app
        self.ruta = tk.StringVar(value=str(Path.home()))
        self.patron = tk.StringVar(value="maest")
        self.extension = tk.StringVar(value="Todas")
        self.estado = tk.StringVar(value="Escribe un criterio y pulsa Buscar.")
        self.resultados = []
        self.cola = queue.Queue()
        self.detener = threading.Event()
        self.buscando = False
        self.carpetas_revisadas = 0
        self.archivos_revisados = 0
        self._build_ui()
        self.after(70, self.procesar_cola)

    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 10))
        if self.app is not None:
            ttk.Button(top, text="← Volver al buscador de herramientas", command=self.app.show_home).pack(side="left")
        ttk.Label(top, text=TOOL_NAME, font=("Segoe UI", 15, "bold")).pack(side="left", padx=12)

        marco = ttk.Frame(self, padding=4)
        marco.pack(fill="both", expand=True)

        ttk.Label(marco, text="Carpeta o unidad donde buscar:").grid(row=0, column=0, sticky="w")
        ttk.Entry(marco, textvariable=self.ruta).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(marco, text="Examinar...", command=self.elegir_carpeta).grid(row=0, column=2, columnspan=2, sticky="ew")

        ttk.Label(marco, text="Nombre o patrón:").grid(row=1, column=0, sticky="w", pady=12)
        entry_patron = ttk.Entry(marco, textvariable=self.patron)
        entry_patron.grid(row=1, column=1, sticky="ew", padx=8)
        entry_patron.bind("<Return>", lambda _e: self.buscar())

        ttk.Label(marco, text="Extensión:").grid(row=2, column=0, sticky="w")
        ttk.Combobox(
            marco,
            textvariable=self.extension,
            values=["Todas", ".xlsx", ".xls", ".xlsm", ".csv", ".pdf", ".docx", ".doc", ".txt", ".pptx", ".py"],
            state="normal",
        ).grid(row=2, column=1, sticky="ew", padx=8)

        self.boton_buscar = ttk.Button(marco, text="Buscar", command=self.buscar)
        self.boton_buscar.grid(row=2, column=2, sticky="ew", padx=(0, 5))
        self.boton_detener = ttk.Button(marco, text="Detener", command=self.parar, state="disabled")
        self.boton_detener.grid(row=2, column=3, sticky="ew")

        ttk.Label(
            marco,
            text=("Ejemplos: maest (contiene), maest%.xlsx (comienza por maest y termina en .xlsx), "
                  "%maest%.xlsx (contiene maest y termina en .xlsx). También admite * y ?."),
            wraplength=1030,
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(12, 8))

        tabla = ttk.Frame(marco)
        tabla.grid(row=4, column=0, columnspan=4, sticky="nsew")
        self.tree = ttk.Treeview(tabla, columns=("numero", "nombre", "carpeta"), show="headings")
        self.tree.heading("numero", text="#")
        self.tree.heading("nombre", text="Archivo")
        self.tree.heading("carpeta", text="Ubicación")
        self.tree.column("numero", width=55, stretch=False, anchor="center")
        self.tree.column("nombre", width=330)
        self.tree.column("carpeta", width=650)
        barra_y = ttk.Scrollbar(tabla, orient="vertical", command=self.tree.yview)
        barra_x = ttk.Scrollbar(tabla, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=barra_y.set, xscrollcommand=barra_x.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        barra_y.grid(row=0, column=1, sticky="ns")
        barra_x.grid(row=1, column=0, sticky="ew")
        tabla.columnconfigure(0, weight=1)
        tabla.rowconfigure(0, weight=1)
        self.tree.bind("<Double-1>", self.abrir_archivo)

        ttk.Label(marco, textvariable=self.estado).grid(row=5, column=0, columnspan=4, sticky="w", pady=(12, 0))
        buttons = ttk.Frame(marco)
        buttons.grid(row=6, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Button(buttons, text="Abrir archivo", command=self.abrir_archivo).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Abrir carpeta del archivo", command=self.abrir_ubicacion).pack(side="left")

        marco.columnconfigure(1, weight=1)
        marco.rowconfigure(4, weight=1)

    def elegir_carpeta(self):
        carpeta = filedialog.askdirectory(initialdir=self.ruta.get())
        if carpeta:
            self.ruta.set(carpeta)

    def buscar(self):
        if self.buscando:
            return
        base = Path(self.ruta.get())
        if not base.is_dir():
            messagebox.showerror("Carpeta inválida", "Selecciona una carpeta o unidad existente.")
            return

        self.tree.delete(*self.tree.get_children())
        self.resultados.clear()
        self.carpetas_revisadas = 0
        self.archivos_revisados = 0
        self.cola = queue.Queue()
        self.detener = threading.Event()
        patron = self.patron.get()
        ext = self.extension.get().strip().lower()
        if ext and ext != "todas" and not ext.startswith("."):
            ext = "." + ext

        self.buscando = True
        self.boton_buscar.configure(state="disabled")
        self.boton_detener.configure(state="normal")
        self.estado.set("Buscando... las coincidencias se agregan en tiempo real.")
        threading.Thread(
            target=self.recorrer,
            args=(base, patron, ext, self.cola, self.detener),
            daemon=True,
        ).start()

    @staticmethod
    def recorrer(base, patron, ext, cola, detener):
        carpetas = archivos = 0
        try:
            for carpeta, _subcarpetas, nombres in os.walk(base, onerror=lambda _error: None):
                if detener.is_set():
                    break
                carpetas += 1
                for nombre in nombres:
                    if detener.is_set():
                        break
                    archivos += 1
                    if coincide(nombre, patron) and (ext in ("", "todas") or nombre.lower().endswith(ext)):
                        cola.put(("archivo", str(Path(carpeta) / nombre), carpeta, nombre))
                if carpetas % 20 == 0:
                    cola.put(("avance", carpetas, archivos))
            cola.put(("fin", carpetas, archivos, detener.is_set(), None))
        except Exception as error:
            cola.put(("fin", carpetas, archivos, detener.is_set(), str(error)))

    def procesar_cola(self):
        if not self.winfo_exists():
            return
        for _ in range(200):
            try:
                evento = self.cola.get_nowait()
            except queue.Empty:
                break

            if evento[0] == "archivo":
                _, ruta, carpeta, nombre = evento
                self.resultados.append(Path(ruta))
                numero = len(self.resultados)
                iid = str(numero - 1)
                self.tree.insert("", "end", iid=iid, values=(numero, nombre, carpeta))
                self.tree.see(iid)
            elif evento[0] == "avance":
                _, self.carpetas_revisadas, self.archivos_revisados = evento
            elif evento[0] == "fin":
                _, self.carpetas_revisadas, self.archivos_revisados, cancelado, error = evento
                self.buscando = False
                self.boton_buscar.configure(state="normal")
                self.boton_detener.configure(state="disabled")
                mensaje = "Búsqueda detenida" if cancelado else "Búsqueda finalizada"
                if error:
                    mensaje += ": " + error
                self.estado.set(
                    f"{mensaje}. {len(self.resultados)} coincidencias; "
                    f"{self.archivos_revisados} archivos examinados en {self.carpetas_revisadas} carpetas."
                )

        if self.buscando:
            self.estado.set(
                f"Buscando... {len(self.resultados)} coincidencias encontradas | "
                f"{self.archivos_revisados} archivos revisados | {self.carpetas_revisadas} carpetas revisadas."
            )
        self.after(70, self.procesar_cola)

    def parar(self):
        self.detener.set()
        self.boton_detener.configure(state="disabled")
        self.estado.set(f"Deteniendo búsqueda... {len(self.resultados)} coincidencias.")

    def _ruta_seleccionada(self):
        seleccion = self.tree.selection()
        if not seleccion:
            messagebox.showinfo("Selecciona un archivo", "Selecciona un resultado de la lista.")
            return None
        try:
            return self.resultados[int(seleccion[0])]
        except (IndexError, ValueError):
            return None

    def abrir_archivo(self, _evento=None):
        ruta = self._ruta_seleccionada()
        if ruta is None:
            return
        try:
            if os.name == "nt":
                os.startfile(str(ruta))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(ruta)])
            else:
                subprocess.Popen(["xdg-open", str(ruta)])
        except OSError as error:
            messagebox.showerror("Error al abrir archivo", str(error))

    def abrir_ubicacion(self):
        ruta = self._ruta_seleccionada()
        if ruta is None:
            return
        try:
            if os.name == "nt":
                subprocess.Popen(["explorer", "/select,", str(ruta)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(ruta)])
            else:
                subprocess.Popen(["xdg-open", str(ruta.parent)])
        except OSError as error:
            messagebox.showerror("Error al abrir carpeta", str(error))

    def on_close(self):
        self.detener.set()


App = FileSearchTool\n\n\ndef main():
    root = tk.Tk()
    root.title(TOOL_NAME)
    root.geometry("1080x690")
    tool = App(root)
    tool.pack(fill="both", expand=True, padx=12, pady=12)
    root.protocol("WM_DELETE_WINDOW", lambda: (tool.on_close(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()