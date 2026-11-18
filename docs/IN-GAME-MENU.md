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
