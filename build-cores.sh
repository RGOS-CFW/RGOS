#!/usr/bin/env bash
# Builds the pre-installed emulator cores once and keeps them in work/cores/. build.sh then uses them instead of compiling.
#   sudo ./build-cores.sh              build every core
#   sudo ./build-cores.sh flycast      build one (several allowed: sudo ./build-cores.sh n64 psx)
#   sudo ./build-cores.sh --list       list the names      |  --clean: wipe work/cores and work/cores-src
# Output: work/cores/*_libretro.so, work/cores/bin/flycast (standalone), work/cores/dolphin-Sys/, work/cores/deps/<name>.txt
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="$HERE/work"; OUTC="$WORK/cores"; SRC="$WORK/cores-src"; LOGS="$WORK/cores-logs"; B="$WORK/cores-builder/rootfs"
DEBIAN_SUITE="${DEBIAN_SUITE:-trixie}"; DEBIAN_MIRROR="${DEBIAN_MIRROR:-http://deb.debian.org/debian}"
NGP_SRC="${NGP_SRC:-https://github.com/libretro/beetle-ngp-libretro/archive/refs/heads/master.tar.gz}"
GENESIS_REPO="${GENESIS_REPO:-https://github.com/libretro/Genesis-Plus-GX.git}"
PSX_REPO="${PSX_REPO:-https://github.com/libretro/pcsx_rearmed.git}"
GC_REPO="${GC_REPO:-https://github.com/libretro/dolphin.git}"
DC_REPO="${DC_REPO:-https://github.com/flyinghead/flycast.git}"
DC_MAKE_ARGS="${DC_MAKE_ARGS:-platform=unix FORCE_GLES=1}"
DC_SA_CMAKE_ARGS="${DC_SA_CMAKE_ARGS:-}"
N64_REPO="${N64_REPO:-https://github.com/libretro/mupen64plus-libretro-nx.git}"
N64_MAKE_ARGS="${N64_MAKE_ARGS:-platform=unix FORCE_GLES=1}"
SATURN_REPO="${SATURN_REPO:-https://github.com/libretro/yabasanshiro.git}"
SATURN_MAKE_DIR="${SATURN_MAKE_DIR:-yabause/src/libretro}"; SATURN_MAKE_ARGS="${SATURN_MAKE_ARGS:-platform=unix}"
PICO8_REPO="${PICO8_REPO:-https://github.com/jtothebell/fake-08.git}"; PICO8_ALT_REPO="${PICO8_ALT_REPO:-https://github.com/libretro/retro8.git}"
PICO8_MAKE_DIR="${PICO8_MAKE_DIR:-platform/libretro}"; PICO8_MAKE_ARGS="${PICO8_MAKE_ARGS:-platform=unix}"
STELLA_REPO="${STELLA_REPO:-https://github.com/libretro/stella2014-libretro.git}"
ATARI800_REPO="${ATARI800_REPO:-https://github.com/libretro/libretro-atari800.git}"
PROSYSTEM_REPO="${PROSYSTEM_REPO:-https://github.com/libretro/prosystem-libretro.git}"
MAME2003_REPO="${MAME2003_REPO:-https://github.com/libretro/mame2003-plus-libretro.git}"
MAME_REPO="${MAME_REPO:-https://github.com/libretro/mame.git}"   # current full MAME: huge (hours, 16 GB+ RAM under qemu), only built when named
MAME_MAKE_ARGS="${MAME_MAKE_ARGS:-SUBTARGET=mame PTR64=1 NOWERROR=1}"

