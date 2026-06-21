"""Minimal ttyd WebSocket client to reproduce the reconnect loop locally.

Connects like the browser does (subprotocol 'tty', basic auth), sends the init
frame to spawn the child shell, sends a command, and prints what comes back.
If the child exits immediately, the WS closes right away (= the reconnect loop).
"""

import base64
import json
import os
import time

import websocket

# Point at the live Railway endpoint via env, e.g.:
#   TTYD_URL=wss://xxxx.up.railway.app/ws TTYD_USER=fred TTYD_PASS=... python ttyd_probe.py
URL = os.environ.get("TTYD_URL", "ws://localhost:7682/ws")
USER = os.environ.get("TTYD_USER", "a")
PASS = os.environ.get("TTYD_PASS", "b")


def main() -> None:
    auth = base64.b64encode(f"{USER}:{PASS}".encode()).decode()
    ws = websocket.create_connection(
        URL,
        subprotocols=["tty"],
        header=[f"Authorization: Basic {auth}"],
        timeout=10,
    )
    print("WS connected")
    # init frame (browser sends this first to spawn the process).
    # With --credential, ttyd expects AuthToken = base64("user:pass").
    token = base64.b64encode(f"{USER}:{PASS}".encode()).decode()
    ws.send(json.dumps({"AuthToken": token, "columns": 100, "rows": 30}))
    print("sent init")
    time.sleep(2)
    # Command.INPUT = '0'
    ws.send("0" + "echo HELLO_FROM_WS\r")
    print("sent command")

    start = time.time()
    while time.time() - start < 8:
        try:
            msg = ws.recv()
        except Exception as exc:  # noqa: BLE001
            print(f"recv error / closed: {exc!r}")
            break
        if not msg:
            print("connection closed by server (empty)")
            break
        if isinstance(msg, bytes):
            msg = msg.decode("utf-8", "replace")
        # server output frames are prefixed with '0'
        body = msg[1:] if msg[:1] in "012" else msg
        printable = "".join(c for c in body if c.isprintable() or c in "\n ")
        if printable.strip():
            print("OUT:", printable.strip()[:200])
    ws.close()
    print("done")


if __name__ == "__main__":
    main()
