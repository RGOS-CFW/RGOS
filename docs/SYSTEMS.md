# Supported systems

Put games in `<ROMS>/roms/<folder>/`. Systems whose core is not installed are hidden, and so is GameCube on every device except the RG Rotate. A system with no games still shows up if its core is installed.

| System | Folder | Default core | File types |
|---|---|---|---|
| Game Boy Advance | `gba` | mgba | `.gba` |
| Game Boy | `gb` | gambatte | `.gb` |
| Game Boy Color | `gbc` | gambatte | `.gbc` |
| NES / Famicom | `nes` | nestopia | `.nes` `.unf` `.unif` |
| SNES | `snes` | snes9x | `.sfc` `.smc` `.swc` `.fig` `.bs` |
| Mega Drive / Genesis | `genesis` | genesis_plus_gx | `.md` `.gen` `.smd` `.bin` |
| Master System | `mastersystem` | genesis_plus_gx | `.sms` |
| Game Gear | `gamegear` | genesis_plus_gx | `.gg` |
| SG-1000 / SC-3000 | `sg1000` | genesis_plus_gx | `.sg` `.sc` `.sf` |
| Sega CD / Mega-CD | `segacd` | genesis_plus_gx | `.cue` `.chd` `.iso` `.m3u` `.ccd` |
| Sega 32X | `sega32x` | genesis_plus_gx | `.32x` `.md` `.gen` `.smd` `.bin` |
| Sega Pico | `segapico` | genesis_plus_gx | `.pico` `.bin` |
| Nintendo 64 | `n64` | mupen64plus_next | `.z64` `.n64` `.v64` `.u64` `.ndd` |
| Sega Dreamcast | `dreamcast` | flycast | `.cdi` `.gdi` `.chd` `.cue` `.m3u` |
| Sega Saturn | `saturn` | yabasanshiro | `.cue` `.chd` `.iso` `.m3u` `.ccd` `.mds` |
| Atari 2600 | `atari2600` | stella2014 | `.a26` `.bin` |
| Atari 5200 | `atari5200` | atari800 | `.a52` `.bin` `.car` |
| Atari 7800 | `atari7800` | prosystem | `.a78` `.bin` |
| Neo Geo Pocket | `ngp` | mednafen_ngp | `.ngp` `.ngc` `.ngpc` |
| Neo Geo Pocket Color | `ngpc` | mednafen_ngp | `.ngc` `.ngpc` `.ngp` |
| WonderSwan | `ws` | mednafen_wswan | `.ws` `.wsc` `.pc2` |
| WonderSwan Color | `wsc` | mednafen_wswan | `.wsc` `.ws` `.pc2` |
| PlayStation | `psx` | pcsx_rearmed | `.cue` `.chd` `.pbp` `.m3u` `.iso` `.img` `.ccd` |
| GameCube (Rotate only) | `gc` | dolphin | `.gcm` `.iso` `.gcz` `.rvz` `.ciso` `.m3u` `.dol` `.elf` |
| Arcade (FinalBurn Neo) | `arcade` | fbneo | `.zip` `.7z` |
| Neo Geo | `neogeo` | fbneo | `.zip` `.7z` |
| Ports | `ports` | native | `.sh` |

Files that start with `.` are ignored.

## Which cores ship in the image

`build.sh` installs these Debian libretro packages: gambatte, mgba, snes9x, nestopia and beetle-wswan. It also builds, best effort, the PlayStation core (pcsx_rearmed), Genesis Plus GX, the Neo Geo Pocket core the three Atari cores (stella2014 for the 2600, atari800 for the 5200, prosystem for the 7800), Flycast, Mupen64Plus-Next and YabaSanshiro (Saturn) from source, plus Dolphin on the RG Rotate. A failed source build is reported with a `!!` line and the image is built without that core.

Systems that the build does not provide a core for (for example Arcade/Neo Geo with FinalBurn Neo) only appear when you supply the core yourself: put a prebuilt aarch64 `<name>_libretro.so` in `cores/` before building, or install a Debian package with `EXTRA_PKGS` ([BUILDING.md](BUILDING.md)). The menu lists a system only when a compatible core is present.

## Nintendo 64

`build.sh` builds Mupen64Plus-Next (`mupen64plus_next`) as an **OpenGL ES** core, for the same reason as Flycast below: RetroArch on this image is a GLES build and a desktop-OpenGL core closes right after launch. `N64_REPO=none` skips it, `N64_MAKE_ARGS` changes the make arguments (default `platform=unix FORCE_GLES=1`; the ARM64 dynarec is picked automatically on aarch64) and `N64_REQUIRED=1` stops the build when the core fails to build. The image's own core is looked up before the one on the ROMS card. ParaLLEl N64 (`parallel_n64`) is listed as an alternative core and can be added with *Tools > Core Installer* or by putting a GLES build in `cores/`.

Put ROMs in `roms/n64/` as `.z64`, `.n64` or `.v64` (any byte order works), or `.ndd` for 64DD disks. No BIOS is needed. The system runs with the CPU and GPU clocks pinned to `performance` while a game is running. Many games need the right stick: turn on *DPAD to joystick* ([SETTINGS.md](SETTINGS.md)) if your console has no sticks. Speed varies a lot between games and consoles; the RG35XX H and similar H700 consoles will not run every title at full speed. The video driver can be forced with `retroarch-n64-video.txt` ([SD-CARD-LAYOUT.md](SD-CARD-LAYOUT.md)).

