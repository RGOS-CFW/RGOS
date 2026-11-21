# SD card layout

## Partitions

| Partition | Label | Filesystem | Mounted at | Contents |
|---|---|---|---|---|
| 1 | `RGOS` | FAT | `/boot` | Kernel, `SYSTEM` (the Debian squashfs), `rgos-initrd.cpio`, device tree, `extlinux/`, evidence and log files |
| 2 | stock | from the stock image | not used for your files | Part of the stock ROCKNIX layout; leave it alone |
| 3 (H700) or 4 (Rotate) | `ROMS` | exFAT | `/media/roms` | Your games and data |

Older cards may still carry the stock `ROCKNIX` label on partition 1.

## The ROMS partition

    ROMS/
      roms/<system>/        game files, one folder per system (see SYSTEMS.md)
      roms/ports/           native ports and PortMaster
      bios/                 emulator BIOS files (see BIOS.md)
      cores/                RetroArch cores downloaded by Tools > Core Installer (see CORE-INSTALLER.md)
      saves/<system>/       in-game saves
      states/<system>/      save states
      screenshots/          RetroArch screenshots
      artwork/<system>/     cover art (see ARTWORK.md)
      music/                your launcher music (searched recursively)
      update/               offline update .tar files (see UPDATES.md)
      config/retroarch.cfg  your own RetroArch overrides, appended last
      rgos-data/            RG OS data, e.g. steamgriddb-key.txt
      favorites.txt         your favourites list

Folders such as `saves/`, `states/`, `bios/` and `screenshots/` are created when a game is first launched. You do not need to create them.

## Files you can drop on the boot partition

Put the card in a PC; the boot partition is the small FAT one.

| File | Effect |
|---|---|
| `rgos-governor.txt` | CPU/GPU governor while a native port runs (`default` keeps the stock one). See [PORTS.md](PORTS.md) |
| `retroarch-gc-video.txt` | Force the GameCube video driver: `glcore`, `gl` or `vulkan`. See [GAMECUBE.md](GAMECUBE.md) |
| `ssh-password.txt` | Custom root password for SSH. See [NETWORKING.md](NETWORKING.md) |
| `authorized_keys` or `authorized_keys.txt` | SSH public keys for key login |

Files RG OS writes there for diagnosis are listed in [LOGS.md](LOGS.md).
