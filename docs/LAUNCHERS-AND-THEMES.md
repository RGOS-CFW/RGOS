# Launchers, themes, splash and music

## Launchers

Choose one in *Settings > Launcher*. The choice is remembered.

| Launcher | Look |
|---|---|
| **RG OS** (default) | Classic tile launcher |
| **RG XMB** | PlayStation-style cross media bar |
| **RG Flow** | Carousels for menu, systems and games; cover art on game cards |
| **RG Classic** | Pixel tile launcher with 3x2 buttons |

All launchers share the same home sections: Games, Recents, Favorites, Tools and Settings, plus Power Off (the XMB shows Settings first). **Tools** holds the File Manager and PortMaster.

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
