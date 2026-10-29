import csv
from pathlib import Path

OUT = Path(__file__).with_name("ideas_1000000.csv")

AREAS = [
    "Hogar","Familia","Estudio","Docencia","Empleo","Negocio","Emprendimiento","Oficina","Comunidad","Cultura",
    "Accesibilidad","Adultos mayores","Ninos","Jovenes","Viajes","Fotografia","Multimedia","Juegos","Lectura","Escritura"
]
NEEDS = ["organizacion","aprendizaje","seguimiento","creatividad","colaboracion"]
FORMATS = [
    "Centro","Asistente","Estudio","Academia","Hub","Panel","Planner","Manager","Club","Laboratorio",
    "Biblioteca","Taller","Diario","Agenda","Catalogo","Simulador","Juego","Blog","Revista","Explorador"
]
MODES = ["Facil","Visual","Offline","Accesible","Familiar"]
AUDIENCES = [
    "familias","estudiantes","docentes","emprendedores","adultos mayores","ninos","jovenes","trabajadores",
    "comunidades","creadores","tecnicos","viajeros","lectores","jugadores","oficinas","negocios",
    "voluntarios","artistas","principiantes","usuarios avanzados"
]
CONTEXTS = ["casa","escuela","barrio","trabajo","sin internet"]

def main():
    count = 0
    with OUT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["id","area","propuesta"])
        for area in AREAS:
            for need in NEEDS:
                area_label = f"{area} - {need}"
                for fmt in FORMATS:
                    for mode in MODES:
                        for audience in AUDIENCES:
                            for context in CONTEXTS:
                                count += 1
                                w.writerow([
                                    count,
                                    area_label,
                                    f"{fmt} {mode} de {area} para {audience} en {context}",
                                ])
    if count != 1_000_000:
        raise RuntimeError(f"Conteo incorrecto: {count}")
    print(f"Generadas {count:,} ideas en {OUT}")

if __name__ == "__main__":
    main()
