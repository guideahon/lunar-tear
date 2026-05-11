"""Opens a pywebview window. Launched as a subprocess by app.py."""
import sys
import time
import urllib.request
import ctypes
from pathlib import Path

import webview

arg1  = sys.argv[1] if len(sys.argv) > 1 else "8888"
URL   = arg1 if arg1.startswith("http") else f"http://127.0.0.1:{arg1}"
TITLE = sys.argv[2] if len(sys.argv) > 2 else "Lunar Base — NieR Re[in]carnation DB Manager"

# Wait up to 20 seconds for the server to be ready
for _ in range(40):
    try:
        urllib.request.urlopen(URL, timeout=1)
        break
    except Exception:
        time.sleep(0.5)

ICON = str(Path(__file__).resolve().parent.parent / "lunar-tear.ico")


def _set_windows_app_id():
    """Ensure taskbar uses our app identity/icon instead of pythonw defaults."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "walter-sparrow.lunar-tear.manager"
        )
    except Exception:
        pass


_set_windows_app_id()

window = webview.create_window(
    TITLE,
    URL,
    width=1400,
    height=900,
    min_size=(900, 600),
    hidden=True,
)


def _show_when_ready():
    try:
        window.show()
    except Exception:
        pass


window.events.loaded += _show_when_ready
webview.start(icon=ICON if Path(ICON).exists() else None)
