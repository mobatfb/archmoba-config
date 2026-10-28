# CANVAEDIT - Editor visual por capas para PYRION
# Ruta: AMDEV/TOOLS/CANVAEDIT/canvaedit.py

from dataclasses import dataclass, asdict
from pathlib import Path
import io
import json
import sys
import urllib.request
import uuid

import tkinter as tk
from tkinter import ttk, messagebox

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

BASE_DIR = Path(__file__).resolve().parent
PROJECTS_DIR = BASE_DIR / "projects"
DEFAULT_PROJECT = "pyrion_desing"

PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def get_project_dir(project_name=DEFAULT_PROJECT):
    return PROJECTS_DIR / project_name


def get_project_file(project_name=DEFAULT_PROJECT):
    return get_project_dir(project_name) / "layers.json"


def get_assets_dir(project_name=DEFAULT_PROJECT):
    return get_project_dir(project_name) / "assets"


def list_projects():
    if not PROJECTS_DIR.is_dir():
        return []
    return sorted(
        p.name
        for p in PROJECTS_DIR.iterdir()
        if p.is_dir() and (p / "layers.json").is_file()
    )


@dataclass
class Layer:
    id: str
    name: str
    type: str = "generic"
    visible: bool = True
    locked: bool = False
    opacity: float = 1.0
    z_index: int = 0
    asset: str = ""
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    @classmethod
    def create(cls, name, type="generic", **kwargs):
        return cls(
            id=uuid.uuid4().hex[:12],
            name=name,
            type=type,
            **kwargs,
        )


class LayerManager:
    def __init__(self, project_name=DEFAULT_PROJECT):
        self.project_name = project_name
        self.project_dir = get_project_dir(project_name)
        self.project_file = get_project_file(project_name)
        self.assets_dir = get_assets_dir(project_name)
        self.layers = []

    def add(self, layer):
        self.layers.append(layer)
        self._normalize()

    def remove(self, layer_id):
        layer = self.get(layer_id)
        if layer and layer.locked:
            return False
        self.layers = [x for x in self.layers if x.id != layer_id]
        self._normalize()
        return True

    def move_up(self, layer_id):
        index = self._index(layer_id)
        if index is not None and index < len(self.layers) - 1:
            self.layers[index], self.layers[index + 1] = (
                self.layers[index + 1],
                self.layers[index],
            )
            self._normalize()

    def move_down(self, layer_id):
        index = self._index(layer_id)
        if index is not None and index > 0:
            self.layers[index], self.layers[index - 1] = (
                self.layers[index - 1],
                self.layers[index],
            )
            self._normalize()

    def toggle(self, layer_id):
        layer = self.get(layer_id)
        if layer:
            layer.visible = not layer.visible

    def lock(self, layer_id, value=True):
        layer = self.get(layer_id)
        if layer:
            layer.locked = bool(value)

    def get(self, layer_id):
        return next((x for x in self.layers if x.id == layer_id), None)

    def _index(self, layer_id):
        for i, layer in enumerate(self.layers):
            if layer.id == layer_id:
                return i
        return None

    def _normalize(self):
        for i, layer in enumerate(self.layers):
            layer.z_index = i

    def save(self, path=None):
        target = Path(path) if path else self.project_file
        target.parent.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "format": "CANVAEDIT",
            "version": 1,
            "project": self.project_name,
            "layers": [asdict(x) for x in self.layers],
        }
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def load(self, path=None):
        target = Path(path) if path else self.project_file
        if not target.is_file():
            return False

        data = json.loads(target.read_text(encoding="utf-8"))
        self.project_name = data.get("project", self.project_name)
        self.project_dir = get_project_dir(self.project_name)
        self.project_file = get_project_file(self.project_name)
        self.assets_dir = get_assets_dir(self.project_name)
        self.layers = [Layer(**item) for item in data.get("layers", [])]
        self._normalize()
        return True


