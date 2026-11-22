#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ALL_DEVICES=(rg-rotate rg34xxsp rg35xxh rg35xxsp)

usage() {
  cat <<EOF
usage: sudo ./build.sh <device> [image|installer|update]
       sudo ./build.sh update-img [device]

  device   rg34xxsp   Anbernic RG34XXSP (Allwinner H700, ROCKNIX-H700 base image)
           rg35xxh    Anbernic RG35XX H (Allwinner H700, ROCKNIX-H700 base image)
           rg35xxsp   Anbernic RG35XX SP (Allwinner H700, ROCKNIX-H700 base image)
           rg-rotate  Anbernic RG Rotate (Unisoc T618, ROCKNIX-T618 base image)
           all        build every device above
  image    full SD card image (default)  -> out/<device>-rgos.img
  installer  first-boot installer image  -> out/<device>-rgos-installer.img
           Same card layout, but PortMaster, the libretro cores and ./extras/ travel as a payload on the boot partition.
           On the first boot the device partitions the SD card and installs them with a progress screen (docs/INSTALLER.md).
  update   offline update tar            -> out/rgos-update-<device>-<id>.tar
  update-img  delete the cached stock ROCKNIX image and download it again (just that, no build).
           Without update-img the image is downloaded once into work/<device>/ and reused by every later build.
           Device defaults to all; "./build.sh <device> update-img" works too.

A device is required: ./build.sh with no argument does nothing but print this text.
Options (environment): RG34XXSP: H700_RAM=DDR4|DDR3 (default DDR4, must match the console's RAM),
  RG34XXSP_DTB=sun50i-h700-anbernic-rg34xx-sp[-v2-panel], RG35XXH_DTB=sun50i-h700-anbernic-rg35xx-h[-rev6-panel],
  RG35XXSP_DTB=sun50i-h700-anbernic-rg35xx-sp[-rev6-panel], ROCKNIX_H700_VERSION=<release tag>; any device: ROCKNIX_URL=<image .img.gz>.
EOF
}

DEVICE_ARG="$(printf '%s' "${1:-}" | tr 'A-Z_' 'a-z-')"
MODE="${2:-image}"; [[ "$MODE" == "build" ]] && MODE=image
[[ "$MODE" == "update-img" || "$MODE" == "updateimg" ]] && MODE=update-img
if [[ "$DEVICE_ARG" == "update-img" || "$DEVICE_ARG" == "updateimg" ]]; then
  MODE=update-img; set -- "${2:-all}"
  DEVICE_ARG="$(printf '%s' "$1" | tr 'A-Z_' 'a-z-')"
fi
case "$DEVICE_ARG" in
  rg34xxsp|rg34xx-sp)  DEVICE_ARG=rg34xxsp ;;
  rg35xxh|rg35xx-h)    DEVICE_ARG=rg35xxh ;;
  rg35xxsp|rg35xx-sp)  DEVICE_ARG=rg35xxsp ;;
  rg-rotate|rgrotate)  DEVICE_ARG=rg-rotate ;;
  all)                 ;;
  "")                  usage; exit 1 ;;
  *)                   echo "unknown device '${1}'" >&2; echo >&2; usage >&2; exit 1 ;;
esac
[[ "$MODE" == "image" || "$MODE" == "installer" || "$MODE" == "update" || "$MODE" == "update-img" ]] || { echo "unknown mode '${2}' (use image, installer, update or update-img)" >&2; echo >&2; usage >&2; exit 1; }

if [[ $EUID -ne 0 ]]; then
  command -v sudo >/dev/null || { echo "ERROR: this build needs root; run it as root or install sudo" >&2; exit 1; }
  exec sudo -E bash "${BASH_SOURCE[0]}" "$DEVICE_ARG" "$MODE"
fi

if [[ "$DEVICE_ARG" == "all" ]]; then
  export UPDATE_ID="${UPDATE_ID:-$(date +%Y%m%d-%H%M%S)}"
  failed=()
  for d in "${ALL_DEVICES[@]}"; do
    echo; echo "################ building $d ($MODE) ################"
    bash "${BASH_SOURCE[0]}" "$d" "$MODE" || failed+=("$d")
  done
  echo
  if (( ${#failed[@]} )); then echo "!! build FAILED for: ${failed[*]}" >&2; exit 1; fi
  echo "All devices built: ${ALL_DEVICES[*]} (output in $HERE/out)"
  exit 0
fi
DEVICE="$DEVICE_ARG"

case "$DEVICE" in
  rg-rotate)
    DEVICE_DESC="Anbernic RG Rotate (Unisoc T618)"
    PTABLE=gpt
    BASE_URL="https://github.com/beebono/distribution/releases/download/beta-20260818/ROCKNIX-T618.aarch64-20260818.img.gz"
    ;;
  rg34xxsp)
    DEVICE_DESC="Anbernic RG34XXSP (Allwinner H700)"
    PTABLE=dos
    H700_RAM="${H700_RAM:-DDR4}"
    [[ "$H700_RAM" == "DDR4" || "$H700_RAM" == "DDR3" ]] || { echo "H700_RAM must be DDR4 or DDR3" >&2; exit 1; }
    ROCKNIX_H700_VERSION="${ROCKNIX_H700_VERSION:-20261001}"
    BASE_URL="https://github.com/ROCKNIX/distribution/releases/download/${ROCKNIX_H700_VERSION}/ROCKNIX-H700.aarch64-${ROCKNIX_H700_VERSION}-${H700_RAM}.img.gz"
    RG34XXSP_DTB="${RG34XXSP_DTB:-sun50i-h700-anbernic-rg34xx-sp}"
    [[ "$RG34XXSP_DTB" =~ ^sun50i-h700-anbernic-rg34xx-sp(-v2-panel)?$ ]] || { echo "RG34XXSP_DTB must be sun50i-h700-anbernic-rg34xx-sp or sun50i-h700-anbernic-rg34xx-sp-v2-panel" >&2; exit 1; }
    H700_DTB="$RG34XXSP_DTB"
    ;;
  rg35xxh)
    DEVICE_DESC="Anbernic RG35XX H (Allwinner H700)"
    PTABLE=dos
    H700_RAM="${H700_RAM:-DDR4}"
    [[ "$H700_RAM" == "DDR4" || "$H700_RAM" == "DDR3" ]] || { echo "H700_RAM must be DDR4 or DDR3" >&2; exit 1; }
    ROCKNIX_H700_VERSION="${ROCKNIX_H700_VERSION:-20261001}"
    BASE_URL="https://github.com/ROCKNIX/distribution/releases/download/${ROCKNIX_H700_VERSION}/ROCKNIX-H700.aarch64-${ROCKNIX_H700_VERSION}-${H700_RAM}.img.gz"
    RG35XXH_DTB="${RG35XXH_DTB:-sun50i-h700-anbernic-rg35xx-h}"
    [[ "$RG35XXH_DTB" =~ ^sun50i-h700-anbernic-rg35xx-h(-rev6-panel)?$ ]] || { echo "RG35XXH_DTB must be sun50i-h700-anbernic-rg35xx-h or sun50i-h700-anbernic-rg35xx-h-rev6-panel" >&2; exit 1; }
    H700_DTB="$RG35XXH_DTB"
    ;;
  rg35xxsp)
    DEVICE_DESC="Anbernic RG35XX SP (Allwinner H700)"
    PTABLE=dos
    H700_RAM="${H700_RAM:-DDR4}"
    [[ "$H700_RAM" == "DDR4" || "$H700_RAM" == "DDR3" ]] || { echo "H700_RAM must be DDR4 or DDR3" >&2; exit 1; }
    ROCKNIX_H700_VERSION="${ROCKNIX_H700_VERSION:-20261001}"
    BASE_URL="https://github.com/ROCKNIX/distribution/releases/download/${ROCKNIX_H700_VERSION}/ROCKNIX-H700.aarch64-${ROCKNIX_H700_VERSION}-${H700_RAM}.img.gz"
    RG35XXSP_DTB="${RG35XXSP_DTB:-sun50i-h700-anbernic-rg35xx-sp}"
    [[ "$RG35XXSP_DTB" =~ ^sun50i-h700-anbernic-rg35xx-sp(-rev6-panel)?$ ]] || { echo "RG35XXSP_DTB must be sun50i-h700-anbernic-rg35xx-sp or sun50i-h700-anbernic-rg35xx-sp-rev6-panel" >&2; exit 1; }
    H700_DTB="$RG35XXSP_DTB"
    ;;
esac
echo "==> Device: $DEVICE_DESC  (mode: $MODE)"

