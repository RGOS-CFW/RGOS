# Logs and diagnostic files

## On the boot partition (readable on a PC)

| File | Written | Holds |
|---|---|---|
| `rgos-initramfs.txt` | by the initramfs at boot | Kernel command line, partition found, `/proc/partitions`, last step reached |
| `rgos-bootinfo.txt` | 6 s after switch_root | Early boot state |
| `rgos-logs.txt` | at 8, 28 and 58 s after boot | Combined copy of the main logs below |
| `rgos-retroarch.txt` | after every RetroArch game | Command, missing libraries, attempt logs, exit code or signal, kernel hints |
| `rgos-native.txt` | after every native port / PortMaster run | Command, exit code, run time, missing tools, last 150 lines of `rgos-native.log` |
| `rgos-image-info.txt` | at build | Which build and RAM type the image was made for |
| `rgos-update.id` | after an update | Installed build id |
| `rgos-mbr-backup.bin` / `rgos-gpt-backup.bin` | first boot | Partition table before ROMS was created |

## On the device (`/var/log/`)

`rgos-menu.log`, `rgos-input.log`, `rgos-launch.log`, `rgos-native.log`, `rgos-retroarch.log`, `rgos-roms.log`, `rgos-installer.log`, `rgos-artwork.log`, `rgos-wifi.log`, `rgos-gamemenu.log`, `rgos-update.log`. Many of these are bundled into `rgos-logs.txt`.

## Reporting a problem

Attach `rgos-logs.txt` (and `rgos-retroarch.txt` or `rgos-native.txt` if a game or port is involved), say which device and which image you built (RAM type and panel for the H700 consoles), and describe what you did. Join the Discord for help.
