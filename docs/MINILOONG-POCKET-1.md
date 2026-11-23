# MiniLoong Pocket 1

| | |
|---|---|
| Argument | `miniloong` |
| SoC | Rockchip RK3566, 1 GB RAM |
| Screen | 4", 960x720 (4:3) |
| Input | D-pad, ABXY, L1/R1, L2/R2, Select/Start/Menu, **one analog stick (left)** |
| Base image | `AURKNIX-RK3566.aarch64-<tag>-Specific.img.gz` from AveyondFly/distribution_rocknix (default tag `20260809`) |
| Partition table | MBR, ROMS is created on first boot as partition 3 |

## Build

    sudo ./build.sh miniloong            # SD card image   -> out/miniloong-rgos.img
    sudo ./build.sh miniloong installer  # first-boot installer image
    sudo ./build.sh miniloong update     # offline update tar

Options: `ROCKNIX_RK3566_VERSION=<release tag>`, `MINILOONG_DTB=<name without .dtb>` (default `miniloong`),
`ROCKNIX_URL=<image .img.gz>`.

## How it boots

The Rockchip image selects its device tree with the `FDT` line of `extlinux/extlinux.conf` (the AURKNIX how-to edits it
by hand). The build finds `miniloong.dtb` on the stock boot partition and rewrites that line, then applies the normal RG OS
initramfs patch. Android on the internal storage is not touched; the Pocket 1 boots the card.

## Differences from the H700 consoles

- No `dtb.img`, no DDR3/DDR4 choice, no panel revision choice.
- Menu and installer use the 720x540 layout (exact 4:3, scaled to 960x720); the boot logo is 960x720.
- RetroArch uses `config/retroarch-miniloong.cfg` (960x720, left stick only, R3 unbound).
- Mini-HDMI is not available (HDMI.md covers the H700 only).
- Offline updates may carry `miniloong.dtb` or `device_trees/miniloong.dtb`.
- No GameCube core (RG Rotate only).

## Not verified

Built without access to the real image: check the first build log for the "Detecting the partition table" and
"device tree:" lines. If the image turns out not to be MBR the build stops with a message instead of producing a card
whose ROMS partition would not be created.
