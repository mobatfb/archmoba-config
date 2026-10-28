# CANVAEDIT - Editor visual por capas para PYRION
# Ruta: AMDEV/TOOLS/CANVAEDIT/canvaedit.py

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import sys
import uuid

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

    print("CANVAEDIT - Sistema de capas")
    print(f"Proyecto: {project_name}")
    print(f"Archivo: {manager.project_file}")

    if not manager.load():
        print(f"ERROR: no existe el proyecto '{project_name}'.")
        available = list_projects()
        print("Proyectos disponibles:", ", ".join(available) if available else "(ninguno)")
        return 1

    print(f"Capas cargadas: {len(manager.layers)}")
    for layer in manager.layers:
        print(
            f"{layer.z_index}: {layer.name} | "
            f"type={layer.type} | "
            f"asset={layer.asset} | "
            f"visible={layer.visible} | locked={layer.locked} | "
            f"opacity={layer.opacity}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
