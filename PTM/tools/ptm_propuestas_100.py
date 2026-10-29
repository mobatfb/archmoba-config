# ARGUMENTOS: propuestas ideas tools ptm catalogo checklist seleccion cache csv exportar planificar nuevas herramientas
import csv
import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

TOOL_NAME = "PTM - 1000 Propuestas"
TOOL_DESCRIPTION = "Revisor de 1000 propuestas nuevas y variadas para PTM: suites, juegos, blogs, simuladores, creatividad, entretenimiento, sistema y desarrollo."
TOOL_VERSION = "3.0.0"
APP_NAME = TOOL_NAME
CACHE_DIR = Path.home() / ".ptm"
CACHE_FILE = CACHE_DIR / "propuestas_catalogo_v3_cache.json"

PROPOSALS = []


def _add(title, desc):
    pid = len(PROPOSALS) + 1
    PROPOSALS.append((pid, title, desc))


# 1-100 · SUITES COMPLETAS
_SUITE_CONCEPTS = [
    ("PDF Studio", "Suite completa para unir, dividir, comprimir, ordenar, convertir, extraer imagenes, editar metadatos y previsualizar PDF."),
    ("Image Studio", "Suite para convertir, redimensionar, comprimir, recortar, rotar, limpiar metadatos y procesar imagenes por lotes."),
    ("Audio Studio", "Suite para reproducir, cortar, unir, convertir, normalizar, editar etiquetas y gestionar bibliotecas de audio."),
    ("Video Studio", "Suite para reproducir, recortar, unir, convertir, extraer audio, generar miniaturas y revisar metadatos de video."),
    ("Office Studio", "Centro para visualizar, convertir y organizar documentos Word, Excel, PowerPoint, PDF, CSV y texto."),
    ("Data Studio", "Espacio para abrir, limpiar, comparar, transformar y exportar CSV, JSON, Excel y SQLite."),
    ("Archive Studio", "Gestor unificado de ZIP, TAR y otros paquetes con crear, extraer, modificar, verificar y explorar contenido."),
    ("Web Studio", "Editor y visor local de HTML, CSS y JavaScript con previsualizacion, recursos y empaquetado de proyectos."),
    ("Developer Studio", "Entorno ligero con editor, terminal, Git, dependencias, entornos Python, ejecucion y diagnostico."),
    ("Media Studio", "Biblioteca unificada de musica, video e imagenes con recientes, favoritos, listas, busqueda y etiquetas."),
]
_SUITE_VARIANTS = [
    ("Lite", "minimalista y rapido"),
    ("Pro", "con funciones avanzadas y lotes"),
    ("Portable", "autocontenido y transportable"),
    ("Workspace", "con sesiones y pestanas persistentes"),
    ("Quick", "centrado en arrastrar y soltar"),
    ("Batch", "optimizado para procesamiento masivo"),
    ("Manager", "con biblioteca, historial y favoritos"),
    ("Inspector", "con previsualizacion profunda antes de modificar"),
    ("Automation", "con presets y cadenas de acciones"),
    ("Offline", "sin depender de servicios externos"),
]
for name, desc in _SUITE_CONCEPTS:
    for suffix, mode in _SUITE_VARIANTS:
        _add(f"{name} {suffix}", f"{desc} Variante {suffix}: {mode}. Se plantea como una sola app completa, no como varias mini-tools separadas.")


# 101-200 · JUEGOS
_GAME_GENRES = [
    ("Dungeon Roguelite", "salas aleatorias, mejoras, jefes y progresion persistente"),
    ("Arcade Racer", "carreras cortas, tiempos, rivales y desbloqueos"),
    ("Tower Defense", "oleadas, rutas, torres, mejoras y jefes"),
    ("Puzzle Quest", "rompecabezas con mapa, niveles y recompensas"),
    ("Survivor Arena", "oleadas continuas, mejoras y puntuacion"),
    ("Platform Adventure", "plataformas, secretos, coleccionables y niveles"),
    ("Card Battle", "mazos, cartas, combates y progresion"),
    ("Tycoon Manager", "gestion incremental, recursos y mejoras"),
    ("Arena Fighter", "combates rapidos, personajes y ranking"),
    ("Story Adventure", "exploracion, decisiones y narrativa por capitulos"),
]
_GAME_THEMES = [
    ("Neon", "cyberpunk de luces y hologramas"),
    ("Pyrion", "inspirado en el entorno Pyrion Linux"),
    ("Retro", "estetica de consola clasica"),
    ("Space", "naves, estaciones y planetas"),
    ("Horror", "supervivencia y atmosfera oscura"),
    ("Cyber", "redes, sistemas y entidades digitales"),
    ("Pixel", "pixel art y animacion 2D"),
    ("Police Tech", "entrenamiento arcade ficticio con estetica tecnologica"),
    ("Dungeon", "mazmorras infinitas y arquitectura holografica"),
    ("Arcade", "estilo de salon recreativo y puntuaciones"),
]
for genre, gameplay in _GAME_GENRES:
    for theme, setting in _GAME_THEMES:
        _add(f"{theme} {genre}", f"Juego integrado en PTM con {gameplay}, ambientado en un mundo {setting}. Guardado local, logros y ranking interno.")


