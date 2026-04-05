from __future__ import annotations

import os
import threading
import webbrowser

import uvicorn

from .server import create_app


def main() -> None:
    host = os.environ.get("MEDIA_BROWSER_HOST", "127.0.0.1")
    port = int(os.environ.get("MEDIA_BROWSER_PORT", "8765"))
    open_browser = os.environ.get("MEDIA_BROWSER_OPEN", "1") != "0"
    url = f"http://{host}:{port}"

    if open_browser:
        timer = threading.Timer(1.2, lambda: webbrowser.open(url))
        timer.daemon = True
        timer.start()

    uvicorn.run(create_app(), host=host, port=port)
