# PR draft: pcsx-redux/nugget

Target: `pcsx-redux/nugget` `main`. Patch: `patches/openbios-setconf-nugget.patch` (applies to `5414bd9`
and `42483d7`). Ready as commit `6e469155` on branch `openbios-setconf-retail` in
`D:\RecompDev\upstream\nugget` (builds with GCC 16.1.0); push it to a nugget fork, then open the PR.

---

**Title:** openbios: rebuild the kernel tables in SetConf like the retail kernel

**Body:**

`setConfiguration` (A0:9Ch, SetConf) only stores the event count, thread count
and stack base. The retail kernel rebuilds its tables there: it frees all
ExCBs, EvCBs and TCBs (every exception handler, event and thread except the
running one), allocates new ones and installs the default handlers again
(psx-spx, "SetConf"). PCSX-ReARMed's HLE BIOS does the same: `psxBios_SetConf`
runs its boot-time table setup and returns with interrupts enabled.

Chain loaders depend on this. Motor Toon Grand Prix (USA, SCUS-94355) starts
its bonus programs (`TANK\TANK.EXE`, `SUB\SUB.EXE`, `R.EXE`) through a relay
loader that calls StopPAD, ResetEntryInt, SetConf and FlushCache, then loads
the new PS-X EXE over the main program. It never dequeues the main program's
IRQ handlers itself. Under OpenBIOS those handlers stay linked; once the new
program overwrites their memory, the kernel exception handler jumps into it
(observed targets 0x7FFF7FFF, 0x28202820 and 0xAAAAAAAA).

Change:
- Move the table setup from `kernelSetup()` into `initKernelTables()`;
  `kernelSetup()` prints its banner and calls it, so boot is unchanged.
- `setConfiguration()` stores the values, enters a critical section and
  calls `initKernelTables()`. That ends in
  `initializeCDRomHandlersAndEvents()`, which leaves the critical section, so
  SetConf returns with interrupts enabled. psx-spx does not say what happens to
  interrupts; this matches PCSX-ReARMed (`SR |= 0x401` after `setup_tt`).

Testing: built with `g++-mipsel-none-elf` 16.1.0. With the same change on
pcsx-redux `55fbf04`, all three Motor Toon Grand Prix bonus programs start and
run (60 s each) in a static recompilation that runs this OpenBIOS (PSXRecomp).
The main game's boot, menus and races are unaffected. Not compared against a
retail BIOS on hardware.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