# 201-300 · BLOGS / WIKIS / EXPERIENCIAS DE CONTENIDO
_CONTENT_FORMATS = [
    ("Blog interactivo", "publicaciones, categorias, favoritos y busqueda"),
    ("Revista digital", "ediciones, portadas, articulos y archivo"),
    ("Wiki local", "fichas enlazadas, indice y referencias"),
    ("Diario cronologico", "entradas por fecha, archivo y destacados"),
    ("Galeria comentada", "imagenes, fichas, notas y colecciones"),
    ("Enciclopedia", "articulos tematicos y referencias cruzadas"),
    ("Timeline interactivo", "eventos ordenados con fichas y filtros"),
    ("Museo virtual", "salas tematicas, piezas y descripciones"),
    ("Fan Hub", "personajes, curiosidades, noticias ficticias y galeria"),
    ("Story Hub", "capitulos, personajes, lore y contenido desbloqueable"),
]
_CONTENT_THEMES = [
    "videojuegos retro", "GTA San Andreas", "Crash Bandicoot", "Resident Evil",
    "ENTER Infinite Dungeon", "Pyrion", "ARCHMOBA", "historia de consolas",
    "tecnologia clasica", "cultura gamer"
]
for fmt, behavior in _CONTENT_FORMATS:
    for theme in _CONTENT_THEMES:
        _add(f"{fmt} - {theme}", f"Experiencia integrada en PTM sobre {theme}: {behavior}. Navegable como una app completa y con cache local.")


# 301-400 · SIMULADORES / EDUCATIVOS
_EDU_FORMATS = [
    ("Simulador", "simular escenarios con parametros y resultados"),
    ("Laboratorio", "realizar pruebas guiadas y experimentos"),
    ("Entrenador", "proponer ejercicios progresivos y registrar resultados"),
    ("Visualizador", "representar procesos de forma grafica e interactiva"),
    ("Sandbox", "experimentar libremente con configuraciones"),
    ("Tutor", "explicar conceptos paso a paso con ejemplos"),
    ("Challenge", "plantear retos con niveles y puntuacion"),
    ("Practice Lab", "practicar operaciones con feedback"),
    ("Explorer", "explorar conceptos mediante controles interactivos"),
    ("Academy", "organizar lecciones, practicas y progreso local"),
]
_EDU_TOPICS = [
    "Linux", "redes", "Python", "Git", "bases de datos",
    "algoritmos", "hardware PC", "seguridad defensiva",
    "terminal", "estructura de archivos"
]
for fmt, behavior in _EDU_FORMATS:
    for topic in _EDU_TOPICS:
        _add(f"{topic} {fmt}", f"Aplicacion educativa de {topic} para {behavior}, con ejemplos locales, progreso guardado y modo practica.")


# 401-500 · CREATIVIDAD / DISEÑO
_CREATIVE_APPS = [
    ("Pixel Editor", "dibujar pixel art con capas, paletas y exportacion"),
    ("Sprite Animator", "crear sprites y animaciones cuadro a cuadro"),
    ("Wallpaper Maker", "componer fondos con capas, texto y efectos"),
    ("Poster Maker", "crear posters y piezas verticales"),
    ("Icon Lab", "crear iconos, favicons y variantes de tamano"),
    ("UI Mockup", "crear bocetos de interfaces y paneles"),
    ("Card Designer", "disenar cartas, fichas y coleccionables"),
    ("Story Builder", "organizar escenas, personajes y dialogos"),
    ("Map Builder", "crear mapas 2D por cuadricula y capas"),
    ("Theme Builder", "crear paletas, temas y estilos para apps"),
]
_CREATIVE_STYLES = [
    "Neon", "Retro", "Minimal", "Cyber", "Dark",
    "Arcade", "Police Tech", "Holographic", "Pixel", "Pyrion"
]
for app_name, behavior in _CREATIVE_APPS:
    for style in _CREATIVE_STYLES:
        _add(f"{style} {app_name}", f"App creativa integrada en PTM para {behavior}, con estilo {style}, proyectos guardables y exportacion.")


