"""PYRION 3D Engine: infinitely rotating centered 3D sphere (Tk software)."""
import math
import os
import sys
import time
import tkinter as tk

from .mesh import SphereMesh
from .renderer import SoftwareRenderer

ENGINE_VERSION = "0.1.0"
DESKTOP_VERSION = "0.4.0"


class Pyrion3DApp(tk.Tk):
    """Self-contained, no external GUI dependencies; full-screen desktop scene."""

    def __init__(self):
        super().__init__()
        self.title("PYRION OS - 3D ENGINE")
        self.configure(bg="#050a17")
        self.windowed = (
            "--windowed" in sys.argv or os.environ.get("PYRION_WINDOWED") == "1"
        )
        self._setup_window()

        self.canvas = tk.Canvas(self, bg="#050a17", highlightthickness=0,
                                bd=0, relief="flat", takefocus=1)
        self.canvas.pack(fill="both", expand=True)
        self.mesh = SphereMesh(rings=17, segments=34)
        self.renderer = SoftwareRenderer(self.mesh)
        self.renderer.rotation_y = 0.53
        self.renderer.rotation_x = -0.30
        self.spin_rate = 0.78
        self.base_pitch = -0.30
        self.running = True
        self.show_grid = True
        self.show_info = True
        self.frames = 0
        self.fps = 0.0
        self.visible_triangles = 0
        self.last_time = time.perf_counter()
        self.drag_start = None
        self.angle_delta = 0.0
        self.pending_frame = None
        self._width = 1
        self._height = 1
        self._orb_radius = 1

        self.bind("<space>", lambda _e: self.toggle_animation())
        self.bind("<KeyPress-w>", lambda _e: self.toggle_grid())
        self.bind("<KeyPress-W>", lambda _e: self.toggle_grid())
        self.bind("<KeyPress-i>", lambda _e: self.toggle_info())
        self.bind("<KeyPress-I>", lambda _e: self.toggle_info())
        self.bind("<Left>", lambda _e: self._speed(-0.18))
        self.bind("<Right>", lambda _e: self._speed(+0.18))
        self.bind("<plus>", lambda _e: self._zoom(+0.10))
        self.bind("<minus>", lambda _e: self._zoom(-0.10))
        self.bind("<F11>", self._switch_to_window)
        self.bind("<Control-q>", lambda _e: self.close())
        self.bind("<Escape>", lambda _e: self._escape())
        self.canvas.bind("<ButtonPress-1>", self._mouse_press, add="+")
        self.canvas.bind("<B1-Motion>", self._mouse_move, add="+")
        self.canvas.bind("<ButtonRelease-1>", self._mouse_release, add="+")
        self.canvas.bind("<MouseWheel>", self._scroll)
        self.canvas.bind("<Button-4>", lambda _e: self._zoom(+0.10))
        self.canvas.bind("<Button-5>", lambda _e: self._zoom(-0.10))
        self.canvas.bind("<Configure>", lambda _e: self._request_frame())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(80, self._frame)
        self.after(1000, self._keep_as_desktop)

    def _setup_window(self):
        self.update_idletasks()
        if self.windowed:
            self.geometry("1100x720")
            self.minsize(660, 440)
        elif os.name == "nt":
            self.attributes("-fullscreen", True)
        else:
            # Xorg minimal boot: no requirement for a window manager.
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            self.overrideredirect(True)
            self.geometry(f"{sw}x{sh}+0+0")
            self.after(180, self._repair_fullscreen_geometry)

    def _repair_fullscreen_geometry(self):
        if not self.windowed:
            self.geometry(
                f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0"
            )

    def _keep_as_desktop(self):
        try:
            if not self.windowed:
                self.attributes("-topmost", False)
                self.lower()
            self.after(1250, self._keep_as_desktop)
        except tk.TclError:
            return

    def _switch_to_window(self, _event=None):
        if self.windowed:
            return
        if os.name == "nt":
            self.attributes("-fullscreen", False)
        else:
            self.overrideredirect(False)
        self.windowed = True
        self.geometry("1100x720")
        self._request_frame()

    def close(self):
        if self.pending_frame is not None:
            try:
                self.after_cancel(self.pending_frame)
            except tk.TclError:
                pass
        self.destroy()

    def _escape(self):
        if self.show_info:
            self.show_info = False
            self._request_frame()

    def toggle_animation(self):
        self.running = not self.running
        self._request_frame()

    def toggle_grid(self):
        self.show_grid = not self.show_grid
        self.renderer.wireframe = not self.renderer.wireframe
        self.show_grid = True
        self._request_frame()

    def toggle_info(self):
        self.show_info = not self.show_info
        self._request_frame()

    def _speed(self, amount):
        self.spin_rate = max(0.15, min(3.5, self.spin_rate + amount))
        self._request_frame()

    def _zoom(self, amount):
        self.renderer.zoom = max(0.55, min(1.42, self.renderer.zoom + amount))
        self._request_frame()

    def _mouse_press(self, event):
        cx, cy = self._width * 0.5, self._height * 0.475
        if (event.x - cx)**2 + (event.y - cy)**2 < self._orb_radius ** 2:
            self.drag_start = (event.x, event.y)

    def _mouse_move(self, event):
        if self.drag_start is None:
            return
        dx = event.x - self.drag_start[0]
        dy = event.y - self.drag_start[1]
        self.renderer.rotation_y += dx * 0.007
        self.base_pitch = max(-1.35, min(1.35,
                              self.base_pitch - dy * 0.007))
        self.drag_start = (event.x, event.y)
        self._request_frame()

    def _mouse_release(self, _event):
        self.drag_start = None

    def _scroll(self, event):
        self._zoom(0.08 if event.delta > 0 else -0.08)

    def _request_frame(self):
        if self.pending_frame is None:
            self.pending_frame = self.after_idle(self._draw)

    def _color(self, r, g, b):
        return "#%02x%02x%02x" % (int(r), int(g), int(b))

    def _background(self, width, height):
        c = self.canvas
        c.create_rectangle(0, 0, width, height, fill="#050917", outline="")
        # Thin atmospheric bands for depth, drawn without external images.
        for i in range(18):
            y1 = int(i * height / 18)
            y2 = int((i + 1) * height / 18) + 1
            c.create_rectangle(0, y1, width, y2,
                               fill=self._color(5 + i//5, 9 + i//3,
                                                23 + i//2), outline="")
        for i in range(40):
            x = ((i * 7907 + 135) % 10007) / 10007.0 * width
            y = ((i * 2017 + 43) % 10009) / 10009.0 * height * .75
            bright = "#31527f" if i % 7 == 0 else "#192d4d"
            rr = 1.3 if i % 9 == 0 else 0.65
            c.create_oval(x-rr, y-rr, x+rr, y+rr, fill=bright, outline="")
        cx, cy = width*.5, height*.475
        # Discrete atmosphere, behind the 3D geometry.
        glow_size = min(height*.56,width*.46)*.48
        for i in range(7, 0, -1):
            r = glow_size * (1.02 + i*.019)
            col = self._color(8 + i//2, 16 + i, 38 + i*2)
            c.create_oval(cx-r,cy-r,cx+r,cy+r,outline=col,width=1)
        y = height*.715
        for i in range(4):
            r = width*(.055 + i*.028)
            c.create_oval(cx-r,y-8-i*3,cx+r,y+8+i*3,
                          outline=self._color(10,32+i*2,66+i*5),width=1)
        c.create_line(width*.12,height*.925,width*.88,height*.925,
                      fill="#132a4b",width=1)

    def _label(self, x, y, txt, size=11, color="#cee4ff",
               anchor="nw", bold=False, tag=None):
        size = max(8, int(size * self.scale))
        return self.canvas.create_text(
            x,y,text=txt,fill=color,anchor=anchor,
            font=("DejaVu Sans",size,"bold" if bold else "normal"),
            tags=(tag,) if tag else ()
        )

    def _button(self, x1, y1, x2, y2, title, action, selected=False):
        tag = "ui_" + str(self._button_id)
        self._button_id += 1
        self.canvas.create_rectangle(
            x1, y1, x2, y2,
            fill="#1c315f" if selected else "#0b1930",
            outline="#6a9efb" if selected else "#294972",
            width=1,tags=(tag,)
        )
        self._label((x1+x2)/2,(y1+y2)/2,title,10,
                    "#d8ecff" if selected else "#8faed9",
                    anchor="center",bold=selected,tag=tag)
        self.canvas.tag_bind(tag,"<Button-1>",lambda _e: action())
        self.canvas.tag_bind(tag,"<Enter>",
                             lambda _e: self.canvas.configure(cursor="hand2"))
        self.canvas.tag_bind(tag,"<Leave>",
                             lambda _e: self.canvas.configure(cursor=""))

    def _hud(self, w, h):
        c = self.canvas
        s = self.scale
        pad = 27*s
        self._label(pad,24*s,"PYRION",22,"#e3f3ff",bold=True)
        self._label(pad+7*s,57*s,"3D ENGINE / 0.1.0",10,"#63baff")
        self._label(w-pad,27*s,"SCENE 01    |    UV SPHERE",10,
                    "#8ca9d3",anchor="ne",bold=True)
        c.create_line(pad,78*s,w-pad,78*s,fill="#1b3355",width=1)
        if self.show_info:
            info_x = pad
            info_y = h*.34
            self._label(info_x,info_y,"GEOMETRY",10,"#5ec5ff",bold=True)
            for i,item in enumerate((
                "Mesh    : UV Sphere",
                f"Vertices: {self.mesh.vertex_count}",
                f"Triangles: {self.mesh.triangle_count}",
                f"Visible  : {self.visible_triangles}",
                "Material: procedural",
                "Camera  : perspective",
            )):
                self._label(info_x,info_y+(26+i*25)*s,item,10,"#92acd3")
            right_x = w-pad
            self._label(right_x,info_y,"ROTATION",10,"#a987ff",
                        anchor="ne",bold=True)
            for i,item in enumerate((
                f"Y axis  {math.degrees(self.renderer.rotation_y)%360:05.1f} deg",
                f"X axis  {math.degrees(self.renderer.rotation_x):+05.1f} deg",
                f"Speed   {self.spin_rate:.2f} rad/s",
                "Loop    INFINITE" if self.running else "Loop    PAUSED",
                f"FPS     {self.fps:04.1f}",
                "Render  SOFTWARE",
            )):
                self._label(right_x,info_y+(26+i*25)*s,item,10,"#92acd3",anchor="ne")
        c.create_line(pad,h-99*s,w-pad,h-99*s,fill="#1b3355",width=1)
        self._label(w*.5,h-155*s,"PYRION CORE",14,"#b1cfff",anchor="center",bold=True)
        self._label(w*.5,h-133*s,"REAL 3D MESH  //  CONTINUOUS ROTATION",9,
                    "#638db9",anchor="center")
        self._button_id = 0
        bw = 103*s
        gap = 9*s
        labels = [
            ("PAUSAR" if self.running else "GIRAR",self.toggle_animation,not self.running),
            ("MALLA" if not self.renderer.wireframe else "SOLIDO",self.toggle_grid,self.renderer.wireframe),
            ("- VELOCIDAD",lambda: self._speed(-0.18),False),
            ("+ VELOCIDAD",lambda: self._speed(0.18),False),
            ("- ZOOM",lambda: self._zoom(-0.10),False),
            ("+ ZOOM",lambda: self._zoom(0.10),False),
            ("INFO",self.toggle_info,self.show_info),
        ]
        if w < 870:
            labels = [
                ("PAUSA" if self.running else "GIRAR",self.toggle_animation,not self.running),
                ("MALLA" if not self.renderer.wireframe else "SOLIDO",self.toggle_grid,self.renderer.wireframe),
                ("LENTO",lambda: self._speed(-0.18),False),
                ("RAPIDO",lambda: self._speed(0.18),False),
                ("INFO",self.toggle_info,self.show_info),
            ]
        total=len(labels)*bw+(len(labels)-1)*gap
        x=w*.5-total*.5
        for label,fn,selected in labels:
            self._button(x,h-74*s,x+bw,h-41*s,label,fn,selected)
            x+=bw+gap
        self._label(w*.5,h-20*s,
                    "DRAG: ROTATE  |  W: WIREFRAME  |  SPACE: PAUSE  |  F11: WINDOW",
                    9,"#527399",anchor="center")

    def _draw(self):
        self.pending_frame=None
        if not self.winfo_exists():
            return
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 100 or h < 100:
            return
        self._width,self._height = w,h
        self.scale=max(.70,min(1.3,min(w/1280,h/720)))
        self.canvas.delete("all")
        self._background(w,h)
        diameter=min(h*.55,w*.51)
        self._orb_radius=diameter*.50
        cx, cy=w*.5, h*.475
        self.visible_triangles = self.renderer.draw(
            self.canvas,cx,cy,diameter,
            draw_graticules=self.show_grid
        )
        # Subtle rim light at the contour; the main sphere remains a projected mesh.
        rim=diameter*.483 * self.renderer.zoom
        for i in range(3):
            d=i*2
            self.canvas.create_arc(cx-rim-d,cy-rim-d,cx+rim+d,cy+rim+d,
                                   start=110,extent=113,style="arc",
                                   outline=("#244a89","#2c5aa3","#397ac4")[i],width=1)
        self._hud(w,h)

    def _frame(self):
        now = time.perf_counter()
        elapsed = max(0,min(.1,now - self.last_time))
        self.last_time=now
        if self.running:
            self.renderer.rotation_y=(self.renderer.rotation_y + self.spin_rate*elapsed) % (math.pi*2)
            self.renderer.rotation_x=(self.base_pitch + math.sin(now*.30)*.045)
        if elapsed>0:
            instantaneous = 1.0/elapsed
            self.fps = .88*self.fps + .12*instantaneous if self.fps else instantaneous
        self.frames+=1
        self._draw()
        try:
            self.after(40, self._frame)
        except tk.TclError:
            pass


def run():
    app = Pyrion3DApp()
    app.mainloop()


if __name__ == "__main__":
    run()
