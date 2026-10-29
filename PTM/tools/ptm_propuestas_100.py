# ARGUMENTOS: propuestas ideas tools ptm catalogo checklist seleccion cache csv exportar planificar nuevas herramientas
import csv
import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

TOOL_NAME = "PTM - 100 Propuestas de Tools"
TOOL_DESCRIPTION = "Catalogo interactivo de 100 ideas para nuevas tools PTM con seleccion persistente y exportacion CSV."
TOOL_VERSION = "1.0.0"
APP_NAME = TOOL_NAME
CACHE_DIR = Path.home() / ".ptm"
CACHE_FILE = CACHE_DIR / "propuestas_tools_cache.json"

PROPOSALS = [
    (1, "ARCHMOBA Code", "Editor ligero de texto y codigo con pestanas, numeros de linea, buscar/reemplazar y ejecutar .py."),
    (2, "Administrador de procesos", "Ver procesos, PID, CPU, RAM, ruta y finalizar procesos desde PTM."),
    (3, "Monitor del sistema", "Panel de CPU, RAM, discos, temperatura, uptime y procesos principales."),
    (4, "PTM Tool Builder", "Crear tools compatibles con PTM desde una interfaz sin editar guide.csv manualmente."),
    (5, "Administrador ZIP", "Abrir, explorar, crear, extraer y modificar archivos ZIP."),
    (6, "API Tester", "Cliente HTTP tipo mini Postman con GET, POST, PUT, DELETE, headers, JSON y multipart."),
    (7, "SQLite Manager", "Abrir bases SQLite, explorar tablas, ejecutar SQL y exportar resultados."),
    (8, "Buscador dentro de archivos", "Buscar texto dentro de PY, TXT, CSV, JSON, HTML, LOG y otros formatos."),
    (9, "Inspector de archivos", "Mostrar tamano, MIME, fechas, permisos, hashes y extension real."),
    (10, "Gestor Git", "Clonar, pull, commit, push, branches e historial Git desde una interfaz simple."),
    (11, "System Report", "Generar diagnostico del sistema, Python, dependencias y componentes usados por PTM."),
    (12, "Monitor de red", "Interfaces, IP, gateway, DNS, trafico, ping y conexiones activas."),
    (13, "Gestor de servicios", "Listar, iniciar, detener y reiniciar servicios de Windows o systemd."),
    (14, "Administrador de inicio", "Gestionar aplicaciones que arrancan automaticamente con el sistema."),
    (15, "Downloader", "Descargas por URL con progreso, pausa, reanudacion y verificacion de hash."),
    (16, "Capturador de pantalla", "Capturar pantalla completa, ventana o region y guardar en PNG/JPG."),
    (17, "Grabador de pantalla", "Grabar escritorio o region a video con FPS configurable."),
    (18, "Conversor de imagenes", "Convertir PNG, JPG, WEBP, BMP e ICO de forma individual o por lotes."),
    (19, "Compresor de imagenes", "Reducir peso y resolucion de imagenes manteniendo calidad configurable."),
    (20, "Editor EXIF", "Ver, editar y limpiar metadatos EXIF de imagenes."),
    (21, "Editor ID3", "Editar metadatos de MP3, portada, artista, album y genero."),
    (22, "Generador QR", "Crear QR para texto, URL, Wi-Fi, contactos y otros datos."),
    (23, "Lector QR", "Leer codigos QR desde imagen o camara si esta disponible."),
    (24, "Generador de contrasenas", "Crear contrasenas seguras con reglas configurables."),
    (25, "Gestor de portapapeles", "Historial de textos copiados con favoritos y busqueda."),
    (26, "Notas rapidas", "Notas locales con etiquetas, fijado y busqueda."),
    (27, "Gestor de tareas", "Tareas con estado, prioridad, fecha y filtros."),
    (28, "Temporizadores", "Varios temporizadores y cronometros dentro de PTM."),
    (29, "Calendario local", "Calendario sencillo con eventos almacenados localmente."),
    (30, "Calculadora cientifica", "Calculadora avanzada con historial y conversiones basicas."),
    (31, "Conversor de unidades", "Longitud, masa, temperatura, almacenamiento y otras unidades."),
    (32, "Conversor de monedas manual", "Conversion de monedas con tasas ingresadas por el usuario y cache local."),
    (33, "Visor JSON", "Arbol expandible, validacion, edicion y formato de JSON."),
    (34, "Visor XML", "Arbol XML con busqueda, validacion y formato."),
    (35, "Visor YAML", "Abrir, validar, editar y convertir YAML a JSON."),
    (36, "Comparador de archivos", "Diff visual para texto, codigo, JSON y CSV."),
    (37, "Comparador de carpetas", "Detectar archivos faltantes, modificados y duplicados entre dos carpetas."),
    (38, "Detector de duplicados", "Buscar archivos duplicados por hash, nombre o tamano."),
    (39, "Limpiador de duplicados", "Revisar y eliminar duplicados con confirmacion segura."),
    (40, "Organizador por tipo", "Clasificar archivos automaticamente por extension o categoria."),
    (41, "Renombrador masivo", "Renombrar lotes usando patrones, prefijos, sufijos y numeracion."),
    (42, "Sincronizador de carpetas", "Sincronizar contenido entre dos carpetas localmente."),
    (43, "Backup local", "Crear copias de seguridad de carpetas con historial y restauracion."),
    (44, "Restaurador de backup", "Explorar respaldos creados y restaurar archivos seleccionados."),
    (45, "Visor HEX", "Abrir archivos binarios y navegar por contenido hexadecimal."),
    (46, "Editor HEX", "Modificar bytes de archivos con respaldo automatico."),
    (47, "Inspector PE", "Mostrar informacion basica de ejecutables PE de Windows."),
    (48, "Inspector ELF", "Mostrar cabeceras e informacion de binarios ELF en Linux."),
    (49, "Inspector de librerias", "Listar DLL, SO o dependencias vinculadas a un ejecutable."),
    (50, "Hash Checker", "Calcular y comparar MD5, SHA1, SHA256 y SHA512."),
    (51, "Generador de checksum", "Crear archivos de checksum para carpetas o paquetes."),
    (52, "Verificador de checksum", "Verificar integridad de archivos con hashes previamente guardados."),
    (53, "Editor CSV", "Editar CSV con tabla, filtros, busqueda y exportacion."),
    (54, "Visor Excel", "Abrir XLSX con hojas y previsualizacion simple."),
    (55, "CSV a Excel", "Convertir CSV a XLSX con configuracion de delimitador."),
    (56, "Excel a CSV", "Exportar hojas XLSX a CSV individual o multiple."),
    (57, "CSV Cleaner", "Detectar filas vacias, duplicadas o columnas inconsistentes."),
    (58, "CSV Join", "Unir varios CSV compatibles en uno solo."),
    (59, "CSV Split", "Dividir un CSV por numero de filas o por columna."),
    (60, "JSON a CSV", "Convertir listas y objetos JSON tabulares a CSV."),
    (61, "CSV a JSON", "Convertir CSV a JSON con configuracion de tipos basica."),
    (62, "PDF Merger", "Unir varios PDF en uno solo."),
    (63, "PDF Splitter", "Separar paginas o rangos de un PDF."),
    (64, "PDF Images", "Extraer imagenes de archivos PDF."),
    (65, "Images to PDF", "Crear PDF a partir de imagenes ordenadas."),
    (66, "PDF Metadata", "Ver y editar metadatos basicos de PDF."),
    (67, "PDF Compressor", "Reducir peso de PDF cuando sea posible."),
    (68, "Text Extractor", "Extraer texto de varios formatos compatibles."),
    (69, "Log Viewer", "Abrir logs grandes con filtros, busqueda y seguimiento."),
    (70, "Tail Monitor", "Seguir en tiempo real cambios de archivos de log."),
    (71, "Regex Tester", "Probar expresiones regulares contra texto con coincidencias resaltadas."),
    (72, "Base64 Tool", "Codificar y decodificar texto o archivos en Base64."),
    (73, "URL Encoder", "Codificar y decodificar URL y parametros."),
    (74, "JWT Inspector", "Decodificar localmente cabecera y payload de JWT sin validar firmas."),
    (75, "UUID Generator", "Generar lotes de UUID y copiarlos rapidamente."),
    (76, "Timestamp Converter", "Convertir Unix timestamp a fecha y viceversa."),
    (77, "Cron Helper", "Construir y explicar expresiones cron."),
    (78, "Port Scanner Local", "Comprobar puertos en hosts autorizados o localhost para diagnostico."),
    (79, "Ping Monitor", "Monitorear latencia y perdida de paquetes a uno o varios destinos."),
    (80, "DNS Lookup", "Consultar registros A, AAAA, MX, TXT y NS."),
    (81, "SSL Inspector", "Mostrar informacion de certificados SSL de un host."),
    (82, "HTTP Headers Viewer", "Consultar y mostrar cabeceras HTTP de una URL."),
    (83, "Web Screenshot", "Capturar una pagina web a imagen usando un motor disponible localmente."),
    (84, "HTML Preview", "Editar HTML y previsualizarlo localmente."),
    (85, "Markdown Viewer", "Editar y previsualizar archivos Markdown."),
    (86, "Markdown to HTML", "Convertir Markdown a HTML localmente."),
    (87, "Color Picker", "Selector de color con HEX, RGB, HSL y copia rapida."),
    (88, "Icon Generator", "Generar ICO y tamanos comunes desde una imagen."),
    (89, "Sprite Sheet Builder", "Unir imagenes en una hoja de sprites."),
    (90, "Image Cropper", "Recortar imagenes de forma visual con relacion configurable."),
    (91, "Audio Converter", "Convertir audio entre formatos cuando FFmpeg este disponible."),
    (92, "Audio Cutter", "Recortar fragmentos de audio con inicio y fin."),
    (93, "Video Converter", "Convertir video con perfiles basicos usando FFmpeg."),
    (94, "Video Cutter", "Recortar video sin interfaz compleja."),
    (95, "Thumbnail Generator", "Generar miniaturas de videos o imagenes por lotes."),
    (96, "Launcher Creator", "Crear accesos directos o lanzadores para tools y scripts."),
    (97, "Environment Viewer", "Ver variables de entorno, PATH y rutas de Python."),
    (98, "Dependency Manager", "Detectar imports, paquetes faltantes, instalados y versiones."),
    (99, "Python Environment Builder", "Crear entornos virtuales y preparar requirements.txt."),
    (100, "PTM Diagnostics", "Comprobar integridad de guide.csv, archivos tools, dependencias y configuracion PTM."),
]


