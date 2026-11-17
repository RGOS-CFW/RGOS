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
- PortMaster remains a separate Tools entry. PortMaster-installed ports are
  started through their installed launch scripts, allowing PortMaster to set
  up its own runtime and dependencies; RG OS does not wrap those games in
  RetroArch.

Console ROM folders continue to use the emulator/core configured for their
system. See `rgos-native.log` on the device for native-port output when a port
fails to start.
