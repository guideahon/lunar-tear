#!/usr/bin/env python3
"""
Lunar Tear — NieR Re[in]carnation Private Server Manager
Self-contained GUI app. Requires only Python 3.x standard library.
"""

import glob
import json
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import ctypes
import time
import urllib.request
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from dashboard_server import DASHBOARD_PORT, LogBuffer, start_dashboard_server

# ─── Paths ─────────────────────────────────────────────────────────────────────
ROOT            = Path(__file__).resolve().parent.parent
SERVER_DIR      = ROOT / "server"
SERVER_EXE      = SERVER_DIR / "lunar-tear.exe"
CDN_EXE         = SERVER_DIR / "octo-cdn.exe"
AUTH_EXE        = SERVER_DIR / "auth-server.exe"
CLIENT_DIR      = ROOT / "client"
TOOLS_DIR       = ROOT / "tools"
PATCH_SCRIPT    = CLIENT_DIR / "patch_apk.py"
APKTOOL_JAR     = TOOLS_DIR / "apktool.jar"
ORIGINAL_APK    = CLIENT_DIR / "3.7.1.apk"
PATCHED_DIR     = CLIENT_DIR / "patched"
METADATA_PATH   = PATCHED_DIR / "assets/bin/Data/Managed/Metadata/global-metadata.dat"
METADATA_BACKUP = PATCHED_DIR / "assets/bin/Data/Managed/Metadata/global-metadata.dat.orig"
UNSIGNED_APK    = CLIENT_DIR / "patched_unsigned.apk"
ALIGNED_APK     = CLIENT_DIR / "patched_aligned.apk"
SIGNED_APK      = CLIENT_DIR / "patched_signed.apk"
CONFIG_PATH     = Path(__file__).resolve().parent / "config.json"
DEBUG_KEYSTORE  = Path.home() / ".android" / "debug.keystore"
SHORTCUT_PATH   = Path.home() / "Desktop" / "NieR Lunar Tear Server.lnk"

# ─── Lunar Base ────────────────────────────────────────────────────────────────
LUNAR_BASE_DIR   = ROOT.parent / "lunar-base"
LUNAR_BASE_VENV  = LUNAR_BASE_DIR / ".venv" / "Scripts" / "python.exe"
WEBVIEW_LAUNCHER = Path(__file__).resolve().parent / "webview_launcher.py"
LUNAR_BASE_PORT  = 8888


def _pythonw_executable() -> str:
    """Prefer pythonw on Windows to avoid transient console windows."""
    if sys.platform != "win32":
        return sys.executable
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        return str(exe)
    pyw = exe.with_name("pythonw.exe")
    return str(pyw) if pyw.exists() else sys.executable

# ─── Theme ─────────────────────────────────────────────────────────────────────
BG      = "#14141a"
BG2     = "#1e1e28"
BG3     = "#282832"
BG4     = "#323240"
ACCENT  = "#c8b88a"
ACCENT2 = "#8a7a5a"
FG      = "#e0d8d0"
FG2     = "#908880"
FG3     = "#605850"
GREEN   = "#56a056"
RED     = "#b84848"
YELLOW  = "#b89030"
FONT    = ("Segoe UI", 9)
FONT_M  = ("Segoe UI", 10)
FONT_B  = ("Segoe UI", 10, "bold")
FONT_H  = ("Segoe UI", 13, "bold")
MONO    = ("Consolas", 9)


# ─── Tool Auto-Detection ───────────────────────────────────────────────────────
def _find_java():
    try:
        r = subprocess.run(
            ["java", "-version"],
            capture_output=True,
            timeout=3,
            creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0),
        )
        if r.returncode == 0:
            return "java"
    except Exception:
        pass
    for pattern in [
        r"C:\Program Files\Java\*\bin\java.exe",
        r"C:\Program Files\Eclipse Adoptium\*\bin\java.exe",
        r"C:\Program Files\Microsoft\jdk-*\bin\java.exe",
        r"C:\Program Files\OpenJDK\*\bin\java.exe",
    ]:
        matches = glob.glob(pattern)
        if matches:
            return sorted(matches)[-1]
    return ""


def _find_adb():
    winget = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
    if winget.exists():
        for p in winget.rglob("adb.exe"):
            return str(p)
    sdk = Path.home() / "AppData/Local/Android/Sdk/platform-tools/adb.exe"
    if sdk.exists():
        return str(sdk)
    try:
        r = subprocess.run(
            ["adb", "version"],
            capture_output=True,
            timeout=3,
            creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0),
        )
        if r.returncode == 0:
            return "adb"
    except Exception:
        pass
    return ""


def _find_sdk_tool(name):
    sdk_bt = Path.home() / "AppData/Local/Android/Sdk/build-tools"
    if sdk_bt.exists():
        versions = sorted(sdk_bt.iterdir(), key=lambda p: p.name, reverse=True)
        for v in versions:
            t = v / name
            if t.exists():
                return str(t)
    return ""


def auto_detect_tools():
    return {
        "java":      _find_java(),
        "adb":       _find_adb(),
        "zipalign":  _find_sdk_tool("zipalign.exe"),
        "apksigner": _find_sdk_tool("apksigner.bat"),
        "keystore":  str(DEBUG_KEYSTORE) if DEBUG_KEYSTORE.exists() else "",
        "python":    sys.executable,
    }


# ─── Config ────────────────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "host":      "192.168.1.36",
    "http_port": 8080,
    "grpc_port": 8003,
    "tools":     {},
}


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    detected = auto_detect_tools()
    tools = cfg.setdefault("tools", {})
    for k, v in detected.items():
        if not tools.get(k):
            tools[k] = v
    return cfg


def save_config(cfg: dict):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


