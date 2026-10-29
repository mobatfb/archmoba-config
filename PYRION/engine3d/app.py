"""PYRION OS: a single infinitely rotating 3D sphere at screen center.

The desktop has no panels, labels, orbital rings or visible UI controls.
The UV-sphere geometry and software renderer are provided by PYRION Engine.
"""
import base64
import math
import json
import urllib.request
from pathlib import Path
import os
import sys
import time
import tkinter as tk

from .mesh import SphereMesh, TriangleMesh
from .renderer import SoftwareRenderer

ENGINE_VERSION = "0.4.0"
DESKTOP_VERSION = "0.4.13"
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
    request = urllib.request.Request(url, headers={"User-Agent": "PYRION/0.4.13"})
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8-sig"))


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


def _scene_texture(relative_path):
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
            url = REPO_RAW_BASE + "/engine3d/" + relative.as_posix()
            request = urllib.request.Request(
                url, headers={"User-Agent": "PYRION/0.4.13"})
            with urllib.request.urlopen(request, timeout=8) as response:
                data = response.read(8 * 1024 * 1024 + 1)
        if len(data) > 8 * 1024 * 1024:
            raise ValueError("Scene texture exceeds 8 MiB")
        if relative.suffix.lower() == ".gif":
            # Tkinter understands GIF natively: no Pillow installation needed.
            photo = tk.PhotoImage(data=base64.b64encode(data).decode("ascii"))
            return _TkTexture(photo)
        try:
            from PIL import Image
            from io import BytesIO
        except ImportError:
            return None
        with Image.open(BytesIO(data)) as image:
            image.thumbnail((512, 512))
            return image.convert("RGB")
    except (OSError, ValueError, urllib.error.URLError, tk.TclError):
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
        if model.get("format") != "pyrion.mesh":
            raise ValueError("Unsupported model: " + model_path)
        scale = obj.get("scale", [1, 1, 1])
        if len(scale) != 3 or any(
            not math.isfinite(float(value)) or float(value) <= 0 for value in scale
        ):
            raise ValueError("Invalid model scale")
        primitive = model.get("primitive")
        if primitive == "uv_sphere":
            params = model["parameters"]
            # Preserve the original sphere geometry and rendering scale.
            radius = float(params["radius"]) * sum(map(float, scale)) / 3
            mesh = SphereMesh(rings=int(params["rings"]),
                              segments=int(params["segments"]), radius=radius)
        elif primitive == "triangle_mesh":
            mesh = TriangleMesh(model["vertices"], model["faces"], scale=scale)
            radius = mesh.radius
        else:
            raise ValueError("Unsupported mesh primitive: " + str(primitive))
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
        self.spotlight_enabled = True
        for item in self.objects:
            item["renderer"].rotation_y = item["rotation"]
            item["renderer"].rotation_x = -0.28
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
        self.material_mode = "mat"
        self.material_notice = ""
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

        # HUD includes interactive details and material buttons.
        self.bind("<space>", lambda _event: self.toggle_animation())
        self.bind("<F3>", self._toggle_hud_mode)
        self.bind("<m>", self._toggle_material_mode)
        self.bind("<M>", self._toggle_material_mode)
        self.bind("<l>", self._toggle_spotlight)
        self.bind("<L>", self._toggle_spotlight)
        self.bind("<Tab>", self._toggle_control_mode)
        self.bind("<r>", self._reset_navigation)
        self.bind("<R>", self._reset_navigation)
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
        eye = self.camera_pose["position"]
        forward = self._pose_forward(self.camera_pose)
        ordered = sorted(
            self.objects,
            key=lambda obj: sum(
                (obj["position"][k] - eye[k]) * forward[k]
                for k in range(3)
            ),
            reverse=True
        )
        for item in ordered:
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
        y = 66 if self._width >= 620 else 105
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
                    self.after(16, self._frame)
            except tk.TclError:
                pass


def run():
    app = Pyrion3DApp()
    app.mainloop()


if __name__ == "__main__":
    run()
