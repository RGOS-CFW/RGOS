# Launchers, themes, splash and music

## Launchers

Choose one in *Settings > Launcher*. The choice is remembered.

| Launcher | Look |
|---|---|
| **RG OS** (default) | Classic tile launcher |
| **RG XMB** | PlayStation-style cross media bar |
| **RG Classic** | Pixel tile launcher with 3x2 buttons |

All launchers share the same home sections: Games, Recents, Favorites, Tools and Settings, plus Power Off (the XMB shows Settings first). **Tools** holds the File Manager and PortMaster.

While you use the launcher the CPU and GPU clocks are held at `performance` (and put back about 4 seconds after the last input, and always before a game starts), so scrolling does not start on slow clocks. Set `RGOS_UI_BOOST=0` in the environment to turn this off. On the 640x480 handhelds (RG35XX H / SP) only the rows of the 720x540 menu that changed are scaled and written to the screen each frame.

### Startup and big libraries

The launcher keeps the result of the last ROM scan in `scan-cache.json` next to `state.json`. On the next start (including every return from a game) the library is shown at once from that file and a background scan replaces it only if something changed. Game cards are built when they come into view instead of for the whole list, and a game's file size is read when it is selected rather than for every ROM during the scan, so systems with thousands of games open and scroll without a pause. `RGOS_SWITCH_S` (default `0.001`) sets how long a background thread may hold the interpreter before the render loop gets it back.
### Animation

All three launchers animate. RG Classic has its own pixel animation; **RG OS** and **RG XMB** share the same kind of motion:

- **Entrance.** On the home screen, tiles (RG OS) or categories and items (RG XMB) pop in one after another with a small overshoot. It replays whenever you come back to the home screen, for example after a game or a sub-menu.
- **RG OS focus ring.** One focus ring glides between tiles on a damped spring: it hops, stretches along the direction of travel and leaves a short ghost trail on fast moves. At rest it pulses, sweeps a diagonal shine across the tile and twinkles, the selected icon bobs, and the description fades up after each move. Slow embers drift up behind the tiles.
- **RG XMB.** The selected category icon breathes and sends out a ring when picked, with an occasional sparkle. Items slide in from the right in a staggered wave after a category change; the selected item pops, pulses a ring and gets a nudging chevron.

Animation redraws at full speed only while something moves and drops back to the idle frame rate once the screen settles, so it costs nothing when you leave the launcher alone.

## Themes

*Settings > Theme* opens the list; the colours apply to the launchers and the in-game menu.

Midnight (default), Ocean, Forest, Sunset, Purple Haze, Amber Terminal, Game Boy, Paper (light), MustardOS, High Contrast.

## Startup splash

*Settings > Startup splash* cycles between **On** (video and sound), **video only** and **Off**. The splash plays once at power on; **X** previews it.

## Launcher music

Music plays in shuffled order and does not repeat a track until the list has been played through.

- **Bundled** tracks: put files in `music/` in the repository before building the image.
- **Your own** tracks: copy them to `music/` on the ROMS partition (`/media/roms/music/` on the device).
- Both locations are scanned recursively.
- Supported formats depend on pygame/SDL_mixer: MP3, OGG, WAV, FLAC, MOD, XM, IT and S3M.

## Favorites and recents

Press **Y** on a game to favourite it. Favourites are stored in `favorites.txt` on the ROMS partition, so they survive reflashing the system partition and can be edited from a PC. Recents list the games you played last.

## Cover art

See [ARTWORK.md](ARTWORK.md).
