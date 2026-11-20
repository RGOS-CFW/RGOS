# Supported devices

| Device | Argument | SoC | Base image | Partition table | ROMS partition |
|---|---|---|---|---|---|
| Anbernic RG34XXSP | `rg34xxsp` | Allwinner H700 | ROCKNIX-H700 | MBR | 3 |
| Anbernic RG35XX H | `rg35xxh` | Allwinner H700 | ROCKNIX-H700 | MBR | 3 |
| Anbernic RG35XX SP | `rg35xxsp` | Allwinner H700 | ROCKNIX-H700 | MBR | 3 |
| Anbernic RG Rotate | `rg-rotate` | Unisoc T618 | ROCKNIX-T618 | GPT (`uboot` partition 3) | 4 |

The running device is stored in `/etc/rgos-device`. Offline updates check it, and the menu uses it to pick layouts and hide features.

## What differs between them

| | RG34XXSP | RG35XX H | RG35XX SP | RG Rotate |
|---|---|---|---|---|
| Analog sticks | enabled per `/etc/rgos/input-<device>.json` | same | **no** (`"analog": false`) | enabled per `/etc/rgos/input-<device>.json` |
| L2/R2, L3/R3 | yes | yes | no | yes |
| Bootloader | stock U-Boot on the card, per RAM type | same | same | SPL flashed once, U-Boot on card |
| RAM choice at build | `H700_RAM` DDR4/DDR3 | same | same | not applicable |
| Panel choice at build | `RG34XXSP_DTB` | `RG35XXH_DTB` | `RG35XXSP_DTB` | not applicable |
| GameCube | not shipped | not shipped | not shipped | yes (Dolphin libretro) |
| Device tree file | `dtb.img` | `dtb.img` | `dtb.img` | `device_trees/ums512-rg-rotate.dtb` |

Notes:

- The RG35XX SP's screen is 640x480, so it uses the same 720x540 menu layout and startup video as the RG35XX H.
- The RG35XX SP has its own RetroArch config (`config/retroarch-rg35xxsp.cfg`) and input profile: the stick axes and L3/R3 are unbound, and fast-forward and rewind move to **Menu + Up** and **Menu + Down**. See [CONTROLS.md](CONTROLS.md).
- Because the H700 image is MBR, there is no `uboot` partition and no SPL to flash on those consoles.
- The Rotate boots Android from internal storage when the card's U-Boot cannot start Linux. See [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Panel revisions and RAM types

For the three H700 consoles two independent choices decide whether the screen works:

1. **RAM type** (`DDR4` default, or `DDR3`). A mismatch is a black screen with nothing written to the card.
2. **Panel revision**: standard device tree, or the alternate tree (`-v2-panel` on the RG34XXSP, `-rev6-panel` on the RG35XX H and SP). A wrong choice gives a black or garbled screen, but the card still boots far enough to write `rgos-initramfs.txt`.

With an unknown console, try the four combinations. The RAM type matters only for fresh images; offline updates reuse the U-Boot already on the card.
