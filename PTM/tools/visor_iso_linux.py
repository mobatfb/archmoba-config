# ARGUMENTOS: iso linux visor editor initrd efiboot img vmlinuz bios boot modificar eliminar reemplazar guardar copia
import os
import sys
import io
import gzip
import bz2
import lzma
import shutil
import stat
import struct
import subprocess
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox, simpledialog

TOOL_NAME = "Visor ISO Linux"
TOOL_DESCRIPTION = (
    "Explora ISOs Linux, permite modificar/eliminar/reemplazar archivos en una copia de trabajo, "
    "abre imagenes FAT como EFIBOOT.IMG y archivos INITRD CPIO, permite ver, editar y guardar archivos TXT/HEX en ISO, FAT e INITRD, y genera una copia ISO modificada."
)
TOOL_VERSION = "1.1.4"


def human_size(n):
    n = int(n or 0)
    units = ["B", "KB", "MB", "GB", "TB"]
    v = float(n)
    for u in units:
        if v < 1024 or u == units[-1]:
            return f"{v:.0f} {u}" if u == "B" else f"{v:.1f} {u}"
        v /= 1024


def search_terms(text):
    """Búsqueda por ruta o nombre, sin distinguir mayúsculas."""
    return tuple(word.casefold() for word in text.strip().split() if word)


def matches_search(path, terms):
    name = str(path).casefold()
    return all(word in name for word in terms)


def which(name):
    return shutil.which(name)


def run_cmd(args, cwd=None):
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True,
        creationflags=flags
    )


def detect_compression(data):
    if data.startswith(b"\x1f\x8b"):
        return "gzip"
    if data.startswith(b"\xfd7zXZ\x00"):
        return "xz"
    if data.startswith(b"BZh"):
        return "bz2"
    if data.startswith(b"\x28\xb5\x2f\xfd"):
        return "zstd"
    if data.startswith(b"\x04\x22\x4d\x18"):
        return "lz4"
    if data.startswith(b"\x02\x21\x4c\x18"):
        return "lz4-legacy"
    if data.startswith(b"\x89LZO\x00\x0d\x0a\x1a\x0a"):
        return "lzop"
    return "none"


def decompress_bytes(data):
    kind = detect_compression(data)
    if kind == "gzip":
        return gzip.decompress(data), kind
    if kind == "xz":
        return lzma.decompress(data), kind
    if kind == "bz2":
        return bz2.decompress(data), kind
    if kind == "zstd":
        try:
            import zstandard as zstd
        except Exception as exc:
            raise RuntimeError("INITRD usa Zstandard. Instala: python -m pip install zstandard") from exc
        # Los INITRD suelen omitir el tamaño descomprimido en la cabecera.
        with zstd.ZstdDecompressor().stream_reader(io.BytesIO(data)) as reader:
            return reader.read(), kind
    if kind == "lz4":
        try:
            import lz4.frame
        except ImportError as exc:
            raise RuntimeError(
                "INITRD usa LZ4. Falta la dependencia 'lz4' de PTM."
            ) from exc
        return lz4.frame.decompress(data), kind
    if kind in ("lz4-legacy", "lzop"):
        raise ValueError(
            f"INITRD comprimido en {kind}: este formato aún no es "
            "compatible con el editor. El archivo original no se ha modificado."
        )
    return data, kind


def compress_bytes(data, kind):
    if kind == "gzip":
        return gzip.compress(data, compresslevel=9)
    if kind == "xz":
        return lzma.compress(data, format=lzma.FORMAT_XZ)
    if kind == "bz2":
        return bz2.compress(data, compresslevel=9)
    if kind == "zstd":
        try:
            import zstandard as zstd
        except Exception as exc:
            raise RuntimeError("Falta zstandard. Instala: python -m pip install zstandard") from exc
        return zstd.ZstdCompressor(level=10).compress(data)
    if kind == "lz4":
        try:
            import lz4.frame
        except ImportError as exc:
            raise RuntimeError("Falta la dependencia 'lz4' de PTM.") from exc
        return lz4.frame.compress(data)
    return data


def _pad4(n):
    return (4 - (n % 4)) % 4


def parse_cpio_newc(data, return_end=False):
    """Lee CPIO newc/crc y, opcionalmente, devuelve la posición del trailer."""
    pos = 0
    entries = []
    total = len(data)
    while pos + 110 <= total:
        magic = data[pos:pos + 6]
        if magic not in (b"070701", b"070702"):
            raise ValueError(
                "El contenido no es un archivo CPIO newc válido "
                f"(offset 0x{pos:X})."
            )
        hdr = data[pos:pos + 110]
        pos += 110
        try:
            vals = [int(hdr[6 + i * 8:14 + i * 8], 16) for i in range(13)]
        except ValueError as exc:
            raise ValueError("Cabecera CPIO dañada.") from exc
        (ino, mode, uid, gid, nlink, mtime, filesize,
         devmaj, devmin, rdevmaj, rdevmin, namesize, check) = vals
        if namesize < 1 or pos + namesize > total:
            raise ValueError("CPIO truncado en nombre")
        name_raw = data[pos:pos + namesize]
        name = name_raw.rstrip(b"\x00").decode("utf-8", "replace")
        pos += namesize
        pos += _pad4(110 + namesize)
        if pos + filesize > total:
            raise ValueError("CPIO truncado en datos")
        payload = data[pos:pos + filesize]
        pos += filesize
        pos += _pad4(filesize)
        if name == "TRAILER!!!":
            return (entries, pos) if return_end else entries
        entries.append({
            "name": name, "ino": ino, "mode": mode, "uid": uid, "gid": gid,
            "nlink": nlink, "mtime": mtime, "data": payload,
            "devmaj": devmaj, "devmin": devmin, "rdevmaj": rdevmaj,
            "rdevmin": rdevmin, "check": check,
        })
    raise ValueError("CPIO incompleto: no se encontró TRAILER!!!")


def load_initrd_payload(raw):
    """Desempaqueta INITRD y conserva CPIO iniciales (microcódigo) intactos.

    Algunos initrd.img incluyen un CPIO sin comprimir seguido de otro CPIO
    comprimido. El prefijo se conserva exactamente al volver a guardar.
    Nunca se descartan datos concatenados que no sepamos interpretar.
    """
    prefix = b""
    offset = 0
    while raw[offset:offset + 6] in (b"070701", b"070702"):
        entries, used = parse_cpio_newc(raw[offset:], return_end=True)
        next_pos = offset + used
        while next_pos < len(raw) and raw[next_pos] == 0:
            next_pos += 1
        if next_pos == len(raw):
            return entries, "none", prefix
        prefix = raw[:next_pos]
        offset = next_pos

    payload = raw[offset:]
    kind = detect_compression(payload)
    if kind == "none":
        raise ValueError(
            "No se reconoció un INITRD CPIO o comprimido compatible. "
            f"Cabecera: {payload[:12].hex(' ').upper()}. "
            "El archivo original no se ha modificado."
        )
    unpacked, kind = decompress_bytes(payload)
    entries, used = parse_cpio_newc(unpacked, return_end=True)
    if unpacked[used:].strip(b"\x00"):
        raise ValueError(
            "El INITRD contiene varios archivos CPIO concatenados dentro "
            "de la compresión. Para evitar pérdida de datos no se editará."
        )
    return entries, kind, prefix


