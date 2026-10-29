"""PYRION OS: a single infinitely rotating 3D sphere at screen center.

The desktop has no panels, labels, orbital rings or visible UI controls.
The UV-sphere geometry and software renderer are provided by PYRION Engine.
"""
import math
import json
import urllib.request
from pathlib import Path
import os
import sys
import time
import tkinter as tk

from .mesh import SphereMesh
from .renderer import SoftwareRenderer

ENGINE_VERSION = "0.2.0"
DESKTOP_VERSION = "0.4.6"
BACKGROUND = "#050917"
REPO_RAW_BASE = "https://raw.githubusercontent.com/mobatfb/archmoba-config/main/PYRION"



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
    request = urllib.request.Request(url, headers={"User-Agent": "PYRION/0.4.6"})
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8-sig"))


def _scene_texture(relative_path):
    """Optional JPEG/PNG texture; scene remains usable without Pillow."""
    try:
        from PIL import Image
        from io import BytesIO
    except ImportError:
        return None
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
            url = REPO_RAW_BASE + "/engine3d/" + relative.as_posix()
            request = urllib.request.Request(
                url, headers={"User-Agent": "PYRION/0.4.6"})
            with urllib.request.urlopen(request, timeout=8) as response:
                data = response.read(8 * 1024 * 1024 + 1)
        if len(data) > 8 * 1024 * 1024:
            raise ValueError("Scene texture exceeds 8 MiB")
        with Image.open(BytesIO(data)) as image:
            image.thumbnail((512, 512))
            return image.convert("RGB")
    except (OSError, ValueError, urllib.error.URLError):
        return None


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
        material = model.get("material", {})
        if obj.get("material"):
            material_path = scene_path.parent / obj["material"]
            material = _scene_json(material_path.as_posix())
            if material.get("format") != "pyrion.material":
                raise ValueError("Unsupported material: " + material_path.as_posix())
            material = dict(material)
            if material.get("texture") and material.get("texture_status") == "ready":
                image_path = (material_path.parent / material["texture"]).as_posix()
                image = _scene_texture(image_path)
                if image is not None:
                    material["_texture_image"] = image
        objects.append({"renderer": SoftwareRenderer(mesh, material=material),
                        "position": position,
                        "radius": radius, "speed": math.radians(speed),
                        "rotation": math.radians(float(obj.get("rotation", [0, 0, 0])[1]))})
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
        draw_start = time.perf_counter()
        cpu_draw_start = time.process_time()
        self.canvas.delete("all")
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
        self._render_cpu_interval += max(0.0, time.process_time() - cpu_draw_start)
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
        x, right = 20, 308
        full = self.info_mode == "diagnostico"
        canvas.create_text(x, 20, text="PYRION 3D / " + str(self.scene.get("name", "Scene")),
                           anchor="nw", fill="#71cfff", font=("TkDefaultFont", 9, "bold"))
        canvas.create_rectangle(208, 16, 306, 40, outline="#345878",
                                fill="#10243c", width=1)
        canvas.create_text(257, 28, text="COMPACTO" if full else "DETALLES",
                           fill="#d5eaff", font=("TkDefaultFont", 9))
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
                ("VERTICES", str(vertices)),
                ("TRIANGULOS", "%s / %s" % (self.visible_triangles, faces)),
                ("ANIMACION", "ACTIVA" if self.running else "PAUSADA"),
                ("ESTADO", status),
            ]
        y = 51
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
            raw_elapsed = max(0.0, now - self.last_time)
            self.last_time = now
            elapsed = min(0.1, raw_elapsed)  # Cap animation delta, not FPS measurements.
            update_start = time.perf_counter()
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
                    self.after(16, self._frame)
            except tk.TclError:
                pass


def run():
    app = Pyrion3DApp()
    app.mainloop()


if __name__ == "__main__":
    run()
