RG OS launcher music

Put bundled launcher music files in this folder before building the image. Supported formats depend on pygame/SDL_mixer: MP3, OGG, WAV, FLAC, MOD, XM, IT and S3M. Tracks are played in shuffled order, without repeating until the current list is exhausted.

For music added after flashing, copy tracks to the ROMS partition's music/ folder (for example /media/roms/music/). Bundled files and SD-card files are both scanned recursively.

Music player
Tools > Music is a PSP-style player for the songs in the ROMS partition's music/ folder (sub folders included, natural sort order). It reads titles, artists, albums, lengths and cover pictures from the files (ID3 for MP3, Vorbis comments for FLAC and Ogg). A track list shows everything; press A on a song for the Now Playing page with cover art, a progress bar and shuffle / repeat. Music keeps playing when you go back to the menus. While the player owns the speaker, the launcher's shuffled background music stays quiet; it returns once you stop.

List: Up/Down select, L/R page, A play, START play/pause, Y shuffle, X repeat, SELECT rescan, B back.
Now Playing: A or START play/pause, Left/Right seek 10 s, L/R previous/next, Y shuffle, X repeat, B back to the list.
