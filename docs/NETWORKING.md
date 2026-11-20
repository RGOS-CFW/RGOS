# Wi-Fi, Bluetooth and SSH

## Wi-Fi

1. *Settings > Wi-Fi*, pick a network from the scan list (or add a hidden network) and enter the password with the on-screen keyboard.
2. Once connected, the Wi-Fi row shows the status and the SSH row shows the address.
3. DNS is set up from the DHCP lease automatically (`/run/rgos/resolv.conf`).

Set the regulatory country in `/etc/rgos/wifi.json` if your region needs it.

Many handhelds have no battery-backed clock. HTTPS downloads (artwork, PortMaster) can fail with a certificate error until the clock is roughly right; see [ARTWORK.md](ARTWORK.md).

## Bluetooth

*Settings > Bluetooth* turns the adapter on or off and opens the device list, where you can pair controllers, keyboards and headsets. If it says no adapter was found, check `rgos-logs.txt` ([LOGS.md](LOGS.md)).

## SSH and file transfer

Turn it on in *Settings > SSH / file transfer*. Connect from a PC on the same network:

    ssh root@<ip address>
    sftp root@<ip address>

The ROMS card is at `/media/roms`.

- **Default password:** `rgos`. Change it, because anyone on your network can use it while SSH is on.
- **Custom password:** put the new password on one line in `ssh-password.txt` on the boot partition. It is ignored if empty, too long, or if it contains `:`.
- **Key login:** put your public key in `authorized_keys` (or `authorized_keys.txt`) on the boot partition; it is installed for root at start.
- The server is Dropbear on port 22. Turn it off again in the same menu when you are done.

## Copying games over the network

Use any SFTP client (WinSCP, FileZilla, `sftp`) and copy into `/media/roms/roms/<system>/`, then press X in the launcher to rescan.