class ProposalTool(tk.Frame):
    def __init__(self, parent, app=None):
        super().__init__(parent)
        self.app = app

        self.vars = {}
        self.rows = []
        self.search_var = tk.StringVar()
        self.count_var = tk.StringVar()

        self.cache = self.load_cache()
        self.build_ui()
        self.populate()
        self.search_var.trace_add("write", lambda *_: self.apply_filter())
        self.update_count()

    def load_cache(self):
        try:
            if CACHE_FILE.exists():
                data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {}

    def save_cache(self):
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            data = {str(pid): bool(var.get()) for pid, var in self.vars.items()}
            CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("Error", f"No se pudo guardar el cache:\n{exc}")

    def on_check(self):
        self.save_cache()
        self.update_count()

    def build_ui(self):
        top = tk.Frame(self)
        top.pack(fill="x", padx=12, pady=(12, 8))

        tk.Label(top, text=APP_NAME, font=("Segoe UI", 16, "bold")).pack(side="left")
        tk.Label(top, textvariable=self.count_var, font=("Segoe UI", 10, "bold")).pack(side="right")

        search_bar = tk.Frame(self)
        search_bar.pack(fill="x", padx=12, pady=(0, 8))
        tk.Label(search_bar, text="Buscar:").pack(side="left")
        tk.Entry(search_bar, textvariable=self.search_var).pack(side="left", fill="x", expand=True, padx=(8, 8))
        tk.Button(search_bar, text="Limpiar", command=lambda: self.search_var.set("")).pack(side="left")

        body = tk.Frame(self)
        body.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        self.canvas = tk.Canvas(body, highlightthickness=0)
        scroll = tk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)

        scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = tk.Frame(self.canvas)
        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window_id, width=e.width))
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        bottom = tk.Frame(self)
        bottom.pack(fill="x", padx=12, pady=(0, 12))

        tk.Button(bottom, text="Marcar visibles", command=self.check_visible).pack(side="left")
        tk.Button(bottom, text="Desmarcar visibles", command=self.uncheck_visible).pack(side="left", padx=(6, 0))
        tk.Button(bottom, text="Exportar seleccionados a CSV", command=self.export_csv).pack(side="right")

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def populate(self):
        for pid, title, desc in PROPOSALS:
            var = tk.BooleanVar(value=bool(self.cache.get(str(pid), False)))
            self.vars[pid] = var

            row = tk.Frame(self.inner, bd=1, relief="solid", padx=8, pady=6)
            row.pack(fill="x", pady=2)

            cb = tk.Checkbutton(
                row,
                variable=var,
                command=self.on_check,
                anchor="n",
            )
            cb.pack(side="left", anchor="n")

            text_frame = tk.Frame(row)
            text_frame.pack(side="left", fill="x", expand=True)

            tk.Label(
                text_frame,
                text=f"{pid:03d}. {title}",
                font=("Segoe UI", 10, "bold"),
                anchor="w",
            ).pack(fill="x")

            tk.Label(
                text_frame,
                text=desc,
                anchor="w",
                justify="left",
                wraplength=820,
            ).pack(fill="x", pady=(2, 0))

            self.rows.append((pid, title, desc, row))

    def apply_filter(self):
        term = self.search_var.get().strip().lower()
        for pid, title, desc, row in self.rows:
            haystack = f"{pid} {title} {desc}".lower()
            if not term or term in haystack:
                row.pack(fill="x", pady=2)
            else:
                row.pack_forget()

    def visible_ids(self):
        term = self.search_var.get().strip().lower()
        ids = []
        for pid, title, desc, _ in self.rows:
            haystack = f"{pid} {title} {desc}".lower()
            if not term or term in haystack:
                ids.append(pid)
        return ids

    def check_visible(self):
        for pid in self.visible_ids():
            self.vars[pid].set(True)
        self.save_cache()
        self.update_count()

    def uncheck_visible(self):
        for pid in self.visible_ids():
            self.vars[pid].set(False)
        self.save_cache()
        self.update_count()

    def selected(self):
        selected_ids = {pid for pid, var in self.vars.items() if var.get()}
        return [(pid, title, desc) for pid, title, desc in PROPOSALS if pid in selected_ids]

    def update_count(self):
        count = len(self.selected())
        self.count_var.set(f"Seleccionadas: {count} / {len(PROPOSALS)}")

    def export_csv(self):
        rows = self.selected()
        if not rows:
            messagebox.showinfo("Sin seleccion", "No hay propuestas seleccionadas.")
            return

        path = filedialog.asksaveasfilename(
            title="Guardar CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Todos", "*.*")],
            initialfile="ptm_tools_seleccionadas.csv",
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow(["id", "titulo", "descripcion"])
                writer.writerows(rows)
            messagebox.showinfo("CSV generado", f"Se exportaron {len(rows)} propuestas:\n{path}")
        except Exception as exc:
            messagebox.showerror("Error", f"No se pudo crear el CSV:\n{exc}")


App = ProposalTool


def main():
    root = tk.Tk()
    root.title(TOOL_NAME)
    root.geometry("980x680")
    root.minsize(760, 520)
    tool = App(root)
    tool.pack(fill="both", expand=True)
    root.mainloop()


if __name__ == "__main__":
    main()
