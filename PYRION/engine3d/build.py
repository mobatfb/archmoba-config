"""Bundle PYRION Engine modules into the standalone PYRION/app.py updater target.

Run: python PYRION/engine3d/build.py
The original desktop 0.3.0 must be archived at PYRION/release/v0.3.0/app.py.
"""
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
OLD_DESKTOP = PROJECT / "release" / "v0.3.0" / "app.py"
TARGET = PROJECT / "app.py"


def bundle():
    if not OLD_DESKTOP.is_file():
        raise RuntimeError("Missing 0.3.0 historical app.py needed for updater")
    old_source = OLD_DESKTOP.read_text(encoding="utf-8")
    if "def _mem_usage():" not in old_source:
        raise RuntimeError("Historical 0.3.0 updater prelude missing")
    pre = old_source.split("def _mem_usage():", 1)[0]
    module_app = (HERE / "app.py").read_text(encoding="utf-8")
    version_match = re.search(r'DESKTOP_VERSION\s*=\s*"([^"]+)"', module_app)
    if not version_match:
        raise RuntimeError("No DESKTOP_VERSION in engine3d/app.py")
    version = version_match.group(1)
    pre = pre.replace('APP_VERSION = "0.3.0"', f'APP_VERSION = "{version}"')
    pre = pre.replace(
        '"""PYRION OS - interactive, lightweight desktop environment.\n\n'
        'The desktop is rendered with Tkinter Canvas and the Python standard library.\n'
        'No window manager, Pillow, GPU or external UI toolkit is required.\n"""',
        '"""PYRION OS ' + version + ' - standalone PYRION 3D Engine.\n\n'
        'Mesh geometry, perspective projection, and Tk software renderer.\n'
        'Previous desktop preserved under PYRION/release/v0.3.0.\n"""'
    )
    pre = pre.replace('import tkinter as tk\n',
                      'import tkinter as tk\nfrom dataclasses import dataclass\n')
    mesh = (HERE / "mesh.py").read_text(encoding="utf-8")
    mesh = mesh.replace('import math\nfrom dataclasses import dataclass\n', '')
    renderer = (HERE / "renderer.py").read_text(encoding="utf-8")
    renderer = renderer.replace('import math\n', '')
    # Drop top-level imports already supplied by the standalone prelude.
    scene = module_app
    for statement in (
        "import math", "import json", "import urllib.request",
        "from pathlib import Path", "import os", "import sys",
        "import time", "import tkinter as tk",
        "from .mesh import SphereMesh",
        "from .renderer import SoftwareRenderer",
    ):
        scene = re.sub(r"(?m)^" + re.escape(statement) + r"\n", "", scene, count=1)
    scene = scene.rsplit('if __name__ == "__main__":\n    run()', 1)[0]
    entry = '''\nif __name__ == "__main__":
    if "--no-update" not in sys.argv and check_self_update():
        raise SystemExit(0)
    try:
        run()
    except Exception:
        _error_log(traceback.format_exc())
        raise
'''
    result = pre + "\n" + mesh + "\n" + renderer + "\n" + scene + "\n" + entry
    compile(result, str(TARGET), "exec")
    if result.count("class Pyrion3DApp(") != 1:
        raise RuntimeError("Bundling failed: duplicated scene")
    TARGET.write_text(result, encoding="utf-8")
    print(f"Bundled PYRION OS {version} -> {TARGET}")


if __name__ == "__main__":
    bundle()
