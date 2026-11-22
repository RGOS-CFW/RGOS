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
| Sega Dreamcast | `dreamcast` | flycast | `.cdi` `.gdi` `.chd` `.cue` `.m3u` |
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

`build.sh` installs these Debian libretro packages: gambatte, mgba, snes9x, nestopia and beetle-wswan. It also builds, best effort, the PlayStation core (pcsx_rearmed), Genesis Plus GX, the Neo Geo Pocket core and the three Atari cores (stella2014 for the 2600, atari800 for the 5200, prosystem for the 7800) from source, plus Dolphin on the RG Rotate. A failed source build is reported with a `!!` line and the image is built without that core.

Systems that the build does not provide a core for (for example Arcade/Neo Geo with FinalBurn Neo) only appear when you supply the core yourself: put a prebuilt aarch64 `<name>_libretro.so` in `cores/` before building, or install a Debian package with `EXTRA_PKGS` ([BUILDING.md](BUILDING.md)). The menu lists a system only when a compatible core is present.

## Dreamcast

`build.sh` builds Flycast as an **OpenGL ES** core (`DC_REPO=none` skips it; `DC_MAKE_ARGS` changes the make arguments). RetroArch on this image is a GLES build, and the libretro buildbot Flycast (what *Tools > Core Installer* downloads) is desktop-OpenGL only: it closes right after launch with `Requesting OpenGL context, but RetroArch is compiled against OpenGLES`. The image's own core is looked up before the one on the ROMS card, so it wins. Without a GLES Flycast, put one in `cores/` on the ROMS card (it must be built with `FORCE_GLES=1`).

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
