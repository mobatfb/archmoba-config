# ARGUMENTOS: propuestas ideas tools ptm catalogo checklist seleccion cache csv exportar planificar nuevas herramientas
import csv
import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

TOOL_NAME = "PTM - 10000 Propuestas Sociales"
TOOL_DESCRIPTION = "Catalogo de 10000 propuestas orientadas a necesidades reales de la sociedad: hogar, educacion, empleo, negocios, familia, comunidad, accesibilidad, creatividad, juegos y tecnologia."
TOOL_VERSION = "5.0.0"
APP_NAME = TOOL_NAME
CACHE_DIR = Path.home() / ".ptm"
CACHE_FILE = CACHE_DIR / "propuestas_catalogo_social_v4_cache.json"

PROPOSALS = []


def _add(title, desc):
    pid = len(PROPOSALS) + 1
    PROPOSALS.append((pid, title, desc))


# Catalogo social: 25 areas x 4 necesidades completas x 10 enfoques = 1000.
# Cada propuesta representa una app completa y evita dividir funciones que
# naturalmente pertenecen a una misma solucion.
_SOCIAL_AREAS = [
    ("Hogar", [
        ("Organizador del Hogar", "calendario familiar, pendientes, compras, mantenimiento, documentos y recordatorios del hogar"),
        ("Finanzas del Hogar", "presupuesto, gastos, ingresos, metas, deudas y reportes familiares"),
        ("Inventario del Hogar", "electrodomesticos, garantias, facturas, ubicacion de objetos y vencimientos"),
        ("Recetario Familiar", "recetas, menus semanales, ingredientes, lista de compras y favoritos"),
    ]),
    ("Familia", [
        ("Agenda Familiar", "actividades, citas, cumpleaños, eventos escolares y tareas compartidas"),
        ("Album Familiar", "fotos, videos, recuerdos, fechas, personas y colecciones"),
        ("Arbol Familiar", "familiares, relaciones, historias, fotos y linea de tiempo"),
        ("Centro de Rutinas", "rutinas diarias, responsabilidades, recompensas y seguimiento"),
    ]),
    ("Estudiantes", [
        ("Planificador de Estudios", "materias, tareas, examenes, horarios, metas y progreso"),
        ("Cuaderno Estudiantil", "apuntes, archivos, enlaces, resumentes y organizacion por materia"),
        ("Preparador de Examenes", "banco de preguntas, simulacros, errores frecuentes y estadisticas"),
        ("Gestor de Trabajos", "proyectos, entregas, bibliografia, archivos y checklist"),
    ]),
    ("Docentes", [
        ("Aula Personal", "planificacion de clases, recursos, actividades y calendario"),
        ("Generador de Evaluaciones", "preguntas, bancos, versiones, respuestas y exportacion"),
        ("Seguimiento de Clase", "participacion, observaciones, actividades y avances"),
        ("Biblioteca Docente", "materiales, fichas, enlaces, documentos y clasificacion"),
    ]),
    ("Aprendizaje", [
        ("Academia de Matematicas", "lecciones, ejercicios, niveles, retos y progreso"),
        ("Academia de Lectura", "textos, comprension, vocabulario, retos y progreso"),
        ("Academia de Idiomas", "vocabulario, frases, practica, audio local y progreso"),
        ("Academia Digital", "computacion basica, archivos, internet, seguridad y practica"),
    ]),
    ("Empleo", [
        ("Creador de Curriculum", "CV, perfiles, habilidades, experiencia, plantillas y exportacion"),
        ("Buscador de Empleo Personal", "registro de vacantes, postulaciones, contactos, fechas y estados"),
        ("Preparador de Entrevistas", "preguntas, respuestas, practica, notas y evaluacion"),
        ("Portafolio Profesional", "proyectos, logros, certificados, enlaces y presentacion"),
    ]),
    ("Pequenos Negocios", [
        ("Caja para Negocio", "ventas, ingresos, egresos, arqueo, productos y reportes"),
        ("Inventario para Negocio", "productos, existencias, entradas, salidas, alertas y proveedores"),
        ("Clientes y Pedidos", "clientes, pedidos, estados, pagos, entregas y notas"),
        ("Control Comercial", "ventas, compras, gastos, metas, productos y resumen del negocio"),
    ]),
    ("Emprendimiento", [
        ("Plan de Negocio", "idea, propuesta de valor, costos, clientes, tareas y objetivos"),
        ("Calculadora de Precios", "costos, margen, impuestos configurables, precio sugerido y escenarios"),
        ("Catalogo de Productos", "productos, imagenes, precios, variantes y exportacion"),
        ("Gestor de Ferias", "productos, stock, ventas, contactos y resultados de eventos"),
    ]),
    ("Oficina", [
        ("Centro de Documentos", "PDF, Word, Excel, texto, conversion, organizacion y busqueda"),
        ("PDF Studio", "unir, dividir, comprimir, ordenar, rotar, convertir, extraer y revisar PDF"),
        ("Agenda de Oficina", "reuniones, pendientes, contactos, notas y recordatorios"),
        ("Archivo Digital", "clasificacion, etiquetas, busqueda, historial y ubicacion documental"),
    ]),
    ("Productividad", [
        ("Mi Dia", "prioridades, tareas, agenda, notas rapidas y progreso diario"),
        ("Gestor de Proyectos", "proyectos, etapas, tareas, responsables, fechas y avance"),
        ("Tablero Kanban", "columnas, tarjetas, prioridades, etiquetas y archivo"),
        ("Centro de Ideas", "ideas, categorias, notas, enlaces, archivos y estados"),
    ]),
    ("Bienestar", [
        ("Diario de Bienestar", "estado de animo, habitos, notas, reflexiones y tendencias personales"),
        ("Rutinas Saludables", "agua, descanso, actividad, pausas, objetivos y seguimiento no clinico"),
        ("Pausas Activas", "temporizadores, ejercicios suaves, recordatorios y historial"),
        ("Planificador Personal", "rutinas, metas, descanso, actividades y balance semanal"),
    ]),
    ("Adultos Mayores", [
        ("Panel Facil", "accesos grandes a funciones frecuentes, notas, reloj y contactos"),
        ("Agenda Simple", "citas, eventos, cumpleaños, pendientes y recordatorios visuales"),
        ("Album de Recuerdos", "fotos, nombres, fechas, historias y reproduccion sencilla"),
        ("Juegos de Memoria", "parejas, secuencias, palabras, imagenes y niveles ajustables"),
    ]),
    ("Accesibilidad", [
        ("Lector Facil", "texto grande, contraste, lectura por bloques y controles simples"),
        ("Escritorio Accesible", "accesos grandes, alto contraste, navegacion por teclado y favoritos"),
        ("Magnificador", "zoom de contenido, seguimiento de cursor y presets visuales"),
        ("Comunicador Visual", "tarjetas, frases frecuentes, pictogramas y tableros configurables"),
    ]),
    ("Comunidad", [
        ("Agenda Comunitaria", "eventos, reuniones, actividades, lugares y recordatorios"),
        ("Directorio Comunitario", "servicios, contactos, horarios, categorias y notas"),
        ("Tablero Vecinal", "anuncios locales, tareas comunitarias, eventos y archivo"),
        ("Banco de Recursos", "prestamos comunitarios, objetos, responsables, fechas y devoluciones"),
    ]),
    ("Cultura", [
        ("Museo Virtual", "colecciones, salas, fichas, imagenes, historias y recorridos"),
        ("Archivo de Historia Local", "fotos, documentos, testimonios, fechas y lugares"),
        ("Biblioteca Cultural", "libros, articulos, autores, temas y favoritos"),
        ("Linea de Tiempo Cultural", "eventos, personajes, obras, imagenes y filtros"),
    ]),
    ("Blogs y Publicaciones", [
        ("Blog Personal", "entradas, categorias, imagenes, archivo, favoritos y busqueda"),
        ("Revista Digital", "ediciones, articulos, portadas, secciones y archivo"),
        ("Diario de Viaje", "lugares, fotos, notas, rutas y recuerdos"),
        ("Fan Blog", "publicaciones, personajes, galerias, curiosidades y colecciones"),
    ]),
    ("Creatividad", [
        ("Estudio Grafico", "dibujar, capas, texto, formas, recorte, exportacion y proyectos"),
        ("Creador de Posters", "plantillas, texto, imagenes, fondos, formatos y exportacion"),
        ("Pixel Art Studio", "pixel art, paletas, capas, sprites y animacion"),
        ("Creador de Historias", "personajes, escenas, dialogos, capitulos y exportacion"),
    ]),
    ("Fotografia", [
        ("Organizador de Fotos", "albumes, etiquetas, personas, fechas, favoritos y busqueda"),
        ("Editor de Fotos Simple", "recorte, giro, brillo, contraste, tamano, formato y exportacion"),
        ("Album de Eventos", "seleccion, orden, portadas, comentarios y presentacion"),
        ("Limpiador de Fotos", "duplicados, metadatos, nombres, clasificacion y respaldo"),
    ]),
    ("Multimedia", [
        ("Centro Multimedia", "musica, videos, fotos, listas, favoritos, recientes y busqueda"),
        ("Audio Studio", "reproducir, cortar, unir, convertir, normalizar y editar etiquetas"),
        ("Video Studio", "reproducir, recortar, unir, convertir, miniaturas y metadatos"),
        ("Jukebox Familiar", "biblioteca musical, listas, portadas, favoritos y modo pantalla completa"),
    ]),
    ("Juegos", [
        ("Arcade Familiar", "coleccion de minijuegos sencillos, perfiles, puntuaciones y dificultad"),
        ("Aventura Educativa", "historia, exploracion, retos de conocimiento y progreso"),
        ("Puzzle Club", "rompecabezas, niveles, pistas, logros y ranking local"),
        ("Juego de Gestion", "recursos, decisiones, objetivos, mejoras y progreso persistente"),
    ]),
    ("Ninos", [
        ("Aprende Jugando", "letras, numeros, colores, formas, sonidos y recompensas"),
        ("Cuentos Interactivos", "historias, escenas, decisiones, ilustraciones y lectura guiada"),
        ("Dibujo Infantil", "pinceles grandes, sellos, colores, fondos y guardado"),
        ("Mini Juegos Educativos", "memoria, parejas, secuencias, matematicas y vocabulario"),
    ]),
    ("Tecnologia Cotidiana", [
        ("Asistente de Archivos", "buscar, organizar, renombrar, copiar, comprimir y localizar archivos"),
        ("Centro de Dispositivos", "informacion de discos, USB, almacenamiento y acciones frecuentes"),
        ("Diagnostico del Equipo", "CPU, RAM, discos, red, sistema, estado y reporte facil"),
        ("Centro de Copias", "respaldos, sincronizacion, verificacion y restauracion local"),
    ]),
    ("Internet y Seguridad", [
        ("Centro de Seguridad Digital", "contrasenas, copias, privacidad, buenas practicas y checklist"),
        ("Inspector de Enlaces", "URL, dominio, cabeceras, certificado, redireccion y notas"),
        ("Centro de Descargas", "descargas, historial, carpetas, verificacion y organizacion"),
        ("Navegacion Familiar", "favoritos, historial local, accesos rapidos y perfiles"),
    ]),
    ("Desarrollo", [
        ("Developer Studio", "editor, terminal, Git, dependencias, ejecucion, proyectos y diagnostico"),
        ("API Studio", "GET, POST, headers, JSON, multipart, historial y colecciones"),
        ("Data Studio", "CSV, JSON, Excel, SQLite, filtros, transformaciones y exportacion"),
        ("PTM Tool Builder", "crear, probar, empaquetar, describir y registrar nuevas apps para PTM"),
    ]),
    ("Viajes y Vida Local", [
        ("Planificador de Viajes", "destinos, itinerario, presupuesto, reservas manuales y checklist"),
        ("Diario de Viajes", "lugares, fotos, notas, gastos y recuerdos"),
        ("Maleta Inteligente", "listas por tipo de viaje, personas, clima manual y pendientes"),
        ("Explorador Local", "lugares guardados, categorias, notas, favoritos y rutas manuales"),
    ]),
]

