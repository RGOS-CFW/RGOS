# Tests

Plain `unittest`, standard library only: no pygame, device or root needed (`menu.py` is imported with its hardware modules mocked).

    python3 -m unittest discover -s tests -t . -v      # run everything, from the repo root
    python3 -m unittest tests.test_buttonmap           # one file

| File | Covers |
| --- | --- |
| `test_buttonmap.py` | Map buttons wizard: button steps, L3/R3, stick calibration, skipping, retrying a failed step. Runs against a fake hub and a fake clock, so it is instant. |
| `test_dpadjoy.py` | DPAD to joystick: D-pad becomes left-stick axes only in a game and only when the setting is on, diagonals on the unit circle, a held direction handed over cleanly when the setting or the game changes, a real stick still works; the Menu+Select combo (either press order) is swallowed, a short press turns it on with one buzz, holding turns it off with two, a failed save stays silent, the flag file the in-game menu uses to ignore that Menu tap, the non-blocking `Buzzer`, and the in-game menu reading stick Y as up / down. |
| `test_dpadjoy_setting.py` | Settings > DPAD to joystick row, icon, and the on/off file shared with the hub. |
| `test_hub.py` | `rgos-input`: stick scaling and deadzone, loading the calibration, the live stick feed the wizard reads, button translation. |
| `test_info.py` | Settings > Information text helpers and row list. |
| `test_stick_nav.py` | Menu navigation with the left stick: directions, threshold and hysteresis, auto-repeat, screen-off reset. |
| `test_filemanager.py` | File manager: protected boot files stay protected (including names that start with `..`); `human_size` rolls over to the next unit when the value rounds up (no "1024.0 KB"). |
| `test_volume.py` | `rgos-volume`: the ALSA card from `hw.json` (card 0 is a real card, not "unset"); the in-game volume indicator (`Announcer`: first press shows at once, a held button sends one settled message instead of flooding RetroArch's 8-slot queue). |
| `test_overlay.py` | `rgos-overlay` (the system-wide volume bar): volume/theme file parsing, mapping the bar rectangle onto a rotated framebuffer, and the draw / re-cover / restore logic when a program repaints underneath it or flips pages. |
| `test_gamemenu.py` | In-game menu (`gamemenu.py`): items per game kind, the confirm step for Restart / Exit, Menu tap vs hold vs hotkey combo, pad event translation, pause / resume / restart / exit / save / load for RetroArch (network commands) and native ports (signals), the open -> use -> close order (pixels restored before the game resumes), layout bounds at several screen sizes, and the `ingame` flag / restart request written by `rgos-launch`. |
| `test_dhcp.py` | `rgos-wifi-dhcp`: lease script order (routes flushed before the address is added, so the default route sticks) and resolv.conf. |
| `test_btctl.py` | `btctl`: the saved Bluetooth on/off setting is applied at boot (off stays off). |
| `test_splash.py` | `splash.read_conf`: a malformed splash.json falls back to the defaults instead of raising. |
| `test_keymap.py` | `rgos-input` `load_keymap`: a non-object keymap is ignored and one bad button-map entry keeps the good ones. |
| `test_sshctl.py` | `sshctl.read_password`: a UTF-8 BOM / CRLF in `ssh-password.txt` is not part of the root password. |
| `test_hwctl.py` | `hwctl`: rumble GPIO selection (pin 0 is valid) and `load_conf` (a shipped config that is not an object is ignored, user overrides are merged) and `_audio_init_lines` (a non-list `init` is ignored, blank lines give no command). |
| `test_devices.py` | Every device in `build.sh` is wired into the menu canvas table, the CI workflow, the README and the update-tar docs; the RG35XX SP reuses the RG35XX H's 640x480 layout, has its own `retroarch-rg35xxsp.cfg` (no stick axes / L3 / R3, no hotkeys on missing buttons, no clashes), the build installs `analog: false` for it and never falls back to the RG34XXSP's stick config, and `rgos-launch` appends the SP file on the SP. |
| `test_nativebin.py` | `nativebin`: ELF header parsing, any file name accepted as a port binary, libraries / data / x86 rejected, lib folders next to a port (wrong-arch ones ignored), loader fallback for cards without an execute bit, shipped armhf loader, clear wrong-CPU / garbage messages. |
| `test_launch.py` | `rgos-launch` `pick_core`: a state.json that is not the expected shape (list, null, `"emulators": "a"`, ...) falls back to the system default core instead of crashing. |
| `test_bios.py` | Settings > Missing BIOS check (`biosctl`): required vs optional per selected core, any-one-of PlayStation regions, MD5 "other version", wrong-case names, subfolders (Dolphin `IPL.bin`), second card, missing bios folder, and the screen lines / "put it here" paths. |
| `test_installer.py` | First-boot installer: payload manifest and `mkpayload.py`, the full install into a fake card (cores, PortMaster, folder tree, no `rgos-data`, stamp, payload removal), the options file, an existing PortMaster is kept, a damaged archive fails cleanly and the retry resumes, paths that escape the target / symlinks / wrong checksum / wrong device / too-small ROMS are refused, progress is monotonic, the welcome screen (Install / Power off buttons and their D-pad / hat / A handling), the screen draws in every state, the menu motion (`uimotion.py`: constants, easing and the focus-ring spring checked against the launcher's own, entrance, eased buttons, fades, the loop coming to rest), and the `rgos-session` hook order (including the power-off exit) and `build.sh installer` wiring. |
| `test_system_icons.py` | Per-system icons (RG XMB Games list): every `SYSTEMS` row has a `sys_<id>` icon, an unknown system falls back to the pad, each icon draws inside the 96 px box. |
| `test_pico8.py` | PICO-8: the `pico8` system row (`.p8` / `.p8.png`), fake-08 default and retro8 alternative in the core tables, hidden until a core is installed and listed by the Core Installer, icon and SD folder, `game.p8.png` titles and artwork names drop both extensions, and the ROM scan lists carts but not plain PNGs. |

`helpers.py` loads the real `menu.py` and `rgos-input` for the tests.
| `test_saturn.py` | Sega Saturn: system row and extensions, default / compatible cores, Core Installer offer, icon, SD-card folder, BIOS rules (required only for Beetle Saturn), per-core option namespaces and safe defaults, BIOS/HLE selection, user overrides, and software-rendered Beetle video-driver handling. |
