# Nintendo GameCube (RG Rotate only)

GameCube runs through RetroArch with the **Dolphin libretro** core (`dolphin_libretro.so`). It is built from source (`GC_REPO`, default `https://github.com/libretro/dolphin.git`) **only when building `rg-rotate`**. The `rg34xxsp` and `rg35xxh` builds never compile or ship it, and `menu.py` hides the system on any other device.

**GameCube only, no Wii.** The Dolphin core can technically run both, so there is no Wii menu entry, no `roms/wii` folder, and `.wbfs`/`.wad` are not accepted. Wii games placed in `roms/gc` are not supported (`.iso` is shared by both consoles, so keep Wii dumps out of that folder).

* ROMs: `<ROMS>/roms/gc/*.gcm`, `.iso`, `.gcz`, `.rvz`, `.ciso`, `.m3u`, `.dol`, `.elf`.
* Saves: `<ROMS>/saves/gc/`, states: `<ROMS>/states/gc/`.
* Dolphin's `Sys` data folder is shipped in the image and copied once to `<ROMS>/bios/dolphin-emu/Sys` on the first GameCube launch.
* Optional GameCube BIOS (boot logo): `IPL.bin` in `<ROMS>/bios/dolphin-emu/Sys/GC/<USA|EUR|JAP>/`.

## Build options

    sudo ./build.sh rg-rotate          # includes the GameCube core
    GC_REPO=none sudo -E ./build.sh rg-rotate   # skip it (faster build)

A prebuilt aarch64 `dolphin_libretro.so` in `cores/` is used instead of building (and is deleted again for every device except `rg-rotate`). In GitHub Actions use the *build_gc* checkbox.

The build is best-effort, like the other source-built cores: if it fails, a `!!` line is printed and the image is built without GameCube. It is slow under qemu emulation (plan on a long run).


## Runtime dependency fix

The Dolphin core may fail to load with `liblzo2.so.2: cannot open shared object file` when a prebuilt `dolphin_libretro.so` is used. RG OS now includes Debian's `liblzo2-2` runtime package in the base image so this dependency is present even for prebuilt cores. Rebuild the image or install `liblzo2-2` on an existing Debian-based RG OS image.


## Performance tuning

Every GameCube launch gets a tuned set of Dolphin core options, written to `/run/rgos/dolphin-options.cfg` and handed to RetroArch (`core_options_path`). They target the RG Rotate's Mali-G52 GPU, which is the usual bottleneck:

* **Native resolution** (`dolphin_efb_scale = x1`). The biggest single speed-up; raise it only for light games.
* **ARM64 JIT CPU core (`JITARM64`) + fastmem**, **DSP HLE** (the x86-only `JIT64` and DSP JIT are never requested on aarch64), GPU-side EFB copies, no forced texture filtering.
* **A-sync ubershaders**, so a new effect never freezes the game while its shader compiles. The first minutes of a game can still hitch a little while the shader cache fills; it gets smoother with play.
* **Frame pacing.** GameCube launches turn on adaptive vsync, a third swapchain image and a larger audio buffer, so a game that runs at 50-58 fps no longer drops to 30 fps or crackles. The CPU and GPU governors are already set to `performance` for GameCube (see `/boot/rgos-governor.txt`).
* **Safe retry.** If a game dies within 30 s, the retry also turns fastmem off and uses the cached interpreter. This retry also happens when a video driver is pinned in `/boot/retroarch-gc-video.txt`.

To change any option, create `<ROMS>/config/dolphin-options.cfg` with lines such as:

    dolphin_efb_scale = "x2 (1280 x 1056)"
    dolphin_shader_compilation_mode = "sync UberShaders"
    dolphin_fastmem = "disabled"

Your lines win over the built-in ones, including in the retry. Remove the file to go back to the defaults. A prebuilt `dolphin_libretro.so` is unaffected by the build flag; a core built by `build.sh` is compiled with `-mtune=cortex-a75`.

## If a GameCube game closes right after launching

RG OS now does these things itself; each one was a way for the game to "just close" without a message:

* **Dolphin `Sys` folder.** A half-copied `<ROMS>/bios/dolphin-emu/Sys` (interrupted copy, or the exFAT card refusing file permissions) used to count as done forever. Now a stamp file is written only after a complete copy, so an incomplete folder is finished on the next launch and a new image build refreshes the shipped files. Your own files (`IPL.bin`) are left alone.
* **Missing libraries.** Before starting, the launcher runs `ldd` on the core and, if a library is missing, shows its name instead of closing. `build.sh` does the same check at build time for `rg-rotate` and tries to install what is missing.
* **Video driver.** Dolphin needs a real GL context. GameCube launches pin RetroArch to `glcore` and, if that dies within 30 s, retry once with `gl`. To force one driver, put one word (`glcore`, `gl`, `vulkan`) in `/boot/retroarch-gc-video.txt`.
* **A readable report.** GameCube launches always use RetroArch's verbose log. After every launch `/boot/rgos-retroarch.txt` (on the FAT partition, readable on a PC) holds the command, the missing libraries (if any), the log of every attempt, the exit code or the signal that killed it (for example `SIGSEGV`), and kernel lines about segfaults, out-of-memory kills and GPU errors.

If it still closes, send `rgos-retroarch.txt` and `rgos-logs.txt` from the boot partition.

See also: [SYSTEMS.md](SYSTEMS.md), [BIOS.md](BIOS.md), [LOGS.md](LOGS.md).
