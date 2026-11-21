# Launchers, themes, splash and music

## Launchers

Choose one in *Settings > Launcher*. The choice is remembered.

| Launcher | Look |
|---|---|
| **RG OS** (default) | Classic tile launcher |
| **RG XMB** | PlayStation-style cross media bar |
| **RG Flow** | Carousels for menu, systems and games; cover art on game cards |
| **RG Classic** | Pixel tile launcher with 3x2 buttons |
| **SteamOS** | Steam Deck gaming mode: blurred hero backdrop from the focused game (crossfades as you move), "Recent Games"-style heading, dimmed capsule row with an animated focus ring, green Play button, Y favourite button, SYSTEM / POSITION info columns, 12-hour clock with Wi-Fi and battery icons, and a Deck-style prompt bar (MENU and X on the left, A/B/Y on the right) |

All launchers share the same home sections: Games, Recents, Favorites, Tools and Settings, plus Power Off (the XMB shows Settings first). **Tools** holds the File Manager and PortMaster.

### SteamOS Steam-button menu

Press **MENU** in the SteamOS launcher to slide in the Steam-button panel: a profile header (Online/Offline follows Wi-Fi) and the rows Home, Library, Recent Games, Favorites, Tools, Settings and Power. **Up/Down** move, **A** selects, **B** or **MENU** closes it. The panel opens on the row for the section you are in.

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
