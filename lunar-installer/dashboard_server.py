"""Tiny HTTP API server powering the web dashboard (port 8887)."""
import json
import shutil
import subprocess
import sys
import threading
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DASHBOARD_PORT = 8887
_HTML = Path(__file__).resolve().parent / "dashboard.html"

# ── Paths (mirror app.py) ──────────────────────────────────────────────────────
_ROOT         = Path(__file__).resolve().parent.parent
_SERVER_DIR   = _ROOT / "server"
_SERVER_EXE   = _SERVER_DIR / "lunar-tear.exe"
_CDN_EXE      = _SERVER_DIR / "octo-cdn.exe"
_AUTH_EXE     = _SERVER_DIR / "auth-server.exe"
_CLIENT_DIR   = _ROOT / "client"
_TOOLS_DIR    = _ROOT / "tools"
_PT_DIR       = _TOOLS_DIR / "platform-tools"
_APKTOOL_JAR  = _TOOLS_DIR / "apktool.jar"
_ORIGINAL_APK = _CLIENT_DIR / "3.7.1.apk"
_PATCHED_DIR  = _CLIENT_DIR / "patched"
_SIGNED_APK   = _CLIENT_DIR / "patched_signed.apk"
_METADATA_BAK = _PATCHED_DIR / "assets/bin/Data/Managed/Metadata/global-metadata.dat.orig"
_DEBUG_KS     = Path.home() / ".android" / "debug.keystore"
_CONFIG_PATH  = Path(__file__).resolve().parent / "config.json"

# ── Download URLs ──────────────────────────────────────────────────────────────
_APKTOOL_URL = "https://github.com/iBotPeaches/Apktool/releases/download/v2.9.3/apktool_2.9.3.jar"
_PT_URL      = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
_SERVER_GH   = "https://api.github.com/repos/Walter-Sparrow/lunar-tear/releases/latest"
_APK_URL     = ("https://archive.org/download/nierreincarnation/"
                "Global/apk/NieR%20Re%5Bin%5Dcarnation%203.7.1.apk")


# ── Log buffers ────────────────────────────────────────────────────────────────
class LogBuffer:
    def __init__(self, maxlen: int = 500):
        self._lock = threading.Lock()
        self._lines: list = []
        self._maxlen = maxlen

    def append(self, line: str):
        with self._lock:
            self._lines.append(line)
            if len(self._lines) > self._maxlen:
                self._lines = self._lines[-self._maxlen:]

    def since(self, n: int):
        with self._lock:
            total = len(self._lines)
            lines = self._lines[n:] if 0 <= n <= total else []
            return lines, total


# ── Download state ─────────────────────────────────────────────────────────────
_setup_log = LogBuffer(300)
_dl_lock   = threading.Lock()
_dl_prog   = {"pct": 0, "label": "", "active": False}


