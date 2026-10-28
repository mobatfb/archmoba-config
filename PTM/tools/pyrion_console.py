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
TOOL_VERSION = "1.3.0"

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
    TAB_ORDER = ("Shell", "KILL PY", "Red", "SSL", "GitHub", "Logs")

    def __init__(self, parent, app=None):
        super().__init__(parent, bg=BG)
        self.app = app

        self.open_tabs = []
        self.active_tab = None
        self.histories = {}
        self.processes = []

        self.keyboard_visible = False
        self.keyboard_upper = False

        self._build_ui()

        # Solo Shell existe al iniciar.
        self.open_tab("Shell")

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
            width=122,
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

        self.keyboard = tk.Frame(self, bg=PANEL)
        self.keyboard_rows = tk.Frame(self.keyboard, bg=PANEL)
        self.keyboard_rows.pack(fill="x", padx=4, pady=4)
        self._draw_keyboard()

    # ---------- pestañas ----------
    def open_tab(self, name):
        if name not in self.TAB_ORDER:
            return

        if name not in self.open_tabs:
            self.open_tabs.append(name)
            self.histories[name] = ""
            self._add_side_tab(name)
            self._initialize_tab(name)

        self.activate_tab(name)

    def _add_side_tab(self, name):
        row = tk.Frame(self.side_list, bg=TAB)
        row.pack(fill="x")

        button = tk.Button(
            row,
            text=name,
            command=lambda n=name: self.activate_tab(n),
            bg=TAB,
            fg=MUTED,
            activebackground=TAB_ACTIVE,
            activeforeground=FG,
            bd=0,
            relief="flat",
            highlightthickness=0,
            anchor="w",
            padx=11,
            pady=7,
            font=("DejaVu Sans", 9),
        )
        button.pack(side="left", fill="x", expand=True)

        # Shell es la base y no se puede cerrar.
        if name != "Shell":
            tk.Button(
                row,
                text="×",
                command=lambda n=name: self.close_tab(n),
                bg=TAB,
                fg=MUTED,
                activebackground=TAB_ACTIVE,
                activeforeground=RED,
                bd=0,
                relief="flat",
                width=2,
                font=("DejaVu Sans", 9, "bold"),
            ).pack(side="right", fill="y")

        self.side_buttons[name] = (row, button)

    def close_tab(self, name):
        if name == "Shell" or name not in self.open_tabs:
            return

        was_active = self.active_tab == name
        self.open_tabs.remove(name)

        row, _button = self.side_buttons.pop(name)
        row.destroy()

        if was_active:
            # Volver a la pestaña abierta inmediatamente anterior; Shell siempre existe.
            target = self.open_tabs[-1] if self.open_tabs else "Shell"
            self.activate_tab(target)

    def activate_tab(self, name):
        if name not in self.open_tabs:
            self.open_tab(name)
            return

        self.active_tab = name

        for tab_name, (_row, button) in self.side_buttons.items():
            selected = tab_name == name
            button.configure(
                bg=TAB_ACTIVE if selected else TAB,
                fg=FG if selected else MUTED,
            )

        for tab_name, button in self.launch_buttons.items():
            selected = tab_name == name
            button.configure(
                bg=TAB_ACTIVE if selected else TAB,
                fg=FG if selected else MUTED,
            )

        self._render_history()
        self._configure_prompt()
        self.command.delete(0, "end")
        self.command.focus_set()

        # Diagnósticos se actualizan al entrar.
        if name == "KILL PY":
            self.refresh_kill_py()
        elif name == "Red":
            self.refresh_red()
        elif name == "SSL":
            self.refresh_ssl()
        elif name == "GitHub":
            self.refresh_github()
        elif name == "Logs":
            self.refresh_logs()

    def _initialize_tab(self, name):
        if name == "Shell":
            self.histories[name] = (
                "PYRION - consola grafica\n"
                "Shell persistente: /bin/sh\n"
                "Atajo global: Ctrl + Alt + T\n"
                "Abre otras pestañas desde la barra superior.\n"
                "------------------------------------------------------------\n"
            )

    def _configure_prompt(self):
        if self.active_tab == "KILL PY":
            self.prompt_label.configure(text="killpy:#")
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
    def refresh_kill_py(self):
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

        self._replace("\n".join(lines), "KILL PY")

    def _kill_number(self, raw):
        try:
            number = int(raw.strip())
        except ValueError:
            self._append("KILL PY: escribe un numero valido.", "KILL PY")
            return

        if number < 1 or number > len(self.processes):
            self._append(
                "KILL PY: ese numero no existe en la lista.",
                "KILL PY",
            )
            return

        pid, cmd = self.processes[number - 1]

        if pid == os.getpid():
            self._append(
                "KILL PY: PYRION CONSOLE esta protegida.",
                "KILL PY",
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
                "KILL PY",
            )
            self.after(400, self.refresh_kill_py)

        except OSError as exc:
            self._append(
                f"ERROR al cerrar PID {pid}: {exc}",
                "KILL PY",
            )

    # ---------- diagnósticos ----------
    def refresh_red(self):
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
        self._replace("\n".join(lines), "Red")

    def refresh_ssl(self):
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
        self._replace("\n".join(lines), "SSL")

    def refresh_github(self):
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
        self._replace("\n".join(lines), "GitHub")

    def refresh_logs(self):
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

        self._replace("\n".join(lines), "Logs")

    # ---------- entrada tipo chat ----------
    def execute_input(self, _event=None):
        text = self.command.get().strip()
        self.command.delete(0, "end")

        if not text or not self.active_tab:
            return

        if self.active_tab == "KILL PY":
            self._append(f"killpy:# {text}", "KILL PY")
            self._kill_number(text)
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

    # ---------- teclado ----------
    def toggle_keyboard(self):
        self.keyboard_visible = not self.keyboard_visible

        if self.keyboard_visible:
            self.keyboard.pack(fill="x", padx=2, pady=(0, 2))
        else:
            self.keyboard.pack_forget()

    def _draw_keyboard(self):
        for child in self.keyboard_rows.winfo_children():
            child.destroy()

        letters = (
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            if self.keyboard_upper
            else "abcdefghijklmnopqrstuvwxyz"
        )

        rows = [
            list("1234567890") + ["-", "=", "⌫"],
            list(letters[:10]),
            list(letters[10:19]) + [";", "'", "[", "]"],
            list(letters[19:])
            + ["/", "\\", ".", ",", "@", "#", "$", "%", "&", "*"],
        ]

        for row_index, chars in enumerate(rows):
            for col_index, char in enumerate(chars):
                command = (
                    self._backspace
                    if char == "⌫"
                    else lambda value=char: self._insert_key(value)
                )

                tk.Button(
                    self.keyboard_rows,
                    text=char,
                    command=command,
                    bg=TAB,
                    fg=FG,
                    activebackground=TAB_ACTIVE,
                    activeforeground=FG,
                    bd=1,
                    relief="solid",
                    width=4,
                    font=("DejaVu Sans Mono", 8),
                ).grid(
                    row=row_index,
                    column=col_index,
                    padx=1,
                    pady=1,
                    sticky="nsew",
                )

        extras = tk.Frame(self.keyboard, bg=PANEL)
        extras.pack(fill="x", padx=4, pady=(0, 4))

        tk.Button(
            extras,
            text="ABC/abc",
            command=self._toggle_case,
            bg=TAB,
            fg=FG,
            bd=1,
        ).pack(side="left")

        tk.Button(
            extras,
            text="ESPACIO",
            command=lambda: self._insert_key(" "),
            bg=TAB,
            fg=FG,
            bd=1,
        ).pack(
            side="left",
            fill="x",
            expand=True,
            padx=3,
        )

        tk.Button(
            extras,
            text="ENTER",
            command=self.execute_input,
            bg=TAB,
            fg=FG,
            bd=1,
        ).pack(side="right")

    def _insert_key(self, value):
        self.command.insert("insert", value)
        self.command.focus_set()

    def _backspace(self):
        position = self.command.index("insert")
        if position > 0:
            self.command.delete(position - 1, position)
        self.command.focus_set()

    def _toggle_case(self):
        self.keyboard_upper = not self.keyboard_upper
        self._draw_keyboard()


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