def detect_container_type(path):
    """Identifica INITRD por nombre o contenido antes de comprobar FAT."""
    name = path.name.lower()
    if "initrd" in name or "initramfs" in name or ".cpio" in name:
        return "initrd"
    with path.open("rb") as stream:
        head = stream.read(512)
    if head[:6] in (b"070701", b"070702"):
        return "initrd"
    if detect_compression(head) != "none":
        return "initrd"
    if len(head) >= 512:
        # Un .img no es necesariamente FAT: comprobar salto de arranque,
        # firma del sector, tamaño de sector y número de tablas FAT.
        jump = head[0] in (0xEB, 0xE9)
        boot_sig = head[510:512] == b"\x55\xaa"
        sector_size = int.from_bytes(head[11:13], "little")
        fats = head[16]
        if jump and boot_sig and sector_size in (512, 1024, 2048, 4096) and fats in (1, 2):
            return "fat"
    return "unknown"

def build_cpio_newc(entries):
    out = bytearray()
    ino_fallback = 1
    for e in entries:
        name_b = e["name"].encode("utf-8") + b"\x00"
        payload = e.get("data", b"")
        ino = int(e.get("ino", ino_fallback)); ino_fallback += 1
        fields = [
            ino, int(e.get("mode", stat.S_IFREG | 0o644)), int(e.get("uid", 0)), int(e.get("gid", 0)),
            int(e.get("nlink", 1)), int(e.get("mtime", 0)), len(payload),
            int(e.get("devmaj", 0)), int(e.get("devmin", 0)), int(e.get("rdevmaj", 0)),
            int(e.get("rdevmin", 0)), len(name_b), int(e.get("check", 0)),
        ]
        hdr = b"070701" + b"".join(f"{v & 0xffffffff:08x}".encode("ascii") for v in fields)
        out.extend(hdr)
        out.extend(name_b)
        out.extend(b"\x00" * _pad4(len(hdr) + len(name_b)))
        out.extend(payload)
        out.extend(b"\x00" * _pad4(len(payload)))

    trailer = {"name": "TRAILER!!!", "mode": 0, "nlink": 1, "data": b""}
    name_b = trailer["name"].encode() + b"\x00"
    fields = [0,0,0,0,1,0,0,0,0,0,0,len(name_b),0]
    hdr = b"070701" + b"".join(f"{v:08x}".encode("ascii") for v in fields)
    out.extend(hdr); out.extend(name_b)
    out.extend(b"\x00" * _pad4(len(hdr) + len(name_b)))
    out.extend(b"\x00" * _pad4(len(out)))
    return bytes(out)



def read_file_chunk(path, offset, count):
    """Lectura paginada: no carga archivos grandes completos en memoria."""
    with Path(path).open("rb") as stream:
        stream.seek(offset)
        return stream.read(count)


