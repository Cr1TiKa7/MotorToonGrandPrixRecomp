"""Goodies smoke test: unlock and launch the bonus programs, keep them running.

Usage (from anywhere):
    py -3 tests/smoke/goodies_smoke.py --exe PATH --cue PATH [--program tank|sub|r|all]
                                       [--port 4370] [--secs 60] [--out DIR]

One runtime per program, with PSX_OVERLAY_AUTOCOMPILE_OFF=1 and the software
renderer. From the main menu the test sets the Goodies unlock bytes in the save
struct (0x800E4576 Tank Combat, ...77 Submarine X, ...78 Motor Toon GP R; found
by static analysis of 0x8004CDE8), opens Goodies (UP wraps from the first
row), picks the row, answers the "Save Records and Settings?" dialog with
Discard and lets the relay loader boot.exe start the program. Then, for SECS:
  - the emulated frame counter keeps advancing and runtime.log has no FATAL
    (the loader's SetConf must drop the main game's IRQ handlers; OpenBIOS did
    not until bios/openbios-setconf.patch, and the kernel jumped into memory
    the new program had overwritten);
  - the picture keeps changing;
  - the program's own code runs natively from the static shard
    (overlay_static_entries hits inside its address range grow).
Exit 0/1, one-line reason on stderr; every runtime is shut down.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import psxdbg  # noqa: E402
import psxrun  # noqa: E402
import race_smoke  # noqa: E402

UNLOCK = {"tank": 0x800E4576, "sub": 0x800E4577, "r": 0x800E4578}
DOWNS = {"tank": 2, "sub": 3, "r": 4}          # rows below Extra Characters
CODE_RANGE = {                                   # loaded program text (aot/overlays.json)
    "tank": (0x80020000, 0x8006A000),
    "sub": (0x80010000, 0x80048000),
    "r": (0x80010000, 0x8007D3D0),
}
# Emulated frames, measured 2026-11-01: START at 900 opens the main menu.
START_FRAME = 900
GOODIES_FRAME = 1100
STEP_FRAMES = 60
SAMPLE_SECS = 5.0

SmokeFailure = psxrun.SmokeFailure


def _fail(msg):
    print(f"goodies_smoke: FAIL: {msg}", file=sys.stderr)
    return 1


def static_hits(port, lo, hi):
    reply = psxdbg.send("overlay_static_entries", port=port,
                        addr_lo="0x%08X" % lo, addr_hi="0x%08X" % hi, limit=4)
    if not reply.get("ok"):
        raise SmokeFailure(f"no static overlay dispatcher: {reply.get('error', reply)}")
    return int(reply["range_hits"])


def fatal_line(out_dir):
    with open(os.path.join(out_dir, "runtime.log"), "rb") as fh:
        for line in fh.read().decode(errors="replace").splitlines():
            if "FATAL" in line:
                return line.strip()
    return None


def launch_program(port, program, deadline):
    psxrun.wait_frame(port, START_FRAME, deadline)
    psxrun.press(port, "start", frames=6)
    psxrun.wait_frame(port, GOODIES_FRAME, deadline)
    psxdbg.send("write_ram", port=port, addr="0x%08X" % UNLOCK[program], val=1)
    psxrun.press(port, "up", frames=6)
    frame = GOODIES_FRAME + 2 * STEP_FRAMES
    psxrun.wait_frame(port, frame, deadline)
    psxrun.press(port, "cross", frames=6)
    frame += STEP_FRAMES  # the Goodies screen fades in; the first DOWN comes 120 frames later
    for _ in range(DOWNS[program]):
        frame += STEP_FRAMES
        psxrun.wait_frame(port, frame, deadline)
        psxrun.press(port, "down", frames=6)
    for button, gap in (("cross", 90), ("left", 120), ("cross", 90)):
        frame += gap
        psxrun.wait_frame(port, frame, deadline)
        psxrun.press(port, button, frames=6)
    return frame


def run_program(exe, cue, game, port, out_root, program, secs):
    out_dir = os.path.join(out_root, program)
    os.makedirs(out_dir, exist_ok=True)
    game_sw = race_smoke.renderer_toml(game, "software", out_dir)
    proc = psxrun.launch(exe, cue, game_sw, port, out_dir,
                         env_extra={"PSX_OVERLAY_AUTOCOMPILE_OFF": "1"})
    try:
        deadline = time.monotonic() + 240 + secs
        psxrun.wait_for_ping(proc, port, deadline)
        lo, hi = CODE_RANGE[program]
        before = static_hits(port, lo, hi)
        launch_program(port, program, deadline)
        time.sleep(SAMPLE_SECS)
        _, f_start = psxrun.read_frame(port, deadline)
        shots, frames = [], [f_start]
        t_end = time.monotonic() + secs
        n = 0
        while time.monotonic() < t_end:
            time.sleep(SAMPLE_SECS)
            psxrun.check_alive(proc)
            line = fatal_line(out_dir)
            if line:
                raise SmokeFailure(f"{program}: {line}")
            _, f = psxrun.read_frame(port, deadline)
            if f <= frames[-1]:
                raise SmokeFailure(f"{program}: frame counter stuck at {f}")
            frames.append(f)
            if n % 3 == 0:
                shots.append(race_smoke.shot(port, out_dir, f"{program}-{n:02d}", deadline))
            n += 1
        after = static_hits(port, lo, hi)
        if after <= before:
            raise SmokeFailure(f"{program}: no static-shard code ran in 0x{lo:08X}-0x{hi:08X}")
        diffs = [race_smoke.screen_diff(a, b) for a, b in zip(shots, shots[1:])]
        if diffs and max(diffs) < race_smoke.SCREEN_DIFF_MIN:
            raise SmokeFailure(f"{program}: picture never changed (diffs {[round(d, 3) for d in diffs]})")
        return (f"{program}: frames {frames[0]}->{frames[-1]} static_hits +{after - before} "
                f"diffs={[round(d, 2) for d in diffs]}")
    finally:
        psxrun.shutdown(proc, port)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--exe", required=True)
    ap.add_argument("--cue", required=True)
    ap.add_argument("--port", type=int, default=psxdbg.DEFAULT_PORT)
    ap.add_argument("--program", choices=("tank", "sub", "r", "all"), default="all")
    ap.add_argument("--secs", type=float, default=60.0)
    ap.add_argument("--out", default="")
    ap.add_argument("--game", default=os.path.join(race_smoke.REPO_ROOT, "game.toml"))
    args = ap.parse_args(argv)

    if psxdbg.port_in_use(args.port):
        return _fail(f"port {args.port} busy - another runtime running?")
    if not os.path.isfile(args.exe):
        return _fail(f"exe not found: {args.exe}")
    out_root = os.path.abspath(args.out or os.path.join(
        os.environ.get("TEMP", race_smoke.REPO_ROOT), "mtgp-goodies-" + time.strftime("%Y%m%d-%H%M%S")))
    if not out_root.isascii():
        return _fail(f"out dir must be an ASCII path: {out_root}")
    print(f"goodies_smoke: out={out_root}")
    programs = ("tank", "sub", "r") if args.program == "all" else (args.program,)
    try:
        for program in programs:
            print("goodies_smoke: " + run_program(args.exe, args.cue, args.game, args.port,
                                                  out_root, program, args.secs))
        print("goodies_smoke: OK")
        return 0
    except (SmokeFailure, TimeoutError) as exc:
        return _fail(str(exc))
    except Exception as exc:  # noqa: BLE001 - keep the one-line contract
        return _fail(f"unexpected error: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