ROCKNIX_URL="${ROCKNIX_URL:-$BASE_URL}"
DEBIAN_SUITE="${DEBIAN_SUITE:-trixie}"
DEBIAN_MIRROR="${DEBIAN_MIRROR:-http://deb.debian.org/debian}"
PSX_REPO="${PSX_REPO:-https://github.com/libretro/pcsx_rearmed.git}"
GENESIS_REPO="${GENESIS_REPO:-https://github.com/libretro/Genesis-Plus-GX.git}"
GC_REPO="${GC_REPO:-https://github.com/libretro/dolphin.git}"
# Dreamcast: the Debian RetroArch is a GLES build, the libretro buildbot Flycast is desktop-GL only (it dies with "Requesting
# OpenGL context, but RetroArch is compiled against OpenGLES"), so Flycast is built here as a GLES core. DC_REPO=none skips it.
DC_REPO="${DC_REPO:-https://github.com/flyinghead/flycast.git}"
DC_MAKE_ARGS="${DC_MAKE_ARGS:-platform=unix FORCE_GLES=1}"
# DC_REQUIRED=1 makes a failed Flycast build stop the whole build instead of producing an image without Dreamcast.
STELLA_REPO="${STELLA_REPO:-https://github.com/libretro/stella2014-libretro.git}"
ATARI800_REPO="${ATARI800_REPO:-https://github.com/libretro/libretro-atari800.git}"
PROSYSTEM_REPO="${PROSYSTEM_REPO:-https://github.com/libretro/prosystem-libretro.git}"
[[ "$DEVICE" == "rg-rotate" ]] || GC_REPO=none
RGOS_INITRD="${RGOS_INITRD:-1}"
[[ "$RGOS_INITRD" == 0 || "$RGOS_INITRD" == 1 ]] || { echo "RGOS_INITRD must be 0 or 1" >&2; exit 1; }
NGP_SRC="${NGP_SRC:-https://github.com/libretro/beetle-ngp-libretro/archive/refs/heads/master.tar.gz}"
EMU_PKGS="retroarch,libretro-gambatte,libretro-mgba,libretro-snes9x,libretro-nestopia,libretro-beetle-wswan,libretro-core-info,liblzo2-2,libgl1-mesa-dri,libegl1,libegl-mesa0,libgles2,libgbm1,libsdl2-2.0-0,libopenal1"
EXTRA_PKGS="${EXTRA_PKGS:-}"

WORK="$HERE/work/$DEVICE"; OUT="$HERE/out"; IMG="$OUT/$DEVICE-rgos.img"
[[ "$MODE" == "update" ]] && IMG="$WORK/update-scratch.img"
[[ "$MODE" == "installer" ]] && IMG="$OUT/$DEVICE-rgos-installer.img"
ROOTFS="$WORK/rootfs"

need=(debootstrap losetup mksquashfs unsquashfs wget gunzip md5sum python3 readelf sfdisk truncate)
[[ ( "$MODE" == "image" || "$MODE" == "installer" ) && "$PTABLE" == gpt ]] && need+=(sgdisk)
[[ "$(uname -m)" == "aarch64" ]] || need+=(qemu-aarch64-static)
[[ "$MODE" == "update-img" ]] && need=(wget gunzip)
for t in "${need[@]}"; do
  command -v "$t" >/dev/null || { echo "Missing tool: $t"
    echo "apt install debootstrap qemu-user-static binfmt-support squashfs-tools wget gdisk dosfstools"; exit 1; }
done

mkdir -p "$WORK" "$OUT" "$WORK/mnt"
RX_GZ="$WORK/$(basename "$ROCKNIX_URL")"; RX_IMG="${RX_GZ%.gz}"
LOOP=""
cleanup() { set +e; mountpoint -q "$WORK/mnt" && umount "$WORK/mnt"; [[ -n "$LOOP" ]] && losetup -d "$LOOP"; }
trap cleanup EXIT

# The stock image is downloaded once and reused by every build. Only "build.sh update-img" throws it away.
fetch_stock() {
  echo "==> Downloading the stock ROCKNIX image for $DEVICE"; echo "    $ROCKNIX_URL"
  rm -f "$RX_GZ.part" "$RX_IMG.part"
  if ! wget -O "$RX_GZ.part" "$ROCKNIX_URL"; then
    rm -f "$RX_GZ.part"
    echo "!! download failed. Set ROCKNIX_URL=<url of the stock image .img.gz> (RG34XXSP / RG35XX H: or ROCKNIX_H700_VERSION=<release tag>, H700_RAM=DDR4|DDR3), or put the .img.gz into $WORK/ and re-run." >&2; exit 1
  fi
  mv -f "$RX_GZ.part" "$RX_GZ"
}
unpack_stock() {
  echo "==> Unpacking $(basename "$RX_GZ")"
  if ! gunzip -c "$RX_GZ" > "$RX_IMG.part"; then
    rm -f "$RX_IMG.part" "$RX_GZ"
    echo "!! $RX_GZ is corrupt (removed); run again to download it fresh" >&2; exit 1
  fi
  mv -f "$RX_IMG.part" "$RX_IMG"
}
if [[ "$MODE" == "update-img" ]]; then
  echo "==> update-img: discarding the cached stock image for $DEVICE"
  rm -f "$RX_GZ" "$RX_IMG"
  fetch_stock; unpack_stock
  echo "==> Stock image refreshed: $RX_IMG"
  echo "    Later builds of $DEVICE reuse it until you run update-img again."
  exit 0
fi
if [[ -s "$RX_IMG" ]]; then
  echo "==> Using the cached stock image $RX_IMG (run './build.sh update-img $DEVICE' to download it again)"
else
  [[ -s "$RX_GZ" ]] || fetch_stock
  unpack_stock
fi
echo "==> Copying stock image to $IMG"
cp --sparse=always "$RX_IMG" "$IMG"
LOOP="$(losetup -Pf --show "$IMG")"
BOOT_LABEL="RGOS"
echo "==> Renaming the boot partition label: $(blkid -s LABEL -o value "${LOOP}p1" 2>/dev/null) -> $BOOT_LABEL"
if command -v fatlabel >/dev/null 2>&1; then fatlabel "${LOOP}p1" "$BOOT_LABEL"
elif command -v mlabel >/dev/null 2>&1; then MTOOLS_SKIP_CHECK=1 mlabel -i "${LOOP}p1" "::$BOOT_LABEL"
else echo "!! need fatlabel (dosfstools) or mlabel (mtools) to rename the boot partition" >&2; exit 1; fi
[[ "$(blkid -s LABEL -o value "${LOOP}p1")" == "$BOOT_LABEL" ]] || { echo "!! the boot partition label is not $BOOT_LABEL after renaming" >&2; exit 1; }
mount "${LOOP}p1" "$WORK/mnt"
echo "==> Stock boot partition:"; ls -la "$WORK/mnt"
echo "==> Stock extlinux config (left untouched):"
cat "$WORK/mnt"/extlinux/extlinux.conf 2>/dev/null || cat "$WORK/mnt"/extlinux.conf 2>/dev/null || echo "(none found)"

if [[ "$DEVICE" == "rg34xxsp" || "$DEVICE" == "rg35xxh" || "$DEVICE" == "rg35xxsp" ]]; then
  DTB_SRC="$WORK/mnt/device_trees/$H700_DTB.dtb"
  [[ -f "$DTB_SRC" ]] || { echo "!! $H700_DTB.dtb is not in the stock image's device_trees/ ($(ls "$WORK/mnt/device_trees" 2>/dev/null | tr '\n' ' '))"; exit 1; }
  echo "==> dtb.img <- device_trees/$H700_DTB.dtb"
  cp -f "$DTB_SRC" "$WORK/mnt/dtb.img"
  echo "==> Removing device_trees/ from the boot partition (dtb.img is the only device tree kept)"
  rm -rf "$WORK/mnt/device_trees"
  grep -qi '^[[:space:]]*fdt[[:space:]]\+/dtb.img' "$WORK/mnt/extlinux/extlinux.conf" 2>/dev/null \
    || echo "!! stock extlinux.conf does not load /dtb.img (FDT line differs); check the config printed above"
fi

OLD_SYS="$WORK/mnt/SYSTEM"
[[ -f "$OLD_SYS" ]] || { echo "!! No SYSTEM file on the boot partition. Paste 'ls -la' above to me."; exit 1; }
COMP="$(unsquashfs -s "$OLD_SYS" | awk '/^Compression/ {print $2; exit}')"; COMP="${COMP:-gzip}"
BSIZE="$(unsquashfs -s "$OLD_SYS" | awk '/^Block size/ {print $3; exit}')"; BSIZE="${BSIZE:-131072}"
echo "==> Stock SYSTEM uses squashfs compression: $COMP, block size $BSIZE (matching it)"

rm -rf "$WORK/system"
echo "==> Unpacking stock SYSTEM (for modules/firmware)"
unsquashfs -q -d "$WORK/system" "$OLD_SYS" || echo "   (some unsquashfs errors; continuing)"

rm -rf "$ROOTFS"
echo "==> debootstrap $DEBIAN_SUITE arm64 minbase"
debootstrap --arch=arm64 --variant=minbase --foreign --components=main,non-free --include=busybox-static,kmod,python3,python3-pygame,ca-certificates,fonts-dejavu-core,e2fsprogs,exfatprogs,dosfstools,fdisk,gdisk,iproute2,iw,wpasupplicant,rfkill,alsa-utils,bluez,dbus,dropbear-bin,openssh-sftp-server,"$EMU_PKGS${EXTRA_PKGS:+,${EXTRA_PKGS// /,}}" \
  "$DEBIAN_SUITE" "$ROOTFS" "$DEBIAN_MIRROR"
