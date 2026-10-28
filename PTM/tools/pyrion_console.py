# ARGUMENTOS: pyrion console consola linux procesos python py kill matar cerrar teclado digital virtual caracteres terminal red ssl github logs
import os
import signal
import subprocess
import sys
import tkinter as tk
from pathlib import Path

TOOL_NAME = "PYRION CONSOLE"
TOOL_DESCRIPTION = "Consola PYRION con KILL PY, Red, SSL, GitHub, Logs y teclado digital."
TOOL_VERSION = "1.1.0"

BG = "#05090C"
PANEL = "#0C141D"
TAB = "#151C25"
TAB_ACTIVE = "#263544"
BORDER = "#6C747E"
FG = "#D7DCE2"
MUTED = "#98A2AD"
GREEN = "#42D392"
RED = "#FF4D57"
ACCENT = "#7EB7FF"


def _shorten(text, limit=120):
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
                    cmd = raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
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
            out = subprocess.run(
                ["ps", "-eo", "pid=,args="],
                capture_output=True, text=True, check=False
            ).stdout
            for line in out.splitlines():
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

    ps = (
        "Get-CimInstance Win32_Process | "
        "Where-Object {$_.Name -match '^python(w)?(.exe)?$' -or $_.CommandLine -match '\\.py'} | "
        "ForEach-Object {'{0}|{1}' -f $_.ProcessId,$_.CommandLine}"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        ).stdout
        for line in out.splitlines():
            if "|" not in line:
                continue
            p, cmd = line.split("|", 1)
            try:
                rows.append((int(p.strip()), cmd.strip()))
            except ValueError:
                pass
    except OSError:
        pass
    return sorted(rows)