def _dl_run(url: str, dest: Path, label: str, done_cb):
    """Download URL → dest in a background thread. Updates _dl_prog."""
    if not _dl_lock.acquire(blocking=False):
        _setup_log.append("✗ Descarga ya en progreso — esperá que termine.")
        return
    _dl_prog.update({"pct": 0, "label": label, "active": True})
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        _setup_log.append(f"→ {label}…")
        with urllib.request.urlopen(url, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            done  = 0
            with open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        _dl_prog["pct"]   = done * 100 // total
                        _dl_prog["label"] = (f"{label} — "
                            f"{done/1024/1024:.1f}/{total/1024/1024:.1f} MB")
        tmp.replace(dest)
        done_cb(True)
    except Exception as e:
        _setup_log.append(f"✗ Error: {e}")
        tmp.unlink(missing_ok=True)
        done_cb(False)
    finally:
        _dl_prog.update({"pct": 0, "label": "", "active": False})
        _dl_lock.release()


def _start_dl_apktool():
    def done(ok):
        if ok:
            _setup_log.append(f"✓ apktool.jar descargado → {_APKTOOL_JAR}")
    threading.Thread(
        target=_dl_run, args=(_APKTOOL_URL, _APKTOOL_JAR, "Descargando apktool.jar", done),
        daemon=True
    ).start()


def _start_dl_platform_tools():
    tmp_zip = _TOOLS_DIR / "platform-tools.zip"
    def done(ok):
        if not ok:
            return
        _setup_log.append("→ Extrayendo platform-tools…")
        try:
            with zipfile.ZipFile(tmp_zip) as z:
                z.extractall(_TOOLS_DIR)
            tmp_zip.unlink(missing_ok=True)
            _setup_log.append(f"✓ Platform tools extraídas → {_PT_DIR}")
        except Exception as e:
            _setup_log.append(f"✗ Error extrayendo: {e}")
    threading.Thread(
        target=_dl_run, args=(_PT_URL, tmp_zip, "Descargando platform-tools", done),
        daemon=True
    ).start()


def _start_dl_server():
    def fetch():
        if not _dl_lock.acquire(blocking=False):
            _setup_log.append("✗ Descarga ya en progreso.")
            return
        _dl_prog.update({"pct": 0, "label": "Consultando GitHub…", "active": True})
        _dl_lock.release()
        try:
            req = urllib.request.Request(
                _SERVER_GH,
                headers={"Accept": "application/vnd.github+json",
                         "User-Agent": "lunar-tear-dashboard"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            assets = data.get("assets", [])
            url = ""
            for ext in (".zip", ".exe"):
                for a in assets:
                    n = a["name"].lower()
                    if n.endswith(ext) and ("windows" in n or "win" in n or ext == ".exe"):
                        url = a["browser_download_url"]
                        break
                if url:
                    break
            if not url and assets:
                url = assets[0]["browser_download_url"]
            if not url:
                _setup_log.append("✗ No se encontraron assets en la release de GitHub")
                return
            _start_dl_server_url(url)
        except Exception as e:
            _setup_log.append(f"✗ Error consultando GitHub: {e}")
    threading.Thread(target=fetch, daemon=True).start()


def _start_dl_server_url(url: str):
    dest = _SERVER_DIR / Path(url.split("?")[0]).name
    def done(ok):
        if not ok:
            return
        if dest.suffix.lower() == ".zip":
            _setup_log.append("→ Extrayendo server ZIP…")
            try:
                with zipfile.ZipFile(dest) as z:
                    z.extractall(_SERVER_DIR)
                dest.unlink(missing_ok=True)
                _setup_log.append(f"✓ Server extraído → {_SERVER_DIR}")
            except Exception as e:
                _setup_log.append(f"✗ Error extrayendo: {e}")
        else:
            _setup_log.append(f"✓ Server descargado → {dest}")
    threading.Thread(
        target=_dl_run, args=(url, dest, f"Descargando {dest.name}", done),
        daemon=True
    ).start()


def _start_dl_apk(url: str = _APK_URL):
    tmp = _CLIENT_DIR / "apk_dl.tmp"
    def done(ok):
        if not ok:
            return
        try:
            tmp.replace(_ORIGINAL_APK)
            _setup_log.append(f"✓ APK descargado → {_ORIGINAL_APK}")
        except Exception as e:
            _setup_log.append(f"✗ Error guardando APK: {e}")
    threading.Thread(
        target=_dl_run, args=(url, tmp, "Descargando APK (puede tardar ~500 MB)", done),
        daemon=True
    ).start()


def _start_gen_keystore(app):
    def _run():
        if _DEBUG_KS.exists():
            _setup_log.append(f"✓ Keystore ya existe → {_DEBUG_KS}")
            return
        java = app.cfg.get("tools", {}).get("java") or "java"
        keytool = str(Path(java).parent / "keytool.exe") if java != "java" else "keytool"
        _setup_log.append("→ Generando debug keystore…")
        cmd = [keytool, "-genkeypair", "-v",
               "-keystore",   str(_DEBUG_KS),
               "-alias",      "androiddebugkey",
               "-keyalg",     "RSA", "-keysize", "2048", "-validity", "10000",
               "-storepass",  "android", "-keypass", "android",
               "-dname",      "CN=Android Debug,O=Android,C=US"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            if r.returncode == 0 and _DEBUG_KS.exists():
                _setup_log.append(f"✓ Keystore generado → {_DEBUG_KS}")
                app.cfg.setdefault("tools", {})["keystore"] = str(_DEBUG_KS)
                _write_config(app.cfg)
            else:
                _setup_log.append(f"✗ Error: {r.stderr.strip()[:300]}")
        except Exception as e:
            _setup_log.append(f"✗ Error: {e}")
    threading.Thread(target=_run, daemon=True).start()


def _write_config(cfg: dict):
    _CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def _installer_status():
    return {
        "apktool":        _APKTOOL_JAR.exists(),
        "platform_tools": (_PT_DIR / "adb.exe").exists(),
        "keystore":       _DEBUG_KS.exists(),
        "server":         _SERVER_EXE.exists(),
        "apk":            _ORIGINAL_APK.exists(),
        "signed_apk":     _SIGNED_APK.exists(),
        "metadata_bak":   _METADATA_BAK.exists(),
    }


# ── HTTP Handler ───────────────────────────────────────────────────────────────
class _Handler(BaseHTTPRequestHandler):
    app_ref = None
    lb_port = 8888

    def log_message(self, *_):
        pass

    def _json(self, data, status: int = 200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n)) if n else {}

    def do_GET(self):
        app = _Handler.app_ref
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            body = _HTML.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif path == "/api/status":
            cfg = app.cfg
            self._json({
                "server_running":   app._server.is_running(),
                "lb_running":       app._lb.is_running(),
                "host":             cfg.get("host", ""),
                "http_port":        cfg.get("http_port", 8080),
                "grpc_port":        cfg.get("grpc_port", 8003),
                "lb_port":          _Handler.lb_port,
                "server_installed": _SERVER_EXE.exists(),
            })

        elif path == "/api/logs/server":
            since = int(qs.get("since", ["0"])[0])
            lines, total = app._server_log_buf.since(since)
            self._json({"lines": lines, "total": total})

        elif path == "/api/logs/lb":
            since = int(qs.get("since", ["0"])[0])
            lines, total = app._lb_log_buf.since(since)
            self._json({"lines": lines, "total": total})

        elif path == "/api/logs/apk":
            since = int(qs.get("since", ["0"])[0])
            lines, total = app._apk_log_buf.since(since)
            self._json({"lines": lines, "total": total})

        elif path == "/api/logs/setup":
            since = int(qs.get("since", ["0"])[0])
            lines, total = _setup_log.since(since)
            self._json({"lines": lines, "total": total})

        elif path == "/api/installer/status":
            self._json(_installer_status())

        elif path == "/api/installer/progress":
            self._json(_dl_prog)

        elif path == "/api/tools":
            self._json(app.cfg.get("tools", {}))

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        app = _Handler.app_ref
        path = urlparse(self.path).path
        data = self._read_json()

        # Server actions
        if path == "/api/server/start":
            app.after(0, app._start_server)
        elif path == "/api/server/stop":
            app.after(0, app._stop_server)
        elif path == "/api/server/migrate":
            app.after(0, app._migrate_db_quiet)

        # Config
        elif path == "/api/config":
            def _apply():
                if "host" in data:
                    app._v_host.set(data["host"])
                if "http_port" in data:
                    app._v_http.set(str(data["http_port"]))
                if "grpc_port" in data:
                    app._v_grpc.set(str(data["grpc_port"]))
                app._save_config_quiet()
            app.after(0, _apply)

        # LB actions
        elif path == "/api/lb/start":
            app.after(0, app._lb_start)
        elif path == "/api/lb/stop":
            app.after(0, app._lb_stop)

        # APK pipeline
        elif path == "/api/apk/run-all":
            app.after(0, app._run_all)
        elif path == "/api/apk/install-only":
            app.after(0, app._run_install_only)
        elif path == "/api/apk/patch-meta":
            app.after(0, app._run_patch_meta)

        # Installer / Setup downloads
        elif path == "/api/installer/dl/apktool":
            _start_dl_apktool()
        elif path == "/api/installer/dl/platform-tools":
            _start_dl_platform_tools()
        elif path == "/api/installer/dl/keystore":
            _start_gen_keystore(app)
        elif path == "/api/installer/dl/server":
            if "url" in data:
                _start_dl_server_url(data["url"])
            else:
                _start_dl_server()
        elif path == "/api/installer/dl/apk":
            _start_dl_apk(data.get("url", _APK_URL))

        # Tools config
        elif path == "/api/tools/save":
            def _save_tools():
                tools = app.cfg.setdefault("tools", {})
                tools.update(data)
                if hasattr(app, "_tool_vars"):
                    for k, v in data.items():
                        if k in app._tool_vars:
                            app._tool_vars[k].set(str(v))
                _write_config(app.cfg)
            app.after(0, _save_tools)
        elif path == "/api/tools/auto-detect":
            def _detect():
                from app import auto_detect_tools  # safe: same dir, not circular at runtime
                detected = auto_detect_tools()
                tools = app.cfg.setdefault("tools", {})
                for k, v in detected.items():
                    if v:
                        tools[k] = v
                if hasattr(app, "_tool_vars"):
                    for k, v in detected.items():
                        if v and k in app._tool_vars:
                            app._tool_vars[k].set(v)
                _write_config(app.cfg)
            threading.Thread(target=_detect, daemon=True).start()

        else:
            self.send_response(404)
            self.end_headers()
            return

        self._json({"ok": True})


def start_dashboard_server(app, port: int = DASHBOARD_PORT, lb_port: int = 8888):
    _Handler.app_ref = app
    _Handler.lb_port = lb_port
    server = HTTPServer(("127.0.0.1", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
