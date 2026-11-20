# NES / Famicom (RetroArch + Nestopia core)

On every supported device NES runs through RetroArch with the **Nestopia** libretro core, installed from the Debian `libretro-nestopia` package (`EMU_PKGS` in `build.sh`). *Settings > Emulators* offers whichever other NES core is installed (fceumm, quicknes, mesen).

* ROMs: `<ROMS>/roms/nes/*.nes` (also `.unf`, `.unif`).
* Famicom Disk System: `.fds` games plus `disksys.rom` in `<ROMS>/bios/` ([BIOS.md](BIOS.md)).
* Saves: `<ROMS>/saves/nes/`, states: `<ROMS>/states/nes/`.
* Your own RetroArch overrides: `<ROMS>/config/retroarch.cfg` (appended last, wins over everything).
* Hotkeys while playing: [CONTROLS.md](CONTROLS.md).
