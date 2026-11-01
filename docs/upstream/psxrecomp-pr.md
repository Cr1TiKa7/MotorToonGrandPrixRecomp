# PR draft: RetroPortingToolKit/psxrecomp

Source: `Cr1TiKa7/psxrecomp` branch `openbios-setconf-retail` (commit `6197b8a1`).
Target: `RetroPortingToolKit/psxrecomp` `master` (`a7b37e07`).
Compare: https://github.com/RetroPortingToolKit/psxrecomp/compare/master...Cr1TiKa7:psxrecomp:openbios-setconf-retail

If the nugget PR is merged first, the better follow-up is to re-pin OpenBIOS to that
upstream commit with the same procedure, instead of carrying `bios/openbios-setconf.patch`.

---

**Title:** OpenBIOS: rebuild the kernel tables in SetConf like the retail kernel

**Body:**

Motor Toon Grand Prix (USA) launches three bonus programs through a relay
loader that relies on A0:9Ch SetConf to drop the main program's IRQ handlers.
OpenBIOS's SetConf only stored its arguments, so the kernel later jumped
through handler nodes the new program had overwritten
(`DISPATCH FATAL: misaligned target 0x7FFF7FFF`). The OpenBIOS fix is
proposed upstream in pcsx-redux/nugget; this PR re-pins the bundled image
built with it.

What changed:
- `bios/openbios.bin`: pcsx-redux `55fbf04` + `bios/openbios-setconf.patch`,
  same toolchain and recipe as before (`9333c043…`). Built without the patch,
  the recipe reproduces the previous image byte for byte (`fabe498f…`).
- `bios/OpenBIOS.toml` (+ `overlay_toolchain/` copy): hash, both copy windows
  (ROM text grew by 0x20: shell blob 0xA500 → 0xA520, kernel ramtext LMA
  0xBFC1E4D4 → 0xBFC1E4F4). Kernel RAM code addresses and the install slots did
  not move.
- Seeds: the 6 empirical dispatch-miss seeds relocated by content match,
  then `gen_bios_seeds_from_elf.py` regenerated (648). Run against the old ELFs, the
  same generator reproduces the previous seed set exactly.
- `generated/OpenBIOS_*.c` regenerated with `psxrecomp-bios`, plus the
  emitter stamp. The four skipped data sites are the same ones, moved. With the
  old profile, regeneration differed only in line endings.
- Native OpenBIOS read job: `cdromBlockReading`, `testEvent` and the kernel
  words it checks are byte-identical, so only the audited hash moved
  (cmake, both tests, doc). `.gitignore` allows `bios/*.patch`.

Tests:
- `runtime/tests/test_openbios_read_job.py`: 10 scenarios match.
- `runtime/tests/test_openbios_read_selection.py`: 10 configurations pass.
- `recompiler/tests/test_uncached_fetch_charge.py`: PASS, 17 559 instructions.
- Motor Toon Grand Prix: boot, menus and a Championship race pass, and all
  three bonus programs run 60 s each. Release builds for Windows, Linux and
  macOS (arm64, x64) pass in CI on the title repo.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