# 501-600 · SISTEMA / DESARROLLO
_SYSTEM_APPS = [
    ("Control Center", "centralizar configuracion, estado y accesos"),
    ("Inspector", "examinar detalles tecnicos y dependencias"),
    ("Monitor", "mostrar actividad y consumo en tiempo real"),
    ("Manager", "administrar recursos y acciones frecuentes"),
    ("Dashboard", "resumir indicadores y accesos"),
    ("Recovery Center", "diagnosticar problemas y ofrecer reparaciones seguras"),
    ("Profiler", "medir consumo, tiempos y comportamiento"),
    ("Launcher", "descubrir y ejecutar componentes"),
    ("Audit Viewer", "registrar y consultar actividad local"),
    ("Workspace", "reunir herramientas relacionadas en pestanas"),
]
_SYSTEM_TOPICS = [
    "Python", "procesos", "memoria", "discos", "red",
    "Git", "dependencias", "servicios", "variables de entorno", "PTM"
]
for app_name, behavior in _SYSTEM_APPS:
    for topic in _SYSTEM_TOPICS:
        _add(f"{topic.title()} {app_name}", f"Aplicacion de sistema/desarrollo para {topic}: {behavior}, con historial local y acciones controladas.")


# 601-700 · PRODUCTIVIDAD / ORGANIZACION
_PRODUCTIVITY_APPS = [
    ("Workspace", "reunir informacion y acciones en un espacio"),
    ("Planner", "planificar fechas, tareas y prioridades"),
    ("Tracker", "seguir progreso, estados y cambios"),
    ("Catalog", "catalogar elementos con busqueda y etiquetas"),
    ("Notebook", "guardar notas, enlaces y referencias"),
    ("Board", "organizar tarjetas por columnas y estados"),
    ("Timeline", "ordenar eventos cronologicamente"),
    ("Dashboard", "resumir datos y accesos importantes"),
    ("Inbox", "recibir, clasificar y archivar elementos"),
    ("Organizer", "clasificar y encontrar informacion rapidamente"),
]
_PRODUCTIVITY_TOPICS = [
    "proyectos", "archivos", "ideas", "tareas", "estudio",
    "colecciones", "software", "juegos", "documentos", "recursos"
]
for app_name, behavior in _PRODUCTIVITY_APPS:
    for topic in _PRODUCTIVITY_TOPICS:
        _add(f"{topic.title()} {app_name}", f"App de productividad para {topic}: {behavior}, con filtros, busqueda, cache y persistencia.")


# 701-800 · ENTRETENIMIENTO / EXPERIENCIAS
_EXPERIENCES = [
    ("Jukebox", "biblioteca interactiva con reproduccion y favoritos"),
    ("Arcade Hub", "menu de minijuegos y puntuaciones"),
    ("Trivia", "preguntas, categorias y ranking local"),
    ("Quiz Show", "rondas de preguntas con tiempo y dificultad"),
    ("Collection Viewer", "colecciones visuales con fichas y filtros"),
    ("Randomizer", "retos, combinaciones y selecciones aleatorias"),
    ("Virtual Shelf", "estanteria visual para colecciones"),
    ("Showcase", "presentar contenido en modo exposicion"),
    ("Radio", "listas y reproduccion continua de audio local"),
    ("Screensaver", "visualizaciones animadas y escenas ambient"),
]
_EXPERIENCE_THEMES = [
    "Retro Gaming", "ARCHMOBA", "Pyrion", "Neon", "Pixel",
    "Horror", "Space", "Cyber", "90s", "Arcade"
]
for exp, behavior in _EXPERIENCES:
    for theme in _EXPERIENCE_THEMES:
        _add(f"{theme} {exp}", f"Experiencia de entretenimiento integrada en PTM con tema {theme}: {behavior}, configuracion y estado local.")


