"""Race smoke test: menu -> Championship Race -> first driver -> race, all native.

Usage (from anywhere):
    py -3 tests/smoke/race_smoke.py --exe PATH --cue PATH [--port 4370]
                                    [--renderer software|opengl|game] [--out DIR]

Runs with PSX_OVERLAY_AUTOCOMPILE_OFF=1, so every track ENGINE overlay that
runs natively comes from the static AOT shard linked into the exe. Steps are
timed in emulated frames (not wall time), so a slow host only makes the run
longer. Checks, in order:
  1. START opens the main menu and CROSS reaches the driver select (the screen
     changes after each press: the pad input reaches the game).
  2. A second CROSS starts the race: the track ENGINE overlay at 0x801F2000
     runs from the static shard (overlay_static_entries range hits grow) and
     nothing in it is interpreted (dirty_ram_stats per_pc in that range).
  3. Holding CROSS (accelerate) for RACE_SECS: the picture keeps changing, the
     SPU is audible, and game code outside the kernel stays native
     (interpreted instructions per frame at PCs >= 0x10000 below a bound).
  4. Frame rate (median of three 5 s windows) is reported; with --min-fps it
     is also gated. Other GPU/CPU load on the host distorts it, so the default
     only reports it.
The renderer defaults to software: a temporary copy of game.toml next to the
run output overrides [video] renderer, so host GPU load cannot stall the run.
Exit 0/1, one-line reason on stderr; the runtime is always shut down.
"""

import argparse
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pngcheck  # noqa: E402
import psxdbg  # noqa: E402
import psxrun  # noqa: E402
import wavcheck  # noqa: E402

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ENGINE_LO, ENGINE_HI = 0x801F2000, 0x801F4000
# Emulated-frame timeline measured on the USA disc (2026-11-01): the attract
# flyover ends near frame 800, START at 871 showed the menu, CROSS at 1173 the
# driver select, CROSS at 1310 the track card; the countdown ran near 1640.
START_FRAME = 900
MENU_CROSS_FRAME = 1150
DRIVER_CROSS_FRAME = 1350
RACE_SECS = 20.0
SCREEN_DIFF_MIN = 0.02          # share of pixels that differ between two shots
RMS_MIN = 200.0
SPU_OUT_TAP = 0
SAMPLE_RATE = 44100
GAME_INTERP_INSNS_PER_FRAME_MAX = 3000

SmokeFailure = psxrun.SmokeFailure


def _fail(msg):
    print(f"race_smoke: FAIL: {msg}", file=sys.stderr)
    return 1


def renderer_toml(game, renderer, out_dir):
    """game.toml copy with [video] renderer replaced (or the original for 'game')."""
    if renderer == "game":
        return game
    with open(game, encoding="utf-8") as fh:
        text = fh.read()
    text, n = re.subn(r'(?m)^renderer\s*=\s*"[^"]*"', f'renderer = "{renderer}"', text)
    if n != 1:
        raise SmokeFailure(f"expected one [video] renderer line in {game}, found {n}")
    path = os.path.join(out_dir, "game.toml")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


def shot(port, out_dir, name, deadline):
    """Screenshot to out_dir/name.png, retrying transient 'display disabled' replies."""
    path = os.path.join(out_dir, name + ".png").replace("\\", "/")
    last = "no reply"
    while time.monotonic() < deadline:
        try:
            reply = psxdbg.send("screenshot", port=port, path=path)
            if reply.get("ok") and os.path.isfile(path):
                return path
            last = str(reply.get("error", reply))
        except psxrun.TRANSIENT as exc:
            last = f"{type(exc).__name__}: {exc}"
        time.sleep(0.25)
    raise SmokeFailure(f"screenshot {name} failed: {last}")


def screen_diff(a, b):
    return pngcheck.diff_share(a, b)


def engine_hits(port):
    reply = psxdbg.send("overlay_static_entries", port=port,
                        addr_lo="0x%08X" % ENGINE_LO, addr_hi="0x%08X" % ENGINE_HI, limit=4)
    if not reply.get("ok"):
        raise SmokeFailure(f"no static overlay dispatcher: {reply.get('error', reply)}")
    return int(reply["range_hits"])


