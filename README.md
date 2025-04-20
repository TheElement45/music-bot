# Discord Music Bot

A Python-based Discord bot using `discord.py` to play music from YouTube (and other sources supported by `yt-dlp`) in voice channels. Features interactive controls via buttons on the "Now Playing" message.

## Features

*   Play music from YouTube URLs (videos & playlists) and search queries.
*   Song queueing system.
*   Interactive "Now Playing" message with buttons for:
    *   Pause / Resume
    *   Skip Track
    *   Loop (Off / Single Track / Queue)
    *   Shuffle Queue
    *   View Queue
    *   Clear Queue
    *   Leave Voice Channel
*   Standard text commands for playback control (`-play`, `-skip`, `-pause`, `-resume`, `-stop`).
*   Queue management commands (`-queue`, `-remove`, `-clear`, `-shuffle`, `-loop`).
*   Bot automatically disconnects if left alone in a voice channel.
*   Basic error handling and logging (`discord.log`).
*   Configuration via `.env` file.

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
    git clone <your-repository-url>
    cd <repository-directory>
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
    *   Create a file named `.env` in the root directory of the project.
    *   Add your bot token to this file:
        ```dotenv
        DISCORD_BOT_TOKEN=YOUR_SECRET_BOT_TOKEN_HERE
        ```

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

## Configuration

*   **`.env` file:** Stores the bot token.
    *   `DISCORD_BOT_TOKEN`: Your unique Discord bot token.
*   **`main.py`:**
    *   `COMMAND_PREFIX`: Change the default command prefix (`-`) here if desired.

## Commands

*(Default prefix is `-`)*

**Playback:**

*   `-join`: Makes the bot join your current voice channel.
*   `-leave` / `-dc`: Makes the bot leave the voice channel.
*   `-play <url_or_search_query>` / `-p <url_or_search_query>`: Plays a song/playlist or searches YouTube and adds the result(s) to the queue. Starts playback if nothing is playing.
*   `-pause`: Pauses the current song.
*   `-resume`: Resumes the paused song.
*   `-stop`: Stops playback completely, clears the queue, and makes the bot leave the voice channel.
*   `-skip` / `-s`: Skips the current song.

**Queue Management:**

*   `-queue` / `-q`: Shows the current song queue.
*   `-shuffle`: Shuffles the songs currently in the queue.
*   `-remove <index>` / `-rm <index>`: Removes the song at the specified queue index (starting from 1).
*   `-clear`: Clears all songs from the queue.
*   `-loop`: Toggles loop modes (Off -> Song -> Queue -> Off).

**Information:**

*   `-nowplaying` / `-np`: Shows details about the currently playing song (static embed). *Note: The interactive message sent when a song starts is generally preferred.*

## Dependencies

*   [discord.py](https://github.com/Rapptz/discord.py) - Python wrapper for the Discord API.
*   [yt-dlp](https://github.com/yt-dlp/yt-dlp) - Feature-rich fork of youtube-dl used for extracting stream URLs.
*   [python-dotenv](https://github.com/theskumar/python-dotenv) - For loading environment variables.
*   [PyNaCl](https://github.com/pyca/pynacl) - Required for voice support in discord.py.
*   [FFmpeg](https://ffmpeg.org/) - External tool for audio encoding/decoding.

## License

(MIT License)