[[ "$(uname -m)" == "aarch64" ]] || cp "$(command -v qemu-aarch64-static)" "$ROOTFS/usr/bin/"
mkdir -p "$ROOTFS/usr/sbin"; printf '#!/bin/sh\nexit 101\n' > "$ROOTFS/usr/sbin/policy-rc.d"; chmod +x "$ROOTFS/usr/sbin/policy-rc.d"
chroot "$ROOTFS" /debootstrap/debootstrap --second-stage
rm -f "$ROOTFS/usr/sbin/policy-rc.d"
chroot "$ROOTFS" sh -c "dpkg-query -W -f='\${Package}\n' | xargs -r apt-mark manual" >/dev/null 2>&1 || true
echo "$DEVICE-rgos" > "$ROOTFS/etc/hostname"

echo "root:rgos" | chroot "$ROOTFS" chpasswd || echo "!! could not set the default root password"
rm -f "$ROOTFS"/etc/dropbear/dropbear_*_host_key "$ROOTFS"/etc/dropbear/dropbear_*_host_key.pub 2>/dev/null
mkdir -p "$ROOTFS/etc/bluetooth"
printf '[General]\nClassicBondedOnly=false\n' > "$ROOTFS/etc/bluetooth/input.conf"

MODDIR="$(find "$WORK/system" -maxdepth 7 -type d -path '*/lib/modules/*' -name '[0-9]*' -prune 2>/dev/null | head -1 || true)"
if [[ -n "$MODDIR" ]]; then
  KVER="$(basename "$MODDIR")"; echo "==> Installing modules for $KVER"
  mkdir -p "$ROOTFS/lib/modules"; cp -a "$MODDIR" "$ROOTFS/lib/modules/$KVER"
  chroot "$ROOTFS" depmod -a "$KVER" || true
fi
FWDIR=""; FWBEST=0
for c in $(find "$WORK/system" -maxdepth 9 -type d -path '*lib/firmware' 2>/dev/null) ${MODDIR:+"$(dirname "$(dirname "$MODDIR")")/firmware"}; do
  [[ -d "$c" ]] || continue
  n=$(find "$c" -type f 2>/dev/null | wc -l); (( n > FWBEST )) && { FWBEST=$n; FWDIR="$c"; }
done
echo "==> Firmware directory: ${FWDIR:-NONE FOUND} ($FWBEST files)"
[[ -n "$FWDIR" ]] && { mkdir -p "$ROOTFS/lib/firmware"; cp -a "$FWDIR"/. "$ROOTFS/lib/firmware/"; }
mkdir -p "$ROOTFS/system/etc"; ln -sfn /lib/firmware "$ROOTFS/system/etc/firmware"
mkdir -p "$ROOTFS/etc/rgos/audio"
AST="$(find "$WORK/system" -name asound.state -type f 2>/dev/null | head -1)"
if [[ -n "$AST" ]]; then cp "$AST" "$ROOTFS/etc/rgos/audio/asound.state"; echo "==> Stock mixer state: $AST"
else echo "!! no asound.state in the stock SYSTEM: the speaker relies on audio/init.txt and the driver defaults"; fi
ACF="$(find "$WORK/system" -name asound.conf -type f 2>/dev/null | head -1)"; [[ -n "$ACF" ]] && cp "$ACF" "$ROOTFS/etc/asound.conf" && echo "==> Stock asound.conf: $ACF"
echo "==> Stock audio scripts (for reference): $(find "$WORK/system" -type f \( -iname '*audio*' -o -iname '*amixer*' -o -iname '*alsa*.sh' \) -path '*bin*' 2>/dev/null | sed "s#$WORK/system/##" | head -10 | tr '\n' ' ')"
[[ -d "$HERE/audio" ]] && cp "$HERE"/audio/init.txt "$ROOTFS/etc/rgos/audio/init.txt"
mkdir -p "$ROOTFS/etc/rgos"
if [[ -n "${MODDIR:-}" ]]; then
  find "$MODDIR" -type f -name '*.ko*' 2>/dev/null | grep -i -E '/(wireless|bluetooth)/|sprd|uwe|wcn|sdiohal|rtw|rtl8|brcm|aic8|cfg80211|mac80211|btusb|hci_uart' \
    | sed -E 's#.*/##; s#\.ko(\..*)?$##' | sort -u > "$ROOTFS/etc/rgos/wireless-modules.txt" || true
fi
echo "==> Wi-Fi/Bluetooth modules in the stock kernel: $(tr '\n' ' ' < "$ROOTFS/etc/rgos/wireless-modules.txt" 2>/dev/null)"
[[ -s "$ROOTFS/etc/rgos/wireless-modules.txt" ]] || echo "!! no wireless modules found in the stock SYSTEM: the driver is built into the kernel (needs firmware only) or MODDIR is wrong"
echo "==> Wi-Fi-looking firmware: $(ls "$ROOTFS/lib/firmware" 2>/dev/null | grep -i -E 'wcn|sprd|rtl|rtw|brcm|aic|mt7|ath|wifi|wlan|uwe|sc2' | tr '\n' ' ')"

echo "==> Installing RG OS into /opt/rgos"
HERE_RGOS="$HERE/rgos"
[[ -f "$HERE_RGOS/menu.py" ]] || { echo "!! $HERE_RGOS/menu.py missing"; exit 1; }
mkdir -p "$ROOTFS/opt/rgos" "$ROOTFS/etc/rgos" "$ROOTFS/var/lib/rgos" "$ROOTFS/var/log" "$ROOTFS/media/roms" "$ROOTFS/boot"
mkdir -p "$ROOTFS/flash" "$ROOTFS/storage" "$ROOTFS/run" "$ROOTFS/tmp" "$ROOTFS/root"
find "$HERE_RGOS" -maxdepth 1 -type f -exec cp {} "$ROOTFS/opt/rgos/" \;
chmod 755 "$ROOTFS"/opt/rgos/rgos-* "$ROOTFS/opt/rgos/menu.py" "$ROOTFS/opt/rgos/wifictl.py" "$ROOTFS/opt/rgos/btctl.py" "$ROOTFS/opt/rgos/sshctl.py"
for f in usr/sbin/dropbear usr/bin/dropbearkey usr/lib/openssh/sftp-server usr/bin/bluetoothctl usr/bin/dbus-daemon sbin/mkfs.ext4 sbin/mkfs.exfat sbin/mkfs.vfat usr/sbin/sgdisk sbin/sfdisk usr/sbin/partx sbin/wpa_supplicant; do
  [[ -e "$ROOTFS/$f" || -e "$ROOTFS/usr/$f" ]] || echo "!! $f is missing from the image"
done
ls "$ROOTFS"/usr/libexec/bluetooth/bluetoothd "$ROOTFS"/usr/lib/bluetooth/bluetoothd >/dev/null 2>&1 || echo "!! bluetoothd is missing from the image"
echo "$DEVICE" > "$ROOTFS/etc/rgos-device"
case "$DEVICE" in
  rg34xxsp|rg35xxh|rg35xxsp)
    mkdir -p "$ROOTFS/etc/rgos"
    if [[ "$DEVICE" == "rg35xxsp" ]]; then ANALOG=false; else ANALOG=true; fi
    echo "{\"analog\": $ANALOG}" > "$ROOTFS/etc/rgos/input-$DEVICE.json"
    RA_CFG="$HERE/config/retroarch-$DEVICE.cfg"
    [[ -f "$RA_CFG" || "$DEVICE" == "rg35xxsp" ]] || RA_CFG="$HERE/config/retroarch-rg34xxsp.cfg"
    [[ -f "$RA_CFG" ]] || { echo "!! $RA_CFG missing"; exit 1; }
    cp "$RA_CFG" "$ROOTFS/etc/rgos/retroarch-$DEVICE.cfg"
    ;;
