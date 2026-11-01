# Motor Toon Grand Prix Recompiled

<!-- retcomm-readme-metrics -->
[![GitHub downloads (all assets, all releases)](https://img.shields.io/github/downloads/cr1tika7/MotorToonGrandPrixRecomp/total)](https://github.com/cr1tika7/MotorToonGrandPrixRecomp/releases)
[![GitHub downloads (latest release)](https://img.shields.io/github/downloads/cr1tika7/MotorToonGrandPrixRecomp/latest/total)](https://github.com/cr1tika7/MotorToonGrandPrixRecomp/releases/latest)
[![GitHub release](https://img.shields.io/github/v/release/cr1tika7/MotorToonGrandPrixRecomp)](https://github.com/cr1tika7/MotorToonGrandPrixRecomp/releases/latest)
<!-- /retcomm-readme-metrics -->

A native PC port of **Motor Toon Grand Prix** (PlayStation, 1996), made by
static recompilation: the game's MIPS code is translated to C and compiled
into a real Windows/Linux/macOS executable, linked against the
[psxrecomp](https://github.com/RetroPortingToolKit/psxrecomp) PS1 hardware
runtime and the [recomp-ui](https://github.com/RetroPortingToolKit/recomp-ui)
launcher. It is not an emulator image and contains no game data: you need your
own disc.

The framework is pinned to the fork
[cr1tika7/psxrecomp](https://github.com/cr1tika7/psxrecomp/tree/openbios-setconf-retail),
which adds one OpenBIOS fix on top of upstream: `SetConf` rebuilds the kernel
tables like the retail BIOS, so the Goodies programs can start
([docs/OPENBIOS_SETCONF.md](docs/OPENBIOS_SETCONF.md)).

| | |
|---|---|
| Game | Motor Toon Grand Prix (USA) |
| Serial | SCUS-94355 |
| Players | 1 (two-player mode needs a link cable, not supported) |
| Publisher | Sony Computer Entertainment |
| Year | 1996 |
| Status | **Preview** — boots, menus and Championship races run natively |

## Play

1. Download the zip for your platform from
   [Releases](https://github.com/cr1tika7/MotorToonGrandPrixRecomp/releases)
   and extract it anywhere.
2. Start `Motor_Toon_Grand_Prix_Recompiled.exe`.
3. On first start, select the `.cue` of your own **USA** disc dump
   (SCUS-94355). Other regions are not supported yet.

No BIOS dump is needed: the bundled open-source
[OpenBIOS](https://github.com/grumpycoders/pcsx-redux) (MIT) is used. Saves go
to memory-card files beside the executable and survive updates.

### Controls

Keyboard defaults (rebind in the launcher under **Controls**, or edit
`keybinds.ini`). Gamepads work out of the box.

| In game | PlayStation | Keyboard |
|---|---|---|
| Accelerate | Cross | X |
| Brake | Square | Z |
| Use item | Circle | S |
| Reverse | Triangle | A |
| Camera up / down | R2 / L2 | R / E |
| Rear view | L1 | Q |
| Steer / menus | D-pad | Arrow keys |
| Start / pause | Start | Return |

These are the game's default button assignments (Options → Controller
Settings), which the game lets you change.

## What works

Checked with the automated smoke tests in `tests/smoke` (see
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)):

- Boot logos, attract flyover and the title screen.
- Main menu, driver select, Replay Theater and Options; memory-card saves.
- A full Championship race start: countdown, driving, opponents, sound.
  All race code runs as native code, including the per-track `ENGINE`
  overlays the game streams from `MTGPX2.DAT`, which are compiled ahead of
  time.
- The three bonus programs in the **Goodies** menu (*Tank Combat*,
  *Submarine X*, *Motor Toon GP R*, unlocked after several championship wins)
  start and run, also as native code. Tested for 60 s each from their title
  screens; playing them through is not tested yet. They need the OpenBIOS fix
  in the framework fork above; with upstream psxrecomp they crash.
- Full speed with the default OpenGL renderer at 4x internal resolution:
  60 vblanks per second in a Championship race (RTX 3080, 2026-11-01). The
  game itself draws a new picture every 2–4 vblanks, as its own frame rate.
  The CPU-side software renderer reached 35–60 on the same PC.

Not supported:

- **Two Player Battle.** The game has no split screen: this mode links two
  consoles with a link cable over the serial port (SIO1). The runtime does not
  emulate that port, so the menu entry stays greyed out, as on a console
  without a cable.

Please report problems with your platform, GPU and the steps that lead to them.

<!-- retcomm-readme-launcher -->
## Retro Launcher

You can run this title **standalone** (download the release zip, point it at
your disc, play), or manage installs, updates, and disc/BIOS wiring with
**[Retro Launcher](https://github.com/RetroPortingToolKit/Retro-Launcher)** —
the Retro Compilation Manager hub for self-compiling recomps.

[Downloads](https://github.com/RetroPortingToolKit/Retro-Launcher/releases) ·
[Full README & features](https://github.com/RetroPortingToolKit/Retro-Launcher#readme)

<p align="center">
  <img src="https://raw.githubusercontent.com/RetroPortingToolKit/Retro-Launcher/main/docs/screenshots/hub-and-game-launcher.png" alt="Retro hub with a background build, next to a title’s recomp-ui launcher" width="720">
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/RetroPortingToolKit/Retro-Launcher/main/docs/screenshots/queue-and-background-build.png" alt="Background cmake build with titles queued" width="720">
</p>

Retro checks for updates, installs the prebuilt release zips, and automates
BIOS/ROM/save plumbing so you are not stuck repeating each game’s first run by hand.
<!-- /retcomm-readme-launcher -->

## Legal

You must own the original game. Disc images are never part of this repository
or its releases. Retail BIOS dumps are not redistributed and no C derived from
one is committed; releases run on the bundled MIT OpenBIOS.

`generated/` holds the recompiled game C and **is committed**: release CI
builds the shipped executable from it. Regenerate and commit it whenever seeds,
`aot/overlays.json` or the framework pin change.

Motor Toon Grand Prix is a trademark of Sony Interactive Entertainment. This
project is not affiliated with or endorsed by Sony or Polyphony Digital.

Default app icon: `assets/psxrecomp.ico` (and `.png` / `.svg`) — Retro-themed
controller mark from `psxrecomp/assets/`. Windows builds embed it via `APP_ICON`.

## Building from source

Full workflow, tests and debugging notes: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

```bash
git clone --recurse-submodules https://github.com/cr1tika7/MotorToonGrandPrixRecomp.git
cd MotorToonGrandPrixRecomp
./psxrecomp/tools/ci/build_emitters.sh
# Only needed after changing seeds, aot/overlays.json or the framework pin:
python3 psxrecomp/psxrecomp_cli.py generate \
  --config game.toml --project-root . --disc "/path/to/Motor Toon Grand Prix.cue"
python3 psxrecomp/psxrecomp_cli.py rebuild \
  --config game.toml --project-root . --build-dir build-release --no-pgo
```

Releases: run the *Release builds* workflow on GitHub (or push a `vX.Y.Z`
tag). CI builds the committed `generated/` C on Linux, Windows and macOS and
attaches `mtgp-<version>-<platform>.zip`. Locally:
`scripts/package_release.sh build-release windows-x64`.

## Framework pins

Submodule gitlinks (`psxrecomp`, `recomp-ui`, nested `recomp-net`) are
authoritative. `framework_pins.txt` is an optional scaffold snapshot; release
CI logs SHAs with `record_pins.sh` but builds whatever the gitlinks resolve
to. Bump submodules deliberately and regenerate `generated/` afterwards.

<!-- retcomm-readme-raid -->
---

<p align="center">
  <sub><b>R.A.I.D. — Retro AI Development</b> · a Discord for AI-assisted retro reverse-engineering, decomp &amp; recomp</sub>
</p>

<p align="center">
  <a href="https://discord.gg/Ad9BwSzctP"><img src=".github/raid-discord.png" alt="Join the Retro AI Development (R.A.I.D.) Discord" width="200"></a>
</p>
<!-- /retcomm-readme-raid -->
