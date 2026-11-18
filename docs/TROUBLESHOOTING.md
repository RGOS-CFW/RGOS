# Troubleshooting: the card does not boot

RG OS leaves up to four evidence files on the FAT boot partition (the one labelled RGOS; older cards still carry the stock ROCKNIX label). Put the card in a PC and look at which exist.

| File on the FAT partition | Written by | If it is missing |
|---|---|---|
| `rgos-initramfs.txt` | the RG OS initramfs (`initramfs/init`) | the initramfs never ran (see below) |
| `rgos-bootinfo.txt` | `rgos-init`, 6 s after switch_root | the failure is between switch_root and the session |
| `rgos-logs.txt` | `rgos-session`, at 8, 28 and 58 s | the session never started, or it died early |
| `rgos-retroarch.txt` | `rgos-launch`, after every game | no game was launched yet |

## RG34XXSP / RG35XX H / RG35XX SP: black screen, nothing is written to the card

If the card has no `rgos-initramfs.txt` at all, the console never reached Linux, which is before anything RG OS adds. On the H700 consoles the usual causes are, in this order:

1. **Wrong RAM type.** The stock ROCKNIX H700 images come in `DDR4` and `DDR3` flavours, and the U-Boot on the card is built for exactly one of them. The wrong one gives a black screen with no output, and other systems (which ship their own bootloader) still boot fine on the same console. `build.sh` defaults to DDR4; build the other one with `H700_RAM=DDR3 sudo -E ./build.sh rg35xxh`, or choose `h700_ram` = `DDR3` in the GitHub workflow. The card's `rgos-image-info.txt` says which type the image was built for.
2. **Wrong panel revision (device tree).** The RG35XX H / SP (and RG34XXSP) exist with two screen revisions. A black or garbled screen that still lets the card boot far enough to write `rgos-initramfs.txt` is this. Rebuild with `RG35XXH_DTB=sun50i-h700-anbernic-rg35xx-h-rev6-panel` (RG35XX SP: `RG35XXSP_DTB=...-rev6-panel`, RG34XXSP: `RG34XXSP_DTB=...-v2-panel`), or choose `h700_panel` = `alt` in the workflow. Fully power off (10 s power hold) before trying a new card.
3. **Card not ejected cleanly** after flashing: re-flash it.

The two options are independent, so with an unknown console try the four combinations (DDR4/DDR3 x standard/alt panel). The RAM type is only a concern for fresh images: offline updates reuse the U-Boot already on the card.

## RG Rotate boots Android instead of RG OS

Android does not always mean the SPL failed to find U-Boot. The boot chain falls through to the internal Android whenever the card's U-Boot cannot start Linux, for example when extlinux fails because U-Boot cannot load the `INITRD` file (no `ramdisk_addr_r` in its environment). Stock ROCKNIX has no INITRD line, so this U-Boot may never have been asked to load one.

Tell the two cases apart with the stock ROCKNIX T618 image (the same one `build.sh` downloads): if it also ends up in Android, the SPL or the card is the problem; if it boots, U-Boot is fine and RG OS's boot files are.

`build.sh` now uses the RG OS initramfs on every device (`RGOS_INITRD=1`, the default), so the card boots straight into RG OS and ROCKNIX's own init and boot screen never run. If this U-Boot cannot load the initrd and the Rotate falls through to Android, copy `extlinux/extlinux.conf.stock` over `extlinux/extlinux.conf` on the FAT partition (ROCKNIX's init then starts RG OS, with its boot screen), or rebuild with `RGOS_INITRD=0 sudo -E ./build.sh rg-rotate`.

## ROCKNIX boot screen shows before RG OS (card built with RGOS_INITRD=0)

An older RG Rotate build left `extlinux.conf` untouched, so ROCKNIX's init ran first. Without rebuilding, patch the card from a PC (`rgos-initrd.cpio` is already on the FAT partition):

    python3 initramfs/patch-extlinux.py <FAT partition>/extlinux/extlinux.conf /rgos-initrd.cpio

or flash a new image.

## Nothing is written at all (RG Rotate: boots Android, or stays black)

1. Android again: the SPL did not find U-Boot. Partition 3 of the card must be the GPT partition named `uboot` (`sgdisk -p /dev/sdX`); re-flash the image and the SPL.
2. Black screen, no `rgos-initramfs.txt`: U-Boot started but the RG OS initramfs did not run. Copy `extlinux/extlinux.conf.stock` over `extlinux/extlinux.conf` on the FAT partition and boot again.
   * Boots (slowly): the custom initramfs is the problem on this U-Boot/kernel (for example U-Boot has no `ramdisk_addr_r`, or the kernel was built to ignore an external initrd). Send `extlinux.conf` and a serial log if you have one.
   * Still does not boot: the problem is before the initramfs (SPL, U-Boot, kernel, device tree).

## `rgos-initramfs.txt` exists

Read it from the top: it lists the kernel command line, the partition the boot files were found on, `/proc/partitions` and the last step reached.

* `cannot mount /flash/SYSTEM as squashfs`: the file listing, `/proc/filesystems`, loop devices and the kernel log tail are included. A missing `squashfs` or `loop` entry means the kernel cannot mount SYSTEM; a damaged `SYSTEM` means re-flash the card.
* `switch_root to /usr/sbin/rgos-init` is the last line and there is no `rgos-bootinfo.txt`: the new root started but PID 1 died. Check `rgos-logs.txt` if it exists, otherwise rebuild with a fresh image.

## PortMaster shows "libopenal.so.1: cannot open shared object file" and returns to the menu

PortMaster's GUI runs on its LOVE 11.5 runtime, which needs the system `libopenal1` package. Images built before this was added do not have it. Rebuild (or run an offline update built) with the current `build.sh`; `libopenal1` is now part of the base package list and the build stops if `libopenal.so.1` is missing from the rootfs. To add other missing libraries without editing the script, use `EXTRA_PKGS="pkg1 pkg2"`. `rgos-native.log` on the device shows the exact library that failed to load.

## PortMaster shows its splash and then returns to the menu

PortMaster's output is written to `rgos-native.log` (on the device: `/var/log/rgos-native.log`), and when PortMaster quits within a few seconds the last lines of that log are shown on screen for a moment. Read the lines after the last `PortMaster.sh` header in the log: a Python traceback means PortMaster's GUI (pugwash/harbourmaster) crashed, `error while loading shared libraries` names a missing system package (add it with `EXTRA_PKGS`), and a network error means the first start could not download its runtime. `ALSOFT ... PipeWire` warnings are harmless; the launcher now sets `ALSOFT_DRIVERS=alsa` to avoid them.
