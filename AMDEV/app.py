# ARGUMENTOS: amdev archmomadev launcher apps aplicaciones catalogo remoto github
import base64
import ctypes
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
from pathlib import Path
from tkinter import messagebox

APP_NAME = "ArchMomaDEV"
APP_SHORT = "AMDEV"
APP_VERSION = "1.0.21"
APP_UPDATE_DATE = "29/10/2026"
APP_UPDATE_TIME = "15:18"

REPO_OWNER = "mobatfb"
REPO_NAME = "archmoba-dev"
REPO_RAW_ROOT = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}"

# Interruptor: True = archivos locales ./; False = repositorio GitHub.
MODO_LOCAL = True
# Si falta apps.json junto a este app.py, usar GitHub automáticamente.
MODO_LOCAL = MODO_LOCAL and Path(__file__).resolve().with_name("apps.json").is_file()
# ./ es la raiz del proyecto, independientemente de la carpeta de arranque.
LOCAL_ROOT = Path(__file__).resolve().parent.parent


def _local_path(repo_path):
    path = (LOCAL_ROOT / repo_path).resolve()
    if not path.is_relative_to(LOCAL_ROOT):
        raise ValueError("La ruta debe estar dentro del proyecto local.")
    return path

def _windowless_python():
    """Devuelve pythonw.exe en Windows cuando está disponible."""
    executable = Path(sys.executable)
    if os.name == "nt" and executable.name.lower() == "python.exe":
        pythonw = executable.with_name("pythonw.exe")
        if pythonw.is_file():
            return str(pythonw)
    return str(executable)


def _ensure_windowless_amdev():
    """Relanza AMDEV sin consola cuando fue iniciado con python.exe."""
    if os.name != "nt":
        return False

    executable = Path(sys.executable)
    if executable.name.lower() != "python.exe":
        return False

    pythonw = executable.with_name("pythonw.exe")
    if not pythonw.is_file():
        return False

    if os.environ.get("AMDEV_WINDOWLESS") == "1":
        return False

    env = os.environ.copy()
    env["AMDEV_WINDOWLESS"] = "1"
    current = Path(__file__).resolve()
    subprocess.Popen(
        [str(pythonw), str(current), *sys.argv[1:]],
        cwd=str(current.parent),
        env=env,
    )
    return True

REPO_RAW_BASE = f"{REPO_RAW_ROOT}/main"
APPS_REPO_PATH = "AMDEV/apps.json"
APPS_URL = f"{REPO_RAW_BASE}/{APPS_REPO_PATH}"
SELF_CONFIG_API_URL = (
    f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/AMDEV/config.json?ref=main"
)

TEAL = "#176684"
TEAL_DARK = "#0F536E"
RED = "#FF1616"
WHITE = "#FFFFFF"
BLACK = "#101010"
LIGHT = "#F4F4F4"
MID = "#D7D7D7"
MUTED = "#666666"


def _is_app_active(item):
    """Visibilidad del catálogo: 'activo' tiene prioridad sobre 'active'.

    Si falta el campo, la app se mantiene visible por compatibilidad.
    Solo el valor booleano JSON true habilita una entrada definida.
    """
    if not isinstance(item, dict):
        return False
    return item.get("activo", item.get("active", True)) is True


