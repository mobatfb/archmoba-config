# CANVAEDIT RUNNER
# Unica funcion: actualizar canvaedit.py desde GitHub y mostrarlo debajo.

from pathlib import Path
import importlib
import sys
import tempfile
import tkinter as tk
from tkinter import messagebox
import urllib.request
import json
import base64

BASE_DIR = Path(__file__).resolve().parent
CANVAEDIT_FILE = BASE_DIR / "canvaedit.py"
RUN_VERSION = "1.0.1"
CANVAEDIT_API_URL = (
    "https://api.github.com/repos/"
    "mobatfb/archmoba-config/contents/"
    "AMDEV/TOOLS/CANVAEDIT/canvaedit.py?ref=main"
)


class CanvaEditRunner(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"CANVAEDIT RUN v{RUN_VERSION}")
        self.geometry("1280x820")
        self.minsize(900, 620)
        self.configure(bg="#11151a")

        self.editor = None
        self.module = None

        self._build_ui()
        self.load_canvaedit()

    def _build_ui(self):
        top = tk.Frame(self, bg="#171c22", height=54)
        top.pack(fill="x")
        top.pack_propagate(False)

        tk.Button(
            top,
            text="Actualizar",
            command=self.update_canvaedit,
            bg="#2b3440",
            fg="#ffffff",
            activebackground="#3a4654",
            activeforeground="#ffffff",
            relief="flat",
            padx=18,
            pady=7,
            cursor="hand2",
        ).pack(side="right", padx=12, pady=9)

        self.status_var = tk.StringVar(value="CANVAEDIT")
        tk.Label(
            top,
            textvariable=self.status_var,
            bg="#171c22",
            fg="#9aa6b3",
            font=("Arial", 9),
            anchor="w",
        ).pack(side="left", padx=14)

        self.viewer = tk.Frame(self, bg="#11151a")
        self.viewer.pack(fill="both", expand=True)

    def load_canvaedit(self):
        try:
            if self.editor is not None:
                self.editor.destroy()
                self.editor = None

            if str(BASE_DIR) not in sys.path:
                sys.path.insert(0, str(BASE_DIR))

            if "canvaedit" in sys.modules:
                self.module = importlib.reload(sys.modules["canvaedit"])
            else:
                self.module = importlib.import_module("canvaedit")

            self.editor = self.module.CanvaEditFrame(self.viewer)
            self.editor.pack(fill="both", expand=True)
            version = getattr(self.module, "CANVAEDIT_VERSION", "sin version")
            self.status_var.set(f"CANVAEDIT v{version}")

        except Exception as exc:
            self.status_var.set("Error al cargar CANVAEDIT")
            messagebox.showerror(
                "CANVAEDIT RUN",
                f"No se pudo cargar canvaedit.py:\n\n{exc}",
            )

    def update_canvaedit(self):
        self.status_var.set("Buscando actualizacion...")
        self.update_idletasks()

        try:
            request = urllib.request.Request(
                CANVAEDIT_API_URL,
                headers={
                    "User-Agent": "CANVAEDIT-RUN/1.0",
                    "Accept": "application/vnd.github+json",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))

            content = payload.get("content", "")
            encoding = payload.get("encoding", "")

            if encoding != "base64" or not content:
                raise RuntimeError(
                    "GitHub no devolvio canvaedit.py en Base64."
                )

            new_code = base64.b64decode(
                content.replace("\n", "")
            ).decode("utf-8")

            if not new_code.strip():
                raise RuntimeError("El archivo recibido esta vacio.")

            compile(new_code, str(CANVAEDIT_FILE), "exec")

            current_code = ""
            if CANVAEDIT_FILE.is_file():
                current_code = CANVAEDIT_FILE.read_text(encoding="utf-8")

            if new_code == current_code:
                self.status_var.set("CANVAEDIT ya esta actualizado")
                return

            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                delete=False,
                dir=str(BASE_DIR),
                suffix=".tmp",
            ) as temp:
                temp.write(new_code)
                temp_path = Path(temp.name)

            temp_path.replace(CANVAEDIT_FILE)

            self.status_var.set("Actualizado. Recargando...")
            self.update_idletasks()
            self.load_canvaedit()
            version = getattr(self.module, "CANVAEDIT_VERSION", "sin version")
            self.status_var.set(f"CANVAEDIT actualizado · v{version}")

        except Exception as exc:
            self.status_var.set("No se pudo actualizar")
            messagebox.showerror(
                "CANVAEDIT RUN",
                f"No se pudo actualizar canvaedit.py:\n\n{exc}",
            )


def main():
    app = CanvaEditRunner()
    app.mainloop()


if __name__ == "__main__":
    main()