esac
BOOTLOGO_RAW_DIR="$WORK/bootlogo-raw"
rm -rf "$BOOTLOGO_RAW_DIR"
if [[ -f "$HERE/bootlogo/bootlogo-$DEVICE.bmp" ]]; then
  # raw copy of the boot logo, painted onto the framebuffer by the initramfs and by rgos-init long before the menu starts
  if python3 "$HERE/tools/bmp2fb.py" "$HERE/bootlogo/bootlogo-$DEVICE.bmp" "$BOOTLOGO_RAW_DIR" >/dev/null; then
    mkdir -p "$ROOTFS/etc/rgos/bootlogo" && cp "$BOOTLOGO_RAW_DIR"/*.raw "$ROOTFS/etc/rgos/bootlogo/"
  else
    echo "!! could not convert bootlogo-$DEVICE.bmp: no early boot logo in the image"; rm -rf "$BOOTLOGO_RAW_DIR"
  fi
fi
if [[ -d "$HERE/splash" ]]; then
  mkdir -p "$ROOTFS/etc/rgos/splash"
  SPLASH_DEV="$DEVICE"
  # fall back to the RG35XX H splash only when there is no splash-rg35xxsp.* file of any type
  [[ "$DEVICE" == "rg35xxsp" ]] && ! compgen -G "$HERE/splash/splash-rg35xxsp.*" >/dev/null && SPLASH_DEV=rg35xxh
  for f in "$HERE"/splash/*; do
    [[ -e "$f" ]] || continue   # empty splash/ folder: the glob stays literal and cp would abort the build
    b="$(basename "$f")"
    case "$b" in splash-*) [[ "$b" == splash-"$SPLASH_DEV".* ]] || continue; b="splash-$DEVICE.${b#splash-"$SPLASH_DEV".}" ;; esac
    cp "$f" "$ROOTFS/etc/rgos/splash/$b"
  done
else
  echo "!! $HERE/splash missing: no startup splash in the image"
fi
if [[ -d "$HERE/music" ]]; then
  mkdir -p "$ROOTFS/opt/rgos/music" && cp "$HERE"/music/* "$ROOTFS/opt/rgos/music/"
else
  echo "!! $HERE/music missing: no bundled launcher music in the image"
fi
# PortMaster preinstall: a read-only seed in the rootfs; rgos-session copies it to ROMS/roms/ports/PortMaster on the first boot
# where that folder is missing, and PortMaster then updates itself in place there. PORTMASTER=0 skips it,
# PORTMASTER_ZIP=<local PortMaster.zip> builds offline.
PORTMASTER="${PORTMASTER:-1}"
PORTMASTER_URL="${PORTMASTER_URL:-https://github.com/PortsMaster/PortMaster-GUI/releases/latest/download/PortMaster.zip}"
if [[ "$PORTMASTER" == 1 ]]; then
  PM_ZIP="${PORTMASTER_ZIP:-$WORK/PortMaster.zip}"
  if [[ -z "${PORTMASTER_ZIP:-}" ]]; then
    echo "==> Downloading PortMaster for the preinstall seed"
    wget -q -O "$PM_ZIP.part" "$PORTMASTER_URL" && mv "$PM_ZIP.part" "$PM_ZIP" || { rm -f "$PM_ZIP.part"; echo "!! PortMaster download failed ($PORTMASTER_URL)"; }
  fi
  if [[ -s "$PM_ZIP" ]]; then
    rm -rf "$ROOTFS/opt/rgos/seed"; mkdir -p "$ROOTFS/opt/rgos/seed"
    python3 -c 'import sys,zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' "$PM_ZIP" "$ROOTFS/opt/rgos/seed" \
      || echo "!! cannot unpack $PM_ZIP"
    if [[ -f "$ROOTFS/opt/rgos/seed/PortMaster/PortMaster.sh" ]]; then
      echo "==> PortMaster seed ready ($(du -sh "$ROOTFS/opt/rgos/seed/PortMaster" | cut -f1))"
    else
      rm -rf "$ROOTFS/opt/rgos/seed"
      echo "!! the PortMaster zip has no PortMaster/PortMaster.sh: the image will NOT come with PortMaster"
    fi
  else
    echo "!! no PortMaster zip: the image will NOT come with PortMaster (set PORTMASTER_ZIP=<file> to build offline)"
  fi
fi
# PortMaster's GUI runs on its LOVE 11.5 runtime (love.aarch64), which links the system libopenal.so.1 and does not bundle it;
# without it PortMaster dies at start with "error while loading shared libraries: libopenal.so.1". libopenal1 is in EMU_PKGS;
# the rest are the libraries LOVE commonly links, installed best-effort.
if [[ "$PORTMASTER" == 1 ]]; then
  cp -L /etc/resolv.conf "$ROOTFS/etc/resolv.conf" 2>/dev/null || true
  chroot "$ROOTFS" apt-get update >/dev/null 2>&1 || true
  for pkg in libopenal1 libmpg123-0t64 libvorbisfile3 libvorbis0a libogg0 libtheora0 libmodplug1 libfreetype6 libsdl2-2.0-0 zlib1g \
             unzip wget curl xxd procps psmisc; do
    chroot "$ROOTFS" env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$pkg" >/dev/null 2>&1 || true
  done
  rm -f "$ROOTFS/etc/resolv.conf"
  if ! chroot "$ROOTFS" sh -c 'ldconfig -p 2>/dev/null | grep -q "libopenal.so.1"' && ! ls "$ROOTFS"/usr/lib/*/libopenal.so.1 >/dev/null 2>&1; then
    echo "!! libopenal.so.1 is not in the image: PortMaster will not start (install libopenal1 with EXTRA_PKGS=libopenal1)"; exit 1
  fi
  # PortMaster.sh unpacks its pylibs.zip with unzip before the GUI starts; without it the GUI dies right after the splash.
  [[ -x "$ROOTFS/usr/bin/unzip" ]] || echo "!! unzip is not in the image: PortMaster may close right after its splash (a busybox unzip is linked in below as a fallback)"
