"""PYRION OS 0.4.26 - standalone PYRION 3D Engine.

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
APP_VERSION = "0.4.29"
REPO_OWNER = "mobatfb"
REPO_NAME = "archmoba-dev"
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


def check_self_update(restart=True, raise_errors=False):
    """Keep PYRION's existing pinned-commit update protocol."""
    if os.environ.get("AMDEV_MODE") == "local":
        try:
            current = Path(__file__).resolve()
            config = json.loads(current.with_name("config.json").read_text(encoding="utf-8-sig"))
            version = str(config.get("version", ""))
            if _version_tuple(version) <= _version_tuple(APP_VERSION):
                return False
            source = current.read_text(encoding="utf-8-sig")
            match = re.search(r'''APP_VERSION\s*=\s*["']([^"']+)["']''', source)
            if not match or match.group(1) != version:
                raise RuntimeError("La version local no coincide con config.json")
            compile(source, str(current), "exec")
            if restart:
                if os.name == "nt":
                    subprocess.Popen([sys.executable, str(current), *sys.argv[1:]], cwd=str(current.parent))
                else:
                    os.execv(sys.executable, [sys.executable, str(current), *sys.argv[1:]])
            return True
        except Exception as exc:
            if raise_errors:
                raise
            _error_log(f"Fallo en actualizacion local: {exc}")
            return False

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
        if raise_errors:
            raise
        _error_log(f"Fallo en autoactualizacion: {type(exc).__name__}: {exc}")
        return False




"""3D mesh primitives for PYRION Engine - Python standard library only."""


@dataclass(frozen=True)
class Face:
    indices: tuple
    longitude: float
    latitude: float
    band: int


def normalize_face_colors(colors, count):
    """Color #RRGGBB o None por triangulo; None usa el material existente."""
    if colors is None:
        return (None,) * count
    if not isinstance(colors, list) or len(colors) != count:
        raise ValueError("face_colors must have exactly one item per triangle")
    result = []
    for index, color in enumerate(colors):
        if color is None:
            result.append(None)
        elif (isinstance(color, str) and len(color) == 7 and color.startswith("#")
              and all(ch in "0123456789abcdefABCDEF" for ch in color[1:])):
            result.append(color.upper())
        else:
            raise ValueError("Invalid face_colors[%d]: expected #RRGGBB or null" % index)
    return tuple(result)


class SphereMesh:
    """UV sphere with a single north/south pole and manifold triangle topology."""

    def __init__(self, rings=24, segments=48, radius=1.0, face_colors=None):
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

        self.face_colors = normalize_face_colors(face_colors, len(self.faces))

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
 
