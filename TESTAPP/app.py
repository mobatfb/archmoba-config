# ARGUMENTOS: ptm launcher lanzador buscador ejecutor py python herramientas scripts pestañas icono flotante
import ast
import importlib.util
import os
import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

APP_TITLE = "PTM - Buscador y lanzador de herramientas"
APP_VERSION = "1.0.0"

# Paleta tomada del boceto del usuario.
TEAL = "#176684"
TEAL_DARK = "#0F536E"
RED = "#FF1616"
WHITE = "#FFFFFF"
BLACK = "#101010"
LIGHT = "#F4F4F4"
MID = "#D7D7D7"
MUTED = "#666666"


class TabButton(tk.Canvas):
    """Pestaña dibujada por código con esquina roja tipo PTM."""

    def __init__(self, parent, title, on_open, on_close=None, active=False, width=118, height=30):
        super().__init__(parent, width=width, height=height, highlightthickness=0, bd=0, bg=WHITE)
        self.title = title
        self.on_open = on_open
        self.on_close = on_close
        self.tab_width = width
        self.tab_height = height
        self.active = active
        self.bind("<Button-1>", self._click)
        self.bind("<Button-3>", self._right_click)
        self.draw()

    def set_active(self, active):
        self.active = active
        self.draw()

    def set_size(self, width):
        self.tab_width = width
        self.configure(width=width)
        self.draw()

    def draw(self):
        self.delete("all")
        w, h = self.tab_width, self.tab_height
        fill = WHITE if self.active else TEAL
        fg = TEAL_DARK if self.active else WHITE
        outline = TEAL_DARK
        self.create_rectangle(1, 1, w - 1, h - 1, fill=fill, outline=outline, width=1)
        self.create_polygon(w - 18, 1, w - 1, 1, w - 1, 18, fill=RED, outline=RED)
        if self.active:
            self.create_rectangle(1, h - 5, w - 1, h - 1, fill=RED, outline=RED)
        max_chars = max(7, int((w - 20) / 7.2))
        shown = self.title if len(self.title) <= max_chars else self.title[: max_chars - 1] + "…"
        self.create_text(w / 2, h / 2 - (2 if self.active else 0), text=shown,
                         fill=fg, font=("Segoe UI", 9, "bold" if self.active else "normal"))

    def _click(self, event):
        # En pestañas de herramientas, la esquina roja también sirve para cerrarlas.
        if self.on_close and event.x >= self.tab_width - 22 and event.y <= 22:
            self.on_close()
        else:
            self.on_open()

    def _right_click(self, _event):
        if self.on_close:
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label="Cerrar pestaña", command=self.on_close)
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())


