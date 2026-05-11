"""Opens a pywebview window for Lunar Base. Launched as a subprocess by app.py."""
import sys
import time
import urllib.request

import webview

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8888
URL  = f"http://127.0.0.1:{PORT}"

# Wait up to 20 seconds for uvicorn to be ready
for _ in range(40):
    try:
        urllib.request.urlopen(URL, timeout=1)
        break
    except Exception:
        time.sleep(0.5)

window = webview.create_window(
    "Lunar Base — NieR Re[in]carnation DB Manager",
    URL,
    width=1400,
    height=900,
    min_size=(900, 600),
)
webview.start()