_APPROACHES = [
    ("Esencial", "interfaz simple y directa para cualquier persona"),
    ("Familiar", "pensado para uso compartido por integrantes del hogar"),
    ("Guiado", "con pasos, ayudas y explicaciones para usuarios principiantes"),
    ("Visual", "con tarjetas, iconos grandes, paneles y poco texto tecnico"),
    ("Offline", "centrado en funcionar localmente sin depender de servicios externos"),
    ("Accesible", "con texto grande, contraste, teclado y controles faciles"),
    ("Organizador", "con categorias, etiquetas, busqueda, filtros e historial"),
    ("Planner", "con calendario, metas, estados, seguimiento y recordatorios"),
    ("Comunitario", "orientado a grupos pequenos, asociaciones o espacios compartidos"),
    ("Pro", "con reportes, exportaciones, configuracion y funciones avanzadas"),
]

for area, concepts in _SOCIAL_AREAS:
    for base_name, base_desc in concepts:
        for suffix, approach in _APPROACHES:
            _add(
                f"{base_name} {suffix}",
                f"{area}: aplicacion completa para {base_desc}. Enfoque {suffix}: {approach}.",
            )

# Ampliacion 1001-10000: se conservan intactas las primeras 1000 propuestas
# para mantener compatible el progreso de la version 4.0.0. Cada una recibe
# nueve contextos sociales adicionales que cambian prioridades y requisitos.
_BASE_1000 = list(PROPOSALS)

