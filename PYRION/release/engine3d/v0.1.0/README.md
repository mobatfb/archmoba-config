# PYRION 3D Engine 0.1.0

First mesh: a real UV-sphere composed of vertices and triangles, centered on
screen, continuously rotating about its Y axis. The camera projects a 3D mesh
with perspective, Lambert-inspired procedural lighting and hidden-face culling.

No external Python dependencies; uses only standard library and Tkinter. It
renders polygons in software: not yet GPU-accelerated OpenGL.

## Run

From `PYRION/`:

```bash
python app.py --windowed --no-update
```

Or run the modular engine directly:

```bash
python -m engine3d --windowed
```

Without `--windowed`, PYRION becomes a full-screen background desktop. Press
F11 to switch to windowed mode. Controls:

- Sphere: drag to rotate its angle manually.
- SPACE: pause / resume infinite rotation.
- W: show / hide wireframe.
- Left / Right: adjust rotation speed.
- Plus / Minus or wheel: zoom.
- I: show / hide mesh information.
- Ctrl+Q: close.

The main `PYRION/app.py` includes an embedded standalone copy of the engine
for reliable offline use and the existing single-file updater. The modular
files here are kept as the editable source for future engine features.

Prior PYRION OS desktop 0.3.0 is stored at `PYRION/release/v0.3.0/`.

## Rebuild the standalone main app after engine changes

```bash
python engine3d/build.py
```

It bundles the engine modules into `PYRION/app.py`, preserving the pre-existing
single-file updater. Archive each published app version in `PYRION/release/`.
