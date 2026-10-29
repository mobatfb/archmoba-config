import unittest
from unittest.mock import patch
from types import SimpleNamespace

from PIL import Image, ImageOps
import PYRION.app as pyrion
from PYRION.engine3d.mesh import TriangleMesh
from PYRION.engine3d.renderer import SoftwareRenderer


class Canvas:
    def __init__(self):
        self.surfaces = []
        self.polygons = []

    def draw_surface(self, image, left, top):
        self.surfaces.append((image, left, top))

    def create_polygon(self, *args, **kwargs):
        self.polygons.append((args, kwargs))


class SurfaceTextureTests(unittest.TestCase):
    def renderer(self):
        texture = Image.new("RGB", (16, 16))
        texture.putdata([(40 + x * 10, 60 + y * 8, 90) for y in range(16) for x in range(16)])
        mesh = TriangleMesh([[-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 0]],
                            [[0, 1, 2], [0, 2, 3]])
        return SoftwareRenderer(mesh, {"shader": "pbr", "base_color": "#737984",
            "metallic": 0.02, "roughness": 0.88, "texture_projection": "box",
            "texture_repeat_y": 3, "_texture_image": texture})

    def test_surface_contains_texture_details_and_static_frames_reuse_cache(self):
        renderer = self.renderer()
        renderer.rotation_x = 0
        canvas = Canvas()
        with patch.object(renderer, "_raster_surface", wraps=renderer._raster_surface) as raster:
            self.assertEqual(renderer.draw(canvas, 300, 240, 260, False), 2)
            self.assertTrue(canvas.surfaces)
            image = canvas.surfaces[-1][0]
            colors = image.convert("RGB").getcolors(image.width * image.height)
            self.assertGreater(len(colors), 20)
            renderer.draw(canvas, 300, 240, 260, False)
            self.assertIs(image, canvas.surfaces[-1][0])
            self.assertEqual(raster.call_count, 1)
            renderer.draw(canvas, 300, 240, 260, False, camera_position=(0.2, 0, 3.85))
            self.assertEqual(raster.call_count, 2)

    def test_material_toggle_keeps_untextured_rendering_available(self):
        renderer = self.renderer()
        renderer.material_mode = "mat"
        canvas = Canvas()
        renderer.draw(canvas, 300, 240, 260, False)
        self.assertTrue(canvas.polygons)
        self.assertFalse(canvas.surfaces)

    def test_offscreen_surface_is_bounded_and_does_not_allocate_huge_images(self):
        renderer = self.renderer()
        canvas = Canvas()
        renderer.draw(canvas, 300, 240, 260, False, object_position=(10000, 0, 0))
        self.assertFalse(canvas.surfaces)

    def test_background_covers_viewport_and_reuses_resized_image(self):
        canvas = Canvas()
        source = Image.new("RGB", (800, 400), "#123456")
        app = SimpleNamespace(canvas=canvas, background_image=source, _background_cache=None)
        with patch.object(ImageOps, "fit", wraps=ImageOps.fit) as fit:
            pyrion.Pyrion3DApp._draw_background(app, 300, 240)
            image = canvas.surfaces[-1][0]
            self.assertEqual(image.size, (300, 240))
            self.assertEqual(image.getpixel((150, 120)), (18, 52, 86))
            pyrion.Pyrion3DApp._draw_background(app, 300, 240)
            self.assertIs(canvas.surfaces[-1][0], image)
            self.assertEqual(fit.call_count, 1)
            pyrion.Pyrion3DApp._draw_background(app, 500, 300)
            self.assertEqual(fit.call_count, 2)
            self.assertEqual(canvas.surfaces[-1][0].size, (500, 300))

    def test_scene_without_background_image_still_uses_plain_color(self):
        canvas = Canvas()
        app = SimpleNamespace(canvas=canvas, background_image=None, _background_cache=None)
        pyrion.Pyrion3DApp._draw_background(app, 300, 240)
        self.assertFalse(canvas.surfaces)

    def test_fog_blends_distant_objects_without_affecting_near_objects(self):
        renderer = self.renderer()
        renderer.set_atmosphere({"color": "#405060", "start": 10, "end": 30, "strength": 0.5})
        self.assertEqual(renderer._apply_fog("#000000", 5), "#000000")
        self.assertEqual(renderer._apply_fog("#000000", 30), "#202830")
        self.assertEqual(renderer._apply_fog("#000000", 100), "#202830")

    def test_soft_contact_shadows_cache_and_follow_camera(self):
        canvas = Canvas()
        app = SimpleNamespace(canvas=canvas, _shadow_cache=None, renderer=None,
            scene={"ground_y": 0, "contact_shadows": [{"x": 0, "z": 0, "radius_x": 1, "radius_z": 1}]},
            camera_pose={"position": [0, 2, 6], "yaw": 0, "pitch": -0.2},
            _pose_forward=pyrion.Pyrion3DApp._pose_forward)
        pyrion.Pyrion3DApp._draw_contact_shadows(app, 600, 480, 260)
        image = canvas.surfaces[-1][0]
        self.assertIsNotNone(image.getchannel("A").getbbox())
        self.assertLess(image.getchannel("A").getextrema()[1], 255)
        pyrion.Pyrion3DApp._draw_contact_shadows(app, 600, 480, 260)
        self.assertIs(canvas.surfaces[-1][0], image)
        app.camera_pose["position"][0] = 1
        pyrion.Pyrion3DApp._draw_contact_shadows(app, 600, 480, 260)
        self.assertIsNot(canvas.surfaces[-1][0], image)


if __name__ == "__main__":
    unittest.main()
