# First-boot installer

An **installer image** works like the MustardOS / muOS one: you write it to an SD card and boot the console once. It opens on a welcome screen with two square icon buttons side by side, **Install** (an arrow into a tray) and **Power off** (the power symbol). Choose Install and a popup asks which file system the **ROMS** partition should use (FAT32, exFAT or ext4); then a progress screen partitions the card and installs everything; when it finishes the device restarts into RG OS. Choose Power off and the console switches off without changing anything on the card.

| Control | On the welcome screen |
|---|---|
| D-pad left / right (up / down works too) | Move between Install and Power off |
| **A** (or START) | Confirm the highlighted button |

| Control | On the ROMS format popup |
|---|---|
| D-pad up / down (left / right works too) | Move between FAT32, exFAT and ext4 |
| **A** (or START) | Format ROMS with the highlighted file system and start installing |
| **B** | Go back to the welcome screen (nothing has been changed) |

| Format | Good for | Limits |
|---|---|---|
| FAT32 | Reads on every PC, Mac and console | A single file cannot be bigger than 4 GB |
| exFAT (default, recommended) | Windows, macOS and Linux, big files | None that matter for games |
| ext4 | Linux-native, journaled | Windows cannot read it without extra software; macOS needs a driver |

The choice only applies to a **new** ROMS partition. A card that already has a formatted ROMS partition keeps its file system, so existing games are never wiped. The popup does not appear on a card with no screen: the install runs on its own with exFAT.

If the console has no usable screen there is nothing to choose with, so the install runs on its own.

## Build

    sudo ./build.sh rg34xxsp installer      # out/rg34xxsp-rgos-installer.img
    sudo ./build.sh all installer           # all four devices

It takes the same environment variables as a normal image ([BUILDING.md](BUILDING.md)). Write the `.img` to the whole card like any other image ([GETTING-STARTED.md](GETTING-STARTED.md)).

## What the installer does

Everything below happens after you choose **Install**.

| Step | What happens |
|---|---|
| Partitioning the SD card | `rgos-roms` creates the **ROMS** partition in the free space after the system partitions and formats it with the file system you picked (exFAT by default; partition 3 on the H700 consoles, 4 on the RG Rotate). The old partition table is backed up to the boot partition. A card whose layout is not recognised is left alone and the installer reports it. |
| Creating folders | `roms/<system>/`, `saves/<system>/`, `states/<system>/`, `bios/`, `cores/`, `config/`, `music/`, `screenshots/`, `splash/`, `update/` and `artwork/`. |
| Installing Emulator cores | Every libretro core of the build (`cores`) is unpacked into `cores/` on ROMS, where the launcher and the Core Installer already look. |
| Installing PortMaster | Unpacked into `roms/ports/PortMaster`. If that folder already exists it is left alone, so a PortMaster that updated itself is never rolled back. |
| Installing Extra files | Only when the build had an `extras/` folder (below). |
| Finishing up | Writes `rgos-installed.json` on the boot partition, deletes the payload, restarts. |

RetroArch itself and the RG OS system are the `SYSTEM` file the console just booted from; they are not copied again. The payload is what lives *outside* it: the cores, PortMaster and your extras.

Nothing on the ROMS partition is ever deleted. Each archive is checked against its SHA-256 while it is unpacked.

## Your own files in the installer

Put files in an `extras/` folder next to `build.sh` before building. Its contents are unpacked into the **root of the ROMS partition**, for example `extras/bios/gba_bios.bin` or `extras/music/theme.mp3`. Only add files you may legally redistribute.

## Options

Create `rgos-install.txt` in the root of the boot partition (the small FAT one) before the first boot. One `key=value` per line:

| Key | Effect |
|---|---|
| `skip_install=1` | Never run the installer on this card; boot RG OS as it is |
| `keep_payload=1` | Keep `/rgos-payload` after a successful install |
| `skip=cores,portmaster` | Leave those components out (ids are the archive names in `/rgos-payload`) |

## If something fails

The screen stays up with the reason. **A** tries again, **B** starts RG OS without finishing (the installer runs again on the next boot). Components that already finished are remembered in `rgos-install-state.json`, so a retry continues where it stopped.

The log is `rgos-install-log.txt` on the boot partition (live: `/var/log/rgos-installer.log`; partitioning detail: `/var/log/rgos-roms.log`).

To reinstall later: with `keep_payload=1` set, delete `rgos-installed.json` from the boot partition and boot. Without it, flash the installer image again, or use the Core Installer and PortMaster itself.

To stop the installer for good on a card that keeps failing, delete the `rgos-payload` folder from the boot partition (or add `skip_install=1`).

## Files

| File | Where | Meaning |
|---|---|---|
| `rgos-payload/` | boot partition | Archives plus `manifest.json`; removed after a successful install |
| `rgos-installed.json` | boot partition | Build id, device, time, installed components; its presence means "installed" |
| `rgos-install-state.json` | boot partition | Components finished so far (only while an install is unfinished) |
| `rgos-install.txt` | boot partition | Your options (above) |
| `rgos-install-log.txt` | boot partition | Copy of the installer log |
| `rgos-roms-fs` | boot partition | The file system chosen for ROMS (`fat32`, `exfat` or `ext4`); `rgos-roms` reads it if the installer is interrupted before the partition is formatted |

## Notes

- The boot partition keeps the size of the stock ROCKNIX image, and the payload has to fit on it next to `SYSTEM`. `build.sh` stops with an error when it does not.
- Offline updates (`./build.sh <device> update`) are built the normal way and replace only `SYSTEM` and the boot files, so they work on an installed card.
- Code: `rgos/installer.py` (logic), `rgos/rgos-installer` (welcome screen, ROMS format popup and progress screens; exit status 10 = restart, 20 = power off), `tools/mkpayload.py` (payload packer), hook in `rgos/rgos-session`.
