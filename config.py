# -*- coding: utf-8 -*-
"""
Configuration file for Discord Music Bot
All configurable settings are centralized here
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ====== Bot Configuration ======
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "-")

# ====== Music Configuration ======
# Maximum queue size per guild (0 = unlimited)
MAX_QUEUE_SIZE = int(os.getenv("MAX_QUEUE_SIZE", "100"))

# Maximum song duration in seconds (0 = unlimited)
MAX_SONG_DURATION = int(os.getenv("MAX_SONG_DURATION", "600"))  # 10 minutes default

# Default volume (0-100)
DEFAULT_VOLUME = int(os.getenv("DEFAULT_VOLUME", "75"))

# Auto-disconnect timeout (seconds when alone in VC)
AUTO_DISCONNECT_TIMEOUT = int(os.getenv("AUTO_DISCONNECT_TIMEOUT", "120"))

# ====== Cache Configuration ======
# Cache TTL for song metadata (seconds)
METADATA_CACHE_TTL = int(os.getenv("METADATA_CACHE_TTL", "3600"))  # 1 hour

# Cache TTL for stream URLs (seconds)
STREAM_URL_CACHE_TTL = int(os.getenv("STREAM_URL_CACHE_TTL", "300"))  # 5 minutes

# Maximum cache size (number of items)
MAX_CACHE_SIZE = int(os.getenv("MAX_CACHE_SIZE", "500"))

# ====== History Configuration ======
# Maximum history size per guild
MAX_HISTORY_SIZE = int(os.getenv("MAX_HISTORY_SIZE", "50"))

# ====== Rate Limiting ======
# Commands per user per minute
RATE_LIMIT_COMMANDS = int(os.getenv("RATE_LIMIT_COMMANDS", "5"))

# Rate limit window (seconds)
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))

# ====== Permissions ======
# DJ role name (leave empty to disable DJ role requirement)
DJ_ROLE_NAME = os.getenv("DJ_ROLE_NAME", "")

# Allow users to bypass DJ requirement if alone with bot
ALONE_BYPASS_DJ = os.getenv("ALONE_BYPASS_DJ", "True").lower() == "true"

# ====== yt-dlp Configuration ======
YDL_BASE_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'skip_download': True,
    'socket_timeout': 30,
}

# ====== FFmpeg Configuration ======
def get_ffmpeg_options(volume: int = DEFAULT_VOLUME, speed: float = 1.0, bass_boost: str = 'off'):
    """
    Generate FFmpeg options with dynamic audio filters
    
    Args:
        volume: Volume level (0-100)
        speed: Playback speed (0.5-2.0)
        bass_boost: Bass boost level ('off', 'low', 'medium', 'high')
    
    Returns:
        dict: FFmpeg options
    """
    # Convert volume from 0-100 to 0-2 scale for FFmpeg
    volume_filter = f"volume={volume/100}"
    
    # Speed adjustment
    speed_filter = f"atempo={speed}" if speed != 1.0 else None
    
    # Bass boost filters
    bass_filters = {
        'off': None,
        'low': 'bass=g=5',
        'medium': 'bass=g=10',
        'high': 'bass=g=15'
    }
    bass_filter = bass_filters.get(bass_boost, None)
    
    # Combine filters
    filters = [f for f in [volume_filter, speed_filter, bass_filter] if f]
    filter_string = ','.join(filters)
    
    return {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': f'-vn -filter:a "{filter_string}"'
    }

# Default FFmpeg options
FFMPEG_OPTIONS = get_ffmpeg_options()

# ====== Embed Colors ======
COLOR_PLAYING = 0x00FF00  # Green
COLOR_QUEUED = 0x0099FF   # Blue
COLOR_ERROR = 0xFF0000    # Red
COLOR_INFO = 0xFFFF00     # Yellow

# ====== Logging Configuration ======
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "logs/discord.log")
LOG_ROTATION = os.getenv("LOG_ROTATION", "midnight")  # midnight, H, D, W0-W6
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "7"))

# ====== Feature Flags ======
ENABLE_LYRICS = os.getenv("ENABLE_LYRICS", "True").lower() == "true"
ENABLE_VOTE_SKIP = os.getenv("ENABLE_VOTE_SKIP", "True").lower() == "true"
VOTE_SKIP_THRESHOLD = float(os.getenv("VOTE_SKIP_THRESHOLD", "0.5"))  # 50%

# ====== API Configuration ======
# Lyrics API (using lyrics.ovh as default)
LYRICS_API_URL = os.getenv("LYRICS_API_URL", "https://api.lyrics.ovh/v1")
