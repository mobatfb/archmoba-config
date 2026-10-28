# CANVAEDIT - Editor visual por capas para PYRION
# Ruta: AMDEV/TOOLS/CANVAEDIT/canvaedit.py

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import uuid

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
PROJECT_FILE = BASE_DIR / "layers.json"

ASSETS_DIR.mkdir(parents=True, exist_ok=True)


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
    def __init__(self):
        self.layers = []

    def add(self, layer):
        self.layers.append(layer)
        self._normalize()

    def remove(self, layer_id):
        self.layers = [x for x in self.layers if x.id != layer_id]
        self._normalize()

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

    def save(self, path=PROJECT_FILE):
        payload = {
            "format": "CANVAEDIT",
            "version": 1,
            "layers": [asdict(x) for x in self.layers],
        }
        Path(path).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def load(self, path=PROJECT_FILE):
        path = Path(path)
        if not path.is_file():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        self.layers = [Layer(**item) for item in data.get("layers", [])]
        self._normalize()


def create_default_project():
    manager = LayerManager()
    manager.add(
        Layer.create(
            "Fondo PYRION",
            type="background",
            asset="assets/pyrion_background.png",
        )
    )
    manager.save()
    return manager


if __name__ == "__main__":
    manager = LayerManager()
    manager.load()
    if not manager.layers:
        manager = create_default_project()

    print("CANVAEDIT - Sistema de capas")
    for layer in manager.layers:
        print(
            f"{layer.z_index}: {layer.name} | "
            f"visible={layer.visible} | locked={layer.locked}"
        )
