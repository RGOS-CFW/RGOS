# BIOS files

RG OS does not ship BIOS files. Put the ones you need in `<ROMS>/bios/` (RetroArch's system directory). *Settings > Missing BIOS check* scans your systems, shows what is missing and where each file goes, and tells you when a file's checksum differs from the expected one.

Names are matched exactly, then without regard to upper/lower case (a case-only match is reported and still found by the check, but fix the name to be safe).

| System | File | Needed |
|---|---|---|
| Game Boy Advance | `gba_bios.bin` | only for the gpsp core |
| Game Boy / Color | `gb_bios.bin`, `gbc_bios.bin` | optional boot ROMs |
| NES | `disksys.rom` | only for `.fds` disk games |
| Master System | `bios_E.sms`, `bios_U.sms`, `bios_J.sms` | optional |
| Game Gear | `bios.gg` | optional |
| Sega CD / Mega-CD | `bios_CD_U.bin`, `bios_CD_E.bin`, `bios_CD_J.bin` | required (one for your region) |
| Dreamcast | `dc/dc_boot.bin`, `dc/dc_flash.bin` | optional: Flycast has a built-in replacement BIOS, but the real one is more compatible (the standalone Flycast uses the same files) |
| Atari 5200 | `5200.rom` | required |
| Atari 7800 | `7800 BIOS (U).rom`, `7800 BIOS (E).rom` | optional |
| Neo Geo | `neogeo.zip` (leave zipped) | required |
| PlayStation | `scph5501.bin` (USA), `scph5502.bin` (Europe), `scph5500.bin` (Japan) | required for the mednafen and swanstation cores; pcsx_rearmed can run without |
| GameCube | `dolphin-emu/Sys/GC/<USA\|EUR\|JAP>/IPL.bin` | optional (boot logo) |

"Required" is judged per core: a file needed by one core is only flagged when that core is the one selected for the system. If several files serve the same purpose (for example the three Sega CD regions), having one of them satisfies the check.

You are responsible for obtaining BIOS files legally, for example by dumping them from hardware you own.
