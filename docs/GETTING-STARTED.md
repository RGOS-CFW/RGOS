# Getting started

## What you need

- A supported console: RG34XXSP, RG35XX H, RG35XX SP or RG Rotate (see [DEVICES.md](DEVICES.md)).
- A microSD card. 16 GB or more is sensible; the rest of the card becomes your ROMS partition.
- A flashing tool such as balenaEtcher, Raspberry Pi Imager or `dd`.
- An RG OS image for your device (`<device>-rgos.img`), either built yourself ([BUILDING.md](BUILDING.md), [BUILD-WORKFLOW.md](BUILD-WORKFLOW.md)) or provided by a release.

## 1. Pick the right image

| Device | Image | Things to check first |
|---|---|---|
| RG34XXSP | `rg34xxsp-rgos.img` | RAM type (DDR4 or DDR3), panel revision |
| RG35XX H | `rg35xxh-rgos.img` | RAM type, panel revision |
| RG35XX SP | `rg35xxsp-rgos.img` | RAM type, panel revision |
| RG Rotate | `rg-rotate-rgos.img` | Flash the SPL once ([RG-ROTATE-SPL.md](RG-ROTATE-SPL.md)) |

The three H700 consoles ship their U-Boot on the card, built for one RAM type. A wrong choice gives a black screen. If you are unsure which RAM type your console has, start with DDR4 (the default) and use the table in [TROUBLESHOOTING.md](TROUBLESHOOTING.md) if the screen stays black.

## 2. Flash the card

1. If the image is `.img.gz`, decompress it first.
2. Flash the `.img` to the whole card (not to a partition). This erases everything on the card.
3. Eject the card cleanly. An unclean eject is a common cause of a card that does not boot.

## 3. First boot

- An **installer image** (`*-rgos-installer.img`) shows an RG OS Installer screen on the first boot with two square **Install** and **Power off** buttons (D-pad to choose, **A** to confirm). Install partitions the card, installs PortMaster and the cores, then restarts by itself; Power off switches the console off and leaves the card as it is. Do not switch the console off while an install is running ([INSTALLER.md](INSTALLER.md)). The points below describe a normal image.

- Insert the card and power on. Fully power off first if the console was running another system.
- On the first boot RG OS creates the **ROMS** partition in the free space after the system partitions and formats it as exFAT (partition 3 on the H700 consoles, partition 4 on the RG Rotate). This is done by `rgos-roms` and logged in `/var/log/rgos-roms.log`. It only touches a card whose layout it recognises, and it backs up the old partition table to the boot partition (`rgos-mbr-backup.bin` or `rgos-gpt-backup.bin`).
- PortMaster is copied to `roms/ports/PortMaster` on the first boot where that folder is missing.
- The startup splash plays once at power on (it can be changed in *Settings > Startup splash*).

## 4. Add games

Put the card in a PC and copy ROMs into the folders under `roms/` on the ROMS partition, one folder per system. For example `roms/gba/`, `roms/snes/`, `roms/psx/`. The full table is in [SYSTEMS.md](SYSTEMS.md); the overall layout is in [SD-CARD-LAYOUT.md](SD-CARD-LAYOUT.md).

You can also copy files over the network once Wi-Fi is set up ([NETWORKING.md](NETWORKING.md)).

Back on the device, press **X** in the launcher to rescan. Systems with no games and no installed core are hidden.

## 5. Optional first steps

- *Settings > Missing BIOS check* tells you which BIOS files your systems still need ([BIOS.md](BIOS.md)).
- *Settings > Wi-Fi*, then *Settings > Game artwork* for cover art ([ARTWORK.md](ARTWORK.md)).
- *Settings > Theme* and *Settings > Launcher* to change the look ([LAUNCHERS-AND-THEMES.md](LAUNCHERS-AND-THEMES.md)).
- *Settings > Swap A / B buttons* if confirm and back feel reversed.

## If it does not boot

Take the card to a PC and look for the evidence files on the boot partition; [TROUBLESHOOTING.md](TROUBLESHOOTING.md) explains each one.
