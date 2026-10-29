import base64
import json
import os
import re
import subprocess
import sys
import time
import tkinter as tk
import urllib.request
from pathlib import Path

APP_NAME = "PYRION OS"
APP_VERSION = "0.1.3"

REPO_OWNER = "mobatfb"
REPO_NAME = "archmoba-config"
REPO_RAW_ROOT = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}"
REPO_RAW_BASE = f"{REPO_RAW_ROOT}/main/PYRION"
SELF_CONFIG_URL = f"{REPO_RAW_BASE}/config.json"
SELF_CONFIG_API_URL = (
    f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/PYRION/config.json?ref=main"
)


def _version_tuple(value):
    parts = []
    for part in str(value).strip().split("."):
        match = re.match(r"(\d+)", part)
        parts.append(int(match.group(1)) if match else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def check_self_update(restart=True):
    """Busca una versión nueva de PYRION y reemplaza app.py de forma segura."""
    try:
        remote_config = None

        try:
            api_request = urllib.request.Request(
                SELF_CONFIG_API_URL,
                headers={
                    "User-Agent": f"PYRION/{APP_VERSION}",
                    "Accept": "application/vnd.github+json",
                    "Cache-Control": "no-cache",
                },
            )
            with urllib.request.urlopen(api_request, timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
            encoded = str(payload.get("content", "")).replace("\n", "")
            remote_config = json.loads(
                base64.b64decode(encoded).decode("utf-8-sig")
            )
        except Exception:
            remote_config = None

        if remote_config is None:
            config_request = urllib.request.Request(
                f"{SELF_CONFIG_URL}?v={time.time_ns()}",
                headers={
                    "User-Agent": f"PYRION/{APP_VERSION}",
                    "Cache-Control": "no-cache",
                },
            )
            with urllib.request.urlopen(config_request, timeout=8) as response:
                remote_config = json.loads(response.read().decode("utf-8-sig"))

        remote_version = str(remote_config.get("version", "")).strip()
        if not remote_version:
            return False

        if _version_tuple(remote_version) <= _version_tuple(APP_VERSION):
            return False

        app_path = str(
            remote_config.get("app_path", "PYRION/app.py")
        ).strip().replace("\\", "/").lstrip("/")

        if (Path(app_path).name or "app.py").lower() != "app.py":
            raise RuntimeError("config.json no apunta a un app.py válido.")

        release_commit = str(remote_config.get("release_commit", "")).strip()
        if not re.fullmatch(r"[0-9a-fA-F]{40}", release_commit):
            raise RuntimeError("config.json no contiene un release_commit válido.")

        immutable_app_url = f"{REPO_RAW_ROOT}/{release_commit}/{app_path}"

        source = None
        last_error = None
        for attempt in range(4):
            try:
                app_request = urllib.request.Request(
                    f"{immutable_app_url}?v={time.time_ns()}",
                    headers={
                        "User-Agent": f"PYRION/{APP_VERSION}",
                        "Cache-Control": "no-cache",
                    },
                )
                with urllib.request.urlopen(app_request, timeout=15) as response:
                    source = response.read().decode("utf-8-sig")
                break
            except Exception as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(0.8)

        if source is None:
            raise RuntimeError(
                f"No se pudo descargar el release fijado: {last_error}"
            )

        version_match = re.search(
            r'''APP_VERSION\s*=\s*["']([^"']+)["']''',
            source,
        )
        downloaded_version = (
            version_match.group(1).strip() if version_match else ""
        )

        if downloaded_version != remote_version:
            raise RuntimeError(
                "Versión remota inconsistente: "
                f"config={remote_version}, "
                f"app.py={downloaded_version or 'sin versión'}"
            )

        compile(source, "PYRION/app.py", "exec")

        current_file = Path(__file__).resolve()
        temp_file = current_file.with_suffix(current_file.suffix + ".update")
        temp_file.write_text(source, encoding="utf-8")
        os.replace(temp_file, current_file)

        if restart:
            if os.name == "nt":
                subprocess.Popen(
                    [sys.executable, str(current_file), *sys.argv[1:]],
                    cwd=str(current_file.parent),
                )
                return True

            os.execv(
                sys.executable,
                [sys.executable, str(current_file), *sys.argv[1:]],
            )
            return False

        return True
    except Exception:
        return False


class PyrionApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.configure(bg="#101218")

        self.attributes("-fullscreen", True)

        tk.Label(
            self,
            text="PYRION OS",
            bg="#101218",
            fg="#FFFFFF",
            font=("Segoe UI", 28, "bold"),
        ).pack(expand=True)


if __name__ == "__main__":
    if check_self_update():
        raise SystemExit(0)

    app = PyrionApp()
    app.mainloop()
