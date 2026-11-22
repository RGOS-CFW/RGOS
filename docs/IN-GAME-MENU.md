# In-game menu

Tap the **Menu** button (the hub's Mode button) while a game is running and a panel slides in from the right with
**Resume, Restart, Save State, Load State, Exit Game**. The game is paused while it is open.

| Button | Action |
| --- | --- |
| D-pad Up / Down | move |
| A (or Start) | select |
| B or Menu | back / resume |

- **Restart** and **Exit Game** ask "Are you sure?" first (Cancel is preselected).
- **Save State** keeps the menu open and shows "State saved"; **Load State** closes the menu and resumes from the state.
  Both are RetroArch only, so native ports show Resume / Restart / Exit Game.
- Only a quick, clean tap opens it. Holding Menu, or pressing another button while it is down, is left to RetroArch's
  hotkey combos (Menu is its hotkey-enable button).
- Select+Start held for 2 s still force-stops a native port.

## DPAD to joystick (Menu + Select)

While a game runs, press **Menu + Select** together:

| Press | Result |
| --- | --- |
| quick press | the device vibrates once and **DPAD to joystick** turns on: D-pad presses move the left stick |
| hold for 1 s | the device vibrates twice and **DPAD to joystick** turns off |

The combo flips the same switch as **Settings > DPAD to joystick**, so the Settings row always shows the current state
and the choice is kept across games and reboots. It only works while a game runs; the launcher keeps its normal D-pad.

- The combo is swallowed: the game never sees Select while Menu is down, and the in-game menu does not open. This
  replaces RetroArch's old Menu + Select hotkey (its menu is still one tap of Menu away).
- Diagonals are scaled like a real stick (both directions held gives about 70 % on each axis); opposite directions cancel.
  A real analog stick, on devices that have one, keeps working and the D-pad wins on an axis while it is pushed.
- Games and cores that read only the digital D-pad (NES, SNES, Game Boy, ...) will not respond to the D-pad while it is
  on. Hold Menu + Select to switch it off again.
- If the device has no vibration motor the combo still works, silently.

## RetroArch gets the same panel as native ports

RetroArch renders through DRM/KMS, so pixels written into `/dev/fb0` never show over a running game. Both the volume bar and the
in-game menu panel therefore go on a hardware overlay plane (`drmplane.py`), which the display controller composites above the
game, for RetroArch exactly as for native ports. While RetroArch is the foreground program (`/run/rgos/ingame` has
`"kind": "retroarch"`):

* **Menu tap** opens the RG OS panel above the game (paused): Resume, Restart, Save State, Load State, Exit Game.
* **Volume** is the bar on the overlay plane (`rgos-overlay`).

If the display has no free overlay plane, the panel falls back to RetroArch's own: a Menu tap sends `MENU_TOGGLE`, which opens RGUI
above the game (paused; tap Menu again to close it; its Quick Menu has Resume, Save State, Load State, Restart and Close Content),
and the volume uses RetroArch's on-screen message (`SHOW_MSG`). The fallback is chosen per game, and the log
(`/var/log/rgos-gamemenu.log`) says `no overlay plane` when it happens. Set `RGOS_GAMEMENU_RGUI=1` to always use RGUI for RetroArch,
and `RGOS_GAMEMENU_DRM=0` to never use a plane for the menu.

## How it works

`rgos-launch` writes `/run/rgos/ingame` as JSON (`kind`, `title`, and for native ports the `pid`). `gamemenu.py daemon`
(started by `rgos-session`) watches the hub pad, and on a tap it grabs the pad (the game stops seeing buttons), pauses
the game and paints the panel into the framebuffer the same way `rgos-overlay` paints the volume bar (the pixels under
it are saved and put back). It uses the colours of the launcher theme.

| | RetroArch | Native ports |
| --- | --- | --- |
| pause / resume | `PAUSE_TOGGLE` (only if not already paused) | `SIGSTOP` / `SIGCONT` to the port's process group |
| restart | `RESET` | stop the port; `rgos-launch` sees `/run/rgos/restart` and starts it again |
| exit | `QUIT` (SIGKILL after 3 s if it hangs) | `SIGTERM`, then `SIGKILL` after 3 s |
| save / load | `SAVE_STATE` / `LOAD_STATE` | not offered |

RetroArch's network commands are already enabled in `config/retroarch*.cfg` (`network_cmd_enable`, port 55355).
Log: `/var/log/rgos-gamemenu.log`.

## Demo video

`python3 tools/render-gamemenu-demo.py out.mp4` renders a demo with the real menu code and a fake RetroArch (needs
Pillow and ffmpeg; no device).

See also: [CONTROLS.md](CONTROLS.md) for RetroArch hotkeys.
