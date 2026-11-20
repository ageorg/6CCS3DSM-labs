"""Lab 3: a shared trip planner on two servers.

    python run.py                    start the lab
    python run.py --replay FILE      replay a recorded set of edits

Then open http://localhost:8003 if the browser does not open by itself.
"""

import argparse
import json
import sys
import threading
import webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import planner
from planner import Planner, FIELDS, FAILURES, STAMPS, replay

HERE = Path(__file__).parent
STATIC = HERE / "static"
CONTENT_TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}

USERS = [
    {"name": "Ana", "server": "London"},
    {"name": "Ben", "server": "New York"},
]

system = Planner()
recording = None
lock = threading.Lock()   # one request changes the system at a time


def update_settings(changes):
    s = system.settings
    if changes.get("failure") in FAILURES:
        s.failure = changes["failure"]
    if changes.get("stamps") in STAMPS:
        s.stamps = changes["stamps"]


def page_state():
    state = system.state()
    state["field_options"] = FIELDS
    state["fixed"] = {"sync_delay": planner.SYNC_DELAY, "skew": planner.SKEW}
    if recording:
        state["mode"] = "replay"
        state["recording"] = {key: recording[key] for key in ("title", "description", "complaints")}
        state["users"] = recording["users"]
    else:
        state["mode"] = "lab"
        state["users"] = USERS
    return state


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/state":
            with lock:
                return self.send_json(page_state())

        name = "index.html" if self.path == "/" else self.path.lstrip("/")
        file = STATIC / name
        if file.parent != STATIC or not file.exists():
            return self.send_error(404)
        body = file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPES.get(file.suffix, "text/plain") + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(length) or b"{}")

        with lock:
            if self.path == "/api/settings":
                update_settings(data)
                system.reset()
            elif self.path == "/api/edit" and not recording:
                user = next((u for u in USERS if u["name"] == data.get("user")), None)
                field = data.get("field")
                if user is None or field not in FIELDS or data.get("value") not in FIELDS[field]:
                    return self.send_error(400)
                system.edit(user, field, data["value"])
                system.run_until(system.now + 1000)
            elif self.path == "/api/wait" and not recording:
                if int(data.get("ms", 0)) not in (1000, 5000):
                    return self.send_error(400)
                system.run_until(system.now + int(data["ms"]))
            elif self.path == "/api/reset":
                system.reset()
            elif self.path == "/api/replay" and recording:
                replay(system, recording)
            else:
                return self.send_error(404)
            self.send_json(page_state())

    def send_json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # keep the terminal quiet


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # Browsers sometimes close a connection without sending anything.
        if isinstance(sys.exc_info()[1], ConnectionError):
            return
        super().handle_error(request, client_address)


def main():
    global recording
    parser = argparse.ArgumentParser(description="Lab 3: a shared trip planner on two servers")
    parser.add_argument("--replay", metavar="FILE", help="replay a recorded set of edits")
    parser.add_argument("--port", type=int, default=8003)
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    args = parser.parse_args()

    if args.replay:
        recording = json.loads(Path(args.replay).read_text(encoding="utf-8"))
        update_settings(recording.get("settings", {}))
        system.settings.failure = recording.get("failure", "none")
        system.reset()

    url = f"http://localhost:{args.port}"
    try:
        server = Server(("localhost", args.port), Handler)
    except OSError:
        print(f"Port {args.port} is already in use. Is the lab already running in another window?")
        print(f"Stop it with Ctrl+C there, or start this one with:  --port {args.port + 1}")
        return

    mode = "replay" if recording else "lab"
    print(f"Lab 3 ({mode}) is running at {url}  (press Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
