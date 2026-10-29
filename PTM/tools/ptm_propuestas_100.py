# ARGUMENTOS: propuestas ideas tools ptm catalogo checklist seleccion cache csv exportar planificar nuevas herramientas
import csv
import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

TOOL_NAME = "PTM - 100 Propuestas de Tools"
TOOL_DESCRIPTION = "Revisor secuencial de 100 ideas para nuevas tools PTM con aceptar, rechazar, regreso, listas y progreso persistente."
TOOL_VERSION = "1.1.0"
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

        self.state = self.load_cache()
        self.decisions = self.state.get("decisions", {})
        self.index = int(self.state.get("index", 0))
        self.index = max(0, min(self.index, len(PROPOSALS)))

        self.accepted_count = tk.StringVar()
        self.rejected_count = tk.StringVar()
        self.progress_text = tk.StringVar()
        self.card_title = tk.StringVar()
        self.card_desc = tk.StringVar()

        self.build_ui()
        self.refresh_all()

    def load_cache(self):
        try:
            if CACHE_FILE.exists():
                data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    if "decisions" in data:
                        return data
                    # Migracion desde la primera version basada en checkbox.
                    decisions = {}
                    for key, value in data.items():
                        if str(key).isdigit() and value is True:
                            decisions[str(key)] = "accepted"
                    return {"index": 0, "decisions": decisions}
        except Exception:
            pass
        return {"index": 0, "decisions": {}}

    def save_cache(self):
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "index": self.index,
                "decisions": self.decisions,
            }
            CACHE_FILE.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            messagebox.showerror("Error", f"No se pudo guardar el cache:\n{exc}")

    def build_ui(self):
        top = tk.Frame(self)
        top.pack(fill="x", padx=14, pady=(12, 8))

        tk.Label(
            top,
            text=APP_NAME,
            font=("Segoe UI", 16, "bold"),
        ).pack(side="left")

        counters = tk.Frame(top)
        counters.pack(side="right")
        tk.Label(
            counters,
            textvariable=self.accepted_count,
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(0, 10))
        tk.Label(
            counters,
            textvariable=self.rejected_count,
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left")

        self.tabs = tk.Frame(self)
        self.tabs.pack(fill="x", padx=14, pady=(0, 8))

        self.tab_buttons = {}
        for name in ("Propuestas", "Aceptados", "Rechazados"):
            btn = tk.Button(
                self.tabs,
                text=name,
                command=lambda n=name: self.show_tab(n),
                padx=14,
                pady=5,
            )
            btn.pack(side="left", padx=(0, 4))
            self.tab_buttons[name] = btn

        self.content = tk.Frame(self)
        self.content.pack(fill="both", expand=True, padx=14, pady=(0, 12))

        self.proposals_view = tk.Frame(self.content)
        self.accepted_view = tk.Frame(self.content)
        self.rejected_view = tk.Frame(self.content)

        self.build_proposals_view()
        self.build_list_view(self.accepted_view, "Aceptados")
        self.build_list_view(self.rejected_view, "Rechazados")

        self.show_tab("Propuestas")

    def build_proposals_view(self):
        self.proposals_view.pack(fill="both", expand=True)

        tk.Label(
            self.proposals_view,
            textvariable=self.progress_text,
            font=("Segoe UI", 10, "bold"),
        ).pack(pady=(10, 12))

        card = tk.Frame(
            self.proposals_view,
            bd=1,
            relief="solid",
            padx=28,
            pady=28,
        )
        card.pack(fill="both", expand=True, padx=50, pady=(0, 18))

        tk.Label(
            card,
            textvariable=self.card_title,
            font=("Segoe UI", 20, "bold"),
            anchor="center",
            justify="center",
            wraplength=760,
        ).pack(fill="x", pady=(20, 18))

        tk.Label(
            card,
            textvariable=self.card_desc,
            font=("Segoe UI", 11),
            anchor="center",
            justify="center",
            wraplength=760,
        ).pack(fill="both", expand=True)

        actions = tk.Frame(self.proposals_view)
        actions.pack(pady=(0, 8))

        self.back_button = tk.Button(
            actions,
            text="Regresar",
            command=self.go_back,
            width=14,
            pady=8,
        )
        self.back_button.pack(side="left", padx=6)

        self.accept_button = tk.Button(
            actions,
            text="Aceptar",
            command=lambda: self.decide("accepted"),
            width=16,
            pady=8,
        )
        self.accept_button.pack(side="left", padx=6)

        self.reject_button = tk.Button(
            actions,
            text="Rechazar",
            command=lambda: self.decide("rejected"),
            width=16,
            pady=8,
        )
        self.reject_button.pack(side="left", padx=6)

    def build_list_view(self, parent, kind):
        title = tk.Label(parent, text=kind, font=("Segoe UI", 15, "bold"))
        title.pack(anchor="w", pady=(8, 8))

        body = tk.Frame(parent)
        body.pack(fill="both", expand=True)

        canvas = tk.Canvas(body, highlightthickness=0)
        scroll = tk.Scrollbar(body, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)

        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        inner.bind(
            "<Configure>",
            lambda _e, c=canvas: c.configure(scrollregion=c.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda e, c=canvas, w=window_id: c.itemconfigure(w, width=e.width),
        )

        if kind == "Aceptados":
            self.accepted_inner = inner
        else:
            self.rejected_inner = inner

    def show_tab(self, name):
        for view in (self.proposals_view, self.accepted_view, self.rejected_view):
            view.pack_forget()

        if name == "Propuestas":
            self.proposals_view.pack(fill="both", expand=True)
        elif name == "Aceptados":
            self.accepted_view.pack(fill="both", expand=True)
        else:
            self.rejected_view.pack(fill="both", expand=True)

        for tab_name, button in self.tab_buttons.items():
            button.configure(relief="sunken" if tab_name == name else "raised")

        self.refresh_lists()

    def decide(self, decision):
        if self.index >= len(PROPOSALS):
            return

        pid = PROPOSALS[self.index][0]
        self.decisions[str(pid)] = decision
        self.index += 1
        self.save_cache()
        self.refresh_all()

    def go_back(self):
        if self.index <= 0:
            return
        self.index -= 1
        pid = PROPOSALS[self.index][0]
        self.decisions.pop(str(pid), None)
        self.save_cache()
        self.refresh_all()

    def refresh_all(self):
        accepted = sum(1 for v in self.decisions.values() if v == "accepted")
        rejected = sum(1 for v in self.decisions.values() if v == "rejected")
        self.accepted_count.set(f"Aceptados: {accepted}")
        self.rejected_count.set(f"Rechazados: {rejected}")

        total = len(PROPOSALS)
        if self.index < total:
            pid, title, desc = PROPOSALS[self.index]
            self.progress_text.set(f"Propuesta {self.index + 1} de {total}")
            self.card_title.set(f"{pid:03d}. {title}")
            self.card_desc.set(desc)

            self.accept_button.configure(state="normal")
            self.reject_button.configure(state="normal")
        else:
            self.progress_text.set(f"Completado: {total} de {total}")
            self.card_title.set("Revision completada")
            self.card_desc.set(
                "Ya revisaste las 100 propuestas. Puedes consultar las pestañas "
                "Aceptados y Rechazados, o usar Regresar para revisar la ultima decision."
            )
            self.accept_button.configure(state="disabled")
            self.reject_button.configure(state="disabled")

        self.back_button.configure(state="normal" if self.index > 0 else "disabled")
        self.refresh_lists()

    def refresh_lists(self):
        if not hasattr(self, "accepted_inner"):
            return

        for container in (self.accepted_inner, self.rejected_inner):
            for child in container.winfo_children():
                child.destroy()

        accepted_rows = [
            item for item in PROPOSALS
            if self.decisions.get(str(item[0])) == "accepted"
        ]
        rejected_rows = [
            item for item in PROPOSALS
            if self.decisions.get(str(item[0])) == "rejected"
        ]

        self.fill_list(self.accepted_inner, accepted_rows, "No hay propuestas aceptadas.")
        self.fill_list(self.rejected_inner, rejected_rows, "No hay propuestas rechazadas.")

    def fill_list(self, parent, rows, empty_text):
        if not rows:
            tk.Label(
                parent,
                text=empty_text,
                anchor="w",
                pady=10,
            ).pack(fill="x", padx=6)
            return

        for pid, title, desc in rows:
            row = tk.Frame(parent, bd=1, relief="solid", padx=10, pady=8)
            row.pack(fill="x", pady=3)

            tk.Label(
                row,
                text=f"{pid:03d}. {title}",
                font=("Segoe UI", 10, "bold"),
                anchor="w",
            ).pack(fill="x")

            tk.Label(
                row,
                text=desc,
                anchor="w",
                justify="left",
                wraplength=820,
            ).pack(fill="x", pady=(2, 0))

    def on_close(self):
        self.save_cache()


App = ProposalTool


def main():
    root = tk.Tk()
    root.title(TOOL_NAME)
    root.geometry("980x680")
    root.minsize(760, 520)
    tool = App(root)
    tool.pack(fill="both", expand=True)
    root.protocol("WM_DELETE_WINDOW", lambda: (tool.on_close(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
