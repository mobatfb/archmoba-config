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
    "abre imagenes FAT como EFIBOOT.IMG y archivos INITRD CPIO, y genera una copia ISO modificada."
)
TOOL_VERSION = "1.0.5"


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
        ttk.Button(bar, text="Volver al ISO", command=self.owner._close_container_editor).pack(side="left", padx=(0, 12))
        ttk.Button(bar, text="Reemplazar", command=self.replace).pack(side="left", padx=3)
        ttk.Button(bar, text="Eliminar", command=self.delete).pack(side="left", padx=3)
        ttk.Button(bar, text="Extraer", command=self.extract).pack(side="left", padx=3)
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

    def save(self):
        try:
            raw = build_cpio_newc(self.entries)
            # Preservar exactamente las capas CPIO iniciales no editadas.
            updated = self.prefix + compress_bytes(raw, self.compression)
            self.path.write_bytes(updated)
            messagebox.showinfo("INITRD", "Cambios guardados en la copia de trabajo.", parent=self)
            self.owner.refresh_tree()
        except Exception as exc:
            messagebox.showerror("INITRD", str(exc), parent=self)


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
        if path and self.fs.isdir(path):
            self.current = path
            self.search_var.set("")
            self.refresh()

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
        self._container_host = None
        self.search_var = tk.StringVar(value="")
        self.search_info = tk.StringVar(value="")
        self._search_job = None
        self._search_index = None
        self._build_ui()

    def _build_ui(self):
        self.pack(fill="both", expand=True)
        top = ttk.Frame(self, padding=8); top.pack(fill="x")
        ttk.Button(top, text="Abrir ISO", command=self.open_iso).pack(side="left", padx=3)
        ttk.Button(top, text="Reemplazar", command=self.replace_selected).pack(side="left", padx=3)
        ttk.Button(top, text="Eliminar", command=self.delete_selected).pack(side="left", padx=3)
        ttk.Button(top, text="Extraer", command=self.extract_selected).pack(side="left", padx=3)
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
        self._container_host = None
        if host is not None:
            host.destroy()
            if self.work_dir is not None and self.work_dir.exists():
                self.refresh_tree()

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
            else:
                messagebox.showinfo(
                    "Contenedor",
                    f"{p.name} no tiene una cabecera FAT ni INITRD "
                    "reconocible. No se abrirá como FAT por su extensión "
                    ".img. Puedes inspeccionarlo en HEX, reemplazarlo o "
                    "extraerlo sin modificar el original.",
                    parent=self,
                )
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
