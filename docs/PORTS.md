# Native Linux ports

RG OS treats files discovered in `roms/ports/` as native Linux ports. They are
launched directly by `rgos-launch`; they do not need a RetroArch core or any
other emulator.

- `.sh` and `.bash` launchers are run with Bash when their shebang requests
  Bash, otherwise with `sh`. This works on exFAT ROMS cards where executable
  permission bits may not be preserved.
- Other files are started as native executables and must have execute
  permission on the filesystem.
- The launcher's working directory is the directory containing the selected
  port, so relative asset paths used by common port launchers continue to work.
- PortMaster comes preinstalled: the image carries a copy that is placed in
  `ROMS/roms/ports/PortMaster` on the first boot where that folder is missing, and
  PortMaster updates itself there. An existing install is never overwritten. Build
  with `PORTMASTER=0` to leave it out, or `PORTMASTER_ZIP=<file>` to build offline.
- PortMaster remains a separate Tools entry. PortMaster-installed ports are
  started through their installed launch scripts, allowing PortMaster to set
  up its own runtime and dependencies; RG OS does not wrap those games in
  RetroArch.

Console ROM folders continue to use the emulator/core configured for their
system. See `rgos-native.log` on the device for native-port output when a port
fails to start.

## Controller mapping

SDL ports only treat a joystick as a game controller when a controller database
entry matches it, so `rgos-launch` gives every native port (and PortMaster) a
mapping for the built-in "RG OS Gamepad". It is exported as
`SDL_GAMECONTROLLERCONFIG`, and also written to `/run/rgos/gamecontrollerdb.txt`
(`SDL_GAMECONTROLLERCONFIG_FILE`) for launchers that replace the variable.

Layout (positional, like an Xbox pad): A bottom, B right, X left, Y top,
L1/R1 shoulders, L2/R2 triggers, Select = back, Start, Menu = guide, L3/R3 stick
clicks, d-pad. The sticks are included only when analog sticks are enabled in
`/etc/rgos/input.json`. The Settings > Swap A / B option applies before SDL sees
the pad, so ports follow it automatically.

To change the mapping, add lines in SDL_GameControllerDB format to
`rgos-gamecontrollerdb.txt`:

- `ROMS/ports/rgos-gamecontrollerdb.txt` applies to every port.
- `rgos-gamecontrollerdb.txt` next to a port applies to that port only and wins.

A line with the same GUID replaces the built-in mapping; the GUID is the first
field of the generated `/run/rgos/gamecontrollerdb.txt`. Lines starting with `#`
are ignored. A mapping already exported in `SDL_GAMECONTROLLERCONFIG` wins over
all of these.

## Quitting a port

Hold **Select + Start** for about 2 seconds to stop the running native port and
return to the menu. RG OS sends the port's whole process group SIGTERM, then
SIGKILL after 3 seconds if it has not exited. The stop is logged in
`rgos-native.log` and is not reported as an error. This also works inside
PortMaster. Ports run in their own session so child processes stop with them.