def _version_tuple(value):
    parts = []
    for part in str(value).strip().split("."):
        m = re.match(r"(\d+)", part)
        parts.append(int(m.group(1)) if m else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _fetch_self_release():
    """Lee config y app.py evitando depender del rate limit de GitHub API."""
    if MODO_LOCAL:
        config = json.loads(_local_path("AMDEV/config.json").read_text(encoding="utf-8-sig"))
        app_path = str(config.get("app_path", "AMDEV/app.py"))
        source = _local_path(app_path).read_text(encoding="utf-8-sig")
        match = re.search(r'''APP_VERSION\s*=\s*["']([^"']+)["']''', source)
        version = str(config.get("version", "")).strip()
        if not version or not match or match.group(1).strip() != version:
            raise RuntimeError("La version del app.py local no coincide con config.json")
        compile(source, app_path, "exec")
        return config, source
    config = None

    # RAW primero: las consultas publicas de AMDEV no necesitan consumir
    # el limite de 60 peticiones/hora de la API sin autenticar.
    try:
        request = urllib.request.Request(
            f"{REPO_RAW_BASE}/AMDEV/config.json?v={time.time_ns()}",
            headers={
                "User-Agent": f"AMDEV/{APP_VERSION}",
                "Cache-Control": "no-cache",
            },
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            config = json.loads(response.read().decode("utf-8-sig"))
    except Exception:
        config = None

    # API solo como respaldo.
    if config is None:
        request = urllib.request.Request(
            SELF_CONFIG_API_URL,
            headers={
                "User-Agent": f"AMDEV/{APP_VERSION}",
                "Accept": "application/vnd.github+json",
                "Cache-Control": "no-cache",
            },
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))

        encoded = str(payload.get("content", "")).replace("\n", "")
        config = json.loads(
            base64.b64decode(encoded).decode("utf-8-sig")
        )

    remote_version = str(config.get("version", "")).strip()
    release_commit = str(config.get("release_commit", "")).strip()
    app_path = str(
        config.get("app_path", "AMDEV/app.py")
    ).strip().replace("\\", "/").lstrip("/")

    if not remote_version:
        raise RuntimeError("config.json no contiene una version valida")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", release_commit):
        raise RuntimeError("config.json no contiene un release_commit valido")

    url = (
        f"{REPO_RAW_ROOT}/{release_commit}/{app_path}"
        f"?v={time.time_ns()}"
    )
    source_request = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"AMDEV/{APP_VERSION}",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(source_request, timeout=15) as response:
        source = response.read().decode("utf-8-sig")

    match = re.search(
        r'''APP_VERSION\s*=\s*["']([^"']+)["']''',
        source,
    )
    if not match or match.group(1).strip() != remote_version:
        raise RuntimeError(
            "La version del app.py no coincide con config.json"
        )

    compile(source, "AMDEV/app.py", "exec")
    return config, source


def _launch_update_helper(source):
    """Escribe la nueva version y deja el reemplazo a un proceso auxiliar."""
    current = Path(__file__).resolve()
    parent_pid = os.getpid()

    pending = current.with_suffix(current.suffix + ".pending")
    helper = current.with_suffix(current.suffix + ".updater.py")

    if not MODO_LOCAL:
        pending.write_text(source, encoding="utf-8")

    helper_source = f'''import os
import subprocess
import sys
import time
from pathlib import Path

target = Path({str(current)!r})
pending = Path({str(pending)!r})
helper = Path({str(helper)!r})
parent_pid = {parent_pid}

def parent_alive(pid):
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    try:
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        SYNCHRONIZE = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE,
            False,
            pid,
        )
        if not handle:
            return False
        WAIT_TIMEOUT = 0x00000102
        result = ctypes.windll.kernel32.WaitForSingleObject(handle, 0)
        ctypes.windll.kernel32.CloseHandle(handle)
        return result == WAIT_TIMEOUT
    except Exception:
        return False

deadline = time.time() + 15
while parent_alive(parent_pid) and time.time() < deadline:
    time.sleep(0.12)

last_error = None
for _ in range(0 if {MODO_LOCAL!r} else 80):
    try:
        os.replace(pending, target)
        last_error = None
        break
    except Exception as exc:
        last_error = exc
        time.sleep(0.12)

if last_error is not None:
    raise SystemExit(2)

exe = Path(sys.executable)
if os.name == "nt" and exe.name.lower() == "python.exe":
    pythonw = exe.with_name("pythonw.exe")
    if pythonw.is_file():
        exe = pythonw

subprocess.Popen(
    [str(exe), str(target)],
    cwd=str(target.parent),
)

try:
    helper.unlink(missing_ok=True)
except Exception:
    pass
'''

    helper.write_text(helper_source, encoding="utf-8")

    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(
            subprocess,
            "CREATE_NO_WINDOW",
            0,
        )

    subprocess.Popen(
        [_windowless_python(), str(helper)],
        cwd=str(current.parent),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **kwargs,
    )


def check_self_update():
    """Actualiza AMDEV al arrancar usando un proceso auxiliar seguro."""
    try:
        config, source = _fetch_self_release()
        remote_version = str(config.get("version", "")).strip()

        if (
            not remote_version
            or _version_tuple(remote_version) <= _version_tuple(APP_VERSION)
        ):
            return False

        # En Windows se conserva el helper original, porque python.exe/pythonw.exe
        # puede mantener bloqueado el archivo mientras AMDEV esta en ejecucion.
        if os.name == "nt":
            _launch_update_helper(source)
            return True

        # En MiniLinux/Linux no debemos terminar el proceso principal: /init
        # interpreta la salida de AMDEV como fin de la sesion y entra en la
        # consola de rescate. Reemplazamos el archivo de forma atomica y usamos
        # execv(), que mantiene el mismo proceso en lugar de devolver el control
        # al init.
        current = Path(__file__).resolve()
        if not MODO_LOCAL:
            pending = current.with_suffix(current.suffix + ".pending")
            pending.write_text(source, encoding="utf-8")
            os.replace(pending, current)
        os.execv(
            sys.executable,
            [sys.executable, str(current), *sys.argv[1:]],
        )
        return False  # Solo se alcanza si execv no reemplazo el proceso.
    except Exception:
        return False

def detect_system_dark_mode():
    if sys.platform == "win32":
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return int(value) == 0
        except Exception:
            return False
    return "dark" in os.environ.get("GTK_THEME", "").lower()


DARK_MODE = detect_system_dark_mode()
BG = "#17191C" if DARK_MODE else WHITE
FG = "#F2F4F7" if DARK_MODE else BLACK
CARD = "#22252A" if DARK_MODE else LIGHT
BORDER = "#3A3F46" if DARK_MODE else MID
MUTED_FG = "#A9AFB8" if DARK_MODE else MUTED


class FloatingAMDEV(tk.Toplevel):
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

        self.w = 112
        self.h = 52
        self.geometry(f"{self.w}x{self.h}+0+0")
        self.canvas = tk.Canvas(
            self, width=self.w, height=self.h,
            bg="#010101", highlightthickness=0, bd=0,
            cursor="hand2"
        )
        self.canvas.pack(fill="both", expand=True)
        self._draw()

        self.canvas.bind("<Button-1>", self._down)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._up)
        self.canvas.bind("<Button-3>", self._menu)

        self._dragging = False
        self._press_xy = (0, 0)
        self._loading = False
        self._place_default()

    def _draw(self):
        self.canvas.delete("all")
        self.canvas.create_rectangle(2, 2, self.w - 2, self.h - 2, fill=TEAL, outline=FG, width=1)
        self.canvas.create_polygon(self.w - 20, 2, self.w - 2, 2, self.w - 2, 20, fill=RED, outline=RED)
        self.canvas.create_rectangle(2, self.h - 9, self.w - 2, self.h - 2, fill=RED, outline=RED)
        self.canvas.create_text(self.w / 2, 20, text=APP_SHORT, fill=WHITE, font=("Segoe UI", 18, "bold"))
        selected_name = self.app.get_selected_app_name()
        footer_text = selected_name if selected_name else "Sin selección"
        self.canvas.create_text(
            self.w / 2, self.h - 6,
            text=footer_text,
            fill=WHITE,
            font=("Segoe UI", 6, "bold"),
        )
        self._draw_local_indicator()

    def _draw_local_indicator(self):
        if MODO_LOCAL:
            self.canvas.create_oval(6, 6, 14, 14, fill=WHITE, outline=WHITE)

    def _place_default(self):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{self.w}x{self.h}+{max(10, sw-self.w-18)}+{max(10, sh-self.h-70)}")

    def _down(self, event):
        self._dragging = False
        self._press_xy = (event.x_root, event.y_root)
        self._origin = (self.winfo_x(), self.winfo_y())

    def _drag(self, event):
        dx = event.x_root - self._press_xy[0]
        dy = event.y_root - self._press_xy[1]
        if abs(dx) + abs(dy) > 4:
            self._dragging = True
        self.geometry(f"+{self._origin[0] + dx}+{self._origin[1] + dy}")

    def _up(self, _event):
        if not self._dragging:
            if self.app.selected_app:
                self.start_loading_sweep()
            else:
                self.app.run_selected_app()

    def start_loading_sweep(self):
        if self._loading:
            return
        self._loading = True
        self._loading_step = -56
        self._animate_loading_sweep()

    def _animate_loading_sweep(self):
        if not self._loading:
            return

        self._draw()

        x = self._loading_step

        # Halo exterior: ancho y muy visible.
        self.canvas.create_polygon(
            x - 28, 2,
            x + 42, 2,
            x + 18, self.h - 2,
            x - 52, self.h - 2,
            fill="#2E9FC8",
            outline="",
        )

        # Segundo halo más claro.
        self.canvas.create_polygon(
            x - 14, 2,
            x + 30, 2,
            x + 8, self.h - 2,
            x - 36, self.h - 2,
            fill="#79D9F5",
            outline="",
        )

        # Núcleo blanco de la luz.
        self.canvas.create_polygon(
            x - 3, 2,
            x + 14, 2,
            x - 6, self.h - 2,
            x - 23, self.h - 2,
            fill="#F4FDFF",
            outline="",
        )

        # Borde de carga para reforzar visualmente el efecto.
        self.canvas.create_rectangle(
            2, 2, self.w - 2, self.h - 2,
            outline="#8DE8FF",
            width=2,
        )

        # Redibujar identidad por encima del barrido.
        self.canvas.create_text(
            self.w / 2, 20,
            text=APP_SHORT,
            fill=WHITE,
            font=("Segoe UI", 18, "bold"),
        )
        selected_name = self.app.get_selected_app_name()
        footer_text = selected_name if selected_name else "Sin selección"
        self.canvas.create_text(
            self.w / 2, self.h - 6,
            text=footer_text,
            fill=WHITE,
            font=("Segoe UI", 6, "bold"),
        )

        self._draw_local_indicator()

        # Forzar el refresco para que cada cuadro sea visible.
        self.canvas.update_idletasks()
        self.update_idletasks()

        self._loading_step += 7
        if self._loading_step <= self.w + 56:
            self.after(38, self._animate_loading_sweep)
        else:
            self._loading = False
            self._draw()
            self.canvas.update_idletasks()
            self.after(90, self.app.run_selected_app)

    def _menu(self, _event):
        self.app.show_app_menu(self.winfo_pointerx(), self.winfo_pointery())


class AMDEVApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} - {APP_SHORT}")
        self.configure(bg=BG)
        self.overrideredirect(True)
        self.attributes("-topmost", True)

        self.base_dir = Path(
            os.environ.get("LOCALAPPDATA", str(Path.home()))
        ) / "ARCHMOBA" / "AMDEV"
        self.cache_dir = self.base_dir / "apps"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.apps_cache = self.base_dir / "apps.json"

        self.geometry(self._default_geometry())
        self.protocol("WM_DELETE_WINDOW", self.hide_main)

        self.apps = []
        self.selected_app = None
        self.running_processes = {}

        # La consola es opcional. AMDEV normalmente corre con pythonw.exe,
        # por lo que se crea únicamente cuando el usuario la solicita.
        self._console_created_by_amdev = False
        self._update_queue = queue.Queue()
        self._update_running = False

        self._build_ui()
        self.load_apps()
        self.after(100, self._poll_update_queue)

        self.floating = FloatingAMDEV(self)
        self.withdraw()
        self.bind("<Escape>", lambda _e: self.hide_app_menu())
        self.after(250, self._keep_amdev_on_top)

    def _keep_amdev_on_top(self):
        """Mantiene AMDEV y su control flotante por encima de las demás ventanas."""
        try:
            self.attributes("-topmost", True)
            if self.state() != "withdrawn":
                self.lift()
        except tk.TclError:
            pass

        try:
            self.floating.attributes("-topmost", True)
            self.floating.lift()
        except (tk.TclError, AttributeError):
            pass

        try:
            self.after(500, self._keep_amdev_on_top)
        except tk.TclError:
            pass

    def _default_geometry(self):
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w = min(720, max(600, int(sw * 0.48)))
        h = min(560, max(430, int(sh * 0.55)))
        x = max(20, (sw - w) // 2)
        y = max(20, (sh - h) // 2)
        return f"{w}x{h}+{x}+{y}"

    def _build_ui(self):
        self.outer = tk.Frame(self, bg=BG, bd=1, relief="solid")
        self.outer.pack(fill="both", expand=True)

        top = tk.Frame(self.outer, bg=BG, height=42)
        top.pack(fill="x", padx=10, pady=(8, 0))
        top.pack_propagate(False)
        top.bind("<Button-1>", self._start_move)
        top.bind("<B1-Motion>", self._move)

        tk.Label(
            top, text=f"{APP_NAME}  |  {APP_SHORT}",
            bg=BG, fg=FG, font=("Segoe UI", 12, "bold")
        ).pack(side="left", padx=6)

        close = tk.Canvas(top, width=30, height=30, bg=BG, highlightthickness=0, bd=0, cursor="hand2")
        close.pack(side="right")
        close.create_line(8, 8, 22, 22, fill=FG, width=2)
        close.create_line(22, 8, 8, 22, fill=FG, width=2)
        close.bind("<Button-1>", lambda _e: self.hide_main())

        body = tk.Frame(self.outer, bg=BG)
        body.pack(fill="both", expand=True, padx=22, pady=18)

        tk.Label(
            body,
            text="Aplicaciones",
            bg=BG, fg=FG,
            font=("Segoe UI", 24, "bold"),
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            body,
            text=(
                "Modo local: ejecuta las aplicaciones desde los archivos del proyecto."
                if MODO_LOCAL else
                "Modo repositorio: descarga y ejecuta las aplicaciones de GitHub."
            ),
            bg=BG, fg=MUTED_FG,
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
            wraplength=620,
        ).pack(fill="x", pady=(4, 14))

        self.status = tk.Label(
            body, text="", bg=BG, fg=MUTED_FG,
            font=("Segoe UI", 8), anchor="w"
        )
        self.status.pack(fill="x", pady=(0, 7))

        self.list_frame = tk.Frame(body, bg=BG)
        self.list_frame.pack(fill="both", expand=True)

        footer = tk.Frame(self.outer, bg=BG, height=34)
        footer.pack(fill="x", padx=12, pady=(0, 8))
        footer.pack_propagate(False)

        tk.Label(
            footer,
            text=f"{APP_SHORT} v{APP_VERSION}\nActualizado: {APP_UPDATE_DATE}  {APP_UPDATE_TIME}",
            bg=BG, fg=MUTED_FG,
            font=("Segoe UI", 7), justify="right"
        ).pack(side="right", padx=4)

        # El clic derecho funciona también sobre el panel principal de AMDEV.
        for widget in (self, self.outer, top, body, footer):
            widget.bind(
                "<Button-3>",
                lambda event: self.show_app_menu(
                    event.x_root,
                    event.y_root,
                ),
            )

    def _start_move(self, event):
        self._move_offset = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def _move(self, event):
        self.geometry(f"+{event.x_root - self._move_offset[0]}+{event.y_root - self._move_offset[1]}")

    def _request_text(self, url, timeout=12):
        request = urllib.request.Request(
            f"{url}{'&' if '?' in url else '?'}v={time.time_ns()}",
            headers={"User-Agent": f"AMDEV/{APP_VERSION}", "Cache-Control": "no-cache"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8-sig")

    def _request_repo_file_main(self, repo_path, timeout=12):
        """Lee HEAD de main: RAW primero y API como respaldo."""
        clean = str(repo_path).strip().replace("\\", "/").lstrip("/")
        if MODO_LOCAL:
            return _local_path(clean).read_text(encoding="utf-8-sig")

        try:
            return self._request_text(
                f"{REPO_RAW_BASE}/{clean}",
                timeout=timeout,
            )
        except Exception:
            pass

        api_url = (
            f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/"
            f"{clean}?ref=main"
        )
        request = urllib.request.Request(
            api_url,
            headers={
                "User-Agent": f"AMDEV/{APP_VERSION}",
                "Accept": "application/vnd.github+json",
                "Cache-Control": "no-cache",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))

        encoded = str(payload.get("content", "")).replace("\n", "")
        return base64.b64decode(encoded).decode("utf-8-sig")

    def load_apps(self):
        for child in self.list_frame.winfo_children():
            child.destroy()

        text = None
        try:
            text = self._request_repo_file_main(APPS_REPO_PATH)
            if not MODO_LOCAL:
                self.apps_cache.write_text(text, encoding="utf-8")
            self.status.configure(text=(
                "Catálogo cargado desde ./AMDEV/apps.json."
                if MODO_LOCAL else "Catálogo actualizado desde GitHub."
            ))
        except Exception as exc:
            if not MODO_LOCAL and self.apps_cache.is_file():
                text = self.apps_cache.read_text(encoding="utf-8-sig")
                self.status.configure(text=f"Usando catálogo local. GitHub no respondió: {exc}")
            else:
                self.status.configure(text=f"No se pudo cargar apps.json: {exc}")
                return

        try:
            payload = json.loads(text)
            self.apps = [
                item for item in payload.get("apps", [])
                if _is_app_active(item)
            ]

            if self.selected_app:
                selected_id = str(self.selected_app.get("id", ""))
                refreshed = next(
                    (
                        item for item in self.apps
                        if str(item.get("id", "")) == selected_id
                    ),
                    None,
                )
                self.selected_app = dict(refreshed) if refreshed else None
                if hasattr(self, "floating") and self.floating.winfo_exists():
                    self.floating._draw()
        except Exception as exc:
            self.status.configure(text=f"apps.json no es válido: {exc}")
            return

        if not self.apps:
            tk.Label(
                self.list_frame, text="No hay aplicaciones disponibles.",
                bg=BG, fg=MUTED_FG, font=("Segoe UI", 10)
            ).pack(anchor="w")
            return

        for item in self.apps:
            self._add_app_card(item)

    def _add_app_card(self, item):
        card = tk.Frame(
            self.list_frame, bg=CARD,
            highlightbackground=BORDER, highlightthickness=1,
            cursor="hand2"
        )
        card.pack(fill="x", pady=4)

        left = tk.Frame(card, bg=CARD)
        left.pack(side="left", fill="both", expand=True, padx=12, pady=10)

        name = tk.Label(
            left, text=item.get("name", item.get("id", "App")),
            bg=CARD, fg=FG, font=("Segoe UI", 11, "bold"),
            anchor="w", cursor="hand2"
        )
        name.pack(fill="x")

        desc = tk.Label(
            left, text=item.get("description", ""),
            bg=CARD, fg=MUTED_FG, font=("Segoe UI", 8),
            anchor="w", cursor="hand2"
        )
        desc.pack(fill="x", pady=(3, 0))

        arrow = tk.Label(
            card, text="›", bg=CARD, fg=RED,
            font=("Segoe UI", 22, "bold"), cursor="hand2"
        )
        arrow.pack(side="right", padx=14)

        for widget in (card, left, name, desc, arrow):
            widget.bind("<Button-1>", lambda _e, app=item: self.launch_app(app))

    def get_selected_app_name(self):
        if not self.selected_app:
            return ""
        return str(
            self.selected_app.get(
                "name",
                self.selected_app.get("id", "")
            )
        ).strip()

    def select_app(self, item):
        """Marca una app como seleccionada sin ejecutarla."""
        self.selected_app = dict(item)
        if hasattr(self, "floating") and self.floating.winfo_exists():
            self.floating._draw()

        name = self.get_selected_app_name() or "App"
        self.status.configure(
            text=f"{name} seleccionada. Clic izquierdo en AMDEV para actualizar y ejecutar."
        )

    @staticmethod
    def _pid_is_alive(pid):
        if not pid or pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
        except Exception:
            return False

    def _find_linux_script_pids(self, script_path):
        """Busca procesos Python que ejecuten exactamente este app.py."""
        if os.name == "nt":
            return []

        try:
            target = str(Path(script_path).resolve())
        except Exception:
            target = str(script_path)

        found = []
        proc_root = Path("/proc")
        if not proc_root.is_dir():
            return found

        current_pid = os.getpid()

        for entry in proc_root.iterdir():
            if not entry.name.isdigit():
                continue

            try:
                pid = int(entry.name)
            except ValueError:
                continue

            if pid <= 1 or pid == current_pid:
                continue

            try:
                raw = (entry / "cmdline").read_bytes()
                if not raw:
                    continue

                args = [
                    part.decode("utf-8", errors="replace")
                    for part in raw.split(b"\0")
                    if part
                ]
            except Exception:
                continue

            matched = False
            for arg in args[1:]:
                try:
                    candidate = str(Path(arg).resolve())
                except Exception:
                    candidate = arg

                if candidate == target:
                    matched = True
                    break

            if matched:
                found.append(pid)

        return found

    def _stop_linux_script_instances(self, local_app):
        """Cierra instancias ocultas que un process.pid antiguo no puede localizar."""
        if os.name == "nt":
            return

        pids = self._find_linux_script_pids(local_app)
        if not pids:
            return

        for pid in pids:
            try:
                os.kill(pid, 15)
            except OSError:
                pass

        deadline = time.time() + 3.0
        while time.time() < deadline:
            alive = [
                pid for pid in pids
                if self._pid_is_alive(pid)
            ]
            if not alive:
                return
            time.sleep(0.08)

        for pid in pids:
            if self._pid_is_alive(pid):
                try:
                    os.kill(pid, 9)
                except OSError:
                    pass

        deadline = time.time() + 1.0
        while time.time() < deadline:
            if not any(self._pid_is_alive(pid) for pid in pids):
                break
            time.sleep(0.05)

    def _stop_cached_app_processes(self, app_id, local_app):
        """Cierra la instancia anterior y espera a que libere recursos."""

        if os.name != "nt":
            self._stop_linux_script_instances(local_app)

        previous = self.running_processes.get(app_id)
        if previous is not None and previous.poll() is None:
            try:
                previous.terminate()
                previous.wait(timeout=2)
            except Exception:
                try:
                    previous.kill()
                except Exception:
                    pass

        pid_file = local_app.parent / "process.pid"
        if pid_file.is_file():
            try:
                old_pid = int(pid_file.read_text(encoding="utf-8").strip())
                if old_pid > 0:
                    if sys.platform == "win32":
                        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                        subprocess.run(
                            ["taskkill", "/PID", str(old_pid), "/T", "/F"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=creationflags,
                            check=False,
                        )
                    else:
                        try:
                            os.kill(old_pid, 15)
                        except OSError:
                            pass

                        # En Linux/MiniLinux PTM usa un bloqueo de instancia
                        # única. Esperar a que el proceso anterior termine evita
                        # que la nueva instancia arranque mientras el puerto sigue
                        # ocupado y se cierre silenciosamente.
                        deadline = time.time() + 3.0
                        while (
                            self._pid_is_alive(old_pid)
                            and time.time() < deadline
                        ):
                            time.sleep(0.08)

                        if self._pid_is_alive(old_pid):
                            try:
                                os.kill(old_pid, 9)
                            except OSError:
                                pass

                            deadline = time.time() + 1.0
                            while (
                                self._pid_is_alive(old_pid)
                                and time.time() < deadline
                            ):
                                time.sleep(0.05)
            except Exception:
                pass

        # Compatibilidad con versiones anteriores de AMDEV que aún no
        # guardaban process.pid. En Windows busca la ruta exacta del app.py.
        if sys.platform == "win32":
            try:
                target = str(local_app.resolve()).replace("'", "''")
                script = (
                    "$target='" + target + "'; "
                    "Get-CimInstance Win32_Process | "
                    "Where-Object { "
                    "($_.Name -like 'python*.exe') -and "
                    "$_.CommandLine -and "
                    "$_.CommandLine.Contains($target) "
                    "} | ForEach-Object { "
                    "Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue "
                    "}"
                )
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                subprocess.run(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags,
                    timeout=5,
                    check=False,
                )
            except Exception:
                pass

        try:
            pid_file.unlink(missing_ok=True)
        except Exception:
            pass

    def run_selected_app(self):
        """Reinicia la app seleccionada, descarga su última versión y la ejecuta."""
        if not self.selected_app:
            return

        item = self.selected_app
        app_id = str(item.get("id", "app")).strip() or "app"
        local_dir = self.cache_dir / app_id
        local_app = local_dir / "app.py"

        if MODO_LOCAL:
            try:
                config = json.loads(self._request_repo_file_main(item["config"]))
                local_app = _local_path(config["app_path"])
            except Exception as exc:
                messagebox.showerror(APP_SHORT, f"No se pudo leer la aplicación local:\n\n{exc}")
                return

        self._stop_cached_app_processes(app_id, local_app)
        self.launch_app(item, force_update=True)

    def launch_app(self, item, force_update=False):
        config_path = str(item.get("config", "")).strip().replace("\\", "/").lstrip("/")
        if not config_path:
            messagebox.showerror(APP_SHORT, "La aplicación no tiene config.json definido.")
            return

        try:
            self.status.configure(text=f"Leyendo {config_path}...")
            self.update_idletasks()

            config_text = self._request_repo_file_main(config_path)
            config = json.loads(config_text)

            if config.get("maintenance", False):
                messagebox.showinfo(APP_SHORT, f"{config.get('name', item.get('name', 'La aplicación'))} está en mantenimiento.")
                return

            app_path = str(config.get("app_path", "")).strip().replace("\\", "/").lstrip("/")
            if not app_path:
                raise ValueError("El config.json no contiene app_path.")

            app_id = str(item.get("id", "app")).strip() or "app"
            if MODO_LOCAL:
                local_app = _local_path(app_path)
                if not local_app.is_file():
                    raise FileNotFoundError(f"No existe la aplicación local: {local_app}")
                local_dir = local_app.parent
            else:
                local_dir = self.cache_dir / app_id
                local_dir.mkdir(parents=True, exist_ok=True)
                local_app = local_dir / "app.py"

                self.status.configure(text=f"Descargando {app_path}...")
                self.update_idletasks()

                release_commit = str(config.get("release_commit", "")).strip()
                if not re.fullmatch(r"[0-9a-fA-F]{40}", release_commit):
                    raise RuntimeError(
                        "El config.json no contiene un release_commit válido."
                    )

                immutable_app_url = f"{REPO_RAW_ROOT}/{release_commit}/{app_path}"

                source = None
                last_error = None
                for attempt in range(4):
                    try:
                        source = self._request_text(immutable_app_url, timeout=20)
                        break
                    except Exception as exc:
                        last_error = exc
                        self.status.configure(
                            text=f"Esperando release confirmado... intento {attempt + 1}/4"
                        )
                        self.update_idletasks()
                        if attempt < 3:
                            time.sleep(0.8)

                if source is None:
                    raise RuntimeError(
                        f"No se pudo descargar el release confirmado: {last_error}"
                    )

                compile(source, app_path, "exec")

                expected_version = str(config.get("version", "")).strip()
                version_match = re.search(
                    r'''APP_VERSION\s*=\s*["']([^"']+)["']''',
                    source,
                )
                downloaded_version = version_match.group(1).strip() if version_match else ""

                if expected_version:
                    if not downloaded_version:
                        raise RuntimeError(
                            f"El app.py descargado no declara APP_VERSION; se esperaba v{expected_version}."
                        )
                    if downloaded_version != expected_version:
                        raise RuntimeError(
                            "Versión inconsistente: "
                            f"config.json indica v{expected_version}, "
                            f"pero app.py contiene v{downloaded_version}."
                        )

                temp = local_app.with_suffix(".py.tmp")
                temp.write_text(source, encoding="utf-8")
                try:
                    local_app.unlink(missing_ok=True)
                except Exception:
                    pass
                temp.replace(local_app)

                local_config = local_dir / "config.json"
                local_config.write_text(config_text, encoding="utf-8")

            self.status.configure(
                text=f"Ejecutando {config.get('name', item.get('name', app_id))} v{config.get('version', '')}..."
            )
            log_handle = None
            launch_log = local_dir / "launch.log"
            child_env = os.environ.copy()
            child_env["AMDEV_MODE"] = "local" if MODO_LOCAL else "repo"
            child_env["AMDEV_LOCAL_ROOT"] = str(LOCAL_ROOT)
            popen_kwargs = {
                "cwd": str(local_dir),
                "env": child_env,
            }

            if os.name != "nt":
                # Conservar el error real de arranque en MiniLinux/Linux.
                log_handle = open(
                    launch_log,
                    "w",
                    encoding="utf-8",
                    buffering=1,
                )
                popen_kwargs["stdout"] = log_handle
                popen_kwargs["stderr"] = subprocess.STDOUT

            process = subprocess.Popen(
                [_windowless_python(), str(local_app)],
                **popen_kwargs,
            )
            self.running_processes[app_id] = process

            try:
                (local_dir / "process.pid").write_text(
                    str(process.pid),
                    encoding="utf-8",
                )
            except Exception:
                pass

            app_name = config.get("name", item.get("name", app_id))
            app_version = config.get("version", "")

            self.status.configure(
                text=f"Iniciando {app_name} v{app_version}..."
            )

            def verify_started():
                try:
                    return_code = process.poll()
                except Exception:
                    return_code = None

                if return_code is None:
                    self.status.configure(
                        text=(
                            f"{app_name} iniciada · v{app_version}"
                            if not force_update
                            else f"{app_name} actualizada e iniciada · v{app_version}"
                        )
                    )
                    if log_handle is not None:
                        try:
                            log_handle.flush()
                            log_handle.close()
                        except Exception:
                            pass
                    return

                details = ""
                if log_handle is not None:
                    try:
                        log_handle.flush()
                        log_handle.close()
                    except Exception:
                        pass

                try:
                    if launch_log.is_file():
                        details = launch_log.read_text(
                            encoding="utf-8",
                            errors="replace",
                        ).strip()
                except Exception:
                    details = ""

                if not details:
                    details = (
                        f"El proceso terminó inmediatamente "
                        f"(código {return_code})."
                    )

                self.status.configure(
                    text=f"{app_name} no pudo iniciar."
                )
                messagebox.showerror(
                    APP_SHORT,
                    (
                        f"{app_name} no pudo iniciar en Linux/MiniLinux.\n\n"
                        f"{details[-3500:]}"
                    ),
                    parent=self,
                )

            self.after(1200, verify_started)
        except Exception as exc:
            messagebox.showerror(APP_SHORT, f"No se pudo iniciar la aplicación:\n\n{exc}")
            self.status.configure(text=f"Error: {exc}")

    # ---------- Actualizacion manual ----------
    def update_amdev_now(self):
        """Busca la version publicada y delega el reemplazo a un updater."""
        if self._update_running:
            self.status.configure(
                text="Ya se esta comprobando una actualizacion..."
            )
            return

        self._update_running = True
        origin = "archivos locales" if MODO_LOCAL else "GitHub"
        self.status.configure(text=f"Buscando actualizacion de AMDEV en {origin}...")

        def worker():
            try:
                config, source = _fetch_self_release()
                remote_version = str(
                    config.get("version", "")
                ).strip()

                if (
                    _version_tuple(remote_version)
                    <= _version_tuple(APP_VERSION)
                ):
                    self._update_queue.put(
                        (
                            "info",
                            f"AMDEV ya esta actualizado · v{APP_VERSION}",
                        )
                    )
                    return

                self._update_queue.put(
                    (
                        "status",
                        f"Instalando AMDEV v{remote_version}...",
                    )
                )

                _launch_update_helper(source)
                self._update_queue.put(
                    (
                        "restart",
                        remote_version,
                    )
                )

            except Exception as exc:
                self._update_queue.put(
                    (
                        "error",
                        f"No se pudo actualizar AMDEV:\n\n{exc}",
                    )
                )

        threading.Thread(target=worker, daemon=True).start()

    def _poll_update_queue(self):
        try:
            while True:
                event = self._update_queue.get_nowait()
                kind = event[0]

                if kind == "status":
                    self.status.configure(text=event[1])

                elif kind == "info":
                    self._update_running = False
                    self.status.configure(text=event[1])
                    messagebox.showinfo(
                        APP_SHORT,
                        event[1],
                        parent=self,
                    )

                elif kind == "error":
                    self._update_running = False
                    self.status.configure(text="Error al actualizar AMDEV")
                    messagebox.showerror(
                        APP_SHORT,
                        event[1],
                        parent=self,
                    )

                elif kind == "restart":
                    version = event[1]
                    self.status.configure(
                        text=f"Actualizando a AMDEV v{version}..."
                    )
                    self.after(250, self.exit_app)

        except queue.Empty:
            pass

        try:
            self.after(100, self._poll_update_queue)
        except tk.TclError:
            pass

    # ---------- Consola opcional ----------
    def _console_hwnd(self):
        if os.name != "nt":
            return 0
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.GetConsoleWindow.restype = ctypes.c_void_p
            return int(kernel32.GetConsoleWindow() or 0)
        except Exception:
            return 0

    def _console_is_visible(self):
        hwnd = self._console_hwnd()
        if not hwnd or os.name != "nt":
            return False
        try:
            user32 = ctypes.windll.user32
            user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
            user32.IsWindowVisible.restype = ctypes.c_int
            return bool(user32.IsWindowVisible(hwnd))
        except Exception:
            return False

    def _redirect_console_streams(self):
        """Conecta stdout/stderr/stdin a la consola creada desde pythonw.exe."""
        if os.name != "nt":
            return

        try:
            sys.stdout = open(
                "CONOUT$",
                "w",
                encoding="utf-8",
                buffering=1,
            )
        except Exception:
            pass

        try:
            sys.stderr = open(
                "CONOUT$",
                "w",
                encoding="utf-8",
                buffering=1,
            )
        except Exception:
            pass

        try:
            sys.stdin = open(
                "CONIN$",
                "r",
                encoding="utf-8",
            )
        except Exception:
            pass

    def show_console(self):
        if os.name != "nt":
            self.status.configure(
                text="La consola visible está disponible únicamente en Windows."
            )
            return

        hwnd = self._console_hwnd()

        if not hwnd:
            try:
                kernel32 = ctypes.windll.kernel32
                kernel32.AllocConsole.restype = ctypes.c_int

                if not kernel32.AllocConsole():
                    self.status.configure(text="No se pudo crear la consola.")
                    return

                self._console_created_by_amdev = True
                kernel32.SetConsoleTitleW(
                    ctypes.c_wchar_p(f"{APP_NAME} · Consola")
                )
                self._redirect_console_streams()
                hwnd = self._console_hwnd()

                try:
                    print(
                        f"{APP_NAME} ({APP_SHORT}) v{APP_VERSION}",
                        flush=True,
                    )
                    print(
                        "Consola de AMDEV activa. Puedes ocultarla desde "
                        "el menú de clic derecho.",
                        flush=True,
                    )
                    print("-" * 58, flush=True)
                except Exception:
                    pass
            except Exception as exc:
                self.status.configure(
                    text=f"No se pudo crear la consola: {exc}"
                )
                return

        if hwnd:
            try:
                user32 = ctypes.windll.user32
                user32.ShowWindow.argtypes = [
                    ctypes.c_void_p,
                    ctypes.c_int,
                ]
                user32.ShowWindow.restype = ctypes.c_int
                user32.ShowWindow(
                    ctypes.c_void_p(hwnd),
                    5,
                )
                self.status.configure(text="Consola visible.")
            except Exception as exc:
                self.status.configure(
                    text=f"No se pudo mostrar la consola: {exc}"
                )

    def hide_console(self):
        hwnd = self._console_hwnd()
        if not hwnd or os.name != "nt":
            return

        try:
            user32 = ctypes.windll.user32
            user32.ShowWindow.argtypes = [
                ctypes.c_void_p,
                ctypes.c_int,
            ]
            user32.ShowWindow.restype = ctypes.c_int
            user32.ShowWindow(
                ctypes.c_void_p(hwnd),
                0,
            )
            self.status.configure(text="Consola oculta.")
        except Exception as exc:
            self.status.configure(
                text=f"No se pudo ocultar la consola: {exc}"
            )

    def toggle_console(self):
        if self._console_is_visible():
            self.hide_console()
        else:
            self.show_console()

    def show_app_menu(self, x=None, y=None):
        """Muestra una lista pequeña nativa, igual a un menú de clic derecho."""
        self.load_apps()

        menu = tk.Menu(
            self,
            tearoff=0,
            bg=BG,
            fg=FG,
            activebackground=TEAL,
            activeforeground=WHITE,
            bd=1,
            relief="solid",
        )

        if not self.apps:
            menu.add_command(label="No hay aplicaciones disponibles", state="disabled")
        else:
            selected_id = (
                str(self.selected_app.get("id", ""))
                if self.selected_app else ""
            )
            for item in self.apps:
                item_id = str(item.get("id", ""))
                name = item.get("name", item_id or "App")
                prefix = "✓ " if item_id and item_id == selected_id else "   "
                menu.add_command(
                    label=f"{prefix}{name}",
                    command=lambda app_item=item: self.select_app(app_item),
                )

        menu.add_separator()
        menu.add_command(label="Recargar aplicaciones", command=self.load_apps)
        menu.add_command(label="Actualizar AMDEV", command=self.update_amdev_now)
        menu.add_command(label="Abrir AMDEV", command=self.show_main)

        console_label = (
            "Ocultar consola"
            if self._console_is_visible()
            else "Ver consola"
        )
        menu.add_command(
            label=console_label,
            command=self.toggle_console,
        )

        menu.add_separator()
        menu.add_command(label="Salir", command=self.exit_app)

        if x is None or y is None:
            x = self.floating.winfo_rootx()
            y = self.floating.winfo_rooty()

        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def hide_app_menu(self):
        # Se mantiene por compatibilidad con llamadas existentes.
        pass

    def toggle_main(self):
        if self.state() == "withdrawn":
            self.show_main()
        else:
            self.hide_main()

    def show_main(self):
        self.hide_app_menu()
        self.deiconify()
        self.attributes("-topmost", True)
        self.lift()
        try:
            self.floating.attributes("-topmost", True)
            self.floating.lift()
        except tk.TclError:
            pass
        self.load_apps()

    def hide_main(self):
        self.withdraw()

    def exit_app(self):
        try:
            self.floating.destroy()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    if _ensure_windowless_amdev():
        raise SystemExit(0)

    if check_self_update():
        raise SystemExit(0)

    app = AMDEVApp()
    app.mainloop()