class TriangleMesh:
    """Explicit triangular 3D mesh for faceted or imported low-poly objects."""

    flat_shading = True

    def __init__(self, vertices, faces, scale=(1.0, 1.0, 1.0), face_colors=None):
        if not (3 <= len(vertices) <= 12000 and 1 <= len(faces) <= 20000):
            raise ValueError("Invalid triangle mesh size")
        if len(scale) != 3 or any(
            not math.isfinite(float(value)) or float(value) <= 0 for value in scale
        ):
            raise ValueError("Invalid model scale")
        self.vertices = []
        for xyz in vertices:
            if len(xyz) != 3:
                raise ValueError("Mesh vertex must have 3 coordinates")
            xyz = tuple(float(xyz[k]) * float(scale[k]) for k in range(3))
            if not all(math.isfinite(v) for v in xyz):
                raise ValueError("Nonfinite mesh vertex")
            self.vertices.append(xyz)
        self.radius = max(math.sqrt(sum(k * k for k in xyz)) for xyz in self.vertices)
        low = min(xyz[1] for xyz in self.vertices)
        high = max(xyz[1] for xyz in self.vertices)
        height = max(high - low, 1e-6)
        self.faces = []
        for face in faces:
            if len(face) != 3 or any(
                type(index) is not int or index < 0 or index >= len(self.vertices)
                for index in face
            ):
                raise ValueError("Invalid mesh triangle")
            a, b, c = (self.vertices[i] for i in face)
            centroid = tuple((a[k] + b[k] + c[k]) / 3.0 for k in range(3))
            lon = math.atan2(centroid[2], centroid[0]) % (2 * math.pi)
            lat = math.pi * (1.0 - (centroid[1] - low) / height)
            self.faces.append(Face(tuple(face), lon, lat, 0))
        self.face_colors = normalize_face_colors(face_colors, len(self.faces))

    @property
    def vertex_count(self):
        return len(self.vertices)

    @property
    def triangle_count(self):
        return len(self.faces)

    def signature(self):
        return ("triangle_mesh", self.vertex_count, self.triangle_count)



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

    def __init__(self, mesh, material=None):
        self.mesh = mesh
        self.material = material if isinstance(material, dict) else {}
        self._gem = self.material.get("shader") == "gem"
        self._pbr = self.material.get("shader") in ("pbr", "gem")
        color = str(self.material.get("base_color", "#2767d7"))
        if len(color) != 7 or not color.startswith("#"):
            raise ValueError("Invalid material base_color")
        try:
            self._base_rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
        except ValueError as exc:
            raise ValueError("Invalid material base_color") from exc
        self._metallic = max(0.0, min(1.0, float(self.material.get("metallic", 0))))
        self._roughness = max(0.04, min(1.0, float(self.material.get("roughness", 0.5))))
        # Cada indice corresponde al triangulo en mesh.faces, sin alterar su topologia.
        self._face_rgbs = [
            tuple(int(color[k:k + 2], 16) for k in (1, 3, 5)) if color else None
            for color in getattr(mesh, "face_colors", (None,) * len(mesh.faces))
        ]
        self.material_mode = "mat"
        self._texels = None
        texture = self.material.get("_texture_image")
        if texture is not None:
            pixels = texture.load()
            tw, th = texture.size
            self._texels = [
                pixels[min(tw - 1, max(0, int((face.longitude % (2 * math.pi)) / (2 * math.pi) * (tw - 1)))),
                       min(th - 1, max(0, int(face.latitude / math.pi * (th - 1))))]
                for face in mesh.faces
            ]
        self.has_image_texture = self._texels is not None
        self._surface_texture = None
        self._surface_uv = None
        self._surface_cache = None
        self._surface_photo = None
        self._fog = None
        if texture is not None and self.material.get("texture_projection") == "box" and hasattr(texture, "convert"):
            from PIL import Image
            tile = texture.convert("RGB")
            tile.thumbnail((256, 256))
            tint = self.material.get("texture_tint")
            if tint:
                channels = tile.split()
                tile = Image.merge("RGB", tuple(channel.point(
                    [round(v * int(tint[1+k*2:3+k*2], 16) / 255) for v in range(256)])
                    for k, channel in enumerate(channels)))
            repeat = max(1, min(8, int(self.material.get("texture_repeat_y", 3))))
            repeat_x = max(1, min(8, int(self.material.get("texture_repeat_x", 1))))
            self._surface_texture = Image.new("RGB", (tile.width * repeat_x, tile.height * repeat))
            for row in range(repeat):
                for column in range(repeat_x):
                    self._surface_texture.paste(tile, (column * tile.width, row * tile.height))
            self._surface_uv = []
            low = [min(v[k] for v in mesh.vertices) for k in range(3)]
            span = [max(v[k] for v in mesh.vertices) - low[k] for k in range(3)]
            for face in mesh.faces:
                a, b, c = [mesh.vertices[i] for i in face.indices]
                e, f = [b[k] - a[k] for k in range(3)], [c[k] - a[k] for k in range(3)]
                normal = (e[1]*f[2]-e[2]*f[1], e[2]*f[0]-e[0]*f[2], e[0]*f[1]-e[1]*f[0])
                axis = max(range(3), key=lambda k: abs(normal[k]))
                u_axis, v_axis = ((2, 1) if axis == 0 else (0, 2) if axis == 1 else (0, 1))
                uv = [((v[u_axis]-low[u_axis]) / max(span[u_axis], 1e-9) * (self._surface_texture.width-1),
                       (1-(v[v_axis]-low[v_axis]) / max(span[v_axis], 1e-9)) * (self._surface_texture.height-1))
                      for v in (a, b, c)]
                self._surface_uv.append(uv)
            self._texels = [self._surface_texture.getpixel((
                int(sum(p[0] for p in uv)/3), int(sum(p[1] for p in uv)/3))) for uv in self._surface_uv]
            self.material_mode = "img"
        self.camera_distance = 3.85
        self.rotation_y = 0.0
        self.rotation_x = -0.25
        self.zoom = 1.0
        self.wireframe = False
        self._light_a = _unit((-0.42, 0.77, 0.53))
        self._light_b = _unit((0.74, -0.29, 0.47))
        self._spotlights = ()
        self._spot_ambient = 0.56
        self.spotlight_enabled = True
        self._lines = []
        if hasattr(mesh, "meridian") and hasattr(mesh, "latitude"):
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

    def set_atmosphere(self, fog):
        self._fog = dict(fog) if fog else None

    def _apply_fog(self, color, depth):
        if not self._fog:
            return color
        start, end = float(self._fog.get("start", 15)), float(self._fog.get("end", 40))
        amount = max(0, min(1, (depth-start) / max(0.01, end-start)))
        amount *= max(0, min(1, float(self._fog.get("strength", 0.35))))
        tint = self._fog.get("color", "#416078")
        return _rgb(tuple(int(color[i:i+2], 16)*(1-amount) + int(tint[i:i+2], 16)*amount for i in (1, 3, 5)))

    def set_lights(self, lights, ambient=0.56):
        """Prepare optional spot lights declared in scene.json.

        All positions/targets are scene world coordinates (Y is up).
        Rendering is CPU-per-triangle and does not cast shadows.
        """
        if not isinstance(lights, list):
            raise ValueError("Scene lights must be a list")
        self._spot_ambient = max(0.08, min(1.0, float(ambient)))
        prepared = []
        for light in lights[:8]:
            if not isinstance(light, dict) or light.get("type") != "spot":
                continue
            if not light.get("enabled", True):
                continue
            position = tuple(float(v) for v in light["position"])
            target = tuple(float(v) for v in light["target"])
            if len(position) != 3 or len(target) != 3:
                raise ValueError("Spotlight position and target need 3 coordinates")
            if not all(math.isfinite(v) for v in position + target):
                raise ValueError("Spotlight coordinates must be finite")
            direction_vec = tuple(target[i] - position[i] for i in range(3))
            if _dot(direction_vec, direction_vec) < 1e-10:
                raise ValueError("Spotlight target must differ from its position")
            color = str(light.get("color", "#ffffff"))
            if len(color) != 7 or not color.startswith("#"):
                raise ValueError("Spotlight color must be #RRGGBB")
            tint = tuple(int(color[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
            angle = max(5.0, min(170.0, float(light.get("angle_degrees", 80.0))))
            softness = max(0.0, min(0.95, float(light.get("softness", 0.25))))
            strength = max(0.0, min(8.0, float(light.get("intensity", 1.8))))
            reach = max(0.2, min(100.0, float(light.get("range", 9.0))))
            if not all(math.isfinite(v) for v in (angle, softness, strength, reach)):
                raise ValueError("Spotlight properties must be finite")
            outer = math.cos(math.radians(angle * 0.5))
            inner = math.cos(math.radians(angle * 0.5 * (1.0 - softness)))
            prepared.append({
                "position": position, "direction": _unit(direction_vec),
                "color": tint, "intensity": strength, "range": reach,
                "outer": outer, "inner": inner,
            })
        self._spotlights = tuple(prepared)

    def _shade_spotlights(self, color, normal, towards_camera, world_point):
        """Apply cone, angular incidence, range falloff and specular light."""
        if not self._spotlights or not self.spotlight_enabled:
            return color
        base = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
        result = [channel * self._spot_ambient for channel in base]
        gloss = 13.0 + 70.0 * (1.0 - self._roughness)
        for spot in self._spotlights:
            to_light = tuple(spot["position"][k] - world_point[k] for k in range(3))
            distance_sq = _dot(to_light, to_light)
            if distance_sq < 1e-8 or distance_sq >= spot["range"] ** 2:
                continue
            distance = math.sqrt(distance_sq)
            incident = tuple(component / distance for component in to_light)
            # From the emitter to the shaded triangle, inside the cone.
            cone = -_dot(incident, spot["direction"])
            if cone <= spot["outer"]:
                continue
            if spot["inner"] <= spot["outer"] + 1e-8:
                cone_weight = 1.0
            else:
                cone_weight = max(0.0, min(
                    1.0, (cone - spot["outer"]) /
                    (spot["inner"] - spot["outer"])
                ))
                cone_weight = cone_weight * cone_weight * (3.0 - 2.0 * cone_weight)
            facing = max(0.0, _dot(normal, incident))
            if facing <= 0.0:
                continue
            attenuation = (1.0 - distance_sq / (spot["range"] ** 2)) ** 2
            energy = spot["intensity"] * cone_weight * attenuation
            diffuse = 1.20 * energy * facing
            half_vector = _unit(tuple(
                incident[k] + towards_camera[k] for k in range(3)
            ))
            highlight = max(0.0, _dot(normal, half_vector)) ** gloss
            specular = 0.60 * energy * highlight * facing * float(self.material.get("specular_strength", 1.0))
            for k in range(3):
                result[k] += spot["color"][k] * (
                    base[k] * diffuse + 255.0 * specular
                )
        return _rgb(result)

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

    def _color(self, normal, accent, front, view, texel=None, face_rgb=None):
        """CPU approximation of metallic PBR with environment-like highlights."""
        a = max(0.0, _dot(normal, self._light_a))
        b = max(0.0, _dot(normal, self._light_b))
        if self._gem:
            base = face_rgb if face_rgb is not None else self._base_rgb
            if face_rgb is None and self.material_mode == "img" and texel is not None:
                base = tuple(0.12 * base[k] + 0.88 * texel[k] for k in range(3))
            facet = 0.30 + 0.65 * a + 0.24 * b + 0.21 * accent
            glint = max(0.0, _dot(normal, _unit((-0.28, 0.74, 0.62)))) ** 13
            white = max(0.0, _dot(normal, _unit((0.42, 0.68, 0.53)))) ** 38
            rim = (1.0 - max(0.0, front)) ** 3
            strength = float(self.material.get("highlight_strength", 1.0))
            exposure = float(self.material.get("exposure", 1.0))
            return _rgb((
                exposure*(base[0] * facet + strength*(102 * glint + 108 * white + 30 * rim)),
                exposure*(base[1] * facet + strength*(115 * glint + 130 * white + 23 * rim)),
                exposure*(base[2] * (facet + 0.12) + strength*(135 * glint + 125 * white + 44 * rim)),
            ))
        if not self._pbr:
            if face_rgb is not None:
                # Material procedimental simple: respeta el color explicito con luz.
                diffuse = 0.33 + 0.61 * a + 0.16 * b
                highlight = 19.0 * max(0.0, _dot(
                    normal, _unit((-0.13, 0.62, 0.78))
                )) ** 24
                return _rgb(tuple(channel * diffuse + highlight for channel in face_rgb))
            edge = (1.0 - front) ** 1.9
            spec = max(0.0, _dot(normal, _unit((-0.13, 0.62, 0.78)))) ** 24
            return _rgb((
                17 + 53 * a + 14 * b + 14 * accent + 56 * spec + 24 * edge,
                30 + 80 * a + 21 * b + 19 * accent + 73 * spec + 19 * edge,
                69 + 112 * a + 71 * b + 46 * accent + 48 * spec + 36 * edge,
            ))
        metallic, rough = self._metallic, self._roughness
        base = face_rgb if face_rgb is not None else self._base_rgb
        if face_rgb is None and self.material_mode == "img" and texel is not None:
            # Photo texture wrapped around the rotating 3D sphere.
            base = tuple(0.88 * texel[k] + 0.12 * base[k]
                         for k in range(3))
        half_a = _unit(tuple(self._light_a[i] + view[i] for i in range(3)))
        half_b = _unit(tuple(self._light_b[i] + view[i] for i in range(3)))
        exponent = min(180.0, max(5.0, 2.0 / (rough * rough)))
        sharp = max(0.0, _dot(normal, half_a)) ** exponent
        sharp += 0.45 * max(0.0, _dot(normal, half_b)) ** exponent
        panel = max(0.0, _dot(normal, _unit((-0.38, 0.44, 0.82)))) ** (
            5.0 + 13.0 * (1.0 - rough))
        strip = max(0.0, _dot(normal, _unit((0.68, 0.22, 0.70)))) ** (
            12.0 + 28.0 * (1.0 - rough))
        fresnel = (1.0 - max(0.0, min(1.0, front))) ** 5
        diffuse = (0.15 + 0.46 * a + 0.15 * b) * (1.0 - 0.72 * metallic)
        reflected = (0.18 + 0.16 * a + 0.22 * b +
                     0.70 * panel + 0.38 * strip +
                     1.55 * sharp + 0.16 * fresnel) * (0.3 + 0.7 * metallic)
        return _rgb(tuple(
            base[k] * (diffuse + reflected) +
            (1.0 - metallic) * 10.0 * (a + b)
            for k in range(3)
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

    @staticmethod
    def _clip_near_plane(polygon, near=0.32):
        """Clip view-space polygons to keep walking close to meshes stable."""
        clipped = []
        for i, current in enumerate(polygon):
            previous = polygon[i - 1]
            was_inside = previous[2] >= near
            is_inside = current[2] >= near
            if was_inside != is_inside:
                fraction = (near - previous[2]) / (current[2] - previous[2])
                clipped.append(tuple(
                    previous[k] + fraction * (current[k] - previous[k])
                    for k in range(3)
                ))
            if is_inside:
                clipped.append(current)
        return clipped

    def _paint_surface(self, canvas, image, left, top):
        if hasattr(canvas, "draw_surface"):
            canvas.draw_surface(image, left, top)
        else:
            from PIL import ImageTk
            if self._surface_photo is None:
                self._surface_photo = ImageTk.PhotoImage(image, master=canvas)
            canvas.create_image(left, top, anchor="nw", image=self._surface_photo)

    def _raster_surface(self, faces, viewport):
        """Affine texture patches; cache the finished static tower between frames."""
        from PIL import Image, ImageDraw
        points = [p for _, polygon, _, _ in faces for p in zip(polygon[::2], polygon[1::2])]
        if not points:
            return None
        left = max(0, math.floor(min(p[0] for p in points)))
        top = max(0, math.floor(min(p[1] for p in points)))
        right = min(viewport[0], math.ceil(max(p[0] for p in points)) + 1)
        bottom = min(viewport[1], math.ceil(max(p[1] for p in points)) + 1)
        if right <= left or bottom <= top:
            return None
        output = Image.new("RGBA", (right-left, bottom-top))
        for _, polygon, color, uv in faces:
            coords = [(x-left, y-top) for x, y in zip(polygon[::2], polygon[1::2])]
            if uv is None:
                ImageDraw.Draw(output).polygon(coords, fill=color)
                continue
            x0, y0 = coords[0]
            x1, y1 = coords[1]
            x2, y2 = coords[2]
            determinant = (x1-x0)*(y2-y0)-(x2-x0)*(y1-y0)
            if abs(determinant) < 1e-8:
                continue
            planes = []
            for k in (0, 1, 2):
                values = [point[k] / point[2] if k < 2 else 1 / point[2] for point in uv]
                d1, d2 = values[1]-values[0], values[2]-values[0]
                a = (d1*(y2-y0)-d2*(y1-y0))/determinant
                b = ((x1-x0)*d2-(x2-x0)*d1)/determinant
                planes.append((a, b, values[0]-a*x0-b*y0))
            normalizer = planes[2][2]
            if abs(normalizer) < 1e-10:
                continue
            coefficients = tuple(value/normalizer for plane in planes[:2] for value in plane)
            coefficients += (planes[2][0]/normalizer, planes[2][1]/normalizer)
            patch = self._surface_texture.transform(output.size, Image.Transform.PERSPECTIVE, coefficients,
                                                     resample=Image.Resampling.BILINEAR)
            texel = self._surface_texture.getpixel((int(sum(p[0] for p in uv)/3), int(sum(p[1] for p in uv)/3)))
            target = [int(color[i:i+2], 16) for i in (1, 3, 5)]
            exposure = max(0.1, min(2.0, float(self.material.get("texture_exposure", 1.0))))
            ambient = self.material.get("texture_lighting") == "ambient"
            channels = [channel.point([min(255, round(v * exposure * (1 if ambient else target[k] / max(1, texel[k])))) for v in range(256)])
                        for k, channel in enumerate(patch.split())]
            patch = Image.merge("RGB", channels)
            mask = Image.new("L", output.size)
            ImageDraw.Draw(mask).polygon(coords, fill=255)
            output.paste(patch, (0, 0), mask)
        return output, left, top

    def draw(self, canvas, cx, cy, diameter, draw_graticules=True,
             object_position=(0.0, 0.0, 0.0),
             camera_position=(0.0, 0.0, 3.85),
             camera_yaw=0.0, camera_pitch=0.0):
        """Project rotating world-space models from a movable 3D camera."""
        surface = self._surface_texture is not None and self.material_mode == "img" and not self.wireframe
        signature = (cx, cy, diameter, tuple(object_position), tuple(camera_position), camera_yaw,
                     camera_pitch, self.rotation_x, self.rotation_y, self.zoom,
                     self.spotlight_enabled, str(self._spotlights), self._spot_ambient, str(self._fog))
        if surface and self._surface_cache is not None and self._surface_cache[0] == signature:
            _, cached, count = self._surface_cache
            if cached is not None:
                self._paint_surface(canvas, *cached)
            return count
        focal = max(50.0, diameter * self.camera_distance * 0.47 * self.zoom)
        sy, cyaw = math.sin(camera_yaw), math.cos(camera_yaw)
        sp, cp = math.sin(camera_pitch), math.cos(camera_pitch)
        right = (cyaw, 0.0, sy)
        forward = (sy * cp, sp, -cyaw * cp)
        up = (-sy * sp, cp, cyaw * sp)
        eye = camera_position
        rotated = [self._rotate(v) for v in self.mesh.vertices]
        world = [
            tuple(v[k] + object_position[k] for k in range(3))
            for v in rotated
        ]
        view = []
        for vertex in world:
            delta = tuple(vertex[k] - eye[k] for k in range(3))
            view.append((
                _dot(delta, right), _dot(delta, up), _dot(delta, forward)
            ))
        visible_faces = []
        for face_index, (face, accent) in enumerate(zip(self.mesh.faces, self._material)):
            i, j, k = face.indices
            a, b, c = rotated[i], rotated[j], rotated[k]
            world_center = tuple(
                (world[i][t] + world[j][t] + world[k][t]) / 3.0
                for t in range(3)
            )
            if getattr(self.mesh, "flat_shading", False):
                e1 = tuple(b[t] - a[t] for t in range(3))
                e2 = tuple(c[t] - a[t] for t in range(3))
                normal = _unit((
                    e1[1] * e2[2] - e1[2] * e2[1],
                    e1[2] * e2[0] - e1[0] * e2[2],
                    e1[0] * e2[1] - e1[1] * e2[0]
                ))
            else:
                normal = _unit(tuple(
                    (a[t] + b[t] + c[t]) / 3.0 for t in range(3)
                ))
            towards_camera = _unit(tuple(
                eye[t] - world_center[t] for t in range(3)
            ))
            front = _dot(normal, towards_camera)
            if getattr(self.mesh, "double_sided", False):
                # Doble cara: normal invertida solo para iluminacion interior.
                if front < 0:
                    normal = tuple(-component for component in normal)
                    front = -front
            elif front <= 0.02:
                continue
            polygon = self._clip_near_plane([view[i], view[j], view[k]])
            if len(polygon) < 3:
                continue
            projected = []
            for vx, vy, depth in polygon:
                factor = focal / depth
                projected.extend((cx + vx * factor, cy - vy * factor))
            face_rgb = self._face_rgbs[face_index]
            color = self._color(
                normal, accent, front, towards_camera,
                self._texels[face_index] if self._texels is not None else None,
                face_rgb=face_rgb
            )
            if self._spotlights and self.spotlight_enabled:
                color = self._shade_spotlights(
                    color, normal, towards_camera, world_center
                )
            depth = sum(v[2] for v in polygon) / len(polygon)
            color = self._apply_fog(color, depth)
            # Las caras con color propio se pintan solidas, incluso en modo IMG.
            uv = [(point[0], point[1], view[index][2]) for point, index in zip(self._surface_uv[face_index], (i, j, k))] if surface and face_rgb is None and len(polygon) == 3 and all(view[t][2] >= 0.32 for t in (i, j, k)) else None
            visible_faces.append((depth, projected, color, uv))
        visible_faces.sort(key=lambda item: item[0], reverse=True)
        if surface:
            cached = self._raster_surface(visible_faces, (int(cx*2), int(cy*2)))
            self._surface_cache = (signature, cached, len(visible_faces))
            self._surface_photo = None
            if cached is not None:
                self._paint_surface(canvas, *cached)
            return len(visible_faces)
        for _, polygon, color, _ in visible_faces:
            canvas.create_polygon(
                *polygon, fill=color,
                outline="#22426e" if self.wireframe else color,
                width=0.7 if self.wireframe else 0.2
            )
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


ENGINE_VERSION = "0.4.6"
DESKTOP_VERSION = "0.4.29"
BACKGROUND = "#050917"
REPO_RAW_BASE = "https://raw.githubusercontent.com/mobatfb/archmoba-dev/main/PYRION"



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
    if os.environ.get("AMDEV_MODE") == "local":
        raise FileNotFoundError(f"No existe el recurso local: {local}")
    url = REPO_RAW_BASE + "/engine3d/" + relative.as_posix()
    request = urllib.request.Request(url, headers={"User-Agent": "PYRION/0.4.13"})
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8-sig"))



# Comprobacion de .mesh del repositorio: una version local antigua no debe
# ocultar los colores nuevos del mismo modelo. El acceso a red es opcional.
MESH_REFRESH_SECONDS = 3.0


def _mesh_version_key(model):
    """El antiguo version numerico era formato, NO version del modelo."""
    version = model.get("version", "") if isinstance(model, dict) else ""
    if not isinstance(version, str):
        return (0, 0, 0)
    parts = version.split(".")
    if len(parts) != 3 or not all(part.isdecimal() for part in parts):
        return (0, 0, 0)
    return tuple(int(part) for part in parts)


def _make_model_mesh(model, scale):
    if model.get("format") != "pyrion.mesh":
        raise ValueError("Unsupported model format")
    if len(scale) != 3 or any(
        not math.isfinite(float(v)) or float(v) <= 0 for v in scale
    ):
        raise ValueError("Invalid model scale")
    primitive = model.get("primitive")
    if primitive == "uv_sphere":
        p = model["parameters"]
        radius = float(p["radius"]) * sum(map(float, scale)) / 3
        return SphereMesh(rings=int(p["rings"]), segments=int(p["segments"]),
                          radius=radius, face_colors=model.get("face_colors"))
    if primitive == "triangle_mesh":
        # PYRION Origami: quads editables, triangulados solo para renderizar.
        source_faces = model["faces"]
        source_colors = model.get("face_colors")
        render_faces, render_colors = [], [] if source_colors is not None else None
        if source_colors is not None and len(source_colors) != len(source_faces):
            raise ValueError("face_colors no coincide con faces")
        for pos, face in enumerate(source_faces):
            if len(face) == 3:
                render_faces.append(face)
                if render_colors is not None:
                    render_colors.append(source_colors[pos])
            elif 4 <= len(face) <= 128:
                # Triangulacion en abanico de superficies planas convexas.
                triangles = [[face[0], face[j], face[j + 1]]
                             for j in range(1, len(face) - 1)]
                render_faces.extend(triangles)
                if render_colors is not None:
                    render_colors.extend([source_colors[pos]] * len(triangles))
            else:
                raise ValueError("Origami admite caras de 3 a 128 vertices")
        mesh = TriangleMesh(model["vertices"], render_faces, scale=scale,
                            face_colors=render_colors)
        mesh.double_sided = bool(model.get("render", {}).get("double_sided", False))
        mesh.flat_shading = bool(model.get("render", {}).get("flat_shading", getattr(mesh, "flat_shading", False)))
        return mesh
    raise ValueError("Unsupported mesh primitive: " + str(primitive))


def _fetch_updated_mesh(relative_path, loaded_model, scale):
    """Recuperar una malla modificada; nunca degradar su version ni bloquear Tk."""
    relative = Path(relative_path)
    if (relative.is_absolute() or ".." in relative.parts
            or relative.suffix != ".mesh"):
        raise ValueError("Invalid mesh path")
    if os.environ.get("PYRION_MESH_OFFLINE") == "1":
        return None
    request = urllib.request.Request(
        REPO_RAW_BASE + "/engine3d/" + relative.as_posix()
        + "?pyrion_refresh=" + str(time.time_ns()),
        headers={"User-Agent": "PYRION/" + DESKTOP_VERSION,
                 "Cache-Control": "no-cache", "Pragma": "no-cache"})
    with urllib.request.urlopen(request, timeout=6) as response:
        payload = response.read(2 * 1024 * 1024 + 1)
    if len(payload) > 2 * 1024 * 1024:
        raise ValueError("Mesh exceeds 2 MiB")
    remote = json.loads(payload.decode("utf-8-sig"))
    if remote == loaded_model or _mesh_version_key(remote) < _mesh_version_key(loaded_model):
        return None
    # Validar geometria y colores ANTES de escribir en el disco.
    _make_model_mesh(remote, scale)
    root = Path(__file__).resolve().parent
    engine = root if root.name == "engine3d" else root / "engine3d"
    local = engine / relative
    try:
        local.parent.mkdir(parents=True, exist_ok=True)
        temporary = local.with_name(local.name + ".pyrion.tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, local)
    except OSError:
        # Instalaciones de solo lectura siguen pudiendo usar la copia en RAM.
        pass
    return remote


def _mesh_can_mirror(model):
    """Detecta una media malla sobre X=0 sin reflejar un modelo ya completo."""
    if not isinstance(model, dict) or model.get("primitive") != "triangle_mesh":
        return False
    vertices = model.get("vertices")
    faces = model.get("faces")
    if (not isinstance(vertices, list) or not isinstance(faces, list)
            or len(vertices) * 2 > 12000 or len(faces) * 2 > 20000):
        return False
    left = right = seam = False
    for vertex in vertices:
        x = float(vertex[0])
        if x < -1e-5:
            left = True
        elif x > 1e-5:
            right = True
        else:
            seam = True
        if left and right:
            return False
    return seam and (left or right)


def _make_visible_mesh(model, scale, mirror=False):
    """Construye la mitad opuesta de modo virtual y con colores por cara."""
    base = _make_model_mesh(model, scale)
    if not mirror or not _mesh_can_mirror(model):
        return base
    vertices = list(base.vertices)
    indices = []
    for x, y, z in base.vertices:
        if abs(x) <= 1e-5:
            indices.append(len(indices))  # Costura compartida del eje X=0.
        else:
            indices.append(len(vertices))
            vertices.append((-x, y, z))
    faces = [list(face.indices) for face in base.faces]
    colors = list(base.face_colors) if model.get("face_colors") is not None else None
    for n, face in enumerate(base.faces):
        a, b, c = face.indices
        if all(abs(base.vertices[i][0]) <= 1e-5 for i in (a, b, c)):
            continue
        # Reflejar invierte las normales; invertir el orden de los vertices.
        faces.append([indices[a], indices[c], indices[b]])
        if colors is not None:
            colors.append(base.face_colors[n])
    mirrored = TriangleMesh(vertices, faces, face_colors=colors)
    mirrored.double_sided = getattr(base, "double_sided", False)
    mirrored.flat_shading = getattr(base, "flat_shading", False)
    return mirrored


def _mirror_preferences_path():
    return Path.home() / ".pyrion" / "preferences.json"


def _load_mirror_preference():
    try:
        data = json.loads(_mirror_preferences_path().read_text(encoding="utf-8"))
        return data.get("mirror_x") is True
    except (OSError, ValueError, TypeError):
        return False


def _save_mirror_preference(enabled):
    try:
        path = _mirror_preferences_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except (OSError, ValueError, TypeError):
            data = {}
        data["mirror_x"] = bool(enabled)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, path)
    except OSError:
        pass


class _TkTexture:
    """Wrap Tk's built-in GIF decoder as a mesh RGB pixel source."""

    def __init__(self, photo):
        self._photo = photo
        self.size = (photo.width(), photo.height())

    def load(self):
        return self

    def __getitem__(self, coords):
        pixel = self._photo.get(*coords)
        if isinstance(pixel, str):
            if pixel.startswith("#") and len(pixel) == 7:
                return tuple(int(pixel[i:i + 2], 16) for i in (1, 3, 5))
            return tuple(int(channel) for channel in pixel.split()[:3])
        return tuple(pixel[:3])


def _scene_texture(relative_path, max_size=(512, 512)):
    """Load remote/local scene texture; GIF works with standard Tkinter."""
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Invalid scene texture path")
    root = Path(__file__).resolve().parent
    engine = root if root.name == "engine3d" else root / "engine3d"
    local = engine / relative
    try:
        if local.is_file():
            data = local.read_bytes()
        else:
            if os.environ.get("AMDEV_MODE") == "local":
                raise FileNotFoundError(f"No existe la textura local: {local}")
            url = REPO_RAW_BASE + "/engine3d/" + relative.as_posix()
            request = urllib.request.Request(
                url, headers={"User-Agent": "PYRION/0.4.13"})
            with urllib.request.urlopen(request, timeout=8) as response:
                data = response.read(8 * 1024 * 1024 + 1)
        if len(data) > 8 * 1024 * 1024:
            raise ValueError("Scene texture exceeds 8 MiB")
        try:
            from PIL import Image
            from io import BytesIO
        except ImportError:
            # Fallback to native Tk sampling when Pillow is unavailable.
            photo = tk.PhotoImage(data=base64.b64encode(data).decode("ascii"))
            return _TkTexture(photo)
        with Image.open(BytesIO(data)) as image:
            image.thumbnail(max_size)
            return image.convert("RGB")
    except (OSError, ValueError, urllib.error.URLError, tk.TclError):
        return None


def load_selected_scene():
    selection = _scene_json("scene_selected.json")
    scene_path = Path(selection["selected_scene"])
    scene = _scene_json(scene_path)
    if scene.get("format") != "pyrion.scene":
        raise ValueError("Unsupported scene format")
    background_path = scene.get("background", {}).get("image")
    if background_path:
        scene["_background_image"] = _scene_texture((scene_path.parent / background_path).as_posix(), max_size=(1920, 1080))
    objects = []
    for obj in scene.get("objects", []):
        if not obj.get("visible", True):
            continue
        model_path = (scene_path.parent / obj["model"]).as_posix()
        model = _scene_json(model_path)
        if model.get("format") != "pyrion.mesh":
            raise ValueError("Unsupported model: " + model_path)
        scale = obj.get("scale", [1, 1, 1])
        mesh = _make_model_mesh(model, scale)
        radius = mesh.radius
        position = tuple(float(v) for v in obj.get("position", [0, 0, 0]))
        if len(position) != 3:
            raise ValueError("Invalid model position")
        animation = obj.get("animation", {})
        speed = float(animation.get("speed_degrees_per_second", 0))
        if animation.get("type") != "spin" or animation.get("axis") != [0, 1, 0]:
            speed = 0
        material = model.get("material", {})
        if obj.get("material"):
            material_path = scene_path.parent / obj["material"]
            material = _scene_json(material_path.as_posix())
            if material.get("format") != "pyrion.material":
                raise ValueError("Unsupported material: " + material_path.as_posix())
            material = dict(material)
            if material.get("texture") and material.get("texture_status") == "ready":
                image_path = Path(os.path.normpath(str(
                    material_path.parent / material["texture"]))).as_posix()
                image = _scene_texture(image_path)
                if image is not None:
                    material["_texture_image"] = image
        objects.append({"id": str(obj.get("id", model_path)),
                        "_mesh_path": model_path, "_mesh_source": model,
                        "_mesh_scale": scale,
                        "renderer": SoftwareRenderer(mesh, material=material),
                        "position": position,
                        "render_layer": int(obj.get("render_layer", 0)),
                        "radius": radius, "speed": math.radians(speed),
                        "rotation_x": math.radians(float(obj.get("rotation", [0, 0, 0])[0])),
                        "rotation": math.radians(float(obj.get("rotation", [0, 0, 0])[1]))})
        objects[-1]["renderer"].set_atmosphere(scene.get("fog"))
    return scene, objects




def _hud_cpu_snapshot():
    """Machine-wide CPU counters: (total ticks, idle ticks)."""
    try:
        if sys.platform.startswith("linux"):
            data = Path("/proc/stat").read_text(encoding="ascii").splitlines()[0].split()
            ticks = [float(value) for value in data[1:]]
            return sum(ticks), ticks[3] + (ticks[4] if len(ticks) > 4 else 0)
        if os.name == "nt":
            import ctypes

            class FileTime(ctypes.Structure):
                _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]

            idle, kernel, user = FileTime(), FileTime(), FileTime()
            api = ctypes.WinDLL("kernel32", use_last_error=True)
            api.GetSystemTimes.argtypes = [
                ctypes.POINTER(FileTime), ctypes.POINTER(FileTime), ctypes.POINTER(FileTime)
            ]
            api.GetSystemTimes.restype = ctypes.c_int
            if api.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel),
                                  ctypes.byref(user)):
                def ticks(value):
                    return (value.high << 32) | value.low
                return ticks(kernel) + ticks(user), ticks(idle)
        # psutil is only an optional fallback (not a dependency).
        import psutil
        times = psutil.cpu_times()
        return sum(times), times.idle + getattr(times, "iowait", 0)
    except (OSError, ValueError, IndexError, ImportError, AttributeError):
        return None


def _hud_cpu_usage(previous, current):
    if previous is None or current is None:
        return None
    delta = current[0] - previous[0]
    idle_delta = current[1] - previous[1]
    return max(0.0, min(100.0, 100.0 * (delta - idle_delta) / delta)) if delta > 0 else None


def _hud_system_memory():
    """Percent, used GiB and total GiB of physical RAM on this computer."""
    try:
        if sys.platform.startswith("linux"):
            values = {}
            for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
                key, _, data = line.partition(":")
                values[key] = int(data.split()[0])
            total = values["MemTotal"]
            available = values.get("MemAvailable")
            if available is None:
                available = (values.get("MemFree", 0) + values.get("Buffers", 0)
                             + values.get("Cached", 0))
            used = max(0, total - available)
            return 100.0 * used / total, used / 1048576.0, total / 1048576.0
        if os.name == "nt":
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                    ("total", ctypes.c_ulonglong), ("available", ctypes.c_ulonglong),
                    ("total_pagefile", ctypes.c_ulonglong),
                    ("available_pagefile", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended", ctypes.c_ulonglong),
                ]

            info = MemoryStatus()
            info.length = ctypes.sizeof(info)
            api = ctypes.WinDLL("kernel32", use_last_error=True)
            api.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MemoryStatus)]
            api.GlobalMemoryStatusEx.restype = ctypes.c_int
            if api.GlobalMemoryStatusEx(ctypes.byref(info)) and info.total:
                used = info.total - info.available
                return (100.0 * used / info.total,
                        used / 1073741824.0, info.total / 1073741824.0)
        import psutil
        mem = psutil.virtual_memory()
        return (float(mem.percent), (mem.total - mem.available) / 1073741824.0,
                mem.total / 1073741824.0)
    except (OSError, ValueError, KeyError, ImportError, AttributeError, ZeroDivisionError):
        return None


