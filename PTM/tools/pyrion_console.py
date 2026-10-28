# ARGUMENTOS: pyrion console consola linux procesos python py kill matar cerrar teclado digital virtual caracteres terminal
import os
import signal
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

TOOL_NAME = "PYRION CONSOLE"
TOOL_DESCRIPTION = (
    "Consola de PYRION con KILL PY para listar procesos Python por numero "
    "y teclado digital completo."
)
TOOL_VERSION = "1.0.0"


def _shorten(text, limit=120):
    text = str(text or "").strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _linux_python_processes():
    processes = []
    proc = Path("/proc")

    if proc.is_dir():
        for item in proc.iterdir():
            if not item.name.isdigit():
                continue
            pid = int(item.name)
            try:
                raw = (item / "cmdline").read_bytes()
                cmd = raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
                if not cmd:
                    continue

                lowered = cmd.lower()
                first = lowered.split(" ", 1)[0]
                exe_name = Path(first).name

                if (
                    "python" not in exe_name
                    and ".py" not in lowered
                ):
                    continue

                processes.append((pid, cmd))
            except (OSError, PermissionError):
                continue

        return sorted(processes, key=lambda row: row[0])

    try:
        result = subprocess.run(
            ["ps", "-eo", "pid=,args="],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            try:
                pid = int(parts[0])
            except ValueError:
                continue
            cmd = parts[1].strip()
            lowered = cmd.lower()
            if "python" in lowered or ".py" in lowered:
                processes.append((pid, cmd))
    except OSError:
        pass

    return sorted(processes, key=lambda row: row[0])


def _windows_python_processes():
    processes = []
    ps_script = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -match '^python(w)?(.exe)?$' -or "
        "$_.CommandLine -match '\\.py([ \"']|$)' } | "
        "ForEach-Object { "
        "'{0}|{1}' -f $_.ProcessId, ($_.CommandLine -replace '[\\r\\n]+',' ') "
        "}"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
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
                pid = int(pid_text.strip())
            except ValueError:
                continue
            processes.append((pid, cmd.strip() or "python"))
    except OSError:
        pass

    return sorted(processes, key=lambda row: row[0])


def list_python_processes():
    if os.name == "nt":
        return _windows_python_processes()
    return _linux_python_processes()


class PyrionConsoleTool(ttk.Frame):
    def __init__(self, parent, app=None):
        super().__init__(parent)
        self.app = app
        self.processes = []
        self.selected_number = tk.StringVar()
        self.status = tk.StringVar(value="KILL PY listo.")
        self.keyboard_visible = False
        self.keyboard_mode = tk.StringVar(value="abc")
        self.last_target = None
        self._build_ui()
        self.refresh_processes()

    def _build_ui(self):
        header = ttk.Frame(self)
        header.pack(fill="x", pady=(0, 8))

        ttk.Label(
            header,
            text=TOOL_NAME,
            font=("Segoe UI", 16, "bold"),
        ).pack(side="left")

        ttk.Label(
            header,
            text=f"v{TOOL_VERSION}",
            font=("Segoe UI", 8),
        ).pack(side="left", padx=(8, 0), pady=(5, 0))

        ttk.Button(
            header,
            text="⌨ Teclado",
            command=self.toggle_keyboard,
        ).pack(side="right")

        main = ttk.Panedwindow(self, orient="horizontal")
        main.pack(fill="both", expand=True)

        left = ttk.Frame(main, padding=6)
        right = ttk.Frame(main, padding=6)
        main.add(left, weight=3)
        main.add(right, weight=2)

        # --- KILL PY ---
        kill_head = ttk.Frame(left)
        kill_head.pack(fill="x")

        ttk.Label(
            kill_head,
            text="KILL PY",
            font=("Segoe UI", 13, "bold"),
        ).pack(side="left")

        ttk.Button(
            kill_head,
            text="Actualizar",
            command=self.refresh_processes,
        ).pack(side="right")

        ttk.Label(
            left,
            text=(
                "Procesos Python detectados. El numero de la izquierda es el que "
                "debes escribir para cerrar el proceso."
            ),
            wraplength=650,
        ).pack(fill="x", pady=(4, 8))

        tree_box = ttk.Frame(left)
        tree_box.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(
            tree_box,
            columns=("number", "pid", "command"),
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("number", text="#")
        self.tree.heading("pid", text="PID")
        self.tree.heading("command", text="Proceso Python")
        self.tree.column("number", width=48, stretch=False, anchor="center")
        self.tree.column("pid", width=78, stretch=False, anchor="center")
        self.tree.column("command", width=520, anchor="w")

        ybar = ttk.Scrollbar(tree_box, orient="vertical", command=self.tree.yview)
        xbar = ttk.Scrollbar(tree_box, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        tree_box.columnconfigure(0, weight=1)
        tree_box.rowconfigure(0, weight=1)

        self.tree.bind("<<TreeviewSelect>>", self._tree_selected)

        action = ttk.Frame(left)
        action.pack(fill="x", pady=(10, 0))

        ttk.Label(action, text="Numero:").pack(side="left")
        self.number_entry = ttk.Entry(
            action,
            textvariable=self.selected_number,
            width=8,
            justify="center",
        )
        self.number_entry.pack(side="left", padx=6)
        self.number_entry.bind("<Return>", lambda _event: self.kill_selected())

        ttk.Button(
            action,
            text="KILL PY",
            command=self.kill_selected,
        ).pack(side="left")

        ttk.Label(
            left,
            textvariable=self.status,
            wraplength=650,
        ).pack(fill="x", pady=(8, 0))

        # --- Consola / entrada libre ---
        ttk.Label(
            right,
            text="Entrada",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            right,
            text=(
                "El teclado digital escribe en el ultimo campo seleccionado. "
                "Tambien puedes usar esta zona como bloc rapido de comandos."
            ),
            wraplength=420,
        ).pack(fill="x", pady=(4, 8))

        self.command_text = tk.Text(
            right,
            height=12,
            wrap="word",
            undo=True,
        )
        self.command_text.pack(fill="both", expand=True)
        self.command_text.bind("<FocusIn>", lambda _e: self._set_target(self.command_text))
        self.number_entry.bind("<FocusIn>", lambda _e: self._set_target(self.number_entry))

        command_buttons = ttk.Frame(right)
        command_buttons.pack(fill="x", pady=(6, 0))
        ttk.Button(
            command_buttons,
            text="Limpiar",
            command=lambda: self.command_text.delete("1.0", "end"),
        ).pack(side="left")
        ttk.Button(
            command_buttons,
            text="Copiar",
            command=self.copy_command_text,
        ).pack(side="left", padx=6)

        # --- Teclado digital ---
        self.keyboard = ttk.Frame(self, padding=(4, 8))
        self.keyboard_tabs = ttk.Frame(self.keyboard)
        self.keyboard_tabs.pack(fill="x", pady=(0, 5))

        for label, mode in (
            ("abc", "abc"),
            ("ABC", "ABC"),
            ("123", "123"),
            ("Símbolos", "sym"),
        ):
            ttk.Button(
                self.keyboard_tabs,
                text=label,
                command=lambda m=mode: self.show_keyboard_mode(m),
            ).pack(side="left", padx=(0, 4))

        ttk.Button(
            self.keyboard_tabs,
            text="Espacio",
            command=lambda: self.insert_key(" "),
        ).pack(side="right", padx=(4, 0))
        ttk.Button(
            self.keyboard_tabs,
            text="⌫",
            command=self.backspace,
        ).pack(side="right")
        ttk.Button(
            self.keyboard_tabs,
            text="Enter",
            command=lambda: self.insert_key("\n"),
        ).pack(side="right", padx=(0, 4))

        self.key_grid = ttk.Frame(self.keyboard)
        self.key_grid.pack(fill="x")
        self.show_keyboard_mode("abc")

    def _set_target(self, widget):
        self.last_target = widget

    def _tree_selected(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        values = self.tree.item(selection[0], "values")
        if values:
            self.selected_number.set(str(values[0]))

    def refresh_processes(self):
        self.processes = list_python_processes()
        self.tree.delete(*self.tree.get_children())

        current_pid = os.getpid()

        for index, (pid, command) in enumerate(self.processes, start=1):
            shown = _shorten(command, 180)
            if pid == current_pid:
                shown += "  [PTM / ESTA HERRAMIENTA]"
            self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=(index, pid, shown),
            )

        self.status.set(
            f"{len(self.processes)} proceso(s) Python detectado(s). "
            "Escribe el numero y pulsa KILL PY."
        )

    def kill_selected(self):
        raw = self.selected_number.get().strip()
        try:
            number = int(raw)
        except ValueError:
            messagebox.showinfo(
                "KILL PY",
                "Escribe el numero del proceso, por ejemplo: 1",
                parent=self,
            )
            return

        if number < 1 or number > len(self.processes):
            messagebox.showerror(
                "KILL PY",
                "Ese numero no existe en la lista actual.",
                parent=self,
            )
            return

        pid, command = self.processes[number - 1]

        if pid == os.getpid():
            messagebox.showwarning(
                "KILL PY",
                "Ese proceso es PTM / PYRION CONSOLE y esta protegido para evitar cerrar la herramienta por accidente.",
                parent=self,
            )
            return

        confirm = messagebox.askyesno(
            "KILL PY",
            f"¿Cerrar el proceso #{number}?\n\nPID: {pid}\n{_shorten(command, 240)}",
            parent=self,
        )
        if not confirm:
            return

        try:
            if os.name == "nt":
                result = subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T"],
                    capture_output=True,
                    text=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if result.returncode != 0:
                    raise RuntimeError(
                        (result.stderr or result.stdout or "taskkill fallo").strip()
                    )
            else:
                os.kill(pid, signal.SIGTERM)

            self.status.set(f"Solicitud de cierre enviada a #{number} · PID {pid}.")
            self.after(350, self.refresh_processes)
        except (OSError, RuntimeError) as exc:
            messagebox.showerror(
                "KILL PY",
                f"No se pudo cerrar PID {pid}:\n\n{exc}",
                parent=self,
            )

    def toggle_keyboard(self):
        self.keyboard_visible = not self.keyboard_visible
        if self.keyboard_visible:
            self.keyboard.pack(fill="x", side="bottom")
            if self.last_target is None:
                self._set_target(self.command_text)
        else:
            self.keyboard.pack_forget()

    def show_keyboard_mode(self, mode):
        self.keyboard_mode.set(mode)
        for child in self.key_grid.winfo_children():
            child.destroy()

        layouts = {
            "abc": list("abcdefghijklmnñopqrstuvwxyz"),
            "ABC": list("ABCDEFGHIJKLMNÑOPQRSTUVWXYZ"),
            "123": list("1234567890"),
            "sym": list("!¡?¿@#$%&*()[]{}<>+-_=/:;.,\\|'\"~^°¬€£¥"),
        }
        keys = layouts.get(mode, layouts["abc"])

        columns = 13 if mode in ("abc", "ABC") else 12
        for index, char in enumerate(keys):
            row = index // columns
            col = index % columns
            ttk.Button(
                self.key_grid,
                text=char,
                width=4,
                command=lambda value=char: self.insert_key(value),
            ).grid(row=row, column=col, padx=2, pady=2, sticky="nsew")

        for col in range(columns):
            self.key_grid.columnconfigure(col, weight=1)

    def _target(self):
        widget = self.last_target
        if widget is None or not widget.winfo_exists():
            widget = self.command_text
            self.last_target = widget
        return widget

    def insert_key(self, value):
        widget = self._target()
        try:
            if isinstance(widget, tk.Text):
                widget.insert("insert", value)
                widget.see("insert")
            else:
                widget.insert("insert", value)
            widget.focus_set()
        except tk.TclError:
            self.last_target = self.command_text

    def backspace(self):
        widget = self._target()
        try:
            if isinstance(widget, tk.Text):
                if widget.index("insert") != "1.0":
                    widget.delete("insert-1c", "insert")
            else:
                pos = widget.index("insert")
                if pos > 0:
                    widget.delete(pos - 1, pos)
            widget.focus_set()
        except tk.TclError:
            pass

    def copy_command_text(self):
        text = self.command_text.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status.set("Texto copiado al portapapeles.")

    def on_close(self):
        pass


App = PyrionConsoleTool


def main():
    root = tk.Tk()
    root.title(TOOL_NAME)
    root.geometry("1180x760")
    tool = App(root)
    tool.pack(fill="both", expand=True, padx=12, pady=12)
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