fi
printf 'BUILD_ID=%s\n' "$(date +%Y%m%d-%H%M)" > "$ROOTFS/etc/rgos-release"
echo '{"enabled": false, "mountpoint": "/media/roms2"}' > "$ROOTFS/etc/rgos/sdcard.json"
[[ -f "$HERE/config/retroarch.cfg" ]] || { echo "!! $HERE/config/retroarch.cfg missing"; exit 1; }
cp "$HERE/config/retroarch.cfg" "$ROOTFS/etc/rgos/retroarch.cfg"
mkdir -p "$ROOTFS/etc/rgos/autoconfig" && cp "$HERE"/config/autoconfig/*.cfg "$ROOTFS/etc/rgos/autoconfig/"
LRDIR="$ROOTFS/usr/local/lib/libretro"; mkdir -p "$LRDIR"
cp -L /etc/resolv.conf "$ROOTFS/etc/resolv.conf" 2>/dev/null || true
if chroot "$ROOTFS" apt-get update >/dev/null 2>&1 \
   && chroot "$ROOTFS" env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends libretro-beetle-psx >/dev/null 2>&1; then
  echo "==> Installed libretro-beetle-psx (PlayStation fallback core)"
else
  echo "   (libretro-beetle-psx is not available in $DEBIAN_SUITE; PlayStation uses pcsx_rearmed only)"
fi
if chroot "$ROOTFS" env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends libretro-genesisplusgx >/dev/null 2>&1; then
  echo "==> Installed libretro-genesisplusgx (Genesis Plus GX)"
else
  echo "   (libretro-genesisplusgx is not available in $DEBIAN_SUITE; it will be built from $GENESIS_REPO)"
fi
if ls "$HERE"/cores/*_libretro.so >/dev/null 2>&1; then
  echo "==> Copying prebuilt cores from cores/"; cp "$HERE"/cores/*_libretro.so "$LRDIR/"
fi
[[ "$DEVICE" == "rg-rotate" ]] || rm -f "$LRDIR/dolphin_libretro.so"
WANT_NGP=0; WANT_PSX=0; WANT_GEN=0; WANT_GC=0; WANT_ATARI=0; WANT_DC=0
[[ "$NGP_SRC" != none && ! -e "$LRDIR/mednafen_ngp_libretro.so" ]] && WANT_NGP=1
[[ "$PSX_REPO" != none && ! -e "$LRDIR/pcsx_rearmed_libretro.so" ]] && WANT_PSX=1
have_core() { local f; for f in "$ROOTFS"/usr/lib/*/libretro/"$1"_libretro.so "$ROOTFS/usr/lib/libretro/$1"_libretro.so "$ROOTFS/usr/local/lib/libretro/$1"_libretro.so; do [[ -e "$f" ]] && return 0; done; return 1; }
[[ "$GENESIS_REPO" != none ]] && ! have_core genesis_plus_gx && WANT_GEN=1
[[ "$GC_REPO" != none && ! -e "$LRDIR/dolphin_libretro.so" ]] && WANT_GC=1
[[ "$DC_REPO" != none && ! -e "$LRDIR/flycast_libretro.so" ]] && WANT_DC=1
[[ "$STELLA_REPO" != none ]] && ! have_core stella2014 && WANT_ATARI=1
[[ "$ATARI800_REPO" != none ]] && ! have_core atari800 && WANT_ATARI=1
[[ "$PROSYSTEM_REPO" != none ]] && ! have_core prosystem && WANT_ATARI=1
if (( WANT_NGP || WANT_PSX || WANT_GEN || WANT_GC || WANT_ATARI || WANT_DC )); then
  echo "==> Installing a compiler in the rootfs to build libretro cores"
  rm -rf "$ROOTFS/tmp/core-src"; mkdir -p "$ROOTFS/tmp/core-src"
  cp -L /etc/resolv.conf "$ROOTFS/etc/resolv.conf"
  if chroot "$ROOTFS" apt-get update && chroot "$ROOTFS" env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends gcc g++ make; then
    if (( WANT_NGP )); then
      echo "==> Building the Neo Geo Pocket core (mednafen_ngp)"
      if (
        set -e
        wget -q -O "$WORK/ngp-src.tar.gz" "$NGP_SRC"
        mkdir -p "$ROOTFS/tmp/core-src/ngp"; tar -xzf "$WORK/ngp-src.tar.gz" -C "$ROOTFS/tmp/core-src/ngp" --strip-components=1
        chroot "$ROOTFS" sh -c 'cd /tmp/core-src/ngp && make -j"$(nproc)"'
        install -m 755 "$ROOTFS"/tmp/core-src/ngp/mednafen_ngp_libretro.so "$LRDIR/mednafen_ngp_libretro.so"
      ); then echo "   mednafen_ngp_libretro.so built"
      else echo "!! could not build the Neo Geo Pocket core: NGP/NGPC will have no core (put a prebuilt mednafen_ngp_libretro.so in cores/ and rebuild)"; fi
    fi
    if (( WANT_GEN )); then
      echo "==> Building the Genesis Plus GX core (genesis_plus_gx)"
      if (
        set -e
        command -v git >/dev/null || { echo "git is not installed on this PC (apt install git)"; exit 1; }
        rm -rf "$WORK/genesis-plus-gx"
        git clone -q --depth 1 "$GENESIS_REPO" "$WORK/genesis-plus-gx"
        cp -r "$WORK/genesis-plus-gx" "$ROOTFS/tmp/core-src/gen"
        chroot "$ROOTFS" sh -c 'cd /tmp/core-src/gen && make -f Makefile.libretro platform=unix -j"$(nproc)"'
        install -m 755 "$ROOTFS"/tmp/core-src/gen/genesis_plus_gx_libretro.so "$LRDIR/genesis_plus_gx_libretro.so"
      ); then echo "   genesis_plus_gx_libretro.so built"
      else echo "!! could not build Genesis Plus GX: Mega Drive / Master System / Game Gear / Sega CD will have no core (put a prebuilt genesis_plus_gx_libretro.so in cores/ and rebuild)"; fi
    fi
    if (( WANT_ATARI )); then
      # Atari 2600 (Stella 2014), 5200 (Atari800) and 7800 (ProSystem): small, plain-Makefile cores. Each one is built on its own,
      # so a failure only drops that one system from the menu.
      for spec in "stella2014|$STELLA_REPO|Atari 2600" "atari800|$ATARI800_REPO|Atari 5200" "prosystem|$PROSYSTEM_REPO|Atari 7800"; do
        IFS='|' read -r acore arepo asys <<<"$spec"
        [[ "$arepo" != none ]] && ! have_core "$acore" || continue
        echo "==> Building the $asys core ($acore)"
        if (
          command -v git >/dev/null || { echo "git is not installed on this PC (apt install git)"; exit 1; }
          rm -rf "$WORK/$acore" && git clone -q --depth 1 "$arepo" "$WORK/$acore" || exit 1
          cp -r "$WORK/$acore" "$ROOTFS/tmp/core-src/$acore" || exit 1
          chroot "$ROOTFS" sh -c "cd /tmp/core-src/$acore && make -j\"\$(nproc)\"" || exit 1
          so="$(find "$ROOTFS/tmp/core-src/$acore" -name "${acore}_libretro.so" -type f | head -n1)"
          [[ -n "$so" ]] || exit 1
          install -m 755 "$so" "$LRDIR/${acore}_libretro.so" || exit 1
        ); then echo "   ${acore}_libretro.so built"
        else echo "!! could not build $acore: $asys will have no core (put a prebuilt ${acore}_libretro.so in cores/ and rebuild)"; rm -f "$LRDIR/${acore}_libretro.so"; fi
      done
    fi
    if (( WANT_PSX )); then
      echo "==> Building the PlayStation core (pcsx_rearmed, aarch64 dynarec)"
      if (
        set -e
        command -v git >/dev/null || { echo "git is not installed on this PC (apt install git)"; exit 1; }
        rm -rf "$WORK/pcsx_rearmed"
        git clone -q --depth 1 --recurse-submodules --shallow-submodules "$PSX_REPO" "$WORK/pcsx_rearmed"
        cp -r "$WORK/pcsx_rearmed" "$ROOTFS/tmp/core-src/psx"
        chroot "$ROOTFS" sh -c 'cd /tmp/core-src/psx && make -f Makefile.libretro -j"$(nproc)"'
        install -m 755 "$ROOTFS"/tmp/core-src/psx/pcsx_rearmed_libretro.so "$LRDIR/pcsx_rearmed_libretro.so"
      ); then echo "   pcsx_rearmed_libretro.so built"
      else echo "!! could not build pcsx_rearmed: PlayStation falls back to mednafen_psx (Beetle PSX, slower; software renderer)"; fi
    fi
    if (( WANT_DC )); then
      echo "==> Building the Dreamcast core (flycast, OpenGL ES to match RetroArch)"
      DC_LOG="$WORK/flycast-build.log"; : > "$DC_LOG"
      if (
        set -e
        command -v git >/dev/null || { echo "git is not installed on this PC (apt install git)"; exit 1; }
        rm -rf "$WORK/flycast"
        git clone -q --depth 1 --recurse-submodules --shallow-submodules "$DC_REPO" "$WORK/flycast"
        rm -rf "$ROOTFS/tmp/core-src/dc"; cp -r "$WORK/flycast" "$ROOTFS/tmp/core-src/dc"
        # one package at a time: a package that is missing in this Debian suite must not stop the others from installing
        for pkg in libgles-dev libegl-dev zlib1g-dev libcurl4-openssl-dev pkg-config libzip-dev libasound2-dev; do
          chroot "$ROOTFS" env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$pkg" >>"$DC_LOG" 2>&1 \
            || echo "   (could not install $pkg, continuing)"
        done
        # Flycast is a very large C++ project: with every core in parallel the compiler is often killed for lack of RAM (WSL and
        # small VMs), which shows up as a failed build. Retry with fewer jobs before giving up.
        built=0
        for jobs in "$(nproc)" 2 1; do
          echo "   make -j$jobs $DC_MAKE_ARGS (log: $DC_LOG)"
          if chroot "$ROOTFS" sh -c "cd /tmp/core-src/dc && make -f Makefile $DC_MAKE_ARGS -j$jobs" >>"$DC_LOG" 2>&1; then built=1; break; fi
          echo "   make -j$jobs failed, retrying with fewer jobs"
        done
        (( built )) || { echo "flycast: make failed, last lines of $DC_LOG:"; tail -n 40 "$DC_LOG"; exit 1; }
        so="$(find "$ROOTFS/tmp/core-src/dc" -name flycast_libretro.so -type f | head -n1)"
        [[ -n "$so" ]] || { echo "flycast: make finished but flycast_libretro.so was not produced (check DC_MAKE_ARGS=$DC_MAKE_ARGS, log: $DC_LOG)"; exit 1; }
        # A desktop-GL build dies at start exactly like the buildbot core ("Requesting OpenGL context, but RetroArch is compiled
        # against OpenGLES"), so refuse it here. It links libGL / libOpenGL; a GLES build must not, and must mention GLES.
        if command -v readelf >/dev/null 2>&1 && readelf -d "$so" 2>/dev/null | grep -Eq 'NEEDED.*\[(libGL|libOpenGL)\.so'; then
          echo "flycast_libretro.so links desktop OpenGL (libGL), not OpenGL ES: check DC_MAKE_ARGS=$DC_MAKE_ARGS (FORCE_GLES=1)"; exit 1
        fi
        strings "$so" | grep -qi 'GLES' || { echo "flycast_libretro.so has no GLES code (check DC_MAKE_ARGS)"; exit 1; }
        install -m 755 "$so" "$LRDIR/flycast_libretro.so"
      ); then echo "   flycast_libretro.so built (GLES)"
      else
        echo "!! could not build Flycast: Dreamcast will have NO core in this image (log: $DC_LOG)."
        echo "!! Do not use Tools > Core Installer for it: the libretro buildbot Flycast is desktop-GL and cannot run on this RetroArch."
        echo "!! Fix the build error above, or put a GLES-built flycast_libretro.so in cores/ and rebuild."
        rm -f "$LRDIR/flycast_libretro.so"
        [[ "${DC_REQUIRED:-0}" != 1 ]] || { echo "!! DC_REQUIRED=1: stopping" >&2; exit 1; }
      fi
    fi
    if (( WANT_GC )); then
      echo "==> Building the GameCube core (Dolphin libretro, GameCube only in the menu; RG Rotate)"
      if chroot "$ROOTFS" env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends git ca-certificates cmake ninja-build pkg-config \
           libevdev-dev libudev-dev libasound2-dev libpulse-dev libgl-dev libegl-dev libgles-dev libdrm-dev libgbm-dev libusb-1.0-0-dev libbluetooth-dev \
           libcurl4-openssl-dev libpng-dev libminizip-dev liblzo2-dev libmbedtls-dev libhidapi-dev zlib1g-dev libxi-dev libxrandr-dev libx11-dev \
           && (
        rm -rf "$WORK/dolphin-libretro"
        git clone -q --depth 1 --recurse-submodules --shallow-submodules "$GC_REPO" "$WORK/dolphin-libretro" || exit 1
        cp -r "$WORK/dolphin-libretro" "$ROOTFS/tmp/core-src/gc" || exit 1
        chroot "$ROOTFS" sh -c 'cd /tmp/core-src/gc && cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_FLAGS=-mtune=cortex-a75 -DCMAKE_CXX_FLAGS=-mtune=cortex-a75 -DLIBRETRO=ON -DENABLE_QT=OFF -DENABLE_NOGUI=OFF -DENABLE_X11=OFF -DENABLE_TESTS=OFF -DENABLE_ANALYTICS=OFF -DENABLE_LTO=OFF -DUSE_DISCORD_PRESENCE=OFF -DENABLE_CLI_TOOL=OFF && cmake --build build -j"$(nproc)"' || exit 1
        so="$(find "$ROOTFS/tmp/core-src/gc" -name dolphin_libretro.so -type f | head -n1)"
        [[ -n "$so" ]] || exit 1
        install -m 755 "$so" "$LRDIR/dolphin_libretro.so" || exit 1
        mkdir -p "$ROOTFS/usr/local/share/rgos/dolphin-emu"
        cp -r "$ROOTFS/tmp/core-src/gc/Data/Sys" "$ROOTFS/usr/local/share/rgos/dolphin-emu/Sys" || exit 1
        cat > "$ROOTFS/tmp/core-src/keep-libs.sh" <<'KEEP'
ldd /usr/local/lib/libretro/dolphin_libretro.so | awk '/=>/ {print $3}' | xargs -r dpkg -S 2>/dev/null | cut -d: -f1 | sort -u | xargs -r apt-mark manual
KEEP
        chroot "$ROOTFS" sh /tmp/core-src/keep-libs.sh
      ); then echo "   dolphin_libretro.so built"
      else echo "!! could not build the GameCube core: GameCube will not appear on the RG Rotate (put a prebuilt dolphin_libretro.so in cores/ and rebuild)"; rm -f "$LRDIR/dolphin_libretro.so"; fi
    fi
  else
    echo "!! could not install a compiler in the rootfs: skipped building the Genesis Plus GX / Neo Geo Pocket / Atari / PlayStation cores"
  fi
  chroot "$ROOTFS" env DEBIAN_FRONTEND=noninteractive apt-get purge -y --auto-remove gcc g++ make git cmake ninja-build pkg-config '*-dev' >/dev/null 2>&1 || true
  if ! chroot "$ROOTFS" python3 -c 'import pygame' >/dev/null 2>&1; then
    echo "!! pygame is not importable after the toolchain purge; reinstalling python3-pygame"
    chroot "$ROOTFS" apt-get update >/dev/null 2>&1 || true
    chroot "$ROOTFS" env DEBIAN_FRONTEND=noninteractive apt-get install -y --reinstall python3-pygame || true
  fi
  rm -rf "$ROOTFS/tmp/core-src" "$ROOTFS/etc/resolv.conf"
