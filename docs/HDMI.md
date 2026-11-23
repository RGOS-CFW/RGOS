# Mini HDMI output (H700)

RG OS supports the mini-HDMI output on the Anbernic RG34XXSP, RG35XX H and RG35XX SP (Allwinner H700). The feature uses the kernel DRM connector (`HDMI-A-1`) and the existing framebuffer; it does not require a desktop compositor.

## Connect and boot

1. Connect the handheld to the TV or monitor with a mini-HDMI cable **before powering on**.
2. Power on the handheld. When HDMI is detected during boot, the kernel sizes the framebuffer for the external display and the RG OS menu scales to it. RetroArch uses the HDMI display's current mode and HDMI audio when the HDMI connector is active.
3. With no HDMI cable connected at boot, RG OS continues using the built-in screen as usual.

HDMI output is selected at boot. This implementation does not live-switch displays when a cable is inserted or removed after startup. Connect or disconnect the cable while powered off, then boot again.

## Resolution

The default resolution cap is **720p**, which avoids the extra CPU cost of drawing the menu at 1080p. The saved setting is `/var/lib/rgos/display.json`:

```json
{"hdmi": "720p"}
```

Available modes:

| Mode | Kernel mode | Notes |
|---|---|---|
| `720p` | 1280×720 at 60 Hz | Default; recommended |
| `1080p` | 1920×1080 at 60 Hz | Higher load for the H700's CPU-drawn menu |
| `480p` | 720×480 at 60 Hz | Lower-resolution fallback |
| `auto` | TV preferred mode | Removes the RG OS resolution cap |

Change the setting over SSH as root:

```sh
python3 /opt/rgos/hdmictl.py status
python3 /opt/rgos/hdmictl.py set 720p
```

Replace `720p` with `480p`, `1080p` or `auto`. A successful change to the boot configuration requires a restart. The tool updates the `APPEND` lines in `/boot/extlinux/extlinux.conf`, keeps a one-time backup named `extlinux.conf.pre-hdmi`, and stores the selected mode in `/var/lib/rgos/display.json`. The saved choice is reapplied during startup in case an OS update replaces the boot configuration.

To inspect or reapply the saved setting:

```sh
python3 /opt/rgos/hdmictl.py status
python3 /opt/rgos/hdmictl.py boot
```

## Audio and emulators

When the kernel reports HDMI as connected and enabled, RG OS selects the HDMI ALSA playback device for RetroArch. Otherwise, it uses the handheld's built-in audio device. RetroArch is directed to the HDMI connector and uses its current display mode rather than forcing the handheld panel's fixed dimensions.

## Troubleshooting

- **TV says no signal:** power off, connect the cable firmly at both ends, select the TV's correct HDMI input, then power on the handheld.
- **No HDMI connector is detected:** run `python3 /opt/rgos/hdmictl.py status`. The kernel must expose an HDMI connector under `/sys/class/drm`.
- **Black screen or unsupported mode:** connect the handheld's display as usual, SSH in, run `python3 /opt/rgos/hdmictl.py set 720p`, then reboot with the TV connected. If necessary, try `480p`.
- **No sound over HDMI:** check that the TV is connected before boot and inspect `python3 /opt/rgos/hdmictl.py status` for the HDMI audio device.
- **Built-in screen works but TV does not:** verify that the device is one of the supported H700 handhelds and that the TV/cable accepts the selected mode.

The RG Rotate (T618) is not included in this H700 mini-HDMI implementation.
