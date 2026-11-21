# Build options

    sudo ./build.sh <device> [image|installer|update]

`device` is `rg34xxsp`, `rg35xxh`, `rg35xxsp`, `rg-rotate` or `all`. With no device the script only prints usage. Output goes to `out/`; work files go to `work/<device>/`.

`installer` builds a first-boot installer image (`out/<device>-rgos-installer.img`): PortMaster, the libretro cores and the optional `extras/` folder travel as a payload that the device installs on its first boot ([INSTALLER.md](INSTALLER.md)).

The stock ROCKNIX image is cached in `work/<device>/` and is not downloaded again on later builds. `sudo ./build.sh update-img [device]` (or `./build.sh <device> update-img`) deletes the cached copy and downloads it again without building. Changing `ROCKNIX_URL`, `ROCKNIX_H700_VERSION` or `H700_RAM` selects a different cached file by name, so it downloads that one the first time.

## Host requirements

Root (or `sudo`), and: `debootstrap`, `losetup`, `mksquashfs`/`unsquashfs`, `wget`, `gunzip`, `md5sum`, `python3`, `readelf`, `sfdisk`, `truncate`, plus `sgdisk` for the RG Rotate and `qemu-aarch64-static` when the host is not arm64. On Debian/Ubuntu: `apt install debootstrap qemu-user-static binfmt-support squashfs-tools wget gdisk dosfstools`. Plan for tens of GB of disk and a long run ([BUILD-WORKFLOW.md](BUILD-WORKFLOW.md)).

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `H700_RAM` | `DDR4` | `DDR4` or `DDR3`; must match the console (H700 devices) |
| `RG34XXSP_DTB` | `sun50i-h700-anbernic-rg34xx-sp` | or `...-v2-panel` |
| `RG35XXH_DTB` | `sun50i-h700-anbernic-rg35xx-h` | or `...-rev6-panel` |
| `RG35XXSP_DTB` | `sun50i-h700-anbernic-rg35xx-sp` | or `...-rev6-panel` |
| `ROCKNIX_H700_VERSION` | `20261001` | ROCKNIX release tag for the H700 base image |
| `ROCKNIX_URL` | per device | Full URL of the stock `.img.gz`; not with `all` |
| `DEBIAN_SUITE`, `DEBIAN_MIRROR` | `trixie`, deb.debian.org | Root filesystem source |
| `EXTRA_PKGS` | empty | Extra Debian packages, space separated |
| `PSX_REPO`, `GENESIS_REPO`, `NGP_SRC` | libretro upstreams | Sources of the cores built from source |
| `STELLA_REPO`, `ATARI800_REPO`, `PROSYSTEM_REPO` | libretro upstreams | Sources of the Atari 2600 (`stella2014`), 5200 (`atari800`) and 7800 (`prosystem`) cores; `none` skips that core |
| `GC_REPO` | libretro/dolphin | RG Rotate only; `none` skips GameCube ([GAMECUBE.md](GAMECUBE.md)) |
| `PORTMASTER` | `1` | `0` leaves PortMaster out |
| `PORTMASTER_URL`, `PORTMASTER_ZIP` | latest release / none | Where to get PortMaster; a local zip builds offline |
| `RGOS_INITRD` | `1` | `0` keeps ROCKNIX's own init ([TROUBLESHOOTING.md](TROUBLESHOOTING.md)) |
| `UPDATE_ID` | timestamp | Build id of an update tar |
| `UPDATE_EXTLINUX`, `UPDATE_DTB` | `0` | Include `extlinux.conf` / `dtb.img` in an update tar ([UPDATES.md](UPDATES.md)) |

Pass variables through sudo with `sudo -E`, for example `H700_RAM=DDR3 sudo -E ./build.sh rg35xxh`.

## Prebuilt cores

Any aarch64 `*_libretro.so` placed in `cores/` is copied into the image. `dolphin_libretro.so` is removed again for every device except `rg-rotate`.

## Bundled content

- `music/`: launcher music baked into the image ([LAUNCHERS-AND-THEMES.md](LAUNCHERS-AND-THEMES.md)).
- `config/`: RetroArch configs, one per device family, and the RG OS gamepad autoconfig.
- `rgos/`: the launcher, input hub, session scripts and tools.
- `initramfs/`: the RG OS initramfs and extlinux patcher.
