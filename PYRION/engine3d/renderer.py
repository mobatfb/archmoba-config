"""Software 3D triangle projection and shading for a Tkinter canvas."""
import math


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
            specular = 0.60 * energy * highlight * facing
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

    def _color(self, normal, accent, front, view, texel=None):
        """CPU approximation of metallic PBR with environment-like highlights."""
        a = max(0.0, _dot(normal, self._light_a))
        b = max(0.0, _dot(normal, self._light_b))
        if self._gem:
            base = self._base_rgb
            if self.material_mode == "img" and texel is not None:
                base = tuple(0.12 * base[k] + 0.88 * texel[k] for k in range(3))
            facet = 0.30 + 0.65 * a + 0.24 * b + 0.21 * accent
            glint = max(0.0, _dot(normal, _unit((-0.28, 0.74, 0.62)))) ** 13
            white = max(0.0, _dot(normal, _unit((0.42, 0.68, 0.53)))) ** 38
            rim = (1.0 - max(0.0, front)) ** 3
            return _rgb((
                base[0] * facet + 102 * glint + 108 * white + 30 * rim,
                base[1] * facet + 115 * glint + 130 * white + 23 * rim,
                base[2] * (facet + 0.12) + 135 * glint + 125 * white + 44 * rim,
            ))
        if not self._pbr:
            edge = (1.0 - front) ** 1.9
            spec = max(0.0, _dot(normal, _unit((-0.13, 0.62, 0.78)))) ** 24
            return _rgb((
                17 + 53 * a + 14 * b + 14 * accent + 56 * spec + 24 * edge,
                30 + 80 * a + 21 * b + 19 * accent + 73 * spec + 19 * edge,
                69 + 112 * a + 71 * b + 46 * accent + 48 * spec + 36 * edge,
            ))
        metallic, rough = self._metallic, self._roughness
        base = self._base_rgb
        if self.material_mode == "img" and texel is not None:
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

    def draw(self, canvas, cx, cy, diameter, draw_graticules=True,
             object_position=(0.0, 0.0, 0.0),
             camera_position=(0.0, 0.0, 3.85),
             camera_yaw=0.0, camera_pitch=0.0):
        """Project rotating world-space models from a movable 3D camera."""
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
            if front <= 0.02:
                continue
            polygon = self._clip_near_plane([view[i], view[j], view[k]])
            if len(polygon) < 3:
                continue
            projected = []
            for vx, vy, depth in polygon:
                factor = focal / depth
                projected.extend((cx + vx * factor, cy - vy * factor))
            color = self._color(
                normal, accent, front, towards_camera,
                self._texels[face_index] if self._texels is not None else None
            )
            if self._spotlights and self.spotlight_enabled:
                color = self._shade_spotlights(
                    color, normal, towards_camera, world_center
                )
            depth = sum(v[2] for v in polygon) / len(polygon)
            visible_faces.append((depth, projected, color))
        visible_faces.sort(key=lambda item: item[0], reverse=True)
        for _, polygon, color in visible_faces:
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