# ─── Port Cleanup ──────────────────────────────────────────────────────────────
def _kill_ports(*ports: int):
    """Kill any process listening on the given ports before server start."""
    for port in ports:
        try:
            r = subprocess.run(
                ["powershell", "-Command",
                 f"Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue"
                 f" | Select-Object -ExpandProperty OwningProcess"],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for line in r.stdout.strip().splitlines():
                pid = line.strip()
                if pid.isdigit():
                    subprocess.run(
                        ["powershell", "-Command", f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue"],
                        capture_output=True, timeout=5,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
        except Exception:
            pass


# ─── Server Process Manager ────────────────────────────────────────────────────
class ServerProcess:
    def __init__(self, log_cb, stopped_cb):
        self._procs: dict = {}
        self._log_cb = log_cb
        self._stopped_cb = stopped_cb

    # Keep old signature for compat; http_port == cdn_port
    def start(self, host: str, http_port: int, grpc_port: int, auth_port: int = 3000) -> bool:
        if self.is_running():
            return False
        if not SERVER_EXE.exists():
            return False
        _kill_ports(http_port, grpc_port, auth_port)

        services = []
        if AUTH_EXE.exists():
            services.append(("auth", [
                str(AUTH_EXE),
                "--listen", f"0.0.0.0:{auth_port}",
                "--db",     "db/auth.db",
            ]))
        if CDN_EXE.exists():
            services.append(("cdn", [
                str(CDN_EXE),
                "--listen",      f"0.0.0.0:{http_port}",
                "--public-addr", f"{host}:{http_port}",
                "--assets-dir",  ".",
            ]))
        services.append(("grpc", [
            str(SERVER_EXE),
            "--listen",      f"0.0.0.0:{grpc_port}",
            "--public-addr", f"{host}:{grpc_port}",
            "--db",          "db/game.db",
            "--octo-url",    f"http://{host}:{http_port}",
            "--auth-url",    f"http://localhost:{auth_port}",
        ]))

        for label, cmd in services:
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(SERVER_DIR),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True, bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                self._procs[label] = proc
                threading.Thread(
                    target=self._read_output, args=(label, proc), daemon=True
                ).start()
            except Exception as e:
                self._log_cb(f"[{label}] ✗ No se pudo iniciar: {e}")

        return bool(self._procs)

    def stop(self):
        for label, proc in list(self._procs.items()):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        self._procs.clear()

    def is_running(self) -> bool:
        return any(p.poll() is None for p in self._procs.values())

    def _read_output(self, label: str, proc):
        prefix = f"[{label}] "
        try:
            for line in proc.stdout:
                self._log_cb(prefix + line.rstrip())
        except Exception:
            pass
        if not self.is_running():
            self._stopped_cb()


# ─── Lunar Base Process ────────────────────────────────────────────────────────
class LunarBaseProcess:
    def __init__(self, log_cb, ready_cb, stopped_cb):
        self._proc         = None
        self._webview_proc = None
        self._log_cb       = log_cb
        self._ready_cb     = ready_cb
        self._stopped_cb   = stopped_cb

    def start(self, port: int = LUNAR_BASE_PORT, quiet: bool = False) -> bool:
        if self.is_running():
            return False
        if not LUNAR_BASE_DIR.is_dir():
            self._log_cb(f"[lunar-base] ✗ directorio no encontrado: {LUNAR_BASE_DIR}")
            return False
        if LUNAR_BASE_VENV.exists():
            pyw = LUNAR_BASE_VENV.with_name("pythonw.exe")
            python = str(pyw if pyw.exists() else LUNAR_BASE_VENV)
        else:
            python = _pythonw_executable()
        cmd = [python, "-m", "uvicorn", "web.app:app",
               "--host", "127.0.0.1", "--port", str(port)]
        try:
            popen_kwargs = {}
            if sys.platform == "win32":
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = subprocess.SW_HIDE
                popen_kwargs["startupinfo"] = si
                popen_kwargs["creationflags"] = (
                    subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
                )

            out = subprocess.DEVNULL if quiet else subprocess.PIPE
            self._proc = subprocess.Popen(
                cmd,
                cwd=str(LUNAR_BASE_DIR),
                stdout=out,
                stderr=(subprocess.DEVNULL if quiet else subprocess.STDOUT),
                text=(not quiet),
                bufsize=(1 if not quiet else 0),
                **popen_kwargs,
            )
            if quiet:
                threading.Thread(target=self._wait_ready, args=(port,), daemon=True).start()
            else:
                threading.Thread(
                    target=self._reader, args=(self._proc, port), daemon=True
                ).start()
            return True
        except Exception as e:
            self._log_cb(f"[lunar-base] ✗ {e}")
            return False

    def open_webview(self, port: int = LUNAR_BASE_PORT):
        if self._webview_proc and self._webview_proc.poll() is None:
            return
        self._webview_proc = subprocess.Popen(
            [_pythonw_executable(), str(WEBVIEW_LAUNCHER), str(port)],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    def stop(self):
        if self._webview_proc and self._webview_proc.poll() is None:
            self._webview_proc.terminate()
        self._webview_proc = None
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _reader(self, proc, port):
        ready_fired = False
        try:
            for line in proc.stdout:
                self._log_cb(line.rstrip())
                if not ready_fired and "Application startup complete" in line:
                    ready_fired = True
                    self._ready_cb(port)
        except Exception:
            pass
        self._stopped_cb()

    def _wait_ready(self, port: int):
        url = f"http://127.0.0.1:{port}/"
        for _ in range(40):
            if self._proc is None or self._proc.poll() is not None:
                self._stopped_cb()
                return
            try:
                urllib.request.urlopen(url, timeout=0.5)
                self._ready_cb(port)
                return
            except Exception:
                time.sleep(0.25)
        if self._proc is None or self._proc.poll() is not None:
            self._stopped_cb()


# ─── APK Pipeline ──────────────────────────────────────────────────────────────
class APKPipeline:
    def __init__(self, cfg: dict, log_cb, done_cb):
        self.cfg = cfg
        self._log = log_cb
        self._done = done_cb

    # Public entry points ──────────────────────────────────────────────────────
    def run_all(self):
        threading.Thread(target=self._all_steps, daemon=True).start()

    def run_install_only(self):
        threading.Thread(target=self._install_step, daemon=True).start()

    def run_patch_metadata_only(self):
        threading.Thread(target=self._patch_metadata_step, daemon=True).start()

    # Step sequences ───────────────────────────────────────────────────────────
    def _all_steps(self):
        steps = [
            ("Restaurando metadata original",      self._restore_metadata),
            ("Parcheando metadata (IL2CPP)",        self._patch_metadata),
            ("Compilando APK (apktool)",            self._build_apk),
            ("Alineando APK (zipalign)",            self._align_apk),
            ("Firmando APK (apksigner)",            self._sign_apk),
            ("Instalando en dispositivo (adb)",     self._install_adb),
        ]
        for label, fn in steps:
            self._log(f"\n▶  {label}...")
            ok, err = fn()
            if ok:
                self._log("   ✓ OK")
            else:
                self._log(f"   ✗ FALLÓ: {err}")
                self._done(False)
                return
        self._done(True)

    def _install_step(self):
        self._log("\n▶  Instalando APK en dispositivo (adb)...")
        ok, err = self._install_adb()
        if ok:
            self._log("   ✓ Instalado exitosamente.")
        else:
            self._log(f"   ✗ {err}")
        self._done(ok)

    def _patch_metadata_step(self):
        for label, fn in [
            ("Restaurando metadata original", self._restore_metadata),
            ("Parcheando metadata (IL2CPP)",  self._patch_metadata),
        ]:
            self._log(f"\n▶  {label}...")
            ok, err = fn()
            if ok:
                self._log("   ✓ OK")
            else:
                self._log(f"   ✗ {err}")
                self._done(False)
                return
        self._log("\n✓ Metadata parcheada. Usá el botón completo para rebuild+sign+install.")
        self._done(True)

    # Individual steps ─────────────────────────────────────────────────────────
    def _restore_metadata(self):
        if not METADATA_BACKUP.exists():
            return False, f"Backup no encontrado: {METADATA_BACKUP}"
        shutil.copy2(METADATA_BACKUP, METADATA_PATH)
        return True, ""

    def _patch_metadata(self):
        python = self.cfg["tools"].get("python") or sys.executable
        cmd = [
            python, str(PATCH_SCRIPT),
            "--host",      self.cfg["host"],
            "--http-port", str(self.cfg.get("cdn_port", self.cfg.get("http_port", 8080))),
            "--grpc-port", str(self.cfg["grpc_port"]),
            "--metadata",  str(METADATA_PATH),
        ]
        return self._run(cmd, cwd=str(CLIENT_DIR))

    def _build_apk(self):
        java = self.cfg["tools"].get("java") or "java"
        cmd = [java, "-jar", str(APKTOOL_JAR), "b",
               str(PATCHED_DIR), "-o", str(UNSIGNED_APK)]
        return self._run(cmd, cwd=str(CLIENT_DIR))

    def _align_apk(self):
        zipalign = self.cfg["tools"].get("zipalign", "")
        if not zipalign or not Path(zipalign).exists():
            return False, "zipalign no encontrado — configurá Tools"
        cmd = [zipalign, "-p", "-f", "4", str(UNSIGNED_APK), str(ALIGNED_APK)]
        return self._run(cmd)

    def _sign_apk(self):
        apksigner = self.cfg["tools"].get("apksigner", "")
        keystore  = self.cfg["tools"].get("keystore", "")
        if not apksigner or not Path(apksigner).exists():
            return False, "apksigner no encontrado — configurá Tools"
        if not keystore or not Path(keystore).exists():
            return False, "keystore no encontrado — configurá Tools"
        cmd = [
            apksigner, "sign",
            "--ks",           keystore,
            "--ks-key-alias", "androiddebugkey",
            "--ks-pass",      "pass:android",
            "--key-pass",     "pass:android",
            "--out",          str(SIGNED_APK),
            str(ALIGNED_APK),
        ]
        return self._run(cmd)

    def _install_adb(self):
        adb = self.cfg["tools"].get("adb", "")
        if not adb or not Path(adb).exists():
            return False, "adb no encontrado — conectá el dispositivo y configurá Tools"
        cmd = [adb, "install", "-r", str(SIGNED_APK)]
        return self._run(cmd)

    def _run(self, cmd, cwd=None):
        try:
            proc = subprocess.run(
                cmd, cwd=cwd,
                capture_output=True, text=True,
                timeout=300,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            out = (proc.stdout + "\n" + proc.stderr).strip()
            for line in out.splitlines():
                line = line.strip()
                if line:
                    self._log(f"   {line}")
            if proc.returncode != 0:
                return False, f"exit code {proc.returncode}"
            return True, ""
        except FileNotFoundError:
            return False, f"No se encontró el ejecutable: {cmd[0]}"
        except subprocess.TimeoutExpired:
            return False, "Timeout (>5 min)"
        except Exception as e:
            return False, str(e)


# ─── ADB Device Detection ──────────────────────────────────────────────────────
def get_adb_device(adb_path: str) -> str | None:
    if not adb_path:
        return None
    try:
        r = subprocess.run(
            [adb_path, "devices"],
            capture_output=True, text=True, timeout=3,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for line in r.stdout.strip().splitlines()[1:]:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "device":
                return parts[0]
    except Exception:
        pass
    return None


# ─── Helpers ───────────────────────────────────────────────────────────────────
def _file_mb(p: Path) -> str:
    return f"{p.stat().st_size // (1024 * 1024)} MB" if p.exists() else "—"


def _update_shortcut(cfg: dict):
    if not SHORTCUT_PATH.exists():
        return
    cdn_port  = cfg.get("cdn_port", cfg.get("http_port", 8080))
    grpc_port = cfg["grpc_port"]
    host      = cfg["host"]
    args = (
        f'/k "cd /d {SERVER_DIR} && '
        f'start /B auth-server.exe --listen 0.0.0.0:3000 --db db/auth.db && '
        f'start /B octo-cdn.exe --listen 0.0.0.0:{cdn_port} --public-addr {host}:{cdn_port} && '
        f'lunar-tear.exe --listen 0.0.0.0:{grpc_port} --public-addr {host}:{grpc_port} '
        f'--db db/game.db --octo-url http://{host}:{cdn_port} --auth-url http://localhost:3000"'
    )
    ps = (
        f'$s=(New-Object -ComObject WScript.Shell).CreateShortcut("{SHORTCUT_PATH}");'
        f'$s.Arguments=\'{args}\';$s.Save()'
    )
    try:
        subprocess.run(
            ["powershell", "-Command", ps],
            capture_output=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception:
        pass


# ─── Main Window ───────────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        # Hide immediately to avoid any startup flash of the Tk root window.
        self.withdraw()
        if sys.platform == "win32":
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "walter-sparrow.lunar-tear.manager"
                )
            except Exception:
                pass
        self.cfg = load_config()
        self._server_log_buf = LogBuffer()
        self._lb_log_buf     = LogBuffer()
        self._server = ServerProcess(
            log_cb=self._server_log,
            stopped_cb=self._on_server_stopped,
        )
        self._apk_busy = False
        self._poll_tick = 0
        self._dashboard_webview_proc = None

        self.title("Lunar Tear — NieR Re[in]carnation Manager")
        self.geometry("960x700")
        self.minsize(820, 580)
        self.configure(bg=BG)
        self.resizable(True, True)
        _ico = ROOT / "lunar-tear.ico"
        if _ico.exists():
            self.iconbitmap(str(_ico))

        self._apply_styles()
        self._build_header()
        self._build_config_strip()
        self._build_notebook()
        self._poll()

        self._lb = LunarBaseProcess(
            log_cb=self._lb_log,
            ready_cb=self._on_lb_ready,
            stopped_cb=self._on_lb_stopped,
        )
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Tk window stays hidden — web dashboard is the primary UI
        start_dashboard_server(self, port=DASHBOARD_PORT, lb_port=LUNAR_BASE_PORT)
        self.after(300, self._open_dashboard_webview)
        self.after(800, self._lb_autostart)

    # ── Styles ────────────────────────────────────────────────────────────────
    def _apply_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".",
            background=BG, foreground=FG, font=FONT,
            troughcolor=BG2, fieldbackground=BG3,
        )
        s.configure("TNotebook",     background=BG,  borderwidth=0)
        s.configure("TNotebook.Tab", background=BG2, foreground=FG2,
                    padding=[18, 7], font=FONT_M)
        s.map("TNotebook.Tab",
              background=[("selected", BG3)],
              foreground=[("selected", ACCENT)])
        s.configure("TFrame",         background=BG)
        s.configure("TLabel",         background=BG, foreground=FG, font=FONT)
        s.configure("TLabelframe",    background=BG, bordercolor=BG4,
                    relief="flat", borderwidth=1)
        s.configure("TLabelframe.Label", background=BG, foreground=ACCENT2,
                    font=FONT_M)
        s.configure("TSeparator", background=BG4)

    # ── Header ────────────────────────────────────────────────────────────────
    def _build_header(self):
        hdr = tk.Frame(self, bg=BG2, pady=9)
        hdr.pack(fill="x")

        tk.Label(hdr, text="LUNAR TEAR", font=("Segoe UI", 13, "bold"),
                 bg=BG2, fg=ACCENT).pack(side="left", padx=14)
        tk.Label(hdr, text="NieR Re[in]carnation — Private Server Manager",
                 font=FONT, bg=BG2, fg=FG3).pack(side="left", padx=2)

        self._lbl_device = tk.Label(hdr, text="○ No device",
                                    font=FONT, bg=BG2, fg=FG3)
        self._lbl_device.pack(side="right", padx=14)

        self._lbl_server = tk.Label(hdr, text="● STOPPED",
                                    font=FONT_M, bg=BG2, fg=RED)
        self._lbl_server.pack(side="right", padx=(4, 0))

    # ── Config strip ──────────────────────────────────────────────────────────
    def _build_config_strip(self):
        strip = tk.Frame(self, bg=BG3, pady=7, padx=10)
        strip.pack(fill="x", pady=(1, 0))

        def lbl(text):
            tk.Label(strip, text=text, bg=BG3, fg=FG2, font=FONT).pack(side="left", padx=(10, 3))

        lbl("IP Host:")
        self._v_host = tk.StringVar(value=self.cfg.get("host", "192.168.1.36"))
        _entry(strip, self._v_host, width=16).pack(side="left")

        lbl("HTTP port:")
        self._v_http = tk.StringVar(value=str(self.cfg.get("http_port", 8080)))
        _entry(strip, self._v_http, width=6).pack(side="left")

        lbl("gRPC port:")
        self._v_grpc = tk.StringVar(value=str(self.cfg.get("grpc_port", 443)))
        _entry(strip, self._v_grpc, width=6).pack(side="left")

        _btn(strip, "Save", self._save_config, bg=ACCENT2, fg=BG,
             padx=14, pady=3).pack(side="left", padx=12)

        # APK status badge (right side)
        self._lbl_apk = tk.Label(strip, text="", bg=BG3, fg=FG2, font=FONT)
        self._lbl_apk.pack(side="right", padx=10)
        self._refresh_apk_badge()

    # ── Notebook ──────────────────────────────────────────────────────────────
    def _build_notebook(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=6)

        t1 = ttk.Frame(nb); nb.add(t1, text="  ▶  Server  ")
        t2 = ttk.Frame(nb); nb.add(t2, text="  📱  APK  ")
        t3 = ttk.Frame(nb); nb.add(t3, text="  ⚙  Tools  ")
        t4 = ttk.Frame(nb); nb.add(t4, text="  🌐  Lunar Base  ")

        self._build_server_tab(t1)
        self._build_apk_tab(t2)
        self._build_tools_tab(t3)
        self._build_lunar_base_tab(t4)

    # ── Server Tab ────────────────────────────────────────────────────────────
    def _build_server_tab(self, parent):
        ctrl = tk.Frame(parent, bg=BG, pady=10)
        ctrl.pack(fill="x", padx=12)

        self._btn_start = _btn(ctrl, "▶   START SERVER", self._start_server,
                                bg=GREEN, fg=BG, font=FONT_B, padx=22, pady=9)
        self._btn_start.pack(side="left", padx=(0, 8))

        _btn(ctrl, "⚙ Migrate DB", self._migrate_db,
             bg=BG3, fg=FG2, font=FONT, padx=12, pady=9).pack(side="left", padx=(0, 16))

        self._btn_stop = _btn(ctrl, "■   STOP", self._stop_server,
                               bg=BG4, fg=FG3, font=FONT_B, padx=18, pady=9,
                               state="disabled")
        self._btn_stop.pack(side="left")

        _btn(ctrl, "Clear", self._clear_server_log,
             bg=BG2, fg=FG2, padx=10, pady=5).pack(side="right")

        tk.Label(parent, text="Server output", bg=BG, fg=ACCENT2,
                 font=FONT_M).pack(anchor="w", padx=14)

        self._srv_log = _log_box(parent, fg="#90c080")
        self._srv_log.pack(fill="both", expand=True, padx=12, pady=(2, 8))

    # ── APK Tab ───────────────────────────────────────────────────────────────
    def _build_apk_tab(self, parent):
        info = tk.Frame(parent, bg=BG, pady=8)
        info.pack(fill="x", padx=12)

        self._lbl_apk_files = tk.Label(info, text="", bg=BG, fg=FG2, font=FONT)
        self._lbl_apk_files.pack(side="left")
        self._refresh_apk_files()

        btns = tk.Frame(parent, bg=BG)
        btns.pack(fill="x", padx=12, pady=(0, 8))

        self._btn_all = _btn(btns, "🔧  Patch + Build + Sign + Install",
                              self._run_all, bg=ACCENT, fg=BG, font=FONT_B,
                              padx=18, pady=9)
        self._btn_all.pack(side="left", padx=(0, 8))

        self._btn_install = _btn(btns, "📱  Install APK via ADB",
                                  self._run_install_only, bg=BG3, fg=FG,
                                  font=FONT_M, padx=14, pady=7)
        self._btn_install.pack(side="left", padx=(0, 8))

        self._btn_meta = _btn(btns, "⚙  Patch metadata only",
                               self._run_patch_meta, bg=BG2, fg=FG2,
                               font=FONT, padx=12, pady=6)
        self._btn_meta.pack(side="left")

        tk.Label(parent, text="APK pipeline log", bg=BG, fg=ACCENT2,
                 font=FONT_M).pack(anchor="w", padx=14)

        self._apk_log = _log_box(parent, fg="#c8c090")
        self._apk_log.pack(fill="both", expand=True, padx=12, pady=(2, 8))

    # ── Tools Tab ─────────────────────────────────────────────────────────────
    def _build_tools_tab(self, parent):
        # Tool paths ───────────────────────────────────────────────────────────
        lf = ttk.LabelFrame(parent, text="Tool Paths", padding=12)
        lf.pack(fill="x", padx=12, pady=10)

        TOOLS = [
            ("java",      "Java executable"),
            ("adb",       "ADB (platform-tools)"),
            ("zipalign",  "zipalign.exe (build-tools)"),
            ("apksigner", "apksigner.bat (build-tools)"),
            ("keystore",  "Debug keystore"),
            ("python",    "Python executable"),
        ]
        self._tool_vars: dict[str, tk.StringVar] = {}
        for i, (key, label) in enumerate(TOOLS):
            tk.Label(lf, text=label, bg=BG, fg=FG2, font=FONT,
                     anchor="w", width=28).grid(row=i, column=0, sticky="w", pady=3)
            var = tk.StringVar(value=self.cfg.get("tools", {}).get(key, ""))
            self._tool_vars[key] = var
            tk.Entry(lf, textvariable=var, bg=BG3, fg=FG, font=MONO,
                     width=52, insertbackground=FG, relief="flat", bd=4
                     ).grid(row=i, column=1, padx=6, pady=3)
            _btn(lf, "…", lambda k=key: self._browse_tool(k),
                 bg=BG2, fg=FG2, padx=6, pady=2
                 ).grid(row=i, column=2, pady=3)

        btn_row = tk.Frame(lf, bg=BG)
        btn_row.grid(row=len(TOOLS), column=0, columnspan=3, sticky="w", pady=(10, 2))
        _btn(btn_row, "Auto-Detect All", self._auto_detect,
             bg=ACCENT2, fg=BG, padx=12, pady=4).pack(side="left", padx=(0, 8))
        _btn(btn_row, "Save Tools", self._save_config,
             bg=ACCENT, fg=BG, font=FONT_B, padx=12, pady=4).pack(side="left")

        # Asset & file status ──────────────────────────────────────────────────
        lf2 = ttk.LabelFrame(parent, text="Files & Assets", padding=12)
        lf2.pack(fill="x", padx=12, pady=(0, 10))

        PATHS = [
            ("Original APK",    ORIGINAL_APK),
            ("Patched dir",     PATCHED_DIR),
            ("Metadata backup", METADATA_BACKUP),
            ("Signed APK",      SIGNED_APK),
            ("Server binary",   SERVER_EXE),
            ("Apktool JAR",     APKTOOL_JAR),
            ("Server assets",   SERVER_DIR / "assets"),
        ]
        for i, (label, path) in enumerate(PATHS):
            exists = path.exists()
            size = f"  ({_file_mb(path)})" if path.is_file() and exists else ""
            color = GREEN if exists else RED
            sym   = "✓" if exists else "✗"
            tk.Label(lf2, text=f"{sym}  {label}", bg=BG, fg=color,
                     font=FONT, anchor="w", width=22
                     ).grid(row=i, column=0, sticky="w", pady=2)
            tk.Label(lf2, text=str(path) + size, bg=BG, fg=FG2, font=MONO,
                     anchor="w").grid(row=i, column=1, sticky="w", padx=8, pady=2)

    # ── Actions ───────────────────────────────────────────────────────────────
    def _save_config(self):
        if self._save_config_quiet():
            messagebox.showinfo("Guardado", "Configuración guardada.\nAcceso directo actualizado.")
        else:
            messagebox.showerror("Error", "Los puertos deben ser números enteros.")

    def _open_dashboard_webview(self):
        if self._dashboard_webview_proc and self._dashboard_webview_proc.poll() is None:
            return
        self._dashboard_webview_proc = subprocess.Popen(
            [_pythonw_executable(), str(WEBVIEW_LAUNCHER),
             f"http://127.0.0.1:{DASHBOARD_PORT}",
             "Lunar Tear — NieR Re[in]carnation Manager"],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    def _save_config_quiet(self) -> bool:
        host = self._v_host.get().strip()
        try:
            http_port = int(self._v_http.get())
            grpc_port = int(self._v_grpc.get())
        except ValueError:
            return False
        self.cfg.update(host=host, http_port=http_port, grpc_port=grpc_port)
        tools = self.cfg.setdefault("tools", {})
        if hasattr(self, "_tool_vars"):
            for k, var in self._tool_vars.items():
                tools[k] = var.get().strip()
        save_config(self.cfg)
        _update_shortcut(self.cfg)
        return True

    def _migrate_db_quiet(self):
        self._migrate_db(silent=True)

    def _auto_detect(self):
        detected = auto_detect_tools()
        for k, v in detected.items():
            if k in self._tool_vars:
                self._tool_vars[k].set(v)
        messagebox.showinfo("Auto-detección", "Herramientas detectadas.\nGuardá para aplicar.")

    def _browse_tool(self, key):
        path = filedialog.askopenfilename(title=f"Seleccioná: {key}")
        if path:
            self._tool_vars[key].set(path)

    # Server actions ───────────────────────────────────────────────────────────
    def _start_server(self):
        host = self._v_host.get().strip()
        try:
            http_port = int(self._v_http.get())
            grpc_port = int(self._v_grpc.get())
        except ValueError:
            messagebox.showerror("Error", "Puerto inválido.")
            return
        if not SERVER_EXE.exists():
            messagebox.showerror("Error", f"Server binary no encontrado:\n{SERVER_EXE}")
            return
        self._server_log(f"▶ Iniciando servicios | host={host} cdn/http={http_port} grpc={grpc_port}")
        if self._server.start(host, http_port, grpc_port):
            self._set_server_ui(running=True)
        else:
            self._server_log("✗ No se pudo iniciar el server.")

    def _migrate_db(self, silent: bool = False):
        """Apply pending SQLite migrations without needing goose."""
        import sqlite3 as _sql
        db_path = SERVER_DIR / "db" / "game.db"
        if not db_path.exists():
            messagebox.showinfo("Migrate DB", f"BD no encontrada:\n{db_path}\nEl server la crea al primer inicio.")
            return

        def _col(cur, table, col):
            cur.execute(f"PRAGMA table_info({table})")
            return any(r[1] == col for r in cur.fetchall())

        def _tbl(cur, name):
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
            return bool(cur.fetchone())

        applied = []
        try:
            con = _sql.connect(str(db_path))
            cur = con.cursor()

            if not _col(cur, "users", "facebook_id"):
                cur.execute("ALTER TABLE users ADD COLUMN facebook_id INTEGER")
                cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_facebook_id ON users(facebook_id) WHERE facebook_id IS NOT NULL")
                applied.append("add_facebook_id")

            if not _tbl(cur, "user_parts_status_subs"):
                cur.execute("""
                    CREATE TABLE user_parts_status_subs (
                        user_id                      INTEGER NOT NULL REFERENCES users(user_id),
                        user_parts_uuid              TEXT    NOT NULL,
                        status_index                 INTEGER NOT NULL,
                        parts_status_sub_lottery_id  INTEGER NOT NULL DEFAULT 0,
                        level                        INTEGER NOT NULL DEFAULT 0,
                        status_kind_type             INTEGER NOT NULL DEFAULT 0,
                        status_calculation_type      INTEGER NOT NULL DEFAULT 0,
                        status_change_value          INTEGER NOT NULL DEFAULT 0,
                        latest_version               INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (user_id, user_parts_uuid, status_index)
                    )""")
                cur.execute("UPDATE user_parts SET level = 1")
                applied.append("add_parts_status_subs")

            cur.execute("""
                DELETE FROM user_deck_characters
                WHERE main_user_weapon_uuid = ''
            """)
            cur.execute("""
                DELETE FROM user_decks
                WHERE user_deck_character_uuid01 NOT IN (SELECT user_deck_character_uuid FROM user_deck_characters)
                   AND user_deck_character_uuid01 != ''
            """)

            if not _tbl(cur, "user_costume_lottery_effects"):
                cur.execute("""
                    CREATE TABLE user_costume_lottery_effects (
                        user_id               INTEGER NOT NULL REFERENCES users(user_id),
                        user_costume_uuid     TEXT    NOT NULL,
                        slot_number           INTEGER NOT NULL,
                        odds_number           INTEGER NOT NULL DEFAULT 0,
                        latest_version        INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (user_id, user_costume_uuid, slot_number)
                    )""")
                if not _col(cur, "user_costumes", "costume_lottery_effect_unlocked_slot_count"):
                    cur.execute("ALTER TABLE user_costumes ADD COLUMN costume_lottery_effect_unlocked_slot_count INTEGER NOT NULL DEFAULT 0")
                applied.append("add_costume_lottery_effects")

            if not _tbl(cur, "user_costume_lottery_effect_pending"):
                cur.execute("""
                    CREATE TABLE user_costume_lottery_effect_pending (
                        user_id           INTEGER NOT NULL REFERENCES users(user_id),
                        user_costume_uuid TEXT    NOT NULL,
                        slot_number       INTEGER NOT NULL,
                        odds_number       INTEGER NOT NULL DEFAULT 0,
                        latest_version    INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (user_id, user_costume_uuid)
                    )""")
                applied.append("add_costume_lottery_effect_pending")

            con.commit()
            con.close()
            msg = ("Migraciones aplicadas:\n• " + "\n• ".join(applied)) if applied else "BD ya actualizada. Sin cambios."
            if silent:
                self._server_log(f"[migrate] {msg}")
            else:
                messagebox.showinfo("Migrate DB", msg)
        except Exception as e:
            if silent:
                self._server_log(f"[migrate] ERROR: {e}")
            else:
                messagebox.showerror("Migrate DB Error", str(e))

    def _stop_server(self):
        self._server.stop()
        self._set_server_ui(running=False)

    def _set_server_ui(self, running: bool):
        if running:
            self._btn_start.configure(state="disabled", bg=BG4, fg=FG3)
            self._btn_stop.configure(state="normal",   bg=RED,  fg="white")
            self._lbl_server.configure(text="● RUNNING", fg=GREEN)
        else:
            self._btn_start.configure(state="normal",   bg=GREEN, fg=BG)
            self._btn_stop.configure(state="disabled",  bg=BG4,   fg=FG3)
            self._lbl_server.configure(text="● STOPPED", fg=RED)

    def _on_server_stopped(self):
        self.after(0, lambda: self._set_server_ui(False))
        self.after(0, lambda: self._server_log("■ Server detenido."))

    def _server_log(self, msg: str):
        self._server_log_buf.append(msg)
        def _do():
            self._srv_log.configure(state="normal")
            self._srv_log.insert("end", msg + "\n")
            self._srv_log.see("end")
            self._srv_log.configure(state="disabled")
        self.after(0, _do)

    def _clear_server_log(self):
        self._srv_log.configure(state="normal")
        self._srv_log.delete("1.0", "end")
        self._srv_log.configure(state="disabled")

    # APK actions ──────────────────────────────────────────────────────────────
    def _run_all(self):
        if self._apk_busy:
            return
        self._apk_log_clear()
        self._set_apk_busy(True)
        APKPipeline(self.cfg, self._apk_log_append, self._on_apk_done).run_all()

    def _run_install_only(self):
        if self._apk_busy:
            return
        if not SIGNED_APK.exists():
            messagebox.showerror("Error",
                f"APK firmado no encontrado:\n{SIGNED_APK}\n\n"
                "Ejecutá primero el pipeline completo.")
            return
        self._apk_log_clear()
        self._set_apk_busy(True)
        APKPipeline(self.cfg, self._apk_log_append, self._on_apk_done).run_install_only()

    def _run_patch_meta(self):
        if self._apk_busy:
            return
        self._apk_log_clear()
        self._set_apk_busy(True)
        APKPipeline(self.cfg, self._apk_log_append, self._on_apk_done).run_patch_metadata_only()

    def _set_apk_busy(self, busy: bool):
        self._apk_busy = busy
        st = "disabled" if busy else "normal"
        self._btn_all.configure(state=st)
        self._btn_install.configure(state=st)
        self._btn_meta.configure(state=st)

    def _on_apk_done(self, success: bool):
        def _do():
            self._set_apk_busy(False)
            self._refresh_apk_badge()
            self._refresh_apk_files()
            result = "✓ Pipeline completada." if success else "✗ Pipeline falló — revisá el log."
            self._apk_log_append(f"\n{result}")
        self.after(0, _do)

    def _apk_log_clear(self):
        self._apk_log.configure(state="normal")
        self._apk_log.delete("1.0", "end")
        self._apk_log.configure(state="disabled")

    def _apk_log_append(self, msg: str):
        def _do():
            self._apk_log.configure(state="normal")
            self._apk_log.insert("end", msg + "\n")
            self._apk_log.see("end")
            self._apk_log.configure(state="disabled")
        self.after(0, _do)

    # ── Refresh helpers ───────────────────────────────────────────────────────
    def _refresh_apk_badge(self):
        if SIGNED_APK.exists():
            self._lbl_apk.configure(
                text=f"📦 patched_signed.apk ({_file_mb(SIGNED_APK)})", fg=GREEN)
        else:
            self._lbl_apk.configure(text="⚠ Sin APK firmado", fg=YELLOW)

    def _refresh_apk_files(self):
        parts = []
        for label, p in [("original", ORIGINAL_APK), ("signed", SIGNED_APK)]:
            if p.exists():
                parts.append(f"{label} ({_file_mb(p)})")
        self._lbl_apk_files.configure(
            text="APKs: " + "  |  ".join(parts) if parts else "APKs: ninguno encontrado")

    # ── Lunar Base Tab ────────────────────────────────────────────────────────
    def _build_lunar_base_tab(self, parent):
        ctrl = tk.Frame(parent, bg=BG, pady=10)
        ctrl.pack(fill="x", padx=12)

        self._btn_lb_start = _btn(ctrl, "▶   Abrir Lunar Base", self._lb_start,
                                   bg=GREEN, fg=BG, font=FONT_B, padx=22, pady=9)
        self._btn_lb_start.pack(side="left", padx=(0, 8))

        self._btn_lb_stop = _btn(ctrl, "■   Detener", self._lb_stop,
                                  bg=BG4, fg=FG3, font=FONT_B, padx=18, pady=9,
                                  state="disabled")
        self._btn_lb_stop.pack(side="left", padx=(0, 8))

        self._btn_lb_browser = _btn(ctrl, "🌐  Abrir ventana", self._lb_open_browser,
                                     bg=BG3, fg=FG, font=FONT_M, padx=14, pady=7,
                                     state="disabled")
        self._btn_lb_browser.pack(side="left")

        _btn(ctrl, "Clear", self._lb_log_clear,
             bg=BG2, fg=FG2, padx=10, pady=5).pack(side="right")

        self._lbl_lb = tk.Label(ctrl, text="● DETENIDO", font=FONT_M, bg=BG, fg=RED)
        self._lbl_lb.pack(side="right", padx=(4, 12))

        info = tk.Label(parent,
            text=f"Lunar Base  ·  http://127.0.0.1:{LUNAR_BASE_PORT}  ·  {LUNAR_BASE_DIR}",
            bg=BG, fg=FG2, font=FONT, anchor="w")
        info.pack(anchor="w", padx=14, pady=(0, 2))

        tk.Label(parent, text="Lunar Base output", bg=BG, fg=ACCENT2,
                 font=FONT_M).pack(anchor="w", padx=14)

        self._lb_log_box = _log_box(parent, fg="#80b8c8")
        self._lb_log_box.pack(fill="both", expand=True, padx=12, pady=(2, 8))

    # ── Lunar Base Actions ────────────────────────────────────────────────────
    def _lb_autostart(self):
        self._lb_start(autostart=True)

    def _lb_start(self, autostart: bool = False):
        if self._lb.is_running():
            self._lb_open_browser()
            return
        if not autostart:
            self._lb_log(f"▶ Iniciando Lunar Base en http://127.0.0.1:{LUNAR_BASE_PORT} ...")
        if self._lb.start(LUNAR_BASE_PORT, quiet=autostart):
            self._btn_lb_start.configure(state="disabled", bg=BG4, fg=FG3)
            self._btn_lb_stop.configure(state="normal", bg=RED, fg="white")
            self._lbl_lb.configure(text="● INICIANDO", fg=YELLOW)
        else:
            self._lb_log("✗ No se pudo iniciar Lunar Base.")

    def _lb_stop(self):
        self._lb.stop()
        self._btn_lb_start.configure(state="normal", bg=GREEN, fg=BG)
        self._btn_lb_stop.configure(state="disabled", bg=BG4, fg=FG3)
        self._btn_lb_browser.configure(state="disabled")
        self._lbl_lb.configure(text="● DETENIDO", fg=RED)
        self._lb_log("■ Lunar Base detenido.")

    def _lb_open_browser(self):
        self._lb.open_webview(LUNAR_BASE_PORT)

    def _on_lb_ready(self, port: int):
        def _do():
            self._lbl_lb.configure(text="● RUNNING", fg=GREEN)
            self._btn_lb_browser.configure(state="normal")
        self.after(0, _do)

    def _on_lb_stopped(self):
        def _do():
            if self._lbl_lb.cget("text") != "● DETENIDO":
                self._btn_lb_start.configure(state="normal", bg=GREEN, fg=BG)
                self._btn_lb_stop.configure(state="disabled", bg=BG4, fg=FG3)
                self._btn_lb_browser.configure(state="disabled")
                self._lbl_lb.configure(text="● DETENIDO", fg=RED)
        self.after(0, _do)

    def _lb_log(self, msg: str):
        self._lb_log_buf.append(msg)
        def _do():
            self._lb_log_box.configure(state="normal")
            self._lb_log_box.insert("end", msg + "\n")
            self._lb_log_box.see("end")
            self._lb_log_box.configure(state="disabled")
        self.after(0, _do)

    def _lb_log_clear(self):
        self._lb_log_box.configure(state="normal")
        self._lb_log_box.delete("1.0", "end")
        self._lb_log_box.configure(state="disabled")

    # ── Window close ─────────────────────────────────────────────────────────
    def _on_close(self):
        if self._dashboard_webview_proc and self._dashboard_webview_proc.poll() is None:
            self._dashboard_webview_proc.terminate()
        self._lb.stop()
        self._server.stop()
        self.destroy()

    # ── Status polling ────────────────────────────────────────────────────────
    def _poll(self):
        # Quit when dashboard webview window is closed
        if (self._dashboard_webview_proc is not None
                and self._dashboard_webview_proc.poll() is not None):
            self._on_close()
            return

        # Server state
        if not self._server.is_running():
            if self._lbl_server.cget("text") == "● RUNNING":
                self._set_server_ui(False)

        # Device (every ~5s)
        self._poll_tick += 1
        if self._poll_tick % 10 == 0:
            adb = self.cfg.get("tools", {}).get("adb", "")
            dev = get_adb_device(adb)
            if dev:
                self._lbl_device.configure(text=f"● {dev}", fg=GREEN)
            else:
                self._lbl_device.configure(text="○ Sin dispositivo", fg=FG3)

        self.after(500, self._poll)


# ─── Tkinter Helpers ───────────────────────────────────────────────────────────
def _btn(parent, text, command=None, bg=BG3, fg=FG, font=FONT,
         padx=10, pady=4, state="normal", **kw) -> tk.Button:
    return tk.Button(
        parent, text=text, command=command,
        bg=bg, fg=fg, font=font, relief="flat",
        padx=padx, pady=pady, state=state,
        activebackground=BG4, activeforeground=FG,
        cursor="hand2", **kw,
    )


def _entry(parent, var, width=20) -> tk.Entry:
    return tk.Entry(
        parent, textvariable=var, bg=BG, fg=FG,
        font=FONT, width=width, insertbackground=FG,
        relief="flat", bd=4,
    )


def _log_box(parent, fg="#b0b8a0") -> scrolledtext.ScrolledText:
    box = scrolledtext.ScrolledText(
        parent, bg="#0a0a12", fg=fg, font=MONO,
        relief="flat", bd=0, wrap="word",
        state="disabled",
        selectbackground=BG3,
    )
    return box


# ─── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()
