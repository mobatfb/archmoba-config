"""PYRION OS 0.4.0 - standalone PYRION 3D Engine.

Mesh geometry, perspective projection, and Tk software renderer.
Previous desktop preserved under PYRION/release/v0.3.0.
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
from dataclasses import dataclass
import traceback
import urllib.request
import zlib
from datetime import datetime
from pathlib import Path

APP_NAME = "PYRION OS"
APP_VERSION = "0.4.0"
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



"""3D mesh primitives for PYRION Engine - Python standard library only."""


@dataclass(frozen=True)
class Face:
    indices: tuple
    longitude: float
    latitude: float
    band: int


class SphereMesh:
    """UV sphere with a single north/south pole and manifold triangle topology."""

    def __init__(self, rings=24, segments=48, radius=1.0):
        if rings < 4 or segments < 6:
            raise ValueError("Sphere needs rings>=4 and segments>=6")
        self.rings = int(rings)
        self.segments = int(segments)
        self.radius = float(radius)
        self.vertices = [(0.0, self.radius, 0.0)]
        self.faces = []
        # latitude angles are measured down from the north pole.
        for i in range(1, self.rings):
            theta = math.pi * i / self.rings
            y = self.radius * math.cos(theta)
            radial = self.radius * math.sin(theta)
            for j in range(self.segments):
                longitude = 2.0 * math.pi * j / self.segments
                self.vertices.append((
                    radial * math.cos(longitude), y,
                    radial * math.sin(longitude)
                ))
        self.vertices.append((0.0, -self.radius, 0.0))
        bottom_index = len(self.vertices) - 1

        # upper cap, middle quads, lower cap.
        for j in range(self.segments):
            nxt = (j + 1) % self.segments
            longitude = 2.0 * math.pi * (j + 0.5) / self.segments
            self.faces.append(Face((0, 1 + j, 1 + nxt), longitude,
                                   math.pi / self.rings * 0.55, 0))
        for i in range(1, self.rings - 1):
            for j in range(self.segments):
                nxt = (j + 1) % self.segments
                a = 1 + (i - 1) * self.segments + j
                b = 1 + (i - 1) * self.segments + nxt
                c = 1 + i * self.segments + j
                d = 1 + i * self.segments + nxt
                lon = 2.0 * math.pi * (j + 0.5) / self.segments
                lat = math.pi * (i + 0.5) / self.rings
                self.faces.append(Face((a, c, d), lon, lat, i))
                self.faces.append(Face((a, d, b), lon, lat, i))
        for j in range(self.segments):
            nxt = (j + 1) % self.segments
            a = 1 + (self.rings - 2) * self.segments + j
            b = 1 + (self.rings - 2) * self.segments + nxt
            lon = 2.0 * math.pi * (j + 0.5) / self.segments
            self.faces.append(Face((a, bottom_index, b), lon,
                                   math.pi * (self.rings - 0.55) / self.rings,
                                   self.rings - 1))

    @property
    def vertex_count(self):
        return len(self.vertices)

    @property
    def triangle_count(self):
        return len(self.faces)

    def meridian(self, longitude, steps=96):
        """3D polyline along a meridian, on the surface above the mesh."""
        rad = self.radius * 1.009
        return [(
            rad * math.sin(math.pi * i / steps) * math.cos(longitude),
            rad * math.cos(math.pi * i / steps),
            rad * math.sin(math.pi * i / steps) * math.sin(longitude)
        ) for i in range(steps + 1)]

    def latitude(self, theta, steps=112):
        rad = self.radius * 1.009
        return [(
            rad * math.sin(theta) * math.cos(2 * math.pi * i / steps),
            rad * math.cos(theta),
            rad * math.sin(theta) * math.sin(2 * math.pi * i / steps)
        ) for i in range(steps + 1)]

    def signature(self):
        return (self.rings, self.segments, self.vertex_count,
                self.triangle_count)

"""Software 3D triangle projection and shading for a Tkinter canvas."""


def _unit(vector):
    x, y, z = vector
    n = math.sqrt(x * x + y * y + z * z)
    return (x / n, y / n, z / n) if n else (0.0, 0.0, 1.0)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _rgb(values):
    return "#%02x%02x%02x" % tuple(
        max(0, min(255, round(v))) for v in values
    )


class SoftwareRenderer:
    """Perspective camera + z sorted triangle meshes, without a GPU dependency."""

    def __init__(self, mesh):
        self.mesh = mesh
        self.camera_distance = 3.85
        self.rotation_y = 0.0
        self.rotation_x = -0.25
        self.zoom = 1.0
        self.wireframe = False
        self._light_a = _unit((-0.42, 0.77, 0.53))
        self._light_b = _unit((0.74, -0.29, 0.47))
        self._lines = []
        for i, phi in enumerate((0.0, 2.05, 4.09)):
            self._lines.append((mesh.meridian(phi, steps=42),
                                "#456caa" if i % 2 else "#62b4ed"))
        for i, t in enumerate((0.92, 1.57, 2.23)):
            self._lines.append((mesh.latitude(t, steps=50),
                                "#305a9a" if i % 2 else "#4366a6"))
        self._material = [self._surface_pattern(f.longitude, f.latitude)
                          for f in mesh.faces]
        self._decorative_path = [
            (1.013 * math.sin(t) * math.cos(0.92 + 0.45 * math.sin(t * 3.5)),
             1.013 * math.cos(t),
             1.013 * math.sin(t) * math.sin(0.92 + 0.45 * math.sin(t * 3.5)))
            for t in (math.pi * i / 76 for i in range(77))
        ]

    def _rotate(self, point):
        x, y, z = point
        cy, sy = math.cos(self.rotation_y), math.sin(self.rotation_y)
        x1, z1 = x * cy + z * sy, -x * sy + z * cy
        cx, sx = math.cos(self.rotation_x), math.sin(self.rotation_x)
        return (x1, y * cx - z1 * sx, y * sx + z1 * cx)

    def _project(self, p, cx, cy, focal):
        depth = max(0.4, self.camera_distance - p[2])
        scale = focal / depth
        return (cx + p[0] * scale, cy - p[1] * scale)

    @staticmethod
    def _surface_pattern(lon, lat):
        # Procedural material follows the 3D vertices during rotation.
        veining = math.sin(3.8 * lon + math.sin(lat * 3.6) * 1.8)
        veining += 0.38 * math.cos(7.4 * lon - lat * 4.7)
        return max(0.0, min(1.0, (veining + 0.12) * 0.60))

    def _color(self, normal, accent, front):
        a = max(0.0, _dot(normal, self._light_a))
        b = max(0.0, _dot(normal, self._light_b))
        edge = (1.0 - front) ** 1.9
        spec = max(0.0, _dot(normal, _unit((-0.13, 0.62, 0.78)))) ** 24
        return _rgb((
            17 + 53 * a + 14 * b + 14 * accent + 56 * spec + 24 * edge,
            30 + 80 * a + 21 * b + 19 * accent + 73 * spec + 19 * edge,
            69 + 112 * a + 71 * b + 46 * accent + 48 * spec + 36 * edge,
        ))

    def _visible_curve(self, canvas, points, color, cx, cy, focal,
                       width=1.0):
        old = None
        for point in points:
            v = self._rotate(point)
            # Front hemisphere test. Mesh surface is radius 1.
            active = v[2] > -0.055
            current = self._project(v, cx, cy, focal) if active else None
            if current and old:
                canvas.create_line(*old, *current, fill=color, width=width)
            old = current

    def draw(self, canvas, cx, cy, diameter, draw_graticules=True):
        """Draw 3D mesh centered at cx,cy; returns visible face count."""
        focal = max(50, diameter * self.camera_distance * 0.47 * self.zoom)
        rotated = [self._rotate(p) for p in self.mesh.vertices]
        projected = [self._project(p, cx, cy, focal) for p in rotated]
        visible_faces = []

        for face, accent in zip(self.mesh.faces, self._material):
            i, j, k = face.indices
            a, b, c = rotated[i], rotated[j], rotated[k]
            center = ((a[0] + b[0] + c[0]) / 3,
                      (a[1] + b[1] + c[1]) / 3,
                      (a[2] + b[2] + c[2]) / 3)
            normal = _unit(center)
            towards_camera = _unit((-
                center[0], -center[1], self.camera_distance - center[2]))
            front = _dot(normal, towards_camera)
            if front <= 0.02:
                continue
            pts = (*projected[i], *projected[j], *projected[k])
            color = self._color(normal, accent, front)
            visible_faces.append((center[2], pts, color))

        visible_faces.sort(key=lambda row: row[0])
        for _, pts, color in visible_faces:
            canvas.create_polygon(*pts, fill=color,
                                  outline="#22426e" if self.wireframe else color,
                                  width=0.7 if self.wireframe else 0.2)
        if draw_graticules:
            for points, color in self._lines:
                self._visible_curve(canvas, points, color, cx, cy, focal,
                                    width=1.15 if self.wireframe else 0.85)
            self._visible_curve(canvas, self._decorative_path,
                                "#8b9cff", cx, cy, focal, width=1.7)
        return len(visible_faces)

"""PYRION 3D Engine: infinitely rotating centered 3D sphere (Tk software)."""

ENGINE_VERSION = "0.1.0"
DESKTOP_VERSION = "0.4.0"


class Pyrion3DApp(tk.Tk):
    """Self-contained, no external GUI dependencies; full-screen desktop scene."""

    def __init__(self):
        super().__init__()
        self.title("PYRION OS - 3D ENGINE")
        self.configure(bg="#050a17")
        self.windowed = (
            "--windowed" in sys.argv or os.environ.get("PYRION_WINDOWED") == "1"
        )
        self._setup_window()

        self.canvas = tk.Canvas(self, bg="#050a17", highlightthickness=0,
                                bd=0, relief="flat", takefocus=1)
        self.canvas.pack(fill="both", expand=True)
        self.mesh = SphereMesh(rings=17, segments=34)
        self.renderer = SoftwareRenderer(self.mesh)
        self.renderer.rotation_y = 0.53
        self.renderer.rotation_x = -0.30
        self.spin_rate = 0.78
        self.base_pitch = -0.30
        self.running = True
        self.show_grid = True
        self.show_info = True
        self.frames = 0
        self.fps = 0.0
        self.visible_triangles = 0
        self.last_time = time.perf_counter()
        self.drag_start = None
        self.angle_delta = 0.0
        self.pending_frame = None
        self._width = 1
        self._height = 1
        self._orb_radius = 1

        self.bind("<space>", lambda _e: self.toggle_animation())
        self.bind("<KeyPress-w>", lambda _e: self.toggle_grid())
        self.bind("<KeyPress-W>", lambda _e: self.toggle_grid())
        self.bind("<KeyPress-i>", lambda _e: self.toggle_info())
        self.bind("<KeyPress-I>", lambda _e: self.toggle_info())
        self.bind("<Left>", lambda _e: self._speed(-0.18))
        self.bind("<Right>", lambda _e: self._speed(+0.18))
        self.bind("<plus>", lambda _e: self._zoom(+0.10))
        self.bind("<minus>", lambda _e: self._zoom(-0.10))
        self.bind("<F11>", self._switch_to_window)
        self.bind("<Control-q>", lambda _e: self.close())
        self.bind("<Escape>", lambda _e: self._escape())
        self.canvas.bind("<ButtonPress-1>", self._mouse_press, add="+")
        self.canvas.bind("<B1-Motion>", self._mouse_move, add="+")
        self.canvas.bind("<ButtonRelease-1>", self._mouse_release, add="+")
        self.canvas.bind("<MouseWheel>", self._scroll)
        self.canvas.bind("<Button-4>", lambda _e: self._zoom(+0.10))
        self.canvas.bind("<Button-5>", lambda _e: self._zoom(-0.10))
        self.canvas.bind("<Configure>", lambda _e: self._request_frame())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(80, self._frame)
        self.after(1000, self._keep_as_desktop)

    def _setup_window(self):
        self.update_idletasks()
        if self.windowed:
            self.geometry("1100x720")
            self.minsize(660, 440)
        elif os.name == "nt":
            self.attributes("-fullscreen", True)
        else:
            # Xorg minimal boot: no requirement for a window manager.
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            self.overrideredirect(True)
            self.geometry(f"{sw}x{sh}+0+0")
            self.after(180, self._repair_fullscreen_geometry)

    def _repair_fullscreen_geometry(self):
        if not self.windowed:
            self.geometry(
                f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0"
            )

    def _keep_as_desktop(self):
        try:
            if not self.windowed:
                self.attributes("-topmost", False)
                self.lower()
            self.after(1250, self._keep_as_desktop)
        except tk.TclError:
            return

    def _switch_to_window(self, _event=None):
        if self.windowed:
            return
        if os.name == "nt":
            self.attributes("-fullscreen", False)
        else:
            self.overrideredirect(False)
        self.windowed = True
        self.geometry("1100x720")
        self._request_frame()

    def close(self):
        if self.pending_frame is not None:
            try:
                self.after_cancel(self.pending_frame)
            except tk.TclError:
                pass
        self.destroy()

    def _escape(self):
        if self.show_info:
            self.show_info = False
            self._request_frame()

    def toggle_animation(self):
        self.running = not self.running
        self._request_frame()

    def toggle_grid(self):
        self.show_grid = not self.show_grid
        self.renderer.wireframe = not self.renderer.wireframe
        self.show_grid = True
        self._request_frame()

    def toggle_info(self):
        self.show_info = not self.show_info
        self._request_frame()

    def _speed(self, amount):
        self.spin_rate = max(0.15, min(3.5, self.spin_rate + amount))
        self._request_frame()

    def _zoom(self, amount):
        self.renderer.zoom = max(0.55, min(1.42, self.renderer.zoom + amount))
        self._request_frame()

    def _mouse_press(self, event):
        cx, cy = self._width * 0.5, self._height * 0.475
        if (event.x - cx)**2 + (event.y - cy)**2 < self._orb_radius ** 2:
            self.drag_start = (event.x, event.y)

    def _mouse_move(self, event):
        if self.drag_start is None:
            return
        dx = event.x - self.drag_start[0]
        dy = event.y - self.drag_start[1]
        self.renderer.rotation_y += dx * 0.007
        self.base_pitch = max(-1.35, min(1.35,
                              self.base_pitch - dy * 0.007))
        self.drag_start = (event.x, event.y)
        self._request_frame()

    def _mouse_release(self, _event):
        self.drag_start = None

    def _scroll(self, event):
        self._zoom(0.08 if event.delta > 0 else -0.08)

    def _request_frame(self):
        if self.pending_frame is None:
            self.pending_frame = self.after_idle(self._draw)

    def _color(self, r, g, b):
        return "#%02x%02x%02x" % (int(r), int(g), int(b))

    def _background(self, width, height):
        c = self.canvas
        c.create_rectangle(0, 0, width, height, fill="#050917", outline="")
        # Thin atmospheric bands for depth, drawn without external images.
        for i in range(18):
            y1 = int(i * height / 18)
            y2 = int((i + 1) * height / 18) + 1
            c.create_rectangle(0, y1, width, y2,
                               fill=self._color(5 + i//5, 9 + i//3,
                                                23 + i//2), outline="")
        for i in range(40):
            x = ((i * 7907 + 135) % 10007) / 10007.0 * width
            y = ((i * 2017 + 43) % 10009) / 10009.0 * height * .75
            bright = "#31527f" if i % 7 == 0 else "#192d4d"
            rr = 1.3 if i % 9 == 0 else 0.65
            c.create_oval(x-rr, y-rr, x+rr, y+rr, fill=bright, outline="")
        cx, cy = width*.5, height*.475
        # Discrete atmosphere, behind the 3D geometry.
        glow_size = min(height*.56,width*.46)*.48
        for i in range(7, 0, -1):
            r = glow_size * (1.02 + i*.019)
            col = self._color(8 + i//2, 16 + i, 38 + i*2)
            c.create_oval(cx-r,cy-r,cx+r,cy+r,outline=col,width=1)
        y = height*.715
        for i in range(4):
            r = width*(.055 + i*.028)
            c.create_oval(cx-r,y-8-i*3,cx+r,y+8+i*3,
                          outline=self._color(10,32+i*2,66+i*5),width=1)
        c.create_line(width*.12,height*.925,width*.88,height*.925,
                      fill="#132a4b",width=1)

    def _label(self, x, y, txt, size=11, color="#cee4ff",
               anchor="nw", bold=False, tag=None):
        size = max(8, int(size * self.scale))
        return self.canvas.create_text(
            x,y,text=txt,fill=color,anchor=anchor,
            font=("DejaVu Sans",size,"bold" if bold else "normal"),
            tags=(tag,) if tag else ()
        )

    def _button(self, x1, y1, x2, y2, title, action, selected=False):
        tag = "ui_" + str(self._button_id)
        self._button_id += 1
        self.canvas.create_rectangle(
            x1, y1, x2, y2,
            fill="#1c315f" if selected else "#0b1930",
            outline="#6a9efb" if selected else "#294972",
            width=1,tags=(tag,)
        )
        self._label((x1+x2)/2,(y1+y2)/2,title,10,
                    "#d8ecff" if selected else "#8faed9",
                    anchor="center",bold=selected,tag=tag)
        self.canvas.tag_bind(tag,"<Button-1>",lambda _e: action())
        self.canvas.tag_bind(tag,"<Enter>",
                             lambda _e: self.canvas.configure(cursor="hand2"))
        self.canvas.tag_bind(tag,"<Leave>",
                             lambda _e: self.canvas.configure(cursor=""))

    def _hud(self, w, h):
        c = self.canvas
        s = self.scale
        pad = 27*s
        self._label(pad,24*s,"PYRION",22,"#e3f3ff",bold=True)
        self._label(pad+7*s,57*s,"3D ENGINE / 0.1.0",10,"#63baff")
        self._label(w-pad,27*s,"SCENE 01    |    UV SPHERE",10,
                    "#8ca9d3",anchor="ne",bold=True)
        c.create_line(pad,78*s,w-pad,78*s,fill="#1b3355",width=1)
        if self.show_info:
            info_x = pad
            info_y = h*.34
            self._label(info_x,info_y,"GEOMETRY",10,"#5ec5ff",bold=True)
            for i,item in enumerate((
                "Mesh    : UV Sphere",
                f"Vertices: {self.mesh.vertex_count}",
                f"Triangles: {self.mesh.triangle_count}",
                f"Visible  : {self.visible_triangles}",
                "Material: procedural",
                "Camera  : perspective",
            )):
                self._label(info_x,info_y+(26+i*25)*s,item,10,"#92acd3")
            right_x = w-pad
            self._label(right_x,info_y,"ROTATION",10,"#a987ff",
                        anchor="ne",bold=True)
            for i,item in enumerate((
                f"Y axis  {math.degrees(self.renderer.rotation_y)%360:05.1f} deg",
                f"X axis  {math.degrees(self.renderer.rotation_x):+05.1f} deg",
                f"Speed   {self.spin_rate:.2f} rad/s",
                "Loop    INFINITE" if self.running else "Loop    PAUSED",
                f"FPS     {self.fps:04.1f}",
                "Render  SOFTWARE",
            )):
                self._label(right_x,info_y+(26+i*25)*s,item,10,"#92acd3",anchor="ne")
        c.create_line(pad,h-99*s,w-pad,h-99*s,fill="#1b3355",width=1)
        self._label(w*.5,h-155*s,"PYRION CORE",14,"#b1cfff",anchor="center",bold=True)
        self._label(w*.5,h-133*s,"REAL 3D MESH  //  CONTINUOUS ROTATION",9,
                    "#638db9",anchor="center")
        self._button_id = 0
        bw = 103*s
        gap = 9*s
        labels = [
            ("PAUSAR" if self.running else "GIRAR",self.toggle_animation,not self.running),
            ("MALLA" if not self.renderer.wireframe else "SOLIDO",self.toggle_grid,self.renderer.wireframe),
            ("- VELOCIDAD",lambda: self._speed(-0.18),False),
            ("+ VELOCIDAD",lambda: self._speed(0.18),False),
            ("- ZOOM",lambda: self._zoom(-0.10),False),
            ("+ ZOOM",lambda: self._zoom(0.10),False),
            ("INFO",self.toggle_info,self.show_info),
        ]
        if w < 870:
            labels = [
                ("PAUSA" if self.running else "GIRAR",self.toggle_animation,not self.running),
                ("MALLA" if not self.renderer.wireframe else "SOLIDO",self.toggle_grid,self.renderer.wireframe),
                ("LENTO",lambda: self._speed(-0.18),False),
                ("RAPIDO",lambda: self._speed(0.18),False),
                ("INFO",self.toggle_info,self.show_info),
            ]
        total=len(labels)*bw+(len(labels)-1)*gap
        x=w*.5-total*.5
        for label,fn,selected in labels:
            self._button(x,h-74*s,x+bw,h-41*s,label,fn,selected)
            x+=bw+gap
        self._label(w*.5,h-20*s,
                    "DRAG: ROTATE  |  W: WIREFRAME  |  SPACE: PAUSE  |  F11: WINDOW",
                    9,"#527399",anchor="center")

    def _draw(self):
        self.pending_frame=None
        if not self.winfo_exists():
            return
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 100 or h < 100:
            return
        self._width,self._height = w,h
        self.scale=max(.70,min(1.3,min(w/1280,h/720)))
        self.canvas.delete("all")
        self._background(w,h)
        diameter=min(h*.55,w*.51)
        self._orb_radius=diameter*.50
        cx, cy=w*.5, h*.475
        self.visible_triangles = self.renderer.draw(
            self.canvas,cx,cy,diameter,
            draw_graticules=self.show_grid
        )
        # Subtle rim light at the contour; the main sphere remains a projected mesh.
        rim=diameter*.483 * self.renderer.zoom
        for i in range(3):
            d=i*2
            self.canvas.create_arc(cx-rim-d,cy-rim-d,cx+rim+d,cy+rim+d,
                                   start=110,extent=113,style="arc",
                                   outline=("#244a89","#2c5aa3","#397ac4")[i],width=1)
        self._hud(w,h)

    def _frame(self):
        now = time.perf_counter()
        elapsed = max(0,min(.1,now - self.last_time))
        self.last_time=now
        if self.running:
            self.renderer.rotation_y=(self.renderer.rotation_y + self.spin_rate*elapsed) % (math.pi*2)
            self.renderer.rotation_x=(self.base_pitch + math.sin(now*.30)*.045)
        if elapsed>0:
            instantaneous = 1.0/elapsed
            self.fps = .88*self.fps + .12*instantaneous if self.fps else instantaneous
        self.frames+=1
        self._draw()
        try:
            self.after(40, self._frame)
        except tk.TclError:
            pass


def run():
    app = Pyrion3DApp()
    app.mainloop()




if __name__ == "__main__":
    if "--no-update" not in sys.argv and check_self_update():
        raise SystemExit(0)
    try:
        run()
    except Exception:
        _error_log(traceback.format_exc())
        raise
