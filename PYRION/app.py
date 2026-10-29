import base64
import json
import os
import re
import subprocess
import sys
import time
import tkinter as tk
import urllib.request
from pathlib import Path
from datetime import datetime
import math
import shutil
import socket
import webbrowser

APP_NAME = "PYRION OS"
APP_VERSION = "0.2.0"

REPO_OWNER = "mobatfb"
REPO_NAME = "archmoba-config"
REPO_RAW_ROOT = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}"
REPO_RAW_BASE = f"{REPO_RAW_ROOT}/main/PYRION"
SELF_CONFIG_URL = f"{REPO_RAW_BASE}/config.json"
SELF_CONFIG_API_URL = (
    f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/PYRION/config.json?ref=main"
)


def _version_tuple(value):
    parts = []
    for part in str(value).strip().split("."):
        match = re.match(r"(\d+)", part)
        parts.append(int(match.group(1)) if match else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def check_self_update(restart=True):
    """Busca una versión nueva de PYRION y reemplaza app.py de forma segura."""
    try:
        remote_config = None

        try:
            api_request = urllib.request.Request(
                SELF_CONFIG_API_URL,
                headers={
                    "User-Agent": f"PYRION/{APP_VERSION}",
                    "Accept": "application/vnd.github+json",
                    "Cache-Control": "no-cache",
                },
            )
            with urllib.request.urlopen(api_request, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
            encoded = str(payload.get("content", "")).replace("\n", "")
            remote_config = json.loads(
                base64.b64decode(encoded).decode("utf-8-sig")
            )
        except Exception:
            remote_config = None

        if remote_config is None:
            config_request = urllib.request.Request(
                f"{SELF_CONFIG_URL}?v={time.time_ns()}",
                headers={
                    "User-Agent": f"PYRION/{APP_VERSION}",
                    "Cache-Control": "no-cache",
                },
            )
            with urllib.request.urlopen(config_request, timeout=8) as response:
                remote_config = json.loads(response.read().decode("utf-8-sig"))

        remote_version = str(remote_config.get("version", "")).strip()
        if not remote_version:
            return False

        if _version_tuple(remote_version) <= _version_tuple(APP_VERSION):
            return False

        app_path = str(
            remote_config.get("app_path", "PYRION/app.py")
        ).strip().replace("\\", "/").lstrip("/")

        if (Path(app_path).name or "app.py").lower() != "app.py":
            raise RuntimeError("config.json no apunta a un app.py válido.")

        release_commit = str(remote_config.get("release_commit", "")).strip()
        if not re.fullmatch(r"[0-9a-fA-F]{40}", release_commit):
            raise RuntimeError("config.json no contiene un release_commit válido.")

        immutable_app_url = f"{REPO_RAW_ROOT}/{release_commit}/{app_path}"

        source = None
        last_error = None
        for attempt in range(4):
            try:
                app_request = urllib.request.Request(
                    f"{immutable_app_url}?v={time.time_ns()}",
                    headers={
                        "User-Agent": f"PYRION/{APP_VERSION}",
                        "Cache-Control": "no-cache",
                    },
                )
                with urllib.request.urlopen(app_request, timeout=15) as response:
                    source = response.read().decode("utf-8-sig")
                break
            except Exception as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(0.8)

        if source is None:
            raise RuntimeError(
                f"No se pudo descargar el release fijado: {last_error}"
            )

        version_match = re.search(
            r'''APP_VERSION\s*=\s*["']([^"']+)["']''',
            source,
        )
        downloaded_version = (
            version_match.group(1).strip() if version_match else ""
        )

        if downloaded_version != remote_version:
            raise RuntimeError(
                "Versión remota inconsistente: "
                f"config={remote_version}, "
                f"app.py={downloaded_version or 'sin versión'}"
            )

        compile(source, "PYRION/app.py", "exec")

        current_file = Path(__file__).resolve()
        temp_file = current_file.with_suffix(current_file.suffix + ".update")
        temp_file.write_text(source, encoding="utf-8")
        os.replace(temp_file, current_file)

        if restart:
            if os.name == "nt":
                subprocess.Popen(
                    [sys.executable, str(current_file), *sys.argv[1:]],
                    cwd=str(current_file.parent),
                )
                return True

            os.execv(
                sys.executable,
                [sys.executable, str(current_file), *sys.argv[1:]],
            )
            return False

        return True
    except Exception:
        return False



# PYRION OS 0.2.0 - escritorio ligero construido con Canvas/Tk.
# Sin Pillow, sin compositores externos ni dependencias de interfaz adicionales.
C_BG = "#050918"
C_TEXT = "#dbeafe"
C_MUTED = "#8399b9"
C_CYAN = "#39baff"
C_VIOLET = "#a46cff"
C_PURPLE = "#7a51f1"

APPS = [
    ("Explorador", "DIR", "Favoritos"),
    ("Consola", ">_", "Favoritos"),
    ("Navegador", "WEB", "Internet"),
    ("Editor", "TXT", "Herramientas"),
    ("Multimedia", "PLAY", "Herramientas"),
    ("Monitor", "CPU", "Sistema"),
    ("Ajustes", "SET", "Sistema"),
    ("Red", "NET", "Sistema"),
    ("Acerca de", "OS", "Sistema"),
]
CATEGORIES = ("Favoritos", "Todas", "Sistema", "Herramientas", "Internet")


def _mix(a, b, t):
    t = max(0.0, min(1.0, t))
    a = a.lstrip("#")
    b = b.lstrip("#")
    x = [int(a[i:i + 2], 16) for i in (0, 2, 4)]
    y = [int(b[i:i + 2], 16) for i in (0, 2, 4)]
    v = [int(x[i] * (1 - t) + y[i] * t) for i in range(3)]
    return "#%02x%02x%02x" % tuple(v)


def _disk_state():
    try:
        total, used, unused = shutil.disk_usage("/")
        return round(used * 100 / max(total, 1)), used, total
    except (OSError, ValueError):
        return 0, 0, 0


def _mem_state():
    try:
        raw = Path("/proc/meminfo").read_text(encoding="ascii", errors="ignore")
        values = {}
        for line in raw.splitlines():
            if ":" in line:
                key, rest = line.split(":", 1)
                values[key] = int(rest.strip().split()[0])
        total = values.get("MemTotal", 0)
        free = values.get("MemAvailable", values.get("MemFree", 0))
        if total:
            return round(100 * (total - free) / total), total // 1024
    except (OSError, ValueError, IndexError):
        pass
    if os.name == "nt":
        try:
            import ctypes
            class MemInfo(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            info = MemInfo()
            info.dwLength = ctypes.sizeof(MemInfo)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(info)):
                return info.dwMemoryLoad, round(info.ullTotalPhys / (1024 ** 2))
        except Exception:
            pass
    return None, 0


def _cpu_sample():
    try:
        values = Path("/proc/stat").read_text(encoding="ascii").splitlines()[0].split()
        numbers = [int(v) for v in values[1:]]
        return sum(numbers), numbers[3] + (numbers[4] if len(numbers) > 4 else 0)
    except (OSError, ValueError, IndexError):
        return None


class PyrionApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.configure(bg=C_BG)
        self.windowed = "--windowed" in sys.argv or os.environ.get("PYRION_WINDOWED") == "1"
        self.left_open = True
        self.right_open = True
        self.core_open = False
        self.detail = None
        self.category = "Favoritos"
        self.status = "Sistema preparado"
        self.status_until = 0.0
        self.sessions = []
        self.cpu_prev = _cpu_sample()
        self.cpu_percent = None
        self.ram_percent = None
        self.ram_total = 0
        self.disk_percent = 0
        self.disk_used = 0
        self.disk_total = 0
        self.net_up = False
        self.pulse_phase = 0.0
        self.render_job = None
        self.last_render_w = 0
        self.last_render_h = 0

        # La ventana es el escritorio: permanece detrás de programas externos.
        self._force_fullscreen()

        self.canvas = tk.Canvas(
            self, bg=C_BG, bd=0, highlightthickness=0, relief="flat"
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._schedule_render)
        self.bind("<Escape>", self._escape)
        self.bind("<F11>", self._toggle_windowed)
        self.bind("<Control-Alt-t>", lambda e: self.launch("Consola"))
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self.search_var = tk.StringVar()
        self.search = tk.Entry(
            self.canvas, textvariable=self.search_var, bg="#0b1a32",
            fg=C_TEXT, insertbackground=C_TEXT, selectbackground="#275483",
            relief="flat", bd=0, font=("DejaVu Sans", 10),
            highlightthickness=1, highlightbackground="#23406c",
            highlightcolor="#48a7fa"
        )
        self.search.bind("<KeyRelease>", lambda e: self._schedule_render())
        self.search.bind("<Return>", lambda e: self._launch_first_search())
        self.after(180, self._draw)
        self.after(1100, self._keep_in_background)
        self.after(1000, self._tick)
        self.after(150, self._pulse)

    def _force_fullscreen(self):
        self.update_idletasks()
        if self.windowed:
            self.geometry("1260x750")
            self.minsize(760, 480)
            return
        if os.name == "nt":
            self.attributes("-fullscreen", True)
            return
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.overrideredirect(True)
        self.geometry(f"{sw}x{sh}+0+0")
        try:
            self.attributes("-topmost", False)
        except tk.TclError:
            pass
        self.after(100, lambda: self.geometry(
            f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0"
        ))

    def _toggle_windowed(self, _event=None):
        # Útil para probar PYRION en Windows/Linux sin perder acceso al escritorio.
        if os.name != "nt" and not self.windowed:
            self.overrideredirect(False)
        if os.name == "nt":
            self.attributes("-fullscreen", False)
        self.windowed = True
        self.geometry("1260x750")
        self._schedule_render()

    def _keep_in_background(self):
        try:
            if not self.windowed:
                self.attributes("-topmost", False)
                self.lower()
            self.after(1200, self._keep_in_background)
        except tk.TclError:
            pass

    def _escape(self, _event=None):
        if self.detail:
            self.detail = None
        elif self.core_open:
            self.core_open = False
        else:
            return
        self._schedule_render()

    def _schedule_render(self, _event=None):
        if self.render_job is not None:
            try:
                self.after_cancel(self.render_job)
            except tk.TclError:
                pass
        self.render_job = self.after(85, self._draw)

    def _scaled(self, value):
        return max(0.72, min(1.24, value))

    def _font(self, size, bold=False):
        return ("DejaVu Sans", max(8, round(size * self.s)), "bold" if bold else "normal")

    def _text(self, x, y, value, size=12, fill=C_TEXT, anchor="nw", bold=False, tag=None, width=None):
        kw = {}
        if tag:
            kw["tags"] = (tag,)
        if width:
            kw["width"] = width
        return self.canvas.create_text(
            x, y, text=str(value), font=self._font(size, bold),
            fill=fill, anchor=anchor, **kw
        )

    def _rect(self, x1, y1, x2, y2, fill, outline="", r=0, tag=None, width=1):
        kw = {"tags": (tag,)} if tag else {}
        if r <= 0:
            return self.canvas.create_rectangle(
                x1, y1, x2, y2, fill=fill, outline=outline, width=width, **kw
            )
        r = min(r, (x2-x1)/2, (y2-y1)/2)
        pts = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r,
               x2,y2-r, x2,y2, x2-r,y2, x1+r,y2, x1,y2,
               x1,y2-r, x1,y1+r, x1,y1]
        return self.canvas.create_polygon(
            pts, fill=fill, outline=outline, width=width, smooth=True, **kw
        )

    def _hit(self, tag, func):
        self.canvas.tag_bind(tag, "<Button-1>", lambda e: func())
        self.canvas.tag_bind(tag, "<Enter>", lambda e: self.canvas.configure(cursor="hand2"))
        self.canvas.tag_bind(tag, "<Leave>", lambda e: self.canvas.configure(cursor=""))

    def _background(self):
        c = self.canvas
        # Fondo nocturno ambiental dibujado nativamente (sin decodificadores).
        bands = 72
        for i in range(bands):
            t = i / (bands - 1)
            color = _mix("#050918", "#0a1532", t * 0.70)
            y0 = self.h * i / bands
            y1 = self.h * (i+1) / bands + 1
            c.create_rectangle(0, y0, self.w, y1, fill=color, outline="")
        # Luz central y reflejos de suelo con geometría de bajo coste.
        cx, cy = self.w/2, self.h*.72
        for j in range(35, 0, -1):
            rx = self.w * (.05 + j*.0055)
            ry = self.h * (.009 + j*.00125)
            glow = _mix("#071229", "#15336c", 1-j/35)
            c.create_oval(cx-rx,cy-ry,cx+rx,cy+ry,outline=glow,width=1)
        for i in range(24):
            x = (i * 421 + 117) % max(self.w,1)
            y = ((i * 169 + 37) % max(int(self.h*.6),1))
            rad = 1 + (i % 3 == 0)
            c.create_oval(x-rad,y-rad,x+rad,y+rad,fill="#17335b",outline="")
        c.create_line(self.w*.22,self.h*.92,self.w*.78,self.h*.92,fill="#122c61",width=2)

    def _panel_outline(self, side):
        c = self.canvas
        if side == "left":
            points = [
                self.w*.026,self.h*.11, self.w*.365,self.h*.255,
                self.w*.365,self.h*.835, self.w*.026,self.h*.91
            ]
            glow = C_VIOLET
            inner = "#32419b"
        else:
            points = [
                self.w*.635,self.h*.255, self.w*.974,self.h*.11,
                self.w*.974,self.h*.91, self.w*.635,self.h*.835
            ]
            glow = C_CYAN
            inner = "#276db3"
        c.create_polygon(points,fill="#09142c",outline=inner,width=max(2,self.s*3))
        c.create_polygon(points,fill="",outline=glow,width=max(1,self.s*1.4))
        if side == "left":
            c.create_line(self.w*.028,self.h*.12,self.w*.028,self.h*.89,fill="#6966dd",width=3)
        else:
            c.create_line(self.w*.972,self.h*.12,self.w*.972,self.h*.89,fill="#47b7ff",width=3)

    def _button(self, x1,y1,x2,y2,label,action,fill="#10223f",edge="#21416e",size=11,fg=C_TEXT):
        tag = "hit_" + str(self.hit_counter)
        self.hit_counter += 1
        self._rect(x1,y1,x2,y2,fill,edge,r=8*self.s,tag=tag)
        self._text((x1+x2)/2,(y1+y2)/2,label,size,fg,anchor="center",tag=tag)
        self._hit(tag,action)

    def _left_panel(self):
        if not self.left_open:
            self.search.place_forget()
            self._button(5,self.h*.36,42*self.s,self.h*.64,"APP\n›",
                         lambda: self._toggle_panel("left"),"#152450","#8560ec",12)
            return
        self._panel_outline("left")
        x0=self.w*.066
        outer_right=self.w*.365
        self._text(x0,self.h*.20,"◈  PYRION OS",20,C_CYAN,bold=True)
        self._text(x0,self.h*.255,"APLICACIONES",10,C_MUTED,bold=True)
        search_x=self.w*.103
        search_y=self.h*.295
        search_w=max(96,self.w*.244)
        self.search.place(x=round(search_x),y=round(search_y),
                          width=round(search_w),height=max(22,round(29*self.s)))
        self.search.lift()

        self._button(self.w*.337,self.h*.286,self.w*.36,self.h*.333,"‹",
                     lambda: self._toggle_panel("left"),"#14213e","#5742ac",12)
        start_y=self.h*.365
        nav_x=x0
        nav_w=self.w*.105
        for i, category in enumerate(CATEGORIES):
            y=start_y + i*self.h*.086
            selected=self.category == category
            self._button(nav_x,y,nav_x+nav_w,y+max(25,34*self.s),
                         category,
                         lambda cat=category:self._category(cat),
                         "#303d78" if selected else "#0d1c37",
                         "#7268d1" if selected else "#183960",
                         10,"#dfeaff" if selected else "#a9c1e8")
        query=self.search_var.get().strip().lower()
        filtered=[item for item in APPS if
                  (self.category == "Todas" or
                   (self.category == "Favoritos" and item[0] in
                    ("Explorador","Consola","Navegador","Editor","Monitor","Ajustes")) or
                   item[2] == self.category)
                  and (query in item[0].lower() or query in item[1].lower())]
        grid_x=self.w*.18
        grid_right=outer_right-self.w*.011
        count=3 if self.w >= 1150 else 2
        gap=6*self.s
        usable=grid_right-grid_x
        tile_w=(usable-gap*(count-1))/count
        start=self.h*.368
        step=self.h*.145 if count==3 else self.h*.133
        tile_h=min(108*self.s,self.h*.129)
        for i,(label,icon,group) in enumerate(filtered[:9]):
            row,col=divmod(i,count)
            xx=grid_x+col*(tile_w+gap)
            yy=start+row*step
            if yy+tile_h>self.h*.83:
                break
            tag="app_" + str(i)
            self._rect(xx,yy,xx+tile_w,yy+tile_h,"#0e2043","#31518d",r=8*self.s,tag=tag)
            self._text(xx+tile_w/2,yy+tile_h*.36,icon,18,C_CYAN,anchor="center",bold=True,tag=tag)
            self._text(xx+tile_w/2,yy+tile_h*.75,label,9,"#cbdcfb",anchor="center",tag=tag)
            self._hit(tag,lambda n=label:self.launch(n))
        if not filtered:
            self._text(grid_x+5,start+20,"Sin resultados",10,C_MUTED)

    def _gauge(self,cx,cy,r,percent,label,color):
        p = max(0,min(100,percent or 0))
        self.canvas.create_oval(cx-r,cy-r,cx+r,cy+r,outline="#1a395d",width=6*self.s)
        self.canvas.create_arc(cx-r,cy-r,cx+r,cy+r,start=90,extent=-p*3.6,
                               style="arc",outline=color,width=6*self.s)
        self._text(cx,cy,f"{p}%" if percent is not None else "—",12,
                   C_TEXT,anchor="center",bold=True)
        self._text(cx,cy+r+11*self.s,label,10,C_MUTED,anchor="center")

    def _right_panel(self):
        if not self.right_open:
            self._button(self.w-43*self.s,self.h*.36,self.w-5,self.h*.64,
                         "‹\nSYS",lambda:self._toggle_panel("right"),
                         "#122d56","#3287d8",12)
            return
        self._panel_outline("right")
        x=self.w*.674
        self._text(x,self.h*.195,datetime.now().strftime("%H:%M"),
                   28,"#e1f3ff",bold=True)
        self._text(x,self.h*.257,datetime.now().strftime("%d/%m/%Y"),
                   11,C_MUTED)
        self._button(self.w*.64,self.h*.286,self.w*.664,self.h*.333,"›",
                     lambda:self._toggle_panel("right"),"#102c4d","#2b71ad",12)
        self._rect(self.w*.665,self.h*.318,self.w*.949,self.h*.47,
                   "#0b1c3b","#254e86",r=9*self.s)
        g_y=self.h*.389
        cols=(.726,.81,.894)
        for cx,pc,name,clr in zip(cols,
                                  (self.cpu_percent,self.ram_percent,self.disk_percent),
                                  ("CPU","RAM","DISCO"),
                                  ("#3fbcff","#8b8aff","#55d5f2")):
            self._gauge(self.w*cx,g_y,24*self.s,pc,name,clr)

        self._rect(self.w*.665,self.h*.493,self.w*.949,self.h*.69,
                   "#0b1b37","#254675",r=8*self.s)
        self._text(self.w*.68,self.h*.51,"NOTIFICACIONES",11,C_CYAN,bold=True)
        short=self.status
        if len(short)>70:
            short=short[:67]+"..."
        self._text(self.w*.68,self.h*.563,short,10,C_TEXT,width=self.w*.247)
        running=[name for name,p in self.sessions
                 if p is None or p.poll() is None]
        self._text(self.w*.68,self.h*.615,
                   f"Sesiones: {len(running)}  •  Red: {'conectada' if self.net_up else 'sin conexión'}",
                   9,C_MUTED)
        y=self.h*.725
        items=[("VENTANAS",lambda:self._toggle_panel("both")),
               ("VOLUMEN",self._toggle_volume),
               ("RED",lambda:self._show_detail("Red")),
               ("SISTEMA",lambda:self._show_detail("Sistema"))]
        start=self.w*.665
        end=self.w*.95
        gap=6*self.s
        cell=(end-start-gap*3)/4
        for i,(label,action) in enumerate(items):
            xx=start+i*(cell+gap)
            self._button(xx,y,xx+cell,y+min(self.h*.079,62*self.s),
                         label,action,"#102953","#3465a3",9,C_CYAN)

    def _orb(self):
        c=self.canvas
        cx=self.w*.5
        cy=self.h*.52
        r=min(self.h*.092,self.w*.062)
        for i in range(16,0,-1):
            radius=r+12*self.s+i*2.6*self.s
            c.create_oval(cx-radius,cy-radius,cx+radius,cy+radius,
                          outline=_mix("#071633","#202e79",1-i/16),width=1)
        # Anillos orbitales / plataforma.
        for i in range(4):
            rx=r*(1.28+i*.18)
            ry=r*(.36+i*.08)
            c.create_oval(cx-rx,cy+ry*.92,cx+rx,cy+ry*2.1,
                          outline=("#144279","#2358b0","#4768f6","#27449b")[i],
                          width=1.7*self.s)
        c.create_oval(cx-r-8,cy-r-8,cx+r+8,cy+r+8,
                      outline="#5b75fb",width=2,tag="orb_pulse")
        c.create_oval(cx-r,cy-r,cx+r,cy+r,fill="#5b48b2",outline="#8ba9fa",width=2)
        # Gradiente radial mediante discos superpuestos (sin Pillow).
        for i in range(42,0,-1):
            ratio=i/42
            rr=r*ratio*.97
            col=_mix("#aedbfc","#3f4b91",max(0,(1-ratio)*.93))
            c.create_oval(cx-rr+r*.08,cy-rr-r*.09,cx+rr+r*.08,cy+rr-r*.09,
                          fill=col,outline=col)
        c.create_arc(cx-r*1.3,cy-r*.6,cx+r*1.3,cy+r*.78,
                     start=174,extent=214,style="arc",outline="#8064ff",
                     width=2*self.s)
        self._text(cx,cy+r+38*self.s,"NÚCLEO PYRION",11,C_MUTED,anchor="center",bold=True)
        self._text(cx,cy,"●",max(10,15*self.s), "#d4eeff",anchor="center")
        tag="orb_click"
        c.create_oval(cx-r,cy-r,cx+r,cy+r,fill="",outline="",tags=(tag,))
        self._hit(tag,self._toggle_core)

    def _core_menu(self):
        if not self.core_open:
            return
        cx=self.w*.5
        y=self.h*.71
        menu_w=min(self.w*.23,300*self.s)
        self._rect(cx-menu_w/2,y-7*self.s,cx+menu_w/2,y+102*self.s,
                   "#0c1a36","#4b69be",r=10*self.s)
        self._text(cx,y+4*self.s,"CONTROL CENTRAL",11,C_CYAN,
                   anchor="n",bold=True)
        labels=[
            ("Aplicaciones",lambda:self._open_apps()),
            ("Monitor",lambda:self._show_detail("Sistema")),
            ("Acerca de",lambda:self._show_detail("Acerca de")),
            ("Ocultar",self._hide_core)
        ]
        for i,(name,action) in enumerate(labels):
            x1=cx-menu_w/2+9*self.s+(i%2)*(menu_w/2-4*self.s)
            yy=y+28*self.s+(i//2)*35*self.s
            self._button(x1,yy,x1+menu_w/2-15*self.s,yy+29*self.s,
                         name,action,"#182953","#4263a6",9)

    def _detail_overlay(self):
        if not self.detail:
            return
        cx=self.w*.5
        top=self.h*.10
        width=min(self.w*.37,430*self.s)
        height=self.h*.19
        self._rect(cx-width/2,top,cx+width/2,top+height,
                   "#0a1933","#5b7bc1",r=10*self.s)
        self._text(cx-width/2+16*self.s,top+13*self.s,
                   self.detail,14,C_CYAN,bold=True)
        if self.detail == "Red":
            try:
                content=f"Equipo: {socket.gethostname()}\nInterfaces: {', '.join(n for _,n in socket.if_nameindex())}"
            except (OSError,AttributeError):
                content="Información de interfaces no disponible."
        elif self.detail == "Sistema":
            content=(f"CPU: {self.cpu_percent if self.cpu_percent is not None else 'N/D'}%  "
                     f"RAM: {self.ram_percent if self.ram_percent is not None else 'N/D'}%  "
                     f"Disco: {self.disk_percent}%\n"
                     f"Procesadores lógicos: {os.cpu_count() or 'N/D'}  •  PYRION {APP_VERSION}")
        else:
            content=f"PYRION OS {APP_VERSION}\nEscritorio ligero e interactivo. © ARCHMOBA"
        self._text(cx-width/2+16*self.s,top+44*self.s,content,10,C_TEXT,
                   width=width-32*self.s)
        self._button(cx+width/2-40*self.s,top+8*self.s,
                     cx+width/2-10*self.s,top+33*self.s,"×",
                     lambda:self._show_detail(None),"#1c2744","#5972a2",11)

    def _draw(self):
        self.render_job=None
        if not self.winfo_exists():
            return
        self.w=max(self.canvas.winfo_width(),1)
        self.h=max(self.canvas.winfo_height(),1)
        if self.w < 100 or self.h < 100:
            return
        self.s=self._scaled(min(self.w/1280,self.h/720))
        self.hit_counter=0
        self.canvas.delete("all")
        self._background()
        self._left_panel()
        self._right_panel()
        self._orb()
        self._core_menu()
        self._detail_overlay()
        self._text(self.w*.5,self.h*.953,
                   "PYRION 2030   •   "+datetime.now().strftime("%H:%M")+"   •   v"+APP_VERSION,
                   9,"#5574a5",anchor="center")
        self.last_render_w=self.w
        self.last_render_h=self.h

    def _pulse(self):
        try:
            if self.canvas.winfo_exists() and self.w > 100:
                self.pulse_phase+=.2
                cx=self.w*.5; cy=self.h*.52
                r=min(self.h*.092,self.w*.062)
                d=6*self.s+(math.sin(self.pulse_phase)+1)*6*self.s
                self.canvas.coords("orb_pulse",cx-r-d,cy-r-d,cx+r+d,cy+r+d)
            self.after(130,self._pulse)
        except (tk.TclError,AttributeError):
            pass

    def _tick(self):
        self.ram_percent,self.ram_total=_mem_state()
        self.disk_percent,self.disk_used,self.disk_total=_disk_state()
        cpu_now=_cpu_sample()
        if cpu_now and self.cpu_prev and cpu_now[0]>self.cpu_prev[0]:
            dt=cpu_now[0]-self.cpu_prev[0]
            di=cpu_now[1]-self.cpu_prev[1]
            self.cpu_percent=max(0,min(100,round(100*(dt-di)/dt)))
        self.cpu_prev=cpu_now
        try:
            if hasattr(socket,"if_nameindex"):
                self.net_up=any(name not in ("lo","lo0") for _,name in socket.if_nameindex())
        except OSError:
            self.net_up=False
        self.sessions=[(label,p) for label,p in self.sessions if p is None or p.poll() is None][-8:]
        self._schedule_render()
        self.after(5000,self._tick)

    def _category(self,category):
        self.category=category
        self._schedule_render()

    def _toggle_panel(self,which):
        if which=="left":
            self.left_open=not self.left_open
        elif which=="right":
            self.right_open=not self.right_open
        else:
            self.left_open=not (self.left_open and self.right_open)
            self.right_open=self.left_open
        self._schedule_render()

    def _toggle_core(self):
        self.core_open=not self.core_open
        self._schedule_render()

    def _hide_core(self):
        self.core_open=False
        self._schedule_render()

    def _open_apps(self):
        self.left_open=True
        self.category="Todas"
        self.core_open=False
        self._schedule_render()

    def _show_detail(self,name):
        self.detail=name
        self.core_open=False
        self._schedule_render()

    def _launch_first_search(self):
        term=self.search_var.get().strip().lower()
        matches=[a[0] for a in APPS if term in a[0].lower()]
        if matches:
            self.launch(matches[0])

    def _notify(self,message):
        self.status=str(message)
        self._schedule_render()

    def _run_candidates(self,name,candidates):
        for cmd in candidates:
            path=shutil.which(cmd[0])
            if not path:
                continue
            try:
                proc=subprocess.Popen([path,*cmd[1:]],
                                      cwd=str(Path.home()),
                                      stdin=subprocess.DEVNULL,
                                      stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL)
                self.sessions.append((name,proc))
                self._notify(name+" iniciado")
                return
            except OSError:
                continue
        self._notify(name+": no hay una aplicación compatible instalada")

    def _toggle_volume(self):
        if os.name=="nt":
            self._notify("Control de volumen: utilice las teclas del sistema")
            return
        program=shutil.which("amixer")
        if not program:
            self._notify("Audio: amixer no está disponible")
            return
        try:
            proc=subprocess.run([program,"set","Master","toggle"],
                                timeout=3,capture_output=True,text=True)
            self._notify("Volumen: alternado" if proc.returncode==0
                         else "No se pudo cambiar el volumen")
        except (OSError,subprocess.TimeoutExpired):
            self._notify("No se pudo acceder al mezclador de audio")

    def launch(self,name):
        if name=="Explorador":
            if os.name=="nt":
                self._run_candidates(name,[["explorer.exe",str(Path.home())]])
            else:
                self._run_candidates(name,[[c,str(Path.home())] for c in
                     ("xdg-open","pcmanfm","thunar","nautilus","dolphin","spacefm")])
        elif name=="Consola":
            path=Path("/opt/minilinux/floating_console.py")
            if path.is_file() and os.name!="nt":
                self._run_candidates(name,[[sys.executable,str(path)]])
            else:
                self._run_candidates(name,
                    [["cmd.exe"]] if os.name=="nt" else
                    [[c] for c in ("xterm","xfce4-terminal","lxterminal","konsole","gnome-terminal")])
        elif name=="Navegador":
            self._run_candidates(name,
                [["cmd.exe","/c","start","https://www.google.com"]] if os.name=="nt" else
                [[c] for c in ("firefox","chromium","chromium-browser","brave-browser","epiphany")])
        elif name=="Editor":
            self._run_candidates(name,
                [["notepad.exe"]] if os.name=="nt" else
                [[c] for c in ("mousepad","leafpad","gedit","xed","kate")])
        elif name=="Multimedia":
            self._run_candidates(name,[[c] for c in ("vlc","mpv","totem","smplayer")])
        elif name=="Monitor" or name=="Ajustes":
            self._show_detail("Sistema")
            self._notify("Monitor del sistema: indicadores actualizados")
        elif name=="Red":
            self._show_detail("Red")
        else:
            self._show_detail("Acerca de")


if __name__ == "__main__":
    if check_self_update():
        raise SystemExit(0)

    try:
        app = PyrionApp()
        app.mainloop()
    except Exception:
        import traceback
        try:
            log = Path.home() / "pyrion_error.log"
            log.write_text(traceback.format_exc(), encoding="utf-8")
            print("PYRION: fallo al iniciar, revise", log, file=sys.stderr)
        except Exception:
            traceback.print_exc()
        raise