## Saturn

Put discs in `roms/saturn/` (`.cue` with its `.bin` tracks next to it, `.chd`, `.iso`, `.mds`, or `.m3u` for multi-disc games). The image has exactly one Saturn core pre-installed, YabaSanshiro (the best fit for ARM handhelds), built by `build.sh` from `SATURN_REPO` (`SATURN_REPO=none` skips it, `SATURN_MAKE_DIR` / `SATURN_MAKE_ARGS` change the build, `SATURN_REQUIRED=1` stops the build when it fails). The alternatives, Yabause and Beetle Saturn, are not in the image: install them from *Tools > Core Installer*, or drop a `<name>_libretro.so` into `cores/` on the ROMS card, then pick one in *Settings > Emulators*. If the YabaSanshiro build fails, the image has no Saturn core and the Saturn menu entry stays hidden until you install one. The CPU and GPU clocks are pinned to `performance` while a game runs. BIOS files are listed in [BIOS.md](BIOS.md).

## Dreamcast

`build.sh` builds Flycast as an **OpenGL ES** core (`DC_REPO=none` skips it; `DC_MAKE_ARGS` changes the make arguments). RetroArch on this image is a GLES build, and the libretro buildbot Flycast (what *Tools > Core Installer* downloads) is desktop-OpenGL only: it closes right after launch with `Requesting OpenGL context, but RetroArch is compiled against OpenGLES`. The image's own core is looked up before the one on the ROMS card, so it wins. Without a GLES Flycast, put one in `cores/` on the ROMS card (it must be built with `FORCE_GLES=1`).

**Standalone Flycast.** Besides the libretro core, Dreamcast can run the standalone Flycast emulator. It shows up as **Flycast (standalone)** in *Settings > Emulators* once a `flycast` executable is found in `/usr/local/bin`, `/usr/bin`, `/opt/flycast` or `cores/standalone/` on the ROMS card; the libretro core stays the default until you pick it. RG OS starts it itself (no RetroArch): the game's file is passed on the command line, Select + Start held stops it like a native port, and its output goes to `rgos-native.log` / `rgos-native.txt`. Its settings live on the ROMS card in `config/flycast/` (data in `config/data/flycast/`), and `bios/dc/` is linked in as its BIOS folder, so the BIOS Manager files are shared. RetroArch features (RetroArch's own menu, its save states, overlays and `retroarch.cfg` overrides) do not apply to it; use Flycast's own settings. `build.sh` builds it from `DC_REPO` as an OpenGL ES program and installs `/usr/local/bin/flycast` (`DC_STANDALONE=0` skips it, `DC_SA_CMAKE_ARGS` adds CMake arguments, `DC_SA_REQUIRED=1` stops the build when it fails). It is not on the Core Installer list: a program cannot be fetched from the libretro buildbot, so to add your own build put a GLES `flycast` executable in `cores/standalone/`.

Put discs in `roms/dreamcast/`, one folder per game is fine. Use `.gdi` (keep its track files next to it), `.cdi`, `.chd`, or `.cue`/`.m3u` for multi-disc games. Only the disc file is listed, not the track files. The system runs with the CPU and GPU clocks pinned to `performance` while a game is running, and it is demanding: on the RG35XX H and similar H700 consoles many games will not reach full speed. A real BIOS is optional ([BIOS.md](BIOS.md)).

## Choosing another core

*Settings > Emulators* lists each system and the installed cores that are compatible with it. Compatible alternatives include, for example, gpsp / vbam for GBA, sameboy for Game Boy, fceumm / quicknes / mesen for NES, bsnes variants for SNES, picodrive for Sega systems, and swanstation / mednafen_psx for PlayStation. Only cores that are actually installed appear. *Tools > Core Installer* downloads the ones you do not have yet ([CORE-INSTALLER.md](CORE-INSTALLER.md)).

## Multi-disc games

Use an `.m3u` playlist for PlayStation, Sega CD and GameCube multi-disc games, and keep the playlist next to the disc images. Prefer `.chd` over a pile of `.bin` / `.cue` files.

## Notes

- `.bin` is shared by Genesis, 32X, Pico and Atari systems. Keep each system's files in its own folder.
- `.iso` is shared by Sega CD, PlayStation and GameCube. Keep Wii dumps out of `roms/gc`; Wii is not supported.
- Many systems need BIOS files ([BIOS.md](BIOS.md)).
- System-specific notes: [NES.md](NES.md), [GAMECUBE.md](GAMECUBE.md), [PORTS.md](PORTS.md).

**Dreamcast says `Requesting OpenGL context, but RetroArch is compiled against OpenGLES`?** The `flycast_libretro.so` on the ROMS card is a desktop-GL build. The image build had no GLES Flycast to ship (see `flycast-build.log` in the build work folder; `DC_REQUIRED=1` stops the build when that happens), and the Core Installer no longer downloads the buildbot Flycast. Delete `cores/flycast_libretro.so` from the card, fix the build error and rebuild, or put a `FORCE_GLES=1` build in `cores/`.