class CanvaEditApp(tk.Tk):
    def __init__(self, manager):
        super().__init__()
        self.manager = manager
        self.title(f"CANVAEDIT - {manager.project_name}")
        self.geometry("1280x760")
        self.minsize(900, 560)
        self.configure(bg="#14171d")

        self._source_images = {}
        self._tk_images = {}
        self._resize_job = None

        self._build_ui()
        self._refresh_layers_panel()
        self.after(100, self.render_layers)

    def _build_ui(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("Dark.TFrame", background="#14171d")
        style.configure("Panel.TFrame", background="#1d222b")
        style.configure(
            "Dark.TLabel",
            background="#14171d",
            foreground="#f2f5f8",
            font=("Arial", 11),
        )
        style.configure(
            "Title.TLabel",
            background="#14171d",
            foreground="#ffffff",
            font=("Arial", 16, "bold"),
        )

        header = ttk.Frame(self, style="Dark.TFrame")
        header.pack(fill="x", padx=14, pady=(12, 8))

        ttk.Label(header, text="CANVAEDIT", style="Title.TLabel").pack(side="left")
        ttk.Label(
            header,
            text=f"  Proyecto: {self.manager.project_name}",
            style="Dark.TLabel",
        ).pack(side="left")

        body = tk.PanedWindow(
            self,
            orient="horizontal",
            sashwidth=6,
            bg="#14171d",
            bd=0,
            relief="flat",
        )
        body.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        canvas_frame = tk.Frame(body, bg="#0c0f14", bd=1, relief="solid")
        panel_frame = tk.Frame(body, bg="#1d222b", width=280)

        body.add(canvas_frame, stretch="always")
        body.add(panel_frame, minsize=240)

        self.canvas = tk.Canvas(
            canvas_frame,
            bg="#090b10",
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        tk.Label(
            panel_frame,
            text="CAPAS",
            bg="#1d222b",
            fg="#f6f8fa",
            font=("Arial", 13, "bold"),
            anchor="w",
        ).pack(fill="x", padx=14, pady=(14, 8))

        self.layers_container = tk.Frame(panel_frame, bg="#1d222b")
        self.layers_container.pack(fill="both", expand=True, padx=10)

        footer = tk.Frame(panel_frame, bg="#1d222b")
        footer.pack(fill="x", padx=10, pady=10)

        tk.Button(
            footer,
            text="Recargar",
            command=self.reload_project,
            bg="#2b3440",
            fg="#ffffff",
            activebackground="#384553",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=7,
            cursor="hand2",
        ).pack(fill="x")

        self.status_var = tk.StringVar(value="Listo")
        tk.Label(
            panel_frame,
            textvariable=self.status_var,
            bg="#1d222b",
            fg="#9ca7b5",
            font=("Arial", 9),
            anchor="w",
            justify="left",
            wraplength=245,
        ).pack(fill="x", padx=12, pady=(0, 12))

    def _refresh_layers_panel(self):
        for child in self.layers_container.winfo_children():
            child.destroy()

        for layer in sorted(self.manager.layers, key=lambda x: x.z_index, reverse=True):
            row = tk.Frame(
                self.layers_container,
                bg="#272e38",
                highlightbackground="#3a4350",
                highlightthickness=1,
            )
            row.pack(fill="x", pady=4)

            visible_var = tk.BooleanVar(value=layer.visible)

            def toggle_layer(layer_id=layer.id, var=visible_var):
                target = self.manager.get(layer_id)
                if target:
                    target.visible = var.get()
                    self.manager.save()
                    self.render_layers()

            tk.Checkbutton(
                row,
                variable=visible_var,
                command=toggle_layer,
                bg="#272e38",
                activebackground="#272e38",
                selectcolor="#272e38",
                highlightthickness=0,
                bd=0,
            ).pack(side="left", padx=(8, 4), pady=10)

            text_wrap = tk.Frame(row, bg="#272e38")
            text_wrap.pack(side="left", fill="x", expand=True, pady=7)

            tk.Label(
                text_wrap,
                text=layer.name,
                bg="#272e38",
                fg="#ffffff",
                font=("Arial", 10, "bold"),
                anchor="w",
            ).pack(fill="x")

            details = f"{layer.type}  ·  z:{layer.z_index}"
            if layer.locked:
                details += "  ·  bloqueada"

            tk.Label(
                text_wrap,
                text=details,
                bg="#272e38",
                fg="#9ca7b5",
                font=("Arial", 8),
                anchor="w",
            ).pack(fill="x")

    def _on_canvas_resize(self, _event=None):
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(120, self.render_layers)

    def reload_project(self):
        if self.manager.load():
            self._source_images.clear()
            self._tk_images.clear()
            self._refresh_layers_panel()
            self.render_layers()
            self.status_var.set("Proyecto recargado")
        else:
            messagebox.showerror(
                "CANVAEDIT",
                f"No se pudo cargar {self.manager.project_file}",
            )

    def _download_image(self, url):
        with urllib.request.urlopen(url, timeout=15) as response:
            return response.read()

    def _get_source_image(self, layer):
        if layer.asset in self._source_images:
            return self._source_images[layer.asset]

        if not PIL_AVAILABLE:
            raise RuntimeError(
                "Pillow no está instalado. CANVAEDIT necesita Pillow para mostrar JPG."
            )

        data = self._download_image(layer.asset)
        image = Image.open(io.BytesIO(data)).convert("RGBA")
        self._source_images[layer.asset] = image
        return image

    def render_layers(self):
        self.canvas.delete("all")
        self._tk_images.clear()

        width = max(self.canvas.winfo_width(), 1)
        height = max(self.canvas.winfo_height(), 1)

        visible_layers = [
            layer
            for layer in sorted(self.manager.layers, key=lambda x: x.z_index)
            if layer.visible
        ]

        if not visible_layers:
            self.canvas.create_text(
                width // 2,
                height // 2,
                text="No hay capas visibles",
                fill="#7f8997",
                font=("Arial", 15),
            )
            self.status_var.set("Sin capas visibles")
            return

        for layer in visible_layers:
            if not layer.asset:
                continue

            try:
                src = self._get_source_image(layer)
                img = src.copy()

                if layer.opacity < 1:
                    alpha = img.getchannel("A").point(
                        lambda p: int(p * max(0.0, min(1.0, layer.opacity)))
                    )
                    img.putalpha(alpha)

                target_w = layer.width if layer.width > 0 else width
                target_h = layer.height if layer.height > 0 else height

                if layer.type == "background":
                    scale = max(target_w / img.width, target_h / img.height)
                else:
                    scale = min(target_w / img.width, target_h / img.height)

                new_w = max(1, int(img.width * scale))
                new_h = max(1, int(img.height * scale))
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

                if layer.type == "background":
                    left = max(0, (new_w - target_w) // 2)
                    top = max(0, (new_h - target_h) // 2)
                    img = img.crop((left, top, left + target_w, top + target_h))

                tk_img = ImageTk.PhotoImage(img)
                self._tk_images[layer.id] = tk_img

                x = layer.x
                y = layer.y
                self.canvas.create_image(
                    x,
                    y,
                    anchor="nw",
                    image=tk_img,
                    tags=(layer.id,),
                )

                self.status_var.set(
                    f"{len(visible_layers)} capa(s) visibles · {width}x{height}"
                )

            except Exception as exc:
                self.canvas.create_text(
                    width // 2,
                    height // 2,
                    text=f"No se pudo cargar la capa {layer.name}\n{exc}",
                    fill="#d9dde3",
                    font=("Arial", 12),
                    justify="center",
                )
                self.status_var.set(f"Error en {layer.name}: {exc}")


def create_project(project_name):
    project_dir = get_project_dir(project_name)
    assets_dir = get_assets_dir(project_name)
    project_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    manager = LayerManager(project_name)
    manager.save()
    return manager


def main():
    project_name = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PROJECT
    manager = LayerManager(project_name)

    if not manager.load():
        available = list_projects()
        print(f"ERROR: no existe el proyecto '{project_name}'.")
        print("Proyectos disponibles:", ", ".join(available) if available else "(ninguno)")
        return 1

    app = CanvaEditApp(manager)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
