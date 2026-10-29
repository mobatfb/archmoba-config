"""PYRION OS - interactive, lightweight desktop environment.

The desktop is rendered with Tkinter Canvas and the Python standard library.
No window manager, Pillow, GPU or external UI toolkit is required.
"""

import base64
import json
import math
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import time
import tkinter as tk
import traceback
import urllib.request
import zlib
from datetime import datetime
from pathlib import Path

APP_NAME = "PYRION OS"
APP_VERSION = "0.3.0"
REPO_OWNER = "mobatfb"
REPO_NAME = "archmoba-config"
REPO_RAW_ROOT = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}"
REPO_RAW_BASE = f"{REPO_RAW_ROOT}/main/PYRION"
SELF_CONFIG_URL = f"{REPO_RAW_BASE}/config.json"
SELF_CONFIG_API_URL = (
    f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/"
    "PYRION/config.json?ref=main"
)

BG = "#050919"
TXT = "#e5eeff"
MUTED = "#8da4c9"
CYAN = "#50c6ff"
PURPLE = "#bd8bff"
GREEN = "#66e3ca"
AMBER = "#e5bd72"
PANEL = "#101d3a"

APP_CATALOG = (
    ("Explorador", "folder", "Favoritos"),
    ("Consola", "terminal", "Favoritos"),
    ("Navegador", "browser", "Internet"),
    ("Editor", "editor", "Herramientas"),
    ("Multimedia", "media", "Herramientas"),
    ("Monitor", "monitor", "Sistema"),
    ("Configuracion", "settings", "Sistema"),
    ("Red", "network", "Sistema"),
    ("Acerca de", "about", "Sistema"),
)
CATEGORIES = ("Favoritos", "Todas", "Sistema", "Herramientas", "Internet")
FAVORITES = {"Explorador", "Consola", "Navegador", "Editor", "Monitor", "Configuracion"}


def _clamp(n, low=0.0, high=1.0):
    return max(low, min(high, n))


def _blend(a, b, t):
    t = _clamp(t)
    a = a.lstrip("#")
    b = b.lstrip("#")
    vals = [round(int(a[i:i + 2], 16) * (1 - t)
                  + int(b[i:i + 2], 16) * t) for i in (0, 2, 4)]
    return "#%02x%02x%02x" % tuple(vals)


def _version_tuple(value):
    parts = []
    for part in str(value).strip().split("."):
        m = re.match(r"(\d+)", part)
        parts.append(int(m.group(1)) if m else 0)
    return tuple((parts + [0, 0, 0])[:3])


def _error_log(message):
    try:
        path = Path.home() / "pyrion_error.log"
        with path.open("a", encoding="utf-8") as file:
            file.write(f"\n[{datetime.now().isoformat(timespec='seconds')}]\n{message}\n")
    except OSError:
        pass


def check_self_update(restart=True):
    """Keep PYRION's existing pinned-commit update protocol."""
    try:
        payload = None
        try:
            req = urllib.request.Request(SELF_CONFIG_API_URL, headers={
                "User-Agent": f"PYRION/{APP_VERSION}",
                "Accept": "application/vnd.github+json",
                "Cache-Control": "no-cache",
            })
            with urllib.request.urlopen(req, timeout=6) as response:
                obj = json.loads(response.read().decode("utf-8"))
            encoded = str(obj.get("content", "")).replace("\n", "")
            payload = json.loads(base64.b64decode(encoded).decode("utf-8-sig"))
        except Exception:
            req = urllib.request.Request(
                f"{SELF_CONFIG_URL}?v={time.time_ns()}", headers={
                    "User-Agent": f"PYRION/{APP_VERSION}",
                    "Cache-Control": "no-cache",
                })
            with urllib.request.urlopen(req, timeout=6) as response:
                payload = json.loads(response.read().decode("utf-8-sig"))

        remote_version = str(payload.get("version", "")).strip()
        if not remote_version or _version_tuple(remote_version) <= _version_tuple(APP_VERSION):
            return False
        app_path = str(payload.get("app_path", "PYRION/app.py")).replace("\\", "/").lstrip("/")
        if app_path != "PYRION/app.py":
            raise RuntimeError("Ruta de actualizacion no autorizada")
        release_commit = str(payload.get("release_commit", "")).strip()
        if not re.fullmatch(r"[0-9a-fA-F]{40}", release_commit):
            raise RuntimeError("release_commit invalido")
        req = urllib.request.Request(
            f"{REPO_RAW_ROOT}/{release_commit}/{app_path}?v={time.time_ns()}",
            headers={"User-Agent": f"PYRION/{APP_VERSION}", "Cache-Control": "no-cache"},
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            source = response.read().decode("utf-8-sig")
        match = re.search(r'''APP_VERSION\s*=\s*["']([^"']+)["']''', source)
        if not match or match.group(1) != remote_version:
            raise RuntimeError("La version descargada no coincide con config.json")
        compile(source, "PYRION/app.py", "exec")
        current = Path(__file__).resolve()
        temporary = current.with_suffix(current.suffix + ".update")
        temporary.write_text(source, encoding="utf-8")
        os.replace(temporary, current)
        if restart:
            if os.name == "nt":
                subprocess.Popen([sys.executable, str(current), *sys.argv[1:]], cwd=str(current.parent))
                return True
            os.execv(sys.executable, [sys.executable, str(current), *sys.argv[1:]])
        return True
    except Exception as exc:
        _error_log(f"Fallo en autoactualizacion: {type(exc).__name__}: {exc}")
        return False


def _mem_usage():
    if os.name != "nt":
        try:
            values = {}
            for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
                key, _, rest = line.partition(":")
                if rest:
                    values[key] = int(rest.strip().split()[0])
            total = values.get("MemTotal", 0)
            free = values.get("MemAvailable", values.get("MemFree", 0))
            if total:
                return round(100.0 * (total-free) / total), round(total / 1024)
        except (OSError, ValueError, IndexError):
            pass
    else:
        try:
            import ctypes
            class MemStatus(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                    (name, ctypes.c_ulonglong) for name in (
                        "total_physical", "free_physical", "total_page", "free_page",
                        "total_virtual", "free_virtual", "extended")]
            data = MemStatus()
            data.length = ctypes.sizeof(MemStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(data)):
                return int(data.load), round(data.total_physical / (1024*1024))
        except Exception:
            pass
    return None, 0


def _cpu_ticks():
    try:
        if os.name == "nt":
            import ctypes
            a, b, c = (ctypes.c_ulonglong() for _ in range(3))
            result = ctypes.windll.kernel32.GetSystemTimes(
                ctypes.byref(a), ctypes.byref(b), ctypes.byref(c))
            if result:
                total = int(a.value+b.value+c.value)
                return total, int(a.value)
        else:
            numbers = list(map(int, Path("/proc/stat").read_text(encoding="ascii")
                                   .splitlines()[0].split()[1:]))
            total = sum(numbers)
            return total, numbers[3] + (numbers[4] if len(numbers) > 4 else 0)
    except (OSError, ValueError, IndexError, AttributeError):
        pass
    return None


def _disk_usage():
    try:
        location = Path.home().anchor if os.name == "nt" else "/"
        info = shutil.disk_usage(location)
        return round(info.used*100/max(info.total,1)), info.used, info.total
    except (OSError, ValueError):
        return None, 0, 0


def _network_state():
    try:
        names = [name for _, name in socket.if_nameindex() if name not in ("lo", "lo0")]
    except (OSError, AttributeError):
        return None, "Interfaces no disponibles"
    if not names:
        return False, "Sin interfaces activas"
    if os.name != "nt":
        active = []
        for name in names:
            try:
                if (Path("/sys/class/net") / name / "operstate").read_text().strip() == "up":
                    active.append(name)
            except OSError:
                continue
        return bool(active), ", ".join(active[:2]) if active else "Enlace inactivo"
    return None, f"{len(names)} adaptador(es) detectado(s)"


def _png_chunk(kind, payload):
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))


