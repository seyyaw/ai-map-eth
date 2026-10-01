#!/usr/bin/env python3
"""
Start the whole field stack with one command: collection server + Telegram bot.

    ./run-all.sh

The two processes must share one SQLite database, and the way that goes wrong is
silent -- each service looks healthy on its own and the datasets simply never
meet, which nobody notices until `by_mode` turns out to have only ever counted
one channel. So this supervisor does not merely *document* that they must agree:
it resolves the database path ONCE, to an absolute path, and exports that same
value into both children. Neither child can be pointed somewhere else without
editing this file.

The other silent failure is a bot that died an hour ago while the server kept
serving. If either child exits, the other is stopped and the supervisor exits
non-zero, so a half-running stack cannot be mistaken for a running one.

Environment:
    AIMAP_DB           database path. Default: tools/data/aimap.db
    AIMAP_ADMIN_TOKEN  required by the dashboard and exports. Generated if unset.
    AIMAP_BOT_TOKEN    from @BotFather. Without it the bot is skipped, loudly.
    HOST, PORT         server bind address. Default 127.0.0.1:8000
"""

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GREY, GREEN, YELLOW, RED, BOLD, OFF = (("\033[90m", "\033[32m", "\033[33m", "\033[31m", "\033[1m", "\033[0m")
    if sys.stdout.isatty() else ("", "", "", "", "", ""))

stopping = threading.Event()
children = {}


def say(msg, colour=""):
    print(f"{colour}{msg}{OFF}", flush=True)


def find_python():
    """The interpreter that can actually import the dependencies.

    A virtualenv on macOS can carry several `bin/python*` names pointing at
    different minor versions, and only some of them see the installed packages.
    Picking the first one that imports both frameworks avoids a confusing
    ModuleNotFoundError several seconds after startup looked fine.
    """
    candidates = [ROOT / ".venv/bin/python3.11", ROOT / ".venv/bin/python3",
                  ROOT / ".venv/bin/python", Path(sys.executable)]
    probe = "import importlib.util as u,sys; sys.exit(0 if u.find_spec('fastapi') and u.find_spec('uvicorn') else 1)"
    for c in candidates:
        if c.exists() and subprocess.run([str(c), "-c", probe],
                                         capture_output=True).returncode == 0:
            return c
    return None


def pump(name, stream, colour):
    """Prefix each child's output so two logs in one terminal stay readable."""
    for raw in iter(stream.readline, b""):
        line = raw.decode("utf-8", "replace").rstrip()
        if line:
            print(f"{colour}[{name}]{OFF} {line}", flush=True)
    stream.close()


def spawn(name, argv, env, colour):
    proc = subprocess.Popen(argv, cwd=str(ROOT), env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    children[name] = proc
    threading.Thread(target=pump, args=(name, proc.stdout, colour), daemon=True).start()
    return proc


def shutdown(reason, code):
    if stopping.is_set():
        return
    stopping.set()
    say(f"\n{reason}", YELLOW)
    for name, proc in children.items():
        if proc.poll() is None:
            say(f"  stopping {name}…", GREY)
            proc.terminate()
    deadline = time.time() + 10
    for name, proc in children.items():
        try:
            proc.wait(timeout=max(0.1, deadline - time.time()))
        except subprocess.TimeoutExpired:
            say(f"  {name} did not stop; killing it", RED)
            proc.kill()
    say("stopped.", GREY)
    sys.exit(code)


def main():
    py = find_python()
    if py is None:
        say("No usable interpreter found.", RED)
        say("  python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt")
        return 1

    # ---- one database path, resolved once, handed to both children -----------
    db = Path(os.environ.get("AIMAP_DB") or (ROOT / "tools" / "data" / "aimap.db")).resolve()
    db.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["AIMAP_DB"] = str(db)
    env["PYTHONUNBUFFERED"] = "1"

    host = env.get("HOST", "127.0.0.1")
    port = env.get("PORT", "8000")

    admin = env.get("AIMAP_ADMIN_TOKEN", "").strip()
    generated = False
    if not admin:
        import secrets
        admin = secrets.token_hex(16)
        env["AIMAP_ADMIN_TOKEN"] = admin
        generated = True

    bot_token = env.get("AIMAP_BOT_TOKEN", "").strip()

    say(f"\n{BOLD}AI-MAP Ethiopia{OFF}")
    say(f"  database   {db}", GREY)
    say(f"  survey     http://{host}:{port}/")
    say(f"  dashboard  http://{host}:{port}/dashboard.html")
    say(f"  admin token{'  (generated for this run only)' if generated else ''}: {BOLD}{admin}{OFF}")
    if generated:
        say("  Set AIMAP_ADMIN_TOKEN yourself before real field work: a token that changes\n"
            "  on every restart cannot be given to a field supervisor.", GREY)

    server = spawn("server", [str(py), "-m", "uvicorn", "--app-dir", "tools/server",
                              "app:app", "--host", host, "--port", str(port),
                              "--proxy-headers", "--forwarded-allow-ips=*"],
                   env, GREEN)

    if bot_token:
        say(f"  telegram   long polling (no inbound port needed)")
        spawn("bot", [str(py), "tools/telegram_bot/bot.py"], env, YELLOW)
    else:
        say(f"\n  {YELLOW}Telegram bot NOT started: AIMAP_BOT_TOKEN is not set.{OFF}")
        say("  Get a token from @BotFather, then:", GREY)
        say("      AIMAP_BOT_TOKEN='123456:ABC...' ./run-all.sh", GREY)
        say("  The web questionnaire and dashboard work without it; the citizen\n"
            "  instrument's main field channel does not.", GREY)
    say("")

    def on_signal(_sig, _frm):
        shutdown("Interrupted.", 0)

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    # A dead child is not a degraded stack, it is a broken one. Bring the rest
    # down with it rather than leaving something that looks like it is running.
    while not stopping.is_set():
        for name, proc in list(children.items()):
            rc = proc.poll()
            if rc is not None:
                shutdown(f"{name} exited with code {rc}; stopping the rest.", rc or 1)
        time.sleep(0.4)
    return 0


if __name__ == "__main__":
    sys.exit(main())