def _hud_memory_mb():
    """Current RSS of PYRION, not the RAM usage of the full system."""
    try:
        if sys.platform.startswith("linux"):
            status = Path("/proc/self/status").read_text(encoding="ascii")
            for line in status.splitlines():
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
            pages = int(Path("/proc/self/statm").read_text(encoding="ascii").split()[1])
            return pages * os.sysconf("SC_PAGE_SIZE") / 1048576.0
        if os.name == "nt":
            import ctypes

            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("size", ctypes.c_ulong), ("page_faults", ctypes.c_ulong),
                    ("peak_working_set", ctypes.c_size_t),
                    ("working_set", ctypes.c_size_t),
                    ("peak_paged_pool", ctypes.c_size_t),
                    ("paged_pool", ctypes.c_size_t),
                    ("peak_nonpaged_pool", ctypes.c_size_t),
                    ("nonpaged_pool", ctypes.c_size_t),
                    ("pagefile", ctypes.c_size_t),
                    ("peak_pagefile", ctypes.c_size_t),
                ]

            counters = ProcessMemoryCounters()
            counters.size = ctypes.sizeof(counters)
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            kernel.GetCurrentProcess.restype = ctypes.c_void_p
            psapi.GetProcessMemoryInfo.argtypes = [
                ctypes.c_void_p, ctypes.POINTER(ProcessMemoryCounters), ctypes.c_ulong
            ]
            psapi.GetProcessMemoryInfo.restype = ctypes.c_int
            if psapi.GetProcessMemoryInfo(
                kernel.GetCurrentProcess(), ctypes.byref(counters), counters.size
            ):
                return counters.working_set / 1048576.0
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss / 1048576.0
    except (OSError, ValueError, ImportError, AttributeError):
        return None



