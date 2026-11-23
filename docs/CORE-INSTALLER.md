# Core Installer

*Tools > Core Installer* downloads RetroArch cores that are not installed yet, so you can add alternative emulators for your systems (gpSP or VBA-M for GBA, PicoDrive for Sega, SwanStation for PlayStation, FinalBurn Neo for Arcade, Flycast for Dreamcast, YabaSanshiro for Saturn, ParaLLEl N64 for Nintendo 64, fake-08 or retro8 for PICO-8 and so on) without rebuilding the image.

It needs a network connection first: see [NETWORKING.md](NETWORKING.md).

## Using it

The list shows every compatible core for the systems on this device, with the ones you do not have first. Each row shows the core, the systems it runs (for example `GBA, GB`) and its state.

| Button | Action |
|---|---|
| Up / Down | Select a core |
| L / R | Page up / down |
| A | Install the selected core |
| X | Reinstall the selected core: download it again and replace your copy (see below) |
| B | Back (while a download runs: cancel it) |

**Reinstall (X)** works on cores you downloaded, the ones that have their own `<name>_libretro.so` in the `cores` folder on the ROMS card (the row shows *X Reinstall* when it is selected). Use it to get a fresh copy of a core that misbehaves, a damaged file, or a newer nightly build. The new file is downloaded and checked first and only then swapped in, so a failed or cancelled reinstall leaves the working core in place. Cores that ship in the system image are read-only and are not replaced; pressing X on one says so.

When an install finishes, the menu rescans: a system that had no core appears straight away, and the new core is selectable in *Settings > Emulators*.

A system whose only compatible core is missing (for example Arcade and Neo Geo without FinalBurn Neo) is hidden from the Games list until you install one. It is listed in the Core Installer like any other.

## Where cores go

Downloaded cores are written to `<ROMS>/cores/<name>_libretro.so` on the ROMS card. The system image is read-only, and this folder survives reboots and updates. The menu and `rgos-launch` look there after the built-in core folders. Delete a file there to remove a core, or copy your own `*_libretro.so` into the folder by hand.

Only cores that are not already installed are offered, so a downloaded core never replaces one that ships in the image. GameCube's Dolphin core is not offered: it needs data files that only the RG Rotate image carries ([GAMECUBE.md](GAMECUBE.md)).

## Where they come from

The libretro buildbot, `https://buildbot.libretro.com/nightly/linux/aarch64/latest/<core>_libretro.so.zip`. To use a mirror or your own folder with the same layout, set `RGOS_CORE_URL` or put `{"url": "https://..."}` in `/etc/rgos/coreinstall.json`.

Each download is checked before it is installed: the zip must contain exactly `<core>_libretro.so`, the file must be an ELF library for this CPU, and it is written under a temporary name and renamed into place, so a failed or cancelled download never leaves a half-written core.

## Errors

| Message | Meaning |
|---|---|
| Can't reach the server. Check Wi-Fi in Settings | No network, or the server is down |
| Not available for this device | The buildbot has no build of that core for aarch64 |
| Not enough free space on the ROMS card | Free some space and try again |
| That core is built for a different CPU | The mirror serves the wrong architecture |

A core can install fine and still fail to start if it needs a library that is missing from the image. `rgos-retroarch.txt` on the boot partition lists the missing libraries ([LOGS.md](LOGS.md)).
