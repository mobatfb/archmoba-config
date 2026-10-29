"""PYRION OS 0.4.3 - standalone PYRION 3D Engine.

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
APP_VERSION = "0.4.3"
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

"""PYRION OS: a single infinitely rotating 3D sphere at screen center.

The desktop has no panels, labels, orbital rings or visible UI controls.
The UV-sphere geometry and software renderer are provided by PYRION Engine.
"""

ENGINE_VERSION = "0.1.0"
DESKTOP_VERSION = "0.4.3"
BACKGROUND = "#050917"



def _scene_json(relative_path):
    """Prefer local scene assets; standalone OTA can fetch missing files."""
    root = Path(__file__).resolve().parent
    engine = root if root.name == "engine3d" else root / "engine3d"
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Invalid scene path")
    local = engine / relative
    if local.is_file():
        return json.loads(local.read_text(encoding="utf-8"))
    url = REPO_RAW_BASE + "/engine3d/" + relative.as_posix()
    request = urllib.request.Request(url, headers={"User-Agent": "PYRION/0.4.3"})
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8-sig"))


def load_selected_scene():
    selection = _scene_json("scene_selected.json")
    scene_path = Path(selection["selected_scene"])
    scene = _scene_json(scene_path)
    if scene.get("format") != "pyrion.scene":
        raise ValueError("Unsupported scene format")
    objects = []
    for obj in scene.get("objects", []):
        if not obj.get("visible", True):
            continue
        model_path = (scene_path.parent / obj["model"]).as_posix()
        model = _scene_json(model_path)
        if model.get("format") != "pyrion.mesh" or model.get("primitive") != "uv_sphere":
            raise ValueError("Unsupported model: " + model_path)
        params = model["parameters"]
        scale = obj.get("scale", [1, 1, 1])
        if len(scale) != 3 or any(float(s) <= 0 for s in scale):
            raise ValueError("Invalid model scale")
        # The current software renderer supports uniform sphere scaling.
        radius = float(params["radius"]) * sum(map(float, scale)) / 3
        mesh = SphereMesh(rings=int(params["rings"]),
                          segments=int(params["segments"]), radius=radius)
        position = tuple(float(v) for v in obj.get("position", [0, 0, 0]))
        if len(position) != 3:
            raise ValueError("Invalid model position")
        animation = obj.get("animation", {})
        speed = float(animation.get("speed_degrees_per_second", 0))
        if animation.get("type") != "spin" or animation.get("axis") != [0, 1, 0]:
            speed = 0
        objects.append({"renderer": SoftwareRenderer(mesh), "position": position,
                        "radius": radius, "speed": math.radians(speed),
                        "rotation": math.radians(float(obj.get("rotation", [0, 0, 0])[1]))})
    return scene, objects



def _hud_memory_mb():
    """Current RSS in MB when the OS exposes it."""
    try:
        if sys.platform.startswith("linux"):
            status = Path("/proc/self/status").read_text(encoding="utf-8")
            for line in status.splitlines():
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
        if os.name == "nt":
            import ctypes

            class Counters(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.c_ulong), ("page_faults", ctypes.c_ulong),
                    ("peak_ws", ctypes.c_size_t), ("working_set", ctypes.c_size_t),
                    ("peak_paged_pool", ctypes.c_size_t),
                    ("paged_pool", ctypes.c_size_t),
                    ("peak_nonpaged_pool", ctypes.c_size_t),
                    ("nonpaged_pool", ctypes.c_size_t),
                    ("pagefile", ctypes.c_size_t),
                    ("peak_pagefile", ctypes.c_size_t),
                ]
            counters = Counters()
            counters.cb = ctypes.sizeof(counters)
            process = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.psapi.GetProcessMemoryInfo(
                process, ctypes.byref(counters), counters.cb
            ):
                return counters.working_set / 1048576.0
        if sys.platform == "darwin":
            import resource
            return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1048576.0
    except (OSError, ValueError, AttributeError, ImportError):
        pass
    return None


class Pyrion3DApp(tk.Tk):
    """Minimal full-screen PYRION desktop containing only the rotating sphere."""

    def __init__(self):
        super().__init__()
        self.title("PYRION OS")
        self.scene, self.objects = load_selected_scene()
        self.background = self.scene.get("background", {}).get("color", BACKGROUND)
        self.configure(bg=self.background)
        self.windowed = (
            "--windowed" in sys.argv or os.environ.get("PYRION_WINDOWED") == "1"
        )
        self._setup_window()

        self.canvas = tk.Canvas(
            self, bg=self.background, highlightthickness=0, bd=0,
            relief="flat", takefocus=1
        )
        self.canvas.pack(fill="both", expand=True)
        self.renderer = self.objects[0]["renderer"] if self.objects else None
        for item in self.objects:
            item["renderer"].rotation_y = item["rotation"]
            item["renderer"].rotation_x = -0.28
        self.base_pitch = -0.28
        self.spin_rate = 1.0
        self.running = True
        self.visible_triangles = 0
        self.frames = 0
        self.info_mode = "compacto"
        self.fps = 0.0
        self.frame_ms = 0.0
        self.render_ms = 0.0
        self.average_fps = 0.0
        self.cpu_percent = 0.0
        self.ram_mb = None
        self._fps_count = 0
        self._fps_periods = 0
        self._fps_history = []
        self.started_at = time.perf_counter()
        self._fps_start = self.started_at
        self._cpu_start = time.process_time()
        self.last_time = time.perf_counter()
        self.drag_start = None
        self.pending_frame = None
        self._width = 1
        self._height = 1
        self._orb_radius = 1

        # Controls are keyboard/mouse-only; no controls are drawn on the desktop.
        self.bind("<space>", lambda _event: self.toggle_animation())
        self.bind("<F3>", self._toggle_hud_mode)
        self.bind("<Left>", lambda _event: self._speed(-0.15))
        self.bind("<Right>", lambda _event: self._speed(+0.15))
        self.bind("<plus>", lambda _event: self._zoom(+0.10))
        self.bind("<minus>", lambda _event: self._zoom(-0.10))
        self.bind("<F11>", self._switch_to_window)
        self.bind("<Escape>", self._switch_to_window)
        self.bind("<Control-q>", lambda _event: self.close())
        self.canvas.bind("<ButtonPress-1>", self._mouse_press)
        self.canvas.bind("<B1-Motion>", self._mouse_move)
        self.canvas.bind("<ButtonRelease-1>", self._mouse_release)
        self.canvas.bind("<MouseWheel>", self._scroll)
        self.canvas.bind("<Button-4>", lambda _event: self._zoom(+0.10))
        self.canvas.bind("<Button-5>", lambda _event: self._zoom(-0.10))
        self.canvas.bind("<Configure>", lambda _event: self._request_frame())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(80, self._frame)
        self.after(1000, self._keep_as_desktop)

    def _setup_window(self):
        self.update_idletasks()
        if self.windowed:
            self.geometry("1100x720")
            self.minsize(400, 300)
        elif os.name == "nt":
            self.attributes("-fullscreen", True)
        else:
            # Support minimal Linux/Xorg without a window manager.
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
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
            pass

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

    def toggle_animation(self):
        self.running = not self.running
        self.last_time = time.perf_counter()
        self._request_frame()

    def _speed(self, amount):
        self.spin_rate = max(0.15, min(3.5, self.spin_rate + amount))

    def _zoom(self, amount):
        for item in self.objects:
            r = item["renderer"]
            r.zoom = max(0.55, min(1.42, r.zoom + amount))
        self._request_frame()

    def _mouse_press(self, event):
        if self._hud_click(event):
            return
        cx, cy = self._width / 2, self._height / 2
        if (event.x - cx) ** 2 + (event.y - cy) ** 2 <= self._orb_radius ** 2:
            self.drag_start = (event.x, event.y)

    def _mouse_move(self, event):
        if self.drag_start is None:
            return
        dx, dy = event.x - self.drag_start[0], event.y - self.drag_start[1]
        for item in self.objects:
            item["renderer"].rotation_y += dx * 0.007
        self.base_pitch = max(-1.35, min(1.35, self.base_pitch - dy * 0.007))
        for item in self.objects:
            item["renderer"].rotation_x = self.base_pitch
        self.drag_start = (event.x, event.y)
        self._request_frame()

    def _mouse_release(self, _event):
        self.drag_start = None

    def _scroll(self, event):
        self._zoom(0.10 if event.delta > 0 else -0.10)

    def _request_frame(self):
        if self.pending_frame is None:
            self.pending_frame = self.after_idle(self._draw)

    def _draw(self):
        self.pending_frame = None
        if not self.winfo_exists():
            return
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        if width < 100 or height < 100:
            return
        self._width, self._height = width, height
        self.canvas.delete("all")
        draw_start = time.perf_counter()
        diameter = min(height * 0.60, width * 0.48, 520)
        self._orb_radius = diameter * 0.50
        self.visible_triangles = 0
        for item in sorted(self.objects, key=lambda obj: obj["position"][2]):
            px, py, pz = item["position"]
            depth = max(0.5, 3.85 - pz)
            factor = 3.85 / depth
            renderer = item["renderer"]
            self.visible_triangles += renderer.draw(
                self.canvas, width / 2 + px * diameter * 0.47 * factor,
                height / 2 - py * diameter * 0.47 * factor,
                diameter * factor, draw_graticules=False
            )
        self.render_ms = (time.perf_counter() - draw_start) * 1000.0
        self._draw_hud()


    def _hud_click(self, event):
        if self._width >= 360 and 208 <= event.x <= 306 and 16 <= event.y <= 40:
            self.info_mode = "diagnostico" if self.info_mode == "compacto" else "compacto"
            self._request_frame()
            return True
        return False

    def _toggle_hud_mode(self, _event=None):
        self.info_mode = "diagnostico" if self.info_mode == "compacto" else "compacto"
        self._request_frame()

    def _draw_hud(self):
        if self._width < 360:
            return
        canvas = self.canvas
        x = 20
        full = self.info_mode == "diagnostico"
        canvas.create_text(
            x, 20, text="PYRION 3D  /  " + str(self.scene.get("name", "Scene")),
            anchor="nw", fill="#71cfff", font=("TkDefaultFont", 9, "bold")
        )
        canvas.create_rectangle(
            208, 16, 306, 40, outline="#345878", fill="#10243c", width=1
        )
        canvas.create_text(
            257, 28, text="COMPACTO" if full else "DETALLES",
            fill="#d5eaff", font=("TkDefaultFont", 9)
        )
        status = ("FLUIDO" if self.fps >= 50 else
                  "ACEPTABLE" if self.fps >= 25 else "LENTO")
        # FPS and frame time come from measured frame intervals, not estimates.
        lines = [
            ("FPS", "%.1f" % self.fps),
            ("FRAME", "%.1f ms" % self.frame_ms),
            ("CPU PROCESO", "%.1f%%" % self.cpu_percent),
            ("RAM PROCESO", "%.1f MB" % self.ram_mb if self.ram_mb is not None else "--"),
            ("TRIANGULOS", str(self.visible_triangles)),
            ("ESTADO", status if self.running else "PAUSADO"),
        ]
        if full:
            durations = sorted(self._fps_history)
            low = (sum(durations[:max(1, len(durations) // 100)]) /
                   max(1, len(durations) // 100)) if durations else 0.0
            vertices = sum(len(item["renderer"].mesh.vertices) for item in self.objects)
            total_faces = sum(len(item["renderer"].mesh.faces) for item in self.objects)
            seconds = int(time.perf_counter() - self.started_at)
            lines = [
                ("ESCENA", str(self.scene.get("name", "Scene"))),
                ("FPS", "%.1f" % self.fps),
                ("FPS PROMEDIO", "%.1f" % self.average_fps),
                ("FPS 1% BAJO", "%.1f" % low if durations else "--"),
                ("FRAME", "%.1f ms" % self.frame_ms),
                ("RENDER", "%.1f ms" % self.render_ms),
                ("CPU PROCESO", "%.1f%%" % self.cpu_percent),
                ("RAM PROCESO", "%.1f MB" % self.ram_mb if self.ram_mb is not None else "--"),
                ("MODELOS", str(len(self.objects))),
                ("VERTICES", str(vertices)),
                ("TRIANGULOS", str(self.visible_triangles) + " / " + str(total_faces)),
                ("ANIMACION", "ACTIVA" if self.running else "PAUSADA"),
                ("UPTIME", "%02d:%02d:%02d" % (seconds // 3600, (seconds // 60) % 60, seconds % 60)),
                ("ESTADO", status),
            ]
        y = 50
        for label, value in lines:
            canvas.create_text(x, y, text=label, anchor="nw",
                               fill="#92aaca", font=("TkDefaultFont", 9))
            canvas.create_text(308, y, text=value, anchor="ne",
                               fill="#d1e6fa" if label != "ESTADO" else "#75e2ad",
                               font=("TkDefaultFont", 9))
            y += 19

    def _frame(self):
        try:
            now = time.perf_counter()
            elapsed = max(0.0, min(0.1, now - self.last_time))
            self.last_time = now
            if self.running:
                for item in self.objects:
                    renderer = item["renderer"]
                    renderer.rotation_y = (
                        renderer.rotation_y + item["speed"] * self.spin_rate * elapsed
                    ) % (math.pi * 2)
            self.frames += 1
            self._fps_count += 1
            interval = now - self._fps_start
            if interval >= 0.6:
                self.fps = self._fps_count / interval
                self.frame_ms = 1000.0 / self.fps if self.fps else 0.0
                self._fps_periods += 1
                self.average_fps += (self.fps - self.average_fps) / self._fps_periods
                self._fps_history.append(self.fps)
                self._fps_history = self._fps_history[-120:]
                self.cpu_percent = 100.0 * max(
                    0.0, time.process_time() - self._cpu_start
                ) / interval
                self.ram_mb = _hud_memory_mb()
                self._cpu_start = time.process_time()
                self._fps_count = 0
                self._fps_start = now
            self._draw()
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
