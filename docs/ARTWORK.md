# Game artwork (SteamGridDB)

RG OS can download cover art for your games from [SteamGridDB](https://www.steamgriddb.com).
Covers show in the details panel on the right of the game list.

## Setup

1. Make a free account on steamgriddb.com and copy your API key from
   *Preferences > API*.
2. Connect the console to Wi-Fi (*Settings > Wi-Fi*).
3. Open *Settings > Game artwork*.
4. Choose **SteamGridDB API key** and type the key with the on-screen keyboard.
   Typing 32 characters on a handheld is slow, so there is a shortcut: put a text file called
   `steamgriddb-key.txt` (key on the first line) in the `rgos-data` folder of the ROMS card and it
   is picked up automatically. (A file in the ROMS root from older versions still works.)
5. Choose **Download missing artwork**. Progress is shown on screen; X stops it and a later run
   carries on where it stopped.

## What it does

- Every ROM title is cleaned (region tags removed, "Zelda, The" turned into "The Zelda") and
  searched on SteamGridDB. A result is only used when its name is a close match, so an unknown
  homebrew game gets no cover rather than a wrong one.
- The highest-rated still portrait cover is downloaded (600x900 or similar, no NSFW, humor or
  flashing images) and shrunk so cards load quickly.
- Games with no match are remembered in `artwork/.misses.json` and not asked about again for
  30 days. **Retry games with no match** clears that list.
- The API key is only ever sent to `steamgriddb.com`. Image downloads are accepted only from
  `*.steamgriddb.com` over HTTPS.

## Files

Everything lives on the ROMS card, so you can look at it or edit it from a PC:

    artwork/<system>/<rom file name without extension>.png   (or .jpg)
    artwork/.misses.json
    artwork/overrides.json

- **Your own pictures work.** Drop an image named like the ROM into `artwork/<system>/` and it
  is used. The scraper never overwrites a file that is already there.
- **Wrong or missing match?** `artwork/overrides.json` pins a game to a SteamGridDB game id
  (the number in the game's page URL), for example:

      {"snes/Chrono Trigger (USA)": 5251}

- **Square covers instead of portrait:** create `/etc/rgos/steamgriddb.json` containing
  `{"shape": "square"}` (or `"any"`). The key saved from the menu is stored in the same file.
- **Hide artwork** without deleting it: *Settings > Game artwork > Show artwork on game cards*.

## Troubleshooting

- *"Secure connection failed (is the clock set correctly?)"*: the HTTPS certificate check needs
  a roughly correct date and many handhelds have no battery-backed clock. Set the date, or wait
  for the system clock to sync, and try again. Certificate checking is never turned off.
- *"The API key was rejected"*: re-enter the key, or check it still exists in your SteamGridDB
  preferences.
- *"No internet connection"*: connect Wi-Fi in *Settings > Wi-Fi*.
- *"No internet connection (DNS lookup failed)"* while Wi-Fi shows connected: the image must be built with
  the `/etc/resolv.conf -> /run/rgos/resolv.conf` link (`build.sh` does this). The scraper also asks DNS
  directly as a fallback. Details of every failed request are written to `/var/log/rgos-artwork.log`, which
  is included in `rgos-logs.txt`.

See also: [NETWORKING.md](NETWORKING.md) for Wi-Fi, [SD-CARD-LAYOUT.md](SD-CARD-LAYOUT.md).