class Pyrion3DApp(tk.Tk):
    """Minimal full-screen PYRION desktop containing only the rotating sphere."""

    def __init__(self):
        super().__init__()
        self.title("PYRION OS")
        self._engine_generation = 0
        self._engine_after = set()
        self.windowed = (
            "--windowed" in sys.argv or os.environ.get("PYRION_WINDOWED") == "1"
        )
        self._setup_window()
        self.canvas = tk.Canvas(self, bg=BACKGROUND, highlightthickness=0, bd=0,
                                relief="flat", takefocus=1)
        self.canvas.pack(fill="both", expand=True)
        # La ventana y Canvas son el contenedor; todo lo demás pertenece al motor.
        self._shell_keys = set(self.__dict__) | {"_shell_keys", "_control_bindings", "_live_module_name"}
        self._initialize_engine(*load_selected_scene())
        self.configure(bg=self.background)
        self.canvas.configure(bg=self.background)
        self._bind_controls()
        self._start_engine()

    def _initialize_engine(self, scene, objects):
        """Mismo arranque limpio al abrir la app y en cada reset."""
        self.scene, self.objects = scene, objects
        self.background = scene.get("background", {}).get("color", BACKGROUND)
        self.background_image = scene.get("_background_image")
        self._background_cache = None
        self._shadow_cache = None
        self.renderer = self.objects[0]["renderer"] if self.objects else None
        self.spotlight_enabled = True
        for item in self.objects:
            item["renderer"].rotation_y = item["rotation"]
            item["renderer"].rotation_x = item.get("rotation_x", -0.28)
            item["renderer"].material_mode = self.scene.get("material_mode", "mat")
            item["renderer"].set_lights(
                self.scene.get("lights", []),
                ambient=self.scene.get("ambient_light", 0.56)
            )
        self.base_pitch = -0.28
        self.spin_rate = 1.0
        self.running = True
        self.visible_triangles = 0
        self.frames = 0
        self.info_mode = "compacto"
        self.material_mode = self.scene.get("material_mode", "mat")
        self.material_notice = ""
        import queue
        self._update_events = queue.Queue()
        self._update_running = False
        self._mesh_update_events = queue.Queue()
        self._mesh_check_running = False
        self._next_mesh_check = time.monotonic() + 0.1
        self.fps = 0.0
        self.frame_ms = 0.0
        self.render_ms = 0.0
        self.average_fps = 0.0
        self.cpu_percent = 0.0
        self.cpu_render_percent = 0.0
        self.cpu_system_percent = None
        self.system_memory = None
        self.ram_mb = None
        self.update_ms = 0.0
        self._render_cpu_interval = 0.0
        self._last_frame_error = -100.0
        self._system_cpu_prev = _hud_cpu_snapshot()
        self._fps_count = 0
        self._fps_periods = 0
        self._frame_time_history = []
        self.started_at = time.perf_counter()
        self._fps_start = self.started_at
        self._cpu_start = time.process_time()
        self.last_time = time.perf_counter()
        self.drag_start = None
        self.pending_frame = None
        self._width = 1
        self._height = 1
        self._orb_radius = 1
        self._navigation = self.scene.get("navigation", {})
        self._camera_home = {
            "position": list(self._navigation.get(
                "camera_position", [0.0, 0.0, 3.85])),
            "yaw": math.radians(float(
                self._navigation.get("camera_yaw_degrees", 0.0))),
            "pitch": math.radians(float(
                self._navigation.get("camera_pitch_degrees", 0.0)))
        }
        self.camera_pose = self._copy_pose(self._camera_home)
        self._lights = [dict(light) for light in self.scene.get("lights", [])]
        self._spot_index = next(
            (i for i, light in enumerate(self._lights)
             if light.get("type") == "spot" and light.get("enabled", True)),
            None
        )
        self.focus_pose = self._focus_pose_from_scene()
        self.control_mode = "camara"
        self._sticks = {"move": (0.0, 0.0), "look": (0.0, 0.0)}
        self._active_stick = None
        # Preferencia local independiente del archivo .mesh y del repositorio.
        self.mirror_enabled = _load_mirror_preference()
        if self.mirror_enabled:
            for item in self.objects:
                if _mesh_can_mirror(item.get("_mesh_source")):
                    self._replace_item_mesh(item, item["_mesh_source"])


    def _schedule_engine(self, delay, callback):
        generation = self._engine_generation
        timer_id = None

        def fire():
            self._engine_after.discard(timer_id)
            if generation == self._engine_generation:
                callback()

        timer_id = tk.Misc.after(self, delay, fire)
        self._engine_after.add(timer_id)
        return timer_id

    def _cancel_engine_callbacks(self, legacy=False):
        timers = list(self._engine_after)
        if legacy:
            timers = list(self.tk.splitlist(self.tk.call("after", "info")))
        for timer in timers:
            try:
                self.after_cancel(timer)
            except tk.TclError:
                pass
        self._engine_after.clear()

    def _start_engine(self):
        self._schedule_engine(16, self._frame)
        self._schedule_engine(1000, self._keep_as_desktop)
        if not self.windowed and os.name != "nt":
            self._schedule_engine(180, self._repair_fullscreen_geometry)

    def _adopt_legacy_window(self):
        """Primer reset desde versiones previas sin gestor de ciclo de vida."""
        scene, objects = self.scene, self.objects
        keys = {"master", "children", "tk", "_w", "_tclCommands", "_last_child_ids",
                "_tkloaded", "_windowingsystem_cached", "canvas", "windowed", "_live_module_name", "_control_bindings"}
        shell = {key: value for key, value in self.__dict__.items() if key in keys}
        self._engine_after = set()
        self._cancel_engine_callbacks(legacy=True)
        self.__dict__.clear()
        self.__dict__.update(shell)
        self._shell_keys = keys | {"_shell_keys", "_control_bindings", "_engine_after", "_engine_generation"}
        self._engine_after = set()
        self._engine_generation = 1
        self._initialize_engine(scene, objects)
        self._start_engine()

    def _bind_controls(self):
        if "_engine_generation" not in self.__dict__:
            self._adopt_legacy_window()
        for widget, sequence, binding_id in getattr(self, "_control_bindings", []):
            try:
                widget.unbind(sequence, binding_id)
            except tk.TclError:
                pass
        self._control_bindings = []

        def bind(widget, sequence, callback):
            binding_id = widget.bind(sequence, callback)
            self._control_bindings.append((widget, sequence, binding_id))

        bind(self, "<space>", lambda _event: self.toggle_animation())
        bind(self, "<F3>", self._toggle_hud_mode)
        bind(self, "<m>", self._toggle_material_mode)
        bind(self, "<M>", self._toggle_material_mode)
        bind(self, "<Control-m>", self._toggle_mirror)
        bind(self, "<l>", self._toggle_spotlight)
        bind(self, "<L>", self._toggle_spotlight)
        bind(self, "<Tab>", self._toggle_control_mode)
        bind(self, "<r>", self._reset_navigation)
        bind(self, "<R>", self._reset_navigation)
        bind(self, "<Left>", lambda _event: self._speed(-0.15))
        bind(self, "<Right>", lambda _event: self._speed(+0.15))
        bind(self, "<plus>", lambda _event: self._zoom(+0.10))
        bind(self, "<minus>", lambda _event: self._zoom(-0.10))
        bind(self, "<F11>", self._switch_to_window)
        bind(self, "<Escape>", self._switch_to_window)
        bind(self, "<Control-q>", lambda _event: self.close())
        bind(self.canvas, "<ButtonPress-1>", self._mouse_press)
        bind(self.canvas, "<B1-Motion>", self._mouse_move)
        bind(self.canvas, "<ButtonRelease-1>", self._mouse_release)
        bind(self.canvas, "<MouseWheel>", self._scroll)
        bind(self.canvas, "<Button-4>", lambda _event: self._zoom(+0.10))
        bind(self.canvas, "<Button-5>", lambda _event: self._zoom(-0.10))
        bind(self.canvas, "<Configure>", lambda _event: self._request_frame())
        old_protocol = self.protocol("WM_DELETE_WINDOW")
        self.protocol("WM_DELETE_WINDOW", lambda: self.close())
        if old_protocol:
            try:
                self.deletecommand(old_protocol)
            except tk.TclError:
                pass

    @staticmethod
    def _copy_pose(pose):
        return {
            "position": list(pose["position"]),
            "yaw": float(pose["yaw"]),
            "pitch": float(pose["pitch"])
        }

    def _focus_pose_from_scene(self):
        if self._spot_index is None:
            return None
        light = self._lights[self._spot_index]
        position = [float(v) for v in light["position"]]
        target = [float(v) for v in light["target"]]
        delta = [target[k] - position[k] for k in range(3)]
        horizontal = math.hypot(delta[0], delta[2])
        return {
            "position": position,
            "yaw": math.atan2(delta[0], -delta[2]),
            "pitch": math.atan2(delta[1], horizontal),
            "distance": max(0.1, math.sqrt(sum(v * v for v in delta)))
        }

    @staticmethod
    def _pose_forward(pose):
        yaw, pitch = pose["yaw"], pose["pitch"]
        return (
            math.sin(yaw) * math.cos(pitch),
            math.sin(pitch),
            -math.cos(yaw) * math.cos(pitch)
        )

    def _sync_focus_light(self):
        if self._spot_index is None or self.focus_pose is None:
            return
        pose = self.focus_pose
        point = pose["position"]
        direction = self._pose_forward(pose)
        light = self._lights[self._spot_index]
        light["position"] = list(point)
        light["target"] = [
            point[k] + direction[k] * pose["distance"]
            for k in range(3)
        ]
        for item in self.objects:
            item["renderer"].set_lights(
                self._lights, ambient=self.scene.get("ambient_light", 0.56)
            )

    def _toggle_control_mode(self, _event=None):
        if self._spot_index is None:
            return
        self.control_mode = (
            "foco" if self.control_mode == "camara" else "camara"
        )
        self._sticks = {"move": (0.0, 0.0), "look": (0.0, 0.0)}
        self._active_stick = None
        self._request_frame()

    def _reset_navigation(self, _event=None):
        self.camera_pose = self._copy_pose(self._camera_home)
        self._lights = [dict(light) for light in self.scene.get("lights", [])]
        self.focus_pose = self._focus_pose_from_scene()
        self._sticks = {"move": (0.0, 0.0), "look": (0.0, 0.0)}
        self._active_stick = None
        self._sync_focus_light()
        self._request_frame()

    def _advance_navigation(self, seconds):
        move_x, move_y = self._sticks["move"]
        look_x, look_y = self._sticks["look"]
        if max(abs(move_x), abs(move_y), abs(look_x), abs(look_y)) < 0.015:
            return
        pose = (self.camera_pose if self.control_mode == "camara"
                else self.focus_pose)
        if pose is None:
            return
        walk_speed = max(0.1, min(12.0, float(
            self._navigation.get("walk_speed", 1.9)
        )))
        turn_speed = math.radians(float(
            self._navigation.get("turn_speed_degrees", 95.0)
        ))
        look_speed = math.radians(float(
            self._navigation.get("look_speed_degrees", 115.0)
        ))
        # Tank steering stays horizontal; the other stick tilts the view.
        pose["yaw"] += (move_x * turn_speed + look_x * look_speed) * seconds
        pose["pitch"] = max(-1.35, min(
            1.35, pose["pitch"] - look_y * look_speed * seconds
        ))
        distance = -move_y * walk_speed * seconds
        pose["position"][0] += math.sin(pose["yaw"]) * distance
        pose["position"][2] -= math.cos(pose["yaw"]) * distance
        if self.control_mode == "foco":
            self._sync_focus_light()

    def _analog_geometry(self, name):
        radius = max(32.0, min(
            57.0, self._width * 0.09, self._height * 0.14
        ))
        center_x = (
            23.0 + radius if name == "move"
            else self._width - 23.0 - radius
        )
        center_y = self._height - 23.0 - radius
        return center_x, center_y, radius

    def _navigation_button_bounds(self):
        mid = self._width * 0.5
        top = self._height - (79 if self._width >= 540 else 165)
        return (
            (mid - 145, top, mid - 12, top + 34),
            (mid + 12, top, mid + 137, top + 34)
        )

    def _navigation_mouse_press(self, event):
        for index, rect in enumerate(self._navigation_button_bounds()):
            x1, y1, x2, y2 = rect
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                if index == 0:
                    self._toggle_control_mode()
                else:
                    self._reset_navigation()
                return True
        for name in ("move", "look"):
            cx, cy, radius = self._analog_geometry(name)
            if ((event.x - cx) ** 2 + (event.y - cy) ** 2
                    <= (radius + 14) ** 2):
                self._active_stick = name
                self._move_analog_thumb(event)
                return True
        return False

    def _move_analog_thumb(self, event):
        if self._active_stick is None:
            return
        cx, cy, radius = self._analog_geometry(self._active_stick)
        x = (event.x - cx) / radius
        y = (event.y - cy) / radius
        length = math.hypot(x, y)
        if length > 1.0:
            x /= length
            y /= length
        if math.hypot(x, y) < 0.08:
            x, y = 0.0, 0.0
        self._sticks[self._active_stick] = (x, y)
        self._request_frame()

    def _draw_analog_controls(self):
        canvas = self.canvas
        for name, text in (("move", "TANQUE"), ("look", "MIRAR")):
            cx, cy, radius = self._analog_geometry(name)
            dx, dy = self._sticks[name]
            canvas.create_oval(
                cx - radius, cy - radius, cx + radius, cy + radius,
                fill="#0e1d32", outline="#486b8e", width=2
            )
            canvas.create_line(
                cx - radius * 0.62, cy, cx + radius * 0.62, cy,
                fill="#294463", width=1
            )
            canvas.create_line(
                cx, cy - radius * 0.62, cx, cy + radius * 0.62,
                fill="#294463", width=1
            )
            thumb_x = cx + dx * radius * 0.72
            thumb_y = cy + dy * radius * 0.72
            canvas.create_line(
                cx, cy, thumb_x, thumb_y, fill="#83b6df", width=3
            )
            knob = max(11.0, radius * 0.24)
            canvas.create_oval(
                thumb_x - knob, thumb_y - knob,
                thumb_x + knob, thumb_y + knob,
                fill="#3e709b", outline="#a4d8fd", width=2
            )
            canvas.create_text(
                cx, cy - radius - 14, text=text,
                fill="#c7e5ff", font=("TkDefaultFont", 9, "bold")
            )
        mode_rect, reset_rect = self._navigation_button_bounds()
        for rect, title, active in (
            (mode_rect, "CONTROL: " + self.control_mode.upper(), True),
            (reset_rect, "RESET POS.", False)
        ):
            x1, y1, x2, y2 = rect
            canvas.create_rectangle(
                x1, y1, x2, y2,
                fill="#203c59" if active else "#182d45",
                outline="#6796bd", width=1
            )
            canvas.create_text(
                (x1 + x2) * 0.5, (y1 + y2) * 0.5,
                text=title, fill="#d9ecff",
                font=("TkDefaultFont", 9, "bold")
            )

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
            self._schedule_engine(1250, self._keep_as_desktop)
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
        self._engine_generation += 1
        self._cancel_engine_callbacks()
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
        if self._hud_click(event) or self._navigation_mouse_press(event):
            return
        cx, cy = self._width / 2, self._height / 2
        if (event.x - cx) ** 2 + (event.y - cy) ** 2 <= self._orb_radius ** 2:
            self.drag_start = (event.x, event.y)

    def _mouse_move(self, event):
        if self._active_stick is not None:
            self._move_analog_thumb(event)
            return
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
        if self._active_stick is not None:
            self._sticks[self._active_stick] = (0.0, 0.0)
            self._active_stick = None
            self._request_frame()

    def _scroll(self, event):
        self._zoom(0.10 if event.delta > 0 else -0.10)

    def _request_frame(self):
        if self.pending_frame is None:
            self.pending_frame = self._schedule_engine("idle", self._draw)

    def _replace_item_mesh(self, item, source):
        """Renueva solo la geometría; mantiene giro, material y cámara."""
        geometry = _make_visible_mesh(
            source, item["_mesh_scale"], self.mirror_enabled)
        original = item["renderer"]
        replacement = SoftwareRenderer(geometry, material=original.material)
        for name in ("rotation_x", "rotation_y", "zoom", "wireframe",
                     "camera_distance", "material_mode", "spotlight_enabled"):
            setattr(replacement, name, getattr(original, name))
        replacement.set_lights(
            self._lights, ambient=self.scene.get("ambient_light", 0.56))
        replacement.set_atmosphere(self.scene.get("fog"))
        item["renderer"] = replacement
        item["radius"] = geometry.radius
        if self.renderer is original:
            self.renderer = replacement

    def _mirror_button_bounds(self):
        if self._width >= 760:
            return (590, 16, 732, 40)
        if self._width >= 620:
            return (20, 57, 162, 81)
        if self._width >= 520:
            return (290, 57, 432, 81)
        return (20, 90, 162, 114)

    def _toggle_mirror(self, _event=None):
        available = any(
            _mesh_can_mirror(item.get("_mesh_source")) for item in self.objects)
        if not available:
            return
        self.mirror_enabled = not self.mirror_enabled
        try:
            for item in self.objects:
                if _mesh_can_mirror(item.get("_mesh_source")):
                    self._replace_item_mesh(item, item["_mesh_source"])
        except (ValueError, TypeError, KeyError, AttributeError):
            # No perder el estado anterior si una geometría es inválida.
            self.mirror_enabled = not self.mirror_enabled
            for item in self.objects:
                if _mesh_can_mirror(item.get("_mesh_source")):
                    self._replace_item_mesh(item, item["_mesh_source"])
            return
        _save_mirror_preference(self.mirror_enabled)
        self._shadow_cache = None
        self._request_frame()

    def _begin_mesh_check(self):
        """Consulta GitHub en un hilo, sin congelar el motor ni el giro."""
        if self._mesh_check_running:
            return
        pending = [
            (index, item["_mesh_path"], item["_mesh_source"], item["_mesh_scale"])
            for index, item in enumerate(self.objects)
            if "_mesh_path" in item
        ]
        if not pending:
            return
        import threading
        self._mesh_check_running = True
        queue_ref = self._mesh_update_events

        def worker():
            updates = []
            for index, path, old, scale in pending:
                try:
                    model = _fetch_updated_mesh(path, old, scale)
                    if model is not None:
                        updates.append((index, path, old, model))
                except (OSError, ValueError, KeyError, TypeError,
                        urllib.error.URLError, TimeoutError):
                    # Sin conexion o malla no valida: mantener la version visible.
                    continue
            queue_ref.put(updates)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_mesh_updates(self):
        """Cambiar solo renderer/mesh en hilo Tk; conservar camara y rotacion."""
        import queue
        try:
            updates = self._mesh_update_events.get_nowait()
        except queue.Empty:
            return
        self._mesh_check_running = False
        changed = False
        for index, path, previous, model in updates:
            if index >= len(self.objects):
                continue
            item = self.objects[index]
            if item.get("_mesh_path") != path or item.get("_mesh_source") != previous:
                continue
            try:
                self._replace_item_mesh(item, model)
                item["_mesh_source"] = model
                changed = True
            except (ValueError, TypeError, KeyError, AttributeError):
                continue
        if changed:
            self._shadow_cache = None
            self._request_frame()

    def _draw_background(self, width, height):
        source = self.background_image
        if source is None:
            return
        key = (id(source), width, height)
        if self._background_cache is None or self._background_cache[0] != key:
            if hasattr(source, "convert"):
                from PIL import Image, ImageOps
                fitted = ImageOps.fit(source, (width, height), method=Image.Resampling.BILINEAR)
                if hasattr(self.canvas, "draw_surface"):
                    photo = fitted
                else:
                    from PIL import ImageTk
                    photo = ImageTk.PhotoImage(fitted, master=self.canvas)
                anchor = "nw"
            else:
                # Native Tk fallback: scale to cover the viewport without distortion.
                original = source._photo
                ratio = max(width / original.width(), height / original.height())
                photo = original.zoom(max(1, math.ceil(ratio))) if ratio > 1 else original.subsample(max(1, int(1 / ratio)))
                anchor = "center"
            self._background_cache = (key, photo, anchor)
        _, photo, anchor = self._background_cache
        if hasattr(self.canvas, "draw_surface"):
            self.canvas.draw_surface(photo, 0, 0)
        else:
            x, y = (0, 0) if anchor == "nw" else (width / 2, height / 2)
            self.canvas.create_image(x, y, anchor=anchor, image=photo)

    def _draw_contact_shadows(self, width, height, diameter):
        shadows = self.scene.get("contact_shadows", [])
        if not shadows:
            return
        pose = self.camera_pose
        renderer = getattr(self, "renderer", None)
        zoom = renderer.zoom if renderer is not None else 1.0
        key = (width, height, diameter, tuple(pose["position"]), pose["yaw"], pose["pitch"], zoom, id(self.scene))
        if self._shadow_cache is None or self._shadow_cache[0] != key:
            try:
                from PIL import Image, ImageDraw, ImageFilter
            except ImportError:
                return
            image = Image.new("RGBA", (width, height))
            draw = ImageDraw.Draw(image)
            yaw, pitch = pose["yaw"], pose["pitch"]
            right = (math.cos(yaw), 0, math.sin(yaw))
            up = (-math.sin(yaw)*math.sin(pitch), math.cos(pitch), math.cos(yaw)*math.sin(pitch))
            forward = self._pose_forward(pose)
            focal = max(50, diameter * 3.85 * 0.47 * zoom)
            ground = float(self.scene.get("ground_y", -2.4)) + 0.02
            for shadow in shadows:
                points = []
                for i in range(24):
                    angle = i*math.tau/24
                    world = (shadow["x"] + math.cos(angle)*shadow["radius_x"], ground,
                             shadow["z"] + math.sin(angle)*shadow["radius_z"])
                    delta = tuple(world[k]-pose["position"][k] for k in range(3))
                    depth = sum(delta[k]*forward[k] for k in range(3))
                    if depth <= 0.32:
                        points = []
                        break
                    points.append((width/2 + sum(delta[k]*right[k] for k in range(3))*focal/depth,
                                   height/2 - sum(delta[k]*up[k] for k in range(3))*focal/depth))
                if points:
                    alpha = round(255*max(0, min(1, shadow.get("opacity", 0.38))))
                    draw.polygon(points, fill=(5, 12, 18, alpha))
            image = image.filter(ImageFilter.GaussianBlur(5))
            if hasattr(self.canvas, "draw_surface"):
                photo = image
            else:
                from PIL import ImageTk
                photo = ImageTk.PhotoImage(image, master=self.canvas)
            self._shadow_cache = (key, photo)
        photo = self._shadow_cache[1]
        if hasattr(self.canvas, "draw_surface"):
            self.canvas.draw_surface(photo, 0, 0)
        else:
            self.canvas.create_image(0, 0, anchor="nw", image=photo)

    def _draw(self):
        self.pending_frame = None
        if not self.winfo_exists():
            return
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        if width < 100 or height < 100:
            return
        self._width, self._height = width, height
        draw_start = time.perf_counter()
        cpu_draw_start = time.process_time()
        self.canvas.delete("all")
        self._draw_background(width, height)
        diameter = min(height * 0.60, width * 0.48, 520)
        self._orb_radius = diameter * 0.50
        self.visible_triangles = 0
        eye = self.camera_pose["position"]
        forward = self._pose_forward(self.camera_pose)
        ordered = sorted(
            self.objects,
            key=lambda obj: (obj.get("render_layer", 0), -sum(
                (obj["position"][k] - eye[k]) * forward[k]
                for k in range(3)
            ))
        )
        shadows_drawn = False
        for item in ordered:
            if not shadows_drawn and item.get("render_layer", 0) >= 0:
                self._draw_contact_shadows(width, height, diameter)
                shadows_drawn = True
            renderer = item["renderer"]
            self.visible_triangles += renderer.draw(
                self.canvas, width / 2, height / 2, diameter,
                draw_graticules=False,
                object_position=item["position"],
                camera_position=eye,
                camera_yaw=self.camera_pose["yaw"],
                camera_pitch=self.camera_pose["pitch"]
            )
        self.render_ms = (time.perf_counter() - draw_start) * 1000.0
        self._render_cpu_interval += max(0.0, time.process_time() - cpu_draw_start)
        self._draw_hud()
        self._draw_analog_controls()


    def _material_button_bounds(self):
        if self._width >= 480:
            return (316, 16, 456, 40)
        return (20, 57, 160, 81)

    def _spotlight_button_bounds(self):
        if self._width >= 620:
            return (466, 16, 578, 40)
        return (168, 57, 280, 81)

    def _toggle_spotlight(self, _event=None):
        self.spotlight_enabled = not self.spotlight_enabled
        for item in self.objects:
            item["renderer"].spotlight_enabled = self.spotlight_enabled
        self._request_frame()

    def _toggle_material_mode(self, _event=None):
        target = "img" if self.material_mode == "mat" else "mat"
        if target == "img" and not any(
            item["renderer"].has_image_texture for item in self.objects
        ):
            self.material_notice = "IMG NO DISPONIBLE"
        else:
            self.material_mode = target
            for item in self.objects:
                item["renderer"].material_mode = target
            self.material_notice = ""
        self._request_frame()

    def _hud_click(self, event):
        if self._width < 360:
            return False
        mx1, my1, mx2, my2 = self._mirror_button_bounds()
        if mx1 <= event.x <= mx2 and my1 <= event.y <= my2:
            self._toggle_mirror()
            return True
        if 16 <= event.x <= 40 and 14 <= event.y <= 38:
            self._check_updates_now()
            return True
        lx1, ly1, lx2, ly2 = self._spotlight_button_bounds()
        if lx1 <= event.x <= lx2 and ly1 <= event.y <= ly2:
            self._toggle_spotlight()
            return True
        x1, y1, x2, y2 = self._material_button_bounds()
        if x1 <= event.x <= x2 and y1 <= event.y <= y2:
            self._toggle_material_mode()
            return True
        if 208 <= event.x <= 306 and 16 <= event.y <= 40:
            self.info_mode = "diagnostico" if self.info_mode == "compacto" else "compacto"
            self._request_frame()
            return True
        return False

    def _check_updates_now(self):
        if self._update_running:
            return
        import threading
        self._update_running = True
        self._request_frame()

        def worker():
            try:
                checker = globals().get("check_self_update")
                if checker is None:
                    # El modo modular utiliza el mismo actualizador que app.py.
                    import runpy
                    target = Path(__file__).resolve().parent.parent / "app.py"
                    checker = runpy.run_path(str(target))["check_self_update"]
                    checker.__globals__["APP_VERSION"] = DESKTOP_VERSION
                updated = checker(restart=False, raise_errors=True)
                self._update_events.put(("done", updated))
            except Exception as exc:
                self._update_events.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()
        self._schedule_engine(100, self._poll_manual_update)

    def _poll_manual_update(self):
        import queue
        from tkinter import messagebox
        try:
            kind, result = self._update_events.get_nowait()
        except queue.Empty:
            self._schedule_engine(100, self._poll_manual_update)
            return
        self._update_running = False
        self._request_frame()
        if kind == "error":
            messagebox.showerror("PYRION", f"No se pudo buscar la actualización:\n\n{result}", parent=self)
        else:
            try:
                self._refresh_live()
            except Exception as exc:
                messagebox.showerror("PYRION", f"No se pudo refrescar. La sesión actual se conserva:\n\n{exc}", parent=self)

    def _refresh_live(self):
        """El contenedor permanece; código y estado del motor se reconstruyen."""
        import types
        current = Path(__file__).resolve()
        target = current.parent.parent / "app.py" if current.parent.name == "engine3d" else current
        module_name = f"_pyrion_live_{time.time_ns()}"
        module = types.ModuleType(module_name)
        module.__file__ = str(target)
        sys.modules[module_name] = module
        old_class = self.__class__
        old_state = self.__dict__.copy()
        committed = False
        try:
            source = target.read_text(encoding="utf-8-sig")
            exec(compile(source, str(target), "exec"), module.__dict__)
            config = json.loads(target.with_name("config.json").read_text(encoding="utf-8-sig"))
            if module.APP_VERSION != str(config.get("version", "")):
                raise RuntimeError("El código nuevo no coincide con la versión de config.json")
            engine_dir = target.parent / "engine3d"
            if os.environ.get("AMDEV_MODE") == "local" and all((engine_dir / f"{name}.py").is_file() for name in ("mesh", "renderer", "app")):
                # Paquete aislado: también se recompilan los módulos locales, sin
                # reutilizar imports ni archivos .pyc de la generación anterior.
                package = types.ModuleType(module_name)
                package.__path__ = [str(engine_dir)]
                package.__package__ = module_name
                sys.modules[module_name] = package
                for name in ("mesh", "renderer", "app"):
                    path = engine_dir / f"{name}.py"
                    child = types.ModuleType(f"{module_name}.{name}")
                    child.__file__ = str(path)
                    child.__package__ = module_name
                    sys.modules[child.__name__] = child
                    exec(compile(path.read_text(encoding="utf-8-sig"), str(path), "exec"), child.__dict__)
                    setattr(package, name, child)
                module = package.app
                if module.DESKTOP_VERSION != str(config.get("version", "")):
                    raise RuntimeError("La versión de engine3d no coincide con config.json")
            new_class = module.Pyrion3DApp
            scene, objects = module.load_selected_scene()
            candidate = object.__new__(new_class)
            # Conservar únicamente el contenedor Tk, no atributos del motor anterior.
            candidate.__dict__ = {key: old_state[key] for key in self._shell_keys if key in old_state}
            candidate._engine_generation = self._engine_generation + 1
            candidate._engine_after = set()
            candidate._initialize_engine(scene, objects)
            candidate._live_module_name = module_name

            committed = True
            self._cancel_engine_callbacks()
            self.__class__ = new_class
            self.__dict__.clear()
            self.__dict__.update(candidate.__dict__)
            self.configure(bg=self.background)
            self.canvas.configure(bg=self.background)
            self.canvas.delete("all")
            self._bind_controls()
            self._start_engine()
            self._request_frame()
        except Exception:
            if not committed:
                for name in list(sys.modules):
                    if name == module_name or name.startswith(module_name + "."):
                        sys.modules.pop(name, None)
                raise
            try:
                self._cancel_engine_callbacks()
            finally:
                self.__class__ = old_class
                self.__dict__.clear()
                self.__dict__.update(old_state)
                self._engine_after = set()
                self.pending_frame = None
                self.configure(bg=self.background)
                self.canvas.configure(bg=self.background)
                self._bind_controls()
                self._start_engine()
                self._request_frame()
                for name in list(sys.modules):
                    if name == module_name or name.startswith(module_name + "."):
                        sys.modules.pop(name, None)
            raise
        previous_module = old_state.get("_live_module_name")
        if previous_module:
            for name in list(sys.modules):
                if name == previous_module or name.startswith(previous_module + "."):
                    sys.modules.pop(name, None)

    def _toggle_hud_mode(self, _event=None):
        self.info_mode = "diagnostico" if self.info_mode == "compacto" else "compacto"
        self._request_frame()

    def _draw_hud(self):
        if self._width < 360:
            return
        canvas = self.canvas
        x, right = 20, 308
        full = self.info_mode == "diagnostico"
        canvas.create_rectangle(16, 14, 40, 38, fill="#10243c", outline="#345878")
        canvas.create_text(28, 26, text="…" if self._update_running else "↻",
                           fill="#ffd895" if self._update_running else "#71cfff",
                           font=("Segoe UI Symbol", 15))
        name = str(self.scene.get("name", "Scene"))
        name = name if len(name) <= 9 else name[:8] + "…"
        canvas.create_text(48, 20, text="PYRION 3D / " + name,
                           anchor="nw", fill="#71cfff", font=("TkDefaultFont", 9, "bold"))
        canvas.create_text(x, 38,
                           text=f"VERSIÓN {DESKTOP_VERSION} · MOTOR 3D {ENGINE_VERSION}",
                           anchor="nw", fill="#7894b7", font=("TkDefaultFont", 8))
        canvas.create_rectangle(208, 16, 306, 40, outline="#345878",
                                fill="#10243c", width=1)
        canvas.create_text(257, 28, text="COMPACTO" if full else "DETALLES",
                           fill="#d5eaff", font=("TkDefaultFont", 9))
        bx1, by1, bx2, by2 = self._material_button_bounds()
        canvas.create_rectangle(
            bx1, by1, bx2, by2, outline="#547b98",
            fill="#244057" if self.material_mode == "img" else "#10243c",
            width=1
        )
        canvas.create_text(
            (bx1 + bx2) / 2, (by1 + by2) / 2,
            text="MATERIAL: " + self.material_mode.upper(),
            fill="#ffd895" if self.material_mode == "img" else "#d5eaff",
            font=("TkDefaultFont", 9, "bold")
        )
        if self.material_notice:
            canvas.create_text(
                bx1, by2 + 4, anchor="nw", text=self.material_notice,
                fill="#ff9e82", font=("TkDefaultFont", 8)
            )
        mx1, my1, mx2, my2 = self._mirror_button_bounds()
        can_mirror = any(
            _mesh_can_mirror(item.get("_mesh_source")) for item in self.objects)
        canvas.create_rectangle(mx1, my1, mx2, my2,
                                outline="#6b81ae" if can_mirror else "#3a4356",
                                fill="#233656" if can_mirror and self.mirror_enabled else "#10243c",
                                width=1)
        canvas.create_rectangle(mx1 + 8, my1 + 6, mx1 + 20, my1 + 18,
                                outline="#9ab6df" if can_mirror else "#556178",
                                fill="#18253d", width=1)
        if self.mirror_enabled and can_mirror:
            canvas.create_line(mx1 + 10, my1 + 12, mx1 + 13, my1 + 15,
                               mx1 + 18, my1 + 8, fill="#7ff1c9", width=2)
        canvas.create_text(mx1 + 27, (my1 + my2) / 2, text="ESPEJO X",
                           anchor="w", fill="#e3edff" if can_mirror else "#697b9b",
                           font=("TkDefaultFont", 9, "bold"))
        sx1, sy1, sx2, sy2 = self._spotlight_button_bounds()
        canvas.create_rectangle(
            sx1, sy1, sx2, sy2, outline="#826e49",
            fill="#46361f" if self.spotlight_enabled else "#10243c", width=1
        )
        canvas.create_text(
            (sx1 + sx2) / 2, (sy1 + sy2) / 2,
            text="FOCO: ON" if self.spotlight_enabled else "FOCO: OFF",
            fill="#ffe09b" if self.spotlight_enabled else "#9eafc3",
            font=("TkDefaultFont", 9, "bold")
        )
        status = ("MEDIENDO" if self.fps <= 0 else "FLUIDO" if self.fps >= 50
                  else "ACEPTABLE" if self.fps >= 25 else "LENTO")
        if not self.running:
            status = "PAUSADO"
        status_color = ("#ff8194" if status == "LENTO" else
                        "#f4c376" if status in ("ACEPTABLE", "MEDIENDO") else "#75e2ad")

        def fmt(value, suffix="", decimals=1):
            if value is None:
                return "--"
            # Format the number first; a literal percent suffix must not be
            # interpreted as another Python percent-format placeholder.
            return f"{value:.{decimals}f}{suffix}"

        memory = self.system_memory
        cores = max(1, os.cpu_count() or 1)
        process_cpu = self.cpu_percent / cores
        render_cpu = self.cpu_render_percent / cores
        ratio = (100.0 * self.render_ms / self.frame_ms
                 if self.frame_ms > 0 else None)
        ratio = min(100.0, ratio) if ratio is not None else None
        if not full:
            rows = [
                ("FPS", fmt(self.fps)),
                ("FRAME", fmt(self.frame_ms, " ms")),
                ("RENDER 3D", fmt(self.render_ms, " ms")),
                ("CPU PYRION", fmt(process_cpu, "%")),
                ("RAM PYRION", fmt(self.ram_mb, " MB")),
                ("TRIANGULOS", str(self.visible_triangles)),
                ("ESTADO", status),
            ]
        else:
            frames = sorted(self._frame_time_history, reverse=True)
            nslow = max(1, math.ceil(len(frames) * 0.01))
            low_fps = nslow / sum(frames[:nslow]) if len(frames) >= 60 else None
            vertices = sum(len(o["renderer"].mesh.vertices) for o in self.objects)
            faces = sum(len(o["renderer"].mesh.faces) for o in self.objects)
            up = int(time.perf_counter() - self.started_at)
            rows = [
                ("#SISTEMA", ""),
                ("CPU EQUIPO", fmt(self.cpu_system_percent, "%")),
                ("RAM EQUIPO", fmt(memory[0], "%") if memory else "--"),
                ("RAM USADA", ("%.1f / %.1f GB" % (memory[1], memory[2])) if memory else "--"),
                ("NUCLEOS LOG.", str(cores)),
                ("#PYRION", ""),
                ("CPU PYRION", fmt(process_cpu, "%")),
                ("CPU 1 NUCLEO", fmt(self.cpu_percent, "%")),
                ("RAM PYRION", fmt(self.ram_mb, " MB")),
                ("TIEMPO ACTIVO", "%02d:%02d:%02d" % (
                    up // 3600, (up // 60) % 60, up % 60)),
                ("#MOTOR 3D", ""),
                ("ESCENA", str(self.scene.get("name", "Scene"))),
                ("FPS", fmt(self.fps)),
                ("FPS PROMEDIO", fmt(self.average_fps)),
                ("FPS 1% BAJO", fmt(low_fps)),
                ("FRAME", fmt(self.frame_ms, " ms")),
                ("RENDER", fmt(self.render_ms, " ms")),
                ("UPDATE", fmt(self.update_ms, " ms")),
                ("CPU RENDER", fmt(render_cpu, "%")),
                ("% FRAME 3D", fmt(ratio, "%")),
                ("MODELOS", str(len(self.objects))),
                ("CONTROL", self.control_mode.upper()),
                ("CAM POS", ", ".join("%.2f" % v for v in
                                    self.camera_pose["position"])),
                ("FOCO POS", (", ".join("%.2f" % v for v in
                             self.focus_pose["position"])
                             if self.focus_pose else "--")),
                ("VERTICES", str(vertices)),
                ("TRIANGULOS", "%s / %s" % (self.visible_triangles, faces)),
                ("ANIMACION", "ACTIVA" if self.running else "PAUSADA"),
                ("ESTADO", status),
            ]
        y = (104 if 620 <= self._width < 760 else
             135 if self._width < 520 else
             66 if self._width >= 620 else 105)
        for label, value in rows:
            if y + 15 >= self._height:
                break
            if label.startswith("#"):
                canvas.create_text(x, y + 1, text=label[1:], anchor="nw",
                                   fill="#71cfff", font=("TkDefaultFont", 9, "bold"))
                y += 22
                continue
            canvas.create_text(x, y, text=label, anchor="nw",
                               fill="#92aaca", font=("TkDefaultFont", 9))
            canvas.create_text(right, y, text=value, anchor="ne",
                               fill=status_color if label == "ESTADO" else "#d1e6fa",
                               font=("TkDefaultFont", 9))
            y += 18

    def _frame(self):
        try:
            now = time.perf_counter()
            self._apply_mesh_updates()
            mesh_now = time.monotonic()
            if mesh_now >= self._next_mesh_check:
                self._next_mesh_check = mesh_now + MESH_REFRESH_SECONDS
                self._begin_mesh_check()
            raw_elapsed = max(0.0, now - self.last_time)
            self.last_time = now
            elapsed = min(0.1, raw_elapsed)  # Cap animation delta, not FPS measurements.
            update_start = time.perf_counter()
            self._advance_navigation(elapsed)
            if self.running:
                for item in self.objects:
                    renderer = item["renderer"]
                    renderer.rotation_y = (
                        renderer.rotation_y + item["speed"] * self.spin_rate * elapsed
                    ) % (math.pi * 2)
            self.update_ms = (time.perf_counter() - update_start) * 1000.0
            self.frames += 1
            self._fps_count += 1
            if raw_elapsed > 0:
                self._frame_time_history.append(raw_elapsed)
                self._frame_time_history = self._frame_time_history[-600:]
            interval = now - self._fps_start
            if interval >= 0.6:
                self.fps = self._fps_count / interval
                self.frame_ms = 1000.0 / self.fps if self.fps else 0.0
                self._fps_periods += 1
                self.average_fps += (self.fps - self.average_fps) / self._fps_periods
                self.cpu_percent = 100.0 * max(
                    0.0, time.process_time() - self._cpu_start
                ) / interval
                self.cpu_render_percent = 100.0 * self._render_cpu_interval / interval
                system_snapshot = _hud_cpu_snapshot()
                self.cpu_system_percent = _hud_cpu_usage(
                    self._system_cpu_prev, system_snapshot
                )
                self._system_cpu_prev = system_snapshot
                self.system_memory = _hud_system_memory()
                self.ram_mb = _hud_memory_mb()
                self._render_cpu_interval = 0.0
                self._cpu_start = time.process_time()
                self._fps_count = 0
                self._fps_start = now
            self._draw()
        except tk.TclError:
            return
        except Exception:
            # A HUD/metrics exception must never permanently stop the desktop.
            error_now = time.monotonic()
            if error_now - self._last_frame_error >= 5.0:
                self._last_frame_error = error_now
                try:
                    import traceback
                    log_path = Path.home() / "pyrion_error.log"
                    with log_path.open("a", encoding="utf-8") as log:
                        log.write("\\n[PYRION 3D frame]\\n")
                        log.write(traceback.format_exc())
                except OSError:
                    pass
        finally:
            try:
                if self.winfo_exists():
                    self._schedule_engine(16, self._frame)
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