class PyrionConsoleTool(tk.Frame):
    def __init__(self, parent, app=None):
        super().__init__(parent, bg=BG)
        self.app = app
        self.processes = []
        self.active_tab = None
        self.keyboard_visible = False
        self.keyboard_upper = False
        self._build_ui()
        self.show_console()

    def _build_ui(self):
        self.pack_propagate(False)

        top = tk.Frame(self, bg=TAB, height=31)
        top.pack(fill="x", padx=2, pady=(2, 0))
        top.pack_propagate(False)

        title = tk.Label(
            top, text="PYRION Console", bg=TAB, fg=FG,
            font=("DejaVu Sans", 10, "bold"), padx=12
        )
        title.pack(side="left", fill="y")

        self.tabs = {}
        for label, command in (
            ("KILL PY", self.show_kill_py),
            ("Red", self.show_red),
            ("SSL", self.show_ssl),
            ("GitHub", self.show_github),
            ("Logs", self.show_logs),
        ):
            b = tk.Button(
                top, text=label, command=command,
                bg=TAB, fg=MUTED, activebackground=TAB_ACTIVE,
                activeforeground=FG, bd=1, relief="solid",
                highlightthickness=0, padx=10,
                font=("DejaVu Sans", 9)
            )
            b.pack(side="left", fill="y")
            self.tabs[label] = b

        tk.Button(
            top, text="✕", command=self.clear_output,
            bg=TAB, fg=RED, activebackground=TAB_ACTIVE,
            activeforeground=RED, bd=1, relief="solid",
            highlightthickness=0, width=6,
            font=("DejaVu Sans", 11, "bold")
        ).pack(side="right", fill="y")

        tk.Button(
            top, text="Limpiar", command=self.clear_output,
            bg=TAB, fg=MUTED, activebackground=TAB_ACTIVE,
            activeforeground=FG, bd=1, relief="solid",
            highlightthickness=0, padx=12,
            font=("DejaVu Sans", 9)
        ).pack(side="right", fill="y")

        self.body = tk.Frame(self, bg=BG, bd=1, relief="solid")
        self.body.pack(fill="both", expand=True, padx=2, pady=0)

        self.output = tk.Text(
            self.body,
            bg=BG, fg=FG, insertbackground=FG,
            selectbackground="#29435B", selectforeground=FG,
            font=("DejaVu Sans Mono", 9),
            bd=0, highlightthickness=0, wrap="word",
            padx=9, pady=7
        )
        scroll = tk.Scrollbar(self.body, command=self.output.yview)
        self.output.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.output.pack(side="left", fill="both", expand=True)
        self.output.configure(state="disabled")

        prompt = tk.Frame(self, bg=PANEL, height=42)
        prompt.pack(fill="x", padx=2, pady=(0, 2))
        prompt.pack_propagate(False)

        self.prompt_label = tk.Label(
            prompt, text="root@mini1:#", bg=PANEL, fg=GREEN,
            font=("DejaVu Sans Mono", 10, "bold")
        )
        self.prompt_label.pack(side="left", padx=(9, 5))

        self.command = tk.Entry(
            prompt, bg=PANEL, fg=FG, insertbackground=FG,
            font=("DejaVu Sans Mono", 10),
            bd=0, highlightthickness=0
        )
        self.command.pack(side="left", fill="both", expand=True, padx=(0, 7), pady=7)
        self.command.bind("<Return>", self.execute_command)

        tk.Button(
            prompt, text="⌨", command=self.toggle_keyboard,
            bg=PANEL, fg=ACCENT, activebackground=TAB_ACTIVE,
            activeforeground=FG, bd=0, padx=8,
            font=("DejaVu Sans", 12)
        ).pack(side="right", fill="y")

        self.keyboard = tk.Frame(self, bg=PANEL)
        self.keyboard_rows = tk.Frame(self.keyboard, bg=PANEL)
        self.keyboard_rows.pack(fill="x", padx=4, pady=4)
        self._draw_keyboard()

    def _set_tab(self, name=None):
        self.active_tab = name
        for label, btn in self.tabs.items():
            btn.configure(
                bg=TAB_ACTIVE if label == name else TAB,
                fg=FG if label == name else MUTED
            )

    def _write(self, text="", clear=False):
        self.output.configure(state="normal")
        if clear:
            self.output.delete("1.0", "end")
        if text:
            self.output.insert("end", text)
            if not text.endswith("\n"):
                self.output.insert("end", "\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def clear_output(self):
        self._write("", clear=True)

    def show_console(self):
        self._set_tab(None)
        self._write(
            "PYRION - consola grafica\n"
            "Shell persistente: /bin/sh\n"
            "Atajo global: Ctrl + Alt + T\n"
            "Diagnostico de un clic: KILL PY | Red | SSL | GitHub | Logs\n"
            "------------------------------------------------------------\n",
            clear=True
        )

    def show_kill_py(self):
        self._set_tab("KILL PY")
        self.processes = list_python_processes()
        lines = [
            "KILL PY",
            "Procesos Python detectados:",
            "",
        ]
        current = os.getpid()
        if not self.processes:
            lines.append("No se encontraron procesos Python.")
        else:
            for i, (pid, cmd) in enumerate(self.processes, 1):
                mark = " [PYRION CONSOLE]" if pid == current else ""
                lines.append(f"{i}. PID {pid}  {_shorten(cmd, 150)}{mark}")
        lines += [
            "",
            "Escribe SOLO el numero del proceso en la linea inferior",
            "y pulsa Enter para cerrarlo.",
        ]
        self._write("\n".join(lines), clear=True)
        self.prompt_label.configure(text="killpy:#")
        self.command.delete(0, "end")
        self.command.focus_set()

    def _kill_number(self, raw):
        try:
            number = int(raw.strip())
        except ValueError:
            self._write("KILL PY: escribe un numero valido.")
            return
        if number < 1 or number > len(self.processes):
            self._write("KILL PY: ese numero no existe en la lista.")
            return

        pid, cmd = self.processes[number - 1]
        if pid == os.getpid():
            self._write("KILL PY: PYRION CONSOLE esta protegida.")
            return

        try:
            if os.name == "nt":
                r = subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True, text=True, check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                )
                if r.returncode != 0:
                    raise OSError((r.stderr or r.stdout).strip())
            else:
                os.kill(pid, signal.SIGTERM)
            self._write(f"Cerrando #{number} · PID {pid} · {_shorten(cmd, 100)}")
            self.after(400, self.show_kill_py)
        except OSError as exc:
            self._write(f"ERROR al cerrar PID {pid}: {exc}")

    def show_red(self):
        self._set_tab("Red")
        self.prompt_label.configure(text="root@mini1:#")
        commands = [
            ["ip", "addr"],
            ["ip", "route"],
        ]
        self._write("RED - diagnostico\n", clear=True)
        for cmd in commands:
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=4)
                self._write(f"$ {' '.join(cmd)}\n{r.stdout or r.stderr}")
            except Exception as exc:
                self._write(f"$ {' '.join(cmd)}\n{exc}")

    def show_ssl(self):
        self._set_tab("SSL")
        self.prompt_label.configure(text="root@mini1:#")
        self._write("SSL - diagnostico\n", clear=True)
        for cmd in (["openssl", "version"], ["python3", "-c", "import ssl; print(ssl.OPENSSL_VERSION)"]):
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                self._write(f"$ {' '.join(cmd)}\n{r.stdout or r.stderr}")
            except Exception as exc:
                self._write(str(exc))

    def show_github(self):
        self._set_tab("GitHub")
        self.prompt_label.configure(text="root@mini1:#")
        self._write("GitHub - conectividad\n", clear=True)
        try:
            r = subprocess.run(
                ["python3", "-c",
                 "import urllib.request; r=urllib.request.urlopen('https://github.com',timeout=5); print('HTTP',r.status)"],
                capture_output=True, text=True, timeout=7
            )
            self._write(r.stdout or r.stderr)
        except Exception as exc:
            self._write(str(exc))

    def show_logs(self):
        self._set_tab("Logs")
        self.prompt_label.configure(text="root@mini1:#")
        self._write("Logs recientes\n", clear=True)
        candidates = ["/var/log/messages", "/var/log/syslog", "/tmp/pyrion.log"]
        found = False
        for path in candidates:
            if Path(path).is_file():
                found = True
                try:
                    lines = Path(path).read_text(errors="replace").splitlines()[-60:]
                    self._write(f"--- {path} ---\n" + "\n".join(lines))
                except OSError as exc:
                    self._write(f"{path}: {exc}")
        if not found:
            self._write("No se encontraron logs conocidos.")

    def execute_command(self, _event=None):
        text = self.command.get().strip()
        self.command.delete(0, "end")
        if not text:
            return

        if self.active_tab == "KILL PY":
            self._kill_number(text)
            return

        self._set_tab(None)
        self.prompt_label.configure(text="root@mini1:#")
        self._write(f"root@mini1:# {text}")
        try:
            r = subprocess.run(
                text,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                executable=None if os.name == "nt" else "/bin/sh"
            )
            out = (r.stdout or "") + (r.stderr or "")
            if out:
                self._write(out.rstrip())
            if r.returncode:
                self._write(f"[exit {r.returncode}]")
        except subprocess.TimeoutExpired:
            self._write("[timeout]")
        except Exception as exc:
            self._write(f"[error] {exc}")

    def toggle_keyboard(self):
        self.keyboard_visible = not self.keyboard_visible
        if self.keyboard_visible:
            self.keyboard.pack(fill="x", padx=2, pady=(0, 2))
        else:
            self.keyboard.pack_forget()

    def _draw_keyboard(self):
        for child in self.keyboard_rows.winfo_children():
            child.destroy()

        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if self.keyboard_upper else "abcdefghijklmnopqrstuvwxyz"
        rows = [
            list("1234567890") + ["-", "=", "⌫"],
            list(letters[:10]),
            list(letters[10:19]) + [";", "'", "[", "]"],
            list(letters[19:]) + ["/", "\\", ".", ",", "@", "#", "$", "%", "&", "*"],
        ]

        for r, chars in enumerate(rows):
            for c, ch in enumerate(chars):
                cmd = self._backspace if ch == "⌫" else (lambda x=ch: self._insert_key(x))
                tk.Button(
                    self.keyboard_rows, text=ch, command=cmd,
                    bg=TAB, fg=FG, activebackground=TAB_ACTIVE,
                    activeforeground=FG, bd=1, relief="solid",
                    width=4, font=("DejaVu Sans Mono", 8)
                ).grid(row=r, column=c, padx=1, pady=1, sticky="nsew")

        extras = tk.Frame(self.keyboard, bg=PANEL)
        extras.pack(fill="x", padx=4, pady=(0, 4))
        tk.Button(extras, text="ABC/abc", command=self._toggle_case, bg=TAB, fg=FG, bd=1).pack(side="left")
        tk.Button(extras, text="ESPACIO", command=lambda: self._insert_key(" "), bg=TAB, fg=FG, bd=1).pack(side="left", fill="x", expand=True, padx=3)
        tk.Button(extras, text="ENTER", command=lambda: self.execute_command(), bg=TAB, fg=FG, bd=1).pack(side="right")

    def _insert_key(self, value):
        self.command.insert("insert", value)
        self.command.focus_set()

    def _backspace(self):
        pos = self.command.index("insert")
        if pos > 0:
            self.command.delete(pos - 1, pos)
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