ALL=(ngp genesis stella2014 atari800 prosystem mame2003_plus psx flycast flycast-standalone n64 saturn fake08 retro8 dolphin)
EXTRA=(mame)   # only built when named explicitly
usage() { cat <<U
usage: sudo ./build-cores.sh [--list | --clean | <core>...]
cores: ${ALL[*]}  (+ ${EXTRA[*]}, explicit only)
aliases: gen=genesis dc/dreamcast=flycast dcsa/flycast-sa=flycast-standalone mupen/n64=n64 yaba/yabasanshiro/saturn=saturn
         pico8=fake08+retro8 atari=stella2014+atari800+prosystem gc/gamecube=dolphin
no argument builds everything (dolphin included: GameCube is only used by the rg-rotate build).
U
}
want=()
for a in "$@"; do
  a="$(printf '%s' "$a" | tr 'A-Z_' 'a-z-')"; a="${a%_libretro.so}"; a="${a%-libretro.so}"
  case "$a" in
    -h|--help|help) usage; exit 0 ;;
    --list) printf '%s\n' "${ALL[@]}"; exit 0 ;;
    --clean) rm -rf "$OUTC" "$SRC" "$LOGS"; echo "cleaned work/cores, work/cores-src, work/cores-logs"; exit 0 ;;
    all) want+=("${ALL[@]}") ;;
    ngp|mednafen-ngp|mednafen-ngp-libretro) want+=(ngp) ;;
    genesis|gen|genesis-plus-gx) want+=(genesis) ;;
    stella2014|stella|atari2600) want+=(stella2014) ;;
    atari800|atari5200) want+=(atari800) ;;
    prosystem|atari7800) want+=(prosystem) ;;
    atari) want+=(stella2014 atari800 prosystem) ;;
    psx|pcsx|pcsx-rearmed|playstation) want+=(psx) ;;
    flycast|dc|dreamcast) want+=(flycast) ;;
    flycast-standalone|flycast-sa|dcsa) want+=(flycast-standalone) ;;
    n64|mupen|mupen64plus|mupen64plus-next) want+=(n64) ;;
    saturn|yaba|yabasanshiro) want+=(saturn) ;;
    fake08|fake-08) want+=(fake08) ;;
    retro8) want+=(retro8) ;;
    pico8) want+=(fake08 retro8) ;;
    dolphin|gc|gamecube) want+=(dolphin) ;;
    mame2003|mame2003-plus|mame2003plus) want+=(mame2003_plus) ;;
    mame|mame-full) want+=(mame) ;;
    *) echo "unknown core '$a'" >&2; usage >&2; exit 1 ;;
  esac