class FloatingPTM(tk.Toplevel):
    """Icono flotante PTM generado 100% con Canvas; no usa PNG/ICO."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="#010101")
        try:
            self.wm_attributes("-transparentcolor", "#010101")
        except tk.TclError:
            pass

        self.w = 96
        self.h = 48
        self.geometry(f"{self.w}x{self.h}+0+0")
        self.canvas = tk.Canvas(self, width=self.w, height=self.h, bg="#010101",
                                highlightthickness=0, bd=0, cursor="hand2")
        self.canvas.pack(fill="both", expand=True)
        self._draw()

        self.canvas.bind("<Button-1>", self._left_down)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._left_up)
        self.canvas.bind("<Button-3>", self._menu)
        self.canvas.bind("<Enter>", lambda _e: self._draw(hover=True))
        self.canvas.bind("<Leave>", lambda _e: self._draw(hover=False))
        self.bind("<Double-Button-1>", lambda _e: self.app.show_main())

        self._dragging = False
        self._press_xy = (0, 0)
        self._place_default()

    def _draw(self, hover=False):
        self.canvas.delete("all")
        w, h = self.w, self.h
        fill = "#1E7395" if hover else TEAL
        self.canvas.create_rectangle(2, 2, w - 2, h - 2, fill=fill, outline=BLACK, width=1)
        self.canvas.create_polygon(w - 18, 2, w - 2, 2, w - 2, 18, fill=RED, outline=RED)
        self.canvas.create_rectangle(2, h - 8, w - 2, h - 2, fill=RED, outline=RED)
        self.canvas.create_text(w / 2, 17, text="PTM", fill=WHITE, font=("Segoe UI", 17, "bold"))
        self.canvas.create_text(w / 2, h - 5, text="Buscador y lanzador", fill=WHITE,
                                font=("Segoe UI", 5, "bold"))

    def _place_default(self):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(10, sw - self.w - 18)
        y = max(10, sh - self.h - 70)
        self.geometry(f"{self.w}x{self.h}+{x}+{y}")

    def _left_down(self, event):
        self._dragging = False
        self._press_xy = (event.x_root, event.y_root)
        self._origin = (self.winfo_x(), self.winfo_y())

    def _drag(self, event):
        dx = event.x_root - self._press_xy[0]
        dy = event.y_root - self._press_xy[1]
        if abs(dx) + abs(dy) > 4:
            self._dragging = True
        x = self._origin[0] + dx
        y = self._origin[1] + dy
        self.geometry(f"+{x}+{y}")

    def _left_up(self, _event):
        if not self._dragging:
            self.app.toggle_main()

    def _menu(self, _event):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Abrir PTM", command=self.app.show_main)
        menu.add_command(label="Recargar herramientas", command=self.app.reload_tools)
        menu.add_command(label="Abrir carpeta de herramientas", command=self.app.open_tools_folder)
        menu.add_separator()
        menu.add_command(label="Salir", command=self.app.exit_app)
        menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())


class PTMApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.configure(bg=WHITE)
        self.base_dir = Path(__file__).resolve().parent
        self.tools_dir = self.base_dir / "tools"
        self.tools_dir.mkdir(exist_ok=True)  # Vacía: PTM no incluye módulos de ejemplo.

        self.query = tk.StringVar()
        self.tools = []
        self.open_tabs = {}       # key -> metadata/content
        self.tab_widgets = {}
        self.current_key = "home"
        self.current_tool_widget = None
        self.current_tool_module = None

        self._apply_responsive_geometry()
        self.overrideredirect(True)
        self.protocol("WM_DELETE_WINDOW", self.hide_main)

        self._build_shell()
        self.reload_tools()
        self.show_home()

        self.floating = FloatingPTM(self)
        self.bind("<Escape>", lambda _e: self.hide_main())

    # ---------- Ventana / proporción ----------
    def _apply_responsive_geometry(self):
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        # El boceto ocupa aprox. 75-80% del ancho y 68-72% del alto.
        width = min(1180, max(820, int(sw * 0.78)))
        height = min(760, max(520, int(sh * 0.70)))
        # Nunca exceder la pantalla útil visualmente.
        width = min(width, sw - 80)
        height = min(height, sh - 100)
        x = max(20, (sw - width) // 2)
        y = max(20, (sh - height) // 2 - 10)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(min(820, width), min(520, height))

    def _build_shell(self):
        # Marco exterior simple y limpio.
        self.outer = tk.Frame(self, bg=WHITE, bd=1, relief="solid")
        self.outer.pack(fill="both", expand=True)

        self.top = tk.Frame(self.outer, bg=WHITE, height=42)
        self.top.pack(fill="x", padx=8, pady=(7, 0))
        self.top.pack_propagate(False)

        self.tabs_holder = tk.Frame(self.top, bg=WHITE)
        self.tabs_holder.pack(side="left", fill="both", expand=True)

        self.close_canvas = tk.Canvas(self.top, width=38, height=38, bg=WHITE,
                                      highlightthickness=0, bd=0, cursor="hand2")
        self.close_canvas.pack(side="right", padx=(8, 2))
        self.close_canvas.create_oval(3, 3, 35, 35, outline=BLACK, width=1.5)
        self.close_canvas.create_line(13, 13, 25, 25, fill=BLACK, width=1.5)
        self.close_canvas.create_line(25, 13, 13, 25, fill=BLACK, width=1.5)
        self.close_canvas.bind("<Button-1>", lambda _e: self.hide_main())

        self.separator = tk.Frame(self.outer, bg=WHITE, height=2)
        self.separator.pack(fill="x")

        self.content = tk.Frame(self.outer, bg=WHITE)
        self.content.pack(fill="both", expand=True, padx=10, pady=(2, 10))

        # Permitir mover la ventana arrastrando zonas libres de la franja superior.
        self.top.bind("<Button-1>", self._start_move)
        self.top.bind("<B1-Motion>", self._move_window)
        self.tabs_holder.bind("<Button-1>", self._start_move)
        self.tabs_holder.bind("<B1-Motion>", self._move_window)

    def _start_move(self, event):
        self._move_offset = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def _move_window(self, event):
        x = event.x_root - self._move_offset[0]
        y = event.y_root - self._move_offset[1]
        self.geometry(f"+{x}+{y}")

    # ---------- Pestañas ----------
    def _render_tabs(self):
        for child in self.tabs_holder.winfo_children():
            child.destroy()
        self.tab_widgets.clear()

        keys = ["home"] + list(self.open_tabs.keys())
        available = max(520, self.winfo_width() - 70)
        tab_width = max(90, min(130, available // max(1, len(keys))))

        home = TabButton(
            self.tabs_holder,
            "PTM",
            on_open=self.show_home,
            active=(self.current_key == "home"),
            width=tab_width,
        )
        home.pack(side="left", padx=(0, 6))
        self.tab_widgets["home"] = home

        for key in self.open_tabs:
            meta = self.open_tabs[key]
            tab = TabButton(
                self.tabs_holder,
                meta["name"],
                on_open=lambda k=key: self.switch_to_tool(k),
                on_close=lambda k=key: self.close_tool_tab(k),
                active=(self.current_key == key),
                width=tab_width,
            )
            tab.pack(side="left", padx=(0, 6))
            self.tab_widgets[key] = tab

    def _clear_content(self):
        if self.current_tool_widget is not None:
            try:
                if hasattr(self.current_tool_widget, "on_hide"):
                    self.current_tool_widget.on_hide()
            except Exception:
                pass
        for child in self.content.winfo_children():
            child.pack_forget()
            child.grid_forget()

    # ---------- Inicio ----------
    def show_home(self):
        self.current_key = "home"
        self.current_tool_widget = None
        self.current_tool_module = None
        self._clear_content()

        if not hasattr(self, "home_frame") or not self.home_frame.winfo_exists():
            self.home_frame = tk.Frame(self.content, bg=WHITE)
            self._build_home(self.home_frame)
        self.home_frame.pack(fill="both", expand=True)
        self._render_tabs()
        self.after(40, lambda: self.search_entry.focus_set())

    def _build_home(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_rowconfigure(3, weight=1)

        center = tk.Frame(parent, bg=WHITE)
        center.grid(row=1, column=0, sticky="n", pady=(55, 0))

        # Logo PTM dibujado, sin imagen externa.
        logo_w, logo_h = 230, 104
        logo = tk.Canvas(center, width=logo_w, height=logo_h, bg=WHITE,
                         highlightthickness=0, bd=0)
        logo.pack()
        logo.create_rectangle(2, 2, logo_w - 2, logo_h - 2, fill=TEAL, outline=BLACK, width=1)
        logo.create_polygon(logo_w - 30, 2, logo_w - 2, 2, logo_w - 2, 30, fill=RED, outline=RED)
        logo.create_rectangle(2, logo_h - 20, logo_w - 2, logo_h - 2, fill=RED, outline=RED)
        logo.create_text(logo_w / 2, 46, text="PTM", fill=WHITE, font=("Segoe UI", 38, "bold"))
        logo.create_text(logo_w / 2, logo_h - 10, text="Buscador y lanzador de herramientas",
                         fill=WHITE, font=("Segoe UI", 8, "bold"))

        search_wrap = tk.Frame(center, bg=WHITE)
        search_wrap.pack(pady=(16, 0))

        # Marco de búsqueda parecido al boceto.
        self.search_box = tk.Frame(search_wrap, bg=WHITE, highlightbackground=BLACK,
                                   highlightthickness=1, bd=0)
        self.search_box.pack()

        self.search_entry = tk.Entry(
            self.search_box,
            textvariable=self.query,
            width=43,
            relief="flat",
            bd=0,
            font=("Segoe UI", 12),
            fg=BLACK,
            bg=WHITE,
            insertbackground=BLACK,
        )
        self.search_entry.pack(side="left", padx=(10, 5), pady=7)
        self.search_entry.bind("<KeyRelease>", lambda _e: self.refresh_results())
        self.search_entry.bind("<Return>", lambda _e: self.open_first_result())

        self.search_btn = tk.Canvas(self.search_box, width=28, height=28, bg=WHITE,
                                    highlightthickness=0, bd=0, cursor="hand2")
        self.search_btn.pack(side="left", padx=(2, 0))
        self.search_btn.create_oval(5, 5, 24, 24, fill=RED, outline=BLACK, width=1)
        self.search_btn.bind("<Button-1>", lambda _e: self.open_first_result())

        self.import_btn = tk.Canvas(self.search_box, width=31, height=28, bg=WHITE,
                                    highlightthickness=0, bd=0, cursor="hand2")
        self.import_btn.pack(side="left", padx=(0, 5))
        self._draw_import_icon(self.import_btn)
        self.import_btn.bind("<Button-1>", lambda _e: self.import_py())

        self.results_frame = tk.Frame(center, bg=WHITE)
        self.results_frame.pack(fill="x", pady=(8, 0))

        self.hint = tk.Label(center, text="", bg=WHITE, fg=MUTED, font=("Segoe UI", 9))
        self.hint.pack(pady=(5, 0))

    @staticmethod
    def _draw_import_icon(canvas):
        canvas.create_line(15, 4, 15, 18, fill=BLACK, width=2)
        canvas.create_line(10, 9, 15, 4, 20, 9, fill=BLACK, width=2)
        canvas.create_line(7, 16, 7, 23, 24, 23, 24, 16, fill=BLACK, width=2)

    # ---------- Herramientas ----------
    def reload_tools(self):
        self.tools = []
        for path in sorted(self.tools_dir.rglob("*.py")):
            if path.name == "__init__.py" or path.name.startswith("_"):
                continue
            self.tools.append(self.read_tool_info(path))
        if hasattr(self, "results_frame") and self.results_frame.winfo_exists():
            self.refresh_results()

    def read_tool_info(self, path):
        keywords = ""
        name = path.stem.replace("_", " ").title()
        description = "Herramienta Python"
        try:
            with path.open("r", encoding="utf-8-sig") as f:
                first_line = f.readline().strip()
                source = first_line + "\n" + f.read()
            if first_line.upper().startswith("# ARGUMENTOS:"):
                keywords = first_line.split(":", 1)[1].strip()
            tree = ast.parse(source, filename=str(path))
            for node in tree.body:
                if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                    key = node.targets[0].id
                    if key in {"TOOL_NAME", "TOOL_DESCRIPTION"}:
                        try:
                            value = ast.literal_eval(node.value)
                        except Exception:
                            continue
                        if key == "TOOL_NAME" and isinstance(value, str):
                            name = value
                        elif key == "TOOL_DESCRIPTION" and isinstance(value, str):
                            description = value
        except Exception as exc:
            description = f"No se pudo leer: {exc}"
        return {
            "path": path,
            "name": name,
            "keywords": keywords,
            "description": description,
            "search": f"{path.stem} {name} {keywords} {description}".lower(),
        }

    def filtered_tools(self):
        q = self.query.get().strip().lower()
        if not q:
            return []
        tokens = [t for t in q.replace(",", " ").split() if t]
        return [tool for tool in self.tools if all(t in tool["search"] for t in tokens)]

    def refresh_results(self):
        if not hasattr(self, "results_frame"):
            return
        for child in self.results_frame.winfo_children():
            child.destroy()
        shown = self.filtered_tools()[:8]
        if not self.query.get().strip():
            self.hint.configure(text=f"{len(self.tools)} herramienta(s) disponibles")
            return
        if not shown:
            self.hint.configure(text="Sin coincidencias")
            return
        self.hint.configure(text=f"{len(self.filtered_tools())} coincidencia(s)")
        for tool in shown:
            row = tk.Frame(self.results_frame, bg=LIGHT, highlightbackground=MID, highlightthickness=1)
            row.pack(fill="x", pady=2)
            label = tk.Label(row, text=tool["name"], bg=LIGHT, fg=BLACK,
                             font=("Segoe UI", 10, "bold"), anchor="w")
            label.pack(side="left", fill="x", expand=True, padx=8, pady=5)
            meta = tk.Label(row, text=tool["path"].name, bg=LIGHT, fg=MUTED,
                            font=("Segoe UI", 8), anchor="e")
            meta.pack(side="right", padx=8)
            for widget in (row, label, meta):
                widget.bind("<Double-Button-1>", lambda _e, t=tool: self.open_tool(t))
                widget.bind("<Button-1>", lambda _e, t=tool: self.open_tool(t))

    def open_first_result(self):
        shown = self.filtered_tools()
        if shown:
            self.open_tool(shown[0])
        elif self.query.get().strip():
            messagebox.showinfo("PTM", "No se encontró ninguna herramienta con ese criterio.")

    def import_py(self):
        files = filedialog.askopenfilenames(
            title="Agregar herramientas Python",
            filetypes=[("Archivos Python", "*.py")],
        )
        if not files:
            return
        copied = 0
        for filename in files:
            src = Path(filename)
            dst = self.tools_dir / src.name
            if dst.exists():
                if not messagebox.askyesno("Reemplazar", f"{src.name} ya existe. ¿Deseas reemplazarlo?"):
                    continue
            try:
                shutil.copy2(src, dst)
                copied += 1
            except OSError as exc:
                messagebox.showerror("PTM", f"No se pudo agregar {src.name}:\n{exc}")
        self.reload_tools()
        if copied:
            self.hint.configure(text=f"{copied} herramienta(s) agregada(s)")

    def open_tool(self, tool):
        key = str(tool["path"].resolve())
        if key in self.open_tabs:
            self.switch_to_tool(key)
            return

        try:
            module_name = f"ptm_tool_{tool['path'].stem}_{abs(hash(key))}"
            spec = importlib.util.spec_from_file_location(module_name, tool["path"])
            if spec is None or spec.loader is None:
                raise RuntimeError("No se pudo preparar el módulo.")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as exc:
            messagebox.showerror("PTM", f"No se pudo cargar {tool['path'].name}:\n\n{exc}")
            return

        factory = getattr(module, "create_tool", None)
        frame = tk.Frame(self.content, bg=WHITE)
        if callable(factory):
            try:
                widget = factory(frame, self)
                widget.pack(fill="both", expand=True)
            except Exception as exc:
                frame.destroy()
                messagebox.showerror("PTM", f"Error al abrir {tool['name']}:\n\n{exc}")
                return
        else:
            # Herramientas antiguas siguen siendo utilizables, aunque no puedan integrarse.
            info = tk.Frame(frame, bg=WHITE)
            info.pack(expand=True)
            tk.Label(info, text=tool["name"], bg=WHITE, fg=BLACK,
                     font=("Segoe UI", 20, "bold")).pack(pady=(0, 10))
            tk.Label(info, text="Este archivo no contiene create_tool(parent, app).",
                     bg=WHITE, fg=MUTED, font=("Segoe UI", 10)).pack(pady=5)
            tk.Button(info, text="Ejecutar como programa externo",
                      command=lambda p=tool["path"]: self.run_external(p),
                      bg=TEAL, fg=WHITE, activebackground=TEAL_DARK,
                      relief="flat", padx=16, pady=8).pack(pady=10)

        self.open_tabs[key] = {
            "name": tool["name"],
            "tool": tool,
            "frame": frame,
            "module": module,
        }
        self.switch_to_tool(key)

    def switch_to_tool(self, key):
        if key not in self.open_tabs:
            return
        self.current_key = key
        self._clear_content()
        if hasattr(self, "home_frame") and self.home_frame.winfo_exists():
            self.home_frame.pack_forget()
        meta = self.open_tabs[key]
        meta["frame"].pack(fill="both", expand=True)
        self.current_tool_module = meta["module"]
        # Si la herramienta expuso un único widget hijo, lo usamos para callbacks opcionales.
        children = meta["frame"].winfo_children()
        self.current_tool_widget = children[0] if len(children) == 1 else meta["frame"]
        try:
            if hasattr(self.current_tool_widget, "on_show"):
                self.current_tool_widget.on_show()
        except Exception:
            pass
        self._render_tabs()

    def close_tool_tab(self, key):
        meta = self.open_tabs.get(key)
        if not meta:
            return
        frame = meta["frame"]
        try:
            for child in frame.winfo_children():
                if hasattr(child, "on_close"):
                    child.on_close()
        except Exception:
            pass
        frame.destroy()
        del self.open_tabs[key]
        if self.current_key == key:
            self.show_home()
        else:
            self._render_tabs()

    def run_external(self, path):
        try:
            subprocess.Popen([sys.executable, str(path)], cwd=str(path.parent))
        except OSError as exc:
            messagebox.showerror("PTM", str(exc))

    # ---------- Sistema ----------
    def open_tools_folder(self):
        try:
            if os.name == "nt":
                os.startfile(str(self.tools_dir))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(self.tools_dir)])
            else:
                subprocess.Popen(["xdg-open", str(self.tools_dir)])
        except OSError as exc:
            messagebox.showerror("PTM", str(exc))

    def hide_main(self):
        self.withdraw()

    def show_main(self):
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.after(120, lambda: self.attributes("-topmost", False))

    def toggle_main(self):
        if self.state() == "withdrawn" or not self.winfo_viewable():
            self.show_main()
        else:
            self.hide_main()

    def exit_app(self):
        try:
            self.floating.destroy()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    PTMApp().mainloop()