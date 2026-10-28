# ARGUMENTOS: pyrion console consola linux procesos python py kill matar cerrar teclado digital virtual caracteres terminal red ssl github logs pestañas shell
import os
import signal
import subprocess
import tkinter as tk
from pathlib import Path

TOOL_NAME = "PYRION CONSOLE"
TOOL_DESCRIPTION = (
    "Consola PYRION por pestañas con Shell por defecto, KILL PY, Red, SSL, "
    "GitHub, Logs y teclado digital."
)
TOOL_VERSION = "1.9.0"

BG = "#05090C"
PANEL = "#0C141D"
TAB = "#151C25"
TAB_ACTIVE = "#263544"
FG = "#D7DCE2"
MUTED = "#98A2AD"
GREEN = "#42D392"
RED = "#FF4D57"
ACCENT = "#7EB7FF"


def _shorten(text, limit=150):
    text = str(text or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def list_python_processes():
    rows = []

    if os.name != "nt":
        proc = Path("/proc")
        if proc.is_dir():
            for item in proc.iterdir():
                if not item.name.isdigit():
                    continue

                pid = int(item.name)
                try:
                    raw = (item / "cmdline").read_bytes()
                    cmd = raw.replace(b"\x00", b" ").decode(
                        "utf-8", errors="replace"
                    ).strip()
                except OSError:
                    continue

                if not cmd:
                    continue

                low = cmd.lower()
                exe = Path(low.split(" ", 1)[0]).name
                if "python" in exe or ".py" in low:
                    rows.append((pid, cmd))

            return sorted(rows)

        try:
            result = subprocess.run(
                ["ps", "-eo", "pid=,args="],
                capture_output=True,
                text=True,
                check=False,
            )
            for line in result.stdout.splitlines():
                parts = line.strip().split(None, 1)
                if len(parts) != 2:
                    continue
                try:
                    pid = int(parts[0])
                except ValueError:
                    continue
                if "python" in parts[1].lower() or ".py" in parts[1].lower():
                    rows.append((pid, parts[1]))
        except OSError:
            pass

        return sorted(rows)

    script = (
        "Get-CimInstance Win32_Process | "
        "Where-Object {$_.Name -match '^python(w)?(.exe)?$' -or "
        "$_.CommandLine -match '\\.py'} | "
        "ForEach-Object {'{0}|{1}' -f $_.ProcessId,$_.CommandLine}"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for line in result.stdout.splitlines():
            if "|" not in line:
                continue
            pid_text, cmd = line.split("|", 1)
            try:
                rows.append((int(pid_text.strip()), cmd.strip()))
            except ValueError:
                pass
    except OSError:
        pass

    return sorted(rows)


class PyrionConsoleTool(tk.Frame):
    TAB_ORDER = ("Shell", "Killpy", "Consultas", "Red", "SSL", "GitHub", "Logs")

    def __init__(self, parent, app=None):
        super().__init__(parent, bg=BG)
        self.app = app

        self.open_tabs = []
        self.active_tab = None
        self.histories = {}
        self.tab_types = {}
        self.tab_labels = {}
        self.tab_counters = {}
        self.processes = []
        self.query_commands = [
            ("pwd", "Directorio actual"),
            ("whoami", "Usuario actual"),
            ("id", "Identidad y grupos"),
            ("uname -a", "Kernel y arquitectura"),
            ("date", "Fecha y hora"),
            ("uptime", "Tiempo encendido y carga"),
            ("df -h", "Uso de discos"),
            ("free -h", "Uso de memoria"),
            ("ps", "Procesos"),
            ("ip addr", "Direcciones de red"),
            ("ip route", "Rutas de red"),
            ("hostname", "Nombre del equipo"),
            ("mount", "Sistemas montados"),
            ("cat /proc/cpuinfo", "Informacion de CPU"),
            ("cat /proc/meminfo", "Informacion detallada de memoria"),
            ("cat /proc/asound/cards", "Tarjetas de sonido detectadas por ALSA"),
            ("aplay -l", "Dispositivos de reproduccion de audio"),
            ("arecord -l", "Dispositivos de grabacion de audio"),
            ("amixer scontrols", "Controles de sonido disponibles"),
            ("amixer", "Estado y niveles actuales del mezclador"),
        ]

        self.keyboard_window = None
        self.keyboard_mode = "lower"
        self.keyboard_drag_x = 0
        self.keyboard_drag_y = 0

        self._build_ui()

        # Solo Consola existe al iniciar. Los accesos superiores crean las demas.
        self.open_tabs.append("Consola")
        self.tab_types["Consola"] = "Consola"
        self.tab_labels["Consola"] = "Consola"
        self.histories["Consola"] = (
            "PYRION - consola grafica\n"
            "Shell persistente: /bin/sh\n"
            "Atajo global: Ctrl + Alt + T\n"
            "Abre nuevas pestañas desde la barra superior.\n"
            "------------------------------------------------------------\n"
        )
        self._add_side_tab("Consola", "Consola")
        self.activate_tab("Consola")

    def _build_ui(self):
        # Barra de accesos: no son pestañas abiertas, son creadores/activadores.
        top = tk.Frame(self, bg=TAB, height=32)
        top.pack(fill="x", padx=2, pady=(2, 0))
        top.pack_propagate(False)

        tk.Label(
            top,
            text="PYRION Console",
            bg=TAB,
            fg=FG,
            font=("DejaVu Sans", 10, "bold"),
            padx=12,
        ).pack(side="left", fill="y")

        self.launch_buttons = {}
        for name in self.TAB_ORDER:
            button = tk.Button(
                top,
                text=name,
                command=lambda n=name: self.open_tab(n),
                bg=TAB,
                fg=MUTED,
                activebackground=TAB_ACTIVE,
                activeforeground=FG,
                bd=1,
                relief="solid",
                highlightthickness=0,
                padx=10,
                font=("DejaVu Sans", 9),
            )
            button.pack(side="left", fill="y")
            self.launch_buttons[name] = button

        tk.Button(
            top,
            text="Limpiar",
            command=self.clear_active,
            bg=TAB,
            fg=MUTED,
            activebackground=TAB_ACTIVE,
            activeforeground=FG,
            bd=1,
            relief="solid",
            highlightthickness=0,
            padx=12,
            font=("DejaVu Sans", 9),
        ).pack(side="right", fill="y")

        workspace = tk.Frame(self, bg=BG)
        workspace.pack(fill="both", expand=True, padx=2)

        # Organizador izquierdo: muestra solo las pestañas YA abiertas.
        self.sidebar = tk.Frame(
            workspace,
            bg=TAB,
            width=150,
            bd=1,
            relief="solid",
        )
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        tk.Label(
            self.sidebar,
            text="ABIERTAS",
            bg=TAB,
            fg=MUTED,
            font=("DejaVu Sans", 8, "bold"),
            anchor="w",
            padx=10,
            pady=8,
        ).pack(fill="x")

        self.side_list = tk.Frame(self.sidebar, bg=TAB)
        self.side_list.pack(fill="both", expand=True)
        self.side_buttons = {}

        # Área tipo chat: historial arriba, escritura abajo.
        main = tk.Frame(workspace, bg=BG, bd=1, relief="solid")
        main.pack(side="left", fill="both", expand=True)

        output_wrap = tk.Frame(main, bg=BG)
        output_wrap.pack(fill="both", expand=True)

        self.output = tk.Text(
            output_wrap,
            bg=BG,
            fg=FG,
            insertbackground=FG,
            selectbackground="#29435B",
            selectforeground=FG,
            font=("DejaVu Sans Mono", 9),
            bd=0,
            highlightthickness=0,
            wrap="word",
            padx=10,
            pady=9,
        )
        scroll = tk.Scrollbar(output_wrap, command=self.output.yview)
        self.output.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.output.pack(side="left", fill="both", expand=True)
        self.output.configure(state="disabled")

        # Campo de escritura justo debajo del historial.
        self.input_bar = tk.Frame(main, bg=PANEL, height=43)
        self.input_bar.pack(fill="x")
        self.input_bar.pack_propagate(False)

        self.prompt_label = tk.Label(
            self.input_bar,
            text="root@mini1:#",
            bg=PANEL,
            fg=GREEN,
            font=("DejaVu Sans Mono", 10, "bold"),
        )
        self.prompt_label.pack(side="left", padx=(9, 5))

        self.command = tk.Entry(
            self.input_bar,
            bg=PANEL,
            fg=FG,
            insertbackground=FG,
            font=("DejaVu Sans Mono", 10),
            bd=0,
            highlightthickness=0,
        )
        self.command.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(0, 7),
            pady=7,
        )
        self.command.bind("<Return>", self.execute_input)

        tk.Button(
            self.input_bar,
            text="⌨",
            command=self.toggle_keyboard,
            bg=PANEL,
            fg=ACCENT,
            activebackground=TAB_ACTIVE,
            activeforeground=FG,
            bd=0,
            padx=8,
            font=("DejaVu Sans", 12),
        ).pack(side="right", fill="y")


    # ---------- pestañas ----------
    def open_tab(self, tab_type):
        if tab_type not in self.TAB_ORDER:
            return

        number = self.tab_counters.get(tab_type, 0) + 1
        self.tab_counters[tab_type] = number

        tab_id = f"{tab_type}::{number}"
        label = f"{tab_type} {number}"

        self.open_tabs.append(tab_id)
        self.tab_types[tab_id] = tab_type
        self.tab_labels[tab_id] = label
        self.histories[tab_id] = ""

        self._add_side_tab(tab_id, label)
        self._initialize_tab(tab_id, tab_type)
        self.activate_tab(tab_id)

    def _add_side_tab(self, tab_id, label):
        row = tk.Frame(self.side_list, bg=TAB)
        row.pack(fill="x")

        close_button = tk.Button(
            row,
            text="×",
            command=lambda t=tab_id: self.close_tab(t),
            bg=TAB,
            fg=RED,
            activebackground=TAB_ACTIVE,
            activeforeground="#FFFFFF",
            bd=0,
            relief="flat",
            width=2,
            padx=0,
            pady=7,
            font=("DejaVu Sans", 10, "bold"),
        )
        close_button.pack(side="left", fill="y", padx=(4, 0))

        button = tk.Button(
            row,
            text=label,
            command=lambda t=tab_id: self.activate_tab(t),
            bg=TAB,
            fg=MUTED,
            activebackground=TAB_ACTIVE,
            activeforeground=FG,
            bd=0,
            relief="flat",
            highlightthickness=0,
            anchor="w",
            padx=3,
            pady=7,
            font=("DejaVu Sans", 9),
        )
        button.pack(side="left", fill="x", expand=True)

        self.side_buttons[tab_id] = (row, button, close_button)

    def close_tab(self, tab_id):
        if tab_id not in self.open_tabs:
            return

        was_active = self.active_tab == tab_id
        self.open_tabs.remove(tab_id)
        self.histories.pop(tab_id, None)
        self.tab_types.pop(tab_id, None)
        self.tab_labels.pop(tab_id, None)

        row, _button, _close = self.side_buttons.pop(tab_id)
        row.destroy()

        if was_active:
            if self.open_tabs:
                self.activate_tab(self.open_tabs[-1])
            else:
                self.active_tab = None
                self.output.configure(state="normal")
                self.output.delete("1.0", "end")
                self.output.configure(state="disabled")
                self.prompt_label.configure(text="root@mini1:#")
                self.command.delete(0, "end")

    def activate_tab(self, tab_id):
        if tab_id not in self.open_tabs:
            return

        self.active_tab = tab_id
        tab_type = self.tab_types.get(tab_id, "Consola")

        for current_id, (_row, button, close_button) in self.side_buttons.items():
            selected = current_id == tab_id
            button.configure(
                bg=TAB_ACTIVE if selected else TAB,
                fg=FG if selected else MUTED,
            )
            close_button.configure(
                bg=TAB_ACTIVE if selected else TAB,
                fg=RED,
            )

        self._render_history()
        self._configure_prompt()
        self.command.delete(0, "end")
        self.command.focus_set()

        if tab_type == "Killpy":
            self.refresh_kill_py(tab_id)
        elif tab_type == "Consultas":
            self.refresh_queries(tab_id)
        elif tab_type == "Red":
            self.refresh_red(tab_id)
        elif tab_type == "SSL":
            self.refresh_ssl(tab_id)
        elif tab_type == "GitHub":
            self.refresh_github(tab_id)
        elif tab_type == "Logs":
            self.refresh_logs(tab_id)

    def _initialize_tab(self, tab_id, tab_type):
        if tab_type == "Shell":
            self.histories[tab_id] = (
                "Shell /bin/sh\n"
                "------------------------------------------------------------\n"
            )

    def _configure_prompt(self):
        tab_type = self.tab_types.get(self.active_tab, "Consola")
        if tab_type == "Killpy":
            self.prompt_label.configure(text="killpy:#")
        elif tab_type == "Consultas":
            self.prompt_label.configure(text="consulta:#")
        else:
            self.prompt_label.configure(text="root@mini1:#")

    # ---------- historial ----------
    def _render_history(self):
        text = self.histories.get(self.active_tab, "")
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.output.see("end")
        self.output.configure(state="disabled")

    def _append(self, text="", tab=None):
        tab = tab or self.active_tab
        if tab not in self.histories:
            return

        if text and not text.endswith("\n"):
            text += "\n"

        self.histories[tab] += text

        if tab == self.active_tab:
            self._render_history()

    def _replace(self, text="", tab=None):
        tab = tab or self.active_tab
        if tab not in self.histories:
            return

        if text and not text.endswith("\n"):
            text += "\n"

        self.histories[tab] = text

        if tab == self.active_tab:
            self._render_history()

    def clear_active(self):
        if self.active_tab:
            self.histories[self.active_tab] = ""
            self._render_history()

    # ---------- KILL PY ----------
    def refresh_kill_py(self, tab_id=None):
        self.processes = list_python_processes()
        current = os.getpid()

        lines = [
            "KILL PY",
            "Procesos Python detectados:",
            "",
        ]

        if not self.processes:
            lines.append("No se encontraron procesos Python.")
        else:
            for index, (pid, cmd) in enumerate(self.processes, start=1):
                mark = " [PYRION CONSOLE]" if pid == current else ""
                lines.append(
                    f"{index}. PID {pid}  {_shorten(cmd)}{mark}"
                )

        lines.extend([
            "",
            "Escribe SOLO el numero del proceso abajo y pulsa Enter.",
        ])

        self._replace("\n".join(lines), tab_id or self.active_tab)

    def _kill_number(self, raw, tab_id=None):
        try:
            number = int(raw.strip())
        except ValueError:
            self._append("Killpy: escribe un numero valido.", tab_id or self.active_tab)
            return

        if number < 1 or number > len(self.processes):
            self._append(
                "Killpy: ese numero no existe en la lista.",
                tab_id or self.active_tab,
            )
            return

        pid, cmd = self.processes[number - 1]

        if pid == os.getpid():
            self._append(
                "Killpy: PYRION CONSOLE esta protegida.",
                tab_id or self.active_tab,
            )
            return

        try:
            if os.name == "nt":
                result = subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    check=False,
                    creationflags=getattr(
                        subprocess,
                        "CREATE_NO_WINDOW",
                        0,
                    ),
                )
                if result.returncode != 0:
                    raise OSError(
                        (result.stderr or result.stdout).strip()
                    )
            else:
                os.kill(pid, signal.SIGTERM)

            self._append(
                f"Cerrando #{number} · PID {pid} · {_shorten(cmd, 100)}",
                tab_id or self.active_tab,
            )
            target_tab = tab_id or self.active_tab
            self.after(400, lambda t=target_tab: self.refresh_kill_py(t))

        except OSError as exc:
            self._append(
                f"ERROR al cerrar PID {pid}: {exc}",
                tab_id or self.active_tab,
            )

    # ---------- CONSULTAS ----------
    def refresh_queries(self, tab_id=None):
        lines = [
            "CONSULTAS",
            "Comandos populares de solo lectura:",
            "",
        ]
        for index, (command, description) in enumerate(self.query_commands, start=1):
            lines.append(f"{index}. {command}  -  {description}")

        lines.extend([
            "",
            "Escribe SOLO el numero del comando abajo y pulsa Enter.",
            "Esta pestaña solo ejecuta comandos de consulta predefinidos.",
        ])

        self._replace("\n".join(lines), tab_id or self.active_tab)

    def _run_query_number(self, raw, tab_id=None):
        target = tab_id or self.active_tab
        try:
            number = int(raw.strip())
        except ValueError:
            self._append("Consultas: escribe un numero valido.", target)
            return

        if number < 1 or number > len(self.query_commands):
            self._append("Consultas: ese numero no existe en la lista.", target)
            return

        command, description = self.query_commands[number - 1]
        self._append(f"consulta:# {number} -> {command}  [{description}]", target)

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=20,
                executable=None if os.name == "nt" else "/bin/sh",
            )
            output = (result.stdout or "") + (result.stderr or "")
            if output:
                self._append(output.rstrip(), target)
            if result.returncode:
                self._append(f"[exit {result.returncode}]", target)
        except subprocess.TimeoutExpired:
            self._append("[timeout]", target)
        except Exception as exc:
            self._append(f"[error] {exc}", target)

    # ---------- diagnósticos ----------
    def refresh_red(self, tab_id=None):
        lines = ["RED - diagnostico", ""]
        for cmd in (["ip", "addr"], ["ip", "route"]):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=4,
                )
                lines.append(
                    f"$ {' '.join(cmd)}\n"
                    f"{result.stdout or result.stderr}"
                )
            except Exception as exc:
                lines.append(f"$ {' '.join(cmd)}\n{exc}")
        self._replace("\n".join(lines), tab_id or self.active_tab)

    def refresh_ssl(self, tab_id=None):
        lines = ["SSL - diagnostico", ""]
        commands = (
            ["openssl", "version"],
            [
                "python3",
                "-c",
                "import ssl; print(ssl.OPENSSL_VERSION)",
            ],
        )
        for cmd in commands:
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                lines.append(
                    f"$ {' '.join(cmd)}\n"
                    f"{result.stdout or result.stderr}"
                )
            except Exception as exc:
                lines.append(str(exc))
        self._replace("\n".join(lines), tab_id or self.active_tab)

    def refresh_github(self, tab_id=None):
        lines = ["GitHub - conectividad", ""]
        try:
            result = subprocess.run(
                [
                    "python3",
                    "-c",
                    (
                        "import urllib.request; "
                        "r=urllib.request.urlopen("
                        "'https://github.com',timeout=5); "
                        "print('HTTP',r.status)"
                    ),
                ],
                capture_output=True,
                text=True,
                timeout=7,
            )
            lines.append(result.stdout or result.stderr)
        except Exception as exc:
            lines.append(str(exc))
        self._replace("\n".join(lines), tab_id or self.active_tab)

    def refresh_logs(self, tab_id=None):
        lines = ["Logs recientes", ""]
        candidates = (
            "/var/log/messages",
            "/var/log/syslog",
            "/tmp/pyrion.log",
        )
        found = False

        for path in candidates:
            file_path = Path(path)
            if not file_path.is_file():
                continue

            found = True
            try:
                recent = file_path.read_text(
                    errors="replace"
                ).splitlines()[-60:]
                lines.append(
                    f"--- {path} ---\n" + "\n".join(recent)
                )
            except OSError as exc:
                lines.append(f"{path}: {exc}")

        if not found:
            lines.append("No se encontraron logs conocidos.")

        self._replace("\n".join(lines), tab_id or self.active_tab)

    # ---------- entrada tipo chat ----------
    def execute_input(self, _event=None):
        text = self.command.get().strip()
        self.command.delete(0, "end")

        if not text or not self.active_tab:
            return

        active_type = self.tab_types.get(self.active_tab, "Consola")

        if active_type == "Killpy":
            self._append(f"killpy:# {text}", self.active_tab)
            self._kill_number(text, self.active_tab)
            return

        if active_type == "Consultas":
            self._run_query_number(text, self.active_tab)
            return

        # Todas las demás pestañas aceptan comandos shell sin cambiar de pestaña.
        self._append(
            f"root@mini1:# {text}",
            self.active_tab,
        )

        try:
            result = subprocess.run(
                text,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                executable=None if os.name == "nt" else "/bin/sh",
            )
            output = (result.stdout or "") + (result.stderr or "")

            if output:
                self._append(output.rstrip(), self.active_tab)

            if result.returncode:
                self._append(
                    f"[exit {result.returncode}]",
                    self.active_tab,
                )

        except subprocess.TimeoutExpired:
            self._append("[timeout]", self.active_tab)
        except Exception as exc:
            self._append(f"[error] {exc}", self.active_tab)

    # ---------- teclado flotante ----------
    def toggle_keyboard(self):
        if self.keyboard_window is not None:
            try:
                if self.keyboard_window.winfo_exists():
                    self.close_keyboard()
                    return
            except tk.TclError:
                pass

        self.open_keyboard()

    def open_keyboard(self):
        if self.keyboard_window is not None:
            try:
                if self.keyboard_window.winfo_exists():
                    self.keyboard_window.lift()
                    return
            except tk.TclError:
                pass

        win = tk.Toplevel(self)
        self.keyboard_window = win

        try:
            win.overrideredirect(True)
        except tk.TclError:
            pass

        try:
            win.attributes("-topmost", True)
        except tk.TclError:
            pass

        win.configure(bg=TAB)

        width = 560
        height = 255
        try:
            self.update_idletasks()
            x = self.winfo_rootx() + max(20, (self.winfo_width() - width) // 2)
            y = self.winfo_rooty() + max(40, self.winfo_height() - height - 55)
        except tk.TclError:
            x, y = 120, 120

        win.geometry(f"{width}x{height}+{x}+{y}")

        titlebar = tk.Frame(win, bg=TAB_ACTIVE, height=34)
        titlebar.pack(fill="x")
        titlebar.pack_propagate(False)

        title = tk.Label(
            titlebar,
            text="PYRION Keyboard",
            bg=TAB_ACTIVE,
            fg=FG,
            font=("DejaVu Sans", 9, "bold"),
            padx=10,
        )
        title.pack(side="left", fill="y")

        tk.Button(
            titlebar,
            text="×",
            command=self.close_keyboard,
            bg=TAB_ACTIVE,
            fg=RED,
            activebackground=RED,
            activeforeground="#FFFFFF",
            bd=0,
            relief="flat",
            width=4,
            font=("DejaVu Sans", 12, "bold"),
        ).pack(side="right", fill="y")

        for widget in (titlebar, title):
            widget.bind("<Button-1>", self._keyboard_drag_start)
            widget.bind("<B1-Motion>", self._keyboard_drag_move)

        modes = tk.Frame(win, bg=PANEL, height=36)
        modes.pack(fill="x")
        modes.pack_propagate(False)

        self.keyboard_mode_buttons = {}
        for mode, label in (
            ("numbers", "123"),
            ("upper", "ABC"),
            ("lower", "abc"),
            ("symbols", "#+="),
        ):
            button = tk.Button(
                modes,
                text=label,
                command=lambda m=mode: self.set_keyboard_mode(m),
                bg=TAB,
                fg=MUTED,
                activebackground=TAB_ACTIVE,
                activeforeground=FG,
                bd=1,
                relief="solid",
                padx=14,
                font=("DejaVu Sans", 9, "bold"),
            )
            button.pack(side="left", fill="y", padx=(4, 0), pady=3)
            self.keyboard_mode_buttons[mode] = button

        self.keyboard_rows = tk.Frame(win, bg=PANEL)
        self.keyboard_rows.pack(fill="both", expand=True, padx=5, pady=(2, 5))

        self._draw_keyboard()
        self.command.focus_set()

    def close_keyboard(self):
        if self.keyboard_window is not None:
            try:
                self.keyboard_window.destroy()
            except tk.TclError:
                pass
        self.keyboard_window = None
        self.command.focus_set()

    def _keyboard_drag_start(self, event):
        self.keyboard_drag_x = event.x_root
        self.keyboard_drag_y = event.y_root

    def _keyboard_drag_move(self, event):
        if self.keyboard_window is None:
            return
        try:
            x = self.keyboard_window.winfo_x() + (event.x_root - self.keyboard_drag_x)
            y = self.keyboard_window.winfo_y() + (event.y_root - self.keyboard_drag_y)
            self.keyboard_window.geometry(f"+{x}+{y}")
            self.keyboard_drag_x = event.x_root
            self.keyboard_drag_y = event.y_root
        except tk.TclError:
            pass

    def set_keyboard_mode(self, mode):
        if mode not in ("numbers", "upper", "lower", "symbols"):
            return
        self.keyboard_mode = mode
        self._draw_keyboard()

    def _draw_keyboard(self):
        if self.keyboard_window is None:
            return

        try:
            if not self.keyboard_window.winfo_exists():
                return
        except tk.TclError:
            return

        for child in self.keyboard_rows.winfo_children():
            child.destroy()

        for mode, button in self.keyboard_mode_buttons.items():
            selected = mode == self.keyboard_mode
            button.configure(
                bg=TAB_ACTIVE if selected else TAB,
                fg=FG if selected else MUTED,
            )

        if self.keyboard_mode == "numbers":
            rows = [
                list("1234567890"),
                ["-", "+", "=", "*", "/", "%", ".", ",", "(", ")"],
            ]
        elif self.keyboard_mode == "upper":
            rows = [
                list("QWERTYUIOP"),
                list("ASDFGHJKL"),
                list("ZXCVBNM"),
            ]
        elif self.keyboard_mode == "lower":
            rows = [
                list("qwertyuiop"),
                list("asdfghjkl"),
                list("zxcvbnm"),
            ]
        else:
            rows = [
                ["!", "@", "#", "$", "%", "^", "&", "*", "(", ")"],
                ["_", "-", "+", "=", "{", "}", "[", "]", "|", "\\"],
                [":", ";", "'", '"', "<", ">", ",", ".", "?", "/", "~", "`"],
            ]

        for row_index, chars in enumerate(rows):
            row = tk.Frame(self.keyboard_rows, bg=PANEL)
            row.pack(fill="x", expand=True, pady=1)

            spacer_left = tk.Frame(row, bg=PANEL)
            spacer_left.pack(side="left", expand=True)

            for char in chars:
                tk.Button(
                    row,
                    text=char,
                    command=lambda value=char: self._insert_key(value),
                    bg=TAB,
                    fg=FG,
                    activebackground=TAB_ACTIVE,
                    activeforeground=FG,
                    bd=1,
                    relief="solid",
                    width=4,
                    font=("DejaVu Sans Mono", 9),
                ).pack(side="left", padx=1, pady=1)

            spacer_right = tk.Frame(row, bg=PANEL)
            spacer_right.pack(side="left", expand=True)

        actions = tk.Frame(self.keyboard_rows, bg=PANEL)
        actions.pack(fill="x", pady=(4, 0))

        tk.Button(
            actions,
            text="⌫",
            command=self._backspace,
            bg=TAB,
            fg=FG,
            activebackground=TAB_ACTIVE,
            activeforeground=FG,
            bd=1,
            width=6,
            font=("DejaVu Sans", 9, "bold"),
        ).pack(side="left")

        tk.Button(
            actions,
            text="ESPACIO",
            command=lambda: self._insert_key(" "),
            bg=TAB,
            fg=FG,
            activebackground=TAB_ACTIVE,
            activeforeground=FG,
            bd=1,
            font=("DejaVu Sans", 9),
        ).pack(side="left", fill="x", expand=True, padx=4)

        tk.Button(
            actions,
            text="ENTER",
            command=self.execute_input,
            bg=TAB,
            fg=GREEN,
            activebackground=TAB_ACTIVE,
            activeforeground=FG,
            bd=1,
            width=8,
            font=("DejaVu Sans", 9, "bold"),
        ).pack(side="right")

    def _insert_key(self, value):
        self.command.insert("insert", value)
        self.command.focus_set()

    def _backspace(self):
        position = self.command.index("insert")
        if position > 0:
            self.command.delete(position - 1, position)
        self.command.focus_set()


App = PyrionConsoleTool


def main():
    root = tk.Tk()
    root.title(TOOL_NAME)
    root.geometry("1000x560")
    root.configure(bg=BG)

    tool = App(root)
    tool.pack(fill="both", expand=True)

    root.mainloop()


if __name__ == "__main__":
    main()