_CONTEXTS = [
    ("Rural", "prioriza funcionamiento offline, equipos modestos, datos locales y uso comunitario"),
    ("Urbano", "prioriza rapidez, alta cantidad de informacion, movilidad y uso cotidiano"),
    ("Familiar", "prioriza perfiles del hogar, uso compartido, simplicidad y privacidad local"),
    ("Escolar", "prioriza estudiantes, docentes, actividades guiadas y organizacion educativa"),
    ("Comunitario", "prioriza grupos, asociaciones, actividades compartidas y gestion sencilla"),
    ("Microemprendimiento", "prioriza costos bajos, ventas, organizacion, reportes y operacion diaria"),
    ("Joven", "prioriza experiencia visual, retos, gamificacion, rapidez y personalizacion"),
    ("Adulto Mayor", "prioriza accesibilidad, texto grande, pasos simples y controles claros"),
    ("Sin Internet", "prioriza funcionamiento completamente local, exportacion manual y respaldo"),
]

for base_id, base_title, base_desc in _BASE_1000:
    for context_name, context_desc in _CONTEXTS:
        _add(
            f"{base_title} - {context_name}",
            f"{base_desc} Contexto {context_name}: {context_desc}.",
        )

assert len(PROPOSALS) == 10000


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
        self.current_tab = "Propuestas"

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

        title_box = tk.Frame(top)
        title_box.pack(side="left")

        tk.Label(
            title_box,
            text=APP_NAME,
            font=("Segoe UI", 16, "bold"),
        ).pack(side="left")

        tk.Label(
            title_box,
            text=f"v{TOOL_VERSION}",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(10, 0), pady=(5, 0))

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
        self.current_tab = name
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
        if self.current_tab in ("Aceptados", "Rechazados"):
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