# 801-900 · UTILIDADES COMPLETAS, NO FRAGMENTADAS
_UTILITY_SUITES = [
    ("File Toolbox", "buscar, renombrar, duplicados, hash, clasificar, copiar y comparar archivos"),
    ("Network Toolbox", "ping, DNS, rutas, interfaces, conexiones, velocidad y diagnostico"),
    ("Text Toolbox", "buscar, reemplazar, comparar, regex, codificar, limpiar y transformar texto"),
    ("Developer Toolbox", "JSON, XML, YAML, Base64, URL, UUID, timestamps y utilidades de codigo"),
    ("Database Toolbox", "SQLite, CSV, JSON, importacion, exportacion, consultas y respaldos"),
    ("Backup Toolbox", "crear, verificar, comparar, restaurar y programar copias locales"),
    ("System Toolbox", "procesos, servicios, inicio, entorno, recursos y diagnostico"),
    ("Media Toolbox", "metadatos, conversion, miniaturas, inspeccion y procesamiento multimedia"),
    ("Package Toolbox", "ZIP, TAR, checksums, estructura, extraccion y creacion de paquetes"),
    ("Web Toolbox", "HTTP, headers, SSL, APIs, descargas, capturas y pruebas web"),
]
_UTILITY_VARIANTS = [
    ("Quick", "flujo rapido"),
    ("Pro", "controles avanzados"),
    ("Portable", "modo autocontenido"),
    ("Batch", "procesamiento por lotes"),
    ("Visual", "interfaz visual"),
    ("Inspector", "previsualizacion y diagnostico"),
    ("Automation", "presets y automatizacion"),
    ("Manager", "historial y biblioteca"),
    ("Offline", "funcionamiento local"),
    ("Workspace", "sesiones y pestanas"),
]
for name, desc in _UTILITY_SUITES:
    for suffix, mode in _UTILITY_VARIANTS:
        _add(f"{name} {suffix}", f"Suite unificada para {desc}. Variante {suffix}: {mode}. Agrupa funciones relacionadas en una sola aplicacion.")


# 901-1000 · ECOSISTEMA PTM / EXPERIMENTOS
_PTM_CONCEPTS = [
    ("App Store local", "catalogar, instalar y actualizar paquetes PTM desde fuentes configuradas"),
    ("Tool Forge", "crear esqueletos y paquetes compatibles con PTM"),
    ("Theme Lab", "crear y probar temas visuales de PTM"),
    ("Plugin Playground", "probar APIs internas y componentes en un entorno aislado"),
    ("Demo Gallery", "mostrar demos tecnicas de interfaces y controles"),
    ("Benchmark Lab", "comparar rendimiento de componentes y dependencias"),
    ("Compatibility Center", "comprobar compatibilidad Windows, Linux y Pyrion"),
    ("Update Center", "gestionar versiones y actualizaciones de componentes"),
    ("Session Manager", "guardar y restaurar grupos de pestanas y tools"),
    ("Command Palette", "buscar acciones y herramientas desde un lanzador rapido"),
]
_PTM_VARIANTS = [
    ("Lite", "minimalista y rapido"),
    ("Pro", "con opciones avanzadas"),
    ("Visual", "centrado en paneles graficos"),
    ("Portable", "autocontenido"),
    ("Offline", "sin servicios externos"),
    ("Developer", "orientado a desarrollo"),
    ("Experimental", "para probar ideas nuevas"),
    ("Safe Mode", "con operaciones limitadas y reversibles"),
    ("Workspace", "con sesiones persistentes"),
    ("Automation", "con acciones encadenadas"),
]
for name, desc in _PTM_CONCEPTS:
    for suffix, mode in _PTM_VARIANTS:
        _add(f"{name} {suffix}", f"Concepto de ecosistema PTM para {desc}. Variante {suffix}: {mode}.")


assert len(PROPOSALS) == 1000


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

        tk.Button(
            top,
            text="Descargar CSV",
            command=self.export_csv,
            padx=10,
            pady=4,
        ).pack(side="right", padx=(0, 12))

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
                f"Ya revisaste las {total} propuestas. Puedes consultar las pestañas "
                "Aceptados y Rechazados, descargar el CSV o usar Regresar para revisar la ultima decision."
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

    def export_csv(self):
        reviewed = [
            (pid, title, desc, self.decisions.get(str(pid)))
            for pid, title, desc in PROPOSALS
            if self.decisions.get(str(pid)) in ("accepted", "rejected")
        ]
        if not reviewed:
            messagebox.showinfo("Sin decisiones", "Aun no hay propuestas aceptadas o rechazadas para exportar.")
            return

        path = filedialog.asksaveasfilename(
            title="Guardar decisiones en CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Todos", "*.*")],
            initialfile="ptm_propuestas_decisiones.csv",
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.writer(fh, delimiter=";")
                writer.writerow(["id", "titulo", "descripcion", "estado"])
                for pid, title, desc, state in reviewed:
                    writer.writerow([
                        pid,
                        title,
                        desc,
                        "ACEPTADO" if state == "accepted" else "RECHAZADO",
                    ])
            messagebox.showinfo(
                "CSV generado",
                f"Se exportaron {len(reviewed)} decisiones.\n{path}",
            )
        except Exception as exc:
            messagebox.showerror("Error", f"No se pudo crear el CSV:\n{exc}")

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
