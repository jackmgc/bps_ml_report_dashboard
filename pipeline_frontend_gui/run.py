"""Launcher: `python -m pipeline_frontend_gui.run` -> uvicorn + open browser."""

import threading
import time
import webbrowser

import uvicorn


def main() -> None:
    host, port = "127.0.0.1", 8000
    url = f"http://{host}:{port}"
    threading.Thread(target=lambda: (time.sleep(1.2), webbrowser.open(url)), daemon=True).start()
    print(f"\n  Pipeline Dashboard -> {url}\n  (Ctrl+C to stop)\n")
    uvicorn.run("pipeline_frontend_gui.app:app", host=host, port=port, reload=False, log_level="info")


if __name__ == "__main__":
    main()
