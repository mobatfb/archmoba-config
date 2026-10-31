"""Render the actual PYRION scene to preview.png; requires Pillow."""
import math
import sys
from types import SimpleNamespace
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[3]))
from PIL import Image, ImageDraw
import PYRION.app as app


def render():
    scene, objects = app.load_selected_scene()
    if scene["name"] != "monumentalShock":
        raise RuntimeError("Select monumentalShock in engine3d/scene_selected.json first")
    width, height = 1600, 1000
    image = Image.new("RGB", (width, height), scene["background"]["color"])
    draw = ImageDraw.Draw(image)

    class Canvas:
        def create_polygon(self, *points, fill, outline, width):
            draw.polygon(list(zip(points[::2], points[1::2])), fill=fill)

        def draw_surface(self, surface, left, top):
            image.paste(surface, (left, top), surface if surface.mode == "RGBA" else None)

    canvas = Canvas()
    background = SimpleNamespace(canvas=canvas, background_image=scene.get("_background_image"), _background_cache=None)
    app.Pyrion3DApp._draw_background(background, width, height)
    camera = scene["navigation"]["camera_position"]
    yaw = math.radians(scene["navigation"]["camera_yaw_degrees"])
    pitch = math.radians(scene["navigation"]["camera_pitch_degrees"])
    forward = (math.sin(yaw) * math.cos(pitch), math.sin(pitch), -math.cos(yaw) * math.cos(pitch))
    ordered = sorted(objects, key=lambda obj: (obj.get("render_layer", 0),
        -sum((obj["position"][i] - camera[i]) * forward[i] for i in range(3))))
    shadow_state = SimpleNamespace(canvas=canvas, scene=scene, _shadow_cache=None,
        camera_pose={"position": camera, "yaw": yaw, "pitch": pitch},
        _pose_forward=app.Pyrion3DApp._pose_forward)
    shadows_drawn = False
    for item in ordered:
        if not shadows_drawn and item.get("render_layer", 0) >= 0:
            app.Pyrion3DApp._draw_contact_shadows(shadow_state, width, height, 520)
            shadows_drawn = True
        renderer = item["renderer"]
        renderer.rotation_y = item["rotation"]
        renderer.rotation_x = item["rotation_x"]
        renderer.material_mode = scene.get("material_mode", "mat")
        renderer.set_lights(scene["lights"], scene["ambient_light"])
        renderer.draw(canvas, width / 2, height / 2, 520, False,
                      item["position"], camera, yaw, pitch)
    image.save(ROOT / "preview.png")


if __name__ == "__main__":
    render()
