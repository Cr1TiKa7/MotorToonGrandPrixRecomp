"""Shared helpers for driving a running Motor_Toon_Grand_Prix_Recompiled instance (stdlib only).

Launching, liveness, frame counter, pad input, RAM reads and shutdown, used by
every smoke test. All remote calls go through psxdbg (one request per TCP
connection). Adapted from MOHRecomp's psxrun; NTSC title, so 60 frames/s.
"""

import os
import subprocess
import time
import zlib

import psxdbg

POLL_SECS = 0.5
FPS = 60
STARVATION_TIMEOUT_US = 30_000_000
# Errors a cold-starting or busy runtime can produce for a single request;
# callers retry them until their deadline instead of aborting the run.
TRANSIENT = (ConnectionError, ValueError, KeyError, OSError, IndexError, zlib.error)

# PS1 digital pad bits; the debug server takes them inverted (0 = pressed).
BUTTONS = {
    "select": 0x0001, "l3": 0x0002, "r3": 0x0004, "start": 0x0008,
    "up": 0x0010, "right": 0x0020, "down": 0x0040, "left": 0x0080,
    "l2": 0x0100, "r2": 0x0200, "l1": 0x0400, "r1": 0x0800,
    "triangle": 0x1000, "circle": 0x2000, "cross": 0x4000, "square": 0x8000,
}


class SmokeFailure(Exception):
    pass


def mask(*names):
    held = 0
    for name in names:
        held |= BUTTONS[name]
    return 0xFFFF & ~held


def check_alive(proc):
    if proc.poll() is not None:
        raise SmokeFailure(f"runtime exited early with code {proc.returncode}")


def launch(exe, cue, game, port, out_dir, env_extra=None, extra_args=None, hidden=True):
    """Start the runtime hidden with its own memory cards under out_dir.

    The runtime's cwd is the exe's directory, so every path is made absolute.
    stdout/stderr go to out_dir/runtime.log. SDL's dummy audio driver keeps the
    game silent on the host; the audio taps are recorded before the device.
    Debug builds abort after 4 s without an emulation heartbeat; the HLE boot
    opens the disc image at cycle ~150 and took longer than that on a busy
    host (2026-10-31), so the harness allows STARVATION_TIMEOUT_US unless the
    caller's environment sets PSX_STARVATION_TIMEOUT_US itself.
    """
    memcards = os.path.join(os.path.abspath(out_dir), "memcards")
    os.makedirs(memcards, exist_ok=True)
    cmd = [os.path.abspath(exe), "--game", os.path.abspath(game),
           "--disc", os.path.abspath(cue),
           "--no-launcher", "--debug-port", str(port),
           "--memcard-dir", memcards] + (["--hidden-window"] if hidden else []) + list(extra_args or [])
    env = dict(os.environ, SDL_AUDIODRIVER="dummy")
    env.setdefault("PSX_STARVATION_TIMEOUT_US", str(STARVATION_TIMEOUT_US))
    env.update(env_extra or {})
    with open(os.path.join(out_dir, "runtime.log"), "wb") as log:
        return subprocess.Popen(cmd, cwd=os.path.dirname(os.path.abspath(exe)),
                                stdout=log, stderr=subprocess.STDOUT, env=env)


def wait_for_ping(proc, port, deadline):
    while time.monotonic() < deadline:
        check_alive(proc)
        try:
            return psxdbg.send("ping", port=port, timeout=2.0)
        except ConnectionError:
            time.sleep(POLL_SECS)
    raise SmokeFailure("debug port never answered")


def read_frame(port, deadline):
    last = "no reply"
    while time.monotonic() < deadline:
        try:
            reply = psxdbg.send("frame", port=port)
            return reply, int(reply["frame"])
        except TRANSIENT as exc:
            last = f"{type(exc).__name__}: {exc}"
            time.sleep(POLL_SECS)
    raise SmokeFailure(f"frame command never answered ({last})")


def wait_frame(port, frame, deadline):
    while time.monotonic() < deadline:
        try:
            current = int(psxdbg.send("frame", port=port)["frame"])
            if current >= frame:
                return current
        except TRANSIENT:
            pass
        time.sleep(POLL_SECS)
    raise TimeoutError(f"frame {frame} not reached before deadline")


def screenshot(port, path):
    """Write a PNG of the current display to path; returns the server reply."""
    reply = psxdbg.send("screenshot", port=port, path=path.replace("\\", "/"))
    if not reply.get("ok"):
        raise SmokeFailure(f"screenshot failed: {reply.get('error', reply)}")
    return reply


def press(port, *names, frames=4):
    psxdbg.send("press", port=port, buttons=mask(*names), frames=frames)


def release(port):
    """Let go of every pad-1 button."""
    psxdbg.send("clear_input", port=port, payload={"port": 1})


def hold_buttons(port, *names):
    """Hold the named pad-1 buttons until release()."""
    psxdbg.send("set_input", port=port, buttons=mask(*names))


def read_bytes(port, addr, n):
    reply = psxdbg.send("read_ram", port=port, addr="0x%08X" % addr, len=n)
    return bytes.fromhex(reply["hex"])


def read_u32(port, addr):
    return int.from_bytes(read_bytes(port, addr, 4), "little")


def shutdown(proc, port):
    if proc.poll() is None:
        try:
            psxdbg.send("quit", port=port, timeout=2.0)
        except ConnectionError:
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
