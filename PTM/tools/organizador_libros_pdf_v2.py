#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Organizador de Libros a PDF, con interfaz grafica para Windows.

Solo utiliza enlaces de imagen que Google Books expone al lector. No elude
controles de acceso, vista previa limitada, DRM ni CAPTCHA. Utilizar con
material cuya descarga/reutilizacion este autorizada.

Sin argumentos: abre la interfaz grafica.
Con argumentos: funciona desde la consola (ver --help).
Requisitos: requests, Pillow, reportlab. Interfaz: tkinter (incluido en Python).
"""

from __future__ import annotations

import argparse
import csv
import html
import io
import json
import os
import queue
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urljoin, urlparse

try:
    import requests
    from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageStat
    from reportlab.pdfgen import canvas
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError as exc:
    raise SystemExit(
        f"Falta una dependencia: {exc}\n"
        "Instala las dependencias: py -m pip install -r requirements.txt\n"
        "o ejecuta INSTALAR_Y_EJECUTAR.bat."
    )

URL_INICIAL = ""
# Google Books usa prefijos: PT (preliminares), PA (paginacion ordinaria), PR, PP...
PATRON_PAGINA = re.compile(r"^([A-Z]{1,4})(\d+)$", re.IGNORECASE)
PATRON_PREFIJO = re.compile(r"^[A-Z]{1,4}$", re.IGNORECASE)
PREFIJOS_GUI = ("AUTO", "PA", "PT", "PR", "PP", "PPA")
PATRON_HOST = re.compile(
    r"^(?:www\.|books\.)?google\.(?:com(?:\.[a-z]{2})?|co\.[a-z]{2}|[a-z]{2,3})$",
    re.IGNORECASE,
)
MODOS_FALTANTES = ("omitir", "blanco", "aviso", "detener")
Notificador = Callable[[str, Any], None]


@dataclass(frozen=True)
class Configuracion:
    url: str
    desde: int = 1
    hasta: int | None = None
    carpeta_salida: Path = Path.cwd()
    modo_faltantes: str = "aviso"
    detectar_blancas: bool = True
    pausa: float = 0.7
    max_paginas: int = 400
    solo_cache: bool = False
    ruta_pdf: Path | None = None
    prefijo: str | None = None  # None: inferido del enlace o del inventario

    def validar(self) -> tuple[str, str]:
        libro_id, base = extraer_volumen(self.url)
        if self.desde < 1:
            raise ValueError("La primera pagina debe empezar en 1 o posterior.")
        if self.prefijo is not None and not PATRON_PREFIJO.fullmatch(self.prefijo):
            raise ValueError("Tipo de pagina invalido (ej.: PA, PT, PR, PP).")
        if self.hasta is not None and self.hasta < self.desde:
            raise ValueError("'Hasta' no puede ser menor que 'Desde'.")
        if self.max_paginas < 1 or self.max_paginas > 5000:
            raise ValueError("El maximo de paginas debe estar entre 1 y 5000.")
        if self.hasta is not None and self.hasta - self.desde + 1 > self.max_paginas:
            raise ValueError(
                f"El intervalo supera el limite de {self.max_paginas} paginas. "
                "Aumenta el limite o reduce el intervalo."
            )
        if not 0 <= self.pausa <= 60:
            raise ValueError("La pausa debe estar entre 0 y 60 segundos.")
        if self.modo_faltantes not in MODOS_FALTANTES:
            raise ValueError("Politica para paginas vacias no reconocida.")
        return libro_id, base


@dataclass
class Resultado:
    libro_id: str
    pdf: Path | None
    csv: Path
    carpeta_imagenes: Path
    obtenidas: int
    faltantes: int
    procesadas: int
    total: int
    paginas_pdf: int
    motivo_fin: str


def numero_pagina(valor: str, obligatorio: bool = True, prefijo: str | None = None) -> int | None:
    """Acepta 7, PT7, PA7, PR7... y valida tipo explicito."""
    valor = valor.strip().upper()
    if not valor and not obligatorio:
        return None
    coinc = re.fullmatch(r"([A-Z]{1,4})?(\d+)", valor)
    if not coinc or int(coinc.group(2)) < 1:
        raise ValueError("Escribe un numero de pagina como 1, PA20 o PT7.")
    if prefijo and coinc.group(1) and coinc.group(1) != prefijo.upper():
        raise ValueError(f"El campo {valor} no corresponde al tipo {prefijo.upper()} seleccionado.")
    return int(coinc.group(2))


def prefijo_escrito(valor: str) -> str | None:
    coinc = re.fullmatch(r"([A-Z]{1,4})\d+", valor.strip().upper())
    return coinc.group(1) if coinc else None


def normalizar_url(texto: str) -> str:
    return html.unescape(texto.strip().strip("<>").replace("\\&", "&"))


def prefijo_del_enlace(url: str) -> str | None:
    try:
        pagina = parse_qs(urlparse(normalizar_url(url)).query).get("pg", [""])[0].upper()
        m = PATRON_PAGINA.fullmatch(pagina)
        return m.group(1) if m else None
    except ValueError:
        return None


def elegir_prefijo(url: str, paginas: list[str], fijado: str | None = None) -> str:
    if fijado and fijado.upper() != "AUTO":
        return fijado.upper()
    en_url = prefijo_del_enlace(url)
    if en_url:
        return en_url
    recuento: dict[str, int] = {}
    for pagina in paginas:
        m = PATRON_PAGINA.fullmatch(str(pagina).upper())
        if m:
            recuento[m.group(1)] = recuento.get(m.group(1), 0) + 1
    if recuento:
        return sorted(recuento, key=lambda tipo: (-recuento[tipo], tipo != "PA", tipo))[0]
    return "PT"  # compatibilidad con enlaces sin pg ni inventario


def extraer_volumen(url: str) -> tuple[str, str]:
    """Acepta lector ?id= y enlaces nuevos /books/edition/.../ID."""
    parsed = urlparse(normalizar_url(url))
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("https", "http") or not PATRON_HOST.fullmatch(host):
        raise ValueError("Pega un enlace valido de Google Books (books.google.com o google.com/books/edition).")
    if parsed.path.rstrip("/") == "/books":
        libro_id = parse_qs(parsed.query).get("id", [""])[0]
    else:
        m = re.fullmatch(r"/books/edition/[^/]+/([A-Za-z0-9_-]{8,40})/?", parsed.path)
        if not m:
            raise ValueError("Enlace no reconocido: usa /books?id=... o /books/edition/TITULO/ID.")
        libro_id = m.group(1)
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,40}", libro_id):
        raise ValueError("El enlace no contiene un identificador de libro valido.")
    # La edicion moderna no ofrece necesariamente el inventario del lector clasico.
    # Normalizamos ambos enlaces al mismo lector, manteniendo el dominio regional.
    sufijo = host.split("google.", 1)[1]
    return libro_id, f"{parsed.scheme}://books.google.{sufijo}/books"


def configurar_sesion(referer: str) -> requests.Session:
    sesion = requests.Session()
    reintentos = Retry(
        total=2,
        backoff_factor=0.6,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=frozenset(("GET",)),
    )
    adaptador = HTTPAdapter(max_retries=reintentos)
    sesion.mount("https://", adaptador)
    sesion.mount("http://", adaptador)
    sesion.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "es-EC,es;q=0.9,en;q=0.7",
        "Referer": normalizar_url(referer),
    })
    return sesion


def metadatos_en_html(contenido: str) -> dict[str, Any] | None:
    """Encuentra el inventario de paginas publicadas por el lector, si existe."""
    for match in re.finditer(r"_OC_Run\((.*?)\)\s*;", contenido, re.S):
        try:
            args = json.loads("[" + match.group(1) + "]")
            if args and isinstance(args[0], dict) and isinstance(args[0].get("page"), list):
                info = args[1] if len(args) > 1 and isinstance(args[1], dict) else {}
                return {"pages": args[0]["page"], "info": info}
        except (ValueError, TypeError, IndexError):
            continue
    return None


def enlaces_en_html(texto: str, base: str, libro_id: str) -> dict[str, str]:
    """Localiza enlaces de imagen realmente publicados en el HTML."""
    urls: dict[str, str] = {}
    texto = html.unescape(texto).replace("\\u0026", "&").replace("\\/", "/")
    patrones = (
        r"(?:src|href|data-src)\s*=\s*['\"]([^'\"]+)['\"]",
        r"(https?://[^\s<>\"']+)",
    )
    for patron in patrones:
        for match in re.finditer(patron, texto, re.IGNORECASE):
            posible = match.group(1).rstrip("),;\\")
            if "img=" not in posible or "pg=" not in posible:
                continue
            absoluta = urljoin(base, posible)
            url_partes = urlparse(absoluta)
            parametros = parse_qs(url_partes.query)
            pid = parametros.get("pg", [""])[0].upper()
            if parametros.get("id", [""])[0] != libro_id:
                continue
            if not PATRON_PAGINA.fullmatch(pid) or parametros.get("img", [""])[0] not in ("1", "true"):
                continue
            if not url_partes.path.startswith("/books") or not PATRON_HOST.fullmatch(url_partes.hostname or ""):
                continue
            urls.setdefault(pid, absoluta)
    return urls


def leer_inventario(sesion: requests.Session, libro_id: str, base: str, url: str
                    ) -> tuple[list[str], dict[str, str], dict[str, Any]]:
    lector_url = normalizar_url(url).split("#", 1)[0]
    # Los enlaces /books/edition/... se consultan por el lector clasico equivalente.
    if "/books/edition/" in urlparse(lector_url).path:
        pg = parse_qs(urlparse(lector_url).query).get("pg", [""])[0]
        parametros = {"id": libro_id}
        if PATRON_PAGINA.fullmatch(pg):
            parametros["pg"] = pg
        respuesta = sesion.get(base, params=parametros, timeout=(12, 35))
    else:
        respuesta = sesion.get(lector_url, timeout=(12, 35))
    if respuesta.status_code in (403, 429):
        raise PermissionError(f"Google Books ha limitado el acceso (HTTP {respuesta.status_code}).")
    respuesta.raise_for_status()
    metadatos = metadatos_en_html(respuesta.text)
    enlaces = enlaces_en_html(respuesta.text, base, libro_id)
    if metadatos:
        pids = [str(p.get("pid", "")).upper() for p in metadatos["pages"] if isinstance(p, dict)]
        for pagina in metadatos["pages"]:
            if not isinstance(pagina, dict):
                continue
            pid, src = str(pagina.get("pid", "")).upper(), pagina.get("src")
            if PATRON_PAGINA.fullmatch(pid) and isinstance(src, str) and src:
                enlaces.setdefault(pid, urljoin(base, html.unescape(src)))
        return pids, enlaces, metadatos["info"]
    return [], enlaces, {}


def consultar_paginas(sesion: requests.Session, base: str, libro_id: str,
                      pid: str) -> dict[str, str]:
    """Busca enlaces visibles del lector, sin inventar ni firmar URLs privadas."""
    respuesta = sesion.get(
        base, params={"id": libro_id, "pg": pid, "jscmd": "click3"},
        timeout=(12, 35),
    )
    if respuesta.status_code in (403, 429):
        raise PermissionError(f"Google Books ha limitado las consultas (HTTP {respuesta.status_code}).")
    respuesta.raise_for_status()
    try:
        payload = respuesta.json()
    except ValueError:
        return enlaces_en_html(respuesta.text, base, libro_id)
    if not isinstance(payload, dict):
        return {}
    urls: dict[str, str] = {}
    for pagina in payload.get("page", []):
        if not isinstance(pagina, dict):
            continue
        item_pid = str(pagina.get("pid", "")).upper()
        src = pagina.get("src")
        if PATRON_PAGINA.fullmatch(item_pid) and isinstance(src, str) and src:
            urls[item_pid] = urljoin(base, html.unescape(src))
    return urls


def es_imagen_blanca(imagen: Image.Image) -> bool:
    """Deteccion conservadora: imagen esencialmente blanca y sin texto visible.

    No interpreta una pagina con pocos caracteres como vacia.
    """
    copia = ImageOps.grayscale(imagen)
    copia.thumbnail((150, 210))
    hist = copia.histogram()
    total = max(1, sum(hist))
    oscuros = sum(hist[:240]) / total
    gris_medio = ImageStat.Stat(copia).mean[0]
    return gris_medio > 247 and oscuros < 0.0015


def preparar_jpeg(datos: bytes, destino: Path, detectar_blancas: bool
                  ) -> tuple[int, int, bool]:
    if len(datos) > 35 * 1024 * 1024:
        raise ValueError("Imagen excede el limite de 35 MB.")
    with Image.open(io.BytesIO(datos)) as original:
        original.load()
        if original.width < 250 or original.height < 250:
            raise ValueError(f"Imagen demasiado pequena: {original.width}x{original.height}.")
        imagen = ImageOps.exif_transpose(original)
        blanca = detectar_blancas and es_imagen_blanca(imagen)
        if blanca:
            return imagen.width, imagen.height, True
        if imagen.mode == "RGBA" or (imagen.mode == "P" and "transparency" in imagen.info):
            con_alpha = imagen.convert("RGBA")
            fondo = Image.new("RGB", con_alpha.size, "white")
            fondo.paste(con_alpha, mask=con_alpha.getchannel("A"))
            imagen = fondo
        else:
            imagen = imagen.convert("RGB")
        # Se guarda de forma atomica para no reciclar archivos parciales.
        temporal = destino.with_suffix(".part.jpg")
        try:
            imagen.save(temporal, "JPEG", quality=92, optimize=True)
            temporal.replace(destino)
        finally:
            temporal.unlink(missing_ok=True)
        return imagen.width, imagen.height, False


def descargar_imagen(sesion: requests.Session, url: str, destino: Path,
                     detectar_blancas: bool) -> tuple[int, int, bool]:
    respuesta = sesion.get(url, timeout=(12, 40))
    if respuesta.status_code in (403, 429):
        raise PermissionError(f"El servidor rechazo la imagen (HTTP {respuesta.status_code}).")
    respuesta.raise_for_status()
    tipo = respuesta.headers.get("Content-Type", "").lower()
    if "text/html" in tipo or "application/json" in tipo:
        raise ValueError("El enlace devolvio HTML/JSON en lugar de una imagen.")
    if len(respuesta.content) < 500:
        raise ValueError("Respuesta vacia o imagen inaccesible.")
    return preparar_jpeg(respuesta.content, destino, detectar_blancas)


def revisar_cache(ruta: Path, detectar_blancas: bool) -> tuple[int, int, bool] | None:
    if not ruta.is_file() or ruta.stat().st_size < 1000:
        return None
    try:
        with Image.open(ruta) as imagen:
            imagen.load()
            return imagen.width, imagen.height, detectar_blancas and es_imagen_blanca(imagen)
    except (OSError, ValueError):
        ruta.unlink(missing_ok=True)
        return None


def _fuentes(tamano: int, negrita: bool = False) -> ImageFont.ImageFont:
    nombres = (
        ("C:/Windows/Fonts/arialbd.ttf" if negrita else "C:/Windows/Fonts/arial.ttf"),
        ("DejaVuSans-Bold.ttf" if negrita else "DejaVuSans.ttf"),
    )
    for nombre in nombres:
        try:
            return ImageFont.truetype(nombre, tamano)
        except OSError:
            pass
    return ImageFont.load_default()


def crear_aviso(pid: str, destino: Path) -> None:
    hoja = Image.new("RGB", (1050, 1485), "white")
    dibujo = ImageDraw.Draw(hoja)
    dibujo.rounded_rectangle((65, 75, 985, 1410), radius=24, outline="#CBD5E1", width=4)
    dibujo.text((125, 225), f"Pagina {pid}", font=_fuentes(46, True), fill="#13233B")
    dibujo.text((125, 322), "No disponible en la vista previa", font=_fuentes(29), fill="#475569")
    dibujo.text((125, 391), "Se conserva su posicion en el PDF.", font=_fuentes(22), fill="#64748B")
    hoja.save(destino, "JPEG", quality=89)


def crear_blanco(destino: Path) -> None:
    Image.new("RGB", (1050, 1485), "white").save(destino, "JPEG", quality=85)


def crear_pdf(imagenes: list[Path], salida: Path) -> None:
    """Cada archivo de imagen se incrusta en una pagina, conservando su proporcion."""
    salida.parent.mkdir(parents=True, exist_ok=True)
    temporal = salida.with_suffix(".en_proceso.pdf")
    doc = canvas.Canvas(str(temporal), pageCompression=1)
    doc.setTitle("Paginas disponibles de Google Books")
    try:
        puntos_por_pixel = 72.0 / 150.0
        for imagen in imagenes:
            with Image.open(imagen) as lectura:
                ancho, alto = lectura.size
            ancho_pt, alto_pt = ancho * puntos_por_pixel, alto * puntos_por_pixel
            doc.setPageSize((ancho_pt, alto_pt))
            doc.drawImage(str(imagen), 0, 0, width=ancho_pt, height=alto_pt)
            doc.showPage()
        doc.save()
        temporal.replace(salida)
    finally:
        temporal.unlink(missing_ok=True)


def _esperar(pausa: float, cancelar: threading.Event) -> bool:
    """True cuando usuario cancelo durante la pausa."""
    return cancelar.wait(pausa) if pausa > 0 else cancelar.is_set()


def procesar(config: Configuracion, notificar: Notificador | None = None,
             cancelar: threading.Event | None = None,
             sesion: requests.Session | None = None) -> Resultado:
    """Motor independiente del GUI, reutilizable para consola y pruebas."""
    libro_id, base = config.validar()
    avisar: Notificador = notificar or (lambda tipo, dato: None)
    cancel = cancelar if cancelar is not None else threading.Event()
    carpeta_salida = config.carpeta_salida.expanduser().resolve()
    carpeta_salida.mkdir(parents=True, exist_ok=True)
    carpeta_imagenes = carpeta_salida / f"paginas_{libro_id}"
    carpeta_imagenes.mkdir(parents=True, exist_ok=True)
    cliente = sesion if sesion is not None else configurar_sesion(config.url)
    avisar("estado", "Consultando inventario del libro...")
    pids, cache_enlaces, info = leer_inventario(cliente, libro_id, base, config.url)
    tipo = elegir_prefijo(config.url, pids, config.prefijo)
    disponibles = sorted({int(m.group(2)) for pid in pids
                          if (m := PATRON_PAGINA.fullmatch(pid)) and m.group(1).upper() == tipo})
    if info.get("title"):
        avisar("log", f"Titulo: {info['title']}")
    avisar("log", f"Libro: {libro_id} | tipo detectado: {tipo} | paginas del inventario: {len(disponibles)}")

    if config.hasta is None:
        if not disponibles:
            raise ValueError(
                "Google Books no mostro un inventario de paginas. "
                f"Escribe un numero en 'Hasta' (por ejemplo {tipo}50) y vuelve a intentar."
            )
        ultimo = max(disponibles)
        hasta = min(ultimo, config.desde + config.max_paginas - 1)
        if hasta < ultimo:
            avisar("log", f"Aviso: se limita la ejecucion a {config.max_paginas} paginas; ultimo detectado {tipo}{ultimo}.")
    else:
        hasta = config.hasta

    if hasta < config.desde:
        raise ValueError(f"No se identificaron paginas a partir de {tipo}{config.desde}.")
    seleccion = [f"{tipo}{n}" for n in range(config.desde, hasta + 1)]
    total = len(seleccion)
    avisar("log", f"Intervalo secuencial: {tipo}{config.desde} a {tipo}{hasta} ({total} paginas).")
    avisar("log", f"Paginas sin imagen: {config.modo_faltantes}.")
    avisar("progreso", (0, total))

    archivos_pdf: list[Path] = []
    filas: list[list[str | int]] = []
    obtenidas = faltantes = procesadas = 0
    motivo_fin = "completado"
    # No se inventan enlaces. El lector debe exponerlos.
    for numero, pid in enumerate(seleccion, 1):
        if cancel.is_set():
            motivo_fin = "cancelado por el usuario"
            avisar("log", "Cancelacion solicitada: se guardaran los resultados parciales.")
            break
        procesadas += 1
        avisar("estado", f"Procesando {pid} ({numero}/{total})...")
        archivo = carpeta_imagenes / f"{pid}.jpg"
        detalle = ""
        problema = ""
        causa_bloqueo = False
        existe = revisar_cache(archivo, config.detectar_blancas)
        if existe and not existe[2]:
            ancho, alto, _ = existe
            archivos_pdf.append(archivo)
            obtenidas += 1
            filas.append([pid, "imagen", "reutilizada", f"{ancho}x{alto}", str(archivo), len(archivos_pdf)])
            avisar("log", f"{pid}: imagen guardada anteriormente ({ancho}x{alto}).")
        else:
            if existe and existe[2]:
                archivo.unlink(missing_ok=True)
                problema = "Imagen guardada detectada como blanca"
            if not config.solo_cache:
                if not cancel.is_set() and pid not in cache_enlaces:
                    try:
                        cache_enlaces.update(consultar_paginas(cliente, base, libro_id, pid))
                    except PermissionError as exc:
                        problema = str(exc)
                        causa_bloqueo = True
                    except (requests.RequestException, ValueError) as exc:
                        problema = f"Consulta fallida: {exc}"
                    if not causa_bloqueo and _esperar(config.pausa, cancel):
                        motivo_fin = "cancelado por el usuario"
                        procesadas -= 1
                        break
                enlace = cache_enlaces.get(pid)
                if enlace and not causa_bloqueo:
                    try:
                        ancho, alto, blanca = descargar_imagen(cliente, enlace, archivo, config.detectar_blancas)
                        if blanca:
                            problema = "La imagen publicada esta practicamente en blanco"
                        else:
                            archivos_pdf.append(archivo)
                            obtenidas += 1
                            filas.append([pid, "imagen", "descargada", f"{ancho}x{alto}", str(archivo), len(archivos_pdf)])
                            avisar("log", f"{pid}: OK, {ancho}x{alto}.")
                    except PermissionError as exc:
                        causa_bloqueo = True
                        problema = str(exc)
                    except (requests.RequestException, ValueError, OSError) as exc:
                        archivo.unlink(missing_ok=True)
                        problema = f"Imagen no disponible: {exc}"
                elif not causa_bloqueo and not problema:
                    problema = f"No hay imagen expuesta por el lector para {pid}"
            elif not problema:
                problema = "Sin imagen local (modo solo cache)"

            if not filas or filas[-1][0] != pid:
                faltantes += 1
                accion = config.modo_faltantes
                ruta_aviso = ""
                indice_pdf: str | int = ""
                if accion == "blanco":
                    destino = carpeta_imagenes / f"{pid}_BLANCO.jpg"
                    crear_blanco(destino)
                    archivos_pdf.append(destino)
                    ruta_aviso, indice_pdf = str(destino), len(archivos_pdf)
                elif accion == "aviso":
                    destino = carpeta_imagenes / f"{pid}_NO_DISPONIBLE.jpg"
                    crear_aviso(pid, destino)
                    archivos_pdf.append(destino)
                    ruta_aviso, indice_pdf = str(destino), len(archivos_pdf)
                filas.append([pid, "sin imagen", accion, problema, ruta_aviso, indice_pdf])
                avisar("log", f"{pid}: {problema} -> {accion}.")
                if causa_bloqueo:
                    motivo_fin = "acceso limitado por Google Books"
                elif accion == "detener":
                    motivo_fin = "detenido por pagina no disponible"
        avisar("progreso", (procesadas, total))
        if motivo_fin != "completado":
            break
        if _esperar(config.pausa, cancel):
            motivo_fin = "cancelado por el usuario"
            break

    # Las paginas posteriores a una parada/cancelacion tambien quedan en el CSV.
    for pid in seleccion[procesadas:]:
        filas.append([pid, "sin procesar", "ninguna", motivo_fin, "", ""])

    etiqueta = f"{tipo}{config.desde}_{tipo}{hasta}"
    pdf = (config.ruta_pdf or carpeta_salida / f"GoogleBooks_{libro_id}_{etiqueta}.pdf").resolve()
    csv_path = pdf.with_suffix(".csv")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fp:
        escritor = csv.writer(fp, delimiter=";")
        escritor.writerow(["pagina", "estado", "accion", "detalle", "archivo", "pagina_pdf"])
        escritor.writerows(filas)

    archivo_final: Path | None = None
    if archivos_pdf:
        avisar("estado", "Uniendo las imagenes en un PDF...")
        crear_pdf(archivos_pdf, pdf)
        archivo_final = pdf
        avisar("log", f"PDF generado: {pdf}")
    else:
        avisar("log", "No habia imagenes para el PDF. Se guardo el CSV de resultados.")
    avisar("log", f"Obtenidas: {obtenidas} | Vacantes: {faltantes} | Paginas PDF: {len(archivos_pdf)}")
    if motivo_fin != "completado":
        avisar("log", f"Proceso finalizado: {motivo_fin}.")
    return Resultado(libro_id, archivo_final, csv_path, carpeta_imagenes,
                     obtenidas, faltantes, procesadas, total, len(archivos_pdf), motivo_fin)


def argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Google Books a PDF: GUI por defecto, consola con argumentos."
    )
    parser.add_argument("--gui", action="store_true", help="Abrir la interfaz grafica.")
    parser.add_argument("--url", default=URL_INICIAL, help="Enlace del libro de Google Books.")
    parser.add_argument("--desde", default="1", help="Primera pagina, ej. 1, PT1 o PA1.")
    parser.add_argument("--hasta", default=None, help="Ultima pagina, ej. 80, PA80 o PT80; vacio = auto.")
    parser.add_argument("--tipo", default="AUTO", help="Prefijo AUTO, PA, PT, PR, PP, etc.")
    parser.add_argument("--faltantes", choices=MODOS_FALTANTES, default="omitir",
                        help="Omitir, blanco, aviso o detener. Por defecto omitir en CLI.")
    parser.add_argument("--marcar-faltantes", action="store_true", help="Equivalente a --faltantes aviso.")
    parser.add_argument("--sin-detectar-blancas", action="store_true", help="No detectar imagenes blancas.")
    parser.add_argument("--max-paginas", type=int, default=400)
    parser.add_argument("--espera", type=float, default=0.7, help="Pausa entre solicitudes (segundos).")
    parser.add_argument("--salida", default=None, help="Ruta final del PDF (opcional).")
    parser.add_argument("--carpeta", default=None, help="Carpeta de archivos.")
    parser.add_argument("--sin-descargar", action="store_true", help="Solo usar imagenes ya guardadas.")
    return parser.parse_args()


def ejecutar_consola(args: argparse.Namespace) -> int:
    tipo_manual = args.tipo.upper() if args.tipo.upper() != "AUTO" else None
    tipos_en_campos = {x for x in (prefijo_escrito(args.desde), prefijo_escrito(args.hasta or "")) if x}
    if len(tipos_en_campos) > 1:
        raise ValueError("Desde y Hasta tienen prefijos diferentes.")
    tipo_campos = next(iter(tipos_en_campos), None)
    if tipo_manual and tipo_campos and tipo_manual != tipo_campos:
        raise ValueError("El --tipo elegido no coincide con Desde o Hasta.")
    tipo_fijado = tipo_manual or tipo_campos
    primero = numero_pagina(args.desde, prefijo=tipo_fijado)
    ultimo = numero_pagina(args.hasta, obligatorio=False, prefijo=tipo_fijado) if args.hasta else None
    carpeta = Path(args.carpeta).expanduser() if args.carpeta else Path.cwd()
    ruta_pdf = Path(args.salida).expanduser() if args.salida else None
    if ruta_pdf and not args.carpeta:
        carpeta = ruta_pdf.parent
    cfg = Configuracion(
        url=args.url, desde=primero, hasta=ultimo, carpeta_salida=carpeta,
        modo_faltantes="aviso" if args.marcar_faltantes else args.faltantes,
        detectar_blancas=not args.sin_detectar_blancas,
        pausa=args.espera, max_paginas=args.max_paginas,
        solo_cache=args.sin_descargar, ruta_pdf=ruta_pdf,
        prefijo=tipo_fijado,
    )

    def salida(tipo: str, dato: Any) -> None:
        if tipo == "log":
            print(dato, flush=True)
        elif tipo == "estado":
            print(dato, flush=True)
    resultado = procesar(cfg, salida)
    print(f"\nCSV: {resultado.csv}")
    if resultado.pdf:
        print(f"PDF: {resultado.pdf}")
    return 0 if resultado.pdf and resultado.motivo_fin == "completado" else 1


def iniciar_gui() -> None:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, scrolledtext, ttk
    except ImportError as exc:
        raise SystemExit(f"Tkinter no esta disponible: {exc}. Reinstala Python con soporte Tcl/Tk.")

    FONDO = "#0B1324"
    TARJETA = "#14213A"
    TARJETA_BORDE = "#263855"
    TEXTO = "#EAF2FF"
    MUTED = "#A8BAD3"
    ACENTO = "#38D9CA"
    ENTRADA = "#F3F6FB"

    class Ventana(tk.Tk):
        def __init__(self):
            super().__init__()
            self.title("Organizador de Libros a PDF")
            self.geometry("1180x660")
            self.minsize(1000, 600)
            self.configure(bg=FONDO)
            self.cola: queue.Queue[tuple[str, Any]] = queue.Queue()
            self.cancelar = threading.Event()
            self.ocupado = False
            self.ultimo_directorio = Path.home() / "Downloads"
            if not self.ultimo_directorio.is_dir():
                self.ultimo_directorio = Path(__file__).resolve().parent

            self.enlace = tk.StringVar(value=URL_INICIAL)
            self.desde = tk.StringVar(value="1")
            self.prefijo = tk.StringVar(value="AUTO")
            self.tipo_detectado = tk.StringVar(value="Tipo detectado: PT")
            self.hasta = tk.StringVar(value="")
            self.modo = tk.StringVar(value="aviso")
            self.blancas = tk.BooleanVar(value=True)
            self.pausa = tk.StringVar(value="0.7")
            self.max_paginas = tk.StringVar(value="400")
            self.carpeta = tk.StringVar(value=str(self.ultimo_directorio))
            self.info = tk.StringVar(value="Pega un enlace de Google Books; PA, PT y otros tipos se detectan automaticamente.")
            self.estado = tk.StringVar(value="Listo para comenzar")
            self.contador = tk.StringVar(value="0 / 0")
            self._crear_estilos(ttk)
            self._construir(tk, ttk, scrolledtext)
            self.enlace.trace_add("write", self._cuando_cambie_enlace)
            self.prefijo.trace_add("write", self._cuando_cambie_enlace)
            self._cuando_cambie_enlace()
            self.after(100, self._procesar_cola)
            self.protocol("WM_DELETE_WINDOW", self._cerrar)

        def _crear_estilos(self, ttk):
            estilos = ttk.Style(self)
            estilos.theme_use("clam")
            estilos.configure("Color.Horizontal.TProgressbar", troughcolor="#263550", background=ACENTO,
                              bordercolor="#263550", lightcolor=ACENTO, darkcolor=ACENTO)
            estilos.configure("Claro.TCombobox", fieldbackground=ENTRADA, foreground="#122238",
                              background=ENTRADA, arrowcolor="#122238", padding=5)
            estilos.map("Claro.TCombobox", fieldbackground=[("readonly", ENTRADA)],
                        selectforeground=[("readonly", "#122238")],
                        selectbackground=[("readonly", ENTRADA)])
            estilos.configure("Claro.TCheckbutton", background=TARJETA, foreground=TEXTO,
                              font=("Segoe UI", 10))
            estilos.map("Claro.TCheckbutton", background=[("active", TARJETA)],
                        foreground=[("active", TEXTO)])

        def _etiqueta(self, padre, texto, *, color=MUTED, tam=10, negrita=False, **kwargs):
            if "textvariable" in kwargs:
                texto = ""
            return tk.Label(padre, text=texto, fg=color, bg=kwargs.pop("bg", TARJETA),
                            font=("Segoe UI", tam, "bold" if negrita else "normal"),
                            anchor="w", **kwargs)

        def _entrada(self, padre, variable, ancho=12):
            return tk.Entry(padre, textvariable=variable, width=ancho, bg=ENTRADA,
                            fg="#15243C", insertbackground="#15243C",
                            relief="flat", highlightthickness=1,
                            highlightbackground="#BECADD", highlightcolor=ACENTO,
                            font=("Segoe UI", 11), bd=5)

        def _boton(self, padre, texto, comando, *, principal=False, peligro=False):
            bg = ACENTO if principal else ("#AF3F58" if peligro else "#273B59")
            fg = "#09182B" if principal else "#F2F7FF"
            return tk.Button(padre, text=texto, command=comando, bg=bg, fg=fg,
                             activebackground="#72F3E3" if principal else "#385578",
                             activeforeground=fg, font=("Segoe UI", 10, "bold"),
                             relief="flat", padx=19, pady=9, cursor="hand2", bd=0)

        def _tarjeta(self, contenedor, **opciones):
            return tk.Frame(contenedor, bg=TARJETA, highlightbackground=TARJETA_BORDE,
                            highlightthickness=1, padx=18, pady=10, **opciones)

        def _construir(self, tk, ttk, scrolledtext):
            cab = tk.Frame(self, bg=FONDO, padx=24, pady=12)
            cab.pack(fill="x")
            self._etiqueta(cab, "ORGANIZADOR DE LIBROS A PDF", bg=FONDO, color=ACENTO,
                           tam=18, negrita=True).pack(anchor="w")
            self._etiqueta(cab, "Une paginas accesibles de Google Books, con prefijo PT, PA y otros.",
                           bg=FONDO, color=MUTED).pack(anchor="w", pady=(3, 0))

            contenedor = tk.Frame(self, bg=FONDO, padx=24)
            contenedor.pack(fill="both", expand=True)
            fila_superior = tk.Frame(contenedor, bg=FONDO)
            fila_superior.pack(fill="x", pady=(0, 7))
            tarjeta_enlace = self._tarjeta(fila_superior)
            tarjeta_enlace.pack(side="left", fill="both", expand=True, padx=(0, 5))
            self._etiqueta(tarjeta_enlace, "1. ENLACE DEL LIBRO", color=ACENTO,
                           tam=10, negrita=True).pack(anchor="w")
            self._entrada(tarjeta_enlace, self.enlace).pack(fill="x", pady=(6, 5))
            linea = tk.Frame(tarjeta_enlace, bg=TARJETA)
            linea.pack(fill="x")
            self.analizar_btn = self._boton(linea, "Analizar enlace", self._analizar)
            self.analizar_btn.pack(side="left")
            tk.Label(tarjeta_enlace, textvariable=self.info, bg=TARJETA, fg=MUTED,
                     font=("Segoe UI", 9), anchor="w", wraplength=800,
                     justify="left").pack(fill="x", pady=(5, 0))

            tarjeta_pag = self._tarjeta(fila_superior)
            tarjeta_pag.pack(side="left", fill="both", expand=True, padx=(5, 0))
            self._etiqueta(tarjeta_pag, "2. INTERVALO Y PAGINAS VACIAS", color=ACENTO,
                           tam=10, negrita=True).pack(anchor="w", pady=(0, 7))
            fila = tk.Frame(tarjeta_pag, bg=TARJETA)
            fila.pack(fill="x")
            col0 = tk.Frame(fila, bg=TARJETA)
            col0.pack(side="left", padx=(0, 12))
            self._etiqueta(col0, "Tipo").pack(anchor="w")
            ttk.Combobox(col0, textvariable=self.prefijo, values=PREFIJOS_GUI,
                         state="readonly", style="Claro.TCombobox", width=7).pack(anchor="w", pady=(4, 0))
            col1 = tk.Frame(fila, bg=TARJETA)
            col1.pack(side="left", padx=(0, 12))
            self._etiqueta(col1, "Desde").pack(anchor="w")
            self._entrada(col1, self.desde, 7).pack(anchor="w", pady=(4, 0))
            col2 = tk.Frame(fila, bg=TARJETA)
            col2.pack(side="left", padx=(0, 12))
            self._etiqueta(col2, "Hasta (auto)").pack(anchor="w")
            self._entrada(col2, self.hasta, 8).pack(anchor="w", pady=(4, 0))
            col3 = tk.Frame(fila, bg=TARJETA)
            col3.pack(side="left", fill="x", expand=True)
            self._etiqueta(col3, "Si una pagina esta vacia o no disponible").pack(anchor="w")
            opciones = (
                "Incluir hoja con aviso",
                "Omitir pagina",
                "Incluir hoja en blanco",
                "Detener al encontrarla",
            )
            self.opciones_map = dict(zip(opciones, ("aviso", "omitir", "blanco", "detener")))
            self.opcion_inversa = {v: k for k, v in self.opciones_map.items()}
            self.etiqueta_opcion = tk.StringVar(value="Incluir hoja con aviso")
            self.combo = ttk.Combobox(col3, textvariable=self.etiqueta_opcion, values=opciones,
                                      state="readonly", style="Claro.TCombobox", width=29)
            self.combo.pack(fill="x", pady=(4, 0))
            self._etiqueta(tarjeta_pag, "", color=ACENTO, tam=9,
                           textvariable=self.tipo_detectado).pack(anchor="w", pady=(8, 0))
            tk.Checkbutton(
                tarjeta_pag, text="Detectar tambien imagenes realmente blancas como paginas vacias",
                variable=self.blancas, bg=TARJETA, fg=TEXTO,
                activebackground=TARJETA, activeforeground=TEXTO,
                selectcolor="#203756", font=("Segoe UI", 10),
            ).pack(anchor="w", pady=(8, 0))

            fila_inferior = tk.Frame(contenedor, bg=FONDO)
            fila_inferior.pack(fill="x", pady=(0, 7))
            tarjeta_dest = self._tarjeta(fila_inferior)
            tarjeta_dest.pack(side="left", fill="both", expand=True, padx=(0, 6))
            self._etiqueta(tarjeta_dest, "3. DESTINO Y AJUSTES", color=ACENTO,
                           tam=10, negrita=True).pack(anchor="w", pady=(0, 6))
            fila_dest = tk.Frame(tarjeta_dest, bg=TARJETA)
            fila_dest.pack(fill="x")
            self._entrada(fila_dest, self.carpeta).pack(side="left", fill="x", expand=True)
            self._boton(fila_dest, "Elegir carpeta", self._buscar_carpeta).pack(side="left", padx=(10, 0))
            avanzado = tk.Frame(tarjeta_dest, bg=TARJETA)
            avanzado.pack(fill="x", pady=(6, 0))
            self._etiqueta(avanzado, "Pausa entre consultas (segundos)").pack(side="left")
            self._entrada(avanzado, self.pausa, 6).pack(side="left", padx=(9, 24))
            self._etiqueta(avanzado, "Max. paginas por ejecucion").pack(side="left")
            self._entrada(avanzado, self.max_paginas, 7).pack(side="left", padx=(9, 0))

            acciones = tk.Frame(fila_inferior, bg=FONDO)
            acciones.pack(side="right", fill="y", padx=(4, 0))
            self.generar_btn = self._boton(acciones, "CREAR PDF", self._iniciar, principal=True)
            self.generar_btn.pack(side="top", fill="x", pady=(0, 4))
            self.cancelar_btn = self._boton(acciones, "Cancelar", self._cancelar, peligro=True)
            self.cancelar_btn.pack(side="top", fill="x", pady=(0, 4))
            self.cancelar_btn.config(state="disabled")
            self.abrir_btn = self._boton(acciones, "Abrir carpeta", self._abrir_carpeta)
            self.abrir_btn.pack(side="top", fill="x")

            tarjeta_log = self._tarjeta(contenedor)
            tarjeta_log.pack(fill="both", expand=True, pady=(0, 9))
            encabezado = tk.Frame(tarjeta_log, bg=TARJETA)
            encabezado.pack(fill="x", pady=(0, 7))
            self._etiqueta(encabezado, "PROGRESO Y REGISTRO", color=ACENTO,
                           tam=10, negrita=True).pack(side="left")
            self._etiqueta(encabezado, "", color=MUTED).pack(side="left")
            tk.Label(encabezado, textvariable=self.contador, fg=MUTED, bg=TARJETA,
                     font=("Segoe UI", 10, "bold")).pack(side="right")
            self.barra = ttk.Progressbar(tarjeta_log, style="Color.Horizontal.TProgressbar",
                                        mode="determinate", maximum=100)
            self.barra.pack(fill="x", pady=(0, 8))
            tk.Label(tarjeta_log, textvariable=self.estado, fg=TEXTO, bg=TARJETA,
                     anchor="w", font=("Segoe UI", 9)).pack(fill="x", pady=(0, 6))
            self.registro = scrolledtext.ScrolledText(
                tarjeta_log, height=5, bg="#091426", fg="#BFD6ED",
                insertbackground=TEXTO, relief="flat", wrap="word", bd=8,
                font=("Consolas", 9), state="disabled",
            )
            self.registro.pack(fill="both", expand=True)
            self._registrar("Listo. Tipo AUTO reconoce PA, PT y mas. Desde = 1, Hasta vacio = automatico.")

        def _registrar(self, mensaje):
            self.registro.configure(state="normal")
            self.registro.insert("end", str(mensaje) + "\n")
            self.registro.see("end")
            self.registro.configure(state="disabled")

        def _cuando_cambie_enlace(self, *_):
            tipo = elegir_prefijo(self.enlace.get(), [], self.prefijo.get())
            self.tipo_detectado.set(f"Tipo efectivo: {tipo} · Ejemplo: {tipo}1, {tipo}2, {tipo}3...")

        def _tipo_campos(self) -> str | None:
            t1, t2 = prefijo_escrito(self.desde.get()), prefijo_escrito(self.hasta.get())
            if t1 and t2 and t1 != t2:
                raise ValueError("Desde y Hasta deben usar el mismo tipo de pagina.")
            manual = self.prefijo.get().upper()
            if manual != "AUTO" and (t1 or t2) and manual != (t1 or t2):
                raise ValueError("Los campos no coinciden con el tipo seleccionado.")
            return manual if manual != "AUTO" else (t1 or t2)

        def _configuracion(self):
            valor = self.pausa.get().strip().replace(",", ".")
            try:
                pausa = float(valor)
                limite = int(self.max_paginas.get().strip())
            except ValueError as exc:
                raise ValueError("La pausa y el maximo de paginas deben ser numeros.") from exc
            carpeta = self.carpeta.get().strip()
            if not carpeta:
                raise ValueError("Selecciona una carpeta de destino.")
            tipo_fijado = self._tipo_campos()
            cfg = Configuracion(
                url=normalizar_url(self.enlace.get()),
                desde=numero_pagina(self.desde.get(), prefijo=tipo_fijado),
                hasta=numero_pagina(self.hasta.get(), obligatorio=False, prefijo=tipo_fijado),
                prefijo=tipo_fijado,
                carpeta_salida=Path(carpeta),
                modo_faltantes=self.opciones_map[self.etiqueta_opcion.get()],
                detectar_blancas=self.blancas.get(), pausa=pausa, max_paginas=limite,
            )
            cfg.validar()
            return cfg

        def _buscar_carpeta(self):
            carpeta = filedialog.askdirectory(parent=self, title="Guardar PDF en",
                                               initialdir=self.carpeta.get())
            if carpeta:
                self.carpeta.set(carpeta)

        def _abrir_carpeta(self):
            directorio = Path(self.carpeta.get()).expanduser()
            if not directorio.is_dir():
                messagebox.showinfo("Carpeta", "Todavia no existe la carpeta seleccionada.", parent=self)
                return
            try:
                if sys.platform == "win32":
                    os.startfile(str(directorio))  # type: ignore[attr-defined]
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(directorio)])
                else:
                    subprocess.Popen(["xdg-open", str(directorio)])
            except OSError as exc:
                messagebox.showerror("No se pudo abrir", str(exc), parent=self)

        def _poner_ocupado(self, valor):
            self.ocupado = valor
            self.analizar_btn.config(state="disabled" if valor else "normal")
            self.generar_btn.config(state="disabled" if valor else "normal")
            self.cancelar_btn.config(state="normal" if valor else "disabled")

        def _trabajo(self, funcion):
            self.cancelar.clear()
            self._poner_ocupado(True)
            threading.Thread(target=funcion, daemon=True).start()

        def _analizar(self):
            try:
                url = normalizar_url(self.enlace.get())
                libro_id, base = extraer_volumen(url)
                tipo_fijado = self._tipo_campos()
            except ValueError as exc:
                messagebox.showerror("Enlace incorrecto", str(exc), parent=self)
                return
            self.estado.set("Analizando enlace sin descargar imagenes...")
            self._registrar("Consultando el inventario de " + libro_id + "...")

            def tarea():
                try:
                    sesion = configurar_sesion(url)
                    pids, links, info = leer_inventario(sesion, libro_id, base, url)
                    tipo = elegir_prefijo(url, pids, tipo_fijado)
                    paginas = sorted({int(m.group(2)) for pid in pids
                                     if (m := PATRON_PAGINA.fullmatch(pid)) and m.group(1).upper() == tipo})
                    if self.cancelar.is_set():
                        self.cola.put(("cancelado_analisis", None))
                    else:
                        self.cola.put(("analizado", (libro_id, tipo, paginas, info, len(links))))
                except Exception as exc:
                    self.cola.put(("error", str(exc)))

            self._trabajo(tarea)

        def _iniciar(self):
            try:
                config = self._configuracion()
            except (ValueError, OSError) as exc:
                messagebox.showerror("Comprueba los datos", str(exc), parent=self)
                return
            self.barra["value"] = 0
            self.contador.set("0 / 0")
            self.estado.set("Iniciando...")
            self._registrar("=" * 45)
            self._registrar("Iniciando conversion desde " +
                            elegir_prefijo(config.url, [], config.prefijo) + str(config.desde) + "...")

            def tarea():
                try:
                    resultado = procesar(
                        config, notificar=lambda tipo, dato: self.cola.put((tipo, dato)),
                        cancelar=self.cancelar,
                    )
                    self.cola.put(("finalizado", resultado))
                except Exception as exc:
                    self.cola.put(("error", str(exc)))

            self._trabajo(tarea)

        def _cancelar(self):
            self.cancelar.set()
            self.estado.set("Cancelando... (puede concluir la solicitud en curso)")
            self.cancelar_btn.config(state="disabled")

        def _procesar_cola(self):
            try:
                while True:
                    tipo, dato = self.cola.get_nowait()
                    if tipo == "log":
                        self._registrar(dato)
                    elif tipo == "estado":
                        self.estado.set(str(dato))
                    elif tipo == "progreso":
                        actuales, total = dato
                        self.contador.set(f"{actuales} / {total}")
                        self.barra["value"] = 100 * actuales / max(1, total)
                    elif tipo == "analizado":
                        libro, tipo, paginas, info, enlaces = dato
                        self.tipo_detectado.set(f"Tipo detectado: {tipo} · rango desde {tipo}1")
                        titulo = info.get("title", "Sin titulo publico")
                        if paginas:
                            self.info.set(
                                f"{titulo} | {len(paginas)} {tipo} identificadas | "
                                f"intervalo: {tipo}{min(paginas)} a {tipo}{max(paginas)}"
                            )
                            # Si Hasta estaba vacio, queda automatico; el usuario puede escribir otro.
                            self._registrar(
                                f"Inventario: {len(paginas)} {tipo}; ultima {tipo}{max(paginas)}. "
                                f"Enlaces visibles en HTML: {enlaces}."
                            )
                        else:
                            self.info.set(f"Tipo {tipo} identificado por enlace; sin inventario. Indica Hasta.")
                            self._registrar(f"Sin inventario {tipo} visible: indica manualmente 'Hasta'.")
                        self.estado.set("Enlace analizado")
                        self._poner_ocupado(False)
                    elif tipo == "cancelado_analisis":
                        self._poner_ocupado(False)
                        self.estado.set("Analisis cancelado")
                    elif tipo == "error":
                        self._poner_ocupado(False)
                        self.estado.set("Error; revisa el registro")
                        self._registrar("ERROR: " + dato)
                        messagebox.showerror("No se pudo completar", str(dato), parent=self)
                    elif tipo == "finalizado":
                        self._poner_ocupado(False)
                        self.estado.set("Finalizado: " + dato.motivo_fin)
                        self._registrar("Registro CSV: " + str(dato.csv))
                        texto = (
                            f"Estado: {dato.motivo_fin}\n\n"
                            f"Imagenes: {dato.obtenidas}\n"
                            f"Paginas vacias/no disponibles: {dato.faltantes}\n"
                            f"Paginas en PDF: {dato.paginas_pdf}\n\n"
                            f"PDF: {dato.pdf if dato.pdf else 'No creado (sin paginas)'}\n"
                            f"Registro CSV: {dato.csv}"
                        )
                        messagebox.showinfo("Resultado de la conversion", texto, parent=self)
            except queue.Empty:
                pass
            self.after(100, self._procesar_cola)

        def _cerrar(self):
            if self.ocupado and not messagebox.askyesno(
                "Salir", "Hay un proceso en curso. Si sales puede quedar incompleto. ¿Salir?",
                parent=self,
            ):
                return
            self.cancelar.set()
            self.destroy()

    app = Ventana()
    app.mainloop()


def main() -> int:
    if len(sys.argv) == 1 or sys.argv[1:] == ["--gui"]:
        iniciar_gui()
        return 0
    args = argumentos()
    if args.gui:
        iniciar_gui()
        return 0
    return ejecutar_consola(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelado por el usuario.")
        raise SystemExit(130)
    except (ValueError, PermissionError, requests.RequestException, OSError) as error:
        print("ERROR:", error)
        raise SystemExit(1)