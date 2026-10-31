"""Minimal client for the PSXRecomp TCP debug server (stdlib only).

The server takes one JSON request per connection: send one line, read one
line back.
"""

import json
import socket

DEFAULT_PORT = 4370


def send(cmd, port=DEFAULT_PORT, timeout=5.0, payload=None, **params):
    """One request/reply. port= is the TCP port; fields that clash with send()'s
    own parameter names (e.g. a command's pad "port") go in payload."""
    request = {"id": 1, "cmd": cmd, **params, **(payload or {})}
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as sock:
            sock.sendall((json.dumps(request) + "\n").encode())
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buf += chunk
    except OSError as exc:
        raise ConnectionError(f"debug port {port}: {exc}") from exc
    if not buf.strip():
        raise ConnectionError(f"debug port {port}: empty reply to {cmd!r}")
    return json.loads(buf.decode())


def port_in_use(port=DEFAULT_PORT):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0