fi
if [[ "$DEVICE" == "rg-rotate" && -e "$LRDIR/dolphin_libretro.so" ]]; then
  gc_missing() { chroot "$ROOTFS" sh -c 'ldd /usr/local/lib/libretro/dolphin_libretro.so 2>&1 | grep "not found"' || true; }
  GC_GONE="$(gc_missing)"
  if [[ -n "$GC_GONE" ]]; then
    echo "==> dolphin_libretro.so needs libraries that are not in the image, trying to install them:"; echo "$GC_GONE"
    cp -L /etc/resolv.conf "$ROOTFS/etc/resolv.conf" 2>/dev/null || true
    chroot "$ROOTFS" apt-get update >/dev/null 2>&1 || true
    for pkg in libevdev2 libudev1 libpulse0 libasound2t64 libcurl4t64 libpng16-16t64 libminizip1t64 liblzo2-2 libmbedcrypto16 libmbedtls21 \
               libmbedx509-7 libhidapi-hidraw0 libusb-1.0-0 libbluetooth3 libdrm2 libgbm1 libegl1 libgles2 libgl1 zlib1g libzstd1 libxxhash0 \
               libpugixml1v5 libminiupnpc17 libenet7 libfmt10 libbz2-1.0 liblzma5; do
      chroot "$ROOTFS" env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$pkg" >/dev/null 2>&1 || true
    done
    rm -f "$ROOTFS/etc/resolv.conf"
    GC_GONE="$(gc_missing)"
    [[ -z "$GC_GONE" ]] || { echo "!! dolphin_libretro.so still has missing libraries (GameCube will not start; install the matching Debian packages with EXTRA_PKGS=... or rebuild the core here):"; echo "$GC_GONE"; }
  fi
