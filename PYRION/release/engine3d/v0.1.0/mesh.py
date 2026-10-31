"""3D mesh primitives for PYRION Engine - Python standard library only."""
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Face:
    indices: tuple
    longitude: float
    latitude: float
    band: int


class SphereMesh:
    """UV sphere with a single north/south pole and manifold triangle topology."""

    def __init__(self, rings=24, segments=48, radius=1.0):
        if rings < 4 or segments < 6:
            raise ValueError("Sphere needs rings>=4 and segments>=6")
        self.rings = int(rings)
        self.segments = int(segments)
        self.radius = float(radius)
        self.vertices = [(0.0, self.radius, 0.0)]
        self.faces = []
        # latitude angles are measured down from the north pole.
        for i in range(1, self.rings):
            theta = math.pi * i / self.rings
            y = self.radius * math.cos(theta)
            radial = self.radius * math.sin(theta)
            for j in range(self.segments):
                longitude = 2.0 * math.pi * j / self.segments
                self.vertices.append((
                    radial * math.cos(longitude), y,
                    radial * math.sin(longitude)
                ))
        self.vertices.append((0.0, -self.radius, 0.0))
        bottom_index = len(self.vertices) - 1

        # upper cap, middle quads, lower cap.
        for j in range(self.segments):
            nxt = (j + 1) % self.segments
            longitude = 2.0 * math.pi * (j + 0.5) / self.segments
            self.faces.append(Face((0, 1 + j, 1 + nxt), longitude,
                                   math.pi / self.rings * 0.55, 0))
        for i in range(1, self.rings - 1):
            for j in range(self.segments):
                nxt = (j + 1) % self.segments
                a = 1 + (i - 1) * self.segments + j
                b = 1 + (i - 1) * self.segments + nxt
                c = 1 + i * self.segments + j
                d = 1 + i * self.segments + nxt
                lon = 2.0 * math.pi * (j + 0.5) / self.segments
                lat = math.pi * (i + 0.5) / self.rings
                self.faces.append(Face((a, c, d), lon, lat, i))
                self.faces.append(Face((a, d, b), lon, lat, i))
        for j in range(self.segments):
            nxt = (j + 1) % self.segments
            a = 1 + (self.rings - 2) * self.segments + j
            b = 1 + (self.rings - 2) * self.segments + nxt
            lon = 2.0 * math.pi * (j + 0.5) / self.segments
            self.faces.append(Face((a, bottom_index, b), lon,
                                   math.pi * (self.rings - 0.55) / self.rings,
                                   self.rings - 1))

    @property
    def vertex_count(self):
        return len(self.vertices)

    @property
    def triangle_count(self):
        return len(self.faces)

    def meridian(self, longitude, steps=96):
        """3D polyline along a meridian, on the surface above the mesh."""
        rad = self.radius * 1.009
        return [(
            rad * math.sin(math.pi * i / steps) * math.cos(longitude),
            rad * math.cos(math.pi * i / steps),
            rad * math.sin(math.pi * i / steps) * math.sin(longitude)
        ) for i in range(steps + 1)]

    def latitude(self, theta, steps=112):
        rad = self.radius * 1.009
        return [(
            rad * math.sin(theta) * math.cos(2 * math.pi * i / steps),
            rad * math.cos(theta),
            rad * math.sin(theta) * math.sin(2 * math.pi * i / steps)
        ) for i in range(steps + 1)]

    def signature(self):
        return (self.rings, self.segments, self.vertex_count,
                self.triangle_count)
