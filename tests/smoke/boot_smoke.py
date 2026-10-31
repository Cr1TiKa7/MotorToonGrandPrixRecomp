"""Boot smoke test: start the runtime hidden, wait for a real frame, quit.

Usage (from anywhere):
    py -3 tests/smoke/boot_smoke.py --exe PATH --cue PATH [--port 4370]
                                    [--timeout 90] [--out DIR] [--game game.toml]

Exit 0 when the frame counter advances and a screenshot with at least
MIN_COLORS distinct colors was captured; exit 1 otherwise (one-line reason
on stderr). The runtime instance started here is always shut down.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pngcheck  # noqa: E402
import psxdbg  # noqa: E402
import psxrun  # noqa: E402

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
MIN_COLORS = 16
SHOT_EVERY_SECS = 2.0

SmokeFailure = psxrun.SmokeFailure
TRANSIENT = psxrun.TRANSIENT


def _fail(msg):
    print(f"boot_smoke: FAIL: {msg}", file=sys.stderr)
    return 1


def _check_frames_advance(port, deadline):
    # "ping" is answered by the server's I/O thread without a frame counter;
    # "frame" goes through the emulation thread and reports emulated frames.
    _, first = psxrun.read_frame(port, deadline)
    time.sleep(2.0)
    reply, second = psxrun.read_frame(port, deadline)
    if second <= first:
        raise SmokeFailure(f"frame counter stuck at {first}")
    return reply


def _wait_for_real_frame(proc, port, out_dir, deadline):
    n = 0
    last = "no screenshot taken"
    while time.monotonic() < deadline:
        psxrun.check_alive(proc)
        shot = os.path.join(out_dir, f"shot-{n:03d}.png").replace("\\", "/")
        try:
            reply = psxdbg.send("screenshot", port=port, path=shot)
            if not reply.get("ok"):
                last = f"server error: {reply.get('error', reply)}"
            elif not os.path.isfile(shot):
                last = f"server reported ok but {shot} is missing"
            else:
                colors = pngcheck.distinct_colors(shot, limit=MIN_COLORS)
                if colors >= MIN_COLORS:
                    return shot, reply
                last = f"{shot} has only {colors} colors"
        except TRANSIENT as exc:
            last = f"{type(exc).__name__}: {exc}"
        n += 1
        time.sleep(SHOT_EVERY_SECS)
    raise SmokeFailure(f"no non-trivial frame (>= {MIN_COLORS} colors) within timeout; last: {last}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--exe", required=True)
    ap.add_argument("--cue", required=True)
    ap.add_argument("--port", type=int, default=psxdbg.DEFAULT_PORT)
    ap.add_argument("--timeout", type=float, default=90.0)
    ap.add_argument("--out", default="")
    ap.add_argument("--game", default=os.path.join(REPO_ROOT, "game.toml"))
    args = ap.parse_args(argv)

    if psxdbg.port_in_use(args.port):
        return _fail(f"port {args.port} busy - another runtime running?")
    if not os.path.isfile(args.exe):
        return _fail(f"exe not found: {args.exe}")

    # Screenshot paths travel through the server's JSON parser, which does not
    # unescape \uXXXX, so the out dir must be ASCII.
    out_dir = os.path.abspath(args.out or os.path.join(
        os.environ.get("TEMP", REPO_ROOT), "mtgp-boot-" + time.strftime("%Y%m%d-%H%M%S")))
    if not out_dir.isascii():
        return _fail(f"out dir must be an ASCII path: {out_dir}")
    os.makedirs(out_dir, exist_ok=True)

    print(f"boot_smoke: out={out_dir}")
    proc = psxrun.launch(args.exe, args.cue, args.game, args.port, out_dir)
    try:
        deadline = time.monotonic() + args.timeout
        first = psxrun.wait_for_ping(proc, args.port, deadline)
        print(f"boot_smoke: first ping {first}")
        later = _check_frames_advance(args.port, deadline)
        shot, reply = _wait_for_real_frame(proc, args.port, out_dir, deadline)
        print(f"boot_smoke: OK frame={later['frame']} "
              f"shot={shot} size={reply.get('width')}x{reply.get('height')}")
        return 0
    except SmokeFailure as exc:
        return _fail(str(exc))
    except Exception as exc:  # noqa: BLE001 - keep the one-line contract
        return _fail(f"unexpected error: {type(exc).__name__}: {exc}")
    finally:
        psxrun.shutdown(proc, args.port)


if __name__ == "__main__":
    sys.exit(main())
