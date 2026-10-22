#!/usr/bin/env python3
"""Run the real site and account Worker with an isolated, disposable local account.

Requires Python 3, Node.js, and `npm install` in api/. Nothing is deployed. The
database, random session, local-only Wrangler config, and logs live outside docs/.
Run `python tools/custom_lists_preview.py start`, then open the printed owner URL.
Run the same command with `stop` when finished. Local data survives restarts.
"""

import argparse
import hashlib
import http.server
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local"))) / "MisterZine" / "custom-lists-preview"


def request_json(url, token=None):
    headers = {"Authorization": "Bearer " + token} if token else {}
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=3) as response:
        return json.load(response)


def available(port):
    with socket.socket() as sock:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind(("127.0.0.1", port))


def isolated_env():
    env = os.environ.copy()
    # This preview uses no Cloudflare account, OAuth, or production credentials.
    for key in list(env):
        if key.startswith(("CLOUDFLARE_", "CF_", "WRANGLER_")):
            del env[key]
    env.update(CI="1", WRANGLER_SEND_METRICS="false", NO_COLOR="1")
    return env


def wrangler():
    node = shutil.which("node")
    script = ROOT / "api/node_modules/wrangler/bin/wrangler.js"
    if not node or not script.is_file():
        raise RuntimeError("Install Node.js and run npm install in api/ first.")
    return [node, str(script)]


