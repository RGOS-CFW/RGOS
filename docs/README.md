# RG OS documentation

RG OS is a Debian-based emulation distribution for Anbernic handhelds (RG34XXSP, RG35XX H, RG35XX SP and RG Rotate), built on the ROCKNIX kernel and device trees.

## Start here

| If you want to... | Read |
|---|---|
| Install RG OS on an SD card and boot it the first time | [GETTING-STARTED.md](GETTING-STARTED.md) |
| Build a first-boot installer image (partitions the card and installs PortMaster and the cores) | [INSTALLER.md](INSTALLER.md) |
| Check what is different between the four supported devices | [DEVICES.md](DEVICES.md) |
| Know where to put ROMs, saves, BIOS files and music | [SD-CARD-LAYOUT.md](SD-CARD-LAYOUT.md) |
| See which systems, file types and cores are supported | [SYSTEMS.md](SYSTEMS.md) |
| Add missing BIOS files | [BIOS.md](BIOS.md) |
| Learn the buttons and hotkeys | [CONTROLS.md](CONTROLS.md) |
| Change the theme, launcher, splash or music | [LAUNCHERS-AND-THEMES.md](LAUNCHERS-AND-THEMES.md) and [SETTINGS.md](SETTINGS.md) |
| Use Wi-Fi, Bluetooth or SSH / SFTP | [NETWORKING.md](NETWORKING.md) |
| Connect a TV or monitor over mini-HDMI on an H700 handheld | [HDMI.md](HDMI.md) |
| Flash the SPL on an RG Rotate | [RG-ROTATE-SPL.md](RG-ROTATE-SPL.md) |
| Fix something that does not work | [TROUBLESHOOTING.md](TROUBLESHOOTING.md), [LOGS.md](LOGS.md), [FAQ.md](FAQ.md) |

## Reference by feature

- [IN-GAME-MENU.md](IN-GAME-MENU.md): the Menu-button panel while a game runs
- [ARTWORK.md](ARTWORK.md): cover art from SteamGridDB
- [PORTS.md](PORTS.md): native Linux ports and PortMaster
- [CORE-INSTALLER.md](CORE-INSTALLER.md): download more RetroArch cores
- [NES.md](NES.md), [GAMECUBE.md](GAMECUBE.md): system-specific notes
- [HDMI.md](HDMI.md): H700 mini-HDMI setup, resolution, audio and troubleshooting
- [UPDATES.md](UPDATES.md): offline `.tar` updates
- [BUILDING.md](BUILDING.md): every build option in one place
- [BUILD-WORKFLOW.md](BUILD-WORKFLOW.md): building in GitHub Actions

## Conventions used in these docs

- **ROMS** is the large exFAT partition on the card (`/media/roms` on the device). **Boot partition** is the small FAT partition labelled `RGOS` (`/boot` on the device).
- Button names follow the RG OS Gamepad layout: A bottom, B right, X left, Y top. If A and B feel swapped, see *Swap A / B buttons* in [SETTINGS.md](SETTINGS.md).
- **Menu** is the hub's Mode button.
- Device ids used in commands: `rg34xxsp`, `rg35xxh`, `rg35xxsp`, `rg-rotate`.
