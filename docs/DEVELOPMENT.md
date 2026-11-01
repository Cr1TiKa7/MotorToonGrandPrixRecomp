# Entwicklung

Kurzreferenz für die Arbeit an MotorToonGrandPrixRecomp. Allgemeine Erfahrungen für weitere
PS1-Ports stehen außerhalb des Repos in `D:\RecompDev\PS1_RECOMP_NOTES.md`.

## Umgebung

Jede neue PowerShell-Sitzung lädt zuerst die Umgebung:

```powershell
. D:\RecompDev\dev-env.ps1
Set-Location D:\RecompDev\MotorToonGrandPrixRecomp
```

`dev-env.ps1` liegt bewusst außerhalb des Repos (maschinenspezifisch). Es setzt TEMP, Toolchain- und
Cache-Variablen auf D: und `MTGP_CUE` = Pfad zur Disc (USA, SCUS-94355).

- Toolchain: `cmake-clang-v1` (Clang 22, CMake, Ninja) unter `D:\RecompDev\Toolchain`.
- Python: Windows-natives `py -3` (≥ 3.11).
- `.gitattributes` erzwingt LF. Ohne sie bricht Windows PowerShell 5.1 in Framework-Skripten an Gits
  LF/CRLF-Warnungen ab.
- `game.toml` enthält bewusst nur `disc = "disc/Motor Toon Grand Prix.cue"`. Die echte Disc wird
  per `--disc` übergeben (Generate, Tests) oder im Launcher gewählt.

## Disc

| | |
|---|---|
| Serial | SCUS-94355 (USA) |
| Boot-EXE | `SCUS_943.55`, Ladeadresse `0x80010000`, Entry `0x80010530`, Text `0x9A800` |
| Datentrack | 568 967 616 Bytes, MD5 `82cdb35aceed9c3a7b255e8b999b1536`, SHA-256 `2a3c8bc7…519f` |
| Tracks | 1 (Single-Track-Dump; Musik liegt als XA im Datentrack) |

Inhalt (54 Dateien): `MTGPX2.DAT` (Datenpaket mit eigenem Inhaltsverzeichnis, 76 Einträge),
`MUSIC0-4.XA`, `VOICE0-1.XA`, `MOVIE/*.STR` (19 Filme), `R.EXE`, `SUB/SUB.EXE`, `TANK/TANK.EXE`.

## Code erzeugen und bauen

```powershell
# Spiel-C aus der Disc neu erzeugen, inkl. statischer Overlays (danach generated/ committen)
py -3 psxrecomp\psxrecomp_cli.py generate --config game.toml --project-root . --disc $env:MTGP_CUE

# Release (ohne Debug-Server) -> build-release\Motor_Toon_Grand_Prix_Recompiled.exe
py -3 psxrecomp\psxrecomp_cli.py rebuild --config game.toml --project-root . --build-dir build-release --no-pgo --no-toolchain-download

# Entwicklung (Debug-Server auf Port 4370) -> build-dev\Motor_Toon_Grand_Prix_Recompiled.exe
py -3 psxrecomp\psxrecomp_cli.py rebuild --config game.toml --project-root . --build-dir build-dev --no-pgo --no-toolchain-download --cmake-extra=-DPSX_DEBUG_TOOLS=ON
```

- Der Name der `.exe` folgt dem `WINDOW_TITLE` in `CMakeLists.txt`.
- Generate erzeugt ~4,1 Mio. Zeilen Spiel-C (112 Shards) plus ~140 MB statische Overlays. Ein Build
  dauert mit 32 Jobs etwa 5–10 Minuten.

## Tests

```powershell
pwsh -File tools/run-smoke.ps1 -Build dev -Test boot   # erstes echtes Bild (~15 s)
pwsh -File tools/run-smoke.ps1 -Build dev -Test race   # Menü -> Championship -> Rennen (~2 min)
pwsh -File tools/run-smoke.ps1 -Build dev -Test all
```

| Test | Prüft |
|---|---|
| `boot` | Debug-Port antwortet, Bildzähler läuft, ein Screenshot mit ≥ 16 Farben. |
| `race` | Ohne Runtime-Autocompile (`PSX_OVERLAY_AUTOCOMPILE_OFF=1`), Software-Renderer. START öffnet das Hauptmenü, CROSS die Fahrerwahl, CROSS das Rennen (Bildwechsel nach jedem Druck). Das Strecken-`ENGINE`-Overlay läuft aus dem statischen Shard (`overlay_static_entries` im Bereich `0x801F2000–0x801F4000`) und nie interpretiert. 20 s Gas: Bild ändert sich, SPU hörbar (RMS ≥ 200), interpretierte Spielbefehle ≤ 3000 pro Bild (gemessen: 7). Bildrate wird nur gemeldet (`--min-fps` macht sie zur Bedingung). Leistungsprüfung auf freiem Rechner: `--renderer game --min-fps 57` (OpenGL, gemessen 60,0). |

