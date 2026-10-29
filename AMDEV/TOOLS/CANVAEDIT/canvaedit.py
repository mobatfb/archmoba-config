# CANVAEDIT - Editor visual por capas
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
CANVAEDIT_VERSION = "1.0.7"
DEFAULT_PROJECT = "pyrion_desing"

REPO_OWNER = "mobatfb"
REPO_NAME = "archmoba-config"
REPO_BRANCH = "main"
REPO_PROJECTS_PATH = "AMDEV/TOOLS/CANVAEDIT/projects"
REPO_API_PROJECTS = (
    f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/"
    f"{REPO_PROJECTS_PATH}?ref={REPO_BRANCH}"
)
REPO_RAW_BASE = (
    f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/"
    f"{REPO_BRANCH}/{REPO_PROJECTS_PATH}"
)


def project_layers_url(project_name=DEFAULT_PROJECT):
    return f"{REPO_RAW_BASE}/{project_name}/layers.json"


def list_projects():
    request = urllib.request.Request(
        REPO_API_PROJECTS,
        headers={"User-Agent": "CANVAEDIT/1.0"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        data = json.loads(response.read().decode("utf-8"))

    return sorted(
        item["name"]
        for item in data
        if item.get("type") == "dir"
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
    align: str = ""

    @classmethod
    def create(cls, name, type="generic", **kwargs):
        return cls(id=uuid.uuid4().hex[:12], name=name, type=type, **kwargs)


class LayerManager:
    def __init__(self, project_name=DEFAULT_PROJECT):
        self.project_name = project_name
        self.project_file = project_layers_url(project_name)
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
                self.layers[index + 1], self.layers[index]
            )
            self._normalize()

    def move_down(self, layer_id):
        index = self._index(layer_id)
        if index is not None and index > 0:
            self.layers[index], self.layers[index - 1] = (
                self.layers[index - 1], self.layers[index]
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
        # Los proyectos se cargan directamente desde GitHub.
        # La escritura remota se implementara por separado cuando se necesite.
        return False

    def load(self, path=None):
        url = path or project_layers_url(self.project_name)
        try:
            request = urllib.request.Request(
                str(url),
                headers={"User-Agent": "CANVAEDIT/1.0"},
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception:
            return False

        self.project_name = data.get("project", self.project_name)
        self.project_file = project_layers_url(self.project_name)
        self.layers = [Layer(**item) for item in data.get("layers", [])]
        self._normalize()
        return True


class CanvaEditFrame(tk.Frame):
    def __init__(self, master, project_name=DEFAULT_PROJECT, **kwargs):
        super().__init__(master, bg="#14171d", **kwargs)
        self.manager = LayerManager(project_name)
        if not self.manager.load():
            available = list_projects()
            if available:
                self.manager = LayerManager(available[0])
                self.manager.load()

        self._source_images = {}
        self._tk_images = {}
        self._resize_job = None
        self.project_var = tk.StringVar(value=self.manager.project_name)

        self._build_ui()
        self._refresh_layers_panel()
        self.after(100, self.render_layers)

    def _build_ui(self):
        header = tk.Frame(self, bg="#14171d")
        header.pack(fill="x", padx=14, pady=(12, 8))

        tk.Label(
            header,
            text=f"CANVAEDIT  v{CANVAEDIT_VERSION}",
            bg="#14171d",
            fg="#ffffff",
            font=("Arial", 16, "bold"),
        ).pack(side="left")

        tk.Label(
            header,
            textvariable=self.project_var,
            bg="#14171d",
            fg="#aeb8c5",
            font=("Arial", 10),
        ).pack(side="left", padx=(12, 0))

        tk.Button(
            header,
            text="Abrir proyectos",
            command=self.open_projects,
            bg="#2b3440",
            fg="#ffffff",
            activebackground="#384553",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
        ).pack(side="right")

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

        tk.Button(
            panel_frame,
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
        ).pack(fill="x", padx=10, pady=10)

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

    def open_projects(self):
        projects = list_projects()
        if not projects:
            messagebox.showinfo("CANVAEDIT", "No hay proyectos disponibles.")
            return

        win = tk.Toplevel(self)
        win.title("Abrir proyecto")
        win.geometry("420x360")
        win.configure(bg="#171b22")
        win.transient(self.winfo_toplevel())

        tk.Label(
            win,
            text="PROYECTOS",
            bg="#171b22",
            fg="#ffffff",
            font=("Arial", 13, "bold"),
        ).pack(anchor="w", padx=16, pady=(16, 8))

        listbox = tk.Listbox(
            win,
            bg="#222933",
            fg="#ffffff",
            selectbackground="#3b4655",
            selectforeground="#ffffff",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#343d49",
            font=("Arial", 11),
        )
        listbox.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        for name in projects:
            listbox.insert("end", name)

        if self.manager.project_name in projects:
            index = projects.index(self.manager.project_name)
            listbox.selection_set(index)
            listbox.see(index)

        def open_selected(_event=None):
            selection = listbox.curselection()
            if not selection:
                return
            self.load_project(projects[selection[0]])
            win.destroy()

        listbox.bind("<Double-Button-1>", open_selected)

        tk.Button(
            win,
            text="Abrir",
            command=open_selected,
            bg="#2b3440",
            fg="#ffffff",
            activebackground="#384553",
            activeforeground="#ffffff",
            relief="flat",
            padx=14,
            pady=7,
            cursor="hand2",
        ).pack(fill="x", padx=16, pady=(0, 16))

    def load_project(self, project_name):
        manager = LayerManager(project_name)
        if not manager.load():
            messagebox.showerror(
                "CANVAEDIT",
                f"No se pudo abrir el proyecto '{project_name}'."
            )
            return

        self.manager = manager
        self.project_var.set(project_name)
        self._source_images.clear()
        self._tk_images.clear()
        self._refresh_layers_panel()
        self.render_layers()
        self.status_var.set(f"Proyecto abierto: {project_name}")

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
        self.load_project(self.manager.project_name)

    def _open_image_bytes(self, data, source_name):
        if not PIL_AVAILABLE:
            raise RuntimeError("Pillow no está instalado.")

        try:
            image = Image.open(io.BytesIO(data))
            image.load()
            return image.convert("RGBA")
        except Exception as exc:
            raise RuntimeError(
                f"{source_name}: Pillow no pudo abrir la imagen: {exc}"
            ) from exc

    def _download_raw_bytes(self, url):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "CANVAEDIT/1.0",
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.read()

    def _download_image_github_api_bytes(self, raw_url):
        prefix = (
            f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/"
            f"{REPO_BRANCH}/"
        )

        if not raw_url.startswith(prefix):
            raise RuntimeError("La URL no pertenece al repositorio configurado.")

        repo_path = raw_url[len(prefix):]
        api_url = (
            f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/"
            f"{repo_path}?ref={REPO_BRANCH}"
        )

        # Primer intento: GitHub Contents API en modo RAW.
        raw_error = None
        request = urllib.request.Request(
            api_url,
            headers={
                "User-Agent": "CANVAEDIT/1.0",
                "Accept": "application/vnd.github.raw",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                data = response.read()
            if data:
                return data
        except Exception as exc:
            raw_error = exc

        # Segundo intento: JSON + Base64.
        request = urllib.request.Request(
            api_url,
            headers={
                "User-Agent": "CANVAEDIT/1.0",
                "Accept": "application/vnd.github+json",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))

            import base64

            content = payload.get("content", "")
            if payload.get("encoding") != "base64" or not content:
                raise RuntimeError("La API no devolvio contenido Base64.")

            return base64.b64decode(content.replace("\n", ""))
        except Exception as exc:
            if raw_error is not None:
                raise RuntimeError(
                    f"API RAW fallo: {raw_error} | API Base64 fallo: {exc}"
                ) from exc
            raise

    def _get_source_image(self, layer):
        if layer.asset in self._source_images:
            return self._source_images[layer.asset]

        raw_error = None
        api_error = None

        try:
            raw_data = self._download_raw_bytes(layer.asset)
            image = self._open_image_bytes(raw_data, "RAW")
            self._source_images[layer.asset] = image
            return image
        except Exception as exc:
            raw_error = exc

        try:
            api_data = self._download_image_github_api_bytes(layer.asset)
            image = self._open_image_bytes(api_data, "GitHub API")
            self._source_images[layer.asset] = image
            return image
        except Exception as exc:
            api_error = exc

        raise RuntimeError(
            f"No se pudo cargar la imagen. RAW: {raw_error} | API: {api_error}"
        )

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

                draw_x = layer.x
                draw_y = layer.y

                if layer.align == "bottom-center":
                    draw_x = max(0, (width - new_w) // 2 + layer.x)
                    draw_y = max(0, height - new_h - layer.y)
                elif layer.align == "center":
                    draw_x = max(0, (width - new_w) // 2 + layer.x)
                    draw_y = max(0, (height - new_h) // 2 + layer.y)

                tk_img = ImageTk.PhotoImage(img)
                self._tk_images[layer.id] = tk_img
                self.canvas.create_image(
                    draw_x,
                    draw_y,
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


class CanvaEditApp(tk.Tk):
    def __init__(self, project_name=DEFAULT_PROJECT):
        super().__init__()
        self.title(f"CANVAEDIT - {project_name}")
        self.geometry("1280x760")
        self.minsize(900, 560)
        self.configure(bg="#14171d")

        self.editor = CanvaEditFrame(self, project_name=project_name)
        self.editor.pack(fill="both", expand=True)


def create_project(project_name):
    raise RuntimeError(
        "Los proyectos se administran desde la carpeta projects del repositorio."
    )


def main():
    project_name = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PROJECT
    app = CanvaEditApp(project_name)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
