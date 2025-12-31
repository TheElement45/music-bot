# Discord Music Bot

A Python-based Discord bot using `discord.py` to play music from YouTube (and other sources supported by `yt-dlp`) in voice channels. Features interactive controls via buttons on the "Now Playing" message.

## Features

### Core Features
*   Play music from YouTube URLs (videos & playlists) and search queries.
*   Intelligent song queueing system with queue size limits.
*   **Advanced Caching System** - Reduces API calls and improves performance.
*   **Playback History Tracking** - Keep track of recently played songs.

### Interactive Controls
*   Interactive "Now Playing" message with buttons for:
    *   Pause / Resume
    *   Skip Track
    *   Loop (Off / Single Track / Queue)
    *   Shuffle Queue
    *   View Queue
    *   Clear Queue
    *   Leave Voice Channel

### Music Commands
*   Standard text commands for playback control (`-play`, `-skip`, `-pause`, `-resume`, `-stop`).
*   Queue management (`-queue`, `-remove`, `-clear`, `-shuffle`, `-loop`, `-move`).
*   **Volume Control** - Adjust playback volume (0-100%).
*   **History & Previous** - Navigate through playback history
*   **Replay/Restart** - Restart the current song
*   **Lyrics Display** - Fetch and display song lyrics

### Advanced Features
*   **Enhanced Queue Display** - Paginated queue with progress bars and ETAs
*   **Statistics Dashboard** - View bot uptime, cache performance, and more
*   **Configurable Limits** - Max queue size, max song duration
*   **Auto-disconnect** - Bot leaves when alone in voice channel
*   **Log Rotation** - Organized logging with automatic rotation

### Configuration & Performance
*   Centralized configuration via `.env` file
*   Intelligent caching for metadata and stream URLs
*   Graceful shutdown handling
*   Comprehensive error handling and logging

## Prerequisites

