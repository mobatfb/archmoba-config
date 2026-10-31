"""Generate monumentalShock's self-contained, low-poly crystal sanctuary."""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def save(path, data):
    destination = ROOT / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rings_mesh(name, rings, sides=4, phase=math.pi / 4):
    vertices = [[round(radius * math.cos(phase + i * math.tau / sides), 6), y,
                 round(radius * math.sin(phase + i * math.tau / sides), 6)]
                for y, radius in rings for i in range(sides)]
    faces = []
    for row in range(len(rings) - 1):
        for i in range(sides):
            a, b = row * sides + i, row * sides + (i + 1) % sides
            c, d = a + sides, b + sides
            faces.extend([[a, c, b], [b, c, d]])
    for i in range(1, sides - 1):
        faces.append([0, i, i + 1])
        top = (len(rings) - 1) * sides
        faces.append([top, top + i + 1, top + i])
    return {"format": "pyrion.mesh", "version": 1, "name": name,
            "primitive": "triangle_mesh", "vertices": vertices, "faces": faces,
            "render": {"flat_shading": True}}


def build():
    outline = [(-16, -15), (-11, -17), (0, -16), (10, -17), (16, -12), (17, -3),
               (16, 7), (13, 14), (2, 15), (-12, 14), (-17, 8), (-16, -4)]
    save("models/terrain.mesh", {"format": "pyrion.mesh", "version": 1,
         "name": "Irregular forest sanctuary ground", "primitive": "triangle_mesh",
         "vertices": [[0, 0, 0]] + [[x, 0, z] for x, z in outline],
         "faces": [[0, (i+1) % len(outline)+1, i+1] for i in range(len(outline))]})
    save("models/monument.mesh", rings_mesh("Tapered monumental tower", [(0, 0.85), (0.12, 0.85), (0.17, 0.64), (0.85, 0.50), (1, 0.31)]))
    save("models/plinth.mesh", rings_mesh("Chamfered floating plinth", [(-0.12, 0.85), (0.06, 0.85), (0.12, 0.72)]))
    save("models/crystal.mesh", rings_mesh("Six-sided double-terminated crystal", [(-1, 0.025), (-0.58, 0.32), (0.48, 0.38), (1, 0.025)], sides=6, phase=0))
    palettes = {
        "obsidian": ("#253E5B", "pbr", 0.48, 0.38),
        "stone": ("#606B72", "pbr", 0.02, 0.88),
        "gold": ("#A28B5B", "pbr", 0.55, 0.62),
        "cyan": ("#25BFCD", "gem", 0.08, 0.16),
        "violet": ("#8451C7", "gem", 0.08, 0.18),
        "rose": ("#C768AE", "gem", 0.08, 0.18),
        "heart": ("#78BEDC", "gem", 0.10, 0.14),
    }
    for name, (color, shader, metal, rough) in palettes.items():
        material = {"format": "pyrion.material", "version": 2,
             "name": name, "shader": shader, "base_color": color,
             "metallic": metal, "roughness": rough, "specular_strength": 0.28}
        if shader == "gem":
            material.update(exposure=0.82, highlight_strength=0.35)
        if name in ("stone", "gold"):
            material.update(texture="../textures/limestone_ashlar.png", texture_status="ready",
                            texture_projection="box", texture_repeat_y=1, texture_exposure=0.95)
        if name == "gold":
            material["texture_tint"] = "#DBB577"
        save(f"materials/{name}.mat", material)
    save("materials/tower_stone.mat", {"format": "pyrion.material", "version": 1,
         "name": "Weathered limestone masonry", "shader": "pbr", "base_color": "#737984",
         "metallic": 0.02, "roughness": 0.88, "texture": "../textures/limestone_ashlar.png",
         "texture_status": "ready", "texture_projection": "box", "texture_repeat_y": 3,
         "texture_exposure": 0.95, "specular_strength": 0.20})
    save("materials/forest_floor.mat", {"format": "pyrion.material", "version": 1,
         "name": "Mossy weathered slate", "shader": "pbr", "base_color": "#4E5A53",
         "metallic": 0.0, "roughness": 0.97, "specular_strength": 0.10,
         "texture": "../textures/forest_floor.png", "texture_status": "ready",
         "texture_projection": "box", "texture_repeat_x": 5, "texture_repeat_y": 5,
         "texture_exposure": 0.68, "texture_lighting": "ambient"})
    objects = []

    def add(identity, model, material, position, scale, speed=0, angle=0):
        obj = {"id": identity, "name": identity, "model": f"models/{model}.mesh",
               "material": f"materials/{material}.mat", "position": position,
               "rotation": [0, angle, 0], "scale": scale, "visible": True}
        if speed:
            obj["animation"] = {"type": "spin", "axis": [0, 1, 0], "speed_degrees_per_second": speed}
        objects.append(obj)

    ground = -2.4
    add("sanctuary_terrace", "terrain", "forest_floor", [0, ground - 0.02, -2], [1, 1, 1])
    objects[-1]["render_layer"] = -1
    add("central_dais", "plinth", "gold", [0, ground + 0.08, -3.2], [2.4, 1.8, 2.4])
    towers = [("central_tower", 0, -3.2, 7.0, 1.55),
              ("west_inner", -4.1, -4.4, 4.7, 1.05), ("east_inner", 4.1, -4.4, 4.7, 1.05),
              ("west_outer", -7.6, -2.8, 3.5, 0.95), ("east_outer", 7.6, -2.8, 3.5, 0.95),
              ("west_gate", -8.6, 1.7, 2.8, 0.8), ("east_gate", 8.6, 1.7, 2.8, 0.8)]
    for identity, x, z, height, width in towers:
        add(identity + "_base", "plinth", "stone", [x, ground, z], [width * 1.4, 1.4, width * 1.4])
        add(identity, "monument", "tower_stone", [x, ground, z], [width, height, width])
        add(identity + "_capital", "plinth", "gold", [x, ground + height, z], [width * 0.65, 0.8, width * 0.65])

    # A central summit and six ascending/descending crystal steps on each side.
    add("summit_crystal", "crystal", "heart", [0, 5.65, -2.7], [1.25, 1.0, 1.25], 19)
    for side, sign in (("left", -1), ("right", 1)):
        for step in range(1, 7):
            x, y, z = sign * step * 1.12, 5.0 - step * 0.80, -1.4 + step * 0.18
            palette = ("violet", "cyan", "rose")[(step - 1) % 3]
            add(f"{side}_step_{step:02d}", "crystal", palette, [x, y, z], [0.86, 0.50, 0.86], sign * (20 + step * 3), step * 17)
            add(f"{side}_step_{step:02d}_plinth", "plinth", "stone", [x, y - 0.65, z], [0.88, 0.65, 0.88])

    for i, (x, z) in enumerate(((-6, -2.8), (-2.2, -4), (2.2, -4), (6, -2.8), (-3.5, 2.2), (3.5, 2.2))):
        add(f"garden_crystal_{i:02d}", "crystal", "cyan" if i % 2 else "violet", [x, ground + 0.9, z], [1.0, 0.85, 1.0], 12 + i * 4, i * 33)

    scene = {"format": "pyrion.scene", "version": 1, "name": "monumentalShock", "units": "world",
             "coordinate_system": {"handedness": "right", "up_axis": "Y"},
             "background": {"color": "#060C1A", "image": "textures/forest_background.png"},
             "material_mode": "img", "objects": objects, "ambient_light": 0.60,
             "ground_y": ground,
             "fog": {"color": "#385265", "start": 13, "end": 42, "strength": 0.30},
             "contact_shadows": [{"x": x+0.12, "z": z-0.25, "radius_x": width*1.1,
                                  "radius_z": width*1.4, "opacity": 0.42}
                                 for _, x, z, _, width in towers],
             "lights": [{"id": "sanctuary_light", "type": "spot", "enabled": True,
                         "position": [-2, 10, 10], "target": [0, 1.8, -2], "color": "#D4E8FF",
                         "intensity": 0.85, "range": 45, "angle_degrees": 120, "softness": 0.65}],
             "navigation": {"camera_position": [0, 2.8, 16.8], "camera_yaw_degrees": 0,
                            "camera_pitch_degrees": -2.7, "walk_speed": 3.0,
                            "turn_speed_degrees": 80, "look_speed_degrees": 95}}
    save("scene.json", scene)
    save("project.json", {"name": "monumentalShock", "version": "1.3.0", "scene": "scene.json",
                           "description": "Sanctuary of monuments and spinning crystal stairways."})
    return scene


if __name__ == "__main__":
    result = build()
    print(f"monumentalShock: {len(result['objects'])} objects generated.")
