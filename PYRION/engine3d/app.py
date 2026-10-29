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

ENGINE_VERSION = "0.1.0"
DESKTOP_VERSION = "0.4.2"
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
    request = urllib.request.Request(url, headers={"User-Agent": "PYRION/0.4.2"})
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
        self.last_time = time.perf_counter()
        self.drag_start = None
        self.pending_frame = None
        self._width = 1
        self._height = 1
        self._orb_radius = 1

        # Controls are keyboard/mouse-only; no controls are drawn on the desktop.
        self.bind("<space>", lambda _event: self.toggle_animation())
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
            self._draw()
            self.after(40, self._frame)
        except tk.TclError:
            pass


def run():
    app = Pyrion3DApp()
    app.mainloop()


if __name__ == "__main__":
    run()