class FileAsTextViewer(ttk.Frame):
    """Visor/editor TXT y HEX integrado para ISO, FAT e INITRD."""

    TEXT_PAGE = 128 * 1024
    HEX_PAGE = 32 * 1024
    MAX_TEXT_EDIT = 4 * 1024 * 1024
    MAX_HEX_EDIT = 256 * 1024

    def __init__(self, parent, name, total_size, reader, save_callback=None):
        super().__init__(parent, padding=8)
        self.parent_editor = parent
        self.name = str(name)
        self.total_size = max(0, int(total_size))
        self.reader = reader
        self.save_callback = save_callback
        self.offset = 0
        self.last_count = 0
        self.editing = False
        self.dirty = False
        self._original_data = None
        self._edit_encoding = "utf-8"
        self._newline = "\n"
        self.mode_var = tk.StringVar(value="TXT")
        self.encoding_var = tk.StringVar(value="Automático")
        self.page_var = tk.StringVar(value="")
        self.info_var = tk.StringVar(value="")
        self._build()
        self.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.lift()
        self._render()

    def _build(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 5))
        ttk.Button(bar, text="Volver", command=self.close).pack(
            side="left", padx=(0, 8),
        )
        self.edit_button = ttk.Button(
            bar, text="Editar", command=self.toggle_edit,
        )
        self.edit_button.pack(side="left", padx=(0, 5))
        self.save_button = ttk.Button(
            bar, text="Guardar (Ctrl+S)", command=self.save_changes,
            state="disabled",
        )
        self.save_button.pack(side="left", padx=(0, 12))
        ttk.Label(bar, text="Ver como:").pack(side="left", padx=(0, 4))
        self.mode_box = ttk.Combobox(
            bar, textvariable=self.mode_var, values=("TXT", "HEX"),
            state="readonly", width=6,
        )
        self.mode_box.pack(side="left", padx=(0, 12))
        self.mode_box.bind("<<ComboboxSelected>>", self._change_format)
        ttk.Label(bar, text="Codificación:").pack(side="left", padx=(0, 4))
        self.encoding_box = ttk.Combobox(
            bar, textvariable=self.encoding_var,
            values=("Automático", "UTF-8", "Latin-1", "UTF-16 LE", "UTF-16 BE"),
            state="readonly", width=13,
        )
        self.encoding_box.pack(side="left", padx=(0, 8))
        self.encoding_box.bind(
            "<<ComboboxSelected>>", lambda _event: self._render(),
        )
        if self.save_callback is None:
            self.edit_button.configure(state="disabled")

        ttk.Label(
            self, text=self.name, anchor="w", wraplength=950,
        ).pack(fill="x", pady=(0, 5))
        content = ttk.Frame(self)
        content.pack(fill="both", expand=True)
        self.text = tk.Text(
            content, wrap="none", font=("DejaVu Sans Mono", 9),
            undo=True, state="disabled",
        )
        vscroll = ttk.Scrollbar(content, orient="vertical", command=self.text.yview)
        hscroll = ttk.Scrollbar(content, orient="horizontal", command=self.text.xview)
        self.text.configure(
            yscrollcommand=vscroll.set, xscrollcommand=hscroll.set,
        )
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)
        self.text.grid(row=0, column=0, sticky="nsew")
        vscroll.grid(row=0, column=1, sticky="ns")
        hscroll.grid(row=1, column=0, sticky="ew")
        self.text.bind("<<Modified>>", self._on_modified)
        self.text.bind("<Control-s>", self._shortcut_save)
        self.text.bind("<Control-S>", self._shortcut_save)
        self.text.bind("<Escape>", lambda _event: self.close())

        footer = ttk.Frame(self)
        footer.pack(fill="x", pady=(6, 0))
        self.prev_button = ttk.Button(
            footer, text="◀ Anterior", command=self.previous_page,
        )
        self.prev_button.pack(side="left", padx=(0, 6))
        self.next_button = ttk.Button(
            footer, text="Siguiente ▶", command=self.next_page,
        )
        self.next_button.pack(side="left")
        ttk.Label(footer, textvariable=self.page_var).pack(side="left", padx=12)
        ttk.Label(footer, textvariable=self.info_var).pack(side="right")
        self.text.focus_set()

    def _change_format(self, _event=None):
        if self.editing:
            return
        self.offset = 0
        self._render()

    def _page_size(self):
        return self.HEX_PAGE if self.mode_var.get() == "HEX" else self.TEXT_PAGE

    def _encoding_for(self, data):
        selected = self.encoding_var.get()
        encodings = {
            "UTF-8": "utf-8",
            "Latin-1": "latin-1",
            "UTF-16 LE": "utf-16-le",
            "UTF-16 BE": "utf-16-be",
        }
        if selected == "Automático":
            if data.startswith((b"\xff\xfe", b"\xfe\xff")):
                return "utf-16"
            if data.startswith(b"\xef\xbb\xbf"):
                return "utf-8-sig"
            try:
                data.decode("utf-8")
                return "utf-8"
            except UnicodeDecodeError:
                return "latin-1"
        if selected == "UTF-8" and data.startswith(b"\xef\xbb\xbf"):
            return "utf-8-sig"
        if selected in ("UTF-16 LE", "UTF-16 BE"):
            if data.startswith((b"\xff\xfe", b"\xfe\xff")):
                return "utf-16"
        return encodings[selected]

    def _decode_text(self, data):
        encoding = self._encoding_for(data)
        text = data.decode(encoding, errors="replace")
        text = text.replace("\x00", "␀")
        return "".join(
            ch if ch in "\n\r\t" or ord(ch) >= 32 else "·"
            for ch in text
        )

    def _hex_text(self, data):
        lines = []
        for index in range(0, len(data), 16):
            chunk = data[index:index + 16]
            hx = " ".join(f"{byte:02X}" for byte in chunk)
            printable = "".join(
                chr(byte) if 32 <= byte < 127 else "."
                for byte in chunk
            )
            lines.append(
                f"{self.offset + index:08X}  {hx:<47}  {printable}"
            )
        return "\n".join(lines)

    def _render(self):
        if self.editing:
            return
        try:
            data = self.reader(self.offset, self._page_size())
            if not isinstance(data, bytes):
                data = bytes(data)
            self.last_count = len(data)
            content = (
                self._hex_text(data)
                if self.mode_var.get() == "HEX"
                else self._decode_text(data)
            )
            if not data:
                content = "(Archivo vacío)" if self.total_size == 0 else "(Sin datos)"
            self.text.configure(state="normal")
            self.text.delete("1.0", "end")
            self.text.insert("1.0", content)
            self.text.configure(state="disabled")
            self.text.edit_modified(False)
            self.text.yview_moveto(0)
            self.text.xview_moveto(0)
            end = self.offset + self.last_count
            self.page_var.set(
                f"Bytes {self.offset:,}–{end:,} de {self.total_size:,} "
                f"({human_size(self.total_size)})"
            )
            self.prev_button.configure(
                state="normal" if self.offset > 0 else "disabled",
            )
            self.next_button.configure(
                state="normal"
                if self.last_count and end < self.total_size
                else "disabled",
            )
            self.info_var.set("Vista previa · pulsa Editar para modificar")
        except Exception as exc:
            messagebox.showerror(
                "Visor TXT/HEX", f"No se pudo leer el archivo:\n{exc}",
                parent=self,
            )

    def _on_modified(self, _event=None):
        if not self.text.edit_modified():
            return
        self.text.edit_modified(False)
        if self.editing:
            self.dirty = True
            self.save_button.configure(state="normal")
            self.info_var.set("Cambios sin guardar")

    def _shortcut_save(self, _event=None):
        self.save_changes()
        return "break"

    def toggle_edit(self):
        if self.editing:
            self.cancel_edit()
        else:
            self.begin_edit()

    def begin_edit(self):
        if self.save_callback is None:
            return
        mode = self.mode_var.get()
        limit = self.MAX_HEX_EDIT if mode == "HEX" else self.MAX_TEXT_EDIT
        if self.total_size > limit:
            messagebox.showinfo(
                "Editar archivo",
                f"Para proteger la memoria, la edición {mode} admite "
                f"hasta {human_size(limit)}.\n"
                "Este archivo puede seguir visualizándose por páginas.",
                parent=self,
            )
            return
        try:
            data = self.reader(0, self.total_size)
            if not isinstance(data, bytes):
                data = bytes(data)
            if len(data) != self.total_size:
                raise IOError("No se pudo leer el archivo completo.")
            if mode == "HEX":
                content = "\n".join(
                    " ".join(f"{byte:02X}" for byte in data[i:i + 16])
                    for i in range(0, len(data), 16)
                )
            else:
                self._edit_encoding = self._encoding_for(data)
                decoded = data.decode(self._edit_encoding, errors="strict")
                if "\x00" in decoded:
                    raise ValueError(
                        "El archivo contiene bytes nulos. "
                        "Para editar archivos binarios usa el modo HEX."
                    )
                controls = sum(
                    1 for ch in decoded
                    if ord(ch) < 32 and ch not in "\r\n\t"
                )
                if controls > max(2, len(decoded) // 100):
                    raise ValueError(
                        "Se detectó contenido binario. Usa el modo HEX "
                        "para evitar dañar el archivo."
                    )
                self._newline = (
                    "\r\n" if "\r\n" in decoded
                    else "\r" if "\r" in decoded else "\n"
                )
                content = decoded.replace("\r\n", "\n").replace("\r", "\n")
        except Exception as exc:
            messagebox.showwarning("Editar archivo", str(exc), parent=self)
            return

        self._original_data = data
        self.editing = True
        self.dirty = False
        self.offset = 0
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self.text.edit_reset()
        self.text.edit_modified(False)
        self.text.focus_set()
        self.edit_button.configure(text="Cancelar edición")
        self.save_button.configure(state="disabled")
        self.mode_box.configure(state="disabled")
        self.encoding_box.configure(state="disabled")
        self.prev_button.configure(state="disabled")
        self.next_button.configure(state="disabled")
        self.page_var.set(f"Editando archivo completo · {human_size(len(data))}")
        self.info_var.set(
            "Edición HEX: bytes hexadecimales separados por espacios"
            if mode == "HEX" else "Edición TXT · Ctrl+S para guardar"
        )

    def save_changes(self):
        if not self.editing or self.save_callback is None:
            return False
        try:
            content = self.text.get("1.0", "end-1c")
            if self.mode_var.get() == "HEX":
                data = bytes.fromhex(content)
            else:
                if self._newline != "\n":
                    content = content.replace("\n", self._newline)
                data = content.encode(self._edit_encoding, errors="strict")
            if data != self._original_data:
                self.save_callback(data)
            self.total_size = len(data)
            self._original_data = None
            self._finish_edit()
            self.info_var.set("Cambios guardados en la copia de trabajo")
            return True
        except ValueError as exc:
            messagebox.showerror(
                "Guardar archivo",
                f"Contenido inválido: {exc}\n"
                "En modo HEX utiliza solo pares 00–FF separados por espacios.",
                parent=self,
            )
        except Exception as exc:
            messagebox.showerror(
                "Guardar archivo",
                f"No se pudo guardar el archivo:\n{exc}",
                parent=self,
            )
        return False

    def _finish_edit(self):
        self.editing = False
        self.dirty = False
        self.offset = 0
        self.edit_button.configure(text="Editar")
        self.save_button.configure(state="disabled")
        self.mode_box.configure(state="readonly")
        self.encoding_box.configure(state="readonly")
        self._render()

    def cancel_edit(self):
        if self.dirty and not messagebox.askyesno(
            "Descartar cambios",
            "Hay cambios sin guardar. ¿Descartarlos?",
            parent=self,
        ):
            return
        self._original_data = None
        self._finish_edit()

    def previous_page(self):
        if self.editing:
            return
        self.offset = max(0, self.offset - self._page_size())
        self._render()

    def next_page(self):
        if self.editing:
            return
        if self.last_count:
            self.offset += self.last_count
            self._render()

    def close(self):
        if self.editing and self.dirty:
            answer = messagebox.askyesnocancel(
                "Cambios sin guardar",
                "¿Guardar los cambios antes de volver?",
                parent=self,
            )
            if answer is None:
                return
            if answer and not self.save_changes():
                return
        self.destroy()
        if getattr(self.parent_editor, "_text_file_viewer", None) is self:
            self.parent_editor._text_file_viewer = None
        if hasattr(self.parent_editor, "tree"):
            try:
                self.parent_editor.tree.focus_set()
            except tk.TclError:
                pass


def show_file_as_text(parent, name, total_size, reader, save_callback=None):
    """Editor embebido: persiste cambios mediante callback del contenedor."""
    previous = getattr(parent, "_text_file_viewer", None)
    if previous is not None and previous.winfo_exists():
        # Evitar descartar accidentalmente cambios al abrir otro archivo.
        if previous.editing and previous.dirty:
            answer = messagebox.askyesnocancel(
                "Cambios sin guardar",
                "¿Guardar los cambios antes de abrir otro archivo?",
                parent=previous,
            )
            if answer is None:
                return previous
            if answer and not previous.save_changes():
                return previous
        previous.destroy()
    viewer = FileAsTextViewer(
        parent, name, total_size, reader, save_callback=save_callback,
    )
    parent._text_file_viewer = viewer
    return viewer


class InitrdEditor(ttk.Frame):
    def __init__(self, owner, path, parent=None):
        super().__init__(parent if parent is not None else owner)
        self.owner = owner
        self.path = Path(path)
        self.entries = []
        self.compression = "none"
        self.prefix = b""
        self.search_var = tk.StringVar(value="")
        self.search_info = tk.StringVar(value="")
        self._search_job = None
        self._build()
        self._load()

    def _build(self):
        bar = ttk.Frame(self, padding=8); bar.pack(fill="x")
        ttk.Button(bar, text="Volver", command=self.owner._close_container_editor).pack(side="left", padx=(0, 12))
        ttk.Button(bar, text="Reemplazar", command=self.replace).pack(side="left", padx=3)
        ttk.Button(bar, text="Eliminar", command=self.delete).pack(side="left", padx=3)
        ttk.Button(bar, text="Extraer", command=self.extract).pack(side="left", padx=3)
        ttk.Button(bar, text="Ver como TXT", command=self.view_selected).pack(side="left", padx=3)
        ttk.Button(bar, text="Guardar INITRD", command=self.save).pack(side="left", padx=12)
        self.info = ttk.Label(bar, text=""); self.info.pack(side="right")

        search_bar = ttk.Frame(self, padding=(8, 0, 8, 6))
        search_bar.pack(fill="x")
        ttk.Label(search_bar, text="Buscar en INITRD:").pack(side="left", padx=(0, 8))
        search_entry = ttk.Entry(search_bar, textvariable=self.search_var)
        search_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(
            search_bar, text="X", width=3,
            command=lambda: self.search_var.set("")
        ).pack(side="left", padx=(5, 8))
        ttk.Label(search_bar, textvariable=self.search_info).pack(side="left")
        search_entry.bind("<Escape>", lambda _event: self.search_var.set(""))
        self.search_var.trace_add("write", self._schedule_search)

        self.tree = ttk.Treeview(self, columns=("name","size","mode"), show="headings")
        self.tree.heading("name", text="Ruta")
        self.tree.heading("size", text="Tamano")
        self.tree.heading("mode", text="Modo")
        self.tree.column("name", width=620)
        self.tree.column("size", width=110, anchor="e")
        self.tree.column("mode", width=110, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=8, pady=(0,8))
        self.tree.bind("<Double-Button-1>", lambda _event: self.view_selected())

    def view_selected(self):
        index = self.selected_index()
        if index is None:
            return
        entry = self.entries[index]
        if stat.S_ISDIR(entry.get("mode", 0)):
            return
        data = entry.get("data", b"")
        def save_entry(updated):
            previous = entry.get("data", b"")
            entry["data"] = updated
            try:
                self.save(silent=True)
                self.refresh()
            except Exception:
                entry["data"] = previous
                raise

        show_file_as_text(
            self, entry["name"], len(data),
            lambda offset, count: entry.get("data", b"")[offset:offset + count],
            save_callback=save_entry,
        )

    def _load(self):
        raw = self.path.read_bytes()
        self.entries, self.compression, self.prefix = load_initrd_payload(raw)
        self.refresh()
        extra = " | microcódigo preservado" if self.prefix else ""
        self.info.config(
            text=f"{len(self.entries)} entradas | {self.compression}{extra}"
        )

    def _schedule_search(self, *_args):
        if self._search_job is not None:
            self.after_cancel(self._search_job)
        self._search_job = self.after(160, self._apply_search)

    def _apply_search(self):
        self._search_job = None
        self.refresh()

    def refresh(self):
        old_selection = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        terms = search_terms(self.search_var.get())
        found = 0
        for i, entry in enumerate(self.entries):
            if not matches_search(entry["name"], terms):
                continue
            found += 1
            self.tree.insert(
                "", "end", iid=str(i),
                values=(
                    entry["name"],
                    human_size(len(entry.get("data", b""))),
                    oct(entry.get("mode", 0)),
                ),
            )
        if old_selection and self.tree.exists(old_selection[0]):
            self.tree.selection_set(old_selection[0])
        self.search_info.set(f"{found} de {len(self.entries)} entradas")

    def selected_index(self):
        s = self.tree.selection()
        return int(s[0]) if s else None

    def replace(self):
        i = self.selected_index()
        if i is None: return
        src = filedialog.askopenfilename(parent=self, title="Archivo de reemplazo")
        if not src: return
        e = self.entries[i]
        if stat.S_ISDIR(e.get("mode",0)):
            messagebox.showwarning("INITRD", "La entrada seleccionada es un directorio", parent=self); return
        e["data"] = Path(src).read_bytes()
        e["mode"] = (e.get("mode",0) & ~stat.S_IFMT(e.get("mode",0))) | stat.S_IFREG
        self.refresh()

    def delete(self):
        i = self.selected_index()
        if i is None: return
        name = self.entries[i]["name"]
        if not messagebox.askyesno("Eliminar", f"Eliminar {name}?", parent=self): return
        prefix = name.rstrip("/") + "/"
        self.entries = [e for j,e in enumerate(self.entries) if j != i and not e["name"].startswith(prefix)]
        self.refresh()

    def extract(self):
        i = self.selected_index()
        if i is None: return
        e = self.entries[i]
        if stat.S_ISDIR(e.get("mode",0)):
            messagebox.showinfo("INITRD", "Seleccione un archivo", parent=self); return
        dst = filedialog.asksaveasfilename(parent=self, initialfile=Path(e["name"]).name)
        if dst:
            Path(dst).write_bytes(e.get("data",b""))

    def save(self, silent=False):
        temporary = None
        try:
            raw = build_cpio_newc(self.entries)
            # Preservar exactamente las capas CPIO iniciales no editadas.
            updated = self.prefix + compress_bytes(raw, self.compression)
            with tempfile.NamedTemporaryFile(
                dir=self.path.parent, prefix=".ptm_initrd_",
                suffix=".tmp", delete=False,
            ) as output:
                temporary = Path(output.name)
                output.write(updated)
            os.replace(temporary, self.path)
            temporary = None
            self.owner.refresh_tree()
            if not silent:
                messagebox.showinfo(
                    "INITRD", "Cambios guardados en la copia de trabajo.",
                    parent=self,
                )
            return True
        except Exception as exc:
            if silent:
                raise
            messagebox.showerror("INITRD", str(exc), parent=self)
            return False
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass


class FatEditor(ttk.Frame):
    def __init__(self, owner, img_path, parent=None):
        super().__init__(parent if parent is not None else owner)
        self.owner = owner
        self.img_path = Path(img_path)
        self.fs = None
        self.current = "/"
        self.search_var = tk.StringVar(value="")
        self.search_info = tk.StringVar(value="")
        self._search_job = None
        self._search_index = None
        self._result_paths = {}
        self._build()
        self._open_fs()

    def _build(self):
        bar = ttk.Frame(self, padding=8); bar.pack(fill="x")
        ttk.Button(bar, text="Volver al ISO", command=self.owner._close_container_editor).pack(side="left", padx=(0, 12))
        ttk.Button(bar, text="Subir", command=self.up).pack(side="left", padx=3)
        ttk.Button(bar, text="Reemplazar", command=self.replace).pack(side="left", padx=3)
        ttk.Button(bar, text="Eliminar", command=self.delete).pack(side="left", padx=3)
        ttk.Button(bar, text="Extraer", command=self.extract).pack(side="left", padx=3)
        ttk.Button(bar, text="Ver como TXT", command=self.view_selected).pack(side="left", padx=3)
        ttk.Button(bar, text="Explorar IMG", command=self.open_nested_selected).pack(side="left", padx=3)
        self.path_var = tk.StringVar(value="/")
        ttk.Label(bar, textvariable=self.path_var).pack(side="left", padx=12)
        search_bar = ttk.Frame(self, padding=(8, 0, 8, 6))
        search_bar.pack(fill="x")
        ttk.Label(search_bar, text="Buscar en FAT:").pack(side="left", padx=(0, 8))
        search_entry = ttk.Entry(search_bar, textvariable=self.search_var)
        search_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(
            search_bar, text="X", width=3,
            command=lambda: self.search_var.set("")
        ).pack(side="left", padx=(5, 8))
        ttk.Label(search_bar, textvariable=self.search_info).pack(side="left")
        search_entry.bind("<Escape>", lambda _event: self.search_var.set(""))
        self.search_var.trace_add("write", self._schedule_search)
        self.tree = ttk.Treeview(self, columns=("name","type","size"), show="headings")
        for c,t,w in (("name","Nombre",560),("type","Tipo",120),("size","Tamano",120)):
            self.tree.heading(c,text=t); self.tree.column(c,width=w)
        self.tree.pack(fill="both", expand=True, padx=8, pady=(0,8))
        self.tree.bind("<Double-Button-1>", self.open_selected)
        self.error_var = tk.StringVar(value="")
        ttk.Label(
            self, textvariable=self.error_var, foreground="#B42318",
            wraplength=680, padding=(8, 5),
        ).pack(fill="x")
        ttk.Button(
            self, text="Reintentar apertura FAT", command=self._open_fs,
        ).pack(anchor="e", padx=8, pady=(0, 4))

    def _open_fs(self):
        self.error_var.set("")
        try:
            from pyfatfs.PyFatFS import PyFatFS
        except Exception as exc:
            self.error_var.set(
                "No se pudo cargar pyfatfs: "
                f"{type(exc).__name__}: {exc}. "
                "Vuelve a abrir el Visor ISO Linux desde PTM para "
                "que se reparen sus dependencias automáticamente."
            )
            return
        try:
            if self.fs is not None:
                self.fs.close()
            self.fs = PyFatFS(str(self.img_path), read_only=False)
            self._search_index = None
            self.refresh()
        except Exception as exc:
            self.fs = None
            self.error_var.set(
                f"No se pudo abrir la imagen FAT: "
                f"{type(exc).__name__}: {exc}"
            )

    def destroy(self):
        try:
            if self.fs: self.fs.close()
        except Exception: pass
        super().destroy()

    def _join(self, name):
        return (self.current.rstrip("/") + "/" + name).replace("//","/")

    def _schedule_search(self, *_args):
        if self._search_job is not None:
            self.after_cancel(self._search_job)
        self._search_job = self.after(160, self._apply_search)

    def _apply_search(self):
        self._search_job = None
        self.refresh()

    def _scan_paths(self):
        """Indexa una vez todas las carpetas FAT para buscar en subcarpetas."""
        result = []
        stack = ["/"]
        visited = {"/"}
        while stack:
            folder = stack.pop()
            for name in self.fs.listdir(folder):
                path = (folder.rstrip("/") + "/" + name).replace("//", "/")
                if path in visited:
                    continue
                visited.add(path)
                try:
                    is_dir = self.fs.isdir(path)
                except Exception:
                    continue
                result.append((path, is_dir))
                if is_dir:
                    stack.append(path)
        return result

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        self._result_paths.clear()
        if self.fs is None:
            return
        try:
            terms = search_terms(self.search_var.get())
            if terms:
                if self._search_index is None:
                    self._search_index = self._scan_paths()
                items = [
                    (path, is_dir, path)
                    for path, is_dir in self._search_index
                    if matches_search(path, terms)
                ]
                self.path_var.set("Resultados en toda la imagen FAT")
            else:
                items = [
                    (self._join(name), self.fs.isdir(self._join(name)), name)
                    for name in sorted(
                        self.fs.listdir(self.current), key=str.casefold
                    )
                ]
                self.path_var.set(self.current)
            for path, is_dir, label in items:
                try:
                    info = self.fs.getinfo(path, namespaces=["details"])
                    size = "" if is_dir else human_size(info.size)
                except Exception:
                    size = ""
                iid = self.tree.insert(
                    "", "end",
                    values=(label, "Carpeta" if is_dir else "Archivo", size),
                )
                self._result_paths[iid] = path
            self.search_info.set(f"{len(items)} coincidencias" if terms else "")
        except Exception as exc:
            messagebox.showerror("FAT", str(exc), parent=self)

    def selected(self):
        selected = self.tree.selection()
        return self._result_paths.get(selected[0]) if selected else None

    def open_selected(self, _e=None):
        path = self.selected()
        if not path or self.fs is None:
            return
        if self.fs.isdir(path):
            self.current = path
            self.search_var.set("")
            self.refresh()
        else:
            if not self.open_nested_selected(silent=True):
                self.view_selected()

    def open_nested_selected(self, silent=False):
        path = self.selected()
        if not path or self.fs is None or self.fs.isdir(path):
            return False
        name = path.lower()
        if not (name.endswith((".img", ".cpio", ".gz", ".xz", ".lz4"))
                or "initrd" in name or "initramfs" in name):
            return False
        try:
            return self.owner._open_nested_fat_file(self.fs, path)
        except Exception as exc:
            if not silent:
                messagebox.showerror("Contenedor anidado", str(exc), parent=self)
            return False

    def view_selected(self):
        path = self.selected()
        if not path or self.fs is None:
            return
        try:
            if self.fs.isdir(path):
                return
            try:
                size = self.fs.getinfo(path, namespaces=["details"]).size
            except Exception:
                with self.fs.openbin(path, "r") as stream:
                    stream.seek(0, 2)
                    size = stream.tell()

            def read_chunk(offset, count):
                with self.fs.openbin(path, "r") as stream:
                    stream.seek(offset)
                    return stream.read(count)

            def save_chunk(data):
                with self.fs.openbin(path, "r") as stream:
                    original = stream.read()
                try:
                    with self.fs.openbin(path, "w") as stream:
                        stream.write(data)
                except Exception:
                    # Intentar recuperar el contenido anterior ante fallo de escritura.
                    try:
                        with self.fs.openbin(path, "w") as stream:
                            stream.write(original)
                    except Exception:
                        pass
                    raise
                self._search_index = None
                self.refresh()
                self.owner.refresh_tree()

            show_file_as_text(
                self, path, size, read_chunk, save_callback=save_chunk,
            )
        except Exception as exc:
            messagebox.showerror("Ver como TXT", str(exc), parent=self)

    def up(self):
        if self.current == "/":
            if self.search_var.get():
                self.search_var.set("")
            return
        self.current = str(Path(self.current).parent).replace("\\", "/")
        if not self.current.startswith("/"):
            self.current = "/" + self.current
        self.search_var.set("")
        self.refresh()

    def replace(self):
        p = self.selected()
        if not p or self.fs.isdir(p): return
        src = filedialog.askopenfilename(parent=self)
        if not src: return
        try:
            with self.fs.openbin(p, "w") as f:
                f.write(Path(src).read_bytes())
            self._search_index = None
            self.refresh(); self.owner.refresh_tree()
        except Exception as exc:
            messagebox.showerror("FAT", str(exc), parent=self)

    def delete(self):
        p = self.selected()
        if not p: return
        if not messagebox.askyesno("Eliminar", f"Eliminar {p}?", parent=self): return
        try:
            if self.fs.isdir(p): self.fs.removetree(p)
            else: self.fs.remove(p)
            self._search_index = None
            self.refresh(); self.owner.refresh_tree()
        except Exception as exc:
            messagebox.showerror("FAT", str(exc), parent=self)

    def extract(self):
        p = self.selected()
        if not p or self.fs.isdir(p): return
        dst = filedialog.asksaveasfilename(parent=self, initialfile=Path(p).name)
        if not dst: return
        try:
            with self.fs.openbin(p, "r") as f:
                Path(dst).write_bytes(f.read())
        except Exception as exc:
            messagebox.showerror("FAT", str(exc), parent=self)


class ISOEditor(ttk.Frame):
    def __init__(self, parent, app=None):
        super().__init__(parent)
        self.app = app
        self.iso_path = None
        self.work_dir = None
        self.temp_dir = None
        self.status_var = tk.StringVar(value="Abra un ISO para comenzar")
        self._paths = {}
        self._expandable_containers = {}
        self._container_host = None
        self._nested_stack = []
        self._nested_files = []
        self.search_var = tk.StringVar(value="")
        self.search_info = tk.StringVar(value="")
        self._search_job = None
        self._search_index = None
        self._build_ui()

    def _build_ui(self):
        self.pack(fill="both", expand=True)
        top = ttk.Frame(self, padding=8); top.pack(fill="x")
        # Versión EN LÍNEA, inmediatamente antes de Abrir ISO.
        # Usar tk.Label con colores propios evita que un tema ttk oscuro
        # o de Linux vuelva el texto ilegible o lo confunda con el fondo.
        self.version_label = tk.Label(
            top,
            text=f"v{TOOL_VERSION}",
            bg="#075D79",
            fg="#FFFFFF",
            font=("DejaVu Sans", 9, "bold"),
            padx=10,
            pady=4,
            bd=0,
            relief="flat",
        )
        self.version_label.pack(side="left", padx=(3, 8), pady=2)
        ttk.Button(top, text="Abrir ISO", command=self.open_iso).pack(side="left", padx=3)
        ttk.Button(top, text="Reemplazar", command=self.replace_selected).pack(side="left", padx=3)
        ttk.Button(top, text="Eliminar", command=self.delete_selected).pack(side="left", padx=3)
        ttk.Button(top, text="Extraer", command=self.extract_selected).pack(side="left", padx=3)
        ttk.Button(top, text="Ver como TXT", command=self.view_selected).pack(side="left", padx=3)
        ttk.Button(top, text="Abrir contenedor", command=self.open_container).pack(side="left", padx=3)
        ttk.Button(top, text="Guardar copia ISO", command=self.save_iso_copy).pack(side="left", padx=14)

        search_bar = ttk.Frame(self, padding=(8, 0, 8, 6))
        search_bar.pack(fill="x")
        ttk.Label(search_bar, text="Buscar en ISO:").pack(side="left", padx=(0, 8))
        search_entry = ttk.Entry(search_bar, textvariable=self.search_var)
        search_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(
            search_bar, text="X", width=3,
            command=lambda: self.search_var.set("")
        ).pack(side="left", padx=(5, 8))
        ttk.Label(search_bar, textvariable=self.search_info).pack(side="left")
        search_entry.bind("<Escape>", lambda _event: self.search_var.set(""))
        self.search_var.trace_add("write", self._schedule_search)

        mid = ttk.Panedwindow(self, orient="horizontal"); mid.pack(fill="both", expand=True, padx=8)
        left = ttk.Frame(mid); right = ttk.Frame(mid); mid.add(left, weight=3); mid.add(right, weight=2)

        self.tree = ttk.Treeview(left, columns=("name","type","size"), show="tree headings")
        self.tree.heading("#0", text="Ruta")
        self.tree.heading("name", text="Nombre")
        self.tree.heading("type", text="Tipo")
        self.tree.heading("size", text="Tamano")
        self.tree.column("#0", width=280)
        self.tree.column("name", width=220)
        self.tree.column("type", width=100)
        self.tree.column("size", width=100, anchor="e")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self.preview())
        self.tree.bind("<<TreeviewOpen>>", self._expand_container_node, add="+")
        self.tree.bind("<Double-Button-1>", lambda _e: self.open_container())

        ttk.Label(right, text="Vista previa / informacion").pack(anchor="w", pady=(0,4))
        self.preview_text = tk.Text(right, wrap="none", font=("Consolas", 9))
        self.preview_text.pack(fill="both", expand=True)

        ttk.Label(self, textvariable=self.status_var, anchor="w", padding=(8,5)).pack(fill="x")

    def set_status(self, text):
        self.status_var.set(text)
        self.update_idletasks()

    def _close_container_editor(self):
        host = self._container_host
        if self._nested_stack:
            previous = self._nested_stack.pop()
            if host is not None:
                host.destroy()
            self._container_host = previous
            previous.place(relx=0, rely=0, relwidth=1, relheight=1)
            previous.lift()
            if self._nested_files:
                tmp = self._nested_files.pop()
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
            self.set_status("Regresaste al contenedor anterior.")
            return
        self._container_host = None
        if host is not None:
            host.destroy()
            if self.work_dir is not None and self.work_dir.exists():
                self.refresh_tree()

    def _open_nested_fat_file(self, fs, path):
        """Extrae un IMG interno a una copia temporal y lo explora sin modificar el original."""
        from tempfile import NamedTemporaryFile
        name = Path(path).name.lower()
        limit = 512 * 1024 * 1024
        temp_path = None
        try:
            with NamedTemporaryFile(prefix="ptm_nested_", suffix=Path(name).suffix or ".img",
                                    delete=False) as out:
                temp_path = Path(out.name)
                count = 0
                with fs.openbin(path, "r") as inp:
                    while True:
                        chunk = inp.read(1024 * 1024)
                        if not chunk:
                            break
                        count += len(chunk)
                        if count > limit:
                            raise RuntimeError("La imagen anidada supera 512 MB.")
                        out.write(chunk)
            kind = detect_container_type(temp_path)
            if kind not in ("fat", "initrd"):
                return False
            previous = self._container_host
            if previous is None:
                raise RuntimeError("No hay contenedor principal abierto.")
            previous.place_forget()
            host = ttk.Frame(self)
            host.place(relx=0, rely=0, relwidth=1, relheight=1)
            host.lift()
            self._container_host = host
            self._nested_stack.append(previous)
            self._nested_files.append(temp_path)
            try:
                editor = FatEditor(self, temp_path, parent=host) if kind == "fat" else InitrdEditor(self, temp_path, parent=host)
                editor.pack(fill="both", expand=True)
            except Exception:
                self._close_container_editor()
                raise
            self.set_status(f"Explorando {Path(path).name} dentro del contenedor ({kind.upper()}); copia temporal.")
            return True
        finally:
            if temp_path is not None and temp_path not in self._nested_files:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def _open_container_editor(self, editor_type, path):
        self._close_container_editor()
        host = ttk.Frame(self)
        host.place(relx=0, rely=0, relwidth=1, relheight=1)
        host.lift()
        self._container_host = host
        try:
            editor = editor_type(self, path, parent=host)
            editor.pack(fill="both", expand=True)
        except Exception:
            self._close_container_editor()
            raise

    def cleanup(self):
        while self._nested_stack:
            self._close_container_editor()
        self._close_container_editor()
        self._search_index = None
        if self.temp_dir:
            try: shutil.rmtree(self.temp_dir, ignore_errors=True)
            except Exception: pass
            self.temp_dir = None

    def open_iso(self):
        path = filedialog.askopenfilename(title="Abrir ISO Linux", filetypes=[("ISO", "*.iso"), ("Todos", "*.*")])
        if not path: return
        self.load_iso(Path(path))

    def load_iso(self, path):
        self.cleanup()
        self.iso_path = Path(path)
        self.temp_dir = Path(tempfile.mkdtemp(prefix="ptm_iso_"))
        self.work_dir = self.temp_dir / "work"
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.set_status("Extrayendo ISO a una copia de trabajo...")

        def worker():
            try:
                self._extract_iso(self.iso_path, self.work_dir)
                self.after(0, self._after_open)
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("ISO", str(exc), parent=self))
                self.after(0, lambda: self.set_status("Error al abrir ISO"))
        threading.Thread(target=worker, daemon=True).start()

    def _extract_iso(self, iso, dest):
        if which("xorriso"):
            r = run_cmd(["xorriso", "-osirrox", "on", "-indev", str(iso), "-extract", "/", str(dest)])
            if r.returncode == 0:
                return
        z = which("7z") or which("7zz")
        if z:
            r = run_cmd([z, "x", "-y", f"-o{dest}", str(iso)])
            if r.returncode == 0:
                return
        try:
            import pycdlib
        except Exception as exc:
            raise RuntimeError(
                "No pude extraer el ISO. Instala pycdlib (python -m pip install pycdlib) "
                "o instala xorriso/7-Zip."
            ) from exc
        isoobj = pycdlib.PyCdlib(); isoobj.open(str(iso))
        try:
            self._extract_pycdlib_tree(isoobj, dest)
        finally:
            isoobj.close()

    def _extract_pycdlib_tree(self, isoobj, dest):
        modes = [("rr_path", "/"), ("joliet_path", "/"), ("iso_path", "/")]
        last = None
        for key, root in modes:
            try:
                walker = isoobj.walk(**{key: root})
                any_item = False
                for dirpath, dirnames, filenames in walker:
                    any_item = True
                    rel = str(dirpath).lstrip("/").replace(";1", "")
                    target_dir = dest / rel
                    target_dir.mkdir(parents=True, exist_ok=True)
                    for fn in filenames:
                        clean = str(fn).replace(";1", "")
                        out = target_dir / clean
                        srcp = (str(dirpath).rstrip("/") + "/" + str(fn)).replace("//","/")
                        kwargs = {key: srcp}
                        with open(out, "wb") as f:
                            isoobj.get_file_from_iso_fp(f, **kwargs)
                if any_item: return
            except Exception as exc:
                last = exc
        raise RuntimeError(f"No se pudo recorrer el ISO: {last}")

    def _after_open(self):
        self._search_index = None
        self.refresh_tree()
        self.set_status(f"Copia de trabajo lista: {self.iso_path.name}")

    def _schedule_search(self, *_args):
        if self._search_job is not None:
            self.after_cancel(self._search_job)
        self._search_job = self.after(160, self._apply_search)

    def _apply_search(self):
        self._search_job = None
        self.refresh_tree()

    def refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        self._paths.clear()
        self._expandable_containers.clear()
        if not self.work_dir or not self.work_dir.exists():
            self.search_info.set("")
            return
        root_id = self.tree.insert(
            "", "end", text="/",
            values=(self.iso_path.name if self.iso_path else "ISO", "ISO", ""),
            open=True,
        )
        self._paths[root_id] = self.work_dir
        terms = search_terms(self.search_var.get())
        if terms:
            if self._search_index is None:
                self._search_index = list(self.work_dir.rglob("*"))
            found = 0
            for path in self._search_index:
                relative = path.relative_to(self.work_dir).as_posix()
                if not matches_search(relative, terms) or not path.exists():
                    continue
                found += 1
                is_dir = path.is_dir()
                typ = "Carpeta" if is_dir else path.suffix.upper().lstrip(".") or "Archivo"
                size = "" if is_dir else human_size(path.stat().st_size)
                iid = self.tree.insert(
                    root_id, "end", text=relative,
                    values=(path.name, typ, size),
                )
                self._paths[iid] = path
                self._mark_container_node(iid, path)
            self.search_info.set(f"{found} coincidencias")
            return

        self.search_info.set("")
        def add(parent_id, folder):
            try:
                items = sorted(
                    folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold())
                )
            except Exception:
                return
            for path in items:
                is_dir = path.is_dir()
                typ = "Carpeta" if is_dir else path.suffix.upper().lstrip(".") or "Archivo"
                size = "" if is_dir else human_size(path.stat().st_size)
                iid = self.tree.insert(
                    parent_id, "end", text=path.name,
                    values=(path.name, typ, size),
                )
                self._paths[iid] = path
                if not is_dir:
                    self._mark_container_node(iid, path)
                if is_dir:
                    add(iid, path)
        add(root_id, self.work_dir)

    def selected_path(self):
        s = self.tree.selection()
        return self._paths.get(s[0]) if s else None

    def preview(self):
        p = self.selected_path()
        self.preview_text.delete("1.0", "end")
        if not p: return
        try:
            if p.is_dir():
                self.preview_text.insert("end", f"Carpeta\n{p}\n")
                return
            data = p.read_bytes()[:65536]
            self.preview_text.insert("end", f"Archivo: {p.name}\nTamano: {human_size(p.stat().st_size)}\nRuta de trabajo: {p}\n\n")
            ext = p.suffix.lower()
            if ext in (".txt",".cfg",".conf",".ini",".lst",".sh",".json",".xml",".md"):
                self.preview_text.insert("end", data.decode("utf-8", "replace"))
            else:
                for off in range(0, min(len(data), 4096), 16):
                    chunk = data[off:off+16]
                    hx = " ".join(f"{b:02X}" for b in chunk)
                    asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
                    self.preview_text.insert("end", f"{off:08X}  {hx:<47}  {asc}\n")
        except Exception as exc:
            self.preview_text.insert("end", str(exc))

    def view_selected(self):
        p = self.selected_path()
        if not p or p.is_dir():
            return
        try:
            def save_chunk(data):
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(
                        dir=p.parent, prefix=".ptm_edit_",
                        suffix=".tmp", delete=False,
                    ) as output:
                        temporary = Path(output.name)
                        output.write(data)
                    shutil.copymode(p, temporary)
                    os.replace(temporary, p)
                    temporary = None
                finally:
                    if temporary is not None:
                        try:
                            temporary.unlink(missing_ok=True)
                        except OSError:
                            pass
                self._search_index = None
                self.refresh_tree()
                self.set_status(
                    f"Archivo guardado en la copia de trabajo: {p.name}. "
                    "Usa Guardar copia ISO para generar el ISO final."
                )

            show_file_as_text(
                self, p.name, p.stat().st_size,
                lambda offset, count: read_file_chunk(p, offset, count),
                save_callback=save_chunk,
            )
        except Exception as exc:
            messagebox.showerror("Ver como TXT", str(exc), parent=self)

    def replace_selected(self):
        p = self.selected_path()
        if not p or p.is_dir(): return
        src = filedialog.askopenfilename(title=f"Reemplazar {p.name}")
        if not src: return
        try:
            shutil.copy2(src, p)
            self._search_index = None
            self.refresh_tree(); self.set_status(f"Reemplazado: {p.name}")
        except Exception as exc:
            messagebox.showerror("Reemplazar", str(exc), parent=self)

    def delete_selected(self):
        p = self.selected_path()
        if not p or p == self.work_dir: return
        if not messagebox.askyesno("Eliminar", f"Eliminar de la copia de trabajo?\n\n{p.name}", parent=self): return
        try:
            if p.is_dir(): shutil.rmtree(p)
            else: p.unlink()
            self._search_index = None
            self.refresh_tree(); self.set_status(f"Eliminado: {p.name}")
        except Exception as exc:
            messagebox.showerror("Eliminar", str(exc), parent=self)

    def extract_selected(self):
        p = self.selected_path()
        if not p: return
        if p.is_dir():
            dst = filedialog.askdirectory(title="Destino")
            if dst:
                shutil.copytree(p, Path(dst)/p.name, dirs_exist_ok=True)
        else:
            dst = filedialog.asksaveasfilename(initialfile=p.name)
            if dst: shutil.copy2(p, dst)

    def _mark_container_node(self, item_id, path):
        """Agrega el desplegable + solo para imagenes con contenido reconocido."""
        name = path.name.lower()
        if not (
            name.endswith((".img", ".cpio", ".cpio.gz", ".cpio.xz",
                           ".initrd", ".initramfs", ".gz", ".xz", ".lz4"))
            or "initrd" in name or "initramfs" in name
        ):
            return
        try:
            kind = detect_container_type(path)
        except (OSError, ValueError):
            return
        if kind not in ("fat", "initrd"):
            return
        self._expandable_containers[item_id] = kind
        # Un hijo marcador activa el control + nativo del Treeview.
        self.tree.insert(item_id, "end", text="Contenido del contenedor",
                         values=("Abrir " + kind.upper(), "Contenedor", ""))

    def _expand_container_node(self, _event=None):
        """El + abre el editor FAT/INITRD en el mismo visor ISO."""
        item = self.tree.focus()
        if item not in self._expandable_containers:
            return
        path = self._paths.get(item)
        if path is None:
            return
        self.tree.selection_set(item)
        # Dejar el signo + disponible al regresar al arbol ISO.
        self.after_idle(lambda: self._launch_expanded_container(item, path))

    def _launch_expanded_container(self, item, path):
        if not self.tree.exists(item):
            return
        self.tree.item(item, open=False)
        self.open_container()

    def open_container(self):
        p = self.selected_path()
        if not p or p.is_dir(): return
        n = p.name.lower()
        try:
            kind = detect_container_type(p)
            if kind == "initrd":
                self._open_container_editor(InitrdEditor, p)
            elif kind == "fat":
                self._open_container_editor(FatEditor, p)
            elif p.suffix.lower() == ".img":
                messagebox.showwarning(
                    "IMG no compatible",
                    f"{p.name} no contiene un sistema FAT ni un INITRD reconocido. "
                    "No se puede abrir como contenedor con este motor.",
                    parent=self,
                )
            else:
                # Doble clic en archivos que no son contenedores: visor TXT/HEX.
                self.view_selected()
        except Exception as exc:
            messagebox.showerror(
                "Abrir contenedor",
                f"No se pudo abrir {p.name}:\n"
                f"{type(exc).__name__}: {exc}",
                parent=self,
            )

    def save_iso_copy(self):
        if not self.iso_path or not self.work_dir: return
        default = self.iso_path.with_name(self.iso_path.stem + "_MOD.iso").name
        dst = filedialog.asksaveasfilename(title="Guardar copia ISO", defaultextension=".iso", initialfile=default, filetypes=[("ISO","*.iso")])
        if not dst: return
        dst = Path(dst)
        self.set_status("Reconstruyendo ISO...")
        def worker():
            try:
                self._rebuild_iso(dst)
                self.after(0, lambda: self.set_status(f"ISO guardado: {dst}"))
                self.after(0, lambda: messagebox.showinfo("ISO", f"Copia modificada creada:\n{dst}", parent=self))
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("Guardar ISO", str(exc), parent=self))
                self.after(0, lambda: self.set_status("No se pudo reconstruir el ISO"))
        threading.Thread(target=worker, daemon=True).start()

    def _rebuild_iso(self, dst):
        if which("xorriso"):
            args = [
                "xorriso", "-indev", str(self.iso_path),
                "-outdev", str(dst),
                "-boot_image", "any", "replay",
                "-update_r", str(self.work_dir), "/",
                "-commit"
            ]
            r = run_cmd(args)
            if r.returncode == 0 and dst.exists() and dst.stat().st_size > 0:
                return
            raise RuntimeError("xorriso no pudo reconstruir el ISO:\n" + (r.stderr or r.stdout)[-2500:])

        try:
            import pycdlib
        except Exception as exc:
            raise RuntimeError(
                "Para guardar una copia arrancable instala xorriso.\n"
                "Sin xorriso solo puedo crear un ISO de datos si instalas pycdlib."
            ) from exc
        iso = pycdlib.PyCdlib()
        iso.new(interchange_level=3, joliet=3, rock_ridge="1.09")
        try:
            dirs = [p for p in self.work_dir.rglob("*") if p.is_dir()]
            for d in sorted(dirs, key=lambda p: len(p.parts)):
                rel = d.relative_to(self.work_dir).as_posix()
                rr = "/" + rel
                iso_name = "/" + "/".join((part[:8].upper().replace(" ","_") or "DIR") for part in rel.split("/"))
                try: iso.add_directory(iso_path=iso_name, rr_name=d.name, joliet_path=rr)
                except Exception: pass
            for f in [p for p in self.work_dir.rglob("*") if p.is_file()]:
                rel = f.relative_to(self.work_dir).as_posix()
                parts = rel.split("/")
                iso_parts = []
                for part in parts[:-1]: iso_parts.append((part[:8].upper().replace(" ","_") or "DIR"))
                stem = Path(parts[-1]).stem[:8].upper().replace(" ","_") or "FILE"
                ext = Path(parts[-1]).suffix[1:4].upper()
                iso_file = stem + ("." + ext if ext else "") + ";1"
                iso_path = "/" + "/".join(iso_parts + [iso_file])
                try: iso.add_file(str(f), iso_path=iso_path, rr_name=f.name, joliet_path="/"+rel)
                except Exception as exc: raise RuntimeError(f"No se pudo agregar {rel}: {exc}")
            iso.write(str(dst))
        finally:
            iso.close()
        if not dst.exists(): raise RuntimeError("No se genero el ISO")


# Entrada explicita para PTM. Se utiliza el editor principal, no los auxiliares.
# Evita que PTM confunda un editor de INITRD con la ventana principal.
App = ISOEditor


class StandaloneApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{TOOL_NAME} {TOOL_VERSION}")
        self.geometry("1180x720")
        self.minsize(900, 560)
        self.editor = ISOEditor(self)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
    def on_close(self):
        self.editor.cleanup(); self.destroy()


def create_tool(parent, app=None):
    """Entrada para PTM: devuelve un Frame embebible."""
    return ISOEditor(parent, app)


def main():
    app = StandaloneApp()
    if len(sys.argv) > 1:
        p = Path(sys.argv[1])
        if p.exists() and p.suffix.lower() == ".iso":
            app.after(200, lambda: app.editor.load_iso(p))
    app.mainloop()


if __name__ == "__main__":
    main()