def interp_by_pc(port):
    """{pc: insns} for every interpreted entry PC since boot."""
    rows = psxdbg.send("dirty_ram_stats", port=port, timeout=10).get("per_pc", [])
    return {int(r["pc"], 16): int(r["insns"]) for r in rows}


def game_interp(before, after):
    """Interpreted instructions at game PCs (>= 0x10000: not kernel/BIOS install slots)."""
    return sum(n - before.get(pc, 0) for pc, n in after.items() if pc >= 0x10000)


def engine_interp(after):
    lo, hi = ENGINE_LO & 0x1FFFFFFF, ENGINE_HI & 0x1FFFFFFF
    return {pc: n for pc, n in after.items() if lo <= pc < hi}


def measure_fps(port, deadline, windows=3, secs=5.0):
    rates = []
    for _ in range(windows):
        _, f0 = psxrun.read_frame(port, deadline)
        t0 = time.monotonic()
        time.sleep(secs)
        _, f1 = psxrun.read_frame(port, deadline)
        rates.append((f1 - f0) / (time.monotonic() - t0))
    return sorted(rates)[len(rates) // 2], rates


def measure_rms(port, out_dir):
    count = 2 * SAMPLE_RATE
    head = int(psxdbg.send("audio_stats", port=port)["taps"][SPU_OUT_TAP]["frames"])
    wav = os.path.join(out_dir, "race.wav").replace("\\", "/")
    reply = psxdbg.send("audio_wav", port=port, path=wav, tap=SPU_OUT_TAP,
                        start=max(0, head - count), count=count)
    if not reply.get("ok"):
        raise SmokeFailure(f"audio_wav failed: {reply.get('err', reply)}")
    return wavcheck.wav_rms(wav)


def press_and_see_change(proc, port, out_dir, at_frame, button, name, deadline):
    psxrun.wait_frame(port, at_frame, deadline)
    psxrun.check_alive(proc)
    before = shot(port, out_dir, f"{name}-before", deadline)
    psxrun.press(port, button, frames=6)
    _, now = psxrun.read_frame(port, deadline)
    psxrun.wait_frame(port, now + 90, deadline)
    after = shot(port, out_dir, f"{name}-after", deadline)
    d = screen_diff(before, after)
    if d < SCREEN_DIFF_MIN:
        raise SmokeFailure(f"{button} at frame {at_frame} did not change the screen ({name}, diff {d:.3f})")
    return d


def run(proc, port, out_dir, deadline, min_fps):
    psxrun.wait_for_ping(proc, port, deadline)
    d_menu = press_and_see_change(proc, port, out_dir, START_FRAME, "start", "menu", deadline)
    d_mode = press_and_see_change(proc, port, out_dir, MENU_CROSS_FRAME, "cross", "championship", deadline)
    base_hits = engine_hits(port)
    d_drv = press_and_see_change(proc, port, out_dir, DRIVER_CROSS_FRAME, "cross", "driver", deadline)

    # The race has begun once the ENGINE overlay keeps running natively.
    while True:
        psxrun.check_alive(proc)
        if time.monotonic() > deadline:
            raise SmokeFailure("track ENGINE overlay never ran from the static shard")
        h0 = engine_hits(port)
        time.sleep(2.0)
        h1 = engine_hits(port)
        if h1 - h0 > 100 and h1 > base_hits:
            break
    _, race_frame = psxrun.read_frame(port, deadline)

    interp0 = interp_by_pc(port)
    _, f0 = psxrun.read_frame(port, deadline)
    psxrun.hold_buttons(port, "cross")
    shots = []
    try:
        t_end = time.monotonic() + RACE_SECS
        n = 0
        while time.monotonic() < t_end:
            psxrun.check_alive(proc)
            shots.append(shot(port, out_dir, f"race-{n:02d}", deadline))
            n += 1
            time.sleep(RACE_SECS / 5)
        rms = measure_rms(port, out_dir)
    finally:
        psxrun.release(port)
    _, f1 = psxrun.read_frame(port, deadline)
    interp1 = interp_by_pc(port)

    diffs = [screen_diff(a, b) for a, b in zip(shots, shots[1:])]
    if min(diffs) < SCREEN_DIFF_MIN:
        raise SmokeFailure(f"race picture stopped changing (diffs {[round(x, 3) for x in diffs]})")
    if rms < RMS_MIN:
        raise SmokeFailure(f"race is silent (SPU RMS {rms:.1f} < {RMS_MIN})")
    engine = engine_interp(interp1)
    if engine:
        raise SmokeFailure("ENGINE overlay ran interpreted at " +
                           ", ".join(f"0x{0x80000000 | pc:08X}" for pc in sorted(engine)))
    per_frame = game_interp(interp0, interp1) / max(1, f1 - f0)
    if per_frame > GAME_INTERP_INSNS_PER_FRAME_MAX:
        top = sorted(((n - interp0.get(pc, 0), pc) for pc, n in interp1.items() if pc >= 0x10000),
                     reverse=True)[:5]
        raise SmokeFailure(f"{per_frame:.0f} interpreted game insns/frame > {GAME_INTERP_INSNS_PER_FRAME_MAX}; "
                           "top " + ", ".join(f"0x{0x80000000 | pc:08X}:{n}" for n, pc in top))
    fps, rates = measure_fps(port, deadline)
    if min_fps and fps < min_fps:
        raise SmokeFailure(f"race runs at {fps:.1f} fps < {min_fps} (windows {[round(r, 1) for r in rates]})")
    return (f"menu_diff={d_menu:.2f} mode_diff={d_mode:.2f} driver_diff={d_drv:.2f} "
            f"race_frame={race_frame} engine_hits={engine_hits(port)} "
            f"game_interp_per_frame={per_frame:.0f} rms={rms:.0f} fps={fps:.1f} "
            f"race_diffs={[round(x, 2) for x in diffs]}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--exe", required=True)
    ap.add_argument("--cue", required=True)
    ap.add_argument("--port", type=int, default=psxdbg.DEFAULT_PORT)
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--out", default="")
    ap.add_argument("--game", default=os.path.join(REPO_ROOT, "game.toml"))
    ap.add_argument("--renderer", choices=("software", "opengl", "game"), default="software")
    ap.add_argument("--min-fps", type=float, default=0.0)
    args = ap.parse_args(argv)

    if psxdbg.port_in_use(args.port):
        return _fail(f"port {args.port} busy - another runtime running?")
    if not os.path.isfile(args.exe):
        return _fail(f"exe not found: {args.exe}")
    out_dir = os.path.abspath(args.out or os.path.join(
        os.environ.get("TEMP", REPO_ROOT), "mtgp-race-" + time.strftime("%Y%m%d-%H%M%S")))
    if not out_dir.isascii():
        return _fail(f"out dir must be an ASCII path: {out_dir}")
    os.makedirs(out_dir, exist_ok=True)
    print(f"race_smoke: out={out_dir}")

    try:
        game = renderer_toml(args.game, args.renderer, out_dir)
    except SmokeFailure as exc:
        return _fail(str(exc))
    proc = psxrun.launch(args.exe, args.cue, game, args.port, out_dir,
                         env_extra={"PSX_OVERLAY_AUTOCOMPILE_OFF": "1"})
    try:
        summary = run(proc, args.port, out_dir, time.monotonic() + args.timeout, args.min_fps)
        print(f"race_smoke: OK {summary}")
        return 0
    except (SmokeFailure, TimeoutError) as exc:
        return _fail(str(exc))
    except Exception as exc:  # noqa: BLE001 - keep the one-line contract
        return _fail(f"unexpected error: {type(exc).__name__}: {exc}")
    finally:
        psxrun.shutdown(proc, args.port)


if __name__ == "__main__":
    sys.exit(main())
