import json
import queue
import tempfile
import threading
import unittest
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch

import AMDEV.app as amdev
import PTM.app as ptm
import PYRION.app as pyrion


class InlineThread:
    def __init__(self, target, daemon):
        self.target = target

    def start(self):
        self.target()


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.network = patch.object(amdev.urllib.request, "urlopen", side_effect=AssertionError("Unexpected network"))
        self.urlopen = self.network.start()
        self.addCleanup(self.network.stop)

    def release(self, name, version):
        folder = self.root / name
        folder.mkdir(exist_ok=True)
        source = f'APP_VERSION = "{version}"\n'
        (folder / "app.py").write_text(source, encoding="utf-8")
        config = {"version": version, "app_path": f"{name}/app.py"}
        (folder / "config.json").write_text(json.dumps(config), encoding="utf-8")
        return source

    def test_manual_update_detects_new_local_version_and_restarts(self):
        source = self.release("AMDEV", "9.0.0")
        fake = SimpleNamespace(_update_running=False, _update_queue=queue.Queue(), status=Mock())
        with patch.object(amdev, "MODO_LOCAL", True), patch.object(amdev, "LOCAL_ROOT", self.root), \
             patch.object(amdev.threading, "Thread", InlineThread), \
             patch.object(amdev, "_launch_update_helper") as restart:
            amdev.AMDEVApp.update_amdev_now(fake)
            restart.assert_called_once_with(source)
            self.assertEqual(fake._update_queue.get()[0], "status")
            self.assertEqual(fake._update_queue.get(), ("restart", "9.0.0"))
            self.assertEqual((self.root / "AMDEV/app.py").read_text(), source)
        self.urlopen.assert_not_called()

    def test_current_local_version_is_not_reinstalled(self):
        self.release("AMDEV", amdev.APP_VERSION)
        with patch.object(amdev, "MODO_LOCAL", True), patch.object(amdev, "LOCAL_ROOT", self.root), \
             patch.object(amdev, "_launch_update_helper") as restart:
            self.assertFalse(amdev.check_self_update())
            restart.assert_not_called()

    def test_mismatched_local_release_is_rejected(self):
        self.release("AMDEV", "9.0.0")
        (self.root / "AMDEV/app.py").write_text('APP_VERSION = "8.0.0"\n')
        with patch.object(amdev, "MODO_LOCAL", True), patch.object(amdev, "LOCAL_ROOT", self.root):
            with self.assertRaisesRegex(RuntimeError, "no coincide"):
                amdev._fetch_self_release()

    def test_local_helper_does_not_stage_or_replace_source(self):
        source = self.release("AMDEV", "9.0.0")
        target = self.root / "AMDEV/app.py"
        with patch.object(amdev, "MODO_LOCAL", True), patch.object(amdev, "__file__", str(target)), \
             patch.object(amdev.subprocess, "Popen"):
            amdev._launch_update_helper(source)
        self.assertFalse(target.with_suffix(".py.pending").exists())
        helper = target.with_suffix(".py.updater.py").read_text()
        self.assertIn("range(0 if True else 80)", helper)
        compile(helper, "helper", "exec")
        self.assertEqual(target.read_text(), source)

    def test_online_update_retains_pinned_release_validation(self):
        source = 'APP_VERSION = "9.0.0"\n'
        config = {"version": "9.0.0", "app_path": "AMDEV/app.py", "release_commit": "a" * 40}
        first = Mock()
        first.__enter__ = Mock(return_value=SimpleNamespace(read=lambda: json.dumps(config).encode()))
        first.__exit__ = Mock(return_value=False)
        second = Mock()
        second.__enter__ = Mock(return_value=SimpleNamespace(read=lambda: source.encode()))
        second.__exit__ = Mock(return_value=False)
        with patch.object(amdev, "MODO_LOCAL", False), \
             patch.object(amdev.urllib.request, "urlopen", side_effect=[first, second]) as fetch:
            self.assertEqual(amdev._fetch_self_release(), (config, source))
            self.assertIn("/AMDEV/config.json", fetch.call_args_list[0].args[0].full_url)
            self.assertIn("/" + "a" * 40 + "/AMDEV/app.py", fetch.call_args_list[1].args[0].full_url)

    def test_children_detect_local_updates_without_replacing_files(self):
        for name, module in (("PTM", ptm), ("PYRION", pyrion)):
            source = self.release(name, "9.0.0")
            target = self.root / name / "app.py"
            with self.subTest(name=name), patch.dict(module.os.environ, {"AMDEV_MODE": "local"}), \
                 patch.object(module, "__file__", str(target)), patch.object(module.subprocess, "Popen") as launch:
                self.assertTrue(module.check_self_update(restart=False))
                launch.assert_not_called()
                self.assertEqual(target.read_text(), source)
                self.assertFalse(target.with_suffix(".py.update").exists())
        self.urlopen.assert_not_called()

    def test_ptm_uses_local_catalog_and_tool_even_when_forced(self):
        folder = self.root / "PTM"
        folder.mkdir()
        (folder / "tools").mkdir()
        (folder / "tools/demo.py").write_text('print("local")\n')
        (folder / "guide.csv").write_text("ruta;nombre\ntools/demo.py;Demo\n")
        fake = SimpleNamespace(base_dir=folder, guide_path=folder / "guide.csv", tools_dir=folder / "tools",
                               _tool_download_write_lock=threading.Lock())
        for method in ("_get_valid_cached_tool", "_store_tool_download", "_local_guide_git_sha"):
            setattr(fake, method, MethodType(getattr(ptm.PTMApp, method), fake))
        with patch.dict(ptm.os.environ, {"AMDEV_MODE": "local"}):
            self.assertTrue(ptm.PTMApp._sync_guide_if_needed(fake))
            self.assertFalse(ptm.PTMApp._sync_guide_if_needed(fake))
            tool = {"repo_path": "tools/demo.py"}
            self.assertEqual(ptm.PTMApp._ensure_tool_local(fake, tool, force_remote=True), folder / "tools/demo.py")
            staged = ptm.PTMApp._ensure_tool_local(fake, tool, force_remote=True, stage_only=True)
            self.assertEqual(staged, folder / "tools/demo.py.ptmreload")
            self.assertTrue(staged.is_file())
            with self.assertRaises(FileNotFoundError):
                ptm.PTMApp._ensure_tool_local(fake, {"repo_path": "tools/missing.py"})
        self.urlopen.assert_not_called()

    def test_pyrion_missing_local_resources_never_fall_back_to_network(self):
        with patch.dict(pyrion.os.environ, {"AMDEV_MODE": "local"}), \
             patch.object(pyrion, "__file__", str(self.root / "PYRION/app.py")):
            with self.assertRaises(FileNotFoundError):
                pyrion._scene_json("missing.json")
            self.assertIsNone(pyrion._scene_texture("missing.gif"))
        self.urlopen.assert_not_called()

    def test_versions_match_configs(self):
        root = Path(__file__).resolve().parents[1]
        for name, module in (("AMDEV", amdev), ("PTM", ptm), ("PYRION", pyrion)):
            config = json.loads((root / name / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(module.APP_VERSION, config["version"])

    def test_monumental_shock_loads_locally_with_spinning_crystal_stairs(self):
        with patch.dict(pyrion.os.environ, {"AMDEV_MODE": "local"}):
            scene, objects = pyrion.load_selected_scene()
        self.assertEqual(scene["name"], "monumentalShock")
        self.assertEqual(len(objects), len(scene["objects"]))
        self.assertEqual(len({obj["id"] for obj in objects}), len(objects))
        by_id = {obj["id"]: obj for obj in objects}
        for side in ("left", "right"):
            stairs = [by_id[f"{side}_step_{i:02d}"] for i in range(1, 7)]
            heights = [obj["position"][1] for obj in stairs]
            self.assertEqual(heights, sorted(heights, reverse=True))
            self.assertTrue(all(abs(obj["speed"]) > 0 for obj in stairs))
            self.assertGreater(by_id["summit_crystal"]["position"][1], max(heights))
        self.assertEqual(by_id["central_tower"]["speed"], 0)
        self.assertEqual(by_id["central_tower"]["rotation_x"], 0)
        self.assertLess(by_id["sanctuary_terrace"]["render_layer"], by_id["central_tower"]["render_layer"])
        self.urlopen.assert_not_called()

    def manual_update_app(self):
        app = SimpleNamespace(_update_running=False, _update_events=queue.Queue(),
                              _request_frame=Mock(), after=Mock(), _schedule_engine=Mock(), close=Mock(), _refresh_live=Mock())
        app._poll_manual_update = MethodType(pyrion.Pyrion3DApp._poll_manual_update, app)
        return app

    def test_refresh_button_searches_without_blocking_or_duplicate_requests(self):
        app = self.manual_update_app()
        with patch.object(threading, "Thread", InlineThread), \
             patch.object(pyrion, "check_self_update", return_value=False) as checker, \
             patch("tkinter.messagebox.showinfo") as info:
            pyrion.Pyrion3DApp._check_updates_now(app)
            pyrion.Pyrion3DApp._check_updates_now(app)
            checker.assert_called_once_with(restart=False, raise_errors=True)
            self.assertTrue(app._update_running)
            info.assert_not_called()
            app._poll_manual_update()
            self.assertFalse(app._update_running)
            info.assert_not_called()
            app._refresh_live.assert_called_once()
            app.close.assert_not_called()

    def test_refresh_button_reports_errors_and_allows_retry(self):
        app = self.manual_update_app()
        with patch.object(threading, "Thread", InlineThread), \
             patch.object(pyrion, "check_self_update", side_effect=RuntimeError("Missing local config")), \
             patch("tkinter.messagebox.showerror") as error:
            pyrion.Pyrion3DApp._check_updates_now(app)
            error.assert_not_called()
            app._poll_manual_update()
            error.assert_called_once()
            self.assertIn("Missing local config", error.call_args.args[1])
            self.assertFalse(app._update_running)
            app.close.assert_not_called()

    def test_refresh_button_reloads_in_place_only_after_new_release_is_ready(self):
        app = self.manual_update_app()
        with patch.object(threading, "Thread", InlineThread), \
             patch.object(pyrion, "check_self_update", return_value=True), \
             patch.object(pyrion.os, "name", "nt"), \
             patch.object(pyrion.subprocess, "Popen") as launch:
            pyrion.Pyrion3DApp._check_updates_now(app)
            launch.assert_not_called()
            app._refresh_live.assert_not_called()
            app._poll_manual_update()
            app._refresh_live.assert_called_once()
            launch.assert_not_called()
            app.close.assert_not_called()

    def live_session(self):
        class Session(pyrion.Pyrion3DApp):
            _cancel_engine_callbacks = pyrion.Pyrion3DApp._cancel_engine_callbacks
            def configure(self, **kwargs):
                self.configured = kwargs

            def _bind_controls(self):
                self.bound = True

            def _request_frame(self):
                self.requested = True

        session = object.__new__(Session)
        session.canvas = Mock()
        session.scene = {"name": "previous"}
        session.objects = []
        session.background = "old"
        session.camera_pose = {"position": [1, 2, 3], "yaw": 0.7, "pitch": 0.1}
        session.focus_pose = None
        session.base_pitch = 0.3
        session.spotlight_enabled = True
        session.material_mode = "mat"
        session.pending_frame = None
        session.running = False
        session.spin_rate = 1.7
        session.windowed = True
        session.after_cancel = Mock()
        session._engine_generation = 3
        session._engine_after = {"old-frame", "old-desktop"}
        session._old_engine_sentinel = True
        session._shell_keys = {"canvas", "windowed", "after_cancel", "_shell_keys", "_engine_generation", "_engine_after", "_live_module_name"}
        return session

    def test_reset_replaces_all_engine_state_and_keeps_window_and_canvas(self):
        target = self.root / "app.py"
        target.write_text('''
APP_VERSION = "9.0.0"
BACKGROUND = "new"
import tkinter as tk
from PYRION.app import Pyrion3DApp as Engine
class Pyrion3DApp(Engine):
    def configure(self, **kwargs): self.configured = kwargs
    def _bind_controls(self): self.bound = True
    def _request_frame(self): self.requested = True
    def changed_method(self): return "new code"
def load_selected_scene(): return {"name": "previous", "revision": "new"}, []
''', encoding="utf-8")
        target.with_name("config.json").write_text('{"version": "9.0.0"}')
        app = self.live_session()
        identity, canvas, camera = id(app), app.canvas, app.camera_pose
        timer_ids = iter(f"timer-{i}" for i in range(20))
        with patch.object(pyrion, "__file__", str(target)), patch.object(pyrion.subprocess, "Popen") as launch, \
             patch.object(pyrion.tk.Misc, "after", side_effect=lambda *args: next(timer_ids)):
            pyrion.Pyrion3DApp._refresh_live(app)
            launch.assert_not_called()
        self.addCleanup(pyrion.sys.modules.pop, app._live_module_name, None)
        self.assertEqual(id(app), identity)
        self.assertIs(app.canvas, canvas)
        self.assertIsNot(app.camera_pose, camera)
        self.assertEqual(app.camera_pose["position"], [0, 0, 3.85])
        self.assertEqual(app.changed_method(), "new code")
        self.assertEqual(app.scene["revision"], "new")
        self.assertTrue(app.running)
        self.assertEqual(app.spin_rate, 1.0)
        self.assertNotIn("_old_engine_sentinel", app.__dict__)
        self.assertEqual(app._engine_generation, 4)
        self.assertEqual(len(app._engine_after), 2)
        self.assertEqual(app.frames, 0)
        self.assertEqual(app.info_mode, "compacto")
        self.assertEqual(app._sticks, {"move": (0.0, 0.0), "look": (0.0, 0.0)})
        self.assertTrue(app.bound)
        self.assertTrue(app.requested)
        new_source = target.read_text().replace(
            '{"name": "previous", "revision": "new"}',
            '{"name": "another project", "navigation": {"camera_position": [7, 8, 9]}}')
        target.write_text(new_source)
        with patch.object(pyrion, "__file__", str(target)), \
             patch.object(pyrion.tk.Misc, "after", side_effect=lambda *args: next(timer_ids)):
            pyrion.Pyrion3DApp._refresh_live(app)
        self.addCleanup(pyrion.sys.modules.pop, app._live_module_name, None)
        self.assertEqual(app.camera_pose["position"], [7, 8, 9])
        self.assertEqual(len(app._engine_after), 2)
        self.assertEqual(app._engine_generation, 5)

    def test_old_generation_callbacks_cannot_run_after_reset(self):
        app = SimpleNamespace(_engine_generation=1, _engine_after=set())
        callback = Mock()
        with patch.object(pyrion.tk.Misc, "after", return_value="old-timer") as schedule:
            pyrion.Pyrion3DApp._schedule_engine(app, 16, callback)
            fire = schedule.call_args.args[2]
        app._engine_generation = 2
        fire()
        callback.assert_not_called()
        self.assertFalse(app._engine_after)

    def test_total_reset_recompiles_local_modules_even_without_version_change(self):
        target = self.root / "app.py"
        target.write_text('APP_VERSION = "9.0.0"\n')
        target.with_name("config.json").write_text('{"version": "9.0.0"}')
        engine = self.root / "engine3d"
        engine.mkdir()
        mesh = engine / "mesh.py"
        mesh.write_text('VALUE = "first"\n')
        (engine / "renderer.py").write_text('from .mesh import VALUE\n')
        (engine / "app.py").write_text('''
from PYRION.app import Pyrion3DApp as Engine
from .renderer import VALUE
DESKTOP_VERSION = "9.0.0"
class Pyrion3DApp(Engine):
    def configure(self, **kwargs): pass
    def _bind_controls(self): pass
    def _request_frame(self): pass
    def marker(self): return VALUE
def load_selected_scene(): return {"name": "modular"}, []
''')
        app = self.live_session()
        timers = iter(f"fresh-{i}" for i in range(10))
        with patch.dict(pyrion.os.environ, {"AMDEV_MODE": "local"}), \
             patch.object(pyrion, "__file__", str(target)), \
             patch.object(pyrion.tk.Misc, "after", side_effect=lambda *args: next(timers)):
            pyrion.Pyrion3DApp._refresh_live(app)
            first_package = app._live_module_name
            self.assertEqual(app.marker(), "first")
            mesh.write_text('VALUE = "second"\n')
            pyrion.Pyrion3DApp._refresh_live(app)
            self.assertEqual(app.marker(), "second")
            self.assertEqual(len(app._engine_after), 2)
        self.assertFalse(any(name == first_package or name.startswith(first_package + ".") for name in pyrion.sys.modules))
        prefix = app._live_module_name
        for name in list(pyrion.sys.modules):
            if name == prefix or name.startswith(prefix + "."):
                pyrion.sys.modules.pop(name, None)

    def test_reset_rolls_back_if_new_controls_fail_during_commit(self):
        target = self.root / "app.py"
        target.write_text('''
APP_VERSION = "9.0.0"
from PYRION.app import Pyrion3DApp as Engine
class Pyrion3DApp(Engine):
    def configure(self, **kwargs): pass
    def _bind_controls(self): raise RuntimeError("New controls failed")
def load_selected_scene(): return {"name": "new"}, []
''', encoding="utf-8")
        target.with_name("config.json").write_text('{"version": "9.0.0"}')
        app = self.live_session()
        previous_class, camera = app.__class__, app.camera_pose
        timer_ids = iter(f"recovered-{i}" for i in range(10))
        with patch.object(pyrion, "__file__", str(target)), \
             patch.object(pyrion.tk.Misc, "after", side_effect=lambda *args: next(timer_ids)):
            with self.assertRaisesRegex(RuntimeError, "New controls failed"):
                pyrion.Pyrion3DApp._refresh_live(app)
        self.assertIs(app.__class__, previous_class)
        self.assertIs(app.camera_pose, camera)
        self.assertEqual(len(app._engine_after), 2)

    def test_legacy_window_is_adopted_with_a_clean_engine_without_recreating_tk(self):
        app = self.live_session()
        app.tk = Mock()
        app.tk.splitlist.return_value = ("legacy-frame", "legacy-desktop")
        del app._engine_generation
        canvas, interpreter = app.canvas, app.tk
        with patch.object(pyrion.tk.Misc, "after", side_effect=["new-frame", "new-desktop"]):
            pyrion.Pyrion3DApp._adopt_legacy_window(app)
        self.assertIs(app.canvas, canvas)
        self.assertIs(app.tk, interpreter)
        self.assertEqual(app.camera_pose["position"], [0, 0, 3.85])
        self.assertTrue(app.running)
        self.assertNotIn("_old_engine_sentinel", app.__dict__)
        self.assertEqual(app._engine_after, {"new-frame", "new-desktop"})

    def test_failed_live_refresh_keeps_previous_code_scene_and_window(self):
        target = self.root / "app.py"
        target.write_text('''
APP_VERSION = "9.0.0"
import tkinter as tk
class Pyrion3DApp(tk.Tk): pass
def load_selected_scene(): raise ValueError("Broken new scene")
''', encoding="utf-8")
        target.with_name("config.json").write_text('{"version": "9.0.0"}')
        app = self.live_session()
        previous_class, previous_scene, previous_canvas = app.__class__, app.scene, app.canvas
        with patch.object(pyrion, "__file__", str(target)):
            with self.assertRaisesRegex(ValueError, "Broken new scene"):
                pyrion.Pyrion3DApp._refresh_live(app)
        self.assertIs(app.__class__, previous_class)
        self.assertIs(app.scene, previous_scene)
        self.assertIs(app.canvas, previous_canvas)
        app.canvas.configure.assert_not_called()


if __name__ == "__main__":
    unittest.main()