fi
CORES="$(ls "$ROOTFS"/usr/local/lib/libretro/*_libretro.so "$ROOTFS"/usr/lib/*/libretro/*_libretro.so "$ROOTFS"/usr/lib/libretro/*_libretro.so 2>/dev/null | xargs -rn1 basename | tr '\n' ' ' || true)"
echo "==> libretro cores in the image: ${CORES:-NONE}"
core_present() { local f; for f in "$ROOTFS"/usr/lib/*/libretro/"$1"_libretro.so "$ROOTFS/usr/lib/libretro/$1"_libretro.so "$ROOTFS/usr/local/lib/libretro/$1"_libretro.so; do [[ -e "$f" ]] && return 0; done; return 1; }
for c in gambatte mgba nestopia genesis_plus_gx snes9x mednafen_wswan mednafen_ngp pcsx_rearmed stella2014 atari800 prosystem; do
  core_present "$c" || echo "!! ${c}_libretro.so is missing from the image (a Debian libretro package missing, or the source build of that core failed)"
done
if [[ "$DEVICE" == "rg-rotate" && "$GC_REPO" != none ]]; then core_present dolphin || echo "!! dolphin_libretro.so is missing from the image: no GameCube on this build"; fi
core_present mednafen_psx || core_present pcsx_rearmed || echo "!! no PlayStation core (neither pcsx_rearmed nor mednafen_psx) is in the image"
[[ -x "$ROOTFS/usr/bin/retroarch" ]] || echo "!! retroarch is not in the image (package missing from $DEBIAN_SUITE?)"
for a in reboot poweroff halt; do ln -sf /bin/busybox "$ROOTFS/sbin/$a"; done
# The root is a read-only squashfs, so the boot-time "busybox --install" in rgos-init cannot create applet links and any command
# Debian's minbase lacks (unzip, xxd, pkill, ...) is missing for PortMaster. Link the missing applets now, into /usr/local/bin:
# only names with no real binary are linked, so no GNU tool is ever replaced by its busybox twin.
chroot "$ROOTFS" sh -c 'mkdir -p /usr/local/bin; for a in $(/bin/busybox --list); do command -v "$a" >/dev/null 2>&1 || ln -s /bin/busybox "/usr/local/bin/$a"; done'
echo "==> busybox fallback applets linked: $(ls "$ROOTFS/usr/local/bin" | wc -l)"
ln -sf /usr/share/fonts/truetype/dejavu "$ROOTFS/usr/share/fonts/dejavu" 2>/dev/null || true

cat > "$ROOTFS/usr/sbin/rgos-init" <<'INIT'
#!/bin/sh
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
mount -t proc proc /proc 2>/dev/null; mount -t sysfs sys /sys 2>/dev/null; mount -t devtmpfs dev /dev 2>/dev/null
# devtmpfs has no /dev/fd (udev/systemd normally makes it); bash process substitution <(...) and PortMaster need it
[ -e /dev/fd ] || ln -s /proc/self/fd /dev/fd 2>/dev/null
[ -e /dev/stdin ] || ln -s /proc/self/fd/0 /dev/stdin 2>/dev/null
[ -e /dev/stdout ] || ln -s /proc/self/fd/1 /dev/stdout 2>/dev/null
[ -e /dev/stderr ] || ln -s /proc/self/fd/2 /dev/stderr 2>/dev/null
[ -d /dev/shm ] || { mkdir -p /dev/shm && mount -t tmpfs -o mode=1777 tmpfs /dev/shm 2>/dev/null; }
[ -x /bin/busybox ] && /bin/busybox --install -s /usr/bin 2>/dev/null
# Boot logo: paint bootlogo-<W>x<H>.raw (32-bit B,G,R,X rows, see tools/bmp2fb.py) onto the framebuffer as soon as it
# exists, so the screen is never blank between U-Boot's logo and the first RG OS screen. Only touches a 32 bpp
# framebuffer whose stride and width match the file; anything else is left alone.
paint_logo() {
  fb=/sys/class/graphics/fb0
  [ -c /dev/fb0 ] && [ "$(cat $fb/bits_per_pixel 2>/dev/null)" = 32 ] || return 1
  vs=$(cat $fb/virtual_size 2>/dev/null); w=${vs%%,*}
  [ -n "$w" ] && [ "$(cat $fb/stride 2>/dev/null)" = "$((w * 4))" ] || return 1
  for f in "$1"/bootlogo-"$w"x*.raw; do [ -f "$f" ] && cat "$f" > /dev/fb0 2>/dev/null && return 0; done
  return 1
}
echo 0 > /sys/class/graphics/fbcon/cursor_blink 2>/dev/null
# paint the logo the moment the framebuffer shows up (the wait below, module loading, audio bring-up and the updater can
# take many seconds before the first RG OS screen); stops after the first success or 20 s
( n=0; until paint_logo /etc/rgos/bootlogo; do n=$((n + 1)); [ "$n" -ge 200 ] && break; sleep 0.1 2>/dev/null || sleep 1; done ) &

# no kernel / driver messages on the screen (they stay in dmesg and in rgos-logs.txt)
echo "0 4 1 7" > /proc/sys/kernel/printk 2>/dev/null
mountpoint -q /run || mount -t tmpfs tmpfs /run
mountpoint -q /tmp || mount -t tmpfs tmpfs /tmp
mount -t tmpfs -o mode=755 tmpfs /var 2>/dev/null
mkdir -p /var/log /var/lib/rgos /var/tmp /var/cache /boot /media/roms
bootdev=""; for d in /dev/mmcblk*p1; do [ -b "$d" ] && { bootdev=$d; break; }; done
if [ -n "$bootdev" ] && ! mountpoint -q /boot; then
  mp=$(awk -v d="$bootdev" '$1==d {print $2; exit}' /proc/mounts)
  if [ -n "$mp" ]; then
    mount -o remount,rw "$mp" 2>/dev/null || mount -o remount,rw "$bootdev" 2>/dev/null
    mount --bind "$mp" /boot 2>/dev/null
  fi
  mountpoint -q /boot || mount -t vfat -o rw,noatime "$bootdev" /boot 2>/dev/null
fi
if mountpoint -q /boot && mkdir -p /boot/rgos-data 2>/dev/null && touch /boot/rgos-data/.w 2>/dev/null; then
  rm -f /boot/rgos-data/.w; mount --bind /boot/rgos-data /var/lib/rgos 2>/dev/null
fi
for i in 1 2 3 4 5 6 7 8 9 10; do [ -e /dev/fb0 ] && break; sleep 1; done
[ -e /dev/fb0 ] || for pass in 1 2 3; do
  find /lib/modules -name '*.ko*' 2>/dev/null | while read -r m; do insmod "$m" 2>/dev/null; done
  [ -e /dev/fb0 ] && break
done
( sleep 6
  mkdir -p /run/bi
  for d in /dev/mmcblk*p1; do [ -b "$d" ] && mount -t vfat "$d" /run/bi 2>/dev/null && break; done
  mountpoint -q /run/bi || exit 0
  { echo "== uptime when written"; cat /proc/uptime; echo "== cmdline"; cat /proc/cmdline
    echo "== partitions"; cat /proc/partitions; echo "== blkid"; blkid; echo "== mounts"; cat /proc/mounts
    echo "== boot partition"; ls -la /run/bi; echo "== extlinux.conf"; cat /run/bi/extlinux/extlinux.conf
  } > /run/bi/rgos-bootinfo.txt 2>&1
  sync; umount /run/bi ) >/dev/null 2>&1 &
/opt/rgos/rgos-session >> /var/log/rgos-session.log 2>&1
for b in /sys/class/backlight/*; do [ -e "$b/max_brightness" ] && cat "$b/max_brightness" > "$b/brightness"; done
[ -e /dev/fb0 ] && tr '\0' '\377' < /dev/zero > /dev/fb0 2>/dev/null
while :; do sleep 3600; done
INIT
chmod +x "$ROOTFS/usr/sbin/rgos-init"
mkdir -p "$ROOTFS/usr/lib/systemd" "$ROOTFS/usr/lib/libreelec" "$ROOTFS/usr/lib/rocknix"
ln -sf ../../sbin/rgos-init "$ROOTFS/usr/lib/systemd/systemd"
ln -sf rgos-init            "$ROOTFS/usr/sbin/init"
ln -sf usr/sbin/rgos-init   "$ROOTFS/init"
# the root is read-only squashfs, so the /roms alias PortMaster-style scripts expect must be baked in (dangling until ROMS mounts)
ln -sfn /media/roms/roms "$ROOTFS/roms"
rm -f "$ROOTFS/usr/bin/qemu-aarch64-static"
if ! chroot "$ROOTFS" python3 -c 'import pygame; print("pygame", pygame.version.ver)'; then
  echo "==> pygame missing from the rootfs: installing python3-pygame"
  cp -L /etc/resolv.conf "$ROOTFS/etc/resolv.conf" 2>/dev/null || true
  chroot "$ROOTFS" apt-get update || true
  chroot "$ROOTFS" env DEBIAN_FRONTEND=noninteractive apt-get install -y python3-pygame || true
  rm -f "$ROOTFS/etc/resolv.conf"
  chroot "$ROOTFS" python3 -c 'import pygame; print("pygame", pygame.version.ver)' \
    || { echo "!! pygame still cannot be imported: the RG OS launcher would not start. Aborting the build." >&2; exit 1; }
fi
# DNS: the root is read-only squashfs, so /etc/resolv.conf must be baked in as a link to the file the Wi-Fi DHCP
# script writes at runtime (/run/rgos/resolv.conf). Without it every host lookup fails and downloads (artwork,
# PortMaster) always report "No internet". This also drops any build-host resolv.conf that apt left behind.
rm -f "$ROOTFS/etc/resolv.conf"
ln -s /run/rgos/resolv.conf "$ROOTFS/etc/resolv.conf"
rm -rf "$ROOTFS/var/cache/apt" "$ROOTFS/var/lib/apt/lists" "$ROOTFS/usr/share/doc" "$ROOTFS/usr/share/man" "$ROOTFS/usr/share/info" "$ROOTFS/usr/share/lintian"
find "$ROOTFS/usr/share/locale" -mindepth 1 -maxdepth 1 ! -name 'en*' ! -name locale.alias -exec rm -rf {} + 2>/dev/null || true

# Installer mode: PortMaster, every libretro core and ./extras/ leave SYSTEM and become the payload that the first-boot installer
# (rgos/installer.py) unpacks onto the ROMS partition after it has partitioned the card. cores.py / rgos-launch already search <ROMS>/cores.
PAYLOAD_DIR="$WORK/payload"; PAYLOAD_KB=0
if [[ "$MODE" == "installer" ]]; then
  echo "==> Installer mode: moving PortMaster and the libretro cores out of SYSTEM into the payload"
  rm -rf "$PAYLOAD_DIR" "$WORK/payload-src"; mkdir -p "$PAYLOAD_DIR" "$WORK/payload-src/cores"
  PAYLOAD_SPECS=()
  # Debian's cores first, then /usr/local/lib/libretro (cores built from source or prebuilt in cores/) so those win on a name clash
  for d in "$ROOTFS"/usr/lib/*/libretro "$ROOTFS/usr/lib/libretro" "$ROOTFS/usr/local/lib/libretro"; do
    [[ -d "$d" ]] || continue
    for so in "$d"/*_libretro.so; do [[ -e "$so" ]] && cp -fL "$so" "$WORK/payload-src/cores/"; done
    find "$d" -maxdepth 1 -name '*_libretro.so' -delete
  done
  NCORES="$(find "$WORK/payload-src/cores" -name '*_libretro.so' | wc -l)"
  echo "   $NCORES libretro cores -> payload"
  (( NCORES > 0 )) && PAYLOAD_SPECS+=("cores|Emulator cores|$WORK/payload-src/cores|roms|cores|") \
    || echo "!! no libretro cores found: the installer image will have no emulators until the Core Installer downloads some"
  if [[ -f "$ROOTFS/opt/rgos/seed/PortMaster/PortMaster.sh" ]]; then
    PAYLOAD_SPECS+=("portmaster|PortMaster|$ROOTFS/opt/rgos/seed|roms|roms/ports|roms/ports/PortMaster")
  else
    echo "   (no PortMaster seed: the payload has no PortMaster)"
  fi
  if [[ -d "$HERE/extras" ]] && [[ -n "$(find "$HERE/extras" -type f 2>/dev/null | head -n1)" ]]; then
    echo "   extras/ -> payload (unpacked into the root of the ROMS partition)"
    PAYLOAD_SPECS+=("extras|Extra files|$HERE/extras|roms||")
  fi
  (( ${#PAYLOAD_SPECS[@]} )) || { echo "!! nothing to put in the installer payload" >&2; exit 1; }
  python3 "$HERE/tools/mkpayload.py" "$PAYLOAD_DIR" "${UPDATE_ID:-$(date +%Y%m%d-%H%M%S)}" "$DEVICE" "${PAYLOAD_SPECS[@]}"
  # the seed and the cores now live in the payload; leaving them in SYSTEM would only make the squashfs bigger
  rm -rf "$ROOTFS/opt/rgos/seed"
  PAYLOAD_KB="$(du -sk "$PAYLOAD_DIR" | cut -f1)"
fi

echo "==> Precompiling Python bytecode"
chroot "$ROOTFS" python3 -m compileall -q --invalidation-mode checked-hash /opt/rgos /usr/lib/python3 /usr/lib/python3/dist-packages >/dev/null 2>&1 \
  || echo "   (bytecode precompile reported errors; continuing, the sources still work)"

echo "==> Building SYSTEM squashfs"
rm -f "$WORK/SYSTEM"
mksquashfs "$ROOTFS" "$WORK/SYSTEM" -comp "$COMP" -b "$BSIZE" -noappend -quiet
ls -la "$WORK/SYSTEM"

echo "==> Installing it on the boot partition"
FREE_KB="$(df -k --output=avail "$WORK/mnt" | tail -1)"
NEED_KB=$(( ( $(stat -c %s "$WORK/SYSTEM") - $(stat -c %s "$OLD_SYS") ) / 1024 + 1 + 4096 + PAYLOAD_KB ))
[[ $NEED_KB -lt $FREE_KB ]] || { echo "!! New SYSTEM doesn't fit on the boot partition"; exit 1; }
cp "$WORK/SYSTEM" "$WORK/mnt/SYSTEM"
BOOTLOGO="$HERE/bootlogo/bootlogo-$DEVICE.bmp"
if [[ -f "$BOOTLOGO" ]]; then
  echo "==> bootlogo.bmp <- $(basename "$BOOTLOGO") (shown by U-Boot while the console starts, until the installer / RG OS takes over)"
  cp -f "$BOOTLOGO" "$WORK/mnt/bootlogo.bmp"
else
  echo "!! $BOOTLOGO missing: the image gets no bootlogo.bmp (python3 tools/render-bootlogo.py creates it)"
fi
if [[ "$MODE" == "installer" ]]; then
  echo "==> Copying the installer payload to /rgos-payload on the boot partition (${PAYLOAD_KB} KiB)"
  rm -rf "$WORK/mnt/rgos-payload" "$WORK/mnt/rgos-installed.json" "$WORK/mnt/rgos-install-state.json"
  mkdir -p "$WORK/mnt/rgos-payload" && cp "$PAYLOAD_DIR"/* "$WORK/mnt/rgos-payload/"
  test -s "$WORK/mnt/rgos-payload/manifest.json" || { echo "!! the payload was not copied" >&2; exit 1; }
fi
if [[ -f "$WORK/mnt/SYSTEM.md5" ]]; then
  (cd "$WORK/mnt" && md5sum SYSTEM > SYSTEM.md5)
fi

echo "==> Building the RG OS initramfs (replaces ROCKNIX's init: no 60 s wait, no error screen)"
BB="$ROOTFS/bin/busybox"
[[ -x "$BB" ]] || { echo "!! $BB missing (busybox-static not installed in the rootfs?)"; exit 1; }
if readelf -lW "$BB" 2>/dev/null | grep -q INTERP; then echo "!! $BB is dynamically linked; the initramfs needs a static busybox"; exit 1; fi
INITRD_NAME="rgos-initrd.cpio"
LOGO_RAWS=(); [[ -d "$BOOTLOGO_RAW_DIR" ]] && LOGO_RAWS=("$BOOTLOGO_RAW_DIR"/*.raw)
python3 "$HERE/initramfs/mkinitramfs.py" "$BB" "$HERE/initramfs/init" "$WORK/mnt/$INITRD_NAME" ${LOGO_RAWS[@]+"${LOGO_RAWS[@]}"}
EXT="$WORK/mnt/extlinux/extlinux.conf"; [[ -f "$EXT" ]] || EXT="$WORK/mnt/extlinux.conf"
[[ -f "$EXT" ]] || { echo "!! no extlinux.conf on the boot partition"; exit 1; }
rm -f "$WORK/mnt/white.cpio.gz"
sed -i "s/boot=LABEL=ROCKNIX/boot=LABEL=$BOOT_LABEL/g" "$EXT"
grep -q "boot=LABEL=$BOOT_LABEL" "$EXT" || echo "   (note: no boot=LABEL=... argument found in extlinux.conf; nothing to rewrite)"
! grep -q "LABEL=ROCKNIX" "$EXT" || { echo "!! extlinux.conf still refers to LABEL=ROCKNIX" >&2; exit 1; }
cp "$EXT" "$(dirname "$EXT")/extlinux.conf.stock"
if [[ "$RGOS_INITRD" == 1 ]]; then
  echo "==> Patched extlinux config:"
  python3 "$HERE/initramfs/patch-extlinux.py" "$EXT" "/$INITRD_NAME"
  grep -qi "^[[:space:]]*initrd[[:space:]]\+/$INITRD_NAME" "$EXT" && grep -q 'rdinit=/rgos-init' "$EXT" \
    || { echo "!! extlinux.conf was not patched correctly"; exit 1; }
else
  echo "==> RGOS_INITRD=0: extlinux.conf left exactly as shipped (no INITRD, no rdinit); ROCKNIX's own init starts RG OS"
  echo "    (rgos-initrd.cpio is still copied to the card, unused, so offline updates keep working; RGOS_INITRD=1 enables the RG OS initramfs)"
fi

if [[ "$MODE" == "update" ]]; then
  rm -rf "$WORK/upd"; mkdir -p "$WORK/upd"
  cp "$WORK/mnt/SYSTEM" "$WORK/mnt/$INITRD_NAME" "$WORK/upd/"
  [[ -f "$WORK/mnt/SYSTEM.md5" ]] && cp "$WORK/mnt/SYSTEM.md5" "$WORK/upd/"
  [[ "${UPDATE_EXTLINUX:-0}" == "1" ]] && cp "$EXT" "$WORK/upd/extlinux.conf"
  [[ ( "$DEVICE" == "rg34xxsp" || "$DEVICE" == "rg35xxh" || "$DEVICE" == "rg35xxsp" ) && "${UPDATE_DTB:-0}" == "1" ]] && cp "$WORK/mnt/dtb.img" "$WORK/upd/dtb.img"
fi

{ echo "RG OS image info (written by build.sh)"
  echo "device: $DEVICE"
  echo "base image: $(basename "$ROCKNIX_URL")"
  if [[ "$PTABLE" == dos ]]; then
    echo "h700 ram type: $H700_RAM   (the U-Boot on this card only starts consoles with this RAM; black screen + nothing written = wrong type, rebuild with H700_RAM=DDR3 or DDR4)"
    echo "device tree: $H700_DTB   (screen black or garbage = wrong panel revision, rebuild with the other one)"
  fi
  [[ "$MODE" == "installer" ]] && echo "installer image: first boot partitions the card and installs the payload (/rgos-payload)"
  echo "build: $(date -u +%Y-%m-%dT%H:%MZ)"
} > "$WORK/mnt/rgos-image-info.txt"
sync
umount "$WORK/mnt"; losetup -d "$LOOP"; LOOP=""

if [[ "$MODE" == "update" ]]; then
  UPD_ID="${UPDATE_ID:-$(date +%Y%m%d-%H%M%S)}"
  UPD_TAR="$OUT/rgos-update-$DEVICE-$UPD_ID.tar"
  ARGS=("SYSTEM=$WORK/upd/SYSTEM" "rgos-initrd.cpio=$WORK/upd/$INITRD_NAME")
  [[ -f "$WORK/upd/SYSTEM.md5" ]] && ARGS+=("SYSTEM.md5=$WORK/upd/SYSTEM.md5")
  [[ -f "$WORK/upd/extlinux.conf" ]] && ARGS+=("extlinux/extlinux.conf=$WORK/upd/extlinux.conf")
  [[ -f "$WORK/upd/dtb.img" ]] && ARGS+=("dtb.img=$WORK/upd/dtb.img")
  rm -f "$OUT"/rgos-update-"$DEVICE"-*.tar
  python3 "$HERE/tools/mkupdate.py" "$UPD_TAR" "$UPD_ID" "$(cat "$ROOTFS/etc/rgos-device")" "${ARGS[@]}"
  rm -rf "$WORK/upd"
  echo
  echo "Done: $UPD_TAR"
  echo "Copy it to the update/ folder of the ROMS partition (or the boot partition) and reboot the device; it installs it and restarts."
  exit 0
fi

if [[ "$PTABLE" == gpt ]]; then
  echo "==> Partitions in the image (partition 3 must be 'uboot'; ROMS is created on first boot as partition 4):"
  sfdisk -l "$IMG" 2>/dev/null | grep -E '^(/|Device)' || true
  sgdisk -i 3 "$IMG" 2>/dev/null | grep -q "^Partition name: 'uboot'" || { echo "!! partition 3 of the image is not 'uboot': the device would boot Android"; exit 1; }
else
  echo "==> Partitions in the image (MBR; ROMS is created on first boot as partition 3):"
  sfdisk -l "$IMG" 2>/dev/null | grep -E '^(/|Device|Disklabel)' || true
  sfdisk -d "$IMG" 2>/dev/null | grep -q '^label: dos' || { echo "!! the stock H700 image is not an MBR (dos) image: rgos-roms would not know how to add ROMS"; exit 1; }
  [[ "$(sfdisk -d "$IMG" 2>/dev/null | grep -c "^$IMG[0-9]* :")" -le 3 ]] || { echo "!! the image already has 4 partitions: no slot left for ROMS"; exit 1; }
fi

echo
echo "Done: $IMG"
[[ "$MODE" != "installer" ]] || echo "This is an INSTALLER image: write it to the SD card and boot. The first boot partitions the card, installs PortMaster and the cores (progress screen), then restarts into RG OS."
echo "To go back to ROCKNIX's own init: copy extlinux/extlinux.conf.stock over extlinux/extlinux.conf on the card's FAT partition."
echo "RG OS logs are copied to rgos-logs.txt on the card's FAT partition at 8, 28 and 58 s after boot."
if [[ "$DEVICE" == "rg-rotate" ]]; then
  echo "Flash the SPL once (cd spl-flasher && ./flash-spl.sh), then write the image to the SD card."
else
  echo "Built for $H700_RAM RAM. The H700 U-Boot on the card is specific to the RAM type: if the console stays black and nothing is written to the card, rebuild with the other one (H700_RAM=DDR3 / DDR4; unsure which? try DDR4 first, then DDR3)."
  echo "Write the image to the SD card (the H700 boots straight from it; no SPL flashing). dtb.img = $H700_DTB.dtb; to change it, rebuild with RG34XXSP_DTB=... / RG35XXH_DTB=... / RG35XXSP_DTB=... (device_trees/ is not on the card)."
fi
