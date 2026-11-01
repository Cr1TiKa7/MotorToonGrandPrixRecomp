"""Exploration driver: boot the dev build, follow a timed input script, take
screenshots and sample native/interpreted dispatch counters.

py -3 tools/explore.py --out DIR --script "3:start,6:cross,..." [--secs 120] [--shot-every 3]
         [--exe build-dev/Motor_Toon_Grand_Prix_Recompiled.exe] [--cue PATH] [--game game.toml]
Actions: button names joined with '+', 'hold:<btns>:<secs>', 'turbo:on', 'turbo:off',
'poke:<addr>:<byte>' (one write_ram byte, e.g. poke:0x800E4576:1).
The cue defaults to %MTGP_CUE% (set by D:/RecompDev/dev-env.ps1).
"""

import argparse
import json
import os
import sys
import time

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(REPO, "tests", "smoke"))

import psxdbg  # noqa: E402
import psxrun  # noqa: E402

EXE = os.path.join(REPO, "build-dev", "Motor_Toon_Grand_Prix_Recompiled.exe")


def counters(port):
    status = psxdbg.send("overlay_loader_status", port=port)
    dirty = psxdbg.send("dirty_ram_stats", port=port)
    return {
        "native_dll": int(status.get("dispatch_native", 0)),
        "interp": int(status.get("dispatch_interp_fallback", 0)),
        "insns": int(dirty.get("insns_run", 0)),
    }


def parse_script(text):
    steps = []
    for part in filter(None, (p.strip() for p in text.split(","))):
        t, action = part.split(":", 1)
        steps.append((float(t), action))
    return sorted(steps)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--script", default="")
    ap.add_argument("--secs", type=float, default=90)
    ap.add_argument("--shot-every", type=float, default=3)
    ap.add_argument("--port", type=int, default=4370)
    ap.add_argument("--autocompile", choices=("on", "off"), default="off")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--exe", default=EXE)
    ap.add_argument("--cue", default=os.environ.get("MTGP_CUE", ""))
    ap.add_argument("--game", default=os.path.join(REPO, "game.toml"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    env = {"PSX_OVERLAY_AUTOCOMPILE_OFF": "1"} if args.autocompile == "off" else {}
    proc = psxrun.launch(args.exe, args.cue, args.game, args.port, args.out, env_extra=env)
    log = []
    try:
        psxrun.wait_for_ping(proc, args.port, time.monotonic() + 60)
        t0 = time.monotonic()
        steps = parse_script(args.script)
        next_shot = 0.0
        n = 0
        while True:
            now = time.monotonic() - t0
            if now > args.secs:
                break
            psxrun.check_alive(proc)
            while steps and steps[0][0] <= now:
                _, action = steps.pop(0)
                if action.startswith("turbo:"):
                    psxdbg.send("turbo", port=args.port, enabled=1 if action.endswith("on") else 0)
                elif action.startswith("hold:"):
                    _, btns, secs = action.split(":")
                    psxrun.hold_buttons(args.port, *btns.split("+"))
                    time.sleep(float(secs))
                    psxrun.release(args.port)
                elif action.startswith("poke:"):
                    _, addr, val = action.split(":")
                    psxdbg.send("write_ram", port=args.port, addr=addr, val=int(val, 0))
                else:
                    psxrun.press(args.port, *action.split("+"), frames=6)
                log.append({"t": round(now, 1), "action": action})
            if now >= next_shot:
                try:
                    frame = int(psxdbg.send("frame", port=args.port)["frame"])
                    shot = os.path.join(args.out, f"s{n:03d}_t{int(now):03d}_f{frame}.png")
                    psxrun.screenshot(args.port, shot)
                    c = counters(args.port)
                    log.append({"t": round(now, 1), "frame": frame, "shot": os.path.basename(shot), **c})
                except psxrun.TRANSIENT + (psxrun.SmokeFailure,) as exc:
                    log.append({"t": round(now, 1), "error": str(exc)})
                n += 1
                next_shot += args.shot_every
            time.sleep(0.1)
        dirty = psxdbg.send("dirty_ram_stats", port=args.port)
        rows = sorted(dirty.get("per_pc", []), key=lambda r: -int(r.get("insns", 0)))
        log.append({"top_interp": rows[:args.top]})
    finally:
        psxrun.shutdown(proc, args.port)
        with open(os.path.join(args.out, "explore.json"), "w") as fh:
            json.dump(log, fh, indent=1)
    for entry in log:
        if "top_interp" in entry:
            print("top interpreted PCs:")
            for r in entry["top_interp"]:
                print("  ", {k: r.get(k) for k in ("pc", "hits", "insns", "entries", "ext_ra")})
        else:
            print(entry)


if __name__ == "__main__":
    main()
