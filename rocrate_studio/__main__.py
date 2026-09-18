"""``python -m rocrate_studio [--port 8765] [--no-browser]``"""
import argparse
import threading
import webbrowser

import uvicorn


def main():
    ap = argparse.ArgumentParser(description="RO-Crate Studio — local GUI for building RO-Crates")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    url = f"http://127.0.0.1:{a.port}"
    if not a.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"RO-Crate Studio at {url}  (Ctrl-C to stop)")
    uvicorn.run("rocrate_studio.app:app", host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
