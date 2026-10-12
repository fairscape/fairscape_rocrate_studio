"""``python -m rocrate_studio [--port 8765] [--no-browser] [--check]``"""
import argparse
import os
import threading
import webbrowser

from . import deps


def main():
    ap = argparse.ArgumentParser(description="FAIRSCAPE Studio — local GUI for building FAIRSCAPE Data Packages")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1",
                    help="address to listen on; 0.0.0.0 shares the studio with the network")
    ap.add_argument("--no-browser", action="store_true")
    # for a shared, deployed studio only; see access.py
    ap.add_argument("--multi-user", action="store_true",
                    help="ask each visitor for a name and give them their own output folder")
    ap.add_argument("--password", help="one password every visitor must give (or ROCRATE_STUDIO_PASSWORD)")
    ap.add_argument("--check", action="store_true",
                    help="report what is installed in this environment and exit")
    a = ap.parse_args()
    if a.check:
        raise SystemExit(deps.print_report())
    # nothing in the studio works without the other fairscape packages, so say
    # so here rather than on the first click
    deps.require()
    if a.multi_user:
        os.environ["ROCRATE_STUDIO_MULTI_USER"] = "1"
    if a.password:
        os.environ["ROCRATE_STUDIO_PASSWORD"] = a.password

    note = deps.startup_note()
    if note:
        print(note)

    # the first start after an install compiles fastapi, pydantic and the
    # fairscape packages to bytecode, which can take a while with no output
    print("Starting FAIRSCAPE Studio... (the first start after installing can take "
          "up to a minute; later starts take a second or two)", flush=True)
    import uvicorn  # after the check: it is one of the things that may be missing
    from .app import app

    url = f"http://{'127.0.0.1' if a.host == '0.0.0.0' else a.host}:{a.port}"
    if not a.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"FAIRSCAPE Studio is running at {url}", flush=True)
    print("Open that address in your browser if it does not open by itself. "
          "Leave this window open while you use it; press Ctrl-C here to stop.", flush=True)
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