def save_state(directory, state):
    (directory / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")


def current_notice():
    match = re.search(r"var NOTICE\s*=\s*\{\s*id:\s*'([a-z0-9-]{1,40})'", (ROOT / "docs/theme.js").read_text(encoding="utf-8"))
    return match.group(1) if match else ""


def prepare(directory, state):
    config = directory / "wrangler.toml"
    config.write_text(
        'name = "misterzine-local-preview"\n'
        f'main = {json.dumps((ROOT / "api/src/index.js").as_posix())}\n'
        'compatibility_date = "2026-08-01"\n'
        '[vars]\n'
        f'SITE_ORIGIN = {json.dumps(state["site"])}\n'
        f'API_ORIGIN = {json.dumps(state["api"])}\n'
        f'DEV_ORIGINS = "{state["site"]},http://127.0.0.1:{state["site_port"]}"\n'
        f'SESSION_SECRET = {json.dumps(state["secret"])}\n'
        'REPORTS_ENABLED = "0"\nFEEDBACK_ENABLED = "0"\n'
        '[[d1_databases]]\nbinding = "DB"\ndatabase_name = "misterzine-preview"\n'
        'database_id = "11111111-1111-4111-8111-111111111111"\n',
        encoding="utf-8",
    )
    seed = directory / "seed.sql"
    statements = []
    for account, token in [("local-custom-lists-preview", state["token"]),
                           ("local-custom-lists-follower", state["follower_token"]),
                           ("local-custom-lists-tester", state["tester_token"])]:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        statements.extend([
            f"INSERT OR IGNORE INTO users (provider, provider_user_id) VALUES ('github', '{account}');",
            "INSERT OR REPLACE INTO sessions (token_hash, user_id) SELECT "
            f"'{token_hash}', id FROM users WHERE provider='github' AND provider_user_id='{account}';",
            f"UPDATE users SET notice_seen='{current_notice()}' WHERE provider='github' AND provider_user_id='{account}';",
        ])
    seed.write_text("\n".join(statements), encoding="utf-8")
    for sql in [ROOT / "api/schema.sql", ROOT / "api/migrations/2026-10-22-custom-lists.sql",
                ROOT / "api/migrations/2026-10-22-list-community.sql", seed]:
        if sql.is_file():
            result = subprocess.run(
                wrangler() + ["d1", "execute", "misterzine-preview", "--local", "--config", str(config),
                              "--persist-to", str(directory / "wrangler"), "--file", str(sql)],
                cwd=directory, env=isolated_env(), capture_output=True, text=True,
                encoding="utf-8", errors="replace",
            )
            with (directory / "setup.log").open("a", encoding="utf-8") as log:
                log.write(result.stdout + result.stderr)
            if result.returncode:
                raise RuntimeError(f"Local database initialization failed; see {directory / 'setup.log'}")


def launch(command, directory, log_name):
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with (directory / log_name).open("a", encoding="utf-8") as log:
        return subprocess.Popen(
            command, cwd=directory, env=isolated_env(), stdin=subprocess.DEVNULL,
            stdout=log, stderr=log, creationflags=flags, start_new_session=os.name != "nt",
        ).pid


def stop(state):
    for key in ["site_pid", "worker_pid"]:
        pid = state.pop(key, None)
        if not pid:
            continue
        if os.name == "nt":
            # Saved PIDs can be reused after a reboot. Verify our own command
            # before asking Windows to stop that process and its child tree.
            result = subprocess.run([
                "powershell.exe", "-NoProfile", "-Command",
                f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine",
            ], capture_output=True, text=True, encoding="utf-8", errors="replace")
            expected = "custom_lists_preview.py" if key == "site_pid" else "wrangler.js"
            if expected not in result.stdout or (key == "worker_pid" and "misterzine" not in result.stdout.lower()):
                continue
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        else:
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass


def ready(state):
    try:
        health = request_json(state["site"] + "/__preview__/health")
        return health.get("preview") == state["preview_id"] and request_json(state["api"] + "/me", state["token"]).get("provider") == "github"
    except (OSError, ValueError):
        return False


def print_status(directory, state):
    print("Local preview account: " + state["site"] + "/__preview__/owner")
    print("Second local account: " + state["site"] + "/__preview__/follower")
    print("Signed-out preview (use another browser or private window): " + state["site"] + "/__preview__/anonymous")
    print("Local API: " + state["api"])
    print("State and logs: " + str(directory))
    print("Process IDs: " + str({key: state.get(key) for key in ["site_pid", "worker_pid"]}))


def serve(directory, state):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ROOT / "docs"), **kwargs)

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_GET(self):
            if self.headers.get("Host") not in [f"localhost:{state['site_port']}", f"127.0.0.1:{state['site_port']}"]:
                self.send_error(403)
                return
            path = self.path.split("?", 1)[0]
            if path == "/__preview__/health":
                body = json.dumps({"preview": state["preview_id"]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path in ["/__preview__/owner", "/__preview__/follower", "/__preview__/tester", "/__preview__/anonymous"]:
                token_key = {"owner": "token", "follower": "follower_token", "tester": "tester_token"}.get(path.rsplit("/", 1)[-1])
                account = f"localStorage.setItem('mz-token', {json.dumps(state[token_key])});" if token_key else "localStorage.removeItem('mz-token');"
                target = "/releases/" if token_key else "/releases/?collection=all"
                body = (
                    "<!doctype html><meta charset=utf-8><title>MisterZine local preview</title>"
                    "<p>Opening the local Custom Lists preview...</p><script>"
                    f"localStorage.setItem('mz-api', {json.dumps(state['api'])});"
                    f"localStorage.setItem('mz-notice', {json.dumps(current_notice())});"
                    "localStorage.removeItem('mz-fav-import');" + account +
                    f"location.replace({json.dumps(target)});</script>"
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("X-Robots-Tag", "noindex, nofollow")
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

    class Server(http.server.ThreadingHTTPServer):
        allow_reuse_address = False

        def server_bind(self):
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()

    Server(("127.0.0.1", state["site_port"]), Handler).serve_forever()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["start", "stop", "status", "prepare", "serve"])
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--site-port", type=int, default=8633)
    parser.add_argument("--api-port", type=int, default=8793)
    args = parser.parse_args()
    directory = args.state_dir.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    state_file = directory / "state.json"
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {
        "site_port": args.site_port, "api_port": args.api_port,
        "site": f"http://localhost:{args.site_port}", "api": f"http://localhost:{args.api_port}",
        "token": secrets.token_urlsafe(32), "secret": secrets.token_urlsafe(32),
        "preview_id": secrets.token_hex(12),
    }
    # Add test accounts without replacing the owner's session or saved lists.
    state.setdefault("follower_token", secrets.token_urlsafe(32))
    state.setdefault("tester_token", secrets.token_urlsafe(32))
    save_state(directory, state)
    if args.command == "serve":
        serve(directory, state)
    elif args.command == "stop":
        stop(state)
        save_state(directory, state)
        print("Stopped preview processes. Local lists are preserved in " + str(directory))
    elif args.command == "status":
        print("Ready" if ready(state) else "Not running or not ready")
        print_status(directory, state)
    elif args.command == "prepare":
        prepare(directory, state)
        print("Prepared local database.")
    elif ready(state):
        print_status(directory, state)
    else:
        # Never take over an occupied port or kill another session's server.
        available(state["site_port"])
        available(state["api_port"])
        available(state["api_port"] + 1000)
        prepare(directory, state)
        state["worker_pid"] = launch(wrangler() + [
            "dev", "--local", "--ip", "127.0.0.1", "--port", str(state["api_port"]),
            "--inspector-port", str(state["api_port"] + 1000),
            "--config", str(directory / "wrangler.toml"), "--persist-to", str(directory / "wrangler"),
        ], directory, "worker.log")
        state["site_pid"] = launch([sys.executable, str(Path(__file__).resolve()), "serve", "--state-dir", str(directory)], directory, "site.log")
        save_state(directory, state)
        for _ in range(30):
            if ready(state):
                print_status(directory, state)
                return
            time.sleep(0.5)
        stop(state)
        save_state(directory, state)
        raise RuntimeError("Preview did not become ready; inspect logs in " + str(directory))


if __name__ == "__main__":
    main()