def _photo_rgba(parent, w, h, rgba_rows):
    """Generate a transparent PNG using only stdlib, then load into Tk PhotoImage."""
    data = bytearray()
    for row in rgba_rows:
        data.append(0)  # PNG filter = none
        data.extend(row)
    png = (b"\x89PNG\r\n\x1a\n"
           + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
           + _png_chunk(b"IDAT", zlib.compress(bytes(data), 6))
           + _png_chunk(b"IEND", b""))
    return tk.PhotoImage(master=parent, data=base64.b64encode(png))


def _orb_texture(parent, diameter):
    """Rim-lit sphere and specular reflection; transparent outside the circle."""
    diameter = max(80, int(diameter))
    radius = diameter/2.0 - 3
    mid = (diameter-1)/2.0
    rows = []
    for y in range(diameter):
        line = bytearray()
        ny = (y-mid)/radius
        for x in range(diameter):
            nx = (x-mid)/radius
            sq = nx*nx + ny*ny
            if sq > 1:
                line.extend((0, 0, 0, 0))
                continue
            nz = math.sqrt(max(0, 1-sq))
            # Soft studio light from the upper-left and a blue lower-right rim.
            main = max(0.0, -.43*nx-.58*ny+.69*nz)
            cool = max(0.0, .74*nx+.20*ny+.35*nz)
            spec = math.exp(-((nx+.31)**2+(ny+.39)**2)/.042)
            purple = _clamp(.47 + ny*.44 - nx*.26)
            base_r = 31 + 45*purple
            base_g = 42 + 23*(1-purple)
            base_b = 113 + 28*main
            light = 95*main**1.85
            rim = (1-nz)**2.1
            r = int(_clamp((base_r + light*.66 + 102*spec + 59*rim)/255)*255)
            g = int(_clamp((base_g + light*1.02 + 129*spec + 89*cool*rim)/255)*255)
            b = int(_clamp((base_b + light*1.12 + 135*spec + 99*rim)/255)*255)
            alpha = int(255*_clamp((1-sq)*radius/1.4))
            line.extend((r, g, b, alpha))
        rows.append(line)
    return _photo_rgba(parent, diameter, diameter, rows)

class PyrionApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME}  {APP_VERSION}")
        self.configure(bg=BG)
        self.windowed = "--windowed" in sys.argv or os.environ.get("PYRION_WINDOWED") == "1"
        self.left_open = True
        self.right_open = True
        self.core_open = False
        self.detail = None
        self.category = "Favoritos"
        self.page = 0
        self.notifications = [
            ("Escritorio PYRION preparado", "Sistema"),
            ("Controles interactivos disponibles", "Interfaz"),
        ]
        self.sessions = []
        self.cpu_prev = _cpu_ticks()
        self.cpu_percent = None
        self.ram_percent = None
        self.ram_total = 0
        self.disk_percent = None
        self.disk_used = 0
        self.disk_total = 0
        self.net_connected = None
        self.net_label = "Detectando interfaces"
        self.w = 1320
        self.h = 720
        self.s = 1.0
        self.compact = False
        self.hit_seq = 0
        self.render_job = None
        self._lower_job = None
        self._tick_job = None
        self._animate_job = None
        self._geom_job = None
        self.orb_photo = None
        self.orb_photo_size = 0
        self.orb_glow_ids = []
        self.pulse_t = 0.0
        self.has_been_drawn = False
        self._force_fullscreen()

        self.canvas = tk.Canvas(self, bg=BG, bd=0, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._schedule_draw)
        self.canvas.bind("<Button-1>", self._canvas_background_click)
        self.canvas.bind("<MouseWheel>", self._wheel_apps)
        self.canvas.bind("<Button-4>", lambda e: self._page_shift(-1))
        self.canvas.bind("<Button-5>", lambda e: self._page_shift(+1))
        self.bind("<Escape>", self._escape)
        self.bind("<F11>", self._toggle_window_mode)
        self.bind("<Control-Alt-t>", lambda e: self.launch("Consola"))
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self.search = tk.Entry(
            self.canvas, bg="#0d1c39", fg="#829dc4", insertbackground=CYAN,
            font=("DejaVu Sans", 10), relief="flat", bd=0,
            highlightbackground="#29476f", highlightcolor="#4cb9f9",
            highlightthickness=1, selectbackground="#315a91",
        )
        self.search_is_placeholder = True
        self.search.insert(0, "Buscar aplicaciones...")
        self.search.bind("<FocusIn>", self._search_focus_in)
        self.search.bind("<FocusOut>", self._search_focus_out)
        self.search.bind("<KeyRelease>", self._search_changed)
        self.search.bind("<Return>", self._search_launch)
        self.search.bind("<Escape>", self._search_escape)

        self.render_job = self.after(180, self._draw)
        self._tick_job = self.after(450, self._tick)
        self._animate_job = self.after(200, self._animate)
        self._lower_job = self.after(800, self._keep_in_background)

    def _force_fullscreen(self):
        self.update_idletasks()
        if self.windowed:
            self.geometry(os.environ.get("PYRION_GEOMETRY", "1320x720"))
            self.minsize(760, 480)
            return
        if os.name == "nt":
            self.attributes("-fullscreen", True)
            return
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.overrideredirect(True)
        self.geometry(f"{sw}x{sh}+0+0")
        try:
            self.attributes("-topmost", False)
        except tk.TclError:
            pass
        self._geom_job = self.after(100, lambda: self.geometry(
            f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0"))

    def _toggle_window_mode(self, _event=None):
        if self.windowed:
            return
        self.windowed = True
        try:
            if os.name == "nt":
                self.attributes("-fullscreen", False)
            else:
                self.overrideredirect(False)
            self.geometry("1320x720")
            self.minsize(760, 480)
        except tk.TclError:
            pass
        self._schedule_draw()

    def _keep_in_background(self):
        try:
            if not self.windowed:
                self.attributes("-topmost", False)
                self.lower()
            self._lower_job = self.after(1200, self._keep_in_background)
        except tk.TclError:
            pass

    def _search_focus_in(self, _event=None):
        if self.search_is_placeholder:
            self.search.delete(0, "end")
            self.search.configure(fg=TXT)
            self.search_is_placeholder = False

    def _search_focus_out(self, _event=None):
        if not self.search.get().strip():
            self.search_is_placeholder = True
            self.search.configure(fg="#829dc4")
            self.search.insert(0, "Buscar aplicaciones...")
        self._schedule_draw()

    def _search_changed(self, _event=None):
        self.page = 0
        self._schedule_draw()

    def _search_launch(self, _event=None):
        matches = self._filtered_apps()
        if matches:
            self.launch(matches[0][0])

    def _search_escape(self, _event=None):
        self.search.delete(0, "end")
        self.search.focus_set()
        self.page = 0
        self._schedule_draw()
        return "break"

    def _search_term(self):
        return "" if self.search_is_placeholder else self.search.get().strip().lower()

    def _filtered_apps(self):
        query = self._search_term()
        output = []
        for item in APP_CATALOG:
            name, icon, group = item
            # La busqueda siempre es global, independientemente de la categoria.
            if not query:
                if self.category == "Favoritos" and name not in FAVORITES:
                    continue
                if self.category not in ("Todas", "Favoritos") and group != self.category:
                    continue
            elif query not in name.lower() and query not in group.lower():
                continue
            output.append(item)
        return output

    def _schedule_draw(self, _event=None):
        if self.render_job is not None:
            try:
                self.after_cancel(self.render_job)
            except tk.TclError:
                pass
        self.render_job = self.after(55, self._draw)

    def _animate(self):
        try:
            self.pulse_t += 0.18
            if self.has_been_drawn:
                for i, (object_id, base) in enumerate(self.orb_glow_ids):
                    d = (math.sin(self.pulse_t + i*.45) + 1) * 3*self.s
                    cx = self.w/2
                    cy = self.h*.475
                    size = base+d
                    self.canvas.coords(object_id, cx-size, cy-size, cx+size, cy+size)
            self._animate_job = self.after(150, self._animate)
        except tk.TclError:
            pass

    def _tick(self):
        try:
            tick = _cpu_ticks()
            if tick is not None and self.cpu_prev is not None and tick[0] > self.cpu_prev[0]:
                delta = tick[0] - self.cpu_prev[0]
                idle = tick[1] - self.cpu_prev[1]
                self.cpu_percent = round(_clamp((delta-idle)/delta)*100)
            self.cpu_prev = tick
            self.ram_percent, self.ram_total = _mem_usage()
            self.disk_percent, self.disk_used, self.disk_total = _disk_usage()
            self.net_connected, self.net_label = _network_state()
            self.sessions = [(label,p) for label,p in self.sessions if p.poll() is None][-16:]
            self._schedule_draw()
        except Exception:
            _error_log(traceback.format_exc())
        finally:
            try:
                self._tick_job = self.after(3500, self._tick)
            except tk.TclError:
                pass

    def _font(self, size, bold=False):
        return ("DejaVu Sans", max(8, round(size*self.s)), "bold" if bold else "normal")

    def _text(self, x, y, value, size=12, color=TXT, anchor="nw", bold=False,
              tags=(), width=None):
        kw = {"tags": tags}
        if width is not None:
            kw["width"] = width
        return self.canvas.create_text(x, y, text=str(value), fill=color, anchor=anchor,
                                       font=self._font(size, bold), **kw)

    def _line(self, x1,y1,x2,y2,color,width=1,tags=()):
        return self.canvas.create_line(x1,y1,x2,y2,fill=color,width=width,tags=tags)

    def _rounded(self,x1,y1,x2,y2,fill,outline="",radius=12,stroke=1,tags=()):
        radius=min(radius,max(0,(x2-x1)/2),max(0,(y2-y1)/2))
        if radius < 1:
            return self.canvas.create_rectangle(x1,y1,x2,y2,fill=fill,outline=outline,
                                                width=stroke,tags=tags)
        points=[x1+radius,y1, x2-radius,y1, x2,y1, x2,y1+radius,
                x2,y2-radius, x2,y2, x2-radius,y2, x1+radius,y2,
                x1,y2,x1,y2-radius, x1,y1+radius, x1,y1]
        return self.canvas.create_polygon(points,smooth=True,fill=fill,outline=outline,
                                          width=stroke,tags=tags)

    def _tag(self, action, target=None, accent=CYAN):
        tag = "tap_" + str(self.hit_seq)
        self.hit_seq += 1
        self.canvas.tag_bind(tag,"<Button-1>",lambda event: action())
        self.canvas.tag_bind(tag,"<Enter>",lambda event: self._hover(target,accent,True))
        self.canvas.tag_bind(tag,"<Leave>",lambda event: self._hover(target,accent,False))
        return tag

    def _hit(self, tag, action, target=None, accent=CYAN):
        self.canvas.tag_bind(tag,"<Button-1>",lambda event: action())
        self.canvas.tag_bind(tag,"<Enter>",lambda event: self._hover(target,accent,True))
        self.canvas.tag_bind(tag,"<Leave>",lambda event: self._hover(target,accent,False))

    def _hover(self, item, color, entered):
        try:
            self.canvas.configure(cursor="hand2" if entered else "")
            if item is not None:
                self.canvas.itemconfigure(item,
                    outline=color if entered else "#29466e",
                    width=1.8*self.s if entered else 1)
        except tk.TclError:
            pass

    def _button(self,x1,y1,x2,y2,label,action,selected=False,accent=CYAN,size=10):
        tag="tap_"+str(self.hit_seq)
        self.hit_seq += 1
        fill = "#253c6c" if selected else "#142648"
        border = accent if selected else "#29466e"
        obj=self._rounded(x1,y1,x2,y2,fill,border,9*self.s,1.2*self.s,(tag,))
        self._text((x1+x2)/2,(y1+y2)/2,label,size,
                   TXT if selected else "#bdcfee",anchor="center",tags=(tag,))
        self._hit(tag,action,obj,accent)
        return obj

    def _background(self):
        c=self.canvas
        bands=105
        for i in range(bands):
            p=i/(bands-1)
            base=_blend("#050918","#091630",p*.9)
            if p>.63:
                base=_blend(base,"#0e1741",(p-.63)*.22)
            y1=self.h*i/bands
            y2=self.h*(i+1)/bands+1
            c.create_rectangle(0,y1,self.w,y2,fill=base,outline="")
        cx=self.w*.5
        cy=self.h*.72
        # Un brillo ambiental plano, en lugar de muchas lineas sobre el suelo.
        for scale,color in ((.24,"#0a1731"),(.17,"#101f46"),(.09,"#173267")):
            xr=self.w*scale
            yr=self.h*.017*scale/.24
            c.create_oval(cx-xr,cy-yr,cx+xr,cy+yr,fill=color,outline="")
        for i in range(13):
            x=(i*487+113)%self.w
            y=(i*167+29)%(self.h*.57)
            d=(1 if i%3 else 2)*self.s
            c.create_oval(x-d,y-d,x+d,y+d,fill="#163052",outline="")
        self._line(self.w*.16,self.h*.91,self.w*.84,self.h*.91,"#10234a",1)

    def _geometry(self,side):
        # Shallower perspective leaves sufficient vertical room for real controls.
        pad=max(14,19*self.s)
        if side=="left":
            x0,x1=pad,self.w*.377
            top0,top1=self.h*.088,self.h*.158
            bottom0,bottom1=self.h*.944,self.h*.856
        else:
            x0,x1=self.w*.623,self.w-pad
            top0,top1=self.h*.158,self.h*.088
            bottom0,bottom1=self.h*.856,self.h*.944
        return x0,x1,top0,top1,bottom0,bottom1

    def _panel(self,side):
        x0,x1,t0,t1,b0,b1=self._geometry(side)
        c=self.canvas
        coords=[x0,t0,x1,t1,x1,b1,x0,b0]
        accent=PURPLE if side=="left" else CYAN
        base="#171139" if side=="left" else "#08284a"
        c.create_polygon(coords,fill="",outline=_blend(BG,accent,.22),width=11*self.s)
        c.create_polygon(coords,fill="",outline=_blend(BG,accent,.43),width=6*self.s)
        c.create_polygon(coords,fill="#0b152c",outline="",width=0)
        bands=68
        for i in range(bands):
            f=i/bands
            q=(i+1)/bands
            y00=t0+(b0-t0)*f
            y10=t1+(b1-t1)*f
            y01=t0+(b0-t0)*q+1
            y11=t1+(b1-t1)*q+1
            upper=_blend("#102447",base,.25 if side=="left" else .12)
            lower="#091329" if side=="left" else "#091831"
            color=_blend(upper,lower,f*.94)
            c.create_polygon([x0,y00,x1,y10,x1,y11,x0,y01],fill=color,outline="")
        c.create_polygon(coords,fill="",outline=_blend(accent,"#81aefb",.32),width=1.7*self.s)
        c.create_line(x0+2*self.s,t0+8*self.s,x0+2*self.s,b0-8*self.s,
                      fill=_blend(accent,BG,.28),width=2.8*self.s)
        c.create_line(x0+7*self.s,t0+11*self.s,x0+7*self.s,b0-11*self.s,
                      fill=_blend(accent,BG,.75),width=.9*self.s)
        c.create_line(x0+13*self.s,t0+6*self.s,x1-10*self.s,t1+4*self.s,
                      fill=_blend(accent,"#b5d8ff",.32),width=.95*self.s)
        content_l=x0+37*self.s
        content_r=x1-32*self.s
        content_t=max(t0,t1)+18*self.s
        content_b=min(b0,b1)-15*self.s
        return content_l,content_t,content_r,content_b

    def _draw_icon(self,kind,cx,cy,size,color,tags=()):
        c=self.canvas
        r=size/2
        dark="#102a52"
        if kind=="folder":
            c.create_polygon(cx-r,cy-r*.40,cx-r*.3,cy-r*.40,
                             cx-r*.05,cy-r*.68,cx+r*.8,cy-r*.68,
                             cx+r,cy-r*.38,cx+r,cy+r*.67,
                             cx-r,cy+r*.67,fill=color,outline="#c3e9ff",width=.7,tags=tags)
            c.create_line(cx-r*.70,cy-r*.16,cx+r*.72,cy-r*.16,
                          fill="#b8eaff",width=1.1,tags=tags)
        elif kind=="terminal":
            self._rounded(cx-r,cy-r*.76,cx+r,cy+r*.76,dark,color,4*self.s,1.6,tags)
            self._text(cx-r*.62,cy-r*.12,">_",12,color,"w",True,tags)
        elif kind=="browser":
            c.create_oval(cx-r*.87,cy-r*.87,cx+r*.87,cy+r*.87,
                          fill=dark,outline=color,width=1.9,tags=tags)
            c.create_line(cx-r*.81,cy,cx+r*.81,cy,fill=color,width=1,tags=tags)
            c.create_arc(cx-r*.44,cy-r*.87,cx+r*.44,cy+r*.87,
                         start=90,extent=180,style="arc",outline=color,width=1,tags=tags)
            c.create_arc(cx-r*.44,cy-r*.87,cx+r*.44,cy+r*.87,
                         start=270,extent=180,style="arc",outline=color,width=1,tags=tags)
        elif kind=="editor":
            c.create_polygon(cx-r*.72,cy-r,cx+r*.40,cy-r,cx+r*.72,cy-r*.65,
                             cx+r*.72,cy+r,cx-r*.72,cy+r,
                             fill=dark,outline=color,width=1.6,tags=tags)
            for n in range(3):
                yy=cy-r*.39+n*r*.42
                c.create_line(cx-r*.41,yy,cx+r*.35,yy,fill=color,width=1,tags=tags)
        elif kind=="media":
            c.create_oval(cx-r*.90,cy-r*.90,cx+r*.90,cy+r*.90,
                          fill=dark,outline=color,width=1.5,tags=tags)
            c.create_polygon(cx-r*.25,cy-r*.52,cx+r*.61,cy,
                             cx-r*.25,cy+r*.52,fill=color,outline="",tags=tags)
        elif kind=="monitor":
            c.create_line(cx-r,cy,cx-r*.53,cy,cx-r*.33,cy-r*.50,
                          cx-r*.05,cy+r*.49,cx+r*.22,cy-r*.28,
                          cx+r*.40,cy,cx+r,cy,fill=color,width=2,tags=tags)
        elif kind=="settings":
            c.create_oval(cx-r*.77,cy-r*.77,cx+r*.77,cy+r*.77,
                          outline=color,width=3,tags=tags)
            c.create_oval(cx-r*.24,cy-r*.24,cx+r*.24,cy+r*.24,
                          fill=color,outline="",tags=tags)
            for i in range(8):
                th=math.pi*i/4
                c.create_line(cx+math.cos(th)*r*.70,cy+math.sin(th)*r*.70,
                              cx+math.cos(th)*r*1.06,cy+math.sin(th)*r*1.06,
                              fill=color,width=2,tags=tags)
        elif kind=="network":
            for x,y in ((cx,cy-r*.86),(cx-r*.86,cy+r*.73),(cx+r*.86,cy+r*.73)):
                c.create_oval(x-3*self.s,y-3*self.s,x+3*self.s,y+3*self.s,
                              fill=color,outline="",tags=tags)
            c.create_line(cx,cy-r*.78,cx-r*.80,cy+r*.67,
                          cx+r*.80,cy+r*.67,cx,cy-r*.78,fill=color,width=1.6,tags=tags)
        else:
            c.create_oval(cx-r*.80,cy-r*.80,cx+r*.80,cy+r*.80,
                          fill=dark,outline=color,width=1.5,tags=tags)
            self._text(cx,cy,"i",15,color,anchor="center",bold=True,tags=tags)

    def _left_panel(self):
        if not self.left_open:
            self.search.place_forget()
            self._button(12*self.s,self.h*.45,105*self.s,self.h*.45+38*self.s,
                         "APPS  >",lambda:self._toggle_panel("left"),accent=PURPLE)
            return
        l,t,r,b=self._panel("left")
        self._text(l,t+4*self.s,"P Y R I O N",20,"#cfd9ff",bold=True)
        self._text(l,t+34*self.s,"APP CENTER  /  DESKTOP",9,"#869fc8")
        self._text(r,t+13*self.s,"03",9,PURPLE,anchor="ne",bold=True)
        self._button(r-26*self.s,t+42*self.s,r,t+69*self.s,"<",
                     lambda:self._toggle_panel("left"),accent=PURPLE,size=11)
        search_y=t+75*self.s
        search_h=32*self.s
        self.search.place(x=round(l),y=round(search_y),
                          width=max(140,round(r-l)),height=round(search_h))
        self.search.lift()
        body_y=t+124*self.s
        categories_width=min(112*self.s,(r-l)*.36)
        grid_left=l+categories_width+15*self.s
        grid_right=r
        nav_h=37*self.s
        nav_step=46*self.s
        for i,cat in enumerate(CATEGORIES):
            y=body_y+i*nav_step
            if y+nav_h > b-32*self.s:
                break
            short={"Configuracion":"Ajustes"}.get(cat,cat)
            self._button(l,y,l+categories_width,y+nav_h,short,
                         lambda v=cat:self._select_category(v),
                         selected=(cat==self.category),accent=PURPLE,size=9)
        self._line(grid_left-7*self.s,body_y,grid_left-7*self.s,b-33*self.s,
                   "#29365c",1)
        apps=self._filtered_apps()
        width=max(1,grid_right-grid_left)
        cols=2 if width >= 160*self.s else 1
        rows=3 if b-body_y >= 240*self.s else 2
        usable_h=b-body_y-34*self.s
        gap_x=10*self.s
        gap_y=10*self.s
        tile_w=(width-(cols-1)*gap_x)/cols
        tile_h=min(94*self.s,(usable_h-(rows-1)*gap_y)/rows)
        tile_h=max(54*self.s,tile_h)
        per_page=cols*rows
        pages=max(1,math.ceil(len(apps)/per_page))
        self.page=min(self.page,pages-1)
        visible=apps[self.page*per_page:(self.page+1)*per_page]
        for i,(label,icon,group) in enumerate(visible):
            row,col=divmod(i,cols)
            x=grid_left+col*(tile_w+gap_x)
            y=body_y+row*(tile_h+gap_y)
            tag="app_"+str(i)
            rect=self._rounded(x,y,x+tile_w,y+tile_h,"#13264b","#29466e",
                               10*self.s,1.2*self.s,(tag,))
            self._draw_icon(icon,x+tile_w/2,y+tile_h*.37,
                            min(31*self.s,tile_h*.37),
                            ("#5ed4ff" if i%3!=1 else "#b58bff"),(tag,))
            display_name="Configuraci\u00f3n" if label=="Configuracion" else label
            self._text(x+tile_w/2,y+tile_h*.78,display_name,9,"#d3e5ff",
                       anchor="center",bold=False,tags=(tag,))
            self._hit(tag,lambda n=label:self.launch(n),rect,PURPLE)
        if not apps:
            self._text(grid_left+5*self.s,body_y+15*self.s,
                       "Sin resultados",10,"#9eb3d3")
        bottom_y=b-23*self.s
        self._text(l,bottom_y,"ARCHMOBA  /  PYRION 0.3",8,"#7689b0")
        if pages>1:
            step=24*self.s
            self._button(r-step*3,bottom_y-4*self.s,r-step*2,bottom_y+19*self.s,
                         "<",lambda:self._page_shift(-1),accent=PURPLE,size=9)
            self._text(r-step*1.55,bottom_y+7*self.s,
                       f"{self.page+1}/{pages}",9,"#adbee2",anchor="center")
            self._button(r-step,bottom_y-4*self.s,r,bottom_y+19*self.s,
                         ">",lambda:self._page_shift(1),accent=PURPLE,size=9)

    def _gauge(self,cx,cy,r,value,label,color):
        c=self.canvas
        s=self.s
        c.create_oval(cx-r,cy-r,cx+r,cy+r,
                      outline="#1d3558",width=5*s)
        if value is not None:
            fraction=_clamp(value/100)
            if fraction>.002:
                c.create_arc(cx-r,cy-r,cx+r,cy+r,start=90,extent=-max(.5,fraction*360),
                             style="arc",outline=color,width=5*s)
            shown=f"{round(value)}%"
        else:
            shown="--"
        self._text(cx,cy-4*s,shown,12,TXT,anchor="center",bold=True)
        self._text(cx,cy+r+10*s,label,9,MUTED,anchor="center")

    def _right_panel(self):
        if not self.right_open:
            x=self.w-109*self.s
            self._button(x,self.h*.45,self.w-12*self.s,self.h*.45+38*self.s,
                         "<  ESTADO",lambda:self._toggle_panel("right"),accent=CYAN)
            return
        l,t,r,b=self._panel("right")
        self._text(l,t+1*self.s,"CENTRO DE SISTEMA",10,CYAN,bold=True)
        self._text(l,t+21*self.s,datetime.now().strftime("%H:%M"),27,TXT,bold=True)
        self._text(r,t+42*self.s,datetime.now().strftime("%d / %m / %Y"),10,
                   "#9eb9e0",anchor="ne")
        self._button(r-28*self.s,t+4*self.s,r,t+31*self.s,">",
                     lambda:self._toggle_panel("right"),accent=CYAN,size=12)
        # Real-time hardware gauges.
        m_top=t+90*self.s
        m_bottom=m_top+105*self.s
        self._rounded(l,m_top,r,m_bottom,"#102546","#2b5687",12*self.s,1)
        self._text(l+13*self.s,m_top+10*self.s,"RENDIMIENTO",9,"#9fc4ee",bold=True)
        metric_y=m_top+56*self.s
        available=r-l
        for i,(name,percent,color) in enumerate((
            ("CPU",self.cpu_percent,CYAN),
            ("RAM",self.ram_percent,PURPLE),
            ("DISCO",self.disk_percent,"#6ee1cd"),
        )):
            cx=l+available*(i+.5)/3
            self._gauge(cx,metric_y,min(24*self.s,available/13),percent,name,color)
        # Network link state (not confused with confirmed Internet access).
        net_top=m_bottom+11*self.s
        net_bottom=net_top+58*self.s
        self._rounded(l,net_top,r,net_bottom,"#101f3b","#294772",10*self.s,1)
        state="ACTIVA" if self.net_connected else "SIN ENLACE" if self.net_connected is False else "DESCONOCIDA"
        dot=GREEN if self.net_connected else AMBER
        self.canvas.create_oval(l+14*self.s,net_top+14*self.s,
                                l+22*self.s,net_top+22*self.s,fill=dot,outline="")
        self._text(l+31*self.s,net_top+11*self.s,"RED LOCAL  /  "+state,10,TXT,bold=True)
        self._text(l+14*self.s,net_top+34*self.s,self.net_label[:58],9,
                   "#94aacd",width=max(90,r-l-27*self.s))
        # Notifications: always real messages generated by PYRION actions.
        note_top=net_bottom+11*self.s
        note_bottom=b-58*self.s
        if note_bottom-note_top > 62*self.s:
            self._rounded(l,note_top,r,note_bottom,"#0e1d37","#263e66",10*self.s,1)
            self._text(l+13*self.s,note_top+11*self.s,"ACTIVIDAD RECIENTE",10,CYAN,bold=True)
            for i,(message,source) in enumerate(self.notifications[-2:][::-1]):
                yy=note_top+(39+i*24)*self.s
                if yy+18*self.s > note_bottom:
                    break
                self.canvas.create_oval(l+13*self.s,yy+3*self.s,
                                        l+18*self.s,yy+8*self.s,fill=GREEN if i==0 else PURPLE,
                                        outline="")
                self._text(l+25*self.s,yy,message[:55],9,"#c8d9f6",
                           width=max(130,r-l-38*self.s))
        # Real quick actions instead of static decorative text.
        action_y=b-45*self.s
        action_h=38*self.s
        choices=(
            ("ESPACIO",self._hide_both),
            ("AUDIO",lambda:self._show_detail("Audio")),
            ("RED",lambda:self._show_detail("Red")),
            ("ENERGIA",lambda:self._show_detail("Energia")),
        )
        gap=7*self.s
        bw=((r-l)-gap*3)/4
        for i,(label,cmd) in enumerate(choices):
            xx=l+i*(bw+gap)
            self._button(xx,action_y,xx+bw,action_y+action_h,label,cmd,
                         accent=CYAN,size=8)

    def _draw_orb(self):
        c=self.canvas
        cx=self.w/2
        cy=self.h*.475
        radius=min(self.w*.066,self.h*.116)
        self.orb_glow_ids=[]
        # Atmospheric halo, understated and animated without re-rendering the image.
        for i in range(3,0,-1):
            r=radius+(10+i*7)*self.s
            ring=c.create_oval(cx-r,cy-r,cx+r,cy+r,
                              outline=("#19225a","#283d85","#3b57bc")[3-i],
                              width=max(1,1.5*self.s))
            self.orb_glow_ids.append((ring,r))
        # Elliptical orbit ring behind the orb.
        c.create_arc(cx-radius*1.46,cy-radius*.46,
                     cx+radius*1.46,cy+radius*.64,
                     start=165,extent=153,style="arc",outline="#594bda",width=1.8*self.s)
        diameter=round(radius*2)
        if self.orb_photo is None or abs(diameter-self.orb_photo_size)>5:
            self.orb_photo=_orb_texture(self,diameter)
            self.orb_photo_size=diameter
        tag="orb"
        c.create_image(cx,cy,image=self.orb_photo,anchor="center",tags=(tag,))
        c.create_arc(cx-radius*1.48,cy-radius*.47,
                     cx+radius*1.48,cy+radius*.66,
                     start=344,extent=157,style="arc",outline="#ac80ff",width=2*self.s,
                     tags=(tag,))
        self._hit(tag,self._toggle_core)
        # Ground light and shadow: only three rings, not dense spider-web lines.
        floor_y=cy+radius+106*self.s
        for scale,color in ((1.17,"#162b5d"),(.90,"#315fb5"),(.52,"#398add")):
            rx=radius*scale
            ry=radius*.14*scale
            c.create_oval(cx-rx,floor_y-ry,cx+rx,floor_y+ry,
                          outline=color,width=1.1*self.s)
        c.create_oval(cx-radius*.23,floor_y-radius*.035,
                      cx+radius*.23,floor_y+radius*.035,
                      fill="#2867ad",outline="")
        self._text(cx,cy+radius+48*self.s,"P Y R I O N",13,TXT,
                   anchor="center",bold=True)
        self._text(cx,cy+radius+68*self.s,"CENTRO DE CONTROL",9,"#8ca4ce",
                   anchor="center")
        # Area around the core label can also open the menu.
        tag2="orb_label"
        c.create_rectangle(cx-radius,cy+radius+43*self.s,
                           cx+radius,cy+radius+78*self.s,
                           fill="",outline="",tags=(tag2,))
        self._hit(tag2,self._toggle_core)

    def _core_menu(self):
        if not self.core_open:
            return
        cx=self.w*.5
        top=self.h*.735
        ww=min(self.w*.30,330*self.s)
        hh=151*self.s
        if top+hh > self.h-12*self.s:
            top=self.h-hh-13*self.s
        # Dark panel shields the dense background and preserves readability.
        self._rounded(cx-ww/2-4*self.s,top-3*self.s,cx+ww/2+4*self.s,
                      top+hh+5*self.s,"#081121","#172b53",16*self.s,3)
        self._rounded(cx-ww/2,top,cx+ww/2,top+hh,"#132449","#6b73bb",14*self.s,1.5)
        self._text(cx,top+15*self.s,"N\u00daCLEO PYRION",12,TXT,anchor="center",bold=True)
        self._text(cx,top+35*self.s,"Control de tu entorno",9,MUTED,anchor="center")
        pad=14*self.s
        gap=9*self.s
        cell=(ww-2*pad-gap)/2
        actions=(
            ("APLICACIONES",self._open_apps),
            ("MONITOR",lambda:self._show_detail("Sistema")),
            ("CONSOLA",lambda:self.launch("Consola")),
            ("CERRAR MENU",self._close_core),
        )
        for i,(label,action) in enumerate(actions):
            row,col=divmod(i,2)
            x=cx-ww/2+pad+col*(cell+gap)
            y=top+60*self.s+row*41*self.s
            self._button(x,y,x+cell,y+32*self.s,label,action,
                         accent=PURPLE,size=9)

    def _detail_text(self,kind):
        if kind=="Sistema":
            cpu=f"{self.cpu_percent}%" if self.cpu_percent is not None else "No disponible"
            mem=f"{self.ram_percent}% de {self.ram_total} MB" if self.ram_percent is not None else "No disponible"
            disk=f"{self.disk_percent}%" if self.disk_percent is not None else "No disponible"
            return [
                ("Procesador",cpu),
                ("Memoria",mem),
                ("Almacenamiento",disk),
                ("Procesadores logicos",str(os.cpu_count() or "No disponible")),
            ]
        if kind=="Red":
            try:
                host=socket.gethostname()
            except OSError:
                host="No disponible"
            status=("Enlace activo" if self.net_connected else
                    "Sin enlace" if self.net_connected is False else "No comprobado")
            return [("Nombre de equipo",host),("Estado de interfaces",status),
                    ("Dispositivos",self.net_label)]
        if kind=="Audio":
            mixer="amixer disponible" if shutil.which("amixer") else "Mezclador no disponible"
            return [("Audio del equipo",mixer),
                    ("Acciones","Control de volumen local")]
        if kind=="Energia":
            return [("Salir del entorno","Cierra PYRION sin apagar el equipo"),
                    ("Apagar Linux","Solo con confirmacion; no disponible en Windows")]
        if kind=="Confirmar apagado":
            return [("Confirmacion","Se intentara apagar el sistema Linux"),
                    ("Advertencia","Guarda tus trabajos antes de continuar")]
        return [("Nombre","PYRION OS"),("Version",APP_VERSION),
                ("Diseño","Escritorio futurista con Canvas y Tkinter"),
                ("Proyecto","ARCHMOBA")]

    def _detail_overlay(self):
        if self.detail is None:
            return
        c=self.canvas
        kind=self.detail
        ww=min(490*self.s,self.w*.46)
        hh=min(320*self.s,self.h*.56)
        x1=self.w*.5-ww/2
        y1=max(32*self.s,self.h*.095)
        x2=x1+ww
        y2=y1+hh
        self._rounded(x1+7*self.s,y1+9*self.s,x2+7*self.s,y2+9*self.s,
                      "#050a17","#08142b",16*self.s,2)
        self._rounded(x1,y1,x2,y2,"#101e3b","#638ac6",15*self.s,1.6)
        self._text(x1+22*self.s,y1+18*self.s,
                   {"Energia":"OPCIONES DE ENERGIA","Confirmar apagado":"CONFIRMAR APAGADO"}.get(
                       kind,kind.upper()),15,TXT,bold=True)
        self._button(x2-41*self.s,y1+12*self.s,x2-13*self.s,y1+43*self.s,
                     "X",self._close_detail,accent=PURPLE)
        self._line(x1+19*self.s,y1+54*self.s,x2-19*self.s,y1+54*self.s,
                   "#365582",1)
        body_top=y1+74*self.s
        for i,(label,value) in enumerate(self._detail_text(kind)):
            y=body_top+i*44*self.s
            if y+21*self.s >= y2-49*self.s:
                break
            self._text(x1+23*self.s,y,label,9,"#83a8d6",bold=True)
            self._text(x1+23*self.s,y+15*self.s,value,11,TXT,
                       width=ww-48*self.s)
        bar_y=y2-47*self.s
        if kind=="Audio":
            gap=9*self.s
            cell=(ww-48*self.s-2*gap)/3
            for i,(label,delta) in enumerate((("- VOL",-5),("SILENCIO",0),("+ VOL",+5))):
                x=x1+24*self.s+i*(cell+gap)
                self._button(x,bar_y,x+cell,bar_y+34*self.s,
                             label,lambda d=delta:self._audio_action(d),size=9)
        elif kind=="Energia":
            cell=(ww-55*self.s)/2
            self._button(x1+20*self.s,bar_y,x1+20*self.s+cell,bar_y+33*self.s,
                         "SALIR DE PYRION",self.destroy,size=9,accent=PURPLE)
            self._button(x2-20*self.s-cell,bar_y,x2-20*self.s,bar_y+33*self.s,
                         "APAGAR LINUX",lambda:self._show_detail("Confirmar apagado"),
                         size=9,accent=AMBER)
        elif kind=="Confirmar apagado":
            cell=(ww-55*self.s)/2
            self._button(x1+20*self.s,bar_y,x1+20*self.s+cell,bar_y+33*self.s,
                         "CANCELAR",lambda:self._show_detail("Energia"),size=9)
            self._button(x2-20*self.s-cell,bar_y,x2-20*self.s,bar_y+33*self.s,
                         "CONFIRMAR",self._poweroff,size=9,accent=AMBER)
        else:
            self._button(x1+ww*.25,bar_y,x1+ww*.75,bar_y+33*self.s,
                         "VOLVER AL ESCRITORIO",self._close_detail,size=9)

    def _draw(self):
        self.render_job=None
        if not self.winfo_exists():
            return
        self.w=max(1,self.canvas.winfo_width())
        self.h=max(1,self.canvas.winfo_height())
        if self.w < 250 or self.h < 260:
            return
        self.s=max(.69,min(1.3,min(self.w/1320,self.h/720)))
        compact_now=self.w<1010 or self.h<580
        if compact_now and not self.compact and self.left_open and self.right_open:
            self.right_open=False
        self.compact=compact_now
        self.hit_seq=0
        self.canvas.delete("all")
        self._background()
        self._draw_orb()
        self._left_panel()
        self._right_panel()
        self._core_menu()
        self._detail_overlay()
        self._text(self.w/2,self.h-13*self.s,
                   f"P Y R I O N   O S     /     {APP_VERSION}",8,
                   "#526b9a",anchor="center")
        self.has_been_drawn=True

    def _canvas_background_click(self,event):
        try:
            current=self.canvas.find_withtag("current")
            if current:
                tags=self.canvas.gettags(current[0])
                if any(t.startswith(("tap_","app_","orb")) for t in tags):
                    return
            if self.detail:
                self._close_detail()
            elif self.core_open:
                self._close_core()
        except tk.TclError:
            pass

    def _escape(self,_event=None):
        if self.detail:
            self._close_detail()
        elif self.core_open:
            self._close_core()

    def _select_category(self,category):
        self.category=category
        self.page=0
        self._schedule_draw()

    def _page_shift(self,step):
        if self.compact:
            columns=1
        else:
            columns=2
        rows=2 if self.h<590 else 3
        count=max(1,rows*columns)
        pages=max(1,math.ceil(len(self._filtered_apps())/count))
        self.page=(self.page+step)%pages
        self._schedule_draw()

    def _wheel_apps(self,event):
        if event.x < self.w*.39:
            self._page_shift(-1 if event.delta>0 else 1)

    def _toggle_panel(self,which):
        if which=="left":
            self.left_open=not self.left_open
            if self.compact and self.left_open:
                self.right_open=False
        else:
            self.right_open=not self.right_open
            if self.compact and self.right_open:
                self.left_open=False
        self._schedule_draw()

    def _hide_both(self):
        if self.left_open or self.right_open:
            self.left_open=False
            self.right_open=False
        else:
            self.left_open=True
            self.right_open=not self.compact
        self._schedule_draw()

    def _toggle_core(self):
        self.core_open=not self.core_open
        self.detail=None
        self._schedule_draw()

    def _close_core(self):
        self.core_open=False
        self._schedule_draw()

    def _open_apps(self):
        self.left_open=True
        if self.compact:
            self.right_open=False
        self.category="Todas"
        self.page=0
        self.core_open=False
        self._schedule_draw()

    def _show_detail(self,name):
        self.detail=name
        self.core_open=False
        self._schedule_draw()

    def _close_detail(self):
        self.detail=None
        self._schedule_draw()

    def _notify(self,message,source="PYRION"):
        self.notifications.append((str(message),source))
        self.notifications=self.notifications[-12:]
        self._schedule_draw()

    def _start_program(self,label,candidates):
        for cmd in candidates:
            command=cmd[0]
            location=shutil.which(command) if not os.path.isabs(command) else (
                command if Path(command).is_file() else None)
            if not location:
                continue
            try:
                proc=subprocess.Popen(
                    [location,*cmd[1:]],cwd=str(Path.home()),
                    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self.sessions.append((label,proc))
                self._notify(f"{label} iniciado","Aplicaciones")
                return True
            except OSError as exc:
                _error_log(f"No se pudo iniciar {label}: {exc}")
        self._notify(f"{label}: aplicacion no disponible","Aplicaciones")
        return False

    def launch(self,label):
        self.core_open=False
        if label=="Explorador":
            if os.name=="nt":
                self._start_program(label,[["explorer.exe",str(Path.home())]])
            else:
                self._start_program(label,[[cmd,str(Path.home())] for cmd in
                    ("xdg-open","pcmanfm","thunar","nautilus","dolphin","spacefm")])
        elif label=="Consola":
            if os.name=="nt":
                self._start_program(label,[["cmd.exe"]])
            else:
                self._start_program(label,[[cmd] for cmd in
                    ("x-terminal-emulator","xterm","lxterminal","xfce4-terminal","gnome-terminal")])
        elif label=="Navegador":
            if os.name=="nt":
                try:
                    import webbrowser
                    result=webbrowser.open("https://www.google.com")
                    self._notify("Navegador solicitado" if result else "No se encontro navegador")
                except Exception as exc:
                    self._notify(f"No se pudo abrir el navegador: {exc}")
            else:
                self._start_program(label,[[cmd] for cmd in
                    ("firefox","chromium","chromium-browser","brave-browser","epiphany")])
        elif label=="Editor":
            self._start_program(label,[["notepad.exe"]] if os.name=="nt" else
                [[cmd] for cmd in ("mousepad","leafpad","gedit","xed","kate")])
        elif label=="Multimedia":
            self._start_program(label,[[cmd] for cmd in ("vlc","mpv","totem","smplayer")])
        elif label in ("Monitor","Configuracion"):
            self._show_detail("Sistema")
        elif label=="Red":
            self._show_detail("Red")
        else:
            self._show_detail("Acerca de")

    def _audio_action(self,change):
        if os.name=="nt":
            self._notify("Volumen: utiliza las teclas del sistema")
            return
        if not shutil.which("amixer"):
            self._notify("Control de audio no disponible")
            return
        cmd=["amixer","set","Master",("toggle" if change==0 else
                                           f"{abs(change)}%{'+' if change>0 else '-'}")]
        try:
            result=subprocess.run(cmd,capture_output=True,text=True,timeout=4)
            self._notify("Audio actualizado" if result.returncode==0 else
                         "El dispositivo no admite esta operacion")
        except (OSError,subprocess.TimeoutExpired):
            self._notify("No se pudo ajustar el audio")

    def destroy(self):
        # Prevent orphan Tcl callbacks during repeated testing/restarts.
        for name in ("render_job", "_tick_job", "_animate_job",
                     "_lower_job", "_geom_job"):
            job=getattr(self,name,None)
            if job is not None:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
                setattr(self,name,None)
        super().destroy()

    def _poweroff(self):
        if os.name=="nt" or self.windowed:
            self._notify("Apagado disponible solo en PYRION Linux a pantalla completa")
            self._close_detail()
            return
        binary=shutil.which("poweroff") or shutil.which("systemctl")
        if not binary:
            self._notify("No hay un comando de apagado disponible")
            self._close_detail()
            return
        args=[binary] if Path(binary).name=="poweroff" else [binary,"poweroff"]
        try:
            subprocess.Popen(args,stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            self._notify("Apagado solicitado")
        except OSError:
            self._notify("No se pudo apagar el equipo")
        self._close_detail()


if __name__ == "__main__":
    if "--no-update" not in sys.argv and check_self_update():
        raise SystemExit(0)
    try:
        app=PyrionApp()
        app.mainloop()
    except Exception:
        _error_log(traceback.format_exc())
        raise
