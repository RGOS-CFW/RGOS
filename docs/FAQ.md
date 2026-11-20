# FAQ

**Which devices are supported?** RG34XXSP, RG35XX H, RG35XX SP and RG Rotate ([DEVICES.md](DEVICES.md)).

**Black screen on an H700 console.** Almost always the wrong RAM type (DDR4 vs DDR3) or panel revision. See [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

**Where do my ROMs go?** `<ROMS>/roms/<system>/`. See [SYSTEMS.md](SYSTEMS.md).

**A system is missing from the menu.** Its core is not installed in the image, or the build of that core failed. See [SYSTEMS.md](SYSTEMS.md).

**A game starts then closes.** Read `rgos-retroarch.txt` (or `rgos-native.txt` for ports) on the boot partition. A missing BIOS is a common cause ([BIOS.md](BIOS.md)).

**Buttons are wrong.** *Settings > Swap A / B buttons*, or *Map buttons*.

**Does it support Wii?** No. GameCube only, and only on the RG Rotate ([GAMECUBE.md](GAMECUBE.md)).

**Can I update without reflashing?** Yes. Build an update `.tar` and put it in `update/` on the ROMS partition ([UPDATES.md](UPDATES.md)).

**Does an update change my games and saves?** No. Updates only replace files on the boot partition.

**Do I need to flash anything special on the RG Rotate?** Yes, the SPL, once ([RG-ROTATE-SPL.md](RG-ROTATE-SPL.md)).

**How do I get covers?** [ARTWORK.md](ARTWORK.md).

**How do I run Linux ports?** Use PortMaster from Tools, or drop `.sh` launchers in `roms/ports/` ([PORTS.md](PORTS.md)).

**Is the SSH password safe?** The default is `rgos`; change it or switch SSH off ([NETWORKING.md](NETWORKING.md)).

**Licensing.** RG OS code is MIT licensed; third-party components keep their own licenses (`THIRD-PARTY-NOTICES.md`). RG OS does not provide games or BIOS files.
