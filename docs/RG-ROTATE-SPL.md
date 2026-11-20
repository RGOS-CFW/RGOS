# RG Rotate: flashing the SPL

The RG Rotate needs a replacement splloader (SPL) so that it can boot Linux from the SD card. This is done once, from a PC, with the tools in `spl-flasher/`. **Use it only on an Anbernic RG Rotate.**

Contents: `flash-spl.bat` / `flash-spl.sh`, `restore-stock-spl.bat` / `restore-stock-spl.sh`, `spl.img`, the download helpers `fdl1-dl.bin` and `fdl2-dl.bin`, and `spd_dump` for Windows and Linux.

## Flash the SPL

1. Fully power off the console.
2. Windows: double-click `flash-spl.bat`. Linux: run `./flash-spl.sh` (use `sudo` if you get a USB permissions error).
3. While holding the **Home/Back** combo button, plug the console into the PC with a USB-A to USB-C cable.
4. Wait for `SPL flash complete!` or an error message.

## Restore the stock SPL

If the console no longer boots after flashing:

1. Plug it into the PC with a USB-A to USB-C cable.
2. Hold **Power + Volume Down + Home/Back**. Do not let go of Home/Back.
3. Run `restore-stock-spl.bat` (Windows) or `./restore-stock-spl.sh` (Linux, `sudo` if needed).
4. When it finishes you can release Home/Back. If the console stays off, hold only Power and Volume Down until it turns on.

## After flashing

Flash the RG OS image to the card ([GETTING-STARTED.md](GETTING-STARTED.md)). Partition 3 of the card must be the GPT partition named `uboot`; if the console boots Android instead of RG OS, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
