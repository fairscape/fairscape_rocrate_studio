"""``python -m rocrate_studio [--port 8765] [--no-browser] [--check]``"""
import argparse
import threading
import webbrowser

from . import deps


def main():
    ap = argparse.ArgumentParser(description="RO-Crate Studio — local GUI for building RO-Crates")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--check", action="store_true",
                    help="report what is installed in this environment and exit")
    a = ap.parse_args()
    if a.check:
        raise SystemExit(deps.print_report())
    # nothing in the studio works without the other fairscape packages, so say
    # so here rather than on the first click
    deps.require()

    import uvicorn  # after the check: it is one of the things that may be missing

    note = deps.startup_note()
    if note:
        print(note)

    url = f"http://127.0.0.1:{a.port}"
    if not a.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"RO-Crate Studio at {url}  (Ctrl-C to stop)")
    uvicorn.run("rocrate_studio.app:app", host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