done
(( ${#want[@]} )) || want=("${ALL[@]}")
mapfile -t want < <(printf '%s\n' "${ALL[@]}" "${EXTRA[@]}" | grep -Fxf <(printf '%s\n' "${want[@]}"))   # unique, in build order

if [[ $EUID -ne 0 ]]; then
  command -v sudo >/dev/null || { echo "ERROR: needs root (run as root or install sudo)" >&2; exit 1; }
  exec sudo -E bash "${BASH_SOURCE[0]}" "$@"
fi
need=(debootstrap git wget tar); [[ "$(uname -m)" == aarch64 ]] || need+=(qemu-aarch64-static)
for t in "${need[@]}"; do command -v "$t" >/dev/null || { echo "Missing tool: $t"; echo "apt install debootstrap qemu-user-static binfmt-support git wget"; exit 1; }; done
mkdir -p "$OUTC/bin" "$OUTC/deps" "$SRC" "$LOGS"

mounts() { mountpoint -q "$B/proc" || { mount -t proc proc "$B/proc"; mount --bind /dev "$B/dev"; mount -t sysfs sys "$B/sys" 2>/dev/null || true; }; }
unmounts() { set +e; for m in sys dev proc; do mountpoint -q "$B/$m" && umount -l "$B/$m"; done; }
trap unmounts EXIT
cx() { chroot "$B" "$@"; }
apt_in() { for p in "$@"; do cx env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$p" >>"$LOGS/apt.log" 2>&1 || echo "   (could not install $p, continuing)"; done; }

# Same Debian suite/arch as the image's rootfs, so every core links against the library versions the image has.
if [[ ! -x "$B/usr/bin/gcc" ]]; then
  echo "==> Creating the arm64 $DEBIAN_SUITE builder (once, kept in work/cores-builder)"
  if [[ ! -f "$B/debootstrap/debootstrap" && ! -x "$B/bin/sh" ]]; then
    rm -rf "$B"; mkdir -p "$B"
    debootstrap --arch=arm64 --variant=minbase --foreign --components=main,non-free "$DEBIAN_SUITE" "$B" "$DEBIAN_MIRROR"
    [[ "$(uname -m)" == aarch64 ]] || cp "$(command -v qemu-aarch64-static)" "$B/usr/bin/"
    chroot "$B" /debootstrap/debootstrap --second-stage
  fi
  mkdir -p "$B/proc" "$B/dev" "$B/sys"; cp -L /etc/resolv.conf "$B/etc/resolv.conf"; mounts
  cx apt-get update >>"$LOGS/apt.log" 2>&1
  cx env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends gcc g++ make git ca-certificates cmake ninja-build pkg-config file >>"$LOGS/apt.log" 2>&1 \
    || { echo "!! could not install the compiler in the builder (see $LOGS/apt.log)"; exit 1; }
fi
cp -L /etc/resolv.conf "$B/etc/resolv.conf"; mounts
mkdir -p "$B/tmp/core-src"

# helpers -----------------------------------------------------------------------------------------------------------------
fetch() { rm -rf "$SRC/$1"; git clone -q --depth 1 --recurse-submodules --shallow-submodules "$2" "$SRC/$1"; rm -rf "$B/tmp/core-src/$1"; cp -r "$SRC/$1" "$B/tmp/core-src/$1"; }
# run a build command in the chroot, retrying with fewer jobs (big C++ projects get OOM-killed in small VMs); $1=log, $2=command with @J@ for the job count
retry() { local log="$1" cmd="$2" j; for j in "$(nproc)" 2 1; do echo "   -j$j (log: $log)"; cx sh -c "${cmd//@J@/$j}" >>"$log" 2>&1 && return 0; echo "   -j$j failed, retrying with fewer jobs"; done; tail -n 40 "$log"; return 1; }
no_desktop_gl() { readelf -d "$1" 2>/dev/null | grep -Eq 'NEEDED.*\[(libGL|libOpenGL)\.so' && { echo "$(basename "$1") links desktop OpenGL (libGL), not OpenGL ES"; return 1; } || return 0; }
# remember which Debian runtime packages a binary needs: build.sh installs them in the image (the image has no -dev / build deps)
save_deps() { # $1=name $2=path inside the builder
  cx sh -c "ldd '$2' | awk '/=>/ {print \$3}' | xargs -r dpkg -S 2>/dev/null | cut -d: -f1 | sort -u" > "$OUTC/deps/$1.txt" || true; }
take() { install -m 755 "$1" "$OUTC/$2"; save_deps "${2%.so}" "${1#"$B"}"; }
find_so() { find "$B/tmp/core-src/$1" -name "$2" -type f | head -n1; }
simple_make() { # name repo so [make args]
  local n="$1" repo="$2" so="$3"; shift 3; local log="$LOGS/$n.log"; : > "$log"
  fetch "$n" "$repo"; retry "$log" "cd /tmp/core-src/$n && make $* -j@J@"; local f; f="$(find_so "$n" "$so")"
  [[ -n "$f" ]] || { echo "$so was not produced (log: $log)"; return 1; }; take "$f" "$so"; }

build_ngp() { rm -rf "$SRC/ngp" "$B/tmp/core-src/ngp"; mkdir -p "$SRC/ngp" "$B/tmp/core-src/ngp"
  wget -q -O "$SRC/ngp.tar.gz" "$NGP_SRC"; tar -xzf "$SRC/ngp.tar.gz" -C "$B/tmp/core-src/ngp" --strip-components=1
  retry "$LOGS/ngp.log" "cd /tmp/core-src/ngp && make -j@J@"; take "$(find_so ngp mednafen_ngp_libretro.so)" mednafen_ngp_libretro.so; }
build_genesis() { simple_make genesis "$GENESIS_REPO" genesis_plus_gx_libretro.so -f Makefile.libretro platform=unix; }
build_stella2014() { simple_make stella2014 "$STELLA_REPO" stella2014_libretro.so; }
build_atari800() { simple_make atari800 "$ATARI800_REPO" atari800_libretro.so; }
build_prosystem() { simple_make prosystem "$PROSYSTEM_REPO" prosystem_libretro.so; }
build_psx() { simple_make psx "$PSX_REPO" pcsx_rearmed_libretro.so -f Makefile.libretro; }
build_mame2003_plus() { simple_make mame2003_plus "$MAME2003_REPO" mame2003_plus_libretro.so platform=unix; }
build_mame() { local log="$LOGS/mame.log"; : > "$log"; apt_in python3 libasound2-dev; fetch mame "$MAME_REPO"
  retry "$log" "cd /tmp/core-src/mame && make -f Makefile.libretro $MAME_MAKE_ARGS -j@J@"
  local so; so="$(find_so mame 'mame*_libretro.so')"; [[ -n "$so" ]] || { echo "mame_libretro.so was not produced (log: $log)"; return 1; }
  take "$so" mame_libretro.so; }
build_retro8() { simple_make retro8 "$PICO8_ALT_REPO" retro8_libretro.so platform=unix; }
build_fake08() { local log="$LOGS/fake08.log"; : > "$log"; fetch fake08 "$PICO8_REPO"
  retry "$log" "cd /tmp/core-src/fake08/$PICO8_MAKE_DIR && make $PICO8_MAKE_ARGS -j@J@"; take "$(find_so fake08 fake08_libretro.so)" fake08_libretro.so; }
build_n64() { local log="$LOGS/n64.log"; : > "$log"; apt_in libgles-dev libegl-dev zlib1g-dev libpng-dev; fetch n64 "$N64_REPO"
  retry "$log" "cd /tmp/core-src/n64 && make -f Makefile $N64_MAKE_ARGS -j@J@"
  local so; so="$(find_so n64 mupen64plus_next_libretro.so)"; [[ -n "$so" ]] || { echo "mupen64plus_next_libretro.so was not produced"; return 1; }
  no_desktop_gl "$so"; take "$so" mupen64plus_next_libretro.so; }
build_saturn() { local log="$LOGS/saturn.log"; : > "$log"; apt_in libgles-dev libegl-dev zlib1g-dev libpng-dev; fetch saturn "$SATURN_REPO"
  retry "$log" "cd /tmp/core-src/saturn/$SATURN_MAKE_DIR && make -f Makefile $SATURN_MAKE_ARGS -j@J@"
  local so; so="$(find_so saturn yabasanshiro_libretro.so)"; [[ -n "$so" ]] || { echo "yabasanshiro_libretro.so was not produced"; return 1; }
  no_desktop_gl "$so"; take "$so" yabasanshiro_libretro.so; }
build_flycast() { local log="$LOGS/flycast.log"; : > "$log"
  apt_in libgles-dev libegl-dev zlib1g-dev libcurl4-openssl-dev pkg-config libzip-dev libasound2-dev; fetch flycast "$DC_REPO"; local ok=0
  if [[ -f "$B/tmp/core-src/flycast/Makefile" ]] && retry "$log" "cd /tmp/core-src/flycast && make -f Makefile $DC_MAKE_ARGS -j@J@"; then ok=1; fi
  (( ok )) || retry "$log" "cd /tmp/core-src/flycast && rm -rf build-gles && cmake -S . -B build-gles -G Ninja -DCMAKE_BUILD_TYPE=Release -DLIBRETRO=ON -DUSE_GLES=ON -DUSE_GLES2=OFF -DUSE_OPENGL=ON -DUSE_VULKAN=OFF -DUSE_OPENMP=OFF && cmake --build build-gles -j@J@"
  local so; so="$(find_so flycast flycast_libretro.so)"; [[ -n "$so" ]] || { echo "flycast_libretro.so was not produced"; return 1; }
  no_desktop_gl "$so"; take "$so" flycast_libretro.so; }
build_flycast_standalone() { local log="$LOGS/flycast-standalone.log"; : > "$log"
  apt_in cmake ninja-build pkg-config libsdl2-dev libgles-dev libegl-dev libgbm-dev libdrm-dev zlib1g-dev libcurl4-openssl-dev libzip-dev libasound2-dev libpulse-dev
  fetch flycast-sa "$DC_REPO"
  retry "$log" "cd /tmp/core-src/flycast-sa && rm -rf build-sa && cmake -S . -B build-sa -G Ninja -DCMAKE_BUILD_TYPE=Release -DUSE_GLES=ON -DUSE_GLES2=OFF -DUSE_OPENGL=ON -DUSE_VULKAN=OFF -DUSE_HOST_SDL=ON -DUSE_OPENMP=OFF -DUSE_DISCORD=OFF $DC_SA_CMAKE_ARGS && cmake --build build-sa -j@J@"
  local exe; exe="$(find "$B/tmp/core-src/flycast-sa/build-sa" -maxdepth 1 -name flycast -type f -perm -u+x | head -n1)"
  [[ -n "$exe" ]] || { echo "no flycast executable was produced"; return 1; }
  no_desktop_gl "$exe"; install -m 755 "$exe" "$OUTC/bin/flycast"; save_deps flycast-standalone "${exe#"$B"}"; }
build_dolphin() { local log="$LOGS/dolphin.log"; : > "$log"
  cx env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends libevdev-dev libudev-dev libasound2-dev libpulse-dev libgl-dev libegl-dev libgles-dev libdrm-dev libgbm-dev libusb-1.0-0-dev libbluetooth-dev libcurl4-openssl-dev libpng-dev libminizip-dev liblzo2-dev libmbedtls-dev libhidapi-dev zlib1g-dev libxi-dev libxrandr-dev libx11-dev >>"$LOGS/apt.log" 2>&1 || { echo "dolphin build dependencies failed to install (see $LOGS/apt.log)"; return 1; }
  fetch dolphin "$GC_REPO"
  cx sh -c 'cd /tmp/core-src/dolphin && cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_FLAGS=-mtune=cortex-a75 -DCMAKE_CXX_FLAGS=-mtune=cortex-a75 -DLIBRETRO=ON -DENABLE_QT=OFF -DENABLE_NOGUI=OFF -DENABLE_X11=OFF -DENABLE_TESTS=OFF -DENABLE_ANALYTICS=OFF -DENABLE_LTO=OFF -DUSE_DISCORD_PRESENCE=OFF -DENABLE_CLI_TOOL=OFF' >>"$log" 2>&1 \
    && retry "$log" "cd /tmp/core-src/dolphin && cmake --build build -j@J@"
  local so; so="$(find_so dolphin dolphin_libretro.so)"; [[ -n "$so" ]] || { echo "dolphin_libretro.so was not produced"; return 1; }
  take "$so" dolphin_libretro.so; rm -rf "$OUTC/dolphin-Sys"; cp -r "$B/tmp/core-src/dolphin/Data/Sys" "$OUTC/dolphin-Sys"; }

# main --------------------------------------------------------------------------------------------------------------------
ok=(); failed=()
for c in "${want[@]}"; do
  echo; echo "==> Building $c"
  if ( set -e; "build_${c//-/_}" ); then echo "   $c OK"; ok+=("$c"); else echo "!! $c FAILED (logs in $LOGS)"; failed+=("$c"); fi
  rm -rf "$B/tmp/core-src/${c}" "$B/tmp/core-src/flycast-sa"
done
echo; echo "Built: ${ok[*]:-none}"; echo "Cores in $OUTC: $(ls "$OUTC" | grep -E '_libretro\.so$|^bin$|^dolphin-Sys$' | tr '\n' ' ')"
(( ${#failed[@]} == 0 )) || { echo "!! FAILED: ${failed[*]}" >&2; exit 1; }
echo "Now run: sudo ./build.sh <device>   (it uses work/cores automatically)"
