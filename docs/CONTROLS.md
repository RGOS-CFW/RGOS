# Controls and hotkeys

## In the launcher

| Button | Action |
|---|---|
| D-pad | move |
| A | open / run / select |
| B | back |
| X | rescan games (in game lists and the home screens) |
| Y | add or remove a favourite (in a game list) |
| L / R | page up / down in long lists |
| Select + Start (hold) | power off, from the launcher |

The hint line at the bottom of each screen shows the buttons that work there. If A and B are reversed, turn on *Settings > Swap A / B buttons*. If other buttons are wrong, use *Settings > Map buttons*.

## While a RetroArch game runs

**Menu** (the hub's Mode button) is RetroArch's hotkey-enable button. Hold it and press:

| Combo | Action |
|---|---|
| Menu + Start | exit the game |
| Menu + Select | RetroArch menu |
| Menu + R | save state |
| Menu + L | load state |
| Menu + Right / Left | next / previous state slot |
| Menu + R2 (hold) | fast-forward (not on the RG35XX SP) |
| Menu + A | pause |
| Menu + X | screenshot |

**Tapping** Menu on its own (quick, clean press) opens RG OS's in-game menu instead; see [IN-GAME-MENU.md](IN-GAME-MENU.md).

### RG35XX SP

The SP has no analog sticks, L2/R2 or L3/R3. Its RetroArch config uses **Menu + Up** to fast-forward and **Menu + Down** to rewind, and the rest of the combos above are unchanged.

## Native ports

Hold **Select + Start** for about 2 seconds to stop the running port and return to the menu. The port's controls are described in [PORTS.md](PORTS.md). Volume buttons work everywhere and show an on-screen bar.

## Customising

- RetroArch overrides: `<ROMS>/config/retroarch.cfg` is appended last and wins over everything ([NES.md](NES.md)).
- Port controller mapping: `rgos-gamecontrollerdb.txt` ([PORTS.md](PORTS.md)).
- Analog sticks are enabled per device in `/etc/rgos/input-<device>.json`.