- Ausgaben (Log, Screenshots, Speicherkarten, WAV) landen unter `D:\RecompDev\Temp\mtgp-<test>-<Zeit>\`.
- Die Testschritte sind in emulierten Bildern getaktet (`START_FRAME` usw. in `race_smoke.py`), nicht
  in Sekunden. Ein langsamer Rechner verlängert nur die Laufzeit.
- `race` nutzt standardmäßig den Software-Renderer (eigene `game.toml`-Kopie im Ausgabeordner), damit
  fremde GPU-Last den Test nicht ausbremst. `--renderer opengl` oder `game` für den echten Pfad.
- Debug-Builds brechen nach 4 s ohne Emulations-Herzschlag ab. Der HLE-Boot öffnet bei Zyklus ~150 das
  Disc-Image und braucht auf einem ausgelasteten Rechner länger. `psxrun.launch` setzt deshalb
  `PSX_STARVATION_TIMEOUT_US=30000000`. Release-Builds haben diesen Watchdog nicht.
- Gemeinsame Helfer: `tests/smoke/psxdbg.py` (TCP-Client), `psxrun.py` (Start, Tasten, RAM, Beenden),
  `pngcheck.py` (Farben, Bilddifferenz), `wavcheck.py` (Lautstärke).

### Erkunden

```powershell
py -3 tools/explore.py --out D:\RecompDev\Temp\mtgp-explore --secs 70 --shot-every 1.5 --script "18:start,30:cross,36:cross"
py -3 tools/montage.py D:\RecompDev\Temp\mtgp-explore\sheet.png 6 2 (Get-ChildItem D:\RecompDev\Temp\mtgp-explore\s0*.png)
```

`explore.py` startet den Dev-Build, drückt Tasten zu festen Sekunden, macht Screenshots und
schreibt `explore.json` mit Bildzähler, interpretierten Dispatches und den meistinterpretierten PCs.
`montage.py` baut daraus einen Kontaktbogen (ohne Pillow).

Menütasten gehen verloren, wenn sie während einer Einblendung kommen. 1,5–2 s Abstand und ein
Screenshot nach jedem Druck sind verlässlicher.

## Spielablauf und Menüs

- Nach dem Boot: SCEA-Logo, Polys-Logo, Flug über die Insel (Attract), Titel. START öffnet das
  Hauptmenü (Emulationsbild ~870).
- Hauptmenü: Championship Race, Single Race, Time Attack, Free Run, Two Player Battle,
  Replay Theater, Options, Goodies. Von „Championship Race“ aus springt HOCH zu „Goodies“.
- Championship Race → Fahrerwahl (Captain Rock, Princess Jean, Bolbox, Penguin Bros., Raptor & Raptor,
  Vanity, Billy the Tough, Ching Tong Chang) → Streckenkarte „Toon Island II“ → Countdown → Rennen.
- Goodies: alle Einträge zeigen anfangs „????“ / „Not Yet!“. Sie werden durch Spielfortschritt
  freigeschaltet.
- Replay Theater → „Create Video Folder“ legt den Spielstand `BASCUS-94355VIDEO` (2 Blöcke) an.

Standard-Tastenbelegung im Spiel (Options → Controller Settings): Gas ×, Bremse □, Item ○,
Rückwärts △, Kamera hoch R2, Kamera runter L2, Rückspiegel L1.

## Overlays vorab nativ (`aot/overlays.json`)

Das Spiel ist im Kern eine große EXE. Nachgeladen wird nur wenig Code, alles wird vorab kompiliert:

| Image | Quelle | Adresse | Wann |
|---|---|---|---|
| Strecken-`ENGINE` (11 verschiedene, `opening` = `island`) | `MTGPX2.DAT`, Einträge `tracks/*/ENGINE` | `0x801F2000` | jede Strecke, auch im Attract-Flug |
| Relay-Loader `boot/boot.exe` | `MTGPX2.DAT` | `0x801C0000` | Programmwechsel aus Goodies |
| `R.EXE` („Motor Toon GP R“) | Disc-Datei, nur Code bis `0x8007D3D0` | `0x80010000` | Goodies |
| `SUB/SUB.EXE`, `TANK/TANK.EXE` | Disc-Dateien (`psx_exe`) | `0x80010000` / `0x80020000` | Goodies |

So lädt das Spiel ein Overlay (Funktionsadressen in `SCUS_943.55`):

1. Der Strecken-Lader `0x80010F00` baut `"%s/ENGINE"` und ruft `LoadEngine` (`0x80025F00`).
2. `LoadExeFromPack` (`0x8001E91C`) sucht den Namen in der Tabelle von `MTGPX2.DAT` und prüft den
   „SCE EXE“-Header (`0x8001E7E8`). Dann liest es das Image nach `exec.t_addr`.
3. FlushCache, dann `jalr exec.pc0` (`0x80025F70`) mit `$a0` = Host-Tabelle `0x8008B2B0`.
4. Der Einstieg trägt 5 Callbacks in die Tabelle ein (+0, +4, +8, +C, +0x68), die der Host per `jalr`
   ruft (`0x80025F9C`, `0x80025FDC`, `0x80026008`, `0x80026034`, `0x80026060`).

Die Overlays rufen nie direkt in die Host-EXE, nur über Zeiger in dieser Tabelle. Der Heap endet vor
dem Slot (`lui 0x801F; ori 0x2001` bei `0x800110AC`).

**Programmwechsel (Goodies, `0x8004CB28`):** lädt `boot/boot.exe` nach `0x801C0000` und baut argv
`{"BOOT.EXE", "TANK\TANK.EXE" | "SUB\SUB.EXE" | "R.EXE"}`. Dann springt ein Trampolin (`0x80010490`)
mit Stack `0x801FFFF0` hinein. `boot.exe` löscht `0x80010000–0x801C0000`, lädt die PS-X-EXE und springt.
SUB und TANK kehren per BIOS-`LoadExec("cdrom:\SCUS_943.55;1")` zurück.

Besonderheiten im Profil:
- `R.EXE` ist ein `fixed_address_extents`-Eintrag nur über den Code (`0x80010000..0x8007D3D0`: Spielcode
  plus fünf BIOS-Thunks `li t2,0xA0; jr t2; li t1,n`). Dahinter liegen Strings und Tabellen. Als ganze
  EXE (`psx_exe`) dekodierte der Static-Compiler 88 Datenfragmente, die das Audit ablehnte
  („No original-input guard proof“, ungültige Branch-Kodierung im Delay-Slot). `generic_exclude_files`
  verhindert, dass der generische Detektor R.EXE trotzdem als ganze EXE aufnimmt.
- `night_r` und `island_r` haben dieselbe Adresse und Größe (`0x1320`). Die Pipeline benennt Extents
  nach `Datei@Adresse+Größe`, das kollidierte. `night_r` ist deshalb um ein Null-Wort (NOP-Padding)
  auf `0x1324` erweitert.
- `"allow_missing": true`, weil der generische Detektor die Container-Images nicht selbst findet.

Prüfen ohne Build:

```powershell
py -3 psxrecomp\tools\aot_overlay_pipeline.py extract --profile aot\overlays.json --game-toml game.toml --recompiler build-recompiler\psxrecomp-game.exe --work-dir D:\RecompDev\Temp\mtgp-aot-work
```

Erwartet: `Verified 15 images / 15 recipes`.

## Bekannte Restpunkte

- Recompiler-Hinweis `mid-function split pre-pass did NOT converge after 256 passes`: einzelne
  Sprungziele mitten in Funktionen bleiben Dispatch-Misses (interpretiert). Im Rennen gemessen:
  7 interpretierte Spielbefehle pro Bild, vernachlässigbar. Häufigster Fall: `0x80082794`
  (gerufen von `0x8006CA8C`).
- Interpretiert laufen außerdem die BIOS-Patch-Slots im Kernel-RAM (`0x27B4`, `0x281C`). Das ist
  Absicht des Frameworks (`psxrecomp/docs/dynamic_handler_install.md`).
- **Goodies-Programme brauchen das gepatchte OpenBIOS.** Mit dem OpenBIOS des Upstream-Frameworks
  (`a7b37e07`) stürzen sie ab: TANK nach ~1 s (`DISPATCH FATAL: misaligned target 0x7FFF7FFF`),
  SUB (`unknown dispatch 0x28202820`), R nach ~8 s (`misaligned target 0xAAAAAAAA`). Ursache: `boot.exe`
  ruft `SetConf` (A0:9Ch) und verlässt sich darauf, dass der Kernel wie beim Retail-BIOS seine Tabellen neu
  aufbaut. OpenBIOS speicherte nur die drei Werte, die Interrupt-Handler des Hauptspiels blieben eingehängt.
  Fix und Re-Pin: [OPENBIOS_SETCONF.md](OPENBIOS_SETCONF.md). Damit laufen alle drei Programme
  (`-Test goodies`). Das Projekt pinnt deshalb den Fork (nächster Abschnitt).

### Framework-Fork

`psxrecomp` zeigt auf `https://github.com/cr1tika7/psxrecomp.git`, Branch `openbios-setconf-retail`
(= Upstream `a7b37e07` + der OpenBIOS-Commit `6197b8a1`). Im Submodul ist `origin` der Fork und
`upstream` das Original. Upstream nachziehen:

```powershell
git -C psxrecomp fetch upstream
git -C psxrecomp rebase upstream/master          # Konflikte meist nur in generated/OpenBIOS_*.c
```

Danach den OpenBIOS-C-Code neu erzeugen (Schritte 3–9 in [OPENBIOS_SETCONF.md](OPENBIOS_SETCONF.md)),
weil sich Emitter oder Profil upstream geändert haben können. Dann `git -C psxrecomp push --force-with-lease`,
Spielcode neu generieren, Tests laufen lassen und den neuen Submodul-Stand committen. Sobald Upstream den Fix
übernommen hat, `.gitmodules` wieder auf `RetroPortingToolKit/psxrecomp` stellen und `git submodule sync`.
- **Bildrate** (2026-11-01, RTX 3080, ohne Fremdlast): OpenGL mit 4x interner Auflösung 60,0 VBlanks/s im
  Rennen (`race_smoke --renderer game`), Software-Renderer 35. `frame_perf` meldet ~51 ms pro *Spielbild*,
  nicht pro VBlank: Laut `gp1_dump` (GP1 05h, Display-Start) zeigt das Spiel im Rennen alle 2–4 VBlanks ein
  neues Bild (15–30 Bilder/s, eigene Bildrate des Spiels). Mit AION2/Roblox im Hintergrund fiel OpenGL auf 18–25.
- Splitscreen ist noch nicht geprüft.

### Goodies testen

Freischalt-Flags (Bytes in der Spielstand-Struktur bei `0x800E4550`, Magic „MTG2“, Funktion `0x8004CDE8`):
`0x800E4576` Tank Combat, `0x800E4577` Submarine X, `0x800E4578` Motor Toon GP R (≠ 0 = frei;
`0x800E4574` Extra Characters ≠ 0, `0x800E4575` Additional Tracks ≥ 6). Ablauf: Hauptmenü, Flags per
`write_ram` setzen, HOCH (Goodies), KREUZ, RUNTER ×2/×3/×4, KREUZ, im Dialog LINKS (Discard), KREUZ.

Automatisch: `pwsh -File tools/run-smoke.ps1 -Build dev -Test goodies` (`tests/smoke/goodies_smoke.py`,
je Programm 60 s: Bildzähler läuft, kein `FATAL` im Log, Bild ändert sich, Programmcode läuft nativ aus dem
statischen Shard). Einzeln: `py -3 tests/smoke/goodies_smoke.py --exe … --cue … --program tank|sub|r`.
Gemessen 2026-11-01 mit gepatchtem OpenBIOS: statische Dispatches TANK +1,4 Mio., SUB +10,6 Mio.,
R +7,2 Mio. in je 60 s.

Von Hand:

```powershell
py -3 tools/explore.py --out D:\RecompDev\Temp\mtgp-tank --secs 95 --shot-every 3 --script "20:start,28:poke:0x800E4576:1,30:up,35:cross,41:down,43:down,46:cross,50:left,53:cross"
```

## Debug-Port

Nur im Dev-Build. Pro TCP-Verbindung eine JSON-Zeile hin, eine zurück, z. B. `{"id":1,"cmd":"ping"}`.
Python: `tests/smoke/psxdbg.py`. Befehlsreferenz: `psxrecomp/docs/TCP_COMMANDS.md`.

Nützlich für diesen Port:
- `overlay_static_entries` mit `addr_lo/addr_hi` (welches statische Overlay lief),
  `overlay_loader_status` (`static_checks`, `static_hits`, `dispatch_interp_fallback`).
- `dirty_ram_stats` mit `lo/hi` → `per_pc` (was interpretiert läuft, mit Aufrufer `ext_ra`).
- `frame_perf`, `phase_profile`, `gcp_ring key=fn` (Leistung).
- `screenshot` liefert `display disabled` bei schwarzem Zwischenbild: weiter pollen.

## Was nie ins Repo gehört

Disc-Images, BIOS-Dumps, Logs, `overlay_captures.json` (enthält Spielcode), Savestates und
Speicherkarten. Die `.gitignore` deckt das ab. Vor jedem Commit trotzdem `git status` prüfen.