*   **Python 3.8+**
*   **pip** (Python package installer)
*   **FFmpeg:** This is **required** for audio playback. You need to install it separately on your system (it's *not* a Python package installed via pip).
    *   **Windows:** Download from the [official FFmpeg website](https://ffmpeg.org/download.html) (get a static build) and add `ffmpeg.exe` to your system's PATH or place it in the bot's root directory.
    *   **Linux (Debian/Ubuntu):** `sudo apt update && sudo apt install ffmpeg`
    *   **macOS (using Homebrew):** `brew install ffmpeg`

## Setup & Installation

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/TheElement45/music-bot
    cd https://github.com/TheElement45/music-bot
    ```

2.  **Create a Virtual Environment (Recommended):**
    ```bash
    python -m venv venv
    # Activate it:
    # Windows
    .\venv\Scripts\activate
    # Linux/macOS
    source venv/bin/activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Create a Discord Bot Application:**
    *   Go to the [Discord Developer Portal](https://discord.com/developers/applications).
    *   Create a "New Application".
    *   Go to the "Bot" tab and click "Add Bot".
    *   **Enable Privileged Gateway Intents:**
        *   `PRESENCE INTENT` (Optional, but good practice if you use presence features)
        *   `SERVER MEMBERS INTENT` (Optional, but good practice if you use member lookups)
        *   `MESSAGE CONTENT INTENT` (**Required** for reading commands like `-play query`).
    *   Copy the **Bot Token** (keep it secret!).

5.  **Configure Environment Variables:**
    *   Copy the example environment file:
        ```bash
        cp .env.example .env
        ```
    *   Edit `.env` and add your bot token:
        ```dotenv
        DISCORD_BOT_TOKEN=YOUR_SECRET_BOT_TOKEN_HERE
        COMMAND_PREFIX=-
        MAX_QUEUE_SIZE=100
        MAX_SONG_DURATION=600
        DEFAULT_VOLUME=75
        ENABLE_LYRICS=True
        ```
    *   See `.env.example` for all available configuration options.

6.  **Invite the Bot:**
    *   Go back to the "General Information" tab in the Developer Portal to find your bot's `APPLICATION ID`.
    *   Go to the "OAuth2" -> "URL Generator" tab.
    *   Select the following scopes:
        *   `bot`
        *   `applications.commands` (Although this bot uses prefix commands, this scope is often useful)
    *   Select the following Bot Permissions:
        *   `View Channels`
        *   `Send Messages`
        *   `Embed Links`
        *   `Attach Files` (Optional, might be needed for some embeds/error messages)
        *   `Read Message History` (To process commands)
        *   `Manage Messages` (For commands like `clear`, `stop`, `skip`, `pause`, `resume` if you restrict them)
        *   `Connect` (To join voice channels)
        *   `Speak` (To play audio)
        *   `Use Voice Activity` (Standard voice permission)
    *   Copy the generated URL and paste it into your browser to invite the bot to your server.

7.  **Run the Bot:**
    ```bash
    python main.py
    ```

## Troubleshooting: YouTube "Sign in to confirm you're not a bot"

If you encounter the error `ERROR: [youtube] NwFVSclD_uc: Sign in to confirm you’re not a bot`, it means YouTube is rate-limiting or blocking the bot's IP. To fix this, you need to provide cookies from a logged-in YouTube account.

### 1. Export Cookies
1.  Install a browser extension like [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/ccmclabmhdceabpgejclgjbmifhbppcb) (Chrome) or [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/) (Firefox).
2.  Go to YouTube and log in.
3.  Use the extension to export cookies for `youtube.com` as a `cookies.txt` file.
4.  Place the `cookies.txt` file in the bot's root directory.

### 2. Configure the Bot
*   **Local Setup:** The bot will automatically detect `cookies.txt` in the root directory.
*   **Docker Setup:** 
    1.  Ensure `cookies.txt` is in the root directory.
    2.  The `docker-compose.yml` is already configured to mount this file.
    3.  Restart the container: `docker-compose up -d --force-recreate`.

## Configuration

Configuration is managed through the `.env` file. Copy `.env.example` to `.env` and customize:

### Required Settings
*   `DISCORD_BOT_TOKEN`: Your unique Discord bot token

### Bot Settings
*   `COMMAND_PREFIX`: Command prefix (default: `-`)
*   `MAX_QUEUE_SIZE`: Maximum songs in queue per guild (0 = unlimited, default: 100)
*   `MAX_SONG_DURATION`: Maximum song length in seconds (0 = unlimited, default: 600)
*   `DEFAULT_VOLUME`: Default playback volume 0-100 (default: 75)

### Feature Flags
*   `ENABLE_LYRICS`: Enable lyrics fetching (default: True)
*   `ENABLE_VOTE_SKIP`: Enable vote-based skip system (default: True)

### Cache Settings
*   `METADATA_CACHE_TTL`: How long to cache song metadata in seconds (default: 3600)
*   `STREAM_URL_CACHE_TTL`: How long to cache stream URLs in seconds (default: 300)
*   `MAX_CACHE_SIZE`: Maximum cached items (default: 500)

### Logging
*   `LOG_LEVEL`: Logging level (default: INFO)
*   `LOG_ROTATION`: When to rotate logs (default: midnight)
*   `LOG_BACKUP_COUNT`: Number of log backups to keep (default: 7)

See `config.py` for all available configuration options.

## Commands

*(Default prefix is `-`)*

### Playback Control

*   `-join`: Makes the bot join your current voice channel.
*   `-leave` / `-disconnect` / `-dc`: Makes the bot leave the voice channel.
*   `-play <url_or_search_query>` / `-p <url_or_search_query>`: Plays a song/playlist or searches YouTube and adds the result(s) to the queue. Starts playback if nothing is playing.
*   `-pause`: Pauses the current song.
*   `-resume` / `-unpause`: Resumes the paused song.
*   `-stop`: Stops playback completely and clears the queue.
*   `-skip` / `-s`: Skips the current song.

### Volume & Effects

*   `-volume [0-100]` / `-vol [0-100]`: View or set playback volume.
*   `-replay` / `-restart`: Restart the current song from the beginning.

### Queue Management

*   `-queue` / `-q`: Shows the current song queue with pagination and progress bars.
*   `-shuffle`: Shuffles the songs currently in the queue.
*   `-remove <index>` / `-rm <index>`: Removes the song at the specified queue index (starting from 1).
*   `-move <from> <to>`: Move a song from one position to another in the queue.
*   `-clear`: Clears all songs from the queue.
*   `-loop`: Toggles loop modes (Off -> Song -> Queue -> Off).

### History & Navigation

*   `-previous` / `-prev` / `-back`: Play the previously played song.
*   `-history`: Show recently played songs (last 10).

### Information & Extras

*   `-nowplaying` / `-np`: Shows details about the currently playing song (static embed).
*   `-lyrics [query]`: Display lyrics for current song or search query.
*   `-stats` / `-botinfo` / `-info`: Show bot statistics (uptime, cache performance, etc.).
*   `-seek <timestamp>`: Jump to a specific time (e.g., 1:30, 90). *Note: Currently displays a placeholder message; full FFmpeg seek implementation is planned for a future update.*

**Note:** Some commands require `Manage Messages` permission.

## Dependencies

*   [discord.py](https://github.com/Rapptz/discord.py) - Python wrapper for the Discord API.
*   [yt-dlp](https://github.com/yt-dlp/yt-dlp) - Feature-rich fork of youtube-dl used for extracting stream URLs.
*   [python-dotenv](https://github.com/theskumar/python-dotenv) - For loading environment variables.
*   [aiohttp](https://github.com/aio-libs/aiohttp) - Async HTTP client for lyrics API.
*   [cachetools](https://github.com/tkem/cachetools) - Caching utilities.
*   [PyNaCl](https://github.com/pyca/pynacl) - Required for voice support in discord.py.
*   [FFmpeg](https://ffmpeg.org/) - External tool for audio encoding/decoding.

## Project Structure

```
music-bot/
├── main.py              # Bot entry point
├── config.py            # Centralized configuration
├── cogs/
│   └── music_cog.py    # Music commands and playback logic
├── utils/
│   ├── __init__.py     # Utils package
│   ├── helpers.py      # Helper functions (formatting, parsing, etc.)
│   ├── cache.py        # Caching system
│   └── lyrics.py       # Lyrics fetching
├── requirements.txt     # Python dependencies
├── .env.example        # Example environment variables
└── README.md           # This file
```

## License

(MIT License)