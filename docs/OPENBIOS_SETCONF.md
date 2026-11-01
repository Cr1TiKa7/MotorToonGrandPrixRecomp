# OpenBIOS SetConf (A0:9Ch) does not reset the kernel

Status: fixed locally, not yet upstream (2026-11-01).

## Symptom

Motor Toon Grand Prix (USA, SCUS-94355) launches three separate programs from
its Goodies menu: `TANK\TANK.EXE`, `SUB\SUB.EXE` and `R.EXE`. Under OpenBIOS
each one starts and then crashes within seconds:

| Program | Runtime report |
|---|---|
| Tank Combat | `DISPATCH FATAL: misaligned target 0x7FFF7FFF` after ~1 s |
| Submarine X | `FAIL-FAST unknown dispatch: addr=0x28202820` |
| Motor Toon GP R | `DISPATCH FATAL: misaligned target 0xAAAAAAAA` after ~8 s |

Each time the kernel exception handler (`$ra` = `0x293C`) walks its interrupt
handler chain and jumps through a node whose memory the new program has
overwritten.

## Cause

The game's relay loader `boot/boot.exe` (loaded to `0x801C0000` from
`MTGPX2.DAT`) calls StopPAD (B0:14h), ResetEntryInt (B0:18h),
**SetConf (A0:9Ch)** and FlushCache, then reads the target PS-X EXE over the
main program and jumps to it. It never removes the main program's IRQ
handlers itself. It relies on SetConf to do that.

On the retail kernel, SetConf rebuilds the kernel tables. psx-spx documents
that it frees all ExCBs, EvCBs and TCBs (so every exception handler, event and
thread except the current one is lost) and installs the default exception
handlers. PCSX-ReARMed's HLE BIOS implements it the same way:
`psxBios_SetConf` runs the boot-time table setup (`setup_tt`: kernel heap,
ExCB/EvCB/PCB/TCB, default chains, syscall handler, CD-ROM IRQ and events) and
returns with interrupts enabled.

OpenBIOS's `setConfiguration` (`openbios/main/main.c`) only stores the three
values. The main program's handler nodes stay linked, the new program reuses
their memory, and the next interrupt goes into the weeds.

## Fix

`patches/openbios-setconf-nugget.patch` (for pcsx-redux/nugget `openbios/`;
the same change for pcsx-redux `55fbf04` is `psxrecomp/bios/openbios-setconf.patch`):

- Move the table setup out of `kernelSetup()` into `initKernelTables()`
  (heap, handler arrays, syscall/IRQ handlers, events, threads, RCnt IRQs,
  CD-ROM handlers and events). `kernelSetup()` prints its banner and calls it.
- `setConfiguration()` stores the values, enters a critical section and calls
  `initKernelTables()`. That function ends in `initializeCDRomHandlersAndEvents()`,
  which leaves the critical section, so SetConf returns with interrupts enabled,
  as on retail and in PCSX-ReARMed.

The patch applies to nugget `5414bd9` (2026-10-31) and builds with the
pinned toolchain.

## Rebuilding and re-pinning in psxrecomp

Done on local branch `openbios-setconf-retail` of the `psxrecomp` submodule
(commit `6197b8a1`, not pushed):

1. Build the pinned OpenBIOS. Without the patch, the result is byte-identical to the
   pinned image (`fabe498f…`):
   pcsx-redux `55fbf0468345acfbe5512628a3be5c0cfe3f22e7` (sparse `src/mips`),
   uC-sdk `69e06871824e2d62069487a7426ded09090ceb69` in `third_party/uC-sdk`,
   `g++-mipsel-none-elf-16.1.0` (distrib.app/alias/pcsx-redux/mips-toolchain, includes `make`),
   `make -C src/mips/openbios PREFIX=mipsel-none-elf FORMAT=elf32-littlemips`.
2. Apply the patch and rebuild. The new image (`9333c043…`) adds 0x20 bytes of ROM text:
   - functions from `0xBFC06A8C` on move by +0x30;
   - the shell blob moves from ROM `0xA500` to `0xA520`, the kernel ramtext LMA from
     `0xBFC1E4D4` to `0xBFC1E4F4`;
   - kernel RAM code addresses do not move. 31 words change (pointers and immediates into ROM),
     none of them in the install slots.
3. `bios/OpenBIOS.toml` (and the `overlay_toolchain/` copy): new SHA-256 and copy windows.
4. Relocate the 6 empirical dispatch-miss seeds by content match (+0x30 / +0x20), then
   regenerate the seeds with `tools/gen_bios_seeds_from_elf.py` (648 seeds).
5. `psxrecomp-bios --config bios/OpenBIOS.toml`, then
   `cmake -DROOT=. -DPROFILE=bios/OpenBIOS.toml -P tools/bios_emitter_fingerprint.cmake > generated/OpenBIOS.emitter.sha`.
   The generator skips the same four data sites as before, moved.
6. The native CD read job is bound to the image hash. `cdromBlockReading`
   (`0xBFC03A78`), `testEvent` (`0xBFC0574C`) and the kernel words the job checks
   are byte-identical, so only the audited hash moves:
   - `cmake/psx_openbios_read_job.cmake`,
   - `runtime/tests/test_openbios_read_job.py`,
   - `runtime/tests/test_openbios_read_selection.py` (including its corrupted-hash prefix),
   - `docs/performance/openbios-read-job.md`.

## Verification

- `tests/smoke/goodies_smoke.py`: Tank Combat, Submarine X and Motor Toon GP R
  each run 60 s, frame counter advancing, no FATAL, program code native from
  the static AOT shard. Screens checked: title and control screens of Tank and
  Submarine, R logo and race.
- `tools/run-smoke.ps1 -Test all` (boot, menus, Championship race) passes.
- Framework tests:
  - `runtime/tests/test_openbios_read_job.py`: 10 scenarios match.
  - `runtime/tests/test_openbios_read_selection.py`: 10 configurations pass.
  - `recompiler/tests/test_uncached_fetch_charge.py`: PASS, 17 559 BIOS instructions compared.
- Not checked against a retail BIOS (none on this machine).
