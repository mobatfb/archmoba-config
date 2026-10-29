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
        self._pbr = self.material.get("shader") == "pbr"
        color = str(self.material.get("base_color", "#2767d7"))
        if len(color) != 7 or not color.startswith("#"):
            raise ValueError("Invalid material base_color")
        try:
            self._base_rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
        except ValueError as exc:
            raise ValueError("Invalid material base_color") from exc
        self._metallic = max(0.0, min(1.0, float(self.material.get("metallic", 0))))
        self._roughness = max(0.04, min(1.0, float(self.material.get("roughness", 0.5))))
        self._texels = None
        texture = self.material.get("_texture_image")
        if texture is not None:
            pixels = texture.load()
            tw, th = texture.size
            self._texels = [
                pixels[min(th - 1, max(0, int(face.latitude / math.pi * (th - 1)))),
                       min(tw - 1, max(0, int((face.longitude % (2 * math.pi)) / (2 * math.pi) * (tw - 1))))]
                for face in mesh.faces
            ]
        self.camera_distance = 3.85
        self.rotation_y = 0.0
        self.rotation_x = -0.25
        self.zoom = 1.0
        self.wireframe = False
        self._light_a = _unit((-0.42, 0.77, 0.53))
        self._light_b = _unit((0.74, -0.29, 0.47))
        self._lines = []
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
        if texel is not None:
            base = tuple(base[k] * (0.30 + 0.70 * texel[k] / 255.0)
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

    def draw(self, canvas, cx, cy, diameter, draw_graticules=True):
        """Draw 3D mesh centered at cx,cy; returns visible face count."""
        focal = max(50, diameter * self.camera_distance * 0.47 * self.zoom)
        rotated = [self._rotate(p) for p in self.mesh.vertices]
        projected = [self._project(p, cx, cy, focal) for p in rotated]
        visible_faces = []

        for face_index, (face, accent) in enumerate(zip(self.mesh.faces, self._material)):
            i, j, k = face.indices
            a, b, c = rotated[i], rotated[j], rotated[k]
            center = ((a[0] + b[0] + c[0]) / 3,
                      (a[1] + b[1] + c[1]) / 3,
                      (a[2] + b[2] + c[2]) / 3)
            normal = _unit(center)
            towards_camera = _unit((-
                center[0], -center[1], self.camera_distance - center[2]))
            front = _dot(normal, towards_camera)
            if front <= 0.02:
                continue
            pts = (*projected[i], *projected[j], *projected[k])
            color = self._color(normal, accent, front, towards_camera,
                                self._texels[face_index] if self._texels is not None else None)
            visible_faces.append((center[2], pts, color))

        visible_faces.sort(key=lambda row: row[0])
        for _, pts, color in visible_faces:
            canvas.create_polygon(*pts, fill=color,
                                  outline="#22426e" if self.wireframe else color,
                                  width=0.7 if self.wireframe else 0.2)
        if draw_graticules:
            for points, color in self._lines:
                self._visible_curve(canvas, points, color, cx, cy, focal,
                                    width=1.15 if self.wireframe else 0.85)
            self._visible_curve(canvas, self._decorative_path,
                                "#8b9cff", cx, cy, focal, width=1.7)
        return len(visible_faces)